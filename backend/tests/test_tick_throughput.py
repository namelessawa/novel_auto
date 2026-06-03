"""Tick 提速验证 (v2.18 Phase 7)。

不减 token 预算的提速:
1. CHARACTER_AGENT_CONCURRENCY 默认从 3 提到 6 — 6 角色一次并发跑完, 不再分两批
2. Narrator (阶段 6) + 只读类周期 agent (Guardian/Critic/ArcTracker) 并行,
   MemoryCompressor 仍串行 (写 memory_store 避免 race)

测试:
- CharacterAgent._default_concurrency 默认 6
- env var 仍可覆盖
- _phase7_readonly_agents 独立可调, 在并行场景下不阻塞 Narrator
"""

from __future__ import annotations

import asyncio

import pytest

from agents.character_agent import _default_concurrency
from agents.orchestrator import Orchestrator
from memory.tick_state import TickState
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    Event,
    TickLocation,
    WorldState,
)
from nf_core.action_resolver import ActionResolver


def _ts(tmp_path) -> TickState:
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(
        WorldState(locations=[TickLocation(id="loc_a", name="A")])
    )
    ts.upsert_character_profile(
        CharacterProfile(id="elara", name="Elara", importance_tier="A")
    )
    ts.upsert_character_state(CharacterState(character_id="elara"))
    return ts


def test_default_concurrency_is_six(monkeypatch) -> None:
    monkeypatch.delenv("CHARACTER_AGENT_CONCURRENCY", raising=False)
    assert _default_concurrency() == 6


def test_concurrency_env_override(monkeypatch) -> None:
    monkeypatch.setenv("CHARACTER_AGENT_CONCURRENCY", "12")
    assert _default_concurrency() == 12


def test_concurrency_env_invalid_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("CHARACTER_AGENT_CONCURRENCY", "not-a-number")
    assert _default_concurrency() == 6


def test_concurrency_env_zero_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("CHARACTER_AGENT_CONCURRENCY", "0")
    assert _default_concurrency() == 6


# ------------------------------------------------------------------
# _phase7_readonly_agents 独立可调
# ------------------------------------------------------------------


class _StubGuardian:
    """模拟一个会被 Orchestrator 调度的 Guardian, 记录被调次数。"""

    def __init__(self) -> None:
        self.calls = 0

    async def scan(self, **kwargs):
        self.calls += 1
        from agents.consistency_guardian import GuardianOutput

        return GuardianOutput(scan_summary="stub", conflicts=[])


class _StubCritic:
    def __init__(self) -> None:
        self.calls = 0

    async def critique(self, **kwargs):
        self.calls += 1

        class _Out:
            recommendations = ["stub_warning"]

        return _Out()


class _StubArcTracker:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, **kwargs):
        self.calls += 1

        class _Out:
            reports: list = []
            summary = ""

        return _Out()


@pytest.mark.asyncio
async def test_phase7_readonly_agents_runs_all_three_when_cadence_match(
    tmp_path,
) -> None:
    """tick 同时满足三个 cadence 时, 三个 agent 都被调用。"""
    ts = _ts(tmp_path)
    g, c, a = _StubGuardian(), _StubCritic(), _StubArcTracker()
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=None,  # type: ignore[arg-type]
        character_agents={},
        narrator=None,  # type: ignore[arg-type]
        action_resolver=ActionResolver(),
        consistency_guardian=g,  # type: ignore[arg-type]
        novelty_critic=c,  # type: ignore[arg-type]
        character_arc_tracker=a,  # type: ignore[arg-type]
    )
    orch._last_tick_events = []  # phase7 读取的字段
    agents_called: list[str] = []
    # tick = 60 同时是 20/30/30 的倍数
    await orch._phase7_readonly_agents(tick=60, agents_called=agents_called)
    assert g.calls == 1
    assert c.calls == 1
    assert a.calls == 1
    assert "consistency_guardian" in agents_called
    assert "novelty_critic" in agents_called
    assert "character_arc_tracker" in agents_called


@pytest.mark.asyncio
async def test_phase7_readonly_agents_skips_offcadence(tmp_path) -> None:
    """tick=1 不满足任何 cadence, 应全部跳过, 不阻塞。"""
    ts = _ts(tmp_path)
    g, c, a = _StubGuardian(), _StubCritic(), _StubArcTracker()
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=None,  # type: ignore[arg-type]
        character_agents={},
        narrator=None,  # type: ignore[arg-type]
        action_resolver=ActionResolver(),
        consistency_guardian=g,  # type: ignore[arg-type]
        novelty_critic=c,  # type: ignore[arg-type]
        character_arc_tracker=a,  # type: ignore[arg-type]
    )
    orch._last_tick_events = []
    agents_called: list[str] = []
    await orch._phase7_readonly_agents(tick=1, agents_called=agents_called)
    assert g.calls == 0
    assert c.calls == 0
    assert a.calls == 0
    assert agents_called == []


@pytest.mark.asyncio
async def test_phase7_readonly_agents_runs_concurrently(tmp_path) -> None:
    """三个 agent 应该并行跑, 总时长接近最慢的那个 (而非三者之和)。"""
    ts = _ts(tmp_path)

    class _SlowAgent:
        def __init__(self, label: str, delay: float) -> None:
            self.label = label
            self.delay = delay
            self.calls = 0

        async def scan(self, **kwargs):
            self.calls += 1
            await asyncio.sleep(self.delay)
            from agents.consistency_guardian import GuardianOutput
            return GuardianOutput(scan_summary=self.label, conflicts=[])

        async def critique(self, **kwargs):
            self.calls += 1
            await asyncio.sleep(self.delay)

            class _Out:
                recommendations: list = []

            return _Out()

        async def evaluate(self, **kwargs):
            self.calls += 1
            await asyncio.sleep(self.delay)

            class _Out:
                reports: list = []
                summary = ""

            return _Out()

    g = _SlowAgent("g", 0.3)
    c = _SlowAgent("c", 0.3)
    a = _SlowAgent("a", 0.3)
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=None,  # type: ignore[arg-type]
        character_agents={},
        narrator=None,  # type: ignore[arg-type]
        action_resolver=ActionResolver(),
        consistency_guardian=g,  # type: ignore[arg-type]
        novelty_critic=c,  # type: ignore[arg-type]
        character_arc_tracker=a,  # type: ignore[arg-type]
    )
    orch._last_tick_events = []

    import time
    t0 = time.monotonic()
    await orch._phase7_readonly_agents(tick=60, agents_called=[])
    elapsed = time.monotonic() - t0
    # 并行: 应该 ≈ 0.3s; 串行会 ≈ 0.9s。给 0.6s 上限做缓冲。
    assert elapsed < 0.6, f"phase7 readonly agents not concurrent: elapsed={elapsed:.2f}s"


@pytest.mark.asyncio
async def test_phase7_readonly_agents_handles_exceptions(tmp_path) -> None:
    """单个 agent 抛异常不应阻塞其他 agent 完成。"""
    ts = _ts(tmp_path)

    class _ExplodingGuardian:
        async def scan(self, **kwargs):
            raise RuntimeError("guardian boom")

    g = _ExplodingGuardian()
    c = _StubCritic()
    a = _StubArcTracker()
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=None,  # type: ignore[arg-type]
        character_agents={},
        narrator=None,  # type: ignore[arg-type]
        action_resolver=ActionResolver(),
        consistency_guardian=g,  # type: ignore[arg-type]
        novelty_critic=c,  # type: ignore[arg-type]
        character_arc_tracker=a,  # type: ignore[arg-type]
    )
    orch._last_tick_events = []
    agents_called: list[str] = []
    # 不应抛, 异常被吞掉; critic/arc_tracker 仍跑了
    await orch._phase7_readonly_agents(tick=60, agents_called=agents_called)
    assert c.calls == 1
    assert a.calls == 1
