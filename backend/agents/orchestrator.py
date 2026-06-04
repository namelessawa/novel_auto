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
from nf_core.llm_client import set_current_tick
from nf_core.token_budget import TokenBudgetTracker, get_global_tracker, set_global_tracker
from dataclasses import dataclass, field as dc_field

from memory_system.models import (
    CharacterAction,
    CharacterState,
    Event,
    MemoryEntry,
    Relationship,
    StateOp,
    StatePatch,
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


@dataclass
class PatchDiagnostic:
    """_apply_state_patches 的诊断输出, 供 TickSummary 累积。"""

    applied: int = 0
    rejected: int = 0
    flags: list[str] = dc_field(default_factory=list)


class _OpRejected(Exception):
    """单 op 应用失败时抛出, 由 _apply_patch_to_* 捕获并记录到 diag.flags。"""


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
        # v2.12 — 把角色名 + 地点名作为 A1 豁免清单注入 narrator critic
        try:
            exempt_words = [
                p.name for p in tick_state.list_character_profiles() if p.name
            ] + [
                loc.name for loc in tick_state.world_state.locations if loc.name
            ]
            if hasattr(narrator, "set_exempt_words"):
                narrator.set_exempt_words(exempt_words)
        except Exception as e:  # pragma: no cover
            logger.debug("set_exempt_words failed (non-fatal): %s", e)

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

        # 并发保护 — 同一 Orchestrator 同一时刻只能有一个 tick 在跑。
        # 两个 HTTP 请求同时 /api/tick/run、或 start_loop 与手动 /run 并发时,
        # 这把锁保证 tick_state / tick_db 不会被双写。
        self._tick_lock: asyncio.Lock = asyncio.Lock()

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
        """执行单 tick 全 7 阶段。返回 TickSummary 供 TickDB / SSE 消费。

        v2.15 — 用 ``_tick_lock`` 串行化,防止并发 tick 双写 tick_state / tick_db。
        外部并发调用会自动排队,锁内只允许一个 tick 推进。
        """
        async with self._tick_lock:
            return await self._run_tick_unlocked()

    async def _run_tick_unlocked(self) -> TickSummary:
        """run_tick 原始实现 — 不加锁版本, 仅供 run_tick 与测试直接调用。"""
        tick = self._tick_state.advance_tick()
        # v2.16 Observability — 把当前 tick 注入 ContextVar, 让所有 LLM 调用
        # (CharacterAgent / NarratorAgent / WorldSimulator / ...) 自动归账到本 tick。
        # 同时通知 TokenBudgetTracker 开始新 tick 窗口, 让 per-tick 上限准确。
        set_current_tick(tick)
        self._token_budget.begin_tick(tick)
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
        # v2.18 Phase 8 — EventInjector 可携带 StatePatch 立即生效, 阶段 5d 应用
        injector_state_patches: list[StatePatch] = []
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
                # v2.18 Phase 8 — 同步收集 state_patches (阶段 5d 应用)
                if hasattr(injector_out, "state_patches"):
                    injector_state_patches = list(injector_out.state_patches or [])
                events_generated_ids.extend(e.id for e in injected_events)
                agents_called.append("event_injector")
                if injected_events:
                    self._tick_state.record_last_event_tick("exogenous", tick)
            except Exception as e:
                logger.error("EventInjector.inject failed: %s", e)

        # 外部手动注入
        # v2.22 — 不立即 clear。此前 .clear() 之后任何阶段 (3-7) 抛错都会让
        # 用户注入的事件永久丢失, 无法重试。改为快照 id 集合, tick 完整跑完
        # (持久化完成、TickSummary 已构造) 后再从队列里把它们移除。
        externally_injected = list(self._injected_pending)
        injected_event_ids = {e.id for e in externally_injected}
        events_generated_ids.extend(e.id for e in externally_injected)

        all_events: list[Event] = (
            list(natural_events) + injected_events + externally_injected
        )

        # 阶段 3: 角色决策 ------------------------------------------------
        affected_ids = self._collect_affected_characters(all_events)
        actions: list[CharacterAction] = []
        if affected_ids:
            # v2.18 — 跳过仍在 cooldown 窗口内的 agent (连续 LLM 失败超阈值时
            # 自动减压, 避免反复浪费 token 撞同一个错误)。
            runnable_ids = [
                cid
                for cid in affected_ids
                if not self._tick_state.is_agent_in_cooldown(
                    f"character_agent:{cid}", tick
                )
            ]
            agents_to_run = [
                self._character_agents[cid]
                for cid in runnable_ids
                if cid in self._character_agents
            ]
            states_map = {
                cid: st
                for cid, st in (
                    (cid, self._tick_state.get_character_state(cid))
                    for cid in runnable_ids
                )
                if st is not None
            }
            if agents_to_run:
                # v2.18 Phase 6 — 从 AgentRuntimeState 读模型降级标记
                model_overrides = self._collect_model_overrides(
                    [a.character_id for a in agents_to_run], tick=tick
                )
                actions = await CharacterAgent.batch_decide(
                    agents_to_run,
                    states_map,
                    all_events,
                    model_overrides=model_overrides,
                )
                # 记录 invocation: action 含 "(LLM 不可用,维持现状)" 描述 →
                # fallback path, 视为失败; 否则视为成功。
                for act in actions:
                    is_fallback = (
                        act.action_type == "wait"
                        and "(LLM 不可用" in (act.description or "")
                    )
                    self._tick_state.record_agent_invocation(
                        f"character_agent:{act.character_id}",
                        tick=tick,
                        success=not is_fallback,
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

        # 阶段 5d: 应用 EventInjector 提交的 StatePatch (v2.18 Phase 8)
        # 顺序: 角色意志 (_apply_actions) → 外部权威 (state_patches), 后者覆盖前者
        # — 例如: 角色拿剑成功后, 紧接着被爆炸炸伤。
        if injector_state_patches:
            try:
                patch_diag = self._apply_state_patches(
                    tick=tick, patches=injector_state_patches
                )
                if patch_diag.applied or patch_diag.rejected:
                    agents_called.append(
                        f"state_patches(applied={patch_diag.applied},"
                        f"rejected={patch_diag.rejected})"
                    )
            except Exception as e:
                logger.warning(
                    "Phase 5d _apply_state_patches failed (non-fatal): %s", e
                )

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

        # 阶段 6 + 阶段 7-readonly 并行 -----------------------------------
        # v2.18 Phase 7 — 让 Narrator (写 narration 文件 / open_loops) 与只读类
        # 周期 agent (Guardian / Critic / ArcTracker) 同步执行。三者只读外部状态,
        # 各自只写不同字段, 互不冲突, 跟 Narrator 也无写冲突。
        # MemoryCompressor 写 memory_store, 仍串行放后面 (sequential_agents)。
        narrator_out, _readonly_result = await asyncio.gather(
            self._narrate(tick, all_events),
            self._phase7_readonly_agents(tick, agents_called),
            return_exceptions=False,
        )
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

        # 阶段 7: 串行维护 (MemoryCompressor 写 memory_store, 避免与 Narrator
        # 的 touch / mark_protected race) — readonly 部分已并行到阶段 6。
        await self._phase7_sequential_agents(tick, agents_called)

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

        # v2.22 — tick 已完整跑完 + 落盘, 现在才真正消费外部注入队列。
        # 用 id 集合做差, 避免漏掉本 tick 期间新追加的事件 (虽然有 _tick_lock,
        # inject_event 不在锁内, 理论上 HTTP 线程可在 tick 中途 append)。
        if injected_event_ids:
            self._injected_pending = [
                e for e in self._injected_pending
                if e.id not in injected_event_ids
            ]

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
        """阶段 5: 应用 CharacterAction 到 CharacterState 并生成 character_action Event。

        v2.16 — 硬状态转移:
        * ``new_location`` → 更新 current_location, 且仅当目标 location_id 在
          WorldState.locations 中存在时才接受 (否则忽略并打 flag)
        * ``inventory_added`` / ``inventory_removed`` → 去重 / 移除, 失败静默
        * ``status_added`` / ``status_removed`` → 同上
        * ``relationship_deltas`` → 合并 trust (clamp [-10, 10]) / new_type /
          history_summary; 同时刷新 last_interaction_tick

        本次 tick 全部 action 应用完之后, 由 _sync_location_membership() 统一
        刷新 WorldState.locations[].present_characters, 而不是每 action 刷一次。
        """
        action_events: list[Event] = []
        valid_location_ids = {
            loc.id for loc in self._tick_state.world_state.locations
        }
        any_location_changed = False

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

            # 应用 emotional shift
            emotional = state.emotional_state
            if action.emotional_shift:
                emotional = action.emotional_shift

            # v2.16 — location
            new_location = state.current_location
            location_flag: str | None = None
            if action.new_location:
                if action.new_location in valid_location_ids:
                    if new_location != action.new_location:
                        any_location_changed = True
                    new_location = action.new_location
                else:
                    location_flag = f"unknown_location:{action.new_location}"

            # v2.16 — inventory
            new_inventory = [
                item for item in state.inventory if item not in action.inventory_removed
            ]
            for item in action.inventory_added:
                if item and item not in new_inventory:
                    new_inventory.append(item)

            # v2.16 — status effects
            new_status = [
                s for s in state.status_effects if s not in action.status_removed
            ]
            for s in action.status_added:
                if s and s not in new_status:
                    new_status.append(s)

            # v2.18 — money. clamp 到 [0, +inf); 若 LLM 让你"花"超过你有的,
            # 钱降到 0 并打 money_overdraft flag, 让 Guardian 后续监控。
            money_overdraft = False
            new_money = state.money + action.money_delta
            if new_money < 0:
                money_overdraft = True
                new_money = 0

            # v2.16 — relationships
            new_relationships = dict(state.relationships)
            for other_id, delta in action.relationship_deltas.items():
                if not other_id:
                    continue
                existing = new_relationships.get(other_id) or Relationship(
                    with_character_id=other_id
                )
                merged_trust = max(-10, min(10, existing.trust + delta.trust_delta))
                merged_type = delta.new_type or existing.type
                merged_history = existing.history_summary
                if delta.history_entry:
                    sep = " | " if merged_history else ""
                    merged_history = (merged_history + sep + delta.history_entry)[-240:]
                new_relationships[other_id] = Relationship(
                    with_character_id=other_id,
                    type=merged_type,
                    trust=merged_trust,
                    history_summary=merged_history,
                    last_interaction_tick=tick,
                )

            updated = state.model_copy(
                update={
                    "current_goals": new_goals,
                    "known_facts": facts,
                    "emotional_state": emotional,
                    "current_location": new_location,
                    "inventory": new_inventory,
                    "status_effects": new_status,
                    "relationships": new_relationships,
                    "money": new_money,
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
            if action.new_location and new_location == action.new_location:
                nv_hint += 1  # 角色真的发生了移动
            if "fight" in (action.action_type or "") or "attack" in (action.action_type or ""):
                nv_hint += 2
            nv_hint = min(nv_hint, 6)  # 上限, narrator 仍可自己评估更高

            # v2.18 — action_type 与硬字段一致性检查。
            # LLM 会偶尔在非交互类 action (wait / speak / investigate) 里随手填
            # inventory_added 或 new_location, 这通常是幻觉。打 flag 让 Guardian /
            # NoveltyCritic 可观测, 但不阻止应用 (毕竟 ActionResolver 已是仲裁层)。
            # 注意: status_added 在 wait/speak 下是合法的 (情绪/疲惫等被动状态),
            # 所以 status 不参与一致性检查。
            consistency_flags = self._consistency_flags(action)

            # 事件 location 用更新后的位置, 这样 narrator 看到的就是角色"现在"的位置
            event_location = new_location or state.current_location
            event = Event(
                id=f"evt_act_{tick}_{action.character_id}_{uuid.uuid4().hex[:6]}",
                tick=tick,
                type="character_action",
                location=event_location,
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
                consequences=(
                    ([location_flag] if location_flag else [])
                    + (["money_overdraft"] if money_overdraft else [])
                    + consistency_flags
                ),
            )
            action_events.append(event)

        if any_location_changed:
            self._sync_location_membership()
        return action_events

    # ------------------------------------------------------------------
    # v2.18 StatePatch 应用
    # ------------------------------------------------------------------

    def _apply_state_patches(
        self,
        tick: int,
        patches: list[StatePatch],
    ) -> "PatchDiagnostic":
        """阶段 5d: 应用 EventInjector / Guardian / Simulator 提交的外部权威补丁。

        与 _apply_actions 并列, 不替代; 顺序为 _apply_actions → _apply_state_patches,
        让外部权威可以"覆盖"角色意志 (例如爆炸炸伤拿剑成功的角色)。

        失败模式:
        * 未知 target_type → rejected
        * 未知 character_id / 不在 WorldState.locations 的 location → rejected
        * 单个 op 应用失败 (类型不匹配, append 到非 list 字段) → 仅该 op rejected,
          patch 内其他 op 仍然尝试

        返回 PatchDiagnostic 供 TickSummary 累积。
        """
        diag = PatchDiagnostic()
        for patch in patches:
            if patch.target_type == "character":
                self._apply_patch_to_character(patch, diag)
            elif patch.target_type == "world":
                self._apply_patch_to_world(patch, diag)
            else:
                # location / faction 暂不支持
                diag.rejected += 1
                diag.flags.append(f"unsupported_target_type:{patch.target_type}")
        return diag

    def _apply_patch_to_character(
        self, patch: StatePatch, diag: "PatchDiagnostic"
    ) -> None:
        state = self._tick_state.get_character_state(patch.target_id)
        if state is None:
            diag.rejected += 1
            diag.flags.append(f"unknown_character:{patch.target_id}")
            return
        valid_location_ids = {
            loc.id for loc in self._tick_state.world_state.locations
        }
        updated_dict = state.model_dump()
        applied_any = False
        for op in patch.ops:
            try:
                self._apply_op_to_dict(
                    updated_dict, op, diag, valid_location_ids=valid_location_ids
                )
                applied_any = True
            except _OpRejected as e:
                diag.flags.append(str(e))
        # money 强制 clamp ≥0 + overdraft flag
        if updated_dict.get("money", 0) < 0:
            updated_dict["money"] = 0
            if "money_overdraft" not in diag.flags:
                diag.flags.append("money_overdraft")
        if applied_any:
            try:
                new_state = CharacterState.model_validate(updated_dict)
            except Exception as e:
                diag.rejected += 1
                diag.flags.append(f"validation_failed:{patch.target_id}:{e}")
                return
            self._tick_state.upsert_character_state(new_state)
            diag.applied += 1
        else:
            diag.rejected += 1

    def _apply_patch_to_world(
        self, patch: StatePatch, diag: "PatchDiagnostic"
    ) -> None:
        ws = self._tick_state.world_state
        updated_dict = ws.model_dump()
        applied_any = False
        for op in patch.ops:
            try:
                self._apply_op_to_dict(updated_dict, op, diag)
                applied_any = True
            except _OpRejected as e:
                diag.flags.append(str(e))
        if applied_any:
            try:
                new_ws = WorldState.model_validate(updated_dict)
            except Exception as e:
                diag.rejected += 1
                diag.flags.append(f"validation_failed:world:{e}")
                return
            self._tick_state.set_world_state(new_ws)
            diag.applied += 1
        else:
            diag.rejected += 1

    @staticmethod
    def _apply_op_to_dict(
        target: dict,
        op: StateOp,
        diag: "PatchDiagnostic",
        valid_location_ids: set[str] | None = None,
    ) -> None:
        """就地修改 target dict 的 op.field; 失败抛 _OpRejected。"""
        if op.field not in target:
            raise _OpRejected(f"unknown_field:{op.field}")
        # location 字段做有效性校验
        if op.field == "current_location" and op.op == "set":
            if valid_location_ids is None or op.value not in valid_location_ids:
                raise _OpRejected(f"unknown_location:{op.value}")
            target[op.field] = op.value
            return
        if op.op == "set":
            target[op.field] = op.value
        elif op.op == "add":
            cur = target.get(op.field, 0)
            if not isinstance(cur, (int, float)) or not isinstance(op.value, (int, float)):
                raise _OpRejected(f"add_type_mismatch:{op.field}")
            target[op.field] = cur + op.value
        elif op.op == "append":
            cur = target.get(op.field)
            if not isinstance(cur, list):
                raise _OpRejected(f"append_non_list:{op.field}")
            if op.value not in cur:
                cur.append(op.value)
        elif op.op == "remove":
            cur = target.get(op.field)
            if not isinstance(cur, list):
                raise _OpRejected(f"remove_non_list:{op.field}")
            if op.value in cur:
                cur.remove(op.value)
        else:  # pragma: no cover — Literal 限定
            raise _OpRejected(f"unknown_op:{op.op}")

    # ------------------------------------------------------------------
    # v2.18 Phase 6 — model_tier_override 读出
    # ------------------------------------------------------------------

    def _collect_model_overrides(
        self, character_ids: list[str], tick: int
    ) -> dict[str, str]:
        """从 TickState.agent_runtime_states 读 model_tier_override, 按 cid 返回。

        仅返回非空 override; 调用方 (batch_decide) 对缺失 cid 视为不降级。
        本方法不写状态 — 单纯只读, 供阶段 3 在并发 batch_decide 前一次性收集。
        """
        out: dict[str, str] = {}
        for cid in character_ids:
            rs = self._tick_state.get_agent_runtime_state(f"character_agent:{cid}")
            if rs is None:
                continue
            if rs.model_tier_override:
                out[cid] = rs.model_tier_override
        return out

    # ------------------------------------------------------------------
    # v2.18 Phase 5 — Guardian 幻觉 conflict 消费
    # ------------------------------------------------------------------

    def _ingest_guardian_conflicts(self, output, tick: int) -> int:
        """把 GuardianOutput 中的 hallucination_<id> conflict 写到 AgentRuntimeState。

        默认 shadow mode (无 ``HALLUCINATION_AUTO_DEGRADE``): 只累加统计,
        不改 model_tier_override。
        env flag 开启时: 同时写 ``model_tier_override='haiku'``。

        返回累计处理的 conflict 数, 供 TickSummary / 日志参考。

        典型调用点: ``_phase7_periodic_maintenance`` 在 Guardian.scan 后调用。
        但本方法独立可测, 不依赖整 tick 流程。
        """
        if output is None:
            return 0
        conflicts = getattr(output, "conflicts", None) or []
        auto_degrade = os.environ.get("HALLUCINATION_AUTO_DEGRADE", "").strip()
        override = "haiku" if auto_degrade in {"1", "true", "TRUE", "yes"} else None

        processed = 0
        for c in conflicts:
            cid = getattr(c, "id", "") or ""
            if not cid.startswith("hallucination_"):
                continue
            character_id = cid[len("hallucination_") :]
            if not character_id:
                continue
            hits = len(getattr(c, "evidence", None) or [])
            self._tick_state.record_degrade_recommendation(
                agent_id=f"character_agent:{character_id}",
                tick=tick,
                hits=hits,
                set_override=override,
            )
            processed += 1
        if processed:
            logger.info(
                "Guardian hallucination conflicts ingested at tick %d: %d "
                "(auto_degrade=%s)",
                tick,
                processed,
                bool(override),
            )
        return processed

    @staticmethod
    def _consistency_flags(action: CharacterAction) -> list[str]:
        """检测 action_type 与硬状态字段的不一致, 产出诊断 flag。

        当前规则 (保守, 仅 LLM 几乎肯定幻觉的组合才打 flag):
        * action_type ∈ {wait, speak, investigate, think, observe} 但 new_location
          非空 → ``location_without_move``
        * 同样的非交互动作但 inventory_added 非空 → ``inventory_without_action``
        * 同样的非交互动作但 money_delta != 0 → ``money_without_action``

        合法组合不打 flag (take/steal/buy/craft + inventory_added,
        move/flee/travel + new_location, buy/sell/pay/earn + money_delta, 等)。
        status_added 在被动场景下合法 (wait + 焦虑), 不参与一致性检查。
        """
        non_interactive = {"wait", "speak", "investigate", "think", "observe"}
        flags: list[str] = []
        atype = (action.action_type or "").lower()
        if atype in non_interactive:
            if action.new_location:
                flags.append("location_without_move")
            if action.inventory_added:
                flags.append("inventory_without_action")
            if action.money_delta != 0:
                flags.append("money_without_action")
        return flags

    def _sync_location_membership(self) -> None:
        """根据当前所有 CharacterState 的 current_location 重建
        WorldState.locations[].present_characters。

        每 tick 至多调用一次, 在 _apply_actions 末尾。避免每 action 重写一次
        WorldState (model_copy 不便宜)。仅在确有角色移动时执行。
        """
        ws = self._tick_state.world_state
        if not ws.locations:
            return
        membership: dict[str, list[str]] = {loc.id: [] for loc in ws.locations}
        for st in self._tick_state.list_character_states():
            if st.current_location and st.current_location in membership:
                membership[st.current_location].append(st.character_id)
        new_locations = [
            loc.model_copy(update={"present_characters": sorted(membership.get(loc.id, []))})
            for loc in ws.locations
        ]
        self._tick_state.set_world_state(
            ws.model_copy(update={"locations": new_locations})
        )

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
        """周期性维护协调入口:

        v2.18 Phase 7 — 拆成两段:
        1. 只读类 (Guardian/Critic/ArcTracker) 并行 — 可被 Narrator 同步触发并行
        2. MemoryCompressor 串行 — 因写 memory_store, 避免与 Narrator.touch 竞态

        当前实现把只读三件套与 MemoryCompressor 都放在 Narrator 之后串行调度,
        但 _phase7_readonly_agents 已是独立可调用方法; 调用方 (run_tick) 可选择
        与 _narrate 并行执行 (asyncio.gather)。Showrunner 在阶段 2 已调度。
        """
        await self._phase7_readonly_agents(tick, agents_called)
        await self._phase7_sequential_agents(tick, agents_called)

    async def _phase7_readonly_agents(
        self, tick: int, agents_called: list[str]
    ) -> None:
        """周期性维护的只读 LLM agent 子集 — 并发执行, 互不依赖。

        Guardian / NoveltyCritic / ArcTracker 三者都满足:
        * 只读 TickState 当前快照 (world_state / char_states / events)
        * 各自只写不同字段 (Guardian → AgentRuntimeState; Critic → novelty_warnings;
          ArcTracker → character_state.arc_stage), 互不写冲突
        * 跟 Narrator 也无写冲突 (Narrator 不改 character_states 主字段, 只 mark
          narration / open_loop)

        单个 agent 抛异常被 gather 吞掉, 不阻塞其他。Showrunner 在阶段 2 已调度,
        不在此处。
        """
        tasks: list = []
        if (
            self._novelty_critic is not None
            and tick % NOVELTY_CRITIC_CADENCE == 0
        ):
            tasks.append(self._run_novelty_critic(tick, agents_called))
        if (
            self._consistency_guardian is not None
            and tick % CONSISTENCY_GUARDIAN_CADENCE == 0
        ):
            tasks.append(self._run_consistency_guardian(tick, agents_called))
        if (
            self._character_arc_tracker is not None
            and tick % CHARACTER_ARC_TRACKER_CADENCE == 0
        ):
            tasks.append(self._run_character_arc_tracker(tick, agents_called))
        if tasks:
            # gather(return_exceptions=True) 让单 agent 失败不传播
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error("phase7 readonly agent failed: %s", r)

    async def _run_novelty_critic(
        self, tick: int, agents_called: list[str]
    ) -> None:
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

    async def _run_consistency_guardian(
        self, tick: int, agents_called: list[str]
    ) -> None:
        try:
            guardian_out = await self._consistency_guardian.scan(
                world_state=self._tick_state.world_state,
                char_states=self._tick_state.list_character_states(),
                recent_events=self._last_tick_events,
                recent_chapter_text=self._recent_chapter_summaries[-10:],
            )
            try:
                self._ingest_guardian_conflicts(guardian_out, tick=tick)
            except Exception as e:
                logger.warning(
                    "Guardian conflicts ingest failed (non-fatal): %s", e
                )
            agents_called.append("consistency_guardian")
        except Exception as e:
            logger.error("ConsistencyGuardian.scan failed: %s", e)

    async def _run_character_arc_tracker(
        self, tick: int, agents_called: list[str]
    ) -> None:
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

    async def _phase7_sequential_agents(
        self, tick: int, agents_called: list[str]
    ) -> None:
        """周期性维护的写 memory_store 类 — 串行避免 race。"""

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
                # v2.15 — 把压缩输出反写回 store: 用 MemoryEntry.source_ids 真正退役旧记录。
                # 此前 source_ids=[] 让 MemoryCompressor 形同空转 (旧 L0 永不删除),
                # 长跑时 store 单调膨胀。compressor 现在保证 source_ids 至少含整批 fallback。
                for new_l1 in getattr(comp_out, "l0_to_l1", []) or []:
                    self._memory_store.replace_with_compressed(
                        source_ids=list(new_l1.source_ids),
                        new_entry=new_l1,
                        current_tick=tick,
                    )
                for new_l2 in getattr(comp_out, "l1_to_l2", []) or []:
                    self._memory_store.replace_with_compressed(
                        source_ids=list(new_l2.source_ids),
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
        # v2.19.4 — 把同步 IO (mkdir + open + write) 卸到 worker 线程, 避免
        # 阻塞主 event loop。Narrator 写 1.5k-3k 字 narrative, 阻塞 5-50ms
        # 不仅吃 tick latency, 还会推迟 phase 7 并行只读 agent (Guardian /
        # Critic / ArcTracker) 的回调处理 — v2.18 Phase 7 的并发收益被打折。
        narratives_dir = os.path.join(self._tick_state.data_dir, "narratives")
        path = os.path.join(narratives_dir, f"tick_{tick:06d}.txt")

        def _sync_write() -> None:
            os.makedirs(narratives_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

        await asyncio.to_thread(_sync_write)
        logger.info(
            "Narrative for tick %d written: %d chars → %s",
            tick,
            len(text),
            path,
        )
