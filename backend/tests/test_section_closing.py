"""Phase 6-C iter#C1 — C6 章末无悬念 det check.

> Aligns with `docs/design/novel_quality_critique_and_iteration.md`:
>
> | code | trigger |
> | --- | --- |
> | C6   | 章节结尾无悬念、无未解问题、无新欲望 (medium) |

Trigger 策略 (保守, 避免 FP — 这是 iter#7 carry-forward 时点过的风险):

* 只看段末 ~60 字
* 只命中 **显式 closure 语言** (尘埃落定 / 至此告一段落 / 再无悬念 ...)
* 不基于"缺少问号"判 (大量正常 narrative 不带问号也无悬念缺失问题)

env kill switch: ``SECTION_CLOSING_ENABLE`` 默认 True.
"""

from __future__ import annotations

import sys
from pathlib import Path

# 项目根 + backend 加 sys.path (与现有 quality_metrics 测试同套路)
_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]
for p in (_ROOT, _BACKEND):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import pytest  # noqa: E402

from quality_metrics.section_closing import (  # noqa: E402
    SectionClosingReport,
    c6_section_closing_check,
    section_closing_report,
)


# ---------------------------------------------------------------------------
# 触发用例
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tail",
    [
        "案子查完了。尘埃落定。",
        "他长舒一口气。一切终于结束了。",
        "事情至此告一段落。",
        "风波平息, 再无悬念。",
        "便是这场十年风波的结局。",
        "至此, 这件事画上句号。",
        "总算尘埃落定。",
        "故事到此就结束了。",
    ],
)
def test_c6_triggers_on_explicit_closure_markers(tail: str) -> None:
    """显式 closure 语言出现在段末 → C6 触发."""
    # 加一个有内容的前缀, 让段落长度 ≥ 100 字 (短文本下面单独测).
    body = (
        "玄烛把卷宗推回桌上。守备官没说话, 只是把茶碗端起来又放下。"
        "屋外的雨还在下, 落在铁皮顶上嘶嘶响。他抬眼看了看墙上的钟。"
    )
    text = body + tail
    triggered, evidence = c6_section_closing_check(text)
    assert triggered, f"expected C6 trigger on tail: {tail!r}"
    assert evidence, "evidence must not be empty when triggered"


# ---------------------------------------------------------------------------
# 不触发用例 (clean / negative)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tail",
    [
        # 落动作 — clean ending per 规范 §3
        "他把帽檐往下压了压。",
        # 落物件 — clean
        "桌上的茶碗还摆着, 凉透了。",
        # 落对话 — clean
        '"走吧。"',
        # 落细节 — clean
        "袖口沾了一点泥。",
        # 普通陈述 + 句号 — 无 closure marker
        "他没回头, 转身走出门外。",
        # 问句结尾 — 显然不无悬念
        "她真的不会回来了吗?",
    ],
)
def test_c6_does_not_trigger_on_clean_endings(tail: str) -> None:
    body = (
        "玄烛把卷宗推回桌上。守备官没说话, 只是把茶碗端起来又放下。"
        "屋外的雨还在下, 落在铁皮顶上嘶嘶响。他抬眼看了看墙上的钟。"
    )
    text = body + tail
    triggered, _ = c6_section_closing_check(text)
    assert not triggered, f"unexpected C6 trigger on clean tail: {tail!r}"


def test_c6_does_not_trigger_when_marker_in_middle_not_tail() -> None:
    """closure 语言出现在段中 (不是段末) → 不触发 — 否则 FP 很高."""
    text = (
        "他以为案子尘埃落定, 但今早收到的信推翻了一切。卷宗里夹着一片血迹"
        "斑斑的布条, 他认得那是十年前的旧物。雨声越来越急, 像是要把铁皮顶"
        "砸穿。他坐回桌前, 把信摊开重新读了一遍, 越读眉头锁得越紧。"
    )
    triggered, _ = c6_section_closing_check(text)
    assert not triggered


def test_c6_returns_evidence_with_marker_phrase() -> None:
    """触发时 evidence 应含命中的 closure phrase, 便于 critic 报告."""
    text = (
        "守备官把最后一份卷宗合上, 长舒一口气。十年悬案, 案犯今早伏法。"
        "尘埃落定。"
    )
    triggered, evidence = c6_section_closing_check(text)
    assert triggered
    assert "尘埃落定" in evidence


# ---------------------------------------------------------------------------
# Short text guard
# ---------------------------------------------------------------------------


def test_c6_does_not_trigger_on_very_short_text() -> None:
    """文本太短 (< 40 字) 时一律 skip — 短 narrative 不需要"留悬念"."""
    text = "尘埃落定。"
    triggered, _ = c6_section_closing_check(text)
    assert not triggered


def test_c6_does_not_trigger_on_empty_text() -> None:
    triggered, _ = c6_section_closing_check("")
    assert not triggered


# ---------------------------------------------------------------------------
# Env kill switch
# ---------------------------------------------------------------------------


def test_c6_env_kill_switch_disables_check(monkeypatch) -> None:
    """SECTION_CLOSING_ENABLE=0 → quality_checks wrapper skip, 返回 []."""
    monkeypatch.setenv("SECTION_CLOSING_ENABLE", "0")
    # 必须用 wrapper 测 env (核心 c6_section_closing_check 不读 env)
    from agents.quality_checks import check_section_closing

    text = (
        "玄烛把卷宗推回桌上。守备官没说话, 只是把茶碗端起来又放下。"
        "屋外的雨还在下。尘埃落定。"
    )
    assert check_section_closing(text) == []


def test_c6_env_default_enables_check(monkeypatch) -> None:
    """SECTION_CLOSING_ENABLE 未设 → 默认 ON."""
    monkeypatch.delenv("SECTION_CLOSING_ENABLE", raising=False)
    from agents.quality_checks import check_section_closing

    text = (
        "玄烛把卷宗推回桌上。守备官没说话, 只是把茶碗端起来又放下。"
        "屋外的雨还在下。尘埃落定。"
    )
    triggers = check_section_closing(text)
    assert len(triggers) == 1
    assert triggers[0].code == "C6"
    assert triggers[0].severity == "medium"


# ---------------------------------------------------------------------------
# Report struct & integration
# ---------------------------------------------------------------------------


def test_section_closing_report_struct() -> None:
    """report 暴露 triggered / evidence / matched_markers, 供 dashboard 用."""
    text = (
        "守备官把最后一份卷宗合上。十年悬案, 案犯今早伏法。"
        "尘埃落定。"
    )
    report = section_closing_report(text)
    assert isinstance(report, SectionClosingReport)
    assert report.c6_triggered is True
    assert "尘埃落定" in report.c6_evidence
    assert "尘埃落定" in report.matched_markers


def test_section_closing_report_clean_text_returns_struct() -> None:
    text = (
        "玄烛把卷宗推回桌上。守备官没说话, 只是把茶碗端起来又放下。"
        "屋外的雨还在下, 落在铁皮顶上嘶嘶响。他没回头。"
    )
    report = section_closing_report(text)
    assert report.c6_triggered is False
    assert report.c6_evidence == ""
    assert report.matched_markers == []


def test_run_deterministic_checks_includes_c6() -> None:
    """run_deterministic_checks 整合后 C6 进总返回."""
    from agents.quality_checks import run_deterministic_checks

    text = (
        "玄烛把卷宗推回桌上。守备官没说话, 只是把茶碗端起来又放下。"
        "屋外的雨还在下, 落在铁皮顶上嘶嘶响。他抬眼看了看墙上的钟。"
        "尘埃落定。"
    )
    triggers = run_deterministic_checks(text)
    codes = [t.code for t in triggers]
    assert "C6" in codes


# ---------------------------------------------------------------------------
# FP guard — healthy long-form narrative should NOT trigger
# ---------------------------------------------------------------------------


def test_c6_healthy_long_narrative_no_trigger() -> None:
    """实测健康 narrative 样本 — 不应误触 C6.

    Sample from iter#29 verdict (the canonical quality reference).
    """
    text = (
        "酸雨落了整夜。天亮时没停。\n"
        "铁影城的屋顶在雾中只露出轮廓, 像一排生锈的锯齿. 街巷窄, "
        "两面高墙夹着, 雨水沿墙根淌下来, 颜色发黄, 碰到铁栏杆就嘶嘶响, "
        "冒一点白烟. 栏杆上原本有漆, 早被蚀光了, 露出底下坑洼的铸铁.\n"
        "玄烛低头走过赤铜巷. 外套领子竖着, 还是挡不住那股味道 — 煤烟混铁锈, "
        "呛嗓子. 他把布袋换到另一边肩上, 里面的东西硌着肋骨. 三份卷宗, 封蜡完好, "
        "是昨夜从外城守备处领回来的. 编号 6-17、6-18、6-19. 守备官递过来的时候"
        "手心出汗, 说了句\"尽快\", 多余的话一个字没有."
    )
    triggered, _ = c6_section_closing_check(text)
    assert not triggered, "healthy narrative sample should not trip C6"
