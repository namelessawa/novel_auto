"""Single-call whole-book outline generation with one bounded schema repair.

The provider is allowed to propose structure, but never owns revisions or
progress.  This module accepts only the strict proposal schema below, rebuilds
the persisted :class:`BookOutline` locally, and applies deterministic
cross-contract validation against :class:`NovelProductionSpec`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import Field, ValidationError

from nf_core.llm_client import LLMResponse, llm_client
from story.models import StoryBible
from story.production_models import (
    BookOutline,
    ChapterOutline,
    NovelProductionSpec,
    ProductionModel,
    VolumeOutline,
)


class OutlineGenerationError(RuntimeError):
    """A provider response failed the bounded outline output contract."""

    def __init__(self, code: str, errors: list[str]) -> None:
        self.code = code
        self.errors = list(errors)
        super().__init__(f"{code}: {'; '.join(self.errors[:8])}")


class GeneratedBookOutline(ProductionModel):
    """Provider-owned fields only; revisions and progress remain server-owned."""

    logline: str = Field(min_length=1)
    global_arc: str = Field(min_length=1)
    volumes: list[VolumeOutline] = Field(min_length=1)
    chapters: list[ChapterOutline] = Field(min_length=1)
    ending_target: str = Field(min_length=1)
    major_turning_points: list[str] = Field(default_factory=list)
    central_conflict_progression: list[str] = Field(default_factory=list)
    thread_schedule: dict[str, list[str]] = Field(default_factory=dict)
    character_arc_schedule: dict[str, list[str]] = Field(default_factory=dict)

    def as_book_outline(
        self,
        *,
        revision: int,
        progress_revision: int,
    ) -> BookOutline:
        return BookOutline(
            revision=revision,
            progress_revision=progress_revision,
            **self.model_dump(mode="python"),
            status="ready",
        )


@dataclass(frozen=True)
class OutlineGenerationResult:
    proposal: GeneratedBookOutline
    provider_calls: int
    repair_performed: bool
    usage: dict[str, int]


def _usage(response: LLMResponse) -> dict[str, int]:
    prompt = int(response.usage_prompt_tokens or 0)
    completion = int(response.usage_completion_tokens or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _merge_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    return {
        key: int(left.get(key, 0)) + int(right.get(key, 0))
        for key in {"prompt_tokens", "completion_tokens", "total_tokens"}
    }


def _public_validation_errors(exc: Exception) -> list[str]:
    if isinstance(exc, ValidationError):
        rows: list[str] = []
        for error in exc.errors(include_url=False):
            location = ".".join(str(item) for item in error.get("loc", ()))
            message = str(error.get("msg") or "invalid value")
            rows.append(f"{location or 'outline'}: {message}")
        return rows[:80]
    message = str(exc).splitlines()[0][:300] if str(exc) else type(exc).__name__
    return [message]


class WholeBookOutlineGenerator:
    """Generate one outline and perform at most one structured repair."""

    SYSTEM_PROMPT = """你是长篇小说整书大纲规划器，只返回一个 JSON 对象。
输出必须严格符合给定 JSON Schema，不得输出 Markdown、解释或思考过程。

硬规则：
1. 卷 ordinal 与章 ordinal 都从 1 开始且连续；每章只属于一个卷，同卷章节连续。
2. volumes 数量、chapters 数量必须等于 ProductionSpec。
3. 每卷 target_chapters/target_chars 必须与所含章节精确相加。
4. 全部 chapter.target_chars 之和必须精确等于 target_total_chars，且每章落在
   accepted_chapter_min_chars 到 accepted_chapter_max_chars 之间。
5. 只能规划 StoryBible 已有的人物、地点、规则和冲突；不修改 StoryBible 或 Canon。
6. required_events、required_end_states、prohibited_additions 使用 schema 中的严格对象；
   没有可靠内容时使用空数组，不要用字符串冒充对象。
7. 规划一次覆盖全书；后续章节生产不会再次调用整书 Planner。"""

    REPAIR_PROMPT = """上一次整书大纲没有通过服务器确定性校验。
只返回一个完整、替换用的 JSON 对象，严格符合 JSON Schema。逐项修复服务器列出的
错误，不添加解释、Markdown、额外字段或第二个候选。不得改变 ProductionSpec。"""

    async def generate(
        self,
        *,
        spec: NovelProductionSpec,
        bible: StoryBible,
    ) -> OutlineGenerationResult:
        schema = json.dumps(
            GeneratedBookOutline.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        authority = self._authority_payload(spec, bible)
        first = await llm_client.chat(
            system_prompt=(
                self.SYSTEM_PROMPT
                + "\n以下 JSON Schema 是唯一输出契约；additionalProperties=false：\n"
                + schema
            ),
            user_prompt=json.dumps(
                authority,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            temperature=0.0,
            max_tokens=65_536,
            agent_id="whole_book_outline",
            priority="critical",
            response_format={"type": "json_object"},
        )
        usage = _usage(first)
        proposal, errors = self._validate(first.content, spec)
        if proposal is not None:
            return OutlineGenerationResult(
                proposal=proposal,
                provider_calls=1,
                repair_performed=False,
                usage=usage,
            )

        repair = await llm_client.chat(
            system_prompt=(
                self.REPAIR_PROMPT
                + "\n以下 JSON Schema 是唯一输出契约；additionalProperties=false：\n"
                + schema
            ),
            user_prompt=json.dumps(
                {
                    "production_spec": authority["production_spec"],
                    "story_bible_authority": authority["story_bible_authority"],
                    "validation_errors": errors,
                    "rejected_output": (first.content or "")[:120_000],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            temperature=0.0,
            max_tokens=65_536,
            agent_id="whole_book_outline_repair",
            priority="critical",
            response_format={"type": "json_object"},
        )
        usage = _merge_usage(usage, _usage(repair))
        repaired, repair_errors = self._validate(repair.content, spec)
        if repaired is None:
            raise OutlineGenerationError(
                "PROVIDER_OUTPUT_INVALID",
                repair_errors,
            )
        return OutlineGenerationResult(
            proposal=repaired,
            provider_calls=2,
            repair_performed=True,
            usage=usage,
        )

    @staticmethod
    def _validate(
        content: str,
        spec: NovelProductionSpec,
    ) -> tuple[GeneratedBookOutline | None, list[str]]:
        try:
            payload: Any = json.loads((content or "").strip())
            proposal = GeneratedBookOutline.model_validate(payload)
            outline = proposal.as_book_outline(
                revision=1,
                progress_revision=1,
            )
            errors = outline.validation_errors_for(spec)
            if errors:
                return None, errors
            return proposal, []
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
            return None, _public_validation_errors(exc)

    @staticmethod
    def _authority_payload(
        spec: NovelProductionSpec,
        bible: StoryBible,
    ) -> dict[str, Any]:
        return {
            "production_spec": spec.model_dump(
                mode="json",
                include={
                    "title",
                    "premise",
                    "genre",
                    "theme",
                    "central_question",
                    "target_total_chars",
                    "volume_count",
                    "chapter_count",
                    "target_chapter_chars",
                    "accepted_chapter_min_chars",
                    "accepted_chapter_max_chars",
                    "section_target_chars",
                    "generation_language",
                    "ending_direction",
                },
            ),
            "story_bible_authority": bible.model_dump(
                mode="json",
                include={
                    "title",
                    "premise",
                    "genre",
                    "theme",
                    "central_question",
                    "setting_summary",
                    "immutable_world_rules",
                    "protagonist_contracts",
                    "main_conflicts",
                    "ending_direction",
                },
            ),
        }


__all__ = [
    "GeneratedBookOutline",
    "OutlineGenerationError",
    "OutlineGenerationResult",
    "WholeBookOutlineGenerator",
]
