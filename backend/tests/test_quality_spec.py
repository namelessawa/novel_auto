"""Tests for quality_spec + quality_checks + NarrativeCritic.

确定性检查可独立验证, NarrativeCritic 用 mock_llm 验证决策矩阵。
"""

from __future__ import annotations

import json

import pytest

from agents.narrative_critic import NarrativeCritic
from agents.quality_checks import (
    check_ai_cliche_blacklist,
    check_cliche_blacklist,
    check_opening_repetition,
    check_summary_ending,
    check_word_repetition,
    run_deterministic_checks,
    summarize_triggers,
)
from agents.quality_spec import (
    AI_CLICHE_BLACKLIST,
    HIGH_SEVERITY_CODES,
    RULES_BY_CODE,
    decide_action,
    render_blacklist_block,
    render_narrator_quality_block,
)


# ---------------------------------------------------------------------------
# quality_spec
# ---------------------------------------------------------------------------


def test_high_severity_codes_match_rules() -> None:
    for code in HIGH_SEVERITY_CODES:
        assert RULES_BY_CODE[code].severity == "high"


def test_decision_matrix_branches() -> None:
    assert decide_action(1, 0) == "REWRITE"
    assert decide_action(2, 5) == "REWRITE"
    assert decide_action(0, 3) == "REVISE"
    assert decide_action(0, 2) == "POLISH"
    assert decide_action(0, 1) == "POLISH"
    assert decide_action(0, 0) == "RED_TEAM"


def test_blacklist_block_contains_core_words() -> None:
    block = render_blacklist_block()
    # 关键黑名单词必须出现在 prompt 片段
    for w in ("仿佛", "心中涌起一股", "命运的齿轮", "月光如水"):
        assert w in block


def test_quality_block_compiles() -> None:
    """完整 narrator quality block 编译不抛异常且非空。"""
    block = render_narrator_quality_block()
    assert len(block) > 500
    assert "硬性禁用清单" in block
    assert "段落禁忌" in block


# ---------------------------------------------------------------------------
# quality_checks: A4 黑名单
# ---------------------------------------------------------------------------


def test_a4_triggers_on_fangfu() -> None:
    text = "他停在门口,仿佛听到了什么。她抬头,仿佛要说话。"
    triggers = check_ai_cliche_blacklist(text)
    codes = {t.code for t in triggers}
    assert "A4" in codes
    assert all(t.severity == "high" for t in triggers if t.code == "A4")


def test_a4_soft_words_need_two_occurrences() -> None:
    # 缓缓地 出现 1 次 — 不触发
    one = "他缓缓地推开门,走进去。"
    assert all(t.code != "A4" or "缓缓地" not in t.evidence for t in check_ai_cliche_blacklist(one))
    # 缓缓地 出现 2 次 — 触发
    two = "他缓缓地推开门,然后缓缓地坐下。"
    assert any(
        t.code == "A4" and "缓缓地" in t.evidence
        for t in check_ai_cliche_blacklist(two)
    )


def test_a4_clean_text_no_trigger() -> None:
    text = "他把钥匙放在桌上。桌面有一圈水渍。他没有去擦。"
    assert check_ai_cliche_blacklist(text) == []


# ---------------------------------------------------------------------------
# quality_checks: D3 陈词滥调
# ---------------------------------------------------------------------------


def test_d3_triggers_on_cliche() -> None:
    text = "月光如水般倾泻在庭院里,她嘴角上扬。"
    triggers = check_cliche_blacklist(text)
    codes = {t.code for t in triggers}
    assert "D3" in codes


# ---------------------------------------------------------------------------
# quality_checks: A1 实词重复
# ---------------------------------------------------------------------------


def test_a1_triggers_on_repeat() -> None:
    # "灯塔" 重复 4 次
    text = "灯塔在夜里亮着。灯塔的光是橙色的。灯塔下有礁石。灯塔是他的责任。"
    triggers = check_word_repetition(text, threshold=3)
    assert any(t.code == "A1" and "灯塔" in t.evidence for t in triggers)


def test_a1_skips_stopwords() -> None:
    # "自己"/"什么" 是 stop nominals, 不触发
    text = "他想自己应该做什么。她不知道自己该说什么。但他们都在想自己究竟在等什么。"
    triggers = check_word_repetition(text)
    assert all("自己" not in t.evidence and "什么" not in t.evidence for t in triggers)


# ---------------------------------------------------------------------------
# quality_checks: A6 段末升华
# ---------------------------------------------------------------------------


def test_a6_triggers_on_summary_ending() -> None:
    text = "他站在风里看着远处的火光,只剩下纯粹的、近乎绝望的紧迫。"
    triggers = check_summary_ending(text)
    assert any(t.code == "A6" and t.severity == "high" for t in triggers)


def test_a6_clean_action_ending() -> None:
    text = "他把火柴放回口袋。风停了一下,又起。他没有再看那扇窗。"
    triggers = check_summary_ending(text)
    assert triggers == []


def test_a6_v214_real_mimo_evidence_endings() -> None:
    """v2.14: 实测 MIMO 输出发现的真实升华句, 必须被识别。"""
    # tick_10 实测段末
    assert check_summary_ending("他停下来,侧耳听了一会儿,只有风声和自己的呼吸。")
    # 其他常见模板
    assert check_summary_ending("剩下的, 只有夜色。")
    assert check_summary_ending("天地间, 仿佛只剩他一人。")
    assert check_summary_ending("时间仿佛静止了。")
    # 正例不误报
    assert not check_summary_ending("他把帽檐往下压了压。")
    assert not check_summary_ending("袖口沾了一点泥。")
    assert not check_summary_ending("走吧。")


# ---------------------------------------------------------------------------
# quality_checks: A5/A7 开头重复
# ---------------------------------------------------------------------------


def test_a7_triggers_when_opening_matches_recent() -> None:
    recent = ["他停在门口", "她抬起头", "雨开始下了"]
    text = "他停在门口,看着窗外。"
    triggers = check_opening_repetition(text, recent)
    assert any(t.code == "A7" for t in triggers)


# ---------------------------------------------------------------------------
# 综合主入口
# ---------------------------------------------------------------------------


def test_run_deterministic_returns_summary() -> None:
    text = (
        "他仿佛看见了什么,缓缓地走过去。月光如水般洒在地上。"
        "他想,他想,他想 — 心中涌起一股说不清的感觉,只剩下纯粹的孤独。"
    )
    triggers = run_deterministic_checks(text)
    summary = summarize_triggers(triggers)
    assert summary["high_count"] >= 2  # A4 仿佛 / 心中涌起一股 / A6 段末升华
    assert "A4" in summary["high_codes"]


# ---------------------------------------------------------------------------
# NarrativeCritic — 集成 (mock LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_critic_accepts_clean_text(mock_llm) -> None:
    """干净文本 LLM critic 返回空 triggers → 决策 RED_TEAM, 直接接受。"""
    mock_llm.set_responses([{"triggers": [], "rationale": "", "red_team_critiques": []}])
    critic = NarrativeCritic()
    text = (
        "他把钥匙放在桌上。桌面有一圈水渍。"
        "他没有去擦。窗外有狗叫了一声,然后停了。"
    )
    out = await critic.critique_and_iterate(draft_text=text)
    assert out.final_text == text
    assert out.final_action in ("RED_TEAM", "ACCEPT")


@pytest.mark.asyncio
async def test_critic_revises_on_medium_only(mock_llm) -> None:
    """3 个中触发 → REVISE 路径, LLM 返回修订后的 text。"""
    # v2.38 (iter#18 review fix) — 长度 ≥ 40 字 (parser 最小长度护栏)
    revised = (
        "他把钥匙放在桌上, 没去擦水渍。雨停了, 远处汽笛拖长了一下。"
        "他坐了片刻, 没开灯。"
    )
    mock_llm.set_responses(
        [
            # round 1 critic: 0 high, 3 medium → REVISE
            {
                "triggers": [
                    {"code": "A1", "severity": "medium", "evidence": "x x x"},
                    {"code": "D2", "severity": "medium", "evidence": "y y y"},
                    {"code": "A2", "severity": "medium", "evidence": "z z z"},
                ],
                "rationale": "中触发",
                "red_team_critiques": [],
            },
            # round 1 revise output
            {
                "revised_text": revised,
                "diffs": [],
                "removed_words": [],
            },
            # round 2 critic: 全清 → 接受
            {"triggers": [], "rationale": "", "red_team_critiques": []},
        ]
    )
    critic = NarrativeCritic()
    out = await critic.critique_and_iterate(draft_text="原稿,有问题但没高触发。")
    assert out.final_text == revised
    assert any(r.action == "REVISE" for r in out.rounds)


@pytest.mark.asyncio
async def test_critic_rewrites_on_high(mock_llm) -> None:
    """高触发 → REWRITE, LLM 返回重写文本。

    v2.38 (iter#6 + review fix) — draft 含 "仿佛" / "缓缓地" 触发 det A4 high,
    新 gating 跳过 LLM critique 直接进入 REWRITE. 测试也跟着调整 mock 序列:
    第一个 mock 直接是 rewrite output, 不再前置 critic JSON.
    """
    # v2.38 (iter#18 review fix) — 长度 ≥ 40 字 (parser 拒绝过短输出, 见
    # _parse_text_field 的 minimum-length guard)
    rewritten = (
        "他把钥匙放在桌上, 没有去擦水渍。窗外的雨停了, 风从纱门缝隙吹进来,"
        "带着夜里的潮气和远处汽笛的尾音。"
    )
    mock_llm.set_responses(
        [
            # round 1 rewrite output (det 已发现 A4 high, 跳过 LLM critique)
            {
                "rewritten_text": rewritten,
                "dimension_shift": "节奏 慢 → 快",
                "avoided_codes": ["A4"],
            },
            # round 2 critic 也被 det-only 路径跳过, 直接 ACCEPT
        ]
    )
    critic = NarrativeCritic()
    out = await critic.critique_and_iterate(
        draft_text="他仿佛看见了什么,缓缓地走过去。"
    )
    assert out.final_text == rewritten
    assert any(r.action == "REWRITE" for r in out.rounds)


@pytest.mark.asyncio
async def test_critic_empty_draft_returns_immediately(mock_llm) -> None:
    critic = NarrativeCritic()
    out = await critic.critique_and_iterate(draft_text="")
    assert out.final_text == ""
    assert out.final_action == "ACCEPT"
    assert out.rounds == []


@pytest.mark.asyncio
async def test_critic_caps_rewrite_attempts(mock_llm, monkeypatch) -> None:
    """REWRITE 上限达到后, 应降级为 REVISE 或接受, 不能死循环。"""
    # 每轮 critic 都返回 1 high (持续 REWRITE), 每次 rewrite 仍带高触发
    rewritten = "依然包含仿佛"
    responses = []
    for _ in range(6):
        responses.append(
            {
                "triggers": [{"code": "A4", "severity": "high", "evidence": "仿佛"}],
                "rationale": "持续高触发",
                "red_team_critiques": [],
            }
        )
        responses.append(
            {
                "rewritten_text": rewritten,
                "dimension_shift": "x",
                "avoided_codes": [],
            }
        )
        # REVISE 兜底分支
        responses.append(
            {
                "revised_text": rewritten,
                "diffs": [],
                "removed_words": [],
            }
        )
    mock_llm.set_responses(responses)

    monkeypatch.setenv("CRITIC_MAX_REWRITE_ROUNDS", "1")
    monkeypatch.setenv("CRITIC_MAX_REVISE_ROUNDS", "1")
    # 重新导入以读取新 env
    import importlib

    import agents.narrative_critic as nc

    importlib.reload(nc)
    critic = nc.NarrativeCritic()
    out = await critic.critique_and_iterate(draft_text="仿佛永不停止。")
    # 必须终止
    assert out.final_action == "ACCEPT"
    # 至少有一轮 REWRITE
    assert any(r.action == "REWRITE" for r in out.rounds)


# ---------------------------------------------------------------------------
# iter#10 critic length-gate integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_narrate_skips_critic_for_short_narrative(mock_llm, monkeypatch) -> None:
    """v2.38 iter#10 — narrative_text < 400 字时跳过 critic 整段.

    用 _CRITIC_MIN_NARRATIVE_LEN monkeypatch 把阈值改成可测的值,
    短 narrative 不触 critic, 长的触发.
    """
    from unittest.mock import AsyncMock

    from agents.narrator_agent import NarratorAgent
    from memory_system.models import Event

    # 构造两个不同长度的 narrator JSON 输出
    # v2.38 (iter#25) — 阈值提高到 600, long_text 跟着提
    short_text = "他走过雨夜的街。"  # ~10 字
    long_text = "他走过雨夜的街。" * 100  # ~800 字

    short_resp = json.dumps(
        {
            "narrative_text": short_text,
            "estimated_length": "short",
            "viewpoint_characters": ["c1"],
            "scene_focus": "",
            "events_consumed": [],
            "open_loops_referenced": [],
            "newly_opened_loops": [],
            "style_diagnostics": {},
            "consistency_flags": [],
        },
        ensure_ascii=False,
    )
    long_resp = json.dumps(
        {
            "narrative_text": long_text,
            "estimated_length": "medium",
            "viewpoint_characters": ["c1"],
            "scene_focus": "",
            "events_consumed": [],
            "open_loops_referenced": [],
            "newly_opened_loops": [],
            "style_diagnostics": {},
            "consistency_flags": [],
        },
        ensure_ascii=False,
    )

    # Mock critic to track calls
    mock_critic = AsyncMock()
    mock_critic.critique_and_iterate = AsyncMock()
    agent = NarratorAgent(critic=mock_critic, enable_critic=True)

    # 单事件触发 narrate (避开 score 阈值跳过)
    dummy_event = Event(
        id="evt_1",
        type="exogenous",
        tick=1,
        description="测试事件",
        narrative_value=10,
        narrative_value_hint=10,
    )

    # --- 短输出: critic 不应被调 ---
    mock_llm.set_responses([short_resp])
    out_short = await agent.narrate(
        tick=1,
        world_time=1,
        tracking_character_id="c1",
        tick_events=[dummy_event],
        char_states=[],
        recent_chapter_summaries=[],
        open_loops=[],
        style_anchors=[],
        last_narration_tick=0,
    )
    assert out_short.should_narrate is True
    assert mock_critic.critique_and_iterate.call_count == 0, (
        "短段落 (<400 字) 不应该触发 critic"
    )

    # --- 长输出: critic 应该被调 ---
    mock_critic.critique_and_iterate.reset_mock()
    # critic 返回时假装直接 ACCEPT, final_text 等于 draft
    from agents.narrative_critic import CritiqueOutput

    mock_critic.critique_and_iterate.return_value = CritiqueOutput(
        final_text=long_text,
        rounds=[],
        surviving_triggers=[],
        decision_trail=[],
        final_action="ACCEPT",
        new_opening_signature="",
        blacklist_to_add=[],
    )
    mock_llm.set_responses([long_resp])
    out_long = await agent.narrate(
        tick=2,
        world_time=2,
        tracking_character_id="c1",
        tick_events=[dummy_event],
        char_states=[],
        recent_chapter_summaries=[],
        open_loops=[],
        style_anchors=[],
        last_narration_tick=0,
    )
    assert out_long.should_narrate is True
    assert mock_critic.critique_and_iterate.call_count == 1, (
        "长段落 (≥600 字默认阈值) 必须触发 critic"
    )


@pytest.mark.asyncio
async def test_critic_min_narrative_len_env_override(mock_llm, monkeypatch) -> None:
    """v2.38 iter#27 review fix — CRITIC_MIN_NARRATIVE_LEN env 立即生效.

    iter#25 第一版用 module-level constant 冻结到 import 时, monkeypatch.setenv
    无效. 改成 _critic_min_narrative_len() 函数 lazy 读 env 后, 测试可控.
    """
    from unittest.mock import AsyncMock

    from agents.narrator_agent import NarratorAgent
    from agents.narrative_critic import CritiqueOutput
    from memory_system.models import Event

    # 把阈值通过 env 降到 50 字, 短段落也应触发 critic
    monkeypatch.setenv("CRITIC_MIN_NARRATIVE_LEN", "50")

    text = "他走过雨夜的街。" * 10  # ~80 字, > 50 但 < 600 默认
    resp_json = json.dumps(
        {
            "narrative_text": text,
            "estimated_length": "short",
            "viewpoint_characters": ["c1"],
            "scene_focus": "",
            "events_consumed": [],
            "open_loops_referenced": [],
            "newly_opened_loops": [],
            "style_diagnostics": {},
            "consistency_flags": [],
        },
        ensure_ascii=False,
    )

    mock_critic = AsyncMock()
    mock_critic.critique_and_iterate = AsyncMock(
        return_value=CritiqueOutput(
            final_text=text,
            rounds=[],
            surviving_triggers=[],
            decision_trail=[],
            final_action="ACCEPT",
            new_opening_signature="",
            blacklist_to_add=[],
        )
    )
    agent = NarratorAgent(critic=mock_critic, enable_critic=True)

    dummy_event = Event(
        id="evt_1",
        type="exogenous",
        tick=1,
        description="测试",
        narrative_value=10,
        narrative_value_hint=10,
    )
    mock_llm.set_responses([resp_json])
    out = await agent.narrate(
        tick=1,
        world_time=1,
        tracking_character_id="c1",
        tick_events=[dummy_event],
        char_states=[],
        recent_chapter_summaries=[],
        open_loops=[],
        style_anchors=[],
        last_narration_tick=0,
    )
    assert out.should_narrate is True
    assert mock_critic.critique_and_iterate.call_count == 1, (
        "env CRITIC_MIN_NARRATIVE_LEN=50 后, 80 字段落必须触发 critic "
        "(原默认 600 会跳过)"
    )


def test_critic_min_narrative_len_rejects_invalid_env(monkeypatch) -> None:
    """v2.38 iter#54 — env 非正整数 / 负值 / 0 都退回 default 600.

    防生产误配 CRITIC_MIN_NARRATIVE_LEN=0 把 critic 总开炸 token.
    """
    from agents.narrator_agent import _critic_min_narrative_len, _CRITIC_MIN_NARRATIVE_LEN_DEFAULT

    # 正常值
    monkeypatch.setenv("CRITIC_MIN_NARRATIVE_LEN", "300")
    assert _critic_min_narrative_len() == 300

    # 0 → default
    monkeypatch.setenv("CRITIC_MIN_NARRATIVE_LEN", "0")
    assert _critic_min_narrative_len() == _CRITIC_MIN_NARRATIVE_LEN_DEFAULT

    # 负值 → default
    monkeypatch.setenv("CRITIC_MIN_NARRATIVE_LEN", "-100")
    assert _critic_min_narrative_len() == _CRITIC_MIN_NARRATIVE_LEN_DEFAULT

    # 非数字 → default
    monkeypatch.setenv("CRITIC_MIN_NARRATIVE_LEN", "abc")
    assert _critic_min_narrative_len() == _CRITIC_MIN_NARRATIVE_LEN_DEFAULT

    # 空字符串 → default
    monkeypatch.setenv("CRITIC_MIN_NARRATIVE_LEN", "")
    assert _critic_min_narrative_len() == _CRITIC_MIN_NARRATIVE_LEN_DEFAULT


def test_critic_enable_llm_env_robust_parsing(monkeypatch) -> None:
    """v2.38 iter#61 — CRITIC_ENABLE_LLM 接受多种 off 拼写.

    v2.38 (iter#74 review fix) — 此前用 importlib.reload 强行换模块, 污染
    sys.modules 影响后续测试. 改成调用 ENABLE_LLM_CRITIC() 函数 (iter#74
    review fix 把它从常量改成函数), monkeypatch.setenv 后直接生效, 无副作用.
    """
    from agents.narrative_critic import ENABLE_LLM_CRITIC

    cases_off = ["0", "false", "False", "FALSE", "no", "off"]
    cases_on = ["1", "true", "yes", "on", "", "anything-else"]

    for v in cases_off:
        monkeypatch.setenv("CRITIC_ENABLE_LLM", v)
        assert ENABLE_LLM_CRITIC() is False, f"{v!r} 应该禁用 critic"

    for v in cases_on:
        monkeypatch.setenv("CRITIC_ENABLE_LLM", v)
        assert ENABLE_LLM_CRITIC() is True, f"{v!r} 应该启用 critic"
