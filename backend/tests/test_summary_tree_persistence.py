"""SummaryTree 持久化(P0 bug 修复)+ legendize 单元测试。"""

from __future__ import annotations

import asyncio
import os

import pytest

from memory.summary_tree import Legend, SummaryNode, SummaryTree


def test_persist_round_trip_with_pending_leaves(tmp_path) -> None:
    tree = SummaryTree(merge_threshold=10)

    async def add_some():
        await tree.add_section_summary(1, 1, "alice enters town")
        await tree.add_section_summary(1, 2, "alice meets bob")
        await tree.add_section_summary(2, 1, "bob betrays alice")

    asyncio.run(add_some())

    path = str(tmp_path / "summary_tree.json")
    tree.persist_to_disk(path)
    assert os.path.isfile(path)

    tree2 = SummaryTree(merge_threshold=10)
    assert tree2.load_from_disk(path) is True
    assert tree2.leaf_count == 3
    # pending leaves 恢复
    summaries = tree2.get_chapter_summaries(1)
    assert "alice enters town" in summaries
    assert "alice meets bob" in summaries


def test_load_missing_file_starts_fresh(tmp_path) -> None:
    tree = SummaryTree()
    assert tree.load_from_disk(str(tmp_path / "ghost.json")) is False
    assert tree.leaf_count == 0


def test_load_corrupted_file_falls_back(tmp_path) -> None:
    path = str(tmp_path / "corrupt.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write("{ this is not json")

    tree = SummaryTree()
    assert tree.load_from_disk(path) is False
    assert tree.leaf_count == 0


def test_atomic_write_no_partial_on_error(tmp_path, monkeypatch) -> None:
    """模拟磁盘写失败 - 不应留下 .tmp 残骸或半截目标文件。"""
    tree = SummaryTree()
    tree._leaves = [SummaryNode(node_id="ch1_s1", level=0, summary="hi", chapter_range=(1, 1))]

    path = str(tmp_path / "out.json")

    # 模拟 os.replace 失败
    original_replace = os.replace
    call_count = [0]

    def fail_replace(src, dst):
        call_count[0] += 1
        raise OSError("disk full simulation")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        tree.persist_to_disk(path)

    monkeypatch.setattr(os, "replace", original_replace)

    # 目标文件不应存在
    assert not os.path.isfile(path)
    # .tmp 残骸应已清理(prefix .summary_tree_)
    leftovers = [f for f in os.listdir(tmp_path) if f.startswith(".summary_tree_")]
    assert leftovers == []


def test_legendize_calls_llm_and_records(tmp_path, mock_llm) -> None:
    mock_llm.set_responses(["这是一段传说化的内容,有不同流传版本。"])

    tree = SummaryTree()
    tree._leaves = [
        SummaryNode(node_id="ch1_s1", level=0, summary="alice meets bob", chapter_range=(1, 1)),
        SummaryNode(node_id="ch1_s2", level=0, summary="bob's secret revealed", chapter_range=(1, 1)),
    ]

    legend = asyncio.run(tree.legendize(["ch1_s1", "ch1_s2"], classification="folk_tale"))
    assert isinstance(legend, Legend)
    assert tree.legend_count == 1
    assert legend.legendary_form.startswith("这是一段传说化的内容")
    assert legend.original_node_ids == ["ch1_s1", "ch1_s2"]
    assert legend.classification == "folk_tale"


def test_legendize_llm_failure_uses_fallback(tmp_path, monkeypatch) -> None:
    """LLM 抛错时,legendize 不应崩溃,应给出 [传说] 前缀的兜底文本。"""
    import nf_core.llm_client as llm_mod

    async def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(llm_mod.llm_client, "chat", boom)

    tree = SummaryTree()
    tree._leaves = [
        SummaryNode(node_id="ch1_s1", level=0, summary="hero falls", chapter_range=(1, 1))
    ]
    legend = asyncio.run(tree.legendize(["ch1_s1"]))
    assert legend.legendary_form.startswith("[传说]")
    assert tree.legend_count == 1


def test_legendize_unknown_node_raises(tmp_path) -> None:
    tree = SummaryTree()
    with pytest.raises(ValueError, match="找不到任何指定 node_id"):
        asyncio.run(tree.legendize(["ghost_node"]))


def test_prune_nodes_removes_from_all_layers(tmp_path) -> None:
    tree = SummaryTree()
    tree._leaves = [
        SummaryNode(node_id="ch1_s1", level=0, summary="a", chapter_range=(1, 1)),
        SummaryNode(node_id="ch1_s2", level=0, summary="b", chapter_range=(1, 1)),
    ]
    tree._pending_chapter_leaves = [tree._leaves[1]]
    removed = tree.prune_nodes(["ch1_s1", "ch1_s2"])
    # _leaves has 2 + pending has 1 (same ref) = 3 logical removals
    assert removed >= 2
    assert tree.leaf_count == 0


def test_persisted_legends_round_trip(tmp_path, mock_llm) -> None:
    mock_llm.set_responses(["一种说法是英雄飞升,另一种说法是英雄战死。"])
    tree = SummaryTree()
    tree._leaves = [
        SummaryNode(node_id="ch1_s1", level=0, summary="hero ends", chapter_range=(1, 1))
    ]
    asyncio.run(tree.legendize(["ch1_s1"], classification="folk_tale"))

    path = str(tmp_path / "tree.json")
    tree.persist_to_disk(path)

    tree2 = SummaryTree()
    assert tree2.load_from_disk(path) is True
    legends = tree2.get_legends()
    assert len(legends) == 1
    assert "英雄飞升" in legends[0].legendary_form
