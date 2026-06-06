"""v2.24 SectionStore — JSONL append-only / 章节计数 / 损坏行容错。"""

from __future__ import annotations

import json
import os

import pytest

from sections.section_store import (
    SectionStore,
    TickSection,
    _clear_for_tests,
    get_section_store,
)


@pytest.fixture(autouse=True)
def _clear_stores():
    _clear_for_tests()
    yield
    _clear_for_tests()


def _make_section(*, chapter: int, section: int, **kw) -> TickSection:
    return TickSection(
        chapter=chapter,
        section=section,
        title=kw.get("title", f"{chapter}-{section}"),
        content=kw.get("content", "正文" * 50),
        word_count=kw.get("word_count", 100),
        tick_start=kw.get("tick_start", 0),
        tick_end=kw.get("tick_end", 5),
        tick_count=kw.get("tick_count", 5),
        silent_tick_count=kw.get("silent_tick_count", 0),
        created_at=TickSection.now_iso(),
    )


def test_empty_store_starts_at_1_1(tmp_path):
    store = SectionStore(data_dir=str(tmp_path))
    assert store.next_position() == (1, 1)
    assert store.count() == 0
    assert store.get_last() is None


def test_append_then_next_position_advances_within_chapter(tmp_path):
    store = SectionStore(data_dir=str(tmp_path))
    c1, s1 = store.next_position()
    store.append(_make_section(chapter=c1, section=s1))
    assert store.next_position() == (1, 2)


def test_fifth_section_then_next_starts_new_chapter(tmp_path):
    store = SectionStore(data_dir=str(tmp_path))
    for s in range(1, 6):
        store.append(_make_section(chapter=1, section=s))
    # 满 5 节 — 下一节进 chapter 2
    assert store.next_position() == (2, 1)


def test_append_rejects_non_advancing_position(tmp_path):
    store = SectionStore(data_dir=str(tmp_path))
    store.append(_make_section(chapter=1, section=1))
    with pytest.raises(ValueError):
        # 试图重复写 (1,1)
        store.append(_make_section(chapter=1, section=1))
    with pytest.raises(ValueError):
        # 试图倒退
        store.append(_make_section(chapter=0, section=999))


def test_reload_after_restart_scans_max_position(tmp_path):
    # 先用一个 store 写入
    s1 = SectionStore(data_dir=str(tmp_path))
    s1.append(_make_section(chapter=1, section=1))
    s1.append(_make_section(chapter=1, section=2))
    s1.append(_make_section(chapter=2, section=1))

    # 模拟进程重启 — 新建一个 store, 应当继续 (2, 2)
    s2 = SectionStore(data_dir=str(tmp_path))
    assert s2.next_position() == (2, 2)
    assert s2.count() == 3


def test_corrupted_line_is_skipped_on_scan(tmp_path):
    path = tmp_path / "tick_sections.jsonl"
    good = _make_section(chapter=1, section=1).model_dump_json()
    path.write_text(good + "\n" + "{not json\n" + "\n", encoding="utf-8")

    store = SectionStore(data_dir=str(tmp_path))
    # 好行被识别 → 下一节 (1, 2)
    assert store.next_position() == (1, 2)
    items = store.list_all()
    # list_all 也要跳过坏行
    assert len(items) == 1
    assert items[0].chapter == 1 and items[0].section == 1


def test_list_all_preserves_order(tmp_path):
    store = SectionStore(data_dir=str(tmp_path))
    for c, s in [(1, 1), (1, 2), (1, 3)]:
        store.append(_make_section(chapter=c, section=s))
    items = store.list_all()
    assert [(it.chapter, it.section) for it in items] == [(1, 1), (1, 2), (1, 3)]


def test_get_last_returns_most_recent(tmp_path):
    store = SectionStore(data_dir=str(tmp_path))
    store.append(_make_section(chapter=1, section=1, title="A"))
    store.append(_make_section(chapter=1, section=2, title="B"))
    last = store.get_last()
    assert last is not None
    assert last.title == "B"


def test_appended_content_is_valid_json_per_line(tmp_path):
    store = SectionStore(data_dir=str(tmp_path))
    store.append(_make_section(chapter=1, section=1))
    store.append(_make_section(chapter=1, section=2))
    raw = open(store.jsonl_path, encoding="utf-8").read().strip().split("\n")
    assert len(raw) == 2
    for line in raw:
        payload = json.loads(line)  # 每行必须是合法 JSON
        assert "chapter" in payload and "section" in payload


# ---- per-novel 单例 ---------------------------------------------------------


def test_get_section_store_requires_data_dir_on_first_call():
    with pytest.raises(ValueError):
        get_section_store("nv1")


def test_get_section_store_caches_per_novel(tmp_path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    sa = get_section_store("novel_a", data_dir=str(a_dir))
    sb = get_section_store("novel_b", data_dir=str(b_dir))
    assert sa is not sb
    # 二次取应当返回同一实例 (缓存)
    sa2 = get_section_store("novel_a")
    assert sa is sa2
