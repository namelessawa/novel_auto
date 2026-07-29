"""Single-call author writer and one-shot targeted repair adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client
from story.chapter_plan import ChapterPlan
from story.context_builder import ContextPackage
from story.models import SectionGoal, WriterCandidate
from story.repair_patch import (
    ProviderRepairPatchSet,
    RepairPatchSet,
)
from story.repair_plan import RepairPlan, repair_patch_prompt_payload


class WriterOutputError(RuntimeError):
    pass


@dataclass(frozen=True)
class WriterResult:
    candidate: WriterCandidate
    usage: dict[str, int]
    ignored_fields: list[str] = field(default_factory=list)
    audit_codes: list[str] = field(default_factory=list)
    repair_patches: RepairPatchSet | None = None
    provider_repair_patches: ProviderRepairPatchSet | None = None


@dataclass(frozen=True)
class PlannerResult:
    plan: ChapterPlan
    usage: dict[str, int]


class WriterProtocol(Protocol):
    async def plan(self, context: ContextPackage, goal: SectionGoal) -> PlannerResult: ...

    async def generate(self, context: ContextPackage, goal: SectionGoal) -> WriterResult: ...

    async def repair(
        self, candidate: WriterCandidate, plan: RepairPlan
    ) -> WriterResult: ...


class AuthorWriter:
    PLANNER_SYSTEM_PROMPT = """You are the internal planning pass of one novel Writer.
Return one ChapterPlan JSON object and nothing else. This is temporary section
planning, not canon, memory, state, or a separate story agent.

You may only allocate the required event IDs and required end-state IDs supplied
by the frozen NarrativeContract and EventExecutionPlan. You must not create a
person, location, item, organization, event, thread, state delta, memory,
background fact, history, relationship, injury, casualty, number, date, or world
rule. Copy IDs exactly. Do not paraphrase IDs.

Use exactly four segments in this order: opening, development, conflict,
resolution. Segment target_chars must sum exactly to SectionBudgetPlan
target_chars. Bind every required event to exactly one segment, preserve event
order, list every required event in required_events, list every required end
state in required_end_states, and preserve all server stop conditions. The
resolution segment lands the required end states. StyleBalanceContract controls
expression only; it may not change event count, structure, or length."""

    PLANNING_WRITER_PROMPT = """
The server-derived ChapterPlan below is mandatory for required event order,
required end states, and stop conditions. Its four segments and per-segment
target_chars are soft structural guidance, not exact prose quotas. The total
SectionBudgetPlan min_chars/max_chars range is the only hard length boundary.
Complete only the listed existing events. Build existing action, environment,
current-character interaction, and existing emotion toward the server target
before writing terminal end-state evidence. Put terminal evidence in the final
closure, then stop.
Do not create plot to fill length. Length must come from elaborating existing
events, not from new people, background, conflict, history, or world rules.

Return chapter_evidence with exactly one record for each segment 1-4. Each record
contains only the event IDs actually completed in that planned segment. This
evidence is diagnostic and never overrides prose validation.
"""

    SYSTEM_PROMPT = """你是长篇小说 Writer。你收到十一个按优先级隔离的上下文槽位。
NarrativeContract 是本节人物、事实、事件链、时间压力和固定结局的正文硬契约；
StoryBible 是主题与世界规则的最高权威；CanonicalState 是当前事实的唯一权威；
历史记忆只能提供背景，不能覆盖前三者。请围绕 SectionGoal 写一节连续正文。

权威顺序必须遵守：NarrativeContract > StoryBible / CanonicalState > StyleContract。
风格要求若不能在现有事件链内完成，则允许少满足一项风格特征，不允许新增事实。
Style controls expression, not event count and not chapter length.
不得靠新增打斗、亲属、陪同者、数字、日期、伤势或幕后责任人满足风格；不得为了
含蓄、悬念或格式而省略 NarrativeContract 的必要事件和最终状态。

必须严格按 narrative_contract 槽位中的 EventExecutionPlan.order 顺序实际完成事件。
“准备、打算、走向、想要、即将、如果、也许、原本可以”均不算完成；最后一段必须
明确落实人物动作、物品接收者以及所有 required_end_states。

只返回一个 JSON 对象，字段严格为：
narrative_text, title, section_summary, event_evidence, end_state_evidence,
state_delta, threads_opened,
threads_advanced, threads_resolved, memory_records, consistency_notes,
chapter_evidence。

最小合法形态是：
{"narrative_text":"连续正文","title":"小标题","section_summary":"事实摘要",
"event_evidence":[],"end_state_evidence":[],
"state_delta":[],"threads_opened":[],"threads_advanced":[],"threads_resolved":[],
"memory_records":[],"consistency_notes":[],
"chapter_evidence":[{"segment":1,"events_completed":[]},
{"segment":2,"events_completed":[]},{"segment":3,"events_completed":[]},
{"segment":4,"events_completed":[]}]}
没有确定变化时保持数组为空，不要用 null。state_delta 项形如
{"op":"set","path":"/characters/角色ID/字段","value":"新值",
"evidence":"正文中逐字出现的短句","confidence":0.9}。
故事线对象至少含 id、type、description；memory 对象至少含 id、type、summary。
故事线 type 只能从 mystery、conflict、promise、threat、goal 中选择，status 只能从
open、advancing、resolved、abandoned、stale、needs_attention 中选择；memory type
只能从 event、decision、relationship_change、revelation、promise、consequence 中选择。
这些枚举值必须原样使用英文，不得翻译或另造类别。

state_delta 的每项必须包含 op、path、value、evidence、confidence；path 只能指向
CanonicalState。不得提出 StoryBible 修改。故事线 resolved 必须附正文中可定位的
resolution_evidence。正文之外不要输出解释、Markdown 或思考过程。"""

    REPAIR_SYSTEM_PROMPT = """你不是作者，你是只做局部修改的小说编辑。
最多执行这一次 Repair。你的任务不是重写文章，只能输出 patch JSON。

严格规则：
1. 根对象只能包含 schema_version 和 patches。
2. 每个 patch 只能包含 patch_id 和 patch_text。
3. patch_id 必须逐字复制 provider_patch_requests；不得新增、遗漏或重复。
4. 你无权返回或修改 patch_type、anchor、offset、targets、target_chars、max_chars、
   preserve、purpose、remove_reason、原文 hash 或契约 hash；这些字段由服务端冻结。
5. patch_text 只扩写获准的既有动作、环境、已有人物互动或已存在情绪。
6. 不新增人物、背景、数字、日期、亲属、伤势、伤亡、世界规则、状态或支线。
7. 不复制整段原文，不输出完整 narrative_text，也不做自报字数。

禁止输出 narrative_text、state_delta、threads、memory、summary、title、解释、Markdown
或内部分析。"""

    LENGTH_SYSTEM_PROMPT = """
SectionWritingPlan and SectionBudgetPlan are server-owned and mandatory. Follow
the four segment budgets and hard maxima. Write within the min_chars/max_chars range
(for a 900-character request this is 900-1100), complete every required event
and required end state, and do not add characters, background, numbers,
kinship, casualties, injuries, dates, or world rules. Style changes narration,
never the event inventory or final state.
The minimum is a rejection floor, not the writing target. Do not close before
the safe target zone. Put the terminal state in the final closure and stop
immediately afterward. Never continue with another person, background, conflict,
history, relationship, or explanation.
"""

    REPAIR_LENGTH_PROMPT = """
The server has already selected every operation and placement. Generate prose
only for provider_patch_requests. Aim near target_chars but never exceed
max_chars. Do not truncate prose automatically and do not report a character
count. The server applies deterministic event, end-state, delete, and compact
operations without asking you to copy them.
"""

    async def plan(self, context: ContextPackage, goal: SectionGoal) -> PlannerResult:
        del goal
        output_schema = json.dumps(
            ChapterPlan.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        response = await llm_client.chat(
            system_prompt=(
                self.PLANNER_SYSTEM_PROMPT
                + "\nThe following JSON Schema is the only output contract; "
                "additionalProperties=false:\n"
                + output_schema
            ),
            user_prompt=json.dumps(
                self._planner_payload(context),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            temperature=0.0,
            max_tokens=2048,
            agent_id="author_writer_planner",
            priority="critical",
        )
        return PlannerResult(
            plan=self._parse_plan(response.content),
            usage=self._usage(response),
        )

    async def generate(self, context: ContextPackage, goal: SectionGoal) -> WriterResult:
        output_schema = json.dumps(
            WriterCandidate.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        response = await llm_client.chat(
            system_prompt=(
                self.SYSTEM_PROMPT
                + self.LENGTH_SYSTEM_PROMPT
                + self.PLANNING_WRITER_PROMPT
                + "\n以下 JSON Schema 是唯一输出契约；additionalProperties=false：\n"
                + output_schema
            ),
            user_prompt=context.prompt + self._final_directive(context),
            temperature=0.65,
            # Reasoning-capable OpenAI-compatible models may consume hidden/reasoning
            # budget before emitting the JSON candidate. Keep the bounded 8192 ceiling
            # available so valid section prose is not truncated before serialization.
            max_tokens=8192,
            agent_id="author_writer",
            priority="critical",
        )
        return WriterResult(
            candidate=self._parse(response.content),
            usage=self._usage(response),
        )

    async def repair(
        self, candidate: WriterCandidate, plan: RepairPlan
    ) -> WriterResult:
        output_schema = json.dumps(
            ProviderRepairPatchSet.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        response = await llm_client.chat(
            system_prompt=(
                self.REPAIR_SYSTEM_PROMPT
                + self.REPAIR_LENGTH_PROMPT
                + "\n以下 JSON Schema 是唯一输出契约；additionalProperties=false：\n"
                + output_schema
            ),
            user_prompt=json.dumps(
                repair_patch_prompt_payload(plan, candidate.narrative_text),
                ensure_ascii=False,
                indent=2,
            ),
            temperature=0.0,
            max_tokens=4096,
            agent_id="author_writer_repair",
            priority="critical",
        )
        ignored_fields = self._repair_ignored_fields(response.content)
        return WriterResult(
            candidate=candidate,
            usage=self._usage(response),
            ignored_fields=ignored_fields,
            audit_codes=(
                ["REPAIR_EXTRA_FIELD_IGNORED"] if ignored_fields else []
            ),
            provider_repair_patches=self._parse_provider_repair_patches(
                response.content
            ),
        )

    @staticmethod
    def _parse(content: str) -> WriterCandidate:
        text = (content or "").strip()
        try:
            payload = parse_llm_json(text)
        except json.JSONDecodeError as exc:
            raise WriterOutputError("Writer returned invalid JSON") from exc
        try:
            return WriterCandidate.model_validate(payload)
        except Exception as exc:
            raise WriterOutputError(f"WriterCandidate validation failed: {exc}") from exc

    @staticmethod
    def _parse_plan(content: str) -> ChapterPlan:
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError as exc:
            raise WriterOutputError("Writer planner returned invalid JSON") from exc
        try:
            return ChapterPlan.model_validate(payload)
        except Exception as exc:
            raise WriterOutputError(
                f"ChapterPlan validation failed: {exc}"
            ) from exc

    @staticmethod
    def _parse_provider_repair_patches(
        content: str,
    ) -> ProviderRepairPatchSet:
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError as exc:
            raise WriterOutputError("Writer repair returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise WriterOutputError("Writer repair must return a JSON object")
        raw_patches = payload.get("patches", [])
        if isinstance(raw_patches, dict):
            raw_patches = [raw_patches]
        if not isinstance(raw_patches, list):
            raw_patches = []
        patches = [
            {
                "patch_id": raw.get("patch_id"),
                "patch_text": raw.get("patch_text"),
            }
            for raw in raw_patches
            if isinstance(raw, dict)
        ]
        try:
            return ProviderRepairPatchSet.model_validate(
                {
                    "schema_version": payload.get("schema_version", 1),
                    "patches": patches,
                }
            )
        except Exception as exc:
            raise WriterOutputError(
                f"Writer repair patch validation failed: {exc}"
            ) from exc

    @staticmethod
    def _parse_repair_patches(content: str) -> RepairPatchSet:
        """Legacy parser for persisted fixtures and compatibility tests only."""
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError as exc:
            raise WriterOutputError("Writer repair returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise WriterOutputError("Writer repair must return a JSON object")
        raw_patches = payload.get("patches", [])
        if isinstance(raw_patches, dict):
            raw_patches = [raw_patches]
        if not isinstance(raw_patches, list):
            raw_patches = []
        patches: list[dict] = []
        allowed_patch_fields = {
            "patch_id",
            "patch_type",
            "anchor",
            "patch_text",
            "target_events",
            "target_end_states",
            "max_chars",
            "preserve",
            "target_chars",
            "purpose",
            "remove_reason",
            "max_remove_chars",
        }
        for raw in raw_patches:
            if not isinstance(raw, dict):
                continue
            item = {key: raw[key] for key in allowed_patch_fields if key in raw}
            anchor = item.get("anchor")
            if isinstance(anchor, str):
                item["anchor"] = {"before_text": anchor, "after_text": ""}
            elif isinstance(anchor, dict):
                item["anchor"] = {
                    key: anchor[key]
                    for key in ("before_text", "after_text", "start", "end")
                    if key in anchor
                }
            for key in ("target_events", "target_end_states", "preserve"):
                value = item.get(key, [])
                if value is None:
                    item[key] = []
                elif not isinstance(value, list):
                    item[key] = [value]
            if isinstance(item.get("patch_type"), str):
                item["patch_type"] = item["patch_type"].strip().lower()
            patches.append(item)
        try:
            return RepairPatchSet.model_validate(
                {
                    "schema_version": payload.get("schema_version", 1),
                    "patches": patches,
                }
            )
        except Exception as exc:
            raise WriterOutputError(
                f"Writer repair patch validation failed: {exc}"
            ) from exc

    @staticmethod
    def _repair_ignored_fields(content: str) -> list[str]:
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        ignored = {
            key for key in payload if key not in {"schema_version", "patches"}
        }
        raw_patches = payload.get("patches", [])
        if isinstance(raw_patches, dict):
            raw_patches = [raw_patches]
        allowed_patch_fields = {"patch_id", "patch_text"}
        if isinstance(raw_patches, list):
            for index, patch in enumerate(raw_patches):
                if not isinstance(patch, dict):
                    continue
                ignored.update(
                    f"patches[{index}].{key}"
                    for key in patch
                    if key not in allowed_patch_fields
                )
        return sorted(ignored)

    @staticmethod
    def _final_directive(context: ContextPackage) -> str:
        writing_plan = context.writing_plan
        budget_plan = context.section_budget_plan
        if writing_plan is None or budget_plan is None:
            return ""
        part_lines = "\n".join(
            f"- {item.name}: 约 {item.budget} 字，最多 {item.max_chars} 字"
            for item in budget_plan.segments
        )
        balance = budget_plan.style_balance_contract
        chapter_plan = context.chapter_plan
        plan_lines = ""
        if chapter_plan is not None:
            rendered_segments = [
                (
                    f"Segment {segment.order}: 目标={segment.purpose}; "
                    f"软长度参考={segment.target_chars}; "
                    f"事件={json.dumps(segment.events, ensure_ascii=False)}"
                )
                for segment in sorted(
                    chapter_plan.segments,
                    key=lambda item: item.order,
                )
            ]
            plan_lines = (
                "\n## 你的章节计划\n"
                + "\n".join(rendered_segments)
                + "\nrequired_end_states="
                + json.dumps(
                    chapter_plan.required_end_states,
                    ensure_ascii=False,
                )
                + "\nstop_condition="
                + json.dumps(
                    chapter_plan.stop_condition,
                    ensure_ascii=False,
                )
                + "\n满足 stop_condition 后立即停止。\n"
            )
        return (
            plan_lines
            + "\n\n## 服务端最终执行令（输出前必须逐项自检）\n"
            f"narrative_text 中心目标 {budget_plan.target_chars} 字，硬接受区间 "
            f"{budget_plan.min_chars}-{budget_plan.max_chars} 字。\n"
            "以下四部分仅作结构提示，可自然衔接；分段字数不是硬配额：\n"
            f"{part_lines}\n"
            "先在既有事件内部扩写动作、环境、当前人物互动和已有情绪，目标进入"
            f"约 {max(budget_plan.min_chars, budget_plan.target_chars - 50)}-"
            f"{budget_plan.target_chars} 字安全区后，再在最后收束段明确落实全部 "
            "required_end_states；终态证据后立即结束。最低字数只是拒绝下限，不是"
            "写作目标，也不得提前用终态收口。停止时必须已完成全部必要事件和全部"
            "最终状态。不得超过 "
            f"{budget_plan.max_chars} 字；不得在结束后增加新人物、背景、冲突、历史、"
            "关系或解释。\n"
            f"风格平衡：{balance.instruction}\n"
            f"限制：{'；'.join(balance.limits)}。\n"
            f"禁止：{'；'.join(balance.forbidden)}。\n"
            "如果尚未进入目标安全区，只能扩写已有动作、环境、已有人物互动或已存在"
            "情绪。不要创造新的剧情来填充长度。禁止用新人物、新背景、新冲突或"
            "新事实补字数。不要输出、自报或猜测统计字数。\n"
        )

    @staticmethod
    def _planner_payload(context: ContextPackage) -> dict:
        narrative_contract = (
            context.narrative_contract.model_dump(mode="json")
            if context.narrative_contract
            else {}
        )
        event_plan = (
            context.event_execution_plan.model_dump(mode="json")
            if context.event_execution_plan
            else {}
        )
        budget_plan = (
            context.section_budget_plan.model_dump(mode="json")
            if context.section_budget_plan
            else {}
        )
        style_balance = (
            context.section_budget_plan.style_balance_contract.model_dump(
                mode="json"
            )
            if context.section_budget_plan
            else {}
        )
        return {
            "story_bible": context.slots.get("story_bible", ""),
            "canonical_state": context.slots.get("canonical_state", ""),
            "narrative_contract": narrative_contract,
            "event_execution_plan": event_plan,
            "section_budget_plan": budget_plan,
            "style_balance_contract": style_balance,
        }

    @staticmethod
    def _usage(response) -> dict[str, int]:
        prompt = int(getattr(response, "usage_prompt_tokens", 0) or 0)
        completion = int(getattr(response, "usage_completion_tokens", 0) or 0)
        cached = int(getattr(response, "usage_cached_tokens", 0) or 0)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "cached_tokens": cached,
            "total_tokens": prompt + completion,
        }


__all__ = [
    "AuthorWriter",
    "PlannerResult",
    "WriterOutputError",
    "WriterProtocol",
    "WriterResult",
]
