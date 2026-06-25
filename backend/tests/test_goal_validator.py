"""Phase 6 iter#J — Goal schema validator.

Background: 两次 500-tick bench (run 1 24 日 / run 2 25 日) 都频繁出现
``CharacterAgent: Skip invalid new_goal`` warnings. LLM 常出:

* ``priority='critical'`` (str) — schema 要 int 0-10
* ``progress='15%'`` (str pct) — schema 要 float 0.0-1.0
* ``id=10`` (int) — schema 要 str
* ``priority=85`` (超 ge≤10 上限) — 应钳到 10

每条 skip 都是浪费的 LLM token. 加 mode='before' validator 强转, 让 LLM 在
"软自然语言" 与 "硬 schema" 之间不再卡死.

锁定:
* str priority 名称表 → int (critical=10, urgent=10, high=8, medium=5, low=3)
* str progress '15%' → 0.15, '0%' → 0.0
* int id → str(id)
* 超出范围 priority 钳到 ge/le
* progress 整数 >1 → clamp to 1.0 (兼容 LLM 误用 "15" 想表达 15%)
* 不可挽救的情况仍抛 ValidationError (e.g., description 缺失)
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

import pytest
from pydantic import ValidationError

from memory_system.models import Goal


# ---------------------------------------------------------------------------
# priority 强转
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("critical", 10),
        ("CRITICAL", 10),
        ("urgent", 10),
        ("Urgent", 10),
        ("high", 8),
        ("HIGH", 8),
        ("medium", 5),
        ("low", 3),
        ("LOW", 3),
    ],
)
def test_priority_str_name_to_int(raw, expected) -> None:
    g = Goal(id="g1", description="x", priority=raw)
    assert g.priority == expected


def test_priority_str_numeric_to_int() -> None:
    """'7' (str) → 7 (int)."""
    g = Goal(id="g1", description="x", priority="7")
    assert g.priority == 7


def test_priority_int_passes_through() -> None:
    g = Goal(id="g1", description="x", priority=6)
    assert g.priority == 6


def test_priority_above_range_clamped_to_10() -> None:
    """run 1 实测出现 priority=85 → 应 clamp 10 而非抛."""
    g = Goal(id="g1", description="x", priority=85)
    assert g.priority == 10


def test_priority_below_range_clamped_to_0() -> None:
    g = Goal(id="g1", description="x", priority=-3)
    assert g.priority == 0


def test_priority_unknown_str_defaults_to_5() -> None:
    """未知词 → fallback 默认 5 (medium), 不抛."""
    g = Goal(id="g1", description="x", priority="???")
    assert g.priority == 5


# ---------------------------------------------------------------------------
# progress 强转
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0%", 0.0),
        ("15%", 0.15),
        ("100%", 1.0),
        ("50 %", 0.5),  # 带空格
    ],
)
def test_progress_pct_str_to_float(raw, expected) -> None:
    g = Goal(id="g1", description="x", progress=raw)
    assert g.progress == pytest.approx(expected)


def test_progress_float_passes_through() -> None:
    g = Goal(id="g1", description="x", progress=0.45)
    assert g.progress == 0.45


def test_progress_int_pct_interpreted() -> None:
    """progress=15 (int >1) → 0.15 (兼容 LLM 误把 0-100 当作百分比)."""
    g = Goal(id="g1", description="x", progress=15)
    assert g.progress == pytest.approx(0.15)


def test_progress_int_above_100_clamped() -> None:
    g = Goal(id="g1", description="x", progress=150)
    assert g.progress == 1.0


def test_progress_negative_clamped_to_0() -> None:
    g = Goal(id="g1", description="x", progress=-0.2)
    assert g.progress == 0.0


def test_progress_str_unparseable_defaults_to_0() -> None:
    g = Goal(id="g1", description="x", progress="???")
    assert g.progress == 0.0


# ---------------------------------------------------------------------------
# id 强转
# ---------------------------------------------------------------------------


def test_id_int_coerced_to_str() -> None:
    """run 1 实测 LLM 反复出 id=10 (int). Schema 要 str."""
    g = Goal(id=10, description="x")
    assert g.id == "10"


def test_id_str_passes_through() -> None:
    g = Goal(id="goal_x", description="y")
    assert g.id == "goal_x"


# ---------------------------------------------------------------------------
# Description still required (irrecoverable)
# ---------------------------------------------------------------------------


def test_missing_description_still_raises() -> None:
    """description 缺失不可强转, 仍抛 ValidationError."""
    with pytest.raises(ValidationError):
        Goal(id="g1")


def test_content_alias_filled_into_description() -> None:
    """LLM 偶发用 'content' 替代 'description' 字段 (实测 run 2). 应 alias."""
    g = Goal(id="g1", content="某目标内容")
    assert g.description == "某目标内容"


# ---------------------------------------------------------------------------
# Combined real-world LLM payload (run 1/2 实测)
# ---------------------------------------------------------------------------


def test_real_world_run1_payload() -> None:
    """Run 1 实际看到的 payload: id=int + priority=str + progress=str%."""
    g = Goal(
        id=10,
        description="对比脚架部件碎片的腐蚀痕迹与档案室西墙铆钉",
        priority="critical",
        progress="5%",
    )
    assert g.id == "10"
    assert g.priority == 10
    assert g.progress == pytest.approx(0.05)


def test_real_world_run2_payload_with_content() -> None:
    """Run 2 payload: id 是 str 但用了 content 字段名."""
    g = Goal(
        id="goal_10_decode_message",
        content="解码前一次迭代版本留在墨珩铜环嵌套结构里的暗格字符",
        priority=10,
    )
    assert g.description.startswith("解码")
    assert g.priority == 10


# ---------------------------------------------------------------------------
# iter#GG — bootstrap path coverage. Goal validator runs transitively when
# CharacterState.model_validate processes current_goals list. 锁定: 不需要
# bootstrap 改, J 已覆盖.
# ---------------------------------------------------------------------------


def test_bootstrap_character_state_passes_bad_goals_through_validator() -> None:
    """CharacterState.model_validate with LLM bad goal payload → Goal validator
    transparently coerces. 不需 bootstrap 改, J 已覆盖."""
    from memory_system.models import CharacterState

    payload = {
        "character_id": "char_test",
        "current_goals": [
            {
                "id": 10,
                "description": "对比铜环刻度",
                "priority": "critical",
                "progress": "15%",
            },
            {
                "id": "goal_y",
                "content": "用 content alias",
                "priority": "high",
            },
        ],
    }
    state = CharacterState.model_validate(payload)
    assert state.character_id == "char_test"
    assert len(state.current_goals) == 2
    # int id → str
    assert state.current_goals[0].id == "10"
    # 'critical' → 10
    assert state.current_goals[0].priority == 10
    # '15%' → 0.15
    assert state.current_goals[0].progress == pytest.approx(0.15)
    # content alias → description
    assert state.current_goals[1].description == "用 content alias"
    assert state.current_goals[1].priority == 8
