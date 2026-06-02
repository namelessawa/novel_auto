"""Orchestrator — tick 架构的纯 Python 调度器。

对应 ``infinite-novel-multiagent-prompts.md`` 第 3 节 + 第 12 节伪代码。

> 你是无限小说生成系统的主调度器。你不创造内容,也不评价内容,你只负责按规则
> 推进系统状态。

7 阶段 tick 流程:

1. ``_phase1_advance_world`` - WorldSimulator 推进时间 / 天气 / 自然事件
2. ``_phase2_inject_events`` - 评估是否触发 Showrunner / EventInjector,合并事件
3. ``_phase3_character_decisions`` - 收集受影响角色,并行 CharacterAgent.batch_decide
4. ``_phase4_resolve_conflicts`` - ActionResolver 解析独占冲突
5. ``_phase5_apply_changes`` - 把 CharacterAction 落到 CharacterState + 转为 Event
6. ``_phase6_narrate`` - NarratorAgent 决定是否产出叙述
7. ``_phase7_periodic_maintenance`` - 每 N tick 调用 MemoryCompressor /
   ConsistencyGuardian / NoveltyCritic(P1/P2)

P0 阶段: Showrunner / EventInjector / MemoryCompressor / ConsistencyGuardian /
NoveltyCritic 五个 agent 还未实现,Orchestrator 通过 Optional 参数兼容它们的缺席。
缺席时仅记录到 TickSummary.agents_called 但不阻塞主流程。

调度禁区(prompts.md 第 3 节):
* 不修改任何 agent 返回的内容
* 不替 Narrator 决定是否产出叙述
* 不替角色 agent 决定其行动
* 不凭空创造事件(那是 EventInjector 的工作)
* 不解释、不评价、不建议剧情走向(那是 Showrunner 的工作)
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import AsyncIterator, Protocol

from agents.character_agent import CharacterAgent
from agents.character_arc_tracker import (
    CharacterArcTracker,
    CharacterArcTrackerOutput,
)
from agents.narrator_agent import NarratorAgent, NarratorOutput
from agents.story_arc_director import StoryArcDirector
from agents.world_simulator import WorldSimulator
from memory.memory_store import PriorityMemoryStore, RetrievalQuery
from memory.tick_state import TickState
from narrative.creativity_scorer import CreativityReport, CreativityScorer
from narrative.fact_ledger import Fact, FactLedger
from narrative.safety_filter import SafetyFilter
from nf_core.token_budget import TokenBudgetTracker, get_global_tracker, set_global_tracker
from memory_system.models import (
    CharacterAction,
    CharacterState,
    Event,
    MemoryEntry,
    TickSummary,
    WorldState,
)
from nf_core.action_resolver import ActionResolver, ResolutionDiagnostic
from persistence.tick_db import TickDB

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# P1/P2 agent 协议(P0 时这些类还不存在,用 Protocol 占位避免循环 import)
# ------------------------------------------------------------------


class ShowrunnerProtocol(Protocol):
    async def assess(self, **kwargs) -> dict: ...  # noqa: D401


class EventInjectorProtocol(Protocol):
    async def inject(self, **kwargs) -> list[Event]: ...


class MemoryCompressorProtocol(Protocol):
    async def compress(self, **kwargs) -> dict: ...


class ConsistencyGuardianProtocol(Protocol):
    async def scan(self, **kwargs) -> dict: ...


class NoveltyCriticProtocol(Protocol):
    async def critique(self, **kwargs) -> dict: ...


# ------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


SHOWRUNNER_CADENCE = _env_int("SHOWRUNNER_CADENCE", 5)
NOVELTY_CRITIC_CADENCE = _env_int("NOVELTY_CRITIC_CADENCE", 20)
CONSISTENCY_GUARDIAN_CADENCE = _env_int("CONSISTENCY_GUARDIAN_CADENCE", 30)
MEMORY_COMPRESSOR_CADENCE = _env_int("MEMORY_COMPRESSOR_CADENCE", 50)
CHARACTER_ARC_TRACKER_CADENCE = _env_int("CHARACTER_ARC_TRACKER_CADENCE", 30)

# 戏剧/外生事件冷却:Showrunner 没就位时,EventInjector 自身的简单触发判断
EXOGENOUS_COOLDOWN_TICKS = _env_int("EXOGENOUS_COOLDOWN_TICKS", 10)
MIN_OPEN_LOOPS = _env_int("MIN_OPEN_LOOPS", 3)


def _get_main_character_id_from_env() -> str | None:
    val = os.environ.get("MAIN_TRACKING_CHARACTER_ID", "").strip()
    return val or None


class Orchestrator:
    """主调度器。所有 LLM 调用都委托给传入的 agent 实例。"""

    def __init__(
        self,
        tick_state: TickState,
        world_simulator: WorldSimulator,
        character_agents: dict[str, CharacterAgent],
        narrator: NarratorAgent,
        action_resolver: ActionResolver,
        *,
        showrunner: ShowrunnerProtocol | None = None,
        event_injector: EventInjectorProtocol | None = None,
        memory_compressor: MemoryCompressorProtocol | None = None,
        consistency_guardian: ConsistencyGuardianProtocol | None = None,
        novelty_critic: NoveltyCriticProtocol | None = None,
        tick_db: TickDB | None = None,
        main_tracking_character_id: str | None = None,
        narrative_text_writer=None,  # Callable[[int, str], Awaitable[None]] - 可选
        memory_store: PriorityMemoryStore | None = None,
        story_arc_director: StoryArcDirector | None = None,
        character_arc_tracker: CharacterArcTracker | None = None,
        fact_ledger: FactLedger | None = None,
        safety_filter: SafetyFilter | None = None,
        token_budget: TokenBudgetTracker | None = None,
        creativity_scorer: CreativityScorer | None = None,
    ) -> None:
        self._tick_state = tick_state
        self._world_simulator = world_simulator
        self._character_agents = character_agents
        self._narrator = narrator
        self._action_resolver = action_resolver
        self._showrunner = showrunner
        self._event_injector = event_injector
        self._memory_compressor = memory_compressor
        self._consistency_guardian = consistency_guardian
        self._novelty_critic = novelty_critic
        self._tick_db = tick_db
        self._main_tracking_character_id = (
            main_tracking_character_id or _get_main_character_id_from_env()
        )
        # 长期记忆存储 (v2.3) — 自动加载 / 持久化, 阶段 5 后填充 L0, 阶段 7 压缩
        self._memory_store = memory_store or PriorityMemoryStore(
            tick_state.data_dir
        )
        try:
            self._memory_store.load()
        except Exception as e:  # pragma: no cover
            logger.warning("MemoryStore.load failed (non-fatal): %s", e)

        # v2.4 叙事大纲守护 — 每 N tick 调用一次, 阶段 6 注入 narrator_hint
        self._story_arc_director = story_arc_director
        # 上一轮 directive — 阶段 6 前用于注入 narrator_hint 到 recent_chapter_summaries
        self._last_story_directive = None

        # v2.5 人物弧光跟踪器 — 阶段 7 周期性维护时调用
        self._character_arc_tracker = character_arc_tracker
        # 角色最近 N 个 action 的环形缓冲, 供 tracker 输入
        self._recent_actions_by_char: dict[str, list[CharacterAction]] = {}
        # 上一轮 tracker 报告 — 阶段 6 前注入 Narrator 性格漂移警告
        self._last_arc_tracker_output: CharacterArcTrackerOutput | None = None

        # v2.6 事实账本 — 阶段 5 自动 ingest, 阶段 6 前注入冲突警告
        self._fact_ledger = fact_ledger or FactLedger(tick_state.data_dir)
        try:
            self._fact_ledger.load()
        except Exception as e:  # pragma: no cover
            logger.warning("FactLedger.load failed (non-fatal): %s", e)
        self._last_fact_conflicts: list[dict] = []

        # v2.7 安全过滤 — Narrator 落盘前检查 PII / 有害指南
        self._safety_filter = safety_filter or SafetyFilter()
        # v2.7 Token 预算追踪 — 持久化 + 全局单例共享
        self._token_budget = token_budget or TokenBudgetTracker(
            tick_state.data_dir
        )
        try:
            self._token_budget.load()
        except Exception as e:  # pragma: no cover
            logger.warning("TokenBudgetTracker.load failed (non-fatal): %s", e)
        set_global_tracker(self._token_budget)

        # v2.8 创造力评分 — 每段叙述后 ingest, 退化时 alert 注入 Narrator
        self._creativity_scorer = creativity_scorer or CreativityScorer()
        self._last_creativity_report: CreativityReport | None = None

        # narrative_text_writer(tick, text) - Orchestrator 把叙述文本交给外部写盘
        # 默认: 写到 ``{data_dir}/narratives/tick_{tick:06d}.txt``
        self._narrative_writer = narrative_text_writer or self._default_narrative_writer

        # 跨 tick 缓存
        self._last_tick_events: list[Event] = []
        self._recent_chapter_summaries: list[str] = []  # NarratorOutput 累积
        self._injected_pending: list[Event] = []  # 外部 inject_event 注入的 Event

        # 暂停/恢复
        self._paused: bool = False
        self._stop_requested: bool = False

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    @property
    def current_tick(self) -> int:
        return self._tick_state.current_tick

    @property
    def is_paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        self._paused = True
        logger.info("Orchestrator paused at tick %d", self.current_tick)

    def resume(self) -> None:
        self._paused = False
        logger.info("Orchestrator resumed at tick %d", self.current_tick)

    def request_stop(self) -> None:
        self._stop_requested = True

    def inject_event(self, event: Event) -> None:
        """外部手动注入事件(管理员/前端)。下一 tick 阶段 2 合并到事件流。"""
        self._injected_pending.append(event)
        logger.info(
            "External event injected: %s @ %s (visible to %d chars)",
            event.id,
            event.location,
            len(event.visible_to),
        )

    def add_character_agent(self, agent: CharacterAgent) -> None:
        """运行时新增角色(EventInjector 引入新人物时调用)。"""
        self._character_agents[agent.character_id] = agent

    async def run_tick(self) -> TickSummary:
        """执行单 tick 全 7 阶段。返回 TickSummary 供 TickDB / SSE 消费。"""
        tick = self._tick_state.advance_tick()
        agents_called: list[str] = []
        events_generated_ids: list[str] = []
        narrator_produced = False
        narrator_chars = 0

        # 阶段 1: 推进世界 ------------------------------------------------
        world_state = self._tick_state.world_state
        sim_out = await self._world_simulator.simulate(
            world_state=world_state,
            last_tick_events=self._last_tick_events,
            time_step=1,
        )
        agents_called.append("world_simulator")
        self._tick_state.set_world_state(sim_out.new_world_state)
        natural_events = sim_out.natural_events
        events_generated_ids.extend(e.id for e in natural_events)

        # 阶段 2: 事件注入 ------------------------------------------------
        injected_events: list[Event] = []
        showrunner_recs: list[dict] = []

        if self._showrunner is not None and tick % SHOWRUNNER_CADENCE == 0:
            try:
                event_stats = (
                    self._tick_db.get_event_stats(last_n_ticks=50)
                    if self._tick_db is not None
                    else {}
                )
                showrunner_out = await self._showrunner.assess(
                    character_arcs=self._tick_state.get_arc_status(),
                    open_loops=self._tick_state.get_open_loops(),
                    recent_chapters=self._recent_chapter_summaries[-20:],
                    event_stats=event_stats,
                    total_ticks=tick,
                    current_tick=tick,
                )
                showrunner_recs = list(getattr(showrunner_out, "recommendations", [])) or []
                agents_called.append("showrunner")
            except Exception as e:
                logger.error("Showrunner.assess failed: %s", e)

        if self._event_injector is not None and self._should_inject(tick):
            try:
                injector_out = await self._event_injector.inject(
                    tick=tick,
                    world_state=self._tick_state.world_state,
                    recent_events=self._last_tick_events,
                    tracking_chars=self._tick_state.list_character_states(),
                    open_loops=self._tick_state.get_open_loops(),
                    showrunner_recommendations=showrunner_recs,
                    dormant_characters=[],  # P2: 维护非活跃角色池
                )
                # 兼容返回 list[Event] 或带 events 字段的对象
                if hasattr(injector_out, "events"):
                    injected_events = list(injector_out.events)
                elif isinstance(injector_out, list):
                    injected_events = list(injector_out)
                events_generated_ids.extend(e.id for e in injected_events)
                agents_called.append("event_injector")
                if injected_events:
                    self._tick_state.record_last_event_tick("exogenous", tick)
            except Exception as e:
                logger.error("EventInjector.inject failed: %s", e)

        # 外部手动注入
        externally_injected = list(self._injected_pending)
        self._injected_pending.clear()
        events_generated_ids.extend(e.id for e in externally_injected)

        all_events: list[Event] = (
            list(natural_events) + injected_events + externally_injected
        )

        # 阶段 3: 角色决策 ------------------------------------------------
        affected_ids = self._collect_affected_characters(all_events)
        actions: list[CharacterAction] = []
        if affected_ids:
            agents_to_run = [
                self._character_agents[cid]
                for cid in affected_ids
                if cid in self._character_agents
            ]
            states_map = {
                cid: st
                for cid, st in (
                    (cid, self._tick_state.get_character_state(cid))
                    for cid in affected_ids
                )
                if st is not None
            }
            if agents_to_run:
                actions = await CharacterAgent.batch_decide(
                    agents_to_run, states_map, all_events
                )
                agents_called.append(f"character_agents×{len(actions)}")

        # 阶段 4: 冲突解析 ------------------------------------------------
        resolved_actions, resolve_diag = self._action_resolver.resolve(
            actions,
            profiles={cid: a.profile for cid, a in self._character_agents.items()},
            world_state=self._tick_state.world_state,
        )
        if resolve_diag.conflict_groups > 0:
            agents_called.append(
                f"action_resolver(conflicts={resolve_diag.conflict_groups})"
            )

        # 阶段 5: 应用变化 ------------------------------------------------
        action_events = self._apply_actions(tick, resolved_actions)
        events_generated_ids.extend(e.id for e in action_events)
        all_events.extend(action_events)

        # 阶段 5a: 记录本 tick 的 CharacterAction 到环形缓冲, 供 v2.5 tracker --
        for action in resolved_actions:
            buf = self._recent_actions_by_char.setdefault(action.character_id, [])
            buf.append(action)
            if len(buf) > 20:  # 每角色最多保留 20 条
                del buf[: len(buf) - 20]

        # 阶段 5b: 把本 tick 显著事件登记到长期记忆 (L0) -------------------
        self._ingest_events_to_memory(tick, all_events)

        # 阶段 5b': 把角色 location 变化登记到 FactLedger, 检测矛盾 (v2.6) --
        self._ingest_facts_from_actions(tick, resolved_actions)

        # 阶段 5c: StoryArcDirector — 节奏曲线 + 节拍守护 (v2.4) ----------
        await self._run_story_arc_director(tick, all_events)

        # 阶段 6: 叙述 ----------------------------------------------------
        narrator_out = await self._narrate(tick, all_events)
        agents_called.append("narrator")
        if narrator_out.should_narrate:
            # v2.7 安全过滤 — block 级命中跳过落盘
            safety_result = self._safety_filter.check(narrator_out.narrative_text)
            if safety_result.is_blocked:
                logger.warning(
                    "Narrator output BLOCKED by SafetyFilter at tick %d: %d hits",
                    tick,
                    len(safety_result.hits),
                )
                narrator_produced = False
            else:
                narrator_produced = True
                narrator_chars = len(narrator_out.narrative_text)
                self._tick_state.mark_narration(tick)
                final_text = (
                    safety_result.sanitized_text or narrator_out.narrative_text
                )
                await self._narrative_writer(tick, final_text)
                # v2.8 创造力评分: ingest 段落, 缓存最新 report 供下 tick 注入
                try:
                    self._creativity_scorer.ingest_paragraph(
                        final_text, tick=tick
                    )
                    self._last_creativity_report = (
                        self._creativity_scorer.report()
                    )
                except Exception as e:  # pragma: no cover
                    logger.debug("CreativityScorer ingest failed: %s", e)
        if narrator_out.should_narrate and narrator_produced:
            # 累积摘要 - 给 Narrator 下一轮 recent_chapter_summaries 用
            self._recent_chapter_summaries.append(
                f"tick {tick}: {narrator_out.scene_focus or narrator_out.narrative_text[:60]}…"
            )
            # 引用的 OpenLoop touch + 关联事件 touch
            for loop_id in narrator_out.open_loops_referenced:
                self._tick_state.touch_open_loop(loop_id, tick)
            # Narrator 实际消费的事件 → memory_store.touch (提升 ref_count, 防遗忘)
            for evt_id in narrator_out.events_consumed:
                self._memory_store.touch(evt_id, tick)
            # 新种 OpenLoop + 若 loop 关联了源事件, 标记为 protected
            for loop in narrator_out.newly_opened_loops:
                self._tick_state.add_open_loop(loop)
                origin_ids = getattr(loop, "origin_event_ids", None) or []
                for evt_id in origin_ids:
                    self._memory_store.mark_protected(
                        evt_id, reason=f"open_loop:{loop.id}"
                    )
        else:
            # 仍要把 tick_summary_for_record 累积,供未来 Narrator 上下文
            if narrator_out.tick_summary_for_record:
                self._recent_chapter_summaries.append(narrator_out.tick_summary_for_record)

        # 阶段 7: 周期性维护 ---------------------------------------------
        await self._phase7_periodic_maintenance(tick, agents_called)

        # OpenLoop 过期清理(防 prompt 膨胀)
        reaped = self._tick_state.reap_stale_open_loops(tick)
        if reaped:
            agents_called.append(f"loop_reaper(-{len(reaped)})")

        # 持久化(原子写)
        self._tick_state.save()
        try:
            self._memory_store.save()
        except Exception as e:  # pragma: no cover
            logger.warning("MemoryStore.save failed (non-fatal): %s", e)
        try:
            self._fact_ledger.save()
        except Exception as e:  # pragma: no cover
            logger.warning("FactLedger.save failed (non-fatal): %s", e)
        try:
            self._token_budget.save()
        except Exception as e:  # pragma: no cover
            logger.warning("TokenBudgetTracker.save failed (non-fatal): %s", e)

        # 维持 recent_chapter_summaries 上限
        if len(self._recent_chapter_summaries) > 100:
            self._recent_chapter_summaries = self._recent_chapter_summaries[-50:]

        self._last_tick_events = all_events

        summary = TickSummary(
            tick=tick,
            world_time=self._tick_state.world_state.world_time,
            world_time_advanced=sim_out.delta_summary[:200],
            agents_called=agents_called,
            events_generated=events_generated_ids,
            narrator_produced_text=narrator_produced,
            narrator_output_chars=narrator_chars,
            state_changes_summary=self._compose_state_changes(
                resolved_actions, narrator_out
            ),
            next_tick_recommendations=self._next_tick_hints(tick),
        )

        # TickDB 持久化 - SQLite 事务保证 tick_log + events 同步写入
        if self._tick_db is not None:
            try:
                self._tick_db.insert_tick(summary, events=all_events)
            except Exception as e:
                logger.error("TickDB.insert_tick failed (non-fatal): %s", e)

        return summary

    async def start_loop(
        self, max_ticks: int | None = None
    ) -> AsyncIterator[TickSummary]:
        """主循环。``max_ticks=None`` 表示不限步数(prompts.md 的 "永不停止" 理念)。

        外部可通过 ``pause()`` / ``request_stop()`` 控制。每 tick yield 一个
        TickSummary,供 SSE 推送 / TickDB 写入。
        """
        n = 0
        while True:
            if self._stop_requested:
                logger.info("Orchestrator stopped at tick %d", self.current_tick)
                break
            if self._paused:
                await asyncio.sleep(0.5)
                continue
            summary = await self.run_tick()
            yield summary
            n += 1
            if max_ticks is not None and n >= max_ticks:
                logger.info("Orchestrator reached max_ticks=%d", max_ticks)
                break

    # ------------------------------------------------------------------
    # 阶段实现细节
    # ------------------------------------------------------------------

    def _should_inject(self, tick: int) -> bool:
        """EventInjector 触发判断(prompts.md 第 3 节 + 5 节)。"""
        if self._tick_state.ticks_since_last_event("exogenous", tick) > EXOGENOUS_COOLDOWN_TICKS:
            return True
        if self._tick_state.get_open_loop_count() < MIN_OPEN_LOOPS:
            return True
        return False

    def _collect_affected_characters(self, events: list[Event]) -> list[str]:
        """阶段 3 输入:在事件位置/参与者/可见集合中的 A/B 级角色。

        可见性标记规则:
        * ``"all"`` → 所有 A/B 级 CharacterAgent 都被波及
        * ``"all_in_location"`` → 在 event.location 同地点的所有 A/B 级角色
        * 其他字符串 → 视为具体 character_id
        """
        affected: set[str] = set()
        for event in events:
            affected.update(event.participants)
            visible_set = set(event.visible_to)

            if "all" in visible_set:
                for cid, agent in self._character_agents.items():
                    if agent.profile.importance_tier in {"A", "B"}:
                        affected.add(cid)
                visible_set.discard("all")

            if "all_in_location" in visible_set:
                for state in self._tick_state.list_character_states():
                    agent = self._character_agents.get(state.character_id)
                    if agent is None or agent.profile.importance_tier == "C":
                        continue
                    if event.location and state.current_location == event.location:
                        affected.add(state.character_id)
                visible_set.discard("all_in_location")

            affected.update(visible_set)

        # 仅保留有 CharacterAgent 实例且非 C 级的
        result = []
        for cid in affected:
            agent = self._character_agents.get(cid)
            if agent is None:
                continue
            if agent.profile.importance_tier == "C":
                continue
            result.append(cid)
        return result

    async def _run_story_arc_director(
        self, tick: int, all_events: list[Event]
    ) -> None:
        """阶段 5c: 调用 StoryArcDirector, 把 directive 缓存供阶段 6 _narrate 使用。"""
        if self._story_arc_director is None:
            return
        arc = self._tick_state.get_story_arc()
        if arc is None:
            return
        # 本 tick narrative_value 总和 (作为 pacing 采样)
        nv_sum = sum(
            max(e.narrative_value or 0, e.narrative_value_hint or 0)
            for e in all_events
        )
        try:
            directive = await self._story_arc_director.direct(
                arc=arc,
                current_tick=tick,
                recent_events=all_events,
                recent_narrator_value_sum=nv_sum,
                narrator_produced=False,  # 阶段 6 还没跑, 这里只采样
            )
            arc.last_updated_tick = tick
            self._tick_state.set_story_arc(arc)
            self._last_story_directive = directive
        except Exception as e:
            logger.warning("StoryArcDirector.direct failed (non-fatal): %s", e)
            self._last_story_directive = None

    def _ingest_facts_from_actions(
        self, tick: int, actions: list[CharacterAction]
    ) -> None:
        """阶段 5b': 把本 tick 的角色位置/死亡/持有变化登记到 FactLedger。

        策略:
        * action.target 看似地点 (有 "loc_" 前缀或匹配 world_state.locations.id) →
          location fact
        * action_type == "die" / status_effects 含 "dead" → death fact
        * 检测矛盾 → 写入 _last_fact_conflicts, 阶段 6 注入 Narrator
        """
        if not actions:
            return
        location_ids = {loc.id for loc in self._tick_state.world_state.locations}
        conflicts_collected: list[dict] = []
        for idx, action in enumerate(actions):
            state = self._tick_state.get_character_state(action.character_id)
            if state is None:
                continue
            new_facts: list[Fact] = []
            # location: action.target 像 location_id, 或 action_type == "move"
            target = action.target or ""
            if target and target in location_ids:
                new_facts.append(
                    Fact(
                        id=f"fact_loc_{tick}_{action.character_id}_{idx}",
                        kind="location",
                        subject=action.character_id,
                        predicate=target,
                        established_tick=tick,
                        source_event_id="",
                    )
                )
            # death
            if "dead" in (state.status_effects or []) or action.action_type == "die":
                new_facts.append(
                    Fact(
                        id=f"fact_death_{tick}_{action.character_id}",
                        kind="death",
                        subject=action.character_id,
                        predicate=action.description[:80] or "未明",
                        established_tick=tick,
                    )
                )
            # 检测 + 提交
            for f in new_facts:
                conflicts = self._fact_ledger.contradict_check(f)
                for c in conflicts:
                    conflicts_collected.append(c.to_dict())
                self._fact_ledger.assert_fact(f)
        self._last_fact_conflicts = conflicts_collected[-5:]  # 上限 5 条

    def _ingest_events_to_memory(self, tick: int, events: list[Event]) -> None:
        """阶段 5b: 把本 tick 显著事件登记到 PriorityMemoryStore 的 L0 层。

        策略:
        * 仅登记 narrative_value (或 hint) ≥ 4 的事件 (背景级别以下不入库)
        * 情感色彩从 event.type 推断 (character_action 等 → []) 后续可由
          Narrator 补充
        * 不重复登记 — store.add 已是 upsert
        """
        if not events:
            return
        for evt in events:
            score = max(evt.narrative_value or 0, evt.narrative_value_hint or 0)
            if score < 4:
                continue
            entry = MemoryEntry(
                id=evt.id,
                tier="L0",
                original_tick_range=(evt.tick, evt.tick),
                summary=evt.description[:200],
                involved=list(evt.participants),
                importance=min(10, max(1, score)),
                emotional_tags=[],
            )
            self._memory_store.add(entry, current_tick=tick)

    def _apply_actions(
        self, tick: int, actions: list[CharacterAction]
    ) -> list[Event]:
        """阶段 5: 应用 CharacterAction 到 CharacterState 并生成 character_action Event。"""
        action_events: list[Event] = []
        for action in actions:
            state = self._tick_state.get_character_state(action.character_id)
            if state is None:
                continue

            # 应用 goal updates
            new_goals = [
                g for g in state.current_goals
                if g.id not in action.completed_goal_ids
                and g.id not in action.abandoned_goal_ids
            ] + list(action.new_goals)

            # 应用 knowledge updates
            facts = list(state.known_facts)
            for f in action.newly_learned:
                if f and f not in facts:
                    facts.append(f)
            speculations = list(state.known_facts)  # 暂归并 known_facts;P1 拆 separate field

            # 应用 emotional shift
            emotional = state.emotional_state
            if action.emotional_shift:
                emotional = action.emotional_shift

            updated = state.model_copy(
                update={
                    "current_goals": new_goals,
                    "known_facts": facts,
                    "emotional_state": emotional,
                }
            )
            self._tick_state.upsert_character_state(updated)

            # 转换为 Event
            visible_to = self._infer_visible_to(action, state)
            # v2.11 — action 事件不再默认 nv=0, 否则 narrator 早期总跳过。
            # 启发式: dialogue + 完成 goal + 新 learned 各 +1, emotional_shift +1
            nv_hint = 1
            if action.dialogue_spoken:
                nv_hint += 1
            if action.completed_goal_ids:
                nv_hint += 1
            if action.newly_learned:
                nv_hint += 1
            if action.emotional_shift:
                nv_hint += 1
            if "fight" in (action.action_type or "") or "attack" in (action.action_type or ""):
                nv_hint += 2
            nv_hint = min(nv_hint, 6)  # 上限, narrator 仍可自己评估更高
            event = Event(
                id=f"evt_act_{tick}_{action.character_id}_{uuid.uuid4().hex[:6]}",
                tick=tick,
                type="character_action",
                location=state.current_location,
                participants=[action.character_id]
                + ([action.target] if action.target else [])
                + list(action.dialogue_to_whom),
                description=(
                    action.description
                    or f"{action.character_id} {action.action_type} → {action.target}"
                ),
                visible_to=visible_to,
                narrative_value=0,  # Narrator 自己评估精确值
                narrative_value_hint=nv_hint,  # 启发式提示, 防止早期跳过
                consequences=[],
            )
            action_events.append(event)
        return action_events

    def _infer_visible_to(
        self, action: CharacterAction, state: CharacterState
    ) -> list[str]:
        """简化可见性推断: 同 location 角色 + dialogue_to_whom。Orchestrator 阶段 5 用。"""
        visible: set[str] = {action.character_id}
        # 同 location 的其他角色
        if state.current_location:
            for cid, agent_state in (
                (s.character_id, s)
                for s in self._tick_state.list_character_states()
            ):
                if agent_state.current_location == state.current_location:
                    visible.add(cid)
        visible.update(action.dialogue_to_whom)
        if action.target:
            visible.add(action.target)
        return sorted(visible)

    async def _narrate(self, tick: int, all_events: list[Event]) -> NarratorOutput:
        # 优先级长期记忆: 从 store 召回 top-5, 拼接为标注前缀的"摘要"行,
        # 与时间线 recent_chapter_summaries 合并后送 Narrator
        memory_summaries = self._build_long_term_memory_excerpts(tick, all_events)
        # v2.4 StoryArc directive: narrator_hint + theme_reminder + 节奏强度建议
        arc_hints = self._build_story_arc_hints()
        # v2.5 CharacterArcTracker: 漂移警告 + 阶段推进
        char_arc_hints = self._build_character_arc_hints()
        # v2.6 FactLedger: 事实冲突警告 (强制 Narrator 不要复述错误事实)
        fact_hints = self._build_fact_conflict_hints()
        # v2.8 CreativityScorer: 多样性退化警报 (词汇/结构/情感)
        creativity_hints = self._build_creativity_hints()
        merged_summaries = (
            fact_hints
            + creativity_hints
            + arc_hints
            + char_arc_hints
            + memory_summaries
            + list(self._recent_chapter_summaries)
        )
        return await self._narrator.narrate(
            tick=tick,
            world_time=self._tick_state.world_state.world_time,
            tracking_character_id=self._main_tracking_character_id or "",
            tick_events=all_events,
            char_states=self._tick_state.list_character_states(),
            recent_chapter_summaries=merged_summaries,
            open_loops=self._tick_state.get_open_loops(top_k=15),
            style_anchors=self._tick_state.get_style_anchors(top_k=5),
            last_narration_tick=self._tick_state.last_narration_tick,
        )

    def _build_creativity_hints(self) -> list[str]:
        """把 v2.8 CreativityScorer alerts 翻译为前缀提示行注入 Narrator。"""
        rep = self._last_creativity_report
        if rep is None or not rep.alerts:
            return []
        return [
            f"[创造力警报 {a.code} {a.severity}] {a.advice[:80]} "
            f"(drop {a.drop_pct:.0%})"
            for a in rep.alerts[:3]
        ]

    def _build_fact_conflict_hints(self) -> list[str]:
        """把 v2.6 FactLedger 最近一轮冲突翻译为前缀摘要行注入 Narrator。"""
        if not self._last_fact_conflicts:
            return []
        lines: list[str] = []
        for c in self._last_fact_conflicts[:3]:
            new = c.get("new_fact", {})
            reason = c.get("reason", "")
            severity = c.get("severity", "medium")
            lines.append(
                f"[事实冲突 {severity}] {new.get('subject', '?')}.{new.get('kind', '?')}: {reason[:80]}"
            )
        return lines

    def _build_character_arc_hints(self) -> list[str]:
        """把 CharacterArcTracker 最近一轮报告翻译为前缀摘要行注入 Narrator。"""
        out = self._last_arc_tracker_output
        if out is None or not out.reports:
            return []
        lines: list[str] = []
        if out.summary and out.summary != "全员稳定":
            lines.append(f"[人物弧光] {out.summary[:120]}")
        for rep in out.reports:
            if rep.drift_codes:
                lines.append(
                    f"[漂移警告 {rep.character_id}] "
                    f"{','.join(rep.drift_codes)} — {rep.rationale[:60]}"
                )
            elif rep.is_stalled and rep.suggested_stage:
                lines.append(
                    f"[阶段推进 {rep.character_id}] "
                    f"{rep.current_stage} → {rep.suggested_stage}"
                )
        return lines[:5]  # 上限 5 行防 prompt 膨胀

    def _build_story_arc_hints(self) -> list[str]:
        """把 StoryArcDirector 的 directive 翻译为 Narrator 可消费的"前缀摘要行"。"""
        d = self._last_story_directive
        if d is None:
            return []
        lines: list[str] = []
        if d.theme_reminder:
            lines.append(f"[叙事大纲] {d.theme_reminder[:120]}")
        if d.narrator_hint:
            lines.append(f"[本段提示] {d.narrator_hint[:80]}")
        if d.intensity_recommendation:
            lines.append(
                f"[节奏建议] 期望强度={d.intensity_recommendation} "
                f"(escalation={d.needs_escalation}, breather={d.needs_breather})"
            )
        if d.overdue_beats:
            lines.append(
                f"[逾期节拍] {', '.join(d.overdue_beats[:3])} — 推进或显式标记跳过"
            )
        return lines

    def _build_long_term_memory_excerpts(
        self, tick: int, all_events: list[Event]
    ) -> list[str]:
        """从 PriorityMemoryStore 取 top-5 高优先级历史条目, 注入 Narrator 上下文。

        提供给 Narrator 的优势:
        * 不仅看时间线邻近 (recent_chapter_summaries), 还看跨章节高优先级条目
        * 保护条目 (open_loop / trauma / 高引用) 享受 score 加成, 不会"被遗忘"
        * 多因子 dedup, 避免相似事件挤占 prompt 空间
        """
        if self._memory_store.size == 0:
            return []
        # 提取本 tick 出场角色作为查询信号
        query_chars: set[str] = set()
        for evt in all_events:
            query_chars.update(evt.participants)
        results = self._memory_store.retrieve(
            RetrievalQuery(
                current_tick=tick,
                query_chars=sorted(query_chars),
                top_k=5,
                min_l0_or_l1=2,
            )
        )
        return [
            f"[长期记忆 tier={r.record.entry.tier} importance={r.record.entry.importance}] "
            f"{r.record.entry.summary[:120]}"
            for r in results
        ]

    async def _phase7_periodic_maintenance(
        self, tick: int, agents_called: list[str]
    ) -> None:
        """周期性维护,Showrunner 已在阶段 2 调度。"""
        if (
            self._novelty_critic is not None
            and tick % NOVELTY_CRITIC_CADENCE == 0
        ):
            try:
                action_patterns = (
                    self._tick_db.get_action_patterns(last_n_ticks=100)
                    if self._tick_db is not None
                    else {}
                )
                critic_out = await self._novelty_critic.critique(
                    recent_chapters=self._recent_chapter_summaries[-30:],
                    recent_events=self._last_tick_events[-50:],
                    action_patterns=action_patterns,
                )
                warnings = list(getattr(critic_out, "recommendations", [])) or []
                self._tick_state.set_novelty_warnings(warnings)
                agents_called.append("novelty_critic")
            except Exception as e:
                logger.error("NoveltyCritic.critique failed: %s", e)

        if (
            self._consistency_guardian is not None
            and tick % CONSISTENCY_GUARDIAN_CADENCE == 0
        ):
            try:
                await self._consistency_guardian.scan(
                    world_state=self._tick_state.world_state,
                    char_states=self._tick_state.list_character_states(),
                    recent_events=self._last_tick_events,
                    recent_chapter_text=self._recent_chapter_summaries[-10:],
                )
                agents_called.append("consistency_guardian")
            except Exception as e:
                logger.error("ConsistencyGuardian.scan failed: %s", e)

        if (
            self._character_arc_tracker is not None
            and tick % CHARACTER_ARC_TRACKER_CADENCE == 0
        ):
            try:
                profiles = {
                    cid: a.profile for cid, a in self._character_agents.items()
                }
                states = {
                    s.character_id: s
                    for s in self._tick_state.list_character_states()
                }
                tracker_out = await self._character_arc_tracker.evaluate(
                    profiles=profiles,
                    states=states,
                    recent_actions_by_char=self._recent_actions_by_char,
                    current_tick=tick,
                )
                self._last_arc_tracker_output = tracker_out
                # 自动推进 suggested_stage (确定性推进, LLM 建议不自动应用)
                for rep in tracker_out.reports:
                    if rep.suggested_stage and rep.is_stalled:
                        state = self._tick_state.get_character_state(rep.character_id)
                        if state is not None:
                            self._tick_state.upsert_character_state(
                                state.model_copy(
                                    update={
                                        "arc_stage": rep.suggested_stage,
                                        "arc_stage_entered_tick": tick,
                                    }
                                )
                            )
                agents_called.append("character_arc_tracker")
            except Exception as e:
                logger.error("CharacterArcTracker.evaluate failed: %s", e)

        if (
            self._memory_compressor is not None
            and tick % MEMORY_COMPRESSOR_CADENCE == 0
        ):
            try:
                # 从 PriorityMemoryStore 抽出真实 MemoryEntry 池 + open_loop 源 id
                all_entries = [r.entry for r in self._memory_store.all_records()]
                # OpenLoop 关联的所有事件 id 作为保护清单
                protected_ids: list[str] = []
                for loop in self._tick_state.get_open_loops():
                    protected_ids.extend(getattr(loop, "origin_event_ids", None) or [])
                comp_out = await self._memory_compressor.compress(
                    current_tick=tick,
                    memory_entries=all_entries,
                    open_loop_origin_ids=protected_ids,
                )
                # 把压缩输出反写回 store: L0→L1 替换, L1→L2 替换
                for new_l1 in getattr(comp_out, "l0_to_l1", []) or []:
                    self._memory_store.replace_with_compressed(
                        source_ids=[],  # MemoryCompressor 不返回原 ids, 替换粒度暂时不细化
                        new_entry=new_l1,
                        current_tick=tick,
                    )
                for new_l2 in getattr(comp_out, "l1_to_l2", []) or []:
                    self._memory_store.replace_with_compressed(
                        source_ids=[],
                        new_entry=new_l2,
                        current_tick=tick,
                    )
                agents_called.append("memory_compressor")
            except Exception as e:
                logger.error("MemoryCompressor.compress failed: %s", e)

    # ------------------------------------------------------------------
    # 输出辅助
    # ------------------------------------------------------------------

    def _compose_state_changes(
        self,
        actions: list[CharacterAction],
        narrator_out: NarratorOutput,
    ) -> str:
        n_actions = len(actions)
        loop_delta = len(narrator_out.newly_opened_loops)
        narr = "produced" if narrator_out.should_narrate else "skipped"
        return (
            f"actions={n_actions}, narrator={narr}, "
            f"new_loops=+{loop_delta}, open_loops={self._tick_state.get_open_loop_count()}"
        )

    def _next_tick_hints(self, tick: int) -> list[str]:
        hints: list[str] = []
        if (tick + 1) % SHOWRUNNER_CADENCE == 0 and self._showrunner is not None:
            hints.append("Showrunner due next tick")
        if (
            self._event_injector is not None
            and self._tick_state.ticks_since_last_event("exogenous", tick) >= EXOGENOUS_COOLDOWN_TICKS - 1
        ):
            hints.append("Exogenous event injection becoming likely")
        if self._tick_state.get_open_loop_count() < MIN_OPEN_LOOPS:
            hints.append("Open loop pool below minimum, injector should refill")
        # arc 完成度 >0.85 提示
        for cid, prog in self._tick_state.get_arc_status().items():
            if prog >= 0.85:
                hints.append(f"Character {cid} arc ripe for resolution (progress {prog:.0%})")
        return hints

    async def _default_narrative_writer(self, tick: int, text: str) -> None:
        narratives_dir = os.path.join(self._tick_state.data_dir, "narratives")
        os.makedirs(narratives_dir, exist_ok=True)
        path = os.path.join(narratives_dir, f"tick_{tick:06d}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(
            "Narrative for tick %d written: %d chars → %s",
            tick,
            len(text),
            path,
        )
