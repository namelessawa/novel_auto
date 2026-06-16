"""Phase 5-B: det 层决定 WorldSimulator 能否跳 LLM (stale tick skip).

设计来自 PHASE5_PLAN.md 候选 I:

世界很多 tick 真静态 (无场景切换、无重大事件), 让 LLM 跑 ~3-5k tokens 只为
返回 "天气还是阴, 时间 +1" 是浪费. 这一层在调 LLM 前做 det 检查, 满足全部
条件就 short-circuit, 直接构造一个零变化 delta + 1 条 stale 自然事件.

# 触发条件 (全部满足才 skip)

1. 上 tick 所有 events 的 max narrative_value < 5 (低价值 tick)
2. 上 tick 没有任何 type 包含 'setting' / 'scene' 的事件 (无场景切换)
3. 距上次实际 LLM world_simulator 调用 < ``max_consecutive_skip`` tick
   (防止 stale 累积漂移, 默认 3)

# 反对意见与对策

* "world 静止不代表无内容" — 即使 skip, 我们仍 emit 一条 stale 自然事件
  ("世界静止, 无显著变化"), 让 CharacterAgent 有可见输入, 不会 starve.
* "stale 累积漂移" — max_consecutive_skip 强制 N tick 后必跑 LLM,
  让世界 refresh.
* "高价值 tick 不能漏" — narrative_value >= 5 任一即不 skip; 默认 EventInjector
  会给 setting/arc/重大事件 value >= 5.

# 不在这一层 (留给 caller)

* metric 计数 (caller / tick_runtime 负责)
* 把决定写回 WorldSimulator 实例的 _last_llm_world_time
* env 开关 (caller 自己读)
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from memory_system.models import Event


# Phase 5-B 调优阈值 (env 可覆盖, 但默认与 PHASE5_PLAN 保持一致).
_DEFAULT_NARRATIVE_VALUE_CAP = 5  # 任一 event >= 此值即不 skip
_DEFAULT_MAX_CONSECUTIVE_SKIP = 3  # 距上次 LLM 调用 >= 此值强制 refresh

# Event.type 在本仓 schema 中是 Literal['endogenous','exogenous','dramatic','character_action'].
# 'dramatic' 是 EventInjector / Showrunner 给场景节拍 / 重大冲突时打的标, 本仓里
# 等价于 PHASE5_PLAN 所说的 "setting_change / location 切换" — 任何 dramatic 事件
# 都意味着世界状态可能要 LLM 重新评估, 不能 skip.
_HIGH_IMPACT_EVENT_TYPES = frozenset({"dramatic"})


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


@dataclass(frozen=True)
class StaleDecision:
    """det 层决定. ``should_skip=False`` 时 ``reason`` 解释为什么必须跑 LLM."""

    should_skip: bool
    reason: str

    def __bool__(self) -> bool:  # 让 if decision: 等价于 if should_skip
        return self.should_skip


def _max_narrative_value(events: list[Event]) -> int:
    """events 中 max(narrative_value, narrative_value_hint). 空 list 返回 0."""
    if not events:
        return 0
    return max(
        max(e.narrative_value or 0, getattr(e, "narrative_value_hint", 0) or 0)
        for e in events
    )


def _any_high_impact_event(events: list[Event]) -> bool:
    """任一 event 的 type 是 high-impact (dramatic) 即 True.

    本仓 Event.type 是 Literal 限 4 个枚举值, 不存在 'setting_change' / 'location_change'.
    'dramatic' 是 EventInjector / Showrunner 给场景节拍 + 重大冲突打的标.
    """
    return any((e.type or "") in _HIGH_IMPACT_EVENT_TYPES for e in events)


def evaluate_stale(
    *,
    current_world_time: int,
    last_llm_world_time: int,
    last_tick_events: list[Event],
    narrative_value_cap: int | None = None,
    max_consecutive_skip: int | None = None,
) -> StaleDecision:
    """Phase 5-B 主 API. 返回 (should_skip, reason).

    Args:
        current_world_time: 本 tick 入口的 world_state.world_time
            (调用 simulate 前的值, 不是 +time_step 后的)
        last_llm_world_time: 上次实际跑 LLM world_simulator 时的 current_world_time.
            -1 表示 "WorldSimulator 还未跑过 LLM" (冷启动) — 一律不 skip.
        last_tick_events: 上 tick 已发生的全部 events (natural + injected + action).
        narrative_value_cap: max narrative_value 触发 force-refresh 的阈值.
            None → 读 WORLD_STALE_VALUE_CAP env, 兜底 5.
        max_consecutive_skip: 距上次 LLM 调用 >= 此值时强制 refresh.
            None → 读 WORLD_STALE_MAX_SKIP env, 兜底 3.
    """
    cap = (
        narrative_value_cap
        if narrative_value_cap is not None
        else _env_int("WORLD_STALE_VALUE_CAP", _DEFAULT_NARRATIVE_VALUE_CAP)
    )
    max_skip = (
        max_consecutive_skip
        if max_consecutive_skip is not None
        else _env_int("WORLD_STALE_MAX_SKIP", _DEFAULT_MAX_CONSECUTIVE_SKIP)
    )

    # Rule 1: cold start — 必须跑 LLM 至少一次, 建立世界基线
    if last_llm_world_time < 0:
        return StaleDecision(False, "cold_start_first_call_must_use_llm")

    # Rule 2: 防漂移 — 距上次 LLM 调用 >= max_skip tick 必须 refresh
    ticks_since_llm = current_world_time - last_llm_world_time
    if ticks_since_llm >= max_skip:
        return StaleDecision(
            False,
            f"force_refresh_after_{ticks_since_llm}_ticks_since_llm",
        )

    # Rule 3: 高价值事件不能漏
    max_value = _max_narrative_value(last_tick_events)
    if max_value >= cap:
        return StaleDecision(
            False, f"high_value_event(max_narrative_value={max_value}>={cap})"
        )

    # Rule 4: dramatic 事件不能漏 (场景节拍 / 重大冲突)
    if _any_high_impact_event(last_tick_events):
        return StaleDecision(False, "high_impact_event_present")

    # 全部 stale 条件满足
    return StaleDecision(
        True,
        f"stale(ticks_since_llm={ticks_since_llm},max_value={max_value})",
    )
