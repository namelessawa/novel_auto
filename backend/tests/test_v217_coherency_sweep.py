"""v2.17 runtime-coherency sweep — 单元测试覆盖 5 项后端修复。

Fix 编号对齐用户提出的关键问题清单:
1. 启动时对齐 active novel (main.py + routes.py + novel_manager)
2. LLM 配置热更新 (settings.py + llm_client.py)
3. TokenBudget 调用前硬拦截 (token_budget.py + llm_client.py)
5. agent_routes tick 字段对齐 (persistence/tick_db.py)
6. legacy pipeline 持久化补全 (pipeline/engine.py)

Fix 4(前端 Tick 控制台)由 npm run build + 真实 LLM 集成测试覆盖。
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import patch

import pytest

import novel_manager
from memory_system.models import Event, EntityType, TickSummary
from persistence.tick_db import TickDB


# ---------------------------------------------------------------------------
# Fix 1 — 启动默认 novel 解析
# ---------------------------------------------------------------------------


def _redirect_novels_dir(monkeypatch, tmp_path) -> None:
    novels_dir = tmp_path / "novels"
    novels_dir.mkdir()
    monkeypatch.setattr(novel_manager, "_NOVELS_DIR", str(novels_dir))
    monkeypatch.setattr(
        novel_manager, "_MANIFEST_PATH", str(novels_dir / "manifest.json")
    )


def test_resolve_default_returns_manifest_first_when_present(tmp_path, monkeypatch):
    _redirect_novels_dir(monkeypatch, tmp_path)
    a = novel_manager.create_novel("A")
    b = novel_manager.create_novel("B")
    # 后建的也存在,但 resolve 应当返回 manifest 第一项
    assert novel_manager.resolve_default_novel_id() == a["id"]
    # 第二次调用幂等,不会创建新条目
    assert novel_manager.resolve_default_novel_id() == a["id"]
    entries = novel_manager.list_novels()
    assert {e["id"] for e in entries} == {a["id"], b["id"]}


def test_resolve_default_creates_when_empty(tmp_path, monkeypatch):
    _redirect_novels_dir(monkeypatch, tmp_path)
    assert novel_manager.list_novels() == []
    nid = novel_manager.resolve_default_novel_id()
    entries = novel_manager.list_novels()
    assert len(entries) == 1
    assert entries[0]["id"] == nid


def test_set_active_novel_id_realigns_legacy_pipeline(tmp_path, monkeypatch):
    """set_active_novel_id 必须重置 legacy pipeline 单例 + 更新 active id。"""
    _redirect_novels_dir(monkeypatch, tmp_path)
    n = novel_manager.create_novel("A")

    import api.routes as routes

    # 模拟启动前: _active_novel_id=None, _pipeline=None
    monkeypatch.setattr(routes, "_active_novel_id", None)
    monkeypatch.setattr(routes, "_pipeline", None)

    routes.set_active_novel_id(n["id"])
    assert routes._active_novel_id == n["id"]

    # 同一 id 再次设置应为 no-op,不重置 pipeline
    class DummyPipe:
        def save_state(self):
            self.saved = True

    fake_pipe = DummyPipe()
    monkeypatch.setattr(routes, "_pipeline", fake_pipe)
    routes.set_active_novel_id(n["id"])
    assert routes._pipeline is fake_pipe  # 未触发重置

    # 不同 id 触发 save + 清空 pipeline
    n2 = novel_manager.create_novel("B")
    routes.set_active_novel_id(n2["id"])
    assert getattr(fake_pipe, "saved", False) is True
    assert routes._pipeline is None
    assert routes._active_novel_id == n2["id"]


# ---------------------------------------------------------------------------
# Fix 2 — LLM 配置热更新
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_client_isolated():
    """每个用例独立 — 测试结束后用启动期 settings 显式还原 _client/_model。"""
    import nf_core.llm_client as llm_module
    from config.settings import settings as _live

    saved = (_live.deepseek_api_key, _live.deepseek_base_url, _live.deepseek_model)
    yield llm_module
    llm_module.llm_client.reload(
        api_key=saved[0], base_url=saved[1], model=saved[2]
    )


def test_llm_client_reload_explicit_params(llm_client_isolated):
    """显式传 api_key/base_url/model 时, 立即生效, 不读 config.json。"""
    llm_module = llm_client_isolated

    old_client = llm_module.llm_client._client
    applied = llm_module.llm_client.reload(
        api_key="sk-hot-reload",
        base_url="https://example.test/v1",
        model="custom-model-x",
    )
    assert applied["base_url"] == "https://example.test/v1"
    assert applied["model"] == "custom-model-x"
    assert llm_module.llm_client._model == "custom-model-x"
    assert llm_module.llm_client._client is not old_client


def test_llm_client_reload_picks_up_config_json_change(monkeypatch, llm_client_isolated):
    """reload() 无参时必须重读 resolve_llm_block_now 的结果。"""
    import sys
    # NOTE: ``config/__init__.py`` 用 ``from .settings import settings`` 把
    # ``config.settings`` 这个属性名劫持成了 Settings 实例 — 所以
    # ``import config.settings as cfg_mod`` 会拿到 Settings 实例, 不是模块。
    # 用 sys.modules 显式取出真正的子模块对象。
    cfg_mod = sys.modules["config.settings"]
    llm_module = llm_client_isolated

    fake_block = {
        "api_key": "sk-from-reload",
        "base_url": "https://hot.example.com/v1",
        "model": "hot-model",
        "provider": "custom",
        "timeout": 60,
        "source": "config.json",
    }
    monkeypatch.setattr(cfg_mod, "resolve_llm_block_now", lambda: fake_block)

    applied = llm_module.llm_client.reload()
    assert applied["base_url"] == "https://hot.example.com/v1"
    assert applied["model"] == "hot-model"
    assert applied["source"] == "config.json"
    assert llm_module.llm_client._model == "hot-model"


# ---------------------------------------------------------------------------
# Fix 3 — TokenBudget 调用前硬拦截
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_raises_budget_exceeded_when_over_limit(monkeypatch):
    """累计超额时,medium/optional 必须被拦截在 OpenAI 调用之前。"""
    import nf_core.llm_client as llm_module
    from nf_core.token_budget import (
        BudgetExceeded,
        TokenBudgetTracker,
        set_global_tracker,
    )

    tracker = TokenBudgetTracker(max_total_tokens=1000)
    tracker.record(
        agent_id="x",
        priority="medium",
        prompt_tokens=950,
        completion_tokens=0,
    )
    set_global_tracker(tracker)

    api_called = {"count": 0}

    async def boom_if_called(**kw):
        api_called["count"] += 1
        raise AssertionError("OpenAI 不应被调用 — 应在 budget 检查处拦截")

    monkeypatch.setattr(
        llm_module.llm_client._client.chat.completions, "create", boom_if_called
    )

    with pytest.raises(BudgetExceeded) as info:
        await llm_module.llm_client.chat(
            system_prompt="sys",
            user_prompt="usr",
            agent_id="novelty_critic",
            priority="optional",
            max_tokens=200,
        )
    assert info.value.agent_id == "novelty_critic"
    assert info.value.priority == "optional"
    assert api_called["count"] == 0


@pytest.mark.asyncio
async def test_chat_critical_priority_always_proceeds(monkeypatch):
    """critical 即使爆预算也必须放行 — Narrator/Guardian 不可掐断。"""
    import nf_core.llm_client as llm_module
    from nf_core.token_budget import (
        TokenBudgetTracker,
        set_global_tracker,
    )

    tracker = TokenBudgetTracker(max_total_tokens=1)  # 立即爆
    tracker.record(
        agent_id="x", priority="medium", prompt_tokens=999, completion_tokens=0
    )
    set_global_tracker(tracker)

    async def fake_create(**kw):
        class _Choice:
            class message:
                content = "ok"

        class _Usage:
            prompt_tokens = 1
            completion_tokens = 1

        class _R:
            choices = [_Choice()]
            usage = _Usage()

        return _R()

    monkeypatch.setattr(
        llm_module.llm_client._client.chat.completions, "create", fake_create
    )

    # 不应抛 BudgetExceeded
    resp = await llm_module.llm_client.chat(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="narrator",
        priority="critical",
        max_tokens=100,
    )
    assert resp.content == "ok"


@pytest.mark.asyncio
async def test_chat_no_budget_limit_allows_everything(monkeypatch):
    """未设上限的 tracker 不应拦截任何调用 — 默认行为不变。"""
    import nf_core.llm_client as llm_module
    from nf_core.token_budget import TokenBudgetTracker, set_global_tracker

    set_global_tracker(TokenBudgetTracker())  # 无 max_total_tokens

    async def fake_create(**kw):
        class _Choice:
            class message:
                content = "ok"

        class _Usage:
            prompt_tokens = 10
            completion_tokens = 10

        class _R:
            choices = [_Choice()]
            usage = _Usage()

        return _R()

    monkeypatch.setattr(
        llm_module.llm_client._client.chat.completions, "create", fake_create
    )

    resp = await llm_module.llm_client.chat(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="x",
        priority="optional",
        max_tokens=999_999,
    )
    assert resp.content == "ok"


# ---------------------------------------------------------------------------
# Fix 5 — TickDB tick 别名
# ---------------------------------------------------------------------------


def test_tick_db_row_to_dict_exposes_tick_alias(tmp_path):
    """get_recent_ticks() 返回的行必须同时含 tick 与 tick_id。"""
    db = TickDB(db_path=str(tmp_path / "ticks.db"))
    summary = TickSummary(
        tick=42,
        world_time=420,
        agents_called=["Orchestrator", "NarratorAgent"],
        events_generated=["evt_1"],
        narrator_produced_text=True,
        narrator_output_chars=120,
        state_changes_summary="alice 离开山顶",
        world_time_advanced="+1 小时",
        next_tick_recommendations=["弱化天气线"],
    )
    db.insert_tick(summary)

    rows = db.get_recent_ticks(n=5)
    assert len(rows) == 1
    row = rows[0]
    assert row["tick_id"] == 42  # SQL 原列
    assert row["tick"] == 42  # 应用层别名
    assert row["narrator_produced"] == 1  # SQL 整数
    assert row["narrator_produced_text"] is True  # 应用层 bool 别名
    assert row["narrator_chars"] == 120
    assert row["narrator_output_chars"] == 120  # 应用层别名
    assert isinstance(row["events_generated"], list)
    db.close()


def test_agent_routes_scan_last_invoked_finds_with_alias(tmp_path):
    """以前的 bug: agent_routes 用 row.get('tick') 始终是 None。

    这个测试通过 _scan_last_invoked 间接验证: 必须返回非 None 的 tick 字段。
    """
    import api.tick_routes as tick_routes
    from api.agent_routes import _scan_last_invoked

    db = TickDB(db_path=str(tmp_path / "ticks.db"))
    summary = TickSummary(
        tick=7,
        world_time=70,
        agents_called=["NarratorAgent"],
        narrator_produced_text=True,
        narrator_output_chars=200,
    )
    db.insert_tick(summary)
    tick_routes._container.tick_db = db

    try:
        info = _scan_last_invoked("narrator_agent")
        assert info is not None
        assert info["tick"] == 7
        assert info["narrator_produced"] is True
    finally:
        tick_routes._container.tick_db = None
        db.close()


# ---------------------------------------------------------------------------
# Fix 6 — legacy pipeline 持久化补全
# ---------------------------------------------------------------------------


def test_pipeline_save_state_persists_summary_tree(tmp_path):
    from memory_system.models import Section
    from pipeline.engine import GenerationPipeline

    p = GenerationPipeline(data_dir=str(tmp_path))
    # 模拟生成过一节
    p._generated_sections.append(
        Section(
            chapter=1,
            section=1,
            title="开端",
            content="abc",
            summary="一段摘要",
            word_count=3,
        )
    )

    async def add():
        await p.summary_tree.add_section_summary(1, 1, "一段摘要")

    asyncio.run(add())

    p.save_state()
    tree_path = tmp_path / "summary_tree_legacy.json"
    assert tree_path.is_file()
    data = json.loads(tree_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert any(
        "一段摘要" in (leaf.get("summary") or "")
        for leaf in data.get("pending_chapter_leaves", []) + data.get("leaves", [])
    )


def test_pipeline_load_state_restores_summary_tree(tmp_path):
    from memory_system.models import Section
    from pipeline.engine import GenerationPipeline

    # 第一次写盘
    p1 = GenerationPipeline(data_dir=str(tmp_path))
    p1._generated_sections.append(
        Section(chapter=1, section=1, title="开端", content="x", word_count=1)
    )

    async def add():
        await p1.summary_tree.add_section_summary(1, 1, "alice meets dragon")

    asyncio.run(add())
    p1.save_state()

    # 模拟重启 — 新 pipeline 实例从同一 data_dir 读回
    p2 = GenerationPipeline(data_dir=str(tmp_path))
    assert p2.summary_tree.leaf_count == 0  # init 时是空
    p2.load_state()
    assert p2.summary_tree.leaf_count == 1
    summaries = p2.summary_tree.get_chapter_summaries(1)
    assert "alice meets dragon" in summaries
    assert p2.current_chapter == 1


def test_pipeline_load_state_restores_kg_from_snapshot(tmp_path):
    """load_state 必须 rollback 到最新 KG 快照 — 否则 entity_states 全空。"""
    from memory_system.models import Entity, Section
    from pipeline.engine import GenerationPipeline

    p1 = GenerationPipeline(data_dir=str(tmp_path))
    # 加一个实体
    p1.knowledge_graph.add_entity(
        Entity(id="alice", name="Alice", entity_type=EntityType.CHARACTER)
    )
    p1.knowledge_graph.take_snapshot(1)
    p1._generated_sections.append(
        Section(chapter=1, section=1, title="t", content="c", word_count=1)
    )
    p1.save_state()  # 这里会再补一次快照,以最新为准

    # 重启
    p2 = GenerationPipeline(data_dir=str(tmp_path))
    assert p2.knowledge_graph.get_entity("alice") is None
    p2.load_state()
    e = p2.knowledge_graph.get_entity("alice")
    assert e is not None and e.name == "Alice"


def test_pipeline_load_state_without_state_json_still_restores_kg(tmp_path):
    """即使 state.json 不存在,只要 KG snapshot 在,也要恢复。

    场景: tick 流水线创建的小说在数据目录里有 snapshot,但用户从未走过 legacy
    pipeline → state.json 缺失。legacy pipeline 仍应看到已有实体。
    """
    from memory_system.models import Entity
    from pipeline.engine import GenerationPipeline

    p1 = GenerationPipeline(data_dir=str(tmp_path))
    p1.knowledge_graph.add_entity(
        Entity(id="bob", name="Bob", entity_type=EntityType.CHARACTER)
    )
    p1.knowledge_graph.take_snapshot(1)
    # 故意不调 save_state — 模拟 tick 流水线产物

    p2 = GenerationPipeline(data_dir=str(tmp_path))
    p2.load_state()
    e = p2.knowledge_graph.get_entity("bob")
    assert e is not None
