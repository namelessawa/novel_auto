"""MemoryCompressor 闭环替换测试 (v2.15)。

旧实现 source_ids=[] → store 不退役旧 L0 → 长跑膨胀。
新实现保证压缩输出携带 source_ids, 且即使 LLM 不标也兜底为整批源 id。

覆盖:
1. _parse_compressed 优先采纳 LLM 给的 original_event_ids, 但只接受真实存在的 (防幻觉)。
2. LLM 未标 source_ids 时, 兜底用整批 fallback_entries.id。
3. 集成: compress → replace_with_compressed 后 store 总条目数下降, 新条目层级正确。
"""

from __future__ import annotations

import asyncio
import os

import pytest

from agents.memory_compressor import MemoryCompressor
from memory.memory_store import PriorityMemoryStore
from memory.summary_tree import SummaryTree
from memory_system.models import MemoryEntry


def _make_l0(id_: str, tick: int) -> MemoryEntry:
    return MemoryEntry(
        id=id_,
        tier="L0",
        original_tick_range=(tick, tick),
        summary=f"事件 {id_} 发生于 tick {tick}",
        involved=["alice"],
        importance=5,
    )


def test_parse_uses_llm_provided_source_ids(tmp_path) -> None:
    """LLM 返回 original_event_ids 时, 解析器应保留这些 id 到 source_ids。"""
    comp = MemoryCompressor(summary_tree=SummaryTree())
    batch = [_make_l0(f"evt_{i}", tick=10 + i) for i in range(3)]
    raw = """{
      "l1_entries": [
        {
          "original_event_ids": ["evt_0", "evt_2"],
          "summary": "alice 在两次场景中行动",
          "involved": ["alice"],
          "importance": 6,
          "tick_range": [10, 12]
        }
      ]
    }"""
    result = comp._parse_compressed(raw, target_tier="L1", fallback_entries=batch)
    assert len(result) == 1
    assert sorted(result[0].source_ids) == ["evt_0", "evt_2"]
    assert result[0].tier == "L1"


def test_parse_filters_hallucinated_ids(tmp_path) -> None:
    """LLM 返回的 source id 不在 batch 中 → 视为幻觉, 过滤掉。

    若过滤后为空, 兜底成整批 id (而不是空, 那会让 store 不退役)。
    """
    comp = MemoryCompressor(summary_tree=SummaryTree())
    batch = [_make_l0("evt_0", tick=10), _make_l0("evt_1", tick=11)]
    raw = """{
      "l1_entries": [
        {
          "original_event_ids": ["evt_999_fake", "evt_hallucination"],
          "summary": "幻觉条目",
          "tick_range": [10, 11]
        }
      ]
    }"""
    result = comp._parse_compressed(raw, target_tier="L1", fallback_entries=batch)
    assert len(result) == 1
    # 全是幻觉 → 兜底成整批
    assert sorted(result[0].source_ids) == ["evt_0", "evt_1"]


def test_parse_fallback_when_no_source_ids(tmp_path) -> None:
    """LLM 完全没标 source ids → 兜底成整批 id。"""
    comp = MemoryCompressor(summary_tree=SummaryTree())
    batch = [_make_l0(f"evt_{i}", tick=10 + i) for i in range(3)]
    raw = """{
      "l1_entries": [
        {
          "summary": "未标 source",
          "tick_range": [10, 12]
        }
      ]
    }"""
    result = comp._parse_compressed(raw, target_tier="L1", fallback_entries=batch)
    assert len(result) == 1
    assert sorted(result[0].source_ids) == ["evt_0", "evt_1", "evt_2"]


def test_compress_then_replace_actually_shrinks_store(tmp_path, mock_llm) -> None:
    """端到端: 3 个旧 L0 → compress → replace_with_compressed → store 数量下降。"""
    store = PriorityMemoryStore(data_dir=str(tmp_path))
    # 注入 3 条 L0, 都"老到足以压缩" (tick_range[1] = 5, 当前 tick=100 → 距 95 > 50)
    for i in range(3):
        store.add(_make_l0(f"evt_{i}", tick=5 + i), current_tick=5 + i)
    assert len(list(store.all_records())) == 3

    comp = MemoryCompressor(summary_tree=SummaryTree())
    mock_llm.set_responses(
        [
            {
                "l1_entries": [
                    {
                        "original_event_ids": ["evt_0", "evt_1", "evt_2"],
                        "summary": "alice 三个连续行动汇总",
                        "involved": ["alice"],
                        "importance": 6,
                        "tick_range": [5, 7],
                    }
                ]
            }
        ]
    )

    out = asyncio.run(
        comp.compress(
            current_tick=100,
            memory_entries=[r.entry for r in store.all_records()],
            open_loop_origin_ids=[],
        )
    )
    assert len(out.l0_to_l1) == 1
    new_l1 = out.l0_to_l1[0]
    assert sorted(new_l1.source_ids) == ["evt_0", "evt_1", "evt_2"]

    # 真正回写
    store.replace_with_compressed(
        source_ids=list(new_l1.source_ids),
        new_entry=new_l1,
        current_tick=100,
    )

    remaining = list(store.all_records())
    assert len(remaining) == 1, "压缩后应只剩 1 条 L1, 旧 L0 已退役"
    assert remaining[0].entry.tier == "L1"
    assert remaining[0].entry.source_ids == new_l1.source_ids
