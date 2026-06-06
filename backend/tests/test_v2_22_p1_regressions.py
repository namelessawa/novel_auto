"""v2.22 P1 修复回归套件 — 钉死三处缺陷的修复行为。

1. update_llm_config(provider=...) 写入 config.json.llm.provider, 不只是 env。
2. update_llm_config 在非法 provider 下不留下半写状态 (api_key/base_url/model)。
3. KnowledgeGraph.add_relation 端点不存在 → KeyError, 不污染图。
4. POST /api/graph/entities 非法 entity_type → 422 (而非 500)。
5. POST /api/graph/relations 非法 relation_type / 端点缺失 → 422 / 404。
"""

from __future__ import annotations

import importlib
import json
import os

import pytest
from fastapi.testclient import TestClient


_settings_mod = importlib.import_module("config.settings")


@pytest.fixture(autouse=True)
def isolate_config_json(tmp_path, monkeypatch):
    """与 test_llm_config_provider_switch 同等的隔离, 避免污染真实 config.json。"""
    fake_path = tmp_path / "config.json"
    fake_path.write_text(
        json.dumps(
            {"llm": {"api_key": "", "base_url": "", "model": "", "provider": "deepseek"}}
        ),
        encoding="utf-8",
    )

    def _fake_load() -> dict:
        with open(fake_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _fake_save(cfg: dict) -> None:
        with open(fake_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    monkeypatch.setattr(_settings_mod, "_load_config", _fake_load)
    monkeypatch.setattr(_settings_mod, "_save_config", _fake_save)
    yield fake_path


@pytest.fixture
def restore_env_provider():
    saved = os.environ.get("LLM_PROVIDER")
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = saved


# ---------------------------------------------------------------------------
# 1. provider 写盘 — 此前只改 env, 重启 / 二次 resolve 走 config.json 分支拿旧值
# ---------------------------------------------------------------------------

def test_provider_persisted_to_config_json(
    isolate_config_json, restore_env_provider
):
    """provider 切换必须同时更新 config.json.llm.provider, 否则 _resolve_llm_block
    在 api_key 非空时走 config.json 分支只读旧 provider, UI 上"保存成功"实际无效。
    """
    # 模拟用户已通过 UI 写过 api_key (api_key 非空 → 走 config.json 分支)
    _settings_mod.update_llm_config(api_key="sk-test")
    # 现在切 provider
    _settings_mod.update_llm_config(provider="mimo")

    # 直接读盘核对
    with open(isolate_config_json, "r", encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["llm"]["provider"] == "mimo", (
        f"provider 必须落盘 config.json, 实际: {on_disk['llm']}"
    )

    # _resolve_llm_block 走 config.json 分支也应拿到新 provider
    resolved = _settings_mod._resolve_llm_block(on_disk)
    assert resolved["provider"] == "mimo"


# ---------------------------------------------------------------------------
# 2. 原子化 — 非法 provider 必须在写盘前 raise, 不留下半写状态
# ---------------------------------------------------------------------------

def test_invalid_provider_does_not_partial_write(
    isolate_config_json, restore_env_provider
):
    """此前 update_llm_config 先 _save_config 再校验 provider, 非法 provider
    虽然抛 ValueError, 但 api_key/base_url/model 已写入 config.json。
    """
    before = json.loads(isolate_config_json.read_text(encoding="utf-8"))

    with pytest.raises(ValueError, match="非法"):
        _settings_mod.update_llm_config(
            api_key="sk-leaked",
            base_url="https://attacker.example.com",
            model="evil-model",
            provider="openai",  # 非法
        )

    after = json.loads(isolate_config_json.read_text(encoding="utf-8"))
    assert after == before, (
        "非法 provider 必须使整个 update_llm_config 原子失败; "
        f"实际盘上变成 {after}"
    )


# ---------------------------------------------------------------------------
# 3. KnowledgeGraph.add_relation 端点存在性校验
# ---------------------------------------------------------------------------

def test_add_relation_rejects_missing_endpoint():
    from graph.knowledge_graph import KnowledgeGraph
    from memory_system.models import (
        Entity,
        EntityType,
        Relation,
        RelationType,
    )

    kg = KnowledgeGraph()
    kg.add_entity(
        Entity(id="hero", name="主角", entity_type=EntityType.CHARACTER)
    )

    # 目标实体不存在
    with pytest.raises(KeyError, match="target"):
        kg.add_relation(
            Relation(
                source_id="hero",
                target_id="ghost",  # 不存在
                relation_type=RelationType.KNOWS,
            )
        )

    # 源实体不存在
    with pytest.raises(KeyError, match="source"):
        kg.add_relation(
            Relation(
                source_id="phantom",  # 不存在
                target_id="hero",
                relation_type=RelationType.KNOWS,
            )
        )

    # 关键: 图状态必须保持干净 (此前 networkx.add_edge 会自动创建空节点)
    assert {e.id for e in kg.list_entities()} == {"hero"}, (
        "失败的 add_relation 不允许把空节点写进图"
    )


# ---------------------------------------------------------------------------
# 4 + 5. API 层 — 枚举越界 / 端点缺失走 4xx 而非 500
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client(monkeypatch, tmp_path):
    """绑定一个最小可用的 FastAPI app + KnowledgeGraph 双实例 pipeline。"""
    from graph.knowledge_graph import KnowledgeGraph
    from api import routes as routes_mod

    kg = KnowledgeGraph(snapshot_dir=str(tmp_path / "snapshots"))

    class _StubPipeline:
        def __init__(self) -> None:
            self.knowledge_graph = kg

    stub = _StubPipeline()
    monkeypatch.setattr(routes_mod, "get_pipeline", lambda: stub)

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(routes_mod.router)
    return TestClient(app), kg


def test_create_entity_invalid_type_returns_422(api_client):
    client, _kg = api_client
    res = client.post(
        "/api/graph/entities",
        json={
            "id": "x",
            "name": "x",
            "entity_type": "not_a_real_type",
            "attributes": {},
        },
    )
    assert res.status_code == 422, res.text


def test_create_relation_invalid_type_returns_422(api_client):
    client, kg = api_client
    from memory_system.models import Entity, EntityType

    kg.add_entity(Entity(id="a", name="A", entity_type=EntityType.CHARACTER))
    kg.add_entity(Entity(id="b", name="B", entity_type=EntityType.CHARACTER))

    res = client.post(
        "/api/graph/relations",
        json={
            "source_id": "a",
            "target_id": "b",
            "relation_type": "bogus_relation",
            "label": "",
        },
    )
    assert res.status_code == 422, res.text


def test_create_relation_missing_endpoint_returns_404(api_client):
    client, kg = api_client
    from memory_system.models import Entity, EntityType

    kg.add_entity(Entity(id="hero", name="主角", entity_type=EntityType.CHARACTER))

    res = client.post(
        "/api/graph/relations",
        json={
            "source_id": "hero",
            "target_id": "ghost",  # 不存在
            "relation_type": "knows",
            "label": "",
        },
    )
    assert res.status_code == 404, res.text

    # 图状态: 没有 ghost, 也没有任何新边
    entity_ids = {e.id for e in kg.list_entities()}
    assert entity_ids == {"hero"}, f"404 路径不能污染图, 实际: {entity_ids}"


def test_list_entities_invalid_type_returns_422(api_client):
    client, _kg = api_client
    res = client.get("/api/graph/entities", params={"entity_type": "bogus"})
    assert res.status_code == 422, res.text
