"""Single-call author writer and one-shot targeted repair adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client
from story.context_builder import ContextPackage
from story.models import SectionGoal, ValidationReport, WriterCandidate
from story.validator import report_as_repair_prompt


class WriterOutputError(RuntimeError):
    pass


@dataclass(frozen=True)
class WriterResult:
    candidate: WriterCandidate
    usage: dict[str, int]


class WriterProtocol(Protocol):
    async def generate(self, context: ContextPackage, goal: SectionGoal) -> WriterResult: ...

    async def repair(
        self, candidate: WriterCandidate, report: ValidationReport
    ) -> WriterResult: ...


class AuthorWriter:
    SYSTEM_PROMPT = """你是长篇小说 Writer。你收到十个按优先级隔离的上下文槽位。
StoryBible 是主题与世界规则的最高权威；CanonicalState 是当前事实的唯一权威；
历史记忆只能提供背景，不能覆盖二者。请围绕 SectionGoal 写一节连续正文。

只返回一个 JSON 对象，字段严格为：
narrative_text, title, section_summary, state_delta, threads_opened,
threads_advanced, threads_resolved, memory_records, consistency_notes。

最小合法形态是：
{"narrative_text":"连续正文","title":"小标题","section_summary":"事实摘要",
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

    REPAIR_SYSTEM_PROMPT = """你是小说一致性修复器。输入只含原正文、明确违规项、
必须保持的事实和最小修正范围。最多执行这一次修复。不要扩写新支线，不要修改
无关事实，不要修改 StoryBible。返回一个 JSON 补丁，必须含
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
        self, candidate: WriterCandidate, report: ValidationReport
    ) -> WriterResult:
        response = await llm_client.chat(
            system_prompt=self.REPAIR_SYSTEM_PROMPT,
            user_prompt=report_as_repair_prompt(report, candidate),
            temperature=0.2,
            max_tokens=8192,
            agent_id="author_writer_repair",
            priority="critical",
        )
        return WriterResult(
            candidate=self._parse_repair(response.content, candidate, report),
            usage=self._usage(response),
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
        report: ValidationReport,
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

        candidate_payload = original.model_dump(mode="python")
        candidate_payload["narrative_text"] = narrative
        candidate_payload["state_delta"] = [
            operation.model_dump(mode="python") for operation in report.validated_delta
        ]
        rejected_thread_ids = {
            item.path.rsplit("/", 1)[-1]
            for item in report.violations
            if item.severity == "high" and item.path.startswith("/threads/")
        }
        for key in ("threads_opened", "threads_advanced", "threads_resolved"):
            candidate_payload[key] = [
                thread
                for thread in candidate_payload[key]
                if thread.get("id") not in rejected_thread_ids
            ]
        return WriterCandidate.model_validate(candidate_payload)

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
