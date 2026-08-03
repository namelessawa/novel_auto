"""Phase 6-B iter#F — /api/tick/narratives 加 viewpoint_character_id.

数据源: sidecar JSON ``tick_NNNNNN.meta.json`` 与 ``tick_NNNNNN.txt`` 并列,
Orchestrator 写 narrative 时同时落盘. endpoint 读 .txt 时 best-effort 拼上
sidecar 内 viewpoint_character_id.

锁定:
* 有 sidecar → viewpoint_character_id 字段
* 无 sidecar (旧 narrative / 已删 sidecar) → 字段 None (不抛)
* malformed sidecar → 视为无 sidecar, 字段 None
* 跨多 tick: 每条按 own sidecar 装配
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import tick_routes
from api.tick_routes import router
from memory.tick_state import TickState
from memory_system.models import WorldState
from persistence.tick_db import TickDB


class _StubRuntime:
    def __init__(self, tick_state, tick_db):
        self.tick_state = tick_state
        self.tick_db = tick_db
        self.orchestrator = None


def _write_narrative(
    data_dir: str,
    tick: int,
    text: str,
    *,
    viewpoint: str | None = None,
) -> None:
    narratives_dir = os.path.join(data_dir, "narratives")
    os.makedirs(narratives_dir, exist_ok=True)
    txt_path = os.path.join(narratives_dir, f"tick_{tick:06d}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    if viewpoint is not None:
        meta_path = os.path.join(narratives_dir, f"tick_{tick:06d}.meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"viewpoint_character_id": viewpoint}, f, ensure_ascii=False)


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(router)
    data_dir = str(tmp_path / "novel")
    os.makedirs(data_dir, exist_ok=True)
    ts = TickState(data_dir=data_dir)
    ts.set_world_state(WorldState())
    for _ in range(5):
        ts.advance_tick()
    db = TickDB(str(tmp_path / "ticks.db"))
    stub_rt = _StubRuntime(tick_state=ts, tick_db=db)
    app.dependency_overrides[tick_routes._resolve_runtime] = lambda: stub_rt
    with TestClient(app) as test_client:
        yield test_client, data_dir, db
    app.dependency_overrides.clear()
    db.close()


def test_viewpoint_included_when_sidecar_present(client) -> None:
    c, data_dir, _ = client
    _write_narrative(data_dir, tick=1, text="苏默走进档案馆。", viewpoint="char_su_mo")
    body = c.get("/api/tick/narratives").json()
    assert body["count"] == 1
    row = body["narratives"][0]
    assert row["viewpoint_character_id"] == "char_su_mo"
    assert row["text"] == "苏默走进档案馆。"


def test_viewpoint_none_when_sidecar_missing(client) -> None:
    """旧 narrative (无 sidecar) → viewpoint_character_id is None."""
    c, data_dir, _ = client
    _write_narrative(data_dir, tick=2, text="孤立段落, 没 sidecar.")
    body = c.get("/api/tick/narratives").json()
    assert body["narratives"][0]["viewpoint_character_id"] is None


def test_viewpoint_none_when_sidecar_malformed(client) -> None:
    """malformed sidecar (不是合法 JSON) → 视为无 sidecar, 不抛."""
    c, data_dir, _ = client
    _write_narrative(data_dir, tick=3, text="坏 sidecar 的段落.")
    meta_path = os.path.join(data_dir, "narratives", "tick_000003.meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write("not-json")

    body = c.get("/api/tick/narratives").json()
    assert body["narratives"][0]["viewpoint_character_id"] is None


def test_viewpoint_mixed_some_with_some_without(client) -> None:
    """Multi-tick: 每条按自己的 sidecar 装配."""
    c, data_dir, _ = client
    _write_narrative(data_dir, tick=1, text="t1", viewpoint="char_a")
    _write_narrative(data_dir, tick=2, text="t2")  # 无 sidecar
    _write_narrative(data_dir, tick=3, text="t3", viewpoint="char_b")
    body = c.get("/api/tick/narratives").json()
    mapping = {n["tick"]: n["viewpoint_character_id"] for n in body["narratives"]}
    assert mapping == {1: "char_a", 2: None, 3: "char_b"}


def test_viewpoint_sidecar_missing_field_returns_none(client) -> None:
    """sidecar 合法 JSON 但缺 viewpoint_character_id 字段 → None."""
    c, data_dir, _ = client
    _write_narrative(data_dir, tick=4, text="t4")
    meta_path = os.path.join(data_dir, "narratives", "tick_000004.meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"other_field": "x"}, f)
    body = c.get("/api/tick/narratives").json()
    assert body["narratives"][0]["viewpoint_character_id"] is None


def test_viewpoint_does_not_break_legacy_fields(client) -> None:
    """加 viewpoint 不影响 tick/text/char_count/world_time 现有字段."""
    c, data_dir, _ = client
    _write_narrative(data_dir, tick=1, text="一二三", viewpoint="char_x")
    body = c.get("/api/tick/narratives").json()
    row = body["narratives"][0]
    assert row["tick"] == 1
    assert row["text"] == "一二三"
    assert row["char_count"] == 3
    assert "world_time" in row  # 已有字段不丢
