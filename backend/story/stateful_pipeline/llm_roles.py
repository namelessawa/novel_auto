"""LLM role services for the stateful chapter generation pipeline.

Each role is a logical function, not an autonomous agent.
They use the same structured Provider call mechanism as the existing Writer.

Roles:
  - Synopsis LLM: generates chapter synopses
  - Foreshadow Extractor: identifies foreshadow candidates from prose
  - Information Extractor: extracts structured info per schema
  - Integration LLM: normalizes info into memory documents
  - Transfer LLM: compiles context for next chapter
  - Schema Generator: auto-generates information schema
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from nf_core.json_utils import parse_llm_json, strip_code_fence
from nf_core.llm_client import llm_client
from story.models import StoryBible
from story.stateful_pipeline.models import (
    ChapterInformation,
    ForeshadowRecord,
    InformationField,
    InformationSchema,
    PipelineModel,
    TransferContext,
)


class PipelineLLMError(RuntimeError):
    """Raised when a pipeline LLM role fails."""


# ---------------------------------------------------------------------------
# StoryBible → PromptView
# ---------------------------------------------------------------------------


class StoryBiblePromptView(PipelineModel):
    """The exact StoryBible material pipeline-owned prompts may use.

    Every field is read by name, so renaming a ``StoryBible`` field breaks here
    loudly instead of silently dropping setting material from a prompt.
    """

    title: str = ""
    genre: str = ""
    premise: str = ""
    theme: str = ""
    central_question: str = ""
    setting_summary: str = ""
    immutable_world_rules: list[str] = Field(default_factory=list)
    forbidden_deviations: list[str] = Field(default_factory=list)
    protagonist_contracts: list[str] = Field(default_factory=list)
    main_conflicts: list[str] = Field(default_factory=list)
    ending_direction: str = ""


def story_bible_prompt_view(bible: StoryBible) -> StoryBiblePromptView:
    """Convert the authoritative StoryBible into its prompt projection."""

    return StoryBiblePromptView(
        title=bible.title,
        genre=bible.genre,
        premise=bible.premise,
        theme=bible.theme,
        central_question=bible.central_question,
        setting_summary=bible.setting_summary,
        immutable_world_rules=list(bible.immutable_world_rules),
        forbidden_deviations=list(bible.forbidden_deviations),
        protagonist_contracts=list(bible.protagonist_contracts),
        main_conflicts=list(bible.main_conflicts),
        ending_direction=bible.ending_direction,
    )


def render_story_bible_prompt(view: StoryBiblePromptView) -> str:
    """Render the projection as compact prompt text (empty fields omitted)."""

    lines: list[str] = []
    for label, value in (
        ("标题", view.title),
        ("类型", view.genre),
        ("故事前提", view.premise),
        ("主题", view.theme),
        ("核心问题", view.central_question),
        ("背景摘要", view.setting_summary),
        ("不可变世界规则", view.immutable_world_rules),
        ("禁止偏离", view.forbidden_deviations),
        ("主角契约", view.protagonist_contracts),
        ("主要冲突", view.main_conflicts),
        ("结局方向", view.ending_direction),
    ):
        if isinstance(value, str):
            if value.strip():
                lines.append(f"{label}：{value.strip()}")
        elif value:
            lines.append(f"{label}：" + "；".join(value))
    return "\n".join(lines)


def _parse_llm_output(raw: str) -> Any:
    """Parse LLM output that can be either a JSON object or array.

    Unlike parse_llm_json which only handles objects, this handles arrays too.
    """
    text = strip_code_fence(raw)
    # Try to parse as JSON directly (handles both objects and arrays)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try parse_llm_json for objects
    try:
        return parse_llm_json(raw)
    except json.JSONDecodeError:
        pass
    # Try to extract array if present
    start = text.find("[")
    if start >= 0:
        # Find matching closing bracket
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise PipelineLLMError(f"Failed to parse LLM output: {raw[:200]}")


# Maximum attempts for structured LLM role calls (extraction / integration).
DEFAULT_ROLE_MAX_ATTEMPTS = 3


async def _retry_llm_call(
    call,
    *,
    max_attempts: int = DEFAULT_ROLE_MAX_ATTEMPTS,
    validate=None,
    role_name: str = "llm_role",
):
    """Invoke an async LLM call with retry on failure or invalid output.

    Args:
        call: async callable returning an LLM response (with .content).
        max_attempts: total attempts before giving up.
        validate: optional callable(content) -> parsed result. If it raises
            or returns None, the attempt is treated as failed and retried.
        role_name: label used in error messages.

    Returns:
        The validated result if ``validate`` is given, else the raw content.

    Raises:
        PipelineLLMError: after all attempts fail.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = await call()
        except Exception as exc:
            last_error = exc
            continue

        content = response.content
        if validate is None:
            if content and content.strip():
                return content
            last_error = PipelineLLMError(f"{role_name} returned empty output")
            continue

        try:
            result = validate(content)
        except Exception as exc:
            last_error = exc
            continue

        if result is not None:
            return result
        last_error = PipelineLLMError(f"{role_name} output failed validation")

    raise PipelineLLMError(
        f"{role_name} failed after {max_attempts} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# Synopsis LLM
# ---------------------------------------------------------------------------

SYNOPSIS_SYSTEM_PROMPT = """你是一个小说梗概生成器。根据提供的故事设定，生成指定章节的梗概。
每个梗概包含标题和概要描述，概括本章的主要情节和发展方向。
输出严格 JSON 格式，不要添加任何额外说明。"""


async def generate_synopsis(
    novel_id: str,
    story_bible_summary: str,
    genre: str,
    chapter_numbers: list[int],
    *,
    max_tokens: int = 2048,
) -> list[dict[str, str]]:
    """Generate synopses for specified chapters.

    Returns list of {"chapter": N, "title": "...", "synopsis": "..."}
    """
    chapters_str = ", ".join(f"第{n}章" for n in chapter_numbers)
    user_prompt = json.dumps(
        {
            "task": "generate_synopsis",
            "chapters": chapters_str,
            "genre": genre,
            "story_bible": story_bible_summary,
            "output_format": {
                "type": "array",
                "items": {
                    "chapter": "int",
                    "title": "string (章节标题)",
                    "synopsis": "string (200-500字梗概)",
                },
            },
        },
        ensure_ascii=False,
    )

    response = await llm_client.chat(
        system_prompt=SYNOPSIS_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.7,
        max_tokens=max_tokens,
        agent_id="pipeline_synopsis",
        priority="critical",
        response_format={"type": "json_object"},
    )

    try:
        data = _parse_llm_output(response.content)
        if isinstance(data, dict):
            items = data.get("chapters", data.get("results", []))
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError(f"Unexpected synopsis output type: {type(data)}")
        return items
    except (json.JSONDecodeError, ValueError, KeyError, PipelineLLMError) as exc:
        raise PipelineLLMError(f"Failed to parse synopsis output: {exc}") from exc


# ---------------------------------------------------------------------------
# Simplified Chapter Writer — experimental / smoke / legacy compatibility only
# ---------------------------------------------------------------------------

SIMPLIFIED_WRITER_SYSTEM_PROMPT = """你是一个小说章节写作器。根据提供的梗概、风格要求和节奏模式，写出一章完整的正文。
要求：
- 直接输出散文正文，不要 JSON 结构
- 遵循梗概的情节方向
- 遵循风格要求的叙事方式
- 根据节奏模式调整本章基调
- 字数控制在 1500-2500 字
正文用 <prose> 标签包裹。"""

PACING_MODE_INSTRUCTIONS = {
    "flat": "本章基调：平淡叙事。以日常描写、人物刻画、环境铺垫为主，节奏舒缓，不引入重大冲突。",
    "conflict": "本章基调：冲突制造。引入新的矛盾、对立或危机，制造紧张感和悬念。",
    "conflict_resolve": "本章基调：冲突解决。此前引入的冲突必须在本章得到明确解决或重大推进，给出结果。",
    "climax": "本章基调：高潮。安排重大转折点或重大事故，情绪张力达到峰值，是全书关键节点。",
}


def _extract_prose(content: str) -> str:
    """Extract prose text from <prose> tags, falling back to raw content."""
    if "<prose>" in content and "</prose>" in content:
        start = content.find("<prose>") + len("<prose>")
        end = content.find("</prose>")
        return content[start:end].strip()
    return content.strip()


# Minimum characters for a valid chapter prose. Below this, treat as empty
# and trigger a retry.
MIN_VALID_PROSE_CHARS = 200
# Maximum writer attempts per chapter (initial call + retries).
DEFAULT_WRITER_MAX_ATTEMPTS = 3


async def write_chapter_simplified(
    novel_id: str,
    chapter_number: int,
    synopsis: str,
    style_prefix: str,
    pacing_mode: str,
    transfer_context: str,
    *,
    max_tokens: int = 6000,
    max_attempts: int = DEFAULT_WRITER_MAX_ATTEMPTS,
    min_prose_chars: int = MIN_VALID_PROSE_CHARS,
) -> str:
    """Write a chapter with simplified plain-prose output.

    Not the official chapter writer.  This role bypasses StoryBible,
    CanonicalState, NarrativeContract, the Author validator, repair and the
    transaction commit boundary, so it is retained only for experimental,
    smoke-test and legacy-compatibility use.  Official chapter prose is
    produced by ``AuthorGenerationService`` through
    :mod:`story.stateful_pipeline.author_bridge`.

    Retries automatically when the model returns empty or too-short prose.
    Returns the prose text (without <prose> tags).

    Raises:
        PipelineLLMError: if all attempts produce empty/invalid output.
    """
    pacing_instruction = PACING_MODE_INSTRUCTIONS.get(
        pacing_mode, PACING_MODE_INSTRUCTIONS["flat"]
    )

    # Build the user prompt
    prompt_parts = [
        f"## 章节：第{chapter_number}章",
        "",
        "## 节奏模式",
        pacing_instruction,
        "",
        "## 章节梗概",
        synopsis,
    ]

    if style_prefix:
        prompt_parts.extend(["", "## 风格要求", style_prefix])

    if transfer_context:
        prompt_parts.extend(["", "## 前文上下文", transfer_context])

    prompt_parts.extend([
        "",
        "## 输出要求",
        "请用 <prose> 标签包裹正文，例如：",
        "<prose>",
        "正文内容...",
        "</prose>",
    ])

    user_prompt = "\n".join(prompt_parts)

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = await llm_client.chat(
                system_prompt=SIMPLIFIED_WRITER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=max_tokens,
                agent_id="pipeline_simplified_writer",
                priority="critical",
            )
        except Exception as exc:
            last_error = exc
            continue

        prose = _extract_prose(response.content)
        if len(prose) >= min_prose_chars:
            return prose

        # Output empty or too short — retry.
        last_error = PipelineLLMError(
            f"Writer output too short ({len(prose)} chars) on attempt {attempt}"
        )

    raise PipelineLLMError(
        f"Chapter writing failed after {max_attempts} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# Foreshadow Extractor LLM
# ---------------------------------------------------------------------------

FORESHADOW_SYSTEM_PROMPT = """你是一个伏笔识别器。从已经生成的正文中识别适合作为未来伏笔的内容。
伏笔是正文中暗示未来情节、悬念或未解之谜的具体元素。
要求：
- 严格从正文中选取，不得凭空创造
- 输出指定数量的伏笔
- 每个伏笔包含原文引用和摘要
输出严格 JSON 格式。"""


async def extract_foreshadows(
    novel_id: str,
    chapter_number: int,
    prose_text: str,
    count: int,
    *,
    max_tokens: int = 2048,
) -> list[dict[str, str]]:
    """Extract exactly `count` foreshadow candidates from prose.

    Returns list of {"source_text": "...", "summary": "..."}
    """
    if count <= 0:
        return []

    user_prompt = json.dumps(
        {
            "task": "extract_foreshadows",
            "chapter": chapter_number,
            "count": count,
            "prose": prose_text,
            "output_format": {
                "type": "array",
                "items": {
                    "source_text": "string (正文中的原文引用)",
                    "summary": "string (伏笔内容摘要)",
                },
            },
        },
        ensure_ascii=False,
    )

    response = await llm_client.chat(
        system_prompt=FORESHADOW_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=max_tokens,
        agent_id="pipeline_foreshadow_extractor",
        priority="critical",
        response_format={"type": "json_object"},
    )

    try:
        data = _parse_llm_output(response.content)
        if isinstance(data, dict):
            items = data.get("foreshadows", data.get("results", []))
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError(f"Unexpected foreshadow output type: {type(data)}")
        return items[:count]  # Ensure we don't return more than requested
    except (json.JSONDecodeError, ValueError, KeyError, PipelineLLMError) as exc:
        raise PipelineLLMError(f"Failed to parse foreshadow output: {exc}") from exc


# ---------------------------------------------------------------------------
# Information Extractor LLM
# ---------------------------------------------------------------------------

INFORMATION_SYSTEM_PROMPT = """你是一个信息抽取器。根据提供的 Schema 从章节正文中抽取结构化信息。
严格按照 Schema 定义的字段进行抽取，不得自行添加、删除或修改字段。
每个字段可以包含多个条目。
输出严格 JSON 格式。"""


async def extract_information(
    novel_id: str,
    chapter_number: int,
    prose_text: str,
    schema: InformationSchema,
    *,
    max_tokens: int = 4096,
    model_override: str | None = None,
    provider_config: Any | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Extract structured information from prose according to schema.

    Returns dict mapping field keys to lists of extracted items.

    provider_config, when given, overrides the request-scoped provider for
    this call only (e.g. to route extraction through deepseek-v4-pro).
    """
    field_descriptions = [
        {
            "key": f.key,
            "name": f.name,
            "description": f.description,
        }
        for f in sorted(schema.fields, key=lambda x: x.order)
    ]

    user_prompt = json.dumps(
        {
            "task": "extract_information",
            "chapter": chapter_number,
            "schema_fields": field_descriptions,
            "prose": prose_text,
            "output_format": {
                "type": "object",
                "fields": {f.key: "array of objects" for f in schema.fields},
            },
        },
        ensure_ascii=False,
    )

    async def _call():
        return await llm_client.chat(
            system_prompt=INFORMATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=max_tokens,
            agent_id="pipeline_information_extractor",
            priority="critical",
            response_format={"type": "json_object"},
            model_override=model_override,
            provider_config=provider_config,
        )

    def _validate(content: str):
        data = _parse_llm_output(content)
        if isinstance(data, dict):
            allowed_keys = set(schema.field_keys)
            result = {}
            for key in allowed_keys:
                if key in data:
                    items = data[key]
                    result[key] = items if isinstance(items, list) else [items]
                else:
                    result[key] = []
            return result
        raise ValueError(f"Unexpected information output type: {type(data)}")

    try:
        return await _retry_llm_call(
            _call, validate=_validate, role_name="information_extractor"
        )
    except PipelineLLMError as exc:
        raise PipelineLLMError(f"Failed to parse information output: {exc}") from exc


# ---------------------------------------------------------------------------
# Integration LLM
# ---------------------------------------------------------------------------

INTEGRATION_SYSTEM_PROMPT = """你是一个记忆整合器。将结构化的章节信息转换为适合长期检索的自然语言记忆文档。
要求：
- 合并同义信息，避免明显重复
- 转换为流畅的自然语言描述
- 保留关键实体和关系
- 输出严格 JSON 格式的文档数组
不要直接访问数据库，你只负责生成文档内容。"""


async def _integrate_single_field(
    chapter_number: int,
    field_key: str,
    field_name: str,
    items: list[Any],
    *,
    max_tokens: int = 2048,
    model_override: str | None = None,
) -> list[dict[str, Any]]:
    """Integrate one schema field's items into memory documents."""
    user_prompt = json.dumps(
        {
            "task": "integrate_memory",
            "chapter": chapter_number,
            "field": field_key,
            "field_name": field_name,
            "items": items,
            "output_format": {
                "type": "array",
                "items": {
                    "content": "string (自然语言记忆描述)",
                    "entities": "array of strings (涉及的实体)",
                },
            },
        },
        ensure_ascii=False,
    )

    async def _call():
        return await llm_client.chat(
            system_prompt=INTEGRATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=max_tokens,
            agent_id="pipeline_integration",
            priority="critical",
            response_format={"type": "json_object"},
            model_override=model_override,
        )

    def _validate(content: str):
        data = _parse_llm_output(content)
        if isinstance(data, dict):
            return data.get("documents", data.get("memories", []))
        if isinstance(data, list):
            return data
        raise ValueError(f"Unexpected integration output type: {type(data)}")

    docs = await _retry_llm_call(_call, validate=_validate, role_name="integration")
    # Tag each doc with its source field for metadata.
    for doc in docs:
        if isinstance(doc, dict):
            doc.setdefault("metadata", {})
            doc["metadata"]["field"] = field_key
    return docs


async def integrate_memory(
    novel_id: str,
    chapter_number: int,
    information: ChapterInformation,
    schema: InformationSchema,
    *,
    max_tokens: int = 2048,
    model_override: str | None = None,
) -> list[dict[str, Any]]:
    """Transform structured information into memory documents.

    Processes each non-empty schema field in a separate LLM call to keep
    per-call input short, then combines the results. Empty fields are skipped.

    Returns list of {"content": "...", "metadata": {...}}
    """
    field_names = {f.key: f.name for f in schema.fields}
    all_documents: list[dict[str, Any]] = []
    field_errors: list[str] = []

    for field_key, items in information.data.items():
        if not items:
            continue  # Skip empty fields — nothing to integrate.

        field_name = field_names.get(field_key, field_key)
        try:
            docs = await _integrate_single_field(
                chapter_number=chapter_number,
                field_key=field_key,
                field_name=field_name,
                items=items,
                max_tokens=max_tokens,
                model_override=model_override,
            )
            all_documents.extend(docs)
        except PipelineLLMError as exc:
            # Record the failure but continue with other fields so one
            # field's failure does not lose the rest of the chapter's memory.
            field_errors.append(f"{field_key}: {exc}")

    if not all_documents and field_errors:
        raise PipelineLLMError(
            f"Integration failed for all fields: {'; '.join(field_errors)}"
        )

    return all_documents


# ---------------------------------------------------------------------------
# Transfer LLM
# ---------------------------------------------------------------------------

TRANSFER_SYSTEM_PROMPT = """你是一个上下文传递器。整理最近章节的信息和选中的伏笔，为下一章创作提供紧凑的上下文。
你不写正文，不改变事实，不新增或选择伏笔，不修改信息。
你只是将程序准备好的内容整理成小说创作容易使用的形式。
输出严格 JSON 格式。"""


async def build_transfer_context(
    novel_id: str,
    target_chapter: int,
    recent_informations: list[ChapterInformation],
    selected_foreshadow: ForeshadowRecord | None,
    chapter_synopsis: str,
    *,
    max_tokens: int = 3072,
) -> TransferContext:
    """Compile context from recent chapters and selected foreshadow.

    Experimental / derived retrieval only.  Official chapter continuity comes
    from the Author ``ContextBuilder`` (previous prose tail, recent section
    summaries and typed long-term memories), so this role is not called on the
    production path and must not become a second context mechanism.

    Returns TransferContext for inspection and derived retrieval.
    """
    recent_data = []
    source_chapters = []
    for info in recent_informations:
        source_chapters.append(info.chapter_number)
        recent_data.append({
            "chapter": info.chapter_number,
            "data": info.data,
        })

    foreshadow_info = None
    if selected_foreshadow:
        foreshadow_info = {
            "id": selected_foreshadow.id,
            "source_chapter": selected_foreshadow.source_chapter,
            "summary": selected_foreshadow.summary,
            "source_text": selected_foreshadow.source_text,
        }

    user_prompt = json.dumps(
        {
            "task": "build_transfer_context",
            "target_chapter": target_chapter,
            "recent_chapters": recent_data,
            "selected_foreshadow": foreshadow_info,
            "chapter_synopsis": chapter_synopsis,
            "output_format": {
                "type": "object",
                "fields": {
                    "recent_context": "string (最近章节的紧凑摘要)",
                    "foreshadow_to_consider": "string (伏笔如何融入本章的建议)",
                    "continuity_constraints": "array of strings (需要保持的连续性约束)",
                    "important_entities": "array of strings (重要实体列表)",
                },
            },
        },
        ensure_ascii=False,
    )

    response = await llm_client.chat(
        system_prompt=TRANSFER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=max_tokens,
        agent_id="pipeline_transfer",
        priority="critical",
        response_format={"type": "json_object"},
    )

    try:
        data = _parse_llm_output(response.content)
        return TransferContext(
            novel_id=novel_id,
            target_chapter=target_chapter,
            recent_context=data.get("recent_context", ""),
            foreshadow_to_consider=data.get("foreshadow_to_consider", ""),
            continuity_constraints=data.get("continuity_constraints", []),
            important_entities=data.get("important_entities", []),
            source_chapters=source_chapters,
        )
    except (json.JSONDecodeError, ValueError, KeyError, PipelineLLMError) as exc:
        raise PipelineLLMError(f"Failed to parse transfer output: {exc}") from exc


# ---------------------------------------------------------------------------
# Schema Generator LLM
# ---------------------------------------------------------------------------

SCHEMA_SYSTEM_PROMPT = """你是一个信息 Schema 生成器。根据小说的类型和设定，生成适合该小说的信息收集字段。
每个字段包含 key(英文标识), name(中文名称), description(描述)。
根据小说类型生成 4-8 个最相关的字段。
输出严格 JSON 格式。"""


async def generate_information_schema(
    novel_id: str,
    story_bible_summary: str,
    genre: str,
    chapter_synopses: list[str],
    *,
    max_tokens: int = 2048,
) -> list[InformationField]:
    """Auto-generate information schema based on story context.

    Returns list of InformationField.
    """
    user_prompt = json.dumps(
        {
            "task": "generate_information_schema",
            "genre": genre,
            "story_bible": story_bible_summary,
            "synopses": chapter_synopses,
            "output_format": {
                "type": "array",
                "items": {
                    "key": "string (英文标识, snake_case)",
                    "name": "string (中文名称)",
                    "description": "string (字段描述)",
                },
            },
        },
        ensure_ascii=False,
    )

    response = await llm_client.chat(
        system_prompt=SCHEMA_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.5,
        max_tokens=max_tokens,
        agent_id="pipeline_schema_generator",
        priority="critical",
        response_format={"type": "json_object"},
    )

    try:
        data = _parse_llm_output(response.content)
        if isinstance(data, dict):
            fields_data = data.get("fields", data.get("schema", []))
        elif isinstance(data, list):
            fields_data = data
        else:
            raise ValueError(f"Unexpected schema output type: {type(data)}")

        fields = []
        for i, item in enumerate(fields_data):
            fields.append(
                InformationField(
                    key=item.get("key", f"field_{i}"),
                    name=item.get("name", item.get("key", f"字段{i}")),
                    description=item.get("description", ""),
                    order=i,
                )
            )
        return fields
    except (json.JSONDecodeError, ValueError, KeyError, PipelineLLMError) as exc:
        raise PipelineLLMError(f"Failed to parse schema output: {exc}") from exc
