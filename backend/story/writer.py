"""Single-call author writer and one-shot targeted repair adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client
from story.context_builder import ContextPackage
from story.models import SectionGoal, WriterCandidate
from story.repair_patch import RepairPatchSet
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


class WriterProtocol(Protocol):
    async def generate(self, context: ContextPackage, goal: SectionGoal) -> WriterResult: ...

    async def repair(
        self, candidate: WriterCandidate, plan: RepairPlan
    ) -> WriterResult: ...


class AuthorWriter:
    SYSTEM_PROMPT = """你是长篇小说 Writer。你收到十一个按优先级隔离的上下文槽位。
NarrativeContract 是本节人物、事实、事件链、时间压力和固定结局的正文硬契约；
StoryBible 是主题与世界规则的最高权威；CanonicalState 是当前事实的唯一权威；
历史记忆只能提供背景，不能覆盖前三者。请围绕 SectionGoal 写一节连续正文。

权威顺序必须遵守：NarrativeContract > StoryBible / CanonicalState > StyleContract。
风格要求若不能在现有事件链内完成，则允许少满足一项风格特征，不允许新增事实。
不得靠新增打斗、亲属、陪同者、数字、日期、伤势或幕后责任人满足风格；不得为了
含蓄、悬念或格式而省略 NarrativeContract 的必要事件和最终状态。

必须严格按 narrative_contract 槽位中的 EventExecutionPlan.order 顺序实际完成事件。
“准备、打算、走向、想要、即将、如果、也许、原本可以”均不算完成；最后一段必须
明确落实人物动作、物品接收者以及所有 required_end_states。

只返回一个 JSON 对象，字段严格为：
narrative_text, title, section_summary, event_evidence, end_state_evidence,
state_delta, threads_opened,
threads_advanced, threads_resolved, memory_records, consistency_notes。

最小合法形态是：
{"narrative_text":"连续正文","title":"小标题","section_summary":"事实摘要",
"event_evidence":[],"end_state_evidence":[],
"state_delta":[],"threads_opened":[],"threads_advanced":[],"threads_resolved":[],
"memory_records":[],"consistency_notes":[]}
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
2. 每个 patch 只能是 insert、replace、delete、expand、compact，并解决一个 RepairPlan 明确问题。
3. anchor 必须逐字复制 relevant_windows 中唯一出现的短文本，不能概括。
4. insert 默认插在 before_text 之后；replace/delete 在只有一个 anchor 时修改该 anchor，
   两个 anchor 时只修改二者之间的局部文本。
5. patch_text 不超过 300 字；compact 单次删除不超过 200 字。不得替换整篇正文。
6. 先完成事件，再落实最终状态，再删除未授权新增，最后才允许受约束的 expand/compact。
7. 事件 patch 必须逐字落实 minimum_completion_evidence 的 actor、target 和完成动作。
8. 终态 patch 必须明确写出谁交、谁收、什么物品以及最终由谁持有；决定、准备、暗示不算。
9. 不修改 preserve 内容，不新增人物、背景、数字、日期、亲属、伤势、世界规则或支线。
10. required_patches 非空时，必须逐字段、逐字原样复制并保持顺序；
    不得改写 patch_text，不得把姓名换成代词，不得替换或缩短 anchor/preserve。
11. expansion_request 非空时，只能在 required_patches 后追加一个符合该请求的 expand。
12. compact 必须逐字段复制 required_patches，不能自己选择删除范围。

禁止输出 narrative_text、state_delta、threads、memory、summary、title、解释、Markdown
或内部分析。即使你认为原文已经足够，也必须返回至少一个有效 patch。"""

    LENGTH_SYSTEM_PROMPT = """
SectionWritingPlan and SectionBudgetPlan are server-owned and mandatory. Follow
the four segment budgets and hard maxima. Write within the min_chars/max_chars range
(for a 900-character request this is 900-1100), complete every required event
and required end state, and do not add characters, background, numbers,
kinship, casualties, injuries, dates, or world rules. Style changes narration,
never the event inventory or final state.
Stop immediately once all required events and end states are complete and the
minimum length is reached. Never continue with another person, background,
conflict, history, relationship, or explanation.
"""

    REPAIR_LENGTH_PROMPT = """
EXPAND is the only length-addition patch type. It is lower priority than event
completion, required end states, and deletion of illegal facts. Copy every
required_patches entry exactly and in order. If expansion_request exists,
append exactly one EXPAND patch using its exact anchor, target_chars, max_chars,
purpose, and preserve fields; generate only patch_text. target_chars is the
desired addition and max_chars is the hard ceiling.
EXPAND may elaborate only existing action, environment, existing-character
interaction, or existing emotion. It may not add an event, person, fact,
number, date, kinship, casualty, injury, background, world rule, or state
change, and it may not repeat source prose.
COMPACT is server-selected deletion only. Copy its start/end anchors,
remove_reason, preserve identifiers, and max_remove_chars exactly. Never put
text into a COMPACT patch and never choose a different deletion span.
"""

    async def generate(self, context: ContextPackage, goal: SectionGoal) -> WriterResult:
        output_schema = json.dumps(
            WriterCandidate.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        writing_plan = context.writing_plan
        budget_plan = context.section_budget_plan
        final_directive = ""
        if writing_plan is not None and budget_plan is not None:
            part_lines = "\n".join(
                f"- {item.name}: 约 {item.budget} 字，最多 {item.max_chars} 字"
                for item in budget_plan.segments
            )
            balance = budget_plan.style_balance_contract
            final_directive = (
                "\n\n## 服务端最终执行令（输出前必须逐项自检）\n"
                f"narrative_text 中心目标 {budget_plan.target_chars} 字，硬接受区间 "
                f"{budget_plan.min_chars}-{budget_plan.max_chars} 字。\n"
                "按以下四部分实际写足，不得合并成提纲：\n"
                f"{part_lines}\n"
                "先完成全部 required_events，再明确落实全部 required_end_states。"
                "停止条件同时满足时必须立即结束：全部必要事件完成、全部最终状态达到、"
                f"非空白字符不少于 {budget_plan.min_chars}。不得超过 "
                f"{budget_plan.max_chars} 字；不得在结束后增加新人物、背景、冲突、历史、"
                "关系或解释。\n"
                f"风格平衡：{balance.instruction}\n"
                f"限制：{'；'.join(balance.limits)}。\n"
                f"禁止：{'；'.join(balance.forbidden)}。\n"
                "如果尚未达到最低长度，只能扩写已有动作、环境、已有人物互动或已存在"
                "情绪。禁止用新事实补字数。不要输出统计过程。\n"
            )
        response = await llm_client.chat(
            system_prompt=(
                self.SYSTEM_PROMPT
                + self.LENGTH_SYSTEM_PROMPT
                + "\n以下 JSON Schema 是唯一输出契约；additionalProperties=false：\n"
                + output_schema
            ),
            user_prompt=context.prompt + final_directive,
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
            RepairPatchSet.model_json_schema(),
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
            repair_patches=self._parse_repair_patches(response.content),
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
    def _parse_repair_patches(content: str) -> RepairPatchSet:
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
        allowed_patch_fields = {
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
    "WriterOutputError",
    "WriterProtocol",
    "WriterResult",
]
