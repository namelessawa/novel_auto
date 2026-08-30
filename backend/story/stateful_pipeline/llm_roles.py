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

from nf_core.json_utils import parse_llm_json, strip_code_fence
from nf_core.llm_client import llm_client
from story.stateful_pipeline.models import (
    ChapterInformation,
    ForeshadowRecord,
    InformationField,
    InformationSchema,
    TransferContext,
)


class PipelineLLMError(RuntimeError):
    """Raised when a pipeline LLM role fails."""


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
) -> dict[str, list[dict[str, Any]]]:
    """Extract structured information from prose according to schema.

    Returns dict mapping field keys to lists of extracted items.
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

    response = await llm_client.chat(
        system_prompt=INFORMATION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,
        max_tokens=max_tokens,
        agent_id="pipeline_information_extractor",
        priority="critical",
        response_format={"type": "json_object"},
    )

    try:
        data = _parse_llm_output(response.content)
        if isinstance(data, dict):
            # Validate keys match schema
            allowed_keys = set(schema.field_keys)
            result = {}
            for key in allowed_keys:
                if key in data:
                    items = data[key]
                    if isinstance(items, list):
                        result[key] = items
                    else:
                        result[key] = [items]
                else:
                    result[key] = []
            return result
        raise ValueError(f"Unexpected information output type: {type(data)}")
    except (json.JSONDecodeError, ValueError, KeyError, PipelineLLMError) as exc:
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


async def integrate_memory(
    novel_id: str,
    chapter_number: int,
    information: ChapterInformation,
    schema: InformationSchema,
    *,
    max_tokens: int = 4096,
) -> list[dict[str, Any]]:
    """Transform structured information into memory documents.

    Returns list of {"content": "...", "metadata": {...}}
    """
    user_prompt = json.dumps(
        {
            "task": "integrate_memory",
            "chapter": chapter_number,
            "schema_revision": schema.revision,
            "information": information.data,
            "output_format": {
                "type": "array",
                "items": {
                    "content": "string (自然语言记忆描述)",
                    "metadata": {
                        "chapter": "int",
                        "field": "string (来源字段)",
                        "entities": "array of strings",
                    },
                },
            },
        },
        ensure_ascii=False,
    )

    response = await llm_client.chat(
        system_prompt=INTEGRATION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,
        max_tokens=max_tokens,
        agent_id="pipeline_integration",
        priority="critical",
        response_format={"type": "json_object"},
    )

    try:
        data = _parse_llm_output(response.content)
        if isinstance(data, dict):
            docs = data.get("documents", data.get("memories", []))
        elif isinstance(data, list):
            docs = data
        else:
            raise ValueError(f"Unexpected integration output type: {type(data)}")
        return docs
    except (json.JSONDecodeError, ValueError, KeyError, PipelineLLMError) as exc:
        raise PipelineLLMError(f"Failed to parse integration output: {exc}") from exc


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

    Returns TransferContext for the Novel LLM.
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
