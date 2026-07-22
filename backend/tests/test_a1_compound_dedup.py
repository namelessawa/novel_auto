"""Phase 6-C iter#C3 — A1 3-char 化合物 dedup.

iter#C2 校准 (a1-calibration-iter-c2.md) 发现 production-like top offenders
不是函数词也不是角色名, 而是 2-gram 切的 3-char 化合物:
* 混凝土 → "混凝" + "凝土" 两条 A1
* 煤气灯 → "煤气" + "气灯" 两条 A1
* 钢筋混凝土 → "钢筋" + "筋混" + "混凝" + "凝土" 四条 A1

这是 ``check_word_repetition`` 的 2-gram 滑窗机制的已知 false positive.
本 iter 修复: 同时建 3-gram counter, 把 3-gram 命中从重叠 2-gram count
中扣除, 然后 threshold check on both. 3-char 化合物 → 1 条 trigger
(不是 2 条).
"""

from __future__ import annotations

import sys
from pathlib import Path

# 项目根 + backend sys.path
_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]
for p in (_ROOT, _BACKEND):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agents.quality_checks import check_word_repetition  # noqa: E402


def _codes(text: str, threshold: int = 3) -> list[str]:
    """Return list of triggered words from A1 evidence strings."""
    triggers = check_word_repetition(text, threshold=threshold)
    out = []
    for t in triggers:
        if t.code != "A1":
            continue
        try:
            w = t.evidence.split('"')[1]
            out.append(w)
        except IndexError:
            continue
    return sorted(out)


# ---------------------------------------------------------------------------
# Core dedup behavior
# ---------------------------------------------------------------------------


def test_3char_compound_counts_as_single_trigger() -> None:
    """混凝土 × 3 → 只触发 1 条 "混凝土", 不再分别触发 "混凝" + "凝土"."""
    text = (
        "工地角落堆着混凝土板。第二车混凝土到了, 工人们卸下。"
        "他踩在混凝土的边缘, 鞋底沾上灰色粉末。"
    )
    triggers = _codes(text)
    assert "混凝土" in triggers, "expected 3-char compound as the trigger word"
    assert "混凝" not in triggers, "2-gram subset must NOT also trigger"
    assert "凝土" not in triggers, "2-gram subset must NOT also trigger"


def test_煤气灯_compound_dedup() -> None:
    """煤气灯 × 3 → 1 条 trigger, 不双发 "煤气"+"气灯"."""
    text = (
        "煤气灯亮着, 在窗外摇晃。煤气灯下站着一个老人。"
        "他点燃第三盏煤气灯, 房间一下子明亮。"
    )
    triggers = _codes(text)
    assert "煤气灯" in triggers
    assert "煤气" not in triggers
    assert "气灯" not in triggers


# ---------------------------------------------------------------------------
# Standalone 2-gram still triggers when not part of a 3-char compound
# ---------------------------------------------------------------------------


def test_standalone_2gram_still_triggers() -> None:
    """灯塔 (not part of any 3-char compound) × 4 → 仍触发 灯塔."""
    text = "灯塔在夜里亮着。灯塔的光是橙色的。灯塔下有礁石。灯塔是他的责任。"
    triggers = _codes(text)
    assert "灯塔" in triggers


def test_mixed_compound_and_standalone() -> None:
    """混凝土 × 2 (不达阈值) + 钢筋 × 3 (达阈值) → 只触发 钢筋."""
    text = (
        "钢筋堆在角落, 锈迹斑斑。混凝土板压在上面。"
        "钢筋从板缝里伸出来, 像断指。他绕过混凝土, 拨开钢筋。"
    )
    triggers = _codes(text)
    assert "钢筋" in triggers
    assert "混凝土" not in triggers  # only 2 occurrences, below threshold
    assert "混凝" not in triggers  # compound subset, must dedupe
    assert "凝土" not in triggers


# ---------------------------------------------------------------------------
# Mixed-context 2-gram (some in compound, some not) — count the standalone
# ---------------------------------------------------------------------------


def test_2gram_with_some_in_compound_counts_standalone() -> None:
    """混凝 出现 5 次, 其中 3 次属于 "混凝土" 3-gram, 2 次独立: 净值 2 < 阈值."""
    text = (
        "混凝土板堆在墙边。第二块混凝土也搬过来。"
        "工人把第三块混凝土砸下。"
        # 下面两次 "混凝" 不连 "土"
        "他混凝着说不清的疲惫。她混凝着同样的不安。"
    )
    triggers = _codes(text)
    # 混凝土 3 次 → 触发
    assert "混凝土" in triggers
    # 混凝 净独立 2 次 < threshold → 不触发
    assert "混凝" not in triggers


def test_2gram_with_standalone_dominant_triggers() -> None:
    """混凝 出现 5 次, 仅 1 次属于 "混凝土", 4 次独立: 净 4 ≥ 阈值, 触发."""
    text = (
        "他说话总是混凝不清, 像含着东西。"
        "她回想往昔, 思绪混凝着一层雾。"
        "夜风也混凝着雨味, 凉得人哆嗦。"
        "他混凝着旧的记忆走出门。"
        # 仅 1 次 "混凝土"
        "巷口堆着一块混凝土, 风从缝里钻。"
    )
    triggers = _codes(text)
    # 混凝 净 4 次 → 触发
    assert "混凝" in triggers
    # 混凝土 仅 1 次 < threshold → 不触发
    assert "混凝土" not in triggers


# ---------------------------------------------------------------------------
# 4-char compound (out of scope for 3-gram dedup, falls back to 2-gram only)
# ---------------------------------------------------------------------------


def test_4char_compound_not_in_dedup_scope() -> None:
    """钢筋混凝土 × 3 → 现 iter 只 dedup 3-gram, 4-gram 仍按 2-gram 算.

    documented limitation — 4-gram dedup 留 iter#C4 (低优先).
    """
    text = (
        "钢筋混凝土的塔楼立在街角。钢筋混凝土被雨水浸黑。"
        "钢筋混凝土的裂缝里长出青苔。"
    )
    triggers = _codes(text)
    # 至少其中一项会触发 (4-gram 切成 2-gram 后 "钢筋"/"筋混"/"混凝"/"凝土"
    # 每个出现 3 次). 不强制要求是哪一个 (4-gram dedup 不在 scope).
    assert len(triggers) >= 1


# ---------------------------------------------------------------------------
# Regression — existing tests should keep passing
# ---------------------------------------------------------------------------


def test_灯塔_regression_existing() -> None:
    """既有测试 (test_quality_spec.py::test_a1_triggers_on_repeat) 不能 regress."""
    text = "灯塔在夜里亮着。灯塔的光是橙色的。灯塔下有礁石。灯塔是他的责任。"
    triggers = _codes(text)
    assert "灯塔" in triggers


def test_stopwords_regression_existing() -> None:
    """既有测试 (test_a1_skips_stopwords) 不能 regress."""
    text = (
        "他想自己应该做什么。她不知道自己该说什么。"
        "但他们都在想自己究竟在等什么。"
    )
    triggers = _codes(text)
    assert "自己" not in triggers
    assert "什么" not in triggers


def test_empty_text_returns_no_triggers() -> None:
    assert _codes("") == []
    assert _codes("   ") == []
