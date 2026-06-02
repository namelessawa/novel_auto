"""Tests for PriorityMemoryStore — 多因子检索 + 持久化 + 保护机制。"""

from __future__ import annotations

import pytest

from memory.memory_store import (
    PriorityMemoryStore,
    RetrievalQuery,
    TRAUMA_TAGS,
)
from memory_system.models import MemoryEntry


def _entry(
    eid: str,
    tier: str = "L0",
    importance: int = 5,
    involved: list[str] | None = None,
    tags: list[str] | None = None,
    summary: str = "",
    tick_end: int = 0,
    protected: str | None = None,
) -> MemoryEntry:
    return MemoryEntry(
        id=eid,
        tier=tier,  # type: ignore[arg-type]
        original_tick_range=(max(0, tick_end - 1), tick_end),
        summary=summary or eid,
        emotional_tags=tags or [],
        involved=involved or [],
        importance=importance,
        protected_reason=protected,
    )


# ---------------------------------------------------------------------------
# 基础 CRUD
# ---------------------------------------------------------------------------


def test_add_and_get(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    e = _entry("m1", importance=7)
    store.add(e, current_tick=10)
    rec = store.get("m1")
    assert rec is not None
    assert rec.entry.importance == 7
    assert rec.last_access_tick == 10


def test_size_and_by_tier(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("a", tier="L0"))
    store.add(_entry("b", tier="L1"))
    store.add(_entry("c", tier="L1"))
    assert store.size == 3
    assert len(store.by_tier("L1")) == 2


def test_add_overwrites_entry_keeps_runtime(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("m1", importance=5), current_tick=10)
    store.touch("m1", current_tick=20)  # ref_count=1, last=20
    store.add(_entry("m1", importance=8))  # 覆盖 entry, runtime 保留
    rec = store.get("m1")
    assert rec.entry.importance == 8
    assert rec.reference_count == 1
    assert rec.last_access_tick == 20


# ---------------------------------------------------------------------------
# 保护机制
# ---------------------------------------------------------------------------


def test_protected_by_reason(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("m1", protected="open_loop_origin"))
    rec = store.get("m1")
    assert rec.is_protected


def test_protected_by_trauma_tag(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("m1", tags=list(TRAUMA_TAGS)[:1]))
    rec = store.get("m1")
    assert rec.is_protected


def test_protected_by_high_reference_count(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("m1"))
    for t in (10, 20, 30):
        store.touch("m1", current_tick=t)
    rec = store.get("m1")
    assert rec.is_protected  # ref_count >= 3


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def test_save_load_roundtrip(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("m1", importance=7), current_tick=5)
    store.touch("m1", current_tick=15)
    store.save()

    fresh = PriorityMemoryStore(str(tmp_path))
    assert fresh.load() is True
    rec = fresh.get("m1")
    assert rec is not None
    assert rec.entry.importance == 7
    assert rec.reference_count == 1
    assert rec.last_access_tick == 15


def test_load_missing_file_returns_false(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    assert store.load() is False


# ---------------------------------------------------------------------------
# 多因子检索 — 防退化
# ---------------------------------------------------------------------------


def test_retrieve_ranks_by_char_overlap(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("m1", involved=["alice"], tick_end=10))
    store.add(_entry("m2", involved=["bob"], tick_end=10))
    store.add(_entry("m3", involved=["alice", "bob"], tick_end=10))

    q = RetrievalQuery(current_tick=20, query_chars=["alice"], top_k=3)
    results = store.retrieve(q)
    assert results[0].record.entry.id in {"m1", "m3"}
    # bob-only 应排最后
    ids = [r.record.entry.id for r in results]
    assert ids.index("m2") > ids.index("m1")


def test_retrieve_respects_tier_filter(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("a", tier="L0"))
    store.add(_entry("b", tier="L3"))
    q = RetrievalQuery(current_tick=10, tier_filter=["L0"], top_k=5)
    results = store.retrieve(q)
    assert {r.record.entry.id for r in results} == {"a"}


def test_retrieve_enforces_min_l0_l1(tmp_path) -> None:
    """避免"全是 L3"的退化 — 必须至少包含 N 条近期层。"""
    store = PriorityMemoryStore(str(tmp_path))
    # 6 条 L3 高 importance + 2 条 L0 低 importance
    for i in range(6):
        store.add(
            _entry(f"l3_{i}", tier="L3", importance=9, summary=f"传说{i}"),
            current_tick=0,
        )
    store.add(_entry("l0_a", tier="L0", importance=3), current_tick=99)
    store.add(_entry("l0_b", tier="L0", importance=3), current_tick=99)

    q = RetrievalQuery(current_tick=100, top_k=5, min_l0_or_l1=2)
    results = store.retrieve(q)
    tiers = [r.record.entry.tier for r in results]
    assert tiers.count("L0") + tiers.count("L1") >= 2


def test_retrieve_dedup_overlapping_involved_and_ticks(tmp_path) -> None:
    """同 involved + 邻近 tick_range → 只保留 score 最高的一条。"""
    store = PriorityMemoryStore(str(tmp_path))
    store.add(
        _entry("a1", involved=["alice"], tick_end=20, importance=8),
        current_tick=20,
    )
    store.add(
        _entry("a2", involved=["alice"], tick_end=21, importance=5),
        current_tick=20,
    )
    store.add(
        _entry("b1", involved=["bob"], tick_end=20, importance=5),
        current_tick=20,
    )
    q = RetrievalQuery(current_tick=22, query_chars=["alice", "bob"], top_k=10)
    results = store.retrieve(q)
    ids = {r.record.entry.id for r in results}
    # a1 和 a2 是 同 involved + 邻近 tick → 应只保留一个 (score 高的 a1)
    assert "a1" in ids
    assert "a2" not in ids
    assert "b1" in ids


def test_retrieve_recency_decays(tmp_path) -> None:
    """长时间未访问的条目 importance 会被衰减。"""
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("old", importance=8, tick_end=0), current_tick=0)
    store.add(_entry("new", importance=5, tick_end=300), current_tick=300)

    q = RetrievalQuery(current_tick=400, top_k=2)
    results = store.retrieve(q)
    # 新条目 recency 高, 应该排第一
    assert results[0].record.entry.id == "new"


def test_protected_entries_get_score_bonus(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("plain", importance=5, tick_end=0), current_tick=0)
    store.add(
        _entry("protected", importance=5, tick_end=0, protected="origin"),
        current_tick=0,
    )
    q = RetrievalQuery(current_tick=500, top_k=2)
    results = store.retrieve(q)
    # protected 享受 +2 加成, 又是 tier=L0, 应排第一
    assert results[0].record.entry.id == "protected"


# ---------------------------------------------------------------------------
# 升级与替换 (MemoryCompressor 协议)
# ---------------------------------------------------------------------------


def test_expired_below_tier(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("recent", tier="L0", tick_end=90), current_tick=90)
    store.add(_entry("old", tier="L0", tick_end=10), current_tick=10)
    store.add(_entry("protected_old", tier="L0", tick_end=10, protected="origin"))

    expired = store.expired_below_tier(current_tick=100, tier="L0", boundary=50)
    ids = {r.entry.id for r in expired}
    assert ids == {"old"}  # recent (距今 10) 不过期, protected_old 受保护


def test_replace_with_compressed_inherits_refs(tmp_path) -> None:
    store = PriorityMemoryStore(str(tmp_path))
    store.add(_entry("l0_a", tier="L0"))
    store.add(_entry("l0_b", tier="L0"))
    store.touch("l0_a", current_tick=10)
    store.touch("l0_a", current_tick=20)
    store.touch("l0_b", current_tick=30)

    new_l1 = _entry("l1_x", tier="L1")
    new_rec = store.replace_with_compressed(
        source_ids=["l0_a", "l0_b"], new_entry=new_l1, current_tick=100
    )
    assert store.get("l0_a") is None
    assert store.get("l0_b") is None
    assert new_rec.reference_count == 3  # 2 + 1
    assert new_rec.entry.tier == "L1"


# ---------------------------------------------------------------------------
# 综合 — 模拟"长记忆崩塌"场景
# ---------------------------------------------------------------------------


def test_long_running_does_not_lose_protected_facts(tmp_path) -> None:
    """模拟运行 5000 tick: 保护条目 (trauma + open_loop) 必须仍可被检索到。"""
    store = PriorityMemoryStore(str(tmp_path))
    # 关键事件 (trauma) 在 tick 50
    store.add(
        _entry(
            "trauma_event",
            tier="L0",
            importance=8,
            tags=["trauma"],
            involved=["alice"],
            tick_end=50,
            summary="alice 失去了父亲",
        ),
        current_tick=50,
    )
    # 海量普通条目填充, 保证检索时主要候选项变多
    for i in range(100):
        store.add(
            _entry(
                f"daily_{i}",
                tier="L0",
                importance=3,
                tick_end=100 + i,
                involved=["alice"],
                summary=f"日常 {i}",
            ),
            current_tick=100 + i,
        )
    q = RetrievalQuery(
        current_tick=5000,
        query_chars=["alice"],
        query_tags=["trauma"],
        top_k=5,
    )
    results = store.retrieve(q)
    ids = [r.record.entry.id for r in results]
    assert "trauma_event" in ids  # 必须仍能被召回, 不被遗忘
