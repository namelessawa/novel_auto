"""Single-call author writer and one-shot targeted repair adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client
from story.context_builder import ContextPackage
from story.models import SectionGoal, WriterCandidate
from story.repair_plan import RepairPlan, repair_plan_prompt_payload


class WriterOutputError(RuntimeError):
    pass


@dataclass(frozen=True)
class WriterResult:
    candidate: WriterCandidate
    usage: dict[str, int]
    ignored_fields: list[str] = field(default_factory=list)


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

    REPAIR_SYSTEM_PROMPT = """你是小说一致性修复器。输入只含原正文、固定事实、
缺失事件、错误最终状态、新增事实、长度问题和最低风格要求。最多执行这一次修复。
只做最小修正；按 RepairPlan 补齐指定事件和终态；不新增人物、数字、日期、亲属、伤势或支线；必须落实缺失结局；
不改变已正确完成的事件；风格优先级低于事实；不要修改 StoryBible。
硬性执行顺序：先逐字删除 unsupported_additions 中列出的 evidence；再为每个待修事件写入 minimum_completion_evidence 所要求的明确完成句；最后让最后一项持有、打开、接收或位置陈述与 wrong_end_states 完全一致。即使你认为原文已经暗示完成，也必须执行这些明示修改，不得原样返回。
返回一个 JSON 补丁，必须含
{"narrative_text":"修复后的完整正文"}。不得返回或重写 state_delta、故事线、
title、section_summary、memory_records、consistency_notes、critique 或解释字段；
系统会自动保留已经通过校验的结构化变化并剔除高风险变化。"""

    async def generate(self, context: ContextPackage, goal: SectionGoal) -> WriterResult:
        output_schema = json.dumps(
            WriterCandidate.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        response = await llm_client.chat(
            system_prompt=(
                self.SYSTEM_PROMPT
                + "\n以下 JSON Schema 是唯一输出契约；additionalProperties=false：\n"
                + output_schema
            ),
            user_prompt=context.prompt,
            temperature=0.65,
            # Short chapters still need room for JSON escaping, deltas and provider
            # reasoning overhead.  A floor of 4096 prevents syntactically truncated
            # candidates while retaining the 8192 hard ceiling.
            max_tokens=min(8192, max(4096, goal.desired_length * 3)),
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
        response = await llm_client.chat(
            system_prompt=self.REPAIR_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                repair_plan_prompt_payload(plan, candidate.narrative_text),
                ensure_ascii=False,
                indent=2,
            ),
            temperature=0.0,
            max_tokens=8192,
            agent_id="author_writer_repair",
            priority="critical",
        )
        ignored_fields = self._repair_ignored_fields(response.content)
        return WriterResult(
            candidate=self._parse_repair(response.content, candidate, plan),
            usage=self._usage(response),
            ignored_fields=ignored_fields,
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
    def _parse_repair(
        content: str,
        original: WriterCandidate,
        report: object | None = None,
    ) -> WriterCandidate:
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError as exc:
            raise WriterOutputError("Writer repair returned invalid JSON") from exc
        if "narrative_text" not in payload and isinstance(
            payload.get("repaired_narrative"), str
        ):
            payload["narrative_text"] = payload["repaired_narrative"]
        narrative = payload.get("narrative_text")
        if not isinstance(narrative, str) or not narrative.strip():
            raise WriterOutputError("Writer repair did not return a complete narrative_text")

        # Repair has prose authority only.  Keep the original structured
        # proposal intact and let StoryValidator re-evaluate every operation
        # and thread against the repaired prose from scratch.
        candidate_payload = original.model_dump(mode="python")
        candidate_payload["narrative_text"] = narrative
        return WriterCandidate.model_validate(candidate_payload)

    @staticmethod
    def _repair_ignored_fields(content: str) -> list[str]:
        try:
            payload = parse_llm_json((content or "").strip())
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []
        return sorted(set(payload) - {"narrative_text"})

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
