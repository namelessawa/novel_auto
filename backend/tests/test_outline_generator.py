from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from story.models import StoryBible
from story.outline_generator import (
    OutlineGenerationError,
    WholeBookOutlineGenerator,
)
from story.production_models import NovelProductionSpec


def _spec() -> NovelProductionSpec:
    return NovelProductionSpec(
        title="潮汐之城",
        premise="城市以遗忘换取潮汐平静。",
        theme="记忆与责任",
        target_total_chars=1_000,
        volume_count=1,
        chapter_count=2,
        target_chapter_chars=500,
        accepted_chapter_min_chars=400,
        accepted_chapter_max_chars=600,
        section_target_chars=250,
    )


def _valid_payload() -> dict:
    return {
        "logline": "守潮人发现平静以记忆为代价。",
        "global_arc": "发现代价，追查来源，公开真相。",
        "volumes": [
            {
                "id": "volume_001",
                "ordinal": 1,
                "title": "失潮",
                "objective": "确认遗忘机制",
                "opening_state": "潮汐稳定",
                "closing_state": "真相公开",
                "target_chapters": 2,
                "target_chars": 1_000,
            }
        ],
        "chapters": [
            {
                "id": "chapter_0001",
                "ordinal": 1,
                "volume_id": "volume_001",
                "title": "退去的名字",
                "objective": "发现第一处记忆缺口",
                "target_chars": 500,
            },
            {
                "id": "chapter_0002",
                "ordinal": 2,
                "volume_id": "volume_001",
                "title": "归还潮声",
                "objective": "公开代价并承担后果",
                "target_chars": 500,
            },
        ],
        "ending_target": "城市保留真相并承担潮灾。",
        "major_turning_points": ["发现记忆账本", "公开交换机制"],
        "central_conflict_progression": ["怀疑", "求证", "承担"],
        "thread_schedule": {},
        "character_arc_schedule": {},
    }


@pytest.mark.asyncio
async def test_outline_generator_accepts_one_strict_valid_call(
    monkeypatch,
) -> None:
    calls: list[dict] = []

    async def fake_chat(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            content=json.dumps(_valid_payload(), ensure_ascii=False),
            usage_prompt_tokens=11,
            usage_completion_tokens=19,
        )

    monkeypatch.setattr(
        "story.outline_generator.llm_client.chat",
        fake_chat,
    )
    result = await WholeBookOutlineGenerator().generate(
        spec=_spec(),
        bible=StoryBible(
            title="潮汐之城",
            premise="城市以遗忘换取潮汐平静。",
            theme="记忆与责任",
            setting_summary="封闭海城。",
            immutable_world_rules=["交换不可逆"],
        ),
    )

    assert result.provider_calls == 1
    assert result.repair_performed is False
    assert result.proposal.chapters[1].ordinal == 2
    assert result.usage["total_tokens"] == 30
    assert len(calls) == 1
    assert calls[0]["agent_id"] == "whole_book_outline"
    assert calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_outline_generator_allows_exactly_one_structured_repair(
    monkeypatch,
) -> None:
    invalid = _valid_payload()
    invalid["chapters"][1]["ordinal"] = 3
    responses = [
        json.dumps(invalid, ensure_ascii=False),
        json.dumps(_valid_payload(), ensure_ascii=False),
    ]
    calls: list[dict] = []

    async def fake_chat(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            content=responses.pop(0),
            usage_prompt_tokens=1,
            usage_completion_tokens=2,
        )

    monkeypatch.setattr(
        "story.outline_generator.llm_client.chat",
        fake_chat,
    )
    result = await WholeBookOutlineGenerator().generate(
        spec=_spec(),
        bible=StoryBible(
            title="潮汐之城",
            premise="城市以遗忘换取潮汐平静。",
            theme="记忆与责任",
            setting_summary="封闭海城。",
            immutable_world_rules=["交换不可逆"],
        ),
    )

    assert result.provider_calls == 2
    assert result.repair_performed is True
    assert result.usage["total_tokens"] == 6
    assert [call["agent_id"] for call in calls] == [
        "whole_book_outline",
        "whole_book_outline_repair",
    ]
    assert all(
        call["response_format"] == {"type": "json_object"}
        for call in calls
    )
    assert "validation_errors" in calls[1]["user_prompt"]


@pytest.mark.asyncio
async def test_outline_generator_fails_closed_after_second_invalid_output(
    monkeypatch,
) -> None:
    calls = 0

    async def fake_chat(**_kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            content="not-json",
            usage_prompt_tokens=0,
            usage_completion_tokens=0,
        )

    monkeypatch.setattr(
        "story.outline_generator.llm_client.chat",
        fake_chat,
    )
    with pytest.raises(OutlineGenerationError) as caught:
        await WholeBookOutlineGenerator().generate(
            spec=_spec(),
            bible=StoryBible(
                title="潮汐之城",
                premise="城市以遗忘换取潮汐平静。",
                theme="记忆与责任",
                setting_summary="封闭海城。",
                immutable_world_rules=["交换不可逆"],
            ),
        )

    assert caught.value.code == "PROVIDER_OUTPUT_INVALID"
    assert calls == 2
