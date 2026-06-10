"""ConsistencyGuardian — 一致性守护者 (prompts.md 第 10 节)。

复用主项目 ``evaluation/continuity_v2.py`` 的 ``EnhancedContinuityEvaluator`` 作为
LLM 调用核心,通过 ``ConsistencyGuardianAdapter`` 把 tick 架构的 WorldState /
CharacterState / Event[] 序列化为 ``memory_context``,把 ContinuityScore.issues
映射为 GuardianOutput.conflicts。

扫描矛盾五类:
1. 角色矛盾(位置不一致 / 知道不该知道的事)
2. 时间矛盾(同时出现在两地、旅行时间被违反)
3. 设定矛盾(违反 WorldState.world_rules)
4. 关系矛盾(死者复生、关系突变无铺垫)
5. 物品矛盾(所有权冲突)

优先级 A 必须修正,B 通过新事件优雅化解,C 传说化处理,D 忽略。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from memory_system.models import CharacterState, ConflictPriority, Event, WorldState

logger = logging.getLogger(__name__)


@dataclass
class GuardianConflict:
    id: str
    type: str  # character|time|setting|relationship|item
    priority: ConflictPriority
    details: str
    evidence: list[str] = field(default_factory=list)
    resolution_method: str = ""
    resolution_specifics: str = ""


@dataclass
class GuardianOutput:
    scan_summary: str = ""
    conflicts: list[GuardianConflict] = field(default_factory=list)
    degraded: bool = False  # LLM 不可用 / 回退到启发式


class ConsistencyGuardianAdapter:
    """把 tick 契约转换为 EnhancedContinuityEvaluator 的输入。

    EnhancedContinuityEvaluator 接受 ``(previous_context, new_content, memory_context)``,
    我们的策略: 把 WorldState / CharacterState dump 成 **dict** 进 memory_context
    (evaluator 期望 dict, 按 'characters' / 'world_state' 键消费),
    把最近章节文本拼成 new_content,把最近事件拼成 previous_context。
    """

    @staticmethod
    def adapt_inputs(
        world_state: WorldState,
        char_states: list[CharacterState],
        recent_events: list[Event],
        recent_chapter_text: list[str],
    ) -> tuple[str, str, dict]:
        # previous_context: 最近事件 + 倒数第二章
        prev_events = "\n".join(
            f"- [{e.tick} | {e.type}] {e.description[:120]}"
            for e in recent_events[-30:]
        ) or "(无)"
        prev_chapter = recent_chapter_text[-2] if len(recent_chapter_text) >= 2 else "(无)"
        previous_context = (
            f"【最近事件】\n{prev_events}\n\n【上一章】\n{prev_chapter}"
        )

        # new_content: 最新一章
        new_content = recent_chapter_text[-1] if recent_chapter_text else ""

        # memory_context: world_state + char_states — 必须是 dict。
        # 此前误序列化成 JSON 字符串, evaluator 端 `'relationships' in str` 子串
        # 命中后 str['relationships'] 直接 TypeError, 扫描永远 degraded。
        # 键名对齐 evaluator 的 _build_evaluation_prompt: 'characters' / 'world_state'。
        ws_dump = world_state.model_dump(mode="json")
        cs_dump = [s.model_dump(mode="json") for s in char_states]
        memory_context = {
            "characters": cs_dump,
            "world_state": ws_dump,
        }
        return previous_context, new_content, memory_context

    @staticmethod
    def adapt_output(score: object) -> GuardianOutput:
        """把 ContinuityScore 转 GuardianOutput。

        ``score`` 是 ``evaluation.continuity_v2.ContinuityScore`` 对象(避免硬依赖
        import 失败时崩溃)。
        """
        issues = getattr(score, "issues", []) or []
        overall = getattr(score, "overall_score", 0.0)
        conflicts: list[GuardianConflict] = []
        for idx, issue in enumerate(issues):
            severity = str(getattr(issue, "severity", "minor")).lower()
            priority: ConflictPriority = (
                "A"
                if severity in {"critical", "blocker"}
                else "B"
                if severity == "major"
                else "C"
                if severity == "minor"
                else "D"
            )
            dim = str(getattr(issue, "dimension", "character"))
            conflict_type = _DIM_TO_TYPE.get(dim, "character")
            conflicts.append(
                GuardianConflict(
                    id=f"conflict_{idx}",
                    type=conflict_type,
                    priority=priority,
                    details=str(getattr(issue, "description", "")),
                    evidence=list(getattr(issue, "evidence", []) or []),
                    resolution_method=_default_resolution(priority),
                    resolution_specifics=str(getattr(issue, "suggestion", "")),
                )
            )

        summary = f"overall_score={overall:.1f}, conflicts={len(conflicts)}"
        return GuardianOutput(scan_summary=summary, conflicts=conflicts)


_DIM_TO_TYPE = {
    "character": "character",
    "plot": "setting",
    "setting": "setting",
    "theme": "setting",
    "style": "character",
    "temporal": "time",
    "relationship": "relationship",
    "foreshadowing": "setting",
}


def _default_resolution(priority: ConflictPriority) -> str:
    return {
        "A": "state_update",       # 必须修正
        "B": "new_event",          # 通过新事件优雅化解
        "C": "legendize",          # 传说化处理
        "D": "ignore",
    }[priority]


class ConsistencyGuardian:
    """每 30 tick 调用一次。LLM 失败时回退到 degraded=True 的空输出。"""

    # v2.18 — 幻觉率监控的硬编码 flag 集合, 与 Orchestrator._consistency_flags
    # 输出对齐。新增 flag 类型时两边同步更新。
    _HALLUCINATION_FLAGS = (
        "inventory_without_action",
        "location_without_move",
        "money_without_action",
    )

    def __init__(self, evaluator=None) -> None:
        """``evaluator`` - EnhancedContinuityEvaluator 实例。若 None 则延迟构造。"""
        self._evaluator = evaluator
        self._adapter = ConsistencyGuardianAdapter()

    def _ensure_evaluator(self):
        if self._evaluator is None:
            try:
                from evaluation.continuity_v2 import EnhancedContinuityEvaluator
                self._evaluator = EnhancedContinuityEvaluator(llm_client=None)
            except ImportError as e:
                logger.error("EnhancedContinuityEvaluator import failed: %s", e)
                return None
        return self._evaluator

    def scan_hallucination_rate(
        self,
        events: list[Event],
        threshold: float = 0.3,
    ) -> list[GuardianConflict]:
        """统计 character_action 事件里的幻觉 flag 出现率, 超阈值产 conflict。

        仅纳入 ``type='character_action'`` 的事件 (exogenous / dramatic 的
        consequences flag 不归属任何 character)。按 ``participants[0]`` 归账。
        ``threshold`` 是严格大于阈值才报 (= 不报), 防边界震荡。

        返回每个 hallucinating character 一个 ``GuardianConflict``:
        priority='B', type='character', resolution_method='state_update',
        resolution_specifics 含降级建议 (model_tier_override='haiku')。

        与 async ``scan()`` 平级 — 调用方 (Orchestrator 阶段 7) 可选择同时跑。
        无 LLM 调用, 纯计数, 100% 确定性。
        """
        if not events:
            return []
        per_char_total: dict[str, int] = {}
        per_char_hits: dict[str, list[str]] = {}
        for ev in events:
            if ev.type != "character_action":
                continue
            if not ev.participants:
                continue
            cid = ev.participants[0]
            per_char_total[cid] = per_char_total.get(cid, 0) + 1
            for cons in ev.consequences:
                if cons in self._HALLUCINATION_FLAGS:
                    per_char_hits.setdefault(cid, []).append(cons)
        conflicts: list[GuardianConflict] = []
        for cid, total in per_char_total.items():
            hits = per_char_hits.get(cid, [])
            if total == 0:
                continue
            rate = len(hits) / total
            if rate <= threshold:
                continue
            unique_flags = sorted(set(hits))
            conflicts.append(
                GuardianConflict(
                    id=f"hallucination_{cid}",
                    type="character",
                    priority="B",
                    details=(
                        f"角色 {cid} 在最近 {total} 个 character_action 中, "
                        f"{len(hits)} 次输出幻觉字段 (rate={rate:.0%}); "
                        f"幻觉类型: {','.join(unique_flags)}"
                    ),
                    evidence=unique_flags,
                    resolution_method="state_update",
                    resolution_specifics=(
                        f"建议为该 agent 设 model_tier_override='haiku', "
                        f"或临时增大 cooldown_until_tick 让其降级冷静。"
                    ),
                )
            )
        return conflicts

    async def scan(
        self,
        *,
        world_state: WorldState,
        char_states: list[CharacterState],
        recent_events: list[Event],
        recent_chapter_text: list[str],
    ) -> GuardianOutput:
        # v2.18 — 幻觉率扫描总是先跑 (无 LLM, 100% 确定性, 即使 evaluator 不可用)
        hallucination_conflicts = self.scan_hallucination_rate(recent_events)

        evaluator = self._ensure_evaluator()
        if evaluator is None or not recent_chapter_text:
            return GuardianOutput(
                scan_summary="evaluator unavailable or no chapter text",
                conflicts=hallucination_conflicts,
                degraded=True,
            )

        previous_context, new_content, memory_context = self._adapter.adapt_inputs(
            world_state, char_states, recent_events, recent_chapter_text
        )
        try:
            # EnhancedContinuityEvaluator.evaluate 接口 - 同步/异步取决于实现
            evaluate_fn = getattr(evaluator, "evaluate")
            result = evaluate_fn(previous_context, new_content, memory_context)
            if hasattr(result, "__await__"):
                result = await result
        except Exception as e:
            logger.error("ConsistencyGuardian.scan failed: %s", e)
            return GuardianOutput(
                scan_summary=f"evaluator error: {e}",
                degraded=True,
            )

        output = self._adapter.adapt_output(result)
        # 把幻觉率 conflict 合并进 LLM 评估器输出
        output.conflicts.extend(hallucination_conflicts)
        return output
