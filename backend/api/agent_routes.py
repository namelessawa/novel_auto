"""agent_routes — 暴露 9 Agent 注册表 + 每个 agent 的完整上下文(系统 prompt /
输入 / 输出 / 最近调用 tick)。供前端「Agent 上下文」视图消费。

注册表是静态描述(从各 agent 模块的 SYSTEM_PROMPT 常量动态加载),不依赖运行时
状态;最近调用 tick 来自 TickDB 扫描。
"""

from __future__ import annotations

import importlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# 注册表:9 个 v2 tick agent + 静态元数据
# ---------------------------------------------------------------------------


@dataclass
class AgentSpec:
    id: str
    cn_name: str
    role: str
    cadence: str
    llm_tier: str | None
    module: str
    prompt_attr: str | None  # 模块里的 SYSTEM_PROMPT 常量名;None 表示无 LLM
    prompt_extras: list[str] = field(default_factory=list)  # 多 prompt 的额外常量名
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)


AGENT_REGISTRY: dict[str, AgentSpec] = {
    "orchestrator": AgentSpec(
        id="orchestrator",
        cn_name="Orchestrator(调度器)",
        role="纯 Python 7 阶段调度。不修改任何 agent 返回内容,不替 Narrator 决定沉默,不替角色决定行动,不凭空创造事件。",
        cadence="每 tick",
        llm_tier=None,
        module="agents.orchestrator",
        prompt_attr=None,
        inputs=[
            "TickState (世界/角色/伏笔)",
            "EventInjector 待注入队列",
            "调度周期 (Showrunner=5 / NoveltyCritic=20 / ConsistencyGuardian=30 / MemoryCompressor=50)",
        ],
        outputs=[
            "7 阶段顺序调用各 agent",
            "TickSummary (agents_called / events_generated / narrator_produced_text / state_changes_summary)",
            "持久化 TickState + TickDB",
        ],
    ),
    "world_simulator": AgentSpec(
        id="world_simulator",
        cn_name="WorldSimulator(世界模拟器)",
        role="虚构世界的物理与社会规则引擎。推进时间/天气/自然事件,不创造剧情。",
        cadence="每 tick",
        llm_tier="small",
        module="agents.world_simulator",
        prompt_attr="SYSTEM_PROMPT",
        inputs=[
            "WorldState (current_tick, world_time, weather, locations, factions)",
            "world_rules",
        ],
        outputs=[
            "time_advance(分钟/小时/天)",
            "weather_event (可选)",
            "natural_events: list[Event] (低 narrative_value 的环境事件)",
        ],
    ),
    "event_injector": AgentSpec(
        id="event_injector",
        cn_name="EventInjector(命运/事件注入器)",
        role="虚构世界的「命运」。注入 endogenous / exogenous / dramatic 三类事件,保持故事流动。OpenLoop <3 时强制触发。",
        cadence="3-5 tick",
        llm_tier="medium",
        module="agents.event_injector",
        prompt_attr="SYSTEM_PROMPT",
        inputs=[
            "最近 N tick 的事件流",
            "open_loops (按 urgency 排序)",
            "character_states (dormant_characters)",
            "Showrunner 的 dramatic 触发信号",
        ],
        outputs=[
            "events: list[Event] (每 tick 0-2 个)",
            "每个事件标记 type / narrative_value / participants / visible_to",
        ],
    ),
    "character_agent": AgentSpec(
        id="character_agent",
        cn_name="CharacterAgent×N(角色代理)",
        role="单角色决策代理。一个 profile 对应一个长期实例,严格按 known_facts + 可见事件决策。A=strong / B=medium / C 不实例化。",
        cadence="每 tick (batch_decide, Semaphore 并发=3)",
        llm_tier="A: strong / B: medium",
        module="agents.character_agent",
        prompt_attr="SYSTEM_PROMPT_TEMPLATE",
        inputs=[
            "CharacterProfile (恒定: 身份/性格/价值观/恐惧/欲望)",
            "CharacterState (current_tick: emotion / known_facts / goals / location)",
            "all_tick_events (会按 visible_to 过滤为可见子集)",
        ],
        outputs=[
            "CharacterAction (action_type / target / description / dialogue / intent)",
            "internal_monologue / emotional_shift",
            "completed_goal_ids / new_goals / abandoned_goal_ids",
            "newly_learned / newly_speculated / flags",
        ],
    ),
    "action_resolver": AgentSpec(
        id="action_resolver",
        cn_name="ActionResolver(行动冲突解析)",
        role="纯 Python 行动冲突解析。独占类(fight/take/claim/...) 按 (tier, goal_priority) 仲裁,无 LLM。",
        cadence="每 tick",
        llm_tier=None,
        module="nf_core.action_resolver",
        prompt_attr=None,
        inputs=[
            "list[CharacterAction] (当前 tick 全部角色决策)",
            "CharacterProfile.importance_tier (A>B>C)",
            "Goal.priority",
        ],
        outputs=[
            "已解析的 CharacterAction 子集",
            "ResolutionDiagnostic (冲突记录,谁让步,谁胜出)",
        ],
    ),
    "narrator_agent": AgentSpec(
        id="narrator_agent",
        cn_name="NarratorAgent(叙述者)",
        role="决定一片混乱数据里哪些值得讲述。沉默是合法选项(总价值<5 跳过)。前 100 tick 用最强模型建立风格基准。",
        cadence="每 tick(可主动沉默)",
        llm_tier="strongest → medium",
        module="agents.narrator_agent",
        prompt_attr="NARRATOR_SYSTEM_PROMPT",
        inputs=[
            "events_this_tick + 每个的 narrative_value",
            "character_states (跟随主跟踪角色视角)",
            "style_anchors (语言风格保持)",
            "open_loops (本章可呼应的伏笔)",
            "last_narration_tick (距上次叙述超 10 tick 触发时间流逝段)",
        ],
        outputs=[
            "narrative_text (中文小说文本) 或 跳过",
            "estimated_length (short/medium/long)",
            "viewpoint_characters / scene_focus / events_consumed",
            "newly_opened_loops (每次 ≤1)",
            "consistency_flags (发现矛盾不修正,在此标记)",
        ],
    ),
    "showrunner": AgentSpec(
        id="showrunner",
        cn_name="Showrunner(节奏总监)",
        role="不写一个字,但决定故事的呼吸。监控节奏曲线/冷线索/弧线进度,触发 EventInjector。",
        cadence="每 5 tick",
        llm_tier="medium",
        module="agents.showrunner",
        prompt_attr="SYSTEM_PROMPT",
        inputs=[
            "最近 N tick 的事件分布与叙述率",
            "open_loops (年龄 + urgency)",
            "arc_status (起承转合阶段)",
            "novelty_warnings",
        ],
        outputs=[
            "next_tick_recommendations (建议给 Orchestrator)",
            "需要 EventInjector 注入 dramatic 的信号",
            "OpenLoop 紧急度调整",
        ],
    ),
    "memory_compressor": AgentSpec(
        id="memory_compressor",
        cn_name="MemoryCompressor(记忆压缩)",
        role="L0→L1→L2→L3 分层压缩。L3 通过 legendize 传说化失真。保护 OpenLoop 源头与创伤事件不被遗忘。",
        cadence="每 50 tick",
        llm_tier="small",
        module="agents.memory_compressor",
        prompt_attr="SYSTEM_PROMPT_L0_L1",
        prompt_extras=["SYSTEM_PROMPT_L1_L2"],
        inputs=[
            "SummaryTree (L0=逐事件 / L1=场景摘要 / L2=章节摘要 / L3=传说)",
            "OpenLoop.opened_tick (源头标记)",
            "Event.traumatic 标记",
        ],
        outputs=[
            "更新 SummaryTree (节点合并/legendize)",
            "保护标记: 关键事件不被压缩掉",
        ],
    ),
    "consistency_guardian": AgentSpec(
        id="consistency_guardian",
        cn_name="ConsistencyGuardian(连贯性卫士)",
        role="包装 evaluation/continuity_v2.EnhancedContinuityEvaluator。5 类矛盾扫描(character/time/setting/relationship/item),优先级 A-D。",
        cadence="每 30 tick",
        llm_tier="continuity_v2 (启发式 + 嵌入)",
        module="agents.consistency_guardian",
        prompt_attr=None,
        inputs=[
            "最近 N tick 的 narrative_text",
            "KnowledgeGraph (实体/关系状态)",
            "CharacterState 历史快照",
        ],
        outputs=[
            "矛盾报告 list (按 priority A/B/C/D)",
            "建议修正动作(交给 Narrator 在后续 consistency_flags 处理)",
        ],
    ),
    "novelty_critic": AgentSpec(
        id="novelty_critic",
        cn_name="NoveltyCritic(新颖性批评)",
        role="监控故事的新颖性。运行越久重复模式越易出现,生成 warnings 反馈给 Narrator。",
        cadence="每 20 tick",
        llm_tier="small",
        module="agents.novelty_critic",
        prompt_attr="SYSTEM_PROMPT",
        inputs=[
            "最近 N tick 的 narrative_text",
            "action_patterns (CharacterAction 频次统计)",
            "rhetoric / structural patterns",
        ],
        outputs=[
            "novelty_warnings (反馈给 NarratorAgent)",
            "重复程度评分",
        ],
    ),
}


# ---------------------------------------------------------------------------
# 加载 agent 模块的 SYSTEM_PROMPT 常量
# ---------------------------------------------------------------------------


def _safe_import(module_path: str) -> Any | None:
    try:
        return importlib.import_module(module_path)
    except Exception as e:
        logger.warning("agent module load failed: %s — %s", module_path, e)
        return None


def _get_prompt(spec: AgentSpec) -> dict | None:
    """返回 {'primary': str, 'extras': {name: str, ...}} 或 None。"""
    if spec.prompt_attr is None:
        return None
    mod = _safe_import(spec.module)
    if mod is None:
        return None
    primary = getattr(mod, spec.prompt_attr, None)
    if not isinstance(primary, str):
        return None
    extras: dict[str, str] = {}
    for extra_name in spec.prompt_extras:
        v = getattr(mod, extra_name, None)
        if isinstance(v, str):
            extras[extra_name] = v
    return {"primary": primary, "extras": extras}


def _module_file(spec: AgentSpec) -> str | None:
    mod = _safe_import(spec.module)
    if mod is None or not hasattr(mod, "__file__") or mod.__file__ is None:
        return None
    # 转成项目相对路径
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    try:
        return os.path.relpath(mod.__file__, project_root).replace(os.sep, "/")
    except ValueError:
        return mod.__file__


# ---------------------------------------------------------------------------
# 最近调用 tick 扫描 — 依赖 tick_routes 的 TickDB 容器
# ---------------------------------------------------------------------------


_AGENT_NAME_ALIASES = {
    "orchestrator": ["orchestrator", "Orchestrator"],
    "world_simulator": ["world_simulator", "WorldSimulator"],
    "event_injector": ["event_injector", "EventInjector"],
    "character_agent": ["character_agent", "CharacterAgent"],
    "action_resolver": ["action_resolver", "ActionResolver"],
    "narrator_agent": ["narrator_agent", "NarratorAgent", "narrator"],
    "showrunner": ["showrunner", "Showrunner"],
    "memory_compressor": ["memory_compressor", "MemoryCompressor"],
    "consistency_guardian": ["consistency_guardian", "ConsistencyGuardian"],
    "novelty_critic": ["novelty_critic", "NoveltyCritic"],
}


def _scan_last_invoked(agent_id: str, last_n: int = 200) -> dict | None:
    """从 TickDB 历史里找最近一次该 agent 被调用的 tick。"""
    try:
        from api.tick_routes import _container as tick_container
    except Exception:
        return None
    db = getattr(tick_container, "tick_db", None)
    if db is None:
        return None
    try:
        rows = db.get_recent_ticks(n=last_n)
    except Exception:
        return None
    aliases = set(_AGENT_NAME_ALIASES.get(agent_id, [agent_id]))
    for row in rows:  # 已按 tick 倒序
        called = row.get("agents_called") or []
        if isinstance(called, list) and any(c in aliases for c in called):
            return {
                "tick": row.get("tick"),
                "world_time": row.get("world_time"),
                "summary": row.get("state_changes_summary", ""),
                "narrator_produced": row.get("narrator_produced_text", False),
            }
    return None


def _dump_pydantic(obj: Any) -> Any:
    """Pydantic v2 / dataclass / dict 兼容 dump。"""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:
            return obj.model_dump()
    if isinstance(obj, list):
        return [_dump_pydantic(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _dump_pydantic(v) for k, v in obj.items()}
    return obj


def _build_live_context(spec: AgentSpec) -> dict:
    """对每个 agent 返回它在下一个 tick 会实际看到的数据切片。

    不存在 / 不可达时统一返回 {available: False, reason}。
    """
    try:
        from api.tick_routes import _container as tc
    except Exception:
        logger.warning("tick_routes 不可用", exc_info=True)
        return {"available": False, "reason": "tick_routes 模块加载失败"}
    ts = getattr(tc, "tick_state", None)
    db = getattr(tc, "tick_db", None)
    orch = getattr(tc, "orchestrator", None)
    if ts is None:
        return {
            "available": False,
            "reason": "TickState 未初始化(后端尚未引导 tick runtime)",
        }

    def _recent_ticks(n: int) -> list[dict]:
        if db is None:
            return []
        try:
            return db.get_recent_ticks(n=n)
        except Exception:
            return []

    def _injected_pending() -> int:
        if orch is None:
            return 0
        pending = getattr(orch, "_injected_pending", None)
        if isinstance(pending, list):
            return len(pending)
        return 0

    aid = spec.id
    ctx: dict[str, Any] = {"available": True, "tick_when_sampled": ts.current_tick}

    if aid == "orchestrator":
        ctx.update({
            "current_tick": ts.current_tick,
            "world_time": ts.world_time,
            "is_paused": bool(getattr(orch, "is_paused", False)) if orch else None,
            "character_count": len(ts.list_character_states()),
            "open_loop_count": ts.get_open_loop_count(),
            "style_anchor_count": len(ts.list_style_anchors()),
            "injected_pending_count": _injected_pending(),
            "last_5_tick_summaries": _recent_ticks(5),
        })

    elif aid == "world_simulator":
        ctx.update({
            "world_state": _dump_pydantic(ts.world_state),
        })

    elif aid == "event_injector":
        ctx.update({
            "open_loops_top_10": [
                _dump_pydantic(l) for l in ts.get_open_loops(top_k=10)
            ],
            "open_loop_count": ts.get_open_loop_count(),
            "last_event_tick_by_type": dict(
                getattr(ts, "_last_event_tick_by_type", {})
            ),
            "recent_events_3_ticks": [
                {"tick": r.get("tick"), "events": r.get("events_generated", [])}
                for r in _recent_ticks(3)
            ],
            "dormant_characters_count": sum(
                1
                for p in ts.list_character_profiles()
                if getattr(p, "importance_tier", "C") in {"A", "B"}
            ),
        })

    elif aid == "character_agent":
        # 每个 A/B 级角色的 profile + state
        ab_profiles = ts.list_character_profiles(tiers=["A", "B"])
        per_char = []
        for p in ab_profiles[:6]:  # 前 6 个,避免 payload 爆炸
            state = ts.get_character_state(p.id)
            per_char.append({
                "character_id": p.id,
                "profile": _dump_pydantic(p),
                "state": _dump_pydantic(state),
            })
        ctx.update({
            "total_ab_characters": len(ab_profiles),
            "characters_preview": per_char,
            "concurrency_limit": int(
                os.environ.get("CHARACTER_AGENT_CONCURRENCY", "3").strip() or 3
            ),
        })

    elif aid == "action_resolver":
        ctx.update({
            "note": "无持久化输入。每 tick 从 CharacterAgent 收到 list[CharacterAction] 后立即仲裁。",
            "tier_priority": "A > B > C",
            "exclusive_action_types": ["fight", "take", "claim", "occupy"],
            "last_resolved_tick_summary": (_recent_ticks(1) or [None])[0],
        })

    elif aid == "narrator_agent":
        ctx.update({
            "character_states": [
                _dump_pydantic(s) for s in ts.list_character_states()[:8]
            ],
            "style_anchors_top_5": [
                _dump_pydantic(a) for a in ts.get_style_anchors(top_k=5)
            ],
            "open_loops_top_10": [
                _dump_pydantic(l) for l in ts.get_open_loops(top_k=10)
            ],
            "last_narration_tick": ts.last_narration_tick,
            "ticks_since_last_narration": (
                ts.current_tick - ts.last_narration_tick
                if ts.last_narration_tick
                else None
            ),
            "novelty_warnings": list(ts.get_novelty_warnings()),
            "events_last_tick": [
                {"tick": r.get("tick"), "events": r.get("events_generated", [])}
                for r in _recent_ticks(1)
            ],
        })

    elif aid == "showrunner":
        try:
            arc_status = ts.get_arc_status()
        except Exception:
            arc_status = {}
        ctx.update({
            "tick_history_20": _recent_ticks(20),
            "open_loops_with_age": [
                {
                    **_dump_pydantic(l),
                    "age": ts.current_tick - l.opened_tick,
                }
                for l in ts.get_open_loops(top_k=15)
            ],
            "arc_status": arc_status,
            "novelty_warnings": list(ts.get_novelty_warnings()),
        })

    elif aid == "memory_compressor":
        # SummaryTree 来自磁盘,从 data_dir 推断
        summary_path = os.path.join(ts.data_dir, "summary_tree.json")
        node_counts = None
        if os.path.isfile(summary_path):
            try:
                with open(summary_path, encoding="utf-8") as f:
                    tree = json.load(f)
                if isinstance(tree, dict):
                    node_counts = {
                        k: len(v) if isinstance(v, list) else None
                        for k, v in tree.items()
                    }
            except Exception:
                pass
        ctx.update({
            "summary_tree_path": os.path.relpath(
                summary_path,
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
            ).replace(os.sep, "/"),
            "node_counts_by_level": node_counts,
            "protected_open_loop_count": ts.get_open_loop_count(),
            "data_dir": ts.data_dir,
        })

    elif aid == "consistency_guardian":
        ctx.update({
            "recent_narrator_ticks": [
                r
                for r in _recent_ticks(10)
                if r.get("narrator_produced_text")
            ],
            "world_state": _dump_pydantic(ts.world_state),
            "character_count": len(ts.list_character_states()),
            "cadence": "每 30 tick 全量扫描;无 LLM,启发式 + 嵌入相似度",
        })

    elif aid == "novelty_critic":
        action_patterns: dict = {}
        if db is not None:
            try:
                action_patterns = db.get_action_patterns(last_n_ticks=100)
            except Exception:
                pass
        ctx.update({
            "recent_narrator_ticks": [
                r
                for r in _recent_ticks(20)
                if r.get("narrator_produced_text")
            ],
            "action_patterns_last_100": action_patterns,
            "current_novelty_warnings": list(ts.get_novelty_warnings()),
        })

    else:
        ctx["note"] = "未配置的 agent,默认只展示通用 TickState 元信息"

    return ctx


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


def _spec_to_brief(spec: AgentSpec) -> dict:
    return {
        "id": spec.id,
        "cn_name": spec.cn_name,
        "role": spec.role,
        "cadence": spec.cadence,
        "llm_tier": spec.llm_tier,
        "module_path": _module_file(spec),
        "has_prompt": spec.prompt_attr is not None,
    }


def _spec_to_detail(spec: AgentSpec) -> dict:
    prompt_block = _get_prompt(spec)
    last_invoked = _scan_last_invoked(spec.id)
    live_context = _build_live_context(spec)
    return {
        **_spec_to_brief(spec),
        "inputs": spec.inputs,
        "outputs": spec.outputs,
        "prompt": prompt_block,
        "last_invoked": last_invoked,
        "live_context": live_context,
    }


@router.get("")
async def list_agents() -> dict:
    return {
        "count": len(AGENT_REGISTRY),
        "agents": [_spec_to_brief(s) for s in AGENT_REGISTRY.values()],
    }


@router.get("/{agent_id}")
async def get_agent_detail(agent_id: str) -> dict:
    spec = AGENT_REGISTRY.get(agent_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"unknown agent: {agent_id}")
    return _spec_to_detail(spec)
