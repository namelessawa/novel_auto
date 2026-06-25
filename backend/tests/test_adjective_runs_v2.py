"""Phase 6 iter#SS — D2 形容词堆砌 det 加强 + 名词列举排除.

iter#C1 时代 check_adjective_runs 用顿号/逗号 ≥3 个 1-3 char 词的启发式,
comment 说"启发式: 后面紧跟动词" 排除名词列举, 但代码没实现 — 总
append. 加排除规则:

* 名词列举模式 (后接动作动词 走/坐/说/堆/摆/挂...) → skip
* 真形容词堆砌 (后接 的 名词 / 句末 / 句号) → keep

锁定:
* 真 D2 case: '高大、威武、英俊的男人' → 触发
* 名词列举: '桌椅、灯具、书籍堆在角落' → 不触发
* 名词列举 + 主语动作: '砖、瓦、木头落下来' → 不触发
* 短句末尾的形容词堆砌: '她又冷、又饿、又困。' → 触发
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]
for p in (_ROOT, _BACKEND):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agents.quality_checks import check_adjective_runs


def _has_d2(text: str) -> bool:
    return any(t.code == "D2" for t in check_adjective_runs(text))


# ---------------------------------------------------------------------------
# Real D2 cases — keep triggering
# ---------------------------------------------------------------------------


def test_d2_classic_adjective_run_triggers() -> None:
    """'高大、威武、英俊的男人' — 真 D2."""
    text = "巷口走来一位高大、威武、英俊的男人。"
    assert _has_d2(text)


def test_d2_emotion_stack_at_sentence_end_triggers() -> None:
    """'她又冷、又饿、又困。' — 形容词堆砌, 真 D2."""
    text = "雨下了一夜没停, 她又冷、又饿、又困。"
    assert _has_d2(text)


def test_d2_de_suffix_chain_triggers() -> None:
    """'灰色的、潮湿的、肮脏的墙' — 三 X 的 修饰一物 = D2."""
    text = "他走进灰色的、潮湿的、肮脏的墙边小巷。"
    assert _has_d2(text)


# ---------------------------------------------------------------------------
# Noun list FP — should NOT trigger after iter#SS
# ---------------------------------------------------------------------------


def test_d2_noun_list_with_verb_no_trigger() -> None:
    """'砖、瓦、木头落下来' — 名词列举 + 动词, 非 D2."""
    text = "屋顶塌了, 砖、瓦、木头落下来, 砸在脚边。"
    assert not _has_d2(text)


def test_d2_objects_in_corner_no_trigger() -> None:
    """'桌椅、灯具、书籍堆在角落' — 名词列举."""
    text = "屋里桌椅、灯具、书籍堆在角落, 灰落得厚."
    assert not _has_d2(text)


def test_d2_character_list_action_no_trigger() -> None:
    """'苏默、林雪、墨珩走进档案馆' — 角色列举 + 动作."""
    text = "天刚亮, 苏默、林雪、墨珩走进档案馆, 守备官递来卷宗。"
    assert not _has_d2(text)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_d2_two_items_no_trigger() -> None:
    """只 2 个 short term, 不到 ≥3 阈值."""
    text = "她长得高大、威武, 走起路来声响很重。"
    assert not _has_d2(text)


def test_d2_empty_text() -> None:
    assert not _has_d2("")
