"""SectionCloser v2.24 — 切节判定 / 补叙 / 标题。"""

from __future__ import annotations

import pytest

from agents.section_closer import (
    SectionCloser,
    SilentTickRecord,
    _count_words,
    _fallback_supplement,
    _fallback_title_from_content,
)


# ---- 阈值层 -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_hard_tick_limit_forces_close_even_below_min_words(mock_llm):
    closer = SectionCloser(target_words=3000, min_words=2400, max_ticks=30)
    decision = await closer.decide_close(
        narrative_text="只有几百字。" * 50,  # ~600 chars 远低于 min
        tick_count=30,
    )
    assert decision.should_close is True
    assert "硬上限" in decision.reason
    # 硬上限路径不触发 LLM
    assert len(mock_llm.calls) == 0


@pytest.mark.asyncio
async def test_below_min_words_never_closes(mock_llm):
    closer = SectionCloser(target_words=3000, min_words=2400, max_ticks=30)
    decision = await closer.decide_close(
        narrative_text="字" * 1000,
        tick_count=10,
    )
    assert decision.should_close is False
    assert "字数下限" in decision.reason
    # 不到下限不调用 LLM
    assert len(mock_llm.calls) == 0


@pytest.mark.asyncio
async def test_in_range_calls_llm_and_closes_when_judged_closed(mock_llm):
    mock_llm.set_responses([{"closed": True, "reason": "场景已结束"}])
    closer = SectionCloser(target_words=3000, min_words=2400, max_ticks=30)
    decision = await closer.decide_close(
        narrative_text="字" * 2500,
        tick_count=15,
    )
    assert decision.should_close is True
    assert "LLM 判定内容闭合" in decision.reason
    assert len(mock_llm.calls) == 1


@pytest.mark.asyncio
async def test_in_range_llm_says_not_closed_keeps_open(mock_llm):
    mock_llm.set_responses([{"closed": False, "reason": "对话进行中"}])
    closer = SectionCloser(target_words=3000, min_words=2400, max_ticks=30)
    decision = await closer.decide_close(
        narrative_text="字" * 2500,
        tick_count=15,
    )
    assert decision.should_close is False
    assert "LLM 判定未闭合" in decision.reason


@pytest.mark.asyncio
async def test_upper_bound_forces_close_even_if_llm_says_not_closed(mock_llm):
    mock_llm.set_responses([{"closed": False, "reason": "还没结束"}])
    closer = SectionCloser(target_words=3000, min_words=2400, max_ticks=30)
    # 3000 * 1.2 = 3600 upper
    decision = await closer.decide_close(
        narrative_text="字" * 3700,
        tick_count=20,
    )
    assert decision.should_close is True
    assert "上限保护" in decision.reason


@pytest.mark.asyncio
async def test_llm_unavailable_fallback_uses_target_words(mock_llm):
    async def _raise(*a, **kw):
        raise RuntimeError("LLM unreachable")

    import nf_core.llm_client as llm_module

    # 替换 mock_llm 的 chat 让它真的抛
    llm_module.llm_client.chat = _raise

    closer = SectionCloser(target_words=3000, min_words=2400, max_ticks=30)
    # words >= target → 兜底切
    d1 = await closer.decide_close(narrative_text="字" * 3000, tick_count=20)
    assert d1.should_close is True
    assert "LLM 不可用" in d1.reason

    # words 在区间但 < target → 兜底不切
    d2 = await closer.decide_close(narrative_text="字" * 2500, tick_count=15)
    assert d2.should_close is False
    assert "LLM 不可用" in d2.reason


@pytest.mark.asyncio
async def test_llm_garbage_output_fallback_to_word_threshold(mock_llm):
    mock_llm.set_responses(["this is not json"])
    closer = SectionCloser(target_words=3000, min_words=2400, max_ticks=30)
    # words 在区间, LLM 输出无法解析, 且 < target → 不切
    d = await closer.decide_close(narrative_text="字" * 2500, tick_count=15)
    assert d.should_close is False
    assert "无法解析" in d.reason


# ---- 切节产出 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_section_with_no_silent_ticks_skips_supplement(mock_llm):
    # 标题 LLM 调用一次
    mock_llm.set_responses(["山雨欲来"])
    closer = SectionCloser()
    out = await closer.close_section(
        narrative_text="正文内容。" * 100,
        silent_ticks=[],
        chapter=1,
        section_no=1,
        novel_title="测试小说",
    )
    assert out.title == "山雨欲来"
    assert out.closure_supplement == ""
    assert out.consumed_silent_ticks == []
    # 终稿与原 narrative_text 一致 (无补叙)
    assert out.final_content == "正文内容。" * 100
    # 仅标题一次 LLM 调用
    assert len(mock_llm.calls) == 1


@pytest.mark.asyncio
async def test_close_section_with_silent_ticks_appends_supplement(mock_llm):
    # 补叙 LLM 一次 + 标题 LLM 一次
    mock_llm.set_responses(
        [
            "那几日他在城外巡视哨卡, 风把旗子吹得猎猎作响, 直到第三天傍晚才回到议事厅。",
            "城外巡哨",
        ]
    )
    closer = SectionCloser()
    silent = [
        SilentTickRecord(tick=12, summary="tick 12: 巡视东哨, 无事。"),
        SilentTickRecord(tick=13, summary="tick 13: 风暴掠过, 旗子撕裂。"),
    ]
    out = await closer.close_section(
        narrative_text="正文。" * 100,
        silent_ticks=silent,
        chapter=2,
        section_no=3,
        novel_title="测试小说",
    )
    assert out.title == "城外巡哨"
    assert "巡视哨卡" in out.closure_supplement
    assert out.consumed_silent_ticks == [12, 13]
    # 补叙拼到正文末尾
    assert out.final_content.endswith(out.closure_supplement)
    assert len(mock_llm.calls) == 2


@pytest.mark.asyncio
async def test_supplement_llm_fail_falls_back_to_summary_concatenation(mock_llm):
    # 第 1 次调用 (补叙) 抛, 第 2 次 (标题) 正常
    call_count = {"n": 0}

    async def _flaky(system_prompt, user_prompt, **kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("supplement LLM down")
        from tests.conftest import FakeLLMResponse
        return FakeLLMResponse(content="备用标题")

    import nf_core.llm_client as llm_module
    llm_module.llm_client.chat = _flaky

    closer = SectionCloser()
    silent = [
        SilentTickRecord(tick=5, summary="tick 5: 主角在码头等船。"),
        SilentTickRecord(tick=6, summary="tick 6: 雨开始下。"),
    ]
    out = await closer.close_section(
        narrative_text="先前剧情。",
        silent_ticks=silent,
        chapter=1,
        section_no=2,
        novel_title="",
    )
    # 兜底补叙应包含两条摘要的内容 (去 "tick N:" 前缀后)
    assert "主角在码头等船" in out.closure_supplement
    assert "雨开始下" in out.closure_supplement
    # 标题 fallback 来自第 2 次 LLM
    assert out.title == "备用标题"


# ---- 辅助函数 ---------------------------------------------------------------


def test_count_words_ignores_whitespace():
    assert _count_words("") == 0
    assert _count_words("  ") == 0
    assert _count_words("abc def") == 6
    assert _count_words("中 文 计 数") == 4
    assert _count_words("行一\n行二\n") == 4


def test_fallback_title_truncates_at_punctuation_then_length():
    # 句号在 8 字处, 在 ≤30 内, 取前 7 字
    assert _fallback_title_from_content("林风走进了客栈。屋里很暗。") == "林风走进了客栈"
    # 无句号 → 取前 14 字
    raw = "无标点超长内容反复出现填满更多字符以测试长度截断"
    assert _fallback_title_from_content(raw) == raw[:14]
    assert _fallback_title_from_content("") == ""


def test_fallback_supplement_strips_tick_prefix():
    silent = [
        SilentTickRecord(tick=1, summary="tick 1: 主角等船。"),
        SilentTickRecord(tick=2, summary="tick 2: 雨停了。"),
    ]
    s = _fallback_supplement(silent)
    assert "tick 1:" not in s
    assert "主角等船" in s
    assert "雨停了" in s


def test_section_closer_rejects_invalid_min_target_combination():
    with pytest.raises(ValueError):
        SectionCloser(target_words=2000, min_words=2500)


# ---- env 阈值覆盖 -----------------------------------------------------------


def test_env_overrides_applied(monkeypatch):
    monkeypatch.setenv("SECTION_TARGET_WORDS", "1500")
    monkeypatch.setenv("SECTION_MIN_WORDS", "1200")
    monkeypatch.setenv("SECTION_MAX_TICKS", "20")
    closer = SectionCloser()
    assert closer.target_words == 1500
    assert closer.min_words == 1200
    assert closer.max_ticks == 20


def test_env_garbage_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("SECTION_TARGET_WORDS", "not-a-number")
    closer = SectionCloser()
    assert closer.target_words == 3000
