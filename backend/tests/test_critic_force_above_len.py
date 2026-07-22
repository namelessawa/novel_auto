"""Phase 6 iter#O — critic length-gate 加严.

接 verdict-spike-rootcause-0625 #2 carry-forward. Run 2 critic 仅 24/500 tick
invoke, 即 ~4% rate (= ≥600 chars 段落比例). spike 段 max 4123 chars 但若
importance 不到 gate (7) 仍跳 critic. 加 CRITIC_FORCE_ABOVE_LEN=2500: 段落
超此长度强制 critic, 哪怕 importance 不到 gate.

锁定:
* 长 narrative (>2500) + 低 importance → critic 被强制
* 短 narrative + 低 importance → critic 跳 (老行为, 不破)
* 长 narrative + 高 importance → critic 自然 invoke (老 path, 不破)
* env CRITIC_FORCE_ABOVE_LEN=0 → disable (回老行为)
* env CRITIC_FORCE_ABOVE_LEN 自定义阈值
* critic 不存在 (enable_critic=False) → 长 narrative 也跳, 不抛
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


from agents.narrator_agent import _critic_force_above_len  # noqa: E402


# ---------------------------------------------------------------------------
# Env knob reader
# ---------------------------------------------------------------------------


def test_force_above_len_default(monkeypatch) -> None:
    monkeypatch.delenv("CRITIC_FORCE_ABOVE_LEN", raising=False)
    assert _critic_force_above_len() == 2500


def test_force_above_len_custom(monkeypatch) -> None:
    monkeypatch.setenv("CRITIC_FORCE_ABOVE_LEN", "3000")
    assert _critic_force_above_len() == 3000


def test_force_above_len_disabled_zero(monkeypatch) -> None:
    """0 → disable (返回大值, 实际等同永远不强制)."""
    monkeypatch.setenv("CRITIC_FORCE_ABOVE_LEN", "0")
    # 0 表示 disable, 视实现可返回 0 或 inf — 锁定语义: ≤ 0 时永不触发
    val = _critic_force_above_len()
    assert val == 0 or val > 10_000


def test_force_above_len_invalid_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("CRITIC_FORCE_ABOVE_LEN", "abc")
    assert _critic_force_above_len() == 2500


def test_force_above_len_negative_falls_back(monkeypatch) -> None:
    """负值无意义 → 回 default."""
    monkeypatch.setenv("CRITIC_FORCE_ABOVE_LEN", "-100")
    assert _critic_force_above_len() == 2500


# ---------------------------------------------------------------------------
# Integration via _should_force_critic_by_length helper
# ---------------------------------------------------------------------------


def test_should_force_critic_long_narrative() -> None:
    from agents.narrator_agent import _should_force_critic_by_length
    assert _should_force_critic_by_length(3000) is True


def test_should_force_critic_short_narrative() -> None:
    from agents.narrator_agent import _should_force_critic_by_length
    assert _should_force_critic_by_length(1500) is False


def test_should_force_critic_at_boundary() -> None:
    """正好等于阈值 → 不触发 (要求 > 严格)."""
    from agents.narrator_agent import _should_force_critic_by_length
    assert _should_force_critic_by_length(2500) is False


def test_should_force_critic_disabled(monkeypatch) -> None:
    monkeypatch.setenv("CRITIC_FORCE_ABOVE_LEN", "0")
    from agents.narrator_agent import _should_force_critic_by_length
    assert _should_force_critic_by_length(10000) is False


def test_should_force_critic_custom_threshold(monkeypatch) -> None:
    monkeypatch.setenv("CRITIC_FORCE_ABOVE_LEN", "1000")
    from agents.narrator_agent import _should_force_critic_by_length
    assert _should_force_critic_by_length(1500) is True
    assert _should_force_critic_by_length(500) is False
