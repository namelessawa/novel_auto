"""v2.24 — section_routes executor 集成路径。

不起 FastAPI server, 直接调 ``_make_section_executor`` (route handler 的内核),
用 fake Orchestrator + tmp_path 的 SectionStore 验证完整切节流程。
"""

from __future__ import annotations

import asyncio
import os

import pytest

from agents.narrator_agent import NarratorOutput
from agents.section_closer import SectionCloser
from api.section_routes import _count_words, _make_section_executor
from sections.section_store import SectionStore, TickSection
from tasks.task_manager import ProgressUpdater, TaskManager


class _FakeTickSummary:
    def __init__(self, tick: int) -> None:
        self.tick = tick


class _FakeOrchestrator:
    """最小 Orchestrator stub — 只暴露 run_tick / current_tick / last_narrator_output。

    构造时给定一个 narrator 输出序列, 每次 run_tick 推一个 tick + 设置缓存。
    """

    def __init__(self, narrator_outputs: list[NarratorOutput]) -> None:
        self._outputs = list(narrator_outputs)
        self._cursor = 0
        self.current_tick = 0
        self.last_narrator_output: NarratorOutput | None = None

    async def run_tick(self) -> _FakeTickSummary:
        if self._cursor >= len(self._outputs):
            # 兜底: 重复最后一项 — 让 hard tick 上限路径仍能跑
            out = self._outputs[-1]
        else:
            out = self._outputs[self._cursor]
            self._cursor += 1
        self.current_tick += 1
        self.last_narrator_output = out
        await asyncio.sleep(0)  # 让出事件循环
        return _FakeTickSummary(tick=self.current_tick)


class _FakeRuntime:
    def __init__(self, orch: _FakeOrchestrator) -> None:
        self.orchestrator = orch


@pytest.fixture
def patch_runtime(monkeypatch):
    """让 section_routes.get_runtime 返回 fake runtime。"""
    holder: dict = {}

    def _set(orch: _FakeOrchestrator) -> None:
        holder["runtime"] = _FakeRuntime(orch)

    def _fake_get_runtime(novel_id=None):
        return holder["runtime"]

    monkeypatch.setattr("api.section_routes.get_runtime", _fake_get_runtime)
    return _set


# ---- executor 主流程 -------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_accumulates_narrative_and_closes_at_target_words(
    patch_runtime, tmp_path, mock_llm
):
    """场景: Narrator 每 tick 都产出 800 字, 4 tick 后字数 3200 触发切节。"""
    # SectionCloser LLM 序列:
    #   第 1 次 decide_close (3200 >= min): {"closed": True} → 切
    #   close_section: 无沉默 → 跳过补叙; 标题 LLM 一次 → "山雨欲来"
    mock_llm.set_responses(
        [
            {"closed": False, "reason": "对话刚开始"},  # tick 3 (2400 字)
            {"closed": True, "reason": "场景结束"},  # tick 4 (3200 字)
            "山雨欲来",  # 标题
        ]
    )

    narrator_outputs = [
        NarratorOutput(
            should_narrate=True,
            narrative_text="字" * 800,
            tick_summary_for_record=f"tick {i+1}: 推进",
        )
        for i in range(10)  # 富余几个 tick, executor 会按需消费
    ]
    orch = _FakeOrchestrator(narrator_outputs)
    patch_runtime(orch)

    store = SectionStore(data_dir=str(tmp_path))
    closer = SectionCloser(target_words=3000, min_words=2400, max_ticks=30)
    mgr = TaskManager()

    executor = _make_section_executor(
        closer=closer,
        store=store,
        novel_title="测试",
        chapter=1,
        section_no=1,
    )

    snap = await mgr.create_task(
        novel_id="nv1",
        novel_title="测试",
        kind="section_generation",
        executor=executor,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
        chapter=1,
        section_no=1,
    )
    await asyncio.sleep(0.2)
    final = mgr.get(snap.id)

    assert final.status == "completed", f"status={final.status} error={final.error}"
    assert final.result_title == "山雨欲来"
    # 4 tick * 800 字 = 3200, close_section 不补叙 → 不变
    assert final.result_word_count == 3200
    # SectionStore 已 append
    items = store.list_all()
    assert len(items) == 1
    assert items[0].chapter == 1 and items[0].section == 1
    assert items[0].word_count == 3200
    assert items[0].silent_tick_count == 0
    assert items[0].tick_count == 4
    mgr._clear_for_tests()


@pytest.mark.asyncio
async def test_executor_collects_silent_ticks_and_appends_supplement(
    patch_runtime, tmp_path, mock_llm
):
    """场景: Narrator 第 2/4 tick 沉默, 切节时补叙拼到节尾。"""
    # 字数: t1 1200 (narrate) + t2 silent + t3 1200 (narrate) + t4 silent + t5 1200 (narrate)
    # = 3600 在 upper 边界 (3000*1.2=3600), upper 保护 — LLM 答未闭合也强切
    #
    # SectionCloser 调用顺序:
    #   tick 1 (1200, narrate): words=1200 < min=2400, 不调 LLM
    #   tick 2 (silent): 同上
    #   tick 3 (2400, narrate): words=2400, 调 decide_close LLM #1
    #   tick 4 (silent): 同 t3 字数 (没增长), 但仍调 decide_close LLM #2
    #   tick 5 (3600, narrate): upper 强切, 不调 decide_close LLM (>= upper 路径)
    #   close_section: 补叙 LLM #3 + 标题 LLM #4
    mock_llm.set_responses(
        [
            {"closed": False, "reason": "刚开始"},  # decide #1 @ 2400
            {"closed": False, "reason": "继续"},   # decide #2 @ 2400
            "雨后, 远处旗子又被风吹得猎猎作响, 直到日头偏西。",  # 补叙 #3
            "夜来风雨",  # 标题 #4
        ]
    )

    narrator_outputs = [
        NarratorOutput(should_narrate=True, narrative_text="字" * 1200),  # t1
        NarratorOutput(
            should_narrate=False, tick_summary_for_record="tick 2: 巡视", skip_reason="价值低"
        ),
        NarratorOutput(should_narrate=True, narrative_text="字" * 1200),  # t3
        NarratorOutput(
            should_narrate=False, tick_summary_for_record="tick 4: 雨停", skip_reason="价值低"
        ),
        NarratorOutput(should_narrate=True, narrative_text="字" * 1200),  # t5
    ]
    orch = _FakeOrchestrator(narrator_outputs)
    patch_runtime(orch)

    store = SectionStore(data_dir=str(tmp_path))
    closer = SectionCloser(target_words=3000, min_words=2400, max_ticks=30)
    mgr = TaskManager()

    executor = _make_section_executor(
        closer=closer,
        store=store,
        novel_title="",
        chapter=1,
        section_no=1,
    )
    snap = await mgr.create_task(
        novel_id="nv1",
        novel_title="",
        kind="section_generation",
        executor=executor,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
        chapter=1,
        section_no=1,
    )
    await asyncio.sleep(0.3)
    final = mgr.get(snap.id)

    assert final.status == "completed", f"err={final.error}"
    items = store.list_all()
    assert len(items) == 1
    sec = items[0]
    assert sec.silent_tick_count == 2
    # 补叙应被拼到 content 末尾
    assert "旗子又被风吹得猎猎作响" in sec.content
    assert sec.closure_supplement == "雨后, 远处旗子又被风吹得猎猎作响, 直到日头偏西。"
    assert sec.title == "夜来风雨"
    mgr._clear_for_tests()


@pytest.mark.asyncio
async def test_executor_hits_hard_tick_limit_below_min_words(
    patch_runtime, tmp_path, mock_llm
):
    """场景: 每 tick narrate 但每次只 30 字, max_ticks=5 → 硬上限强切。"""
    # decide_close 在 words<min 路径不调 LLM, 30 tick 全在 min 以下 →
    # hard limit (tick_count>=max) 触发, executor 不会调 LLM 判定。
    # close_section: 无沉默 → 补叙跳过; 标题 LLM 一次
    mock_llm.set_responses(["短章一"])  # 仅标题

    narrator_outputs = [
        NarratorOutput(should_narrate=True, narrative_text="字" * 30) for _ in range(20)
    ]
    orch = _FakeOrchestrator(narrator_outputs)
    patch_runtime(orch)

    store = SectionStore(data_dir=str(tmp_path))
    closer = SectionCloser(target_words=3000, min_words=2400, max_ticks=5)
    mgr = TaskManager()

    executor = _make_section_executor(
        closer=closer, store=store, novel_title="", chapter=1, section_no=1
    )
    snap = await mgr.create_task(
        novel_id="nv1",
        novel_title="",
        kind="section_generation",
        executor=executor,
        target_words=3000,
        min_words=2400,
        max_ticks=5,
        chapter=1,
        section_no=1,
    )
    await asyncio.sleep(0.2)
    final = mgr.get(snap.id)

    assert final.status == "completed"
    assert final.result_title == "短章一"
    # 5 tick 强切, 5 * 30 = 150 字
    assert final.result_word_count == 150
    items = store.list_all()
    assert items[0].tick_count == 5
    mgr._clear_for_tests()


# ---- 辅助 -------------------------------------------------------------------


def test_count_words_basic():
    assert _count_words("") == 0
    assert _count_words("中文 测试") == 4
    assert _count_words("a b c") == 3
