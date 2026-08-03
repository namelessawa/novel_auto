from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nf_core.provider_runtime import (
    ProviderError,
    ProviderRuntimeConfig,
    ProviderRuntimeReceipt,
)
from story.models import SectionGoal, WriterCandidate
from story.repair_patch import ProviderRepairPatchSet
from story.writer import AuthorWriter


def _response(
    content: str,
    *,
    prompt: int,
    completion: int,
    provider: str = "",
    model: str = "",
    source: str = "",
    fingerprint: str = "",
    thinking_mode: str = "disabled",
    sdk_retries: int = 0,
):
    return SimpleNamespace(
        content=content,
        usage_prompt_tokens=prompt,
        usage_completion_tokens=completion,
        usage_cached_tokens=0,
        provider=provider,
        model=model,
        provider_source=source,
        provider_config_fingerprint=fingerprint,
        provider_runtime_receipt=(
            ProviderRuntimeReceipt(
                provider=provider,
                model=model,
                thinking_mode=thinking_mode,
                max_retries=sdk_retries,
                source=source,
                config_fingerprint=fingerprint,
            )
            if fingerprint
            else None
        ),
    )


def _context():
    return SimpleNamespace(
        prompt="frozen context",
        section_budget_plan=None,
        writing_plan=None,
        chapter_plan=None,
        narrative_contract=None,
        event_execution_plan=None,
        slots={},
    )


def _budget():
    return SimpleNamespace(
        min_chars=900,
        target_chars=1030,
        max_chars=1100,
        segments=[
            SimpleNamespace(name="opening", budget=185, max_chars=235),
            SimpleNamespace(name="development", budget=309, max_chars=359),
            SimpleNamespace(name="conflict", budget=309, max_chars=359),
            SimpleNamespace(name="resolution", budget=227, max_chars=277),
        ],
        style_balance_contract=SimpleNamespace(
            instruction="use existing scene facts",
            limits=[],
            forbidden=[],
        ),
    )


def _candidate_json() -> str:
    return json.dumps(
        {
            "narrative_text": "修复后的正文保持原意。",
            "section_summary": "结构已修复。",
            "event_evidence": [],
            "end_state_evidence": [],
            "state_delta": [],
            "threads_opened": [],
            "threads_advanced": [],
            "threads_resolved": [],
            "memory_records": [],
            "consistency_notes": [],
            "chapter_evidence": [],
        },
        ensure_ascii=False,
    )


_BLOCK_NAMES = [
    "opening_1",
    "opening_2",
    "development_1",
    "development_2",
    "development_3",
    "conflict_1",
    "conflict_2",
    "conflict_3",
    "resolution_1",
    "resolution_2",
]

_CELL_COUNT_BY_PREFIX = {"o": 4, "d": 6, "c": 6, "r": 4}
_CELL_NAMES_BY_BLOCK = {
    name: [
        f"{name[0]}{name.rsplit('_', 1)[1]}u{cell_index}"
        for cell_index in range(1, _CELL_COUNT_BY_PREFIX[name[0]] + 1)
    ]
    for name in _BLOCK_NAMES
}
_CELL_NAMES = [
    cell_name
    for block_name in _BLOCK_NAMES
    for cell_name in _CELL_NAMES_BY_BLOCK[block_name]
]


def _narrative_blocks(lengths: list[int] | None = None) -> dict[str, str]:
    resolved_lengths = lengths or [90] * len(_BLOCK_NAMES)
    assert len(resolved_lengths) == len(_BLOCK_NAMES)
    glyphs = "潮风林石灯桥舟云雨光"
    return {
        name: glyph * length
        for name, glyph, length in zip(
            _BLOCK_NAMES,
            glyphs,
            resolved_lengths,
            strict=True,
        )
    }


def _narrative_cells(block_lengths: list[int] | None = None) -> dict[str, str]:
    resolved_lengths = block_lengths or [90] * len(_BLOCK_NAMES)
    assert len(resolved_lengths) == len(_BLOCK_NAMES)
    glyphs = "潮风林石灯桥舟云雨光"
    cells: dict[str, str] = {}
    for block_name, glyph, block_length in zip(
        _BLOCK_NAMES,
        glyphs,
        resolved_lengths,
        strict=True,
    ):
        names = _CELL_NAMES_BY_BLOCK[block_name]
        base, remainder = divmod(block_length, len(names))
        assert base >= 1
        for index, name in enumerate(names):
            cells[name] = glyph * (base + int(index < remainder))
    return cells


def _cell_candidate_json(block_lengths: list[int] | None = None) -> str:
    payload = json.loads(_candidate_json())
    payload.pop("narrative_text")
    payload["narrative_cells"] = _narrative_cells(block_lengths)
    return json.dumps(payload, ensure_ascii=False)


def _repair_cells(text: str) -> dict[str, str]:
    base, remainder = divmod(len(text), 3)
    lengths = [base + int(index < remainder) for index in range(3)]
    cursor = 0
    cells: dict[str, str] = {}
    for index, length in enumerate(lengths, start=1):
        cells[f"beat_{index}"] = text[cursor : cursor + length]
        cursor += length
    return cells


def test_writer_prompt_schema_uses_the_frozen_safe_length_zone() -> None:
    context = _context()
    context.section_budget_plan = _budget()

    schema = AuthorWriter._writer_output_schema(context)
    cells = schema["properties"]["narrative_cells"]
    properties = cells["properties"]

    assert "narrative_text" not in schema["properties"]
    assert "narrative_cells" in schema["required"]
    assert cells["required"] == _CELL_NAMES
    assert len(cells["required"]) == 52
    assert all(
        properties[name]["type"] == "string"
        and
        properties[name]["minLength"] == 1
        and "maxLength" not in properties[name]
        for name in _CELL_NAMES
    )
    expected_cell_targets = [
        [20, 20, 21, 21],
        [21, 21, 21, 21],
        [21, 21, 21, 21, 21, 21],
        [21, 21, 21, 21, 21, 21],
        [21, 21, 21, 21, 21, 21],
        [21, 21, 21, 21, 21, 21],
        [21, 21, 21, 21, 21, 21],
        [21, 21, 21, 21, 21, 21],
        [21, 21, 21, 21],
        [21, 21, 21, 21],
    ]
    for name, cell_targets in zip(
        _BLOCK_NAMES,
        expected_cell_targets,
        strict=True,
    ):
        block = cells["x-block-map"][name]
        assert block == {
            "cells": _CELL_NAMES_BY_BLOCK[name],
            "group": name.rsplit("_", 1)[0],
            "numeric_block_quota_exposed": False,
        }
        assert [
            properties[cell_name]["x-generation-steering"][
                "soft_target_nonwhitespace_chars"
            ]
            for cell_name in _CELL_NAMES_BY_BLOCK[name]
        ] == cell_targets
        for cell_name in _CELL_NAMES_BY_BLOCK[name]:
            assert properties[cell_name]["x-generation-steering"][
                "soft_sentence_count"
            ] == 1
    assert cells["x-aggregate-length-contract"] == {
        "count": "non-whitespace Unicode characters",
        "min": 900,
        "drafting_target": 1090,
        "max": 1100,
        "min_and_max_server_enforced": True,
        "drafting_target_server_enforced": False,
    }
    assert cells["x-provider-calibration"] == {
        "logical_cell_count": 52,
        "total_prose_leaf_count": 52,
        "soft_target_per_prose_cell_min": 20,
        "soft_target_per_prose_cell_max": 21,
        "additive_soft_target_sum": 1090,
        "calibration_targets_are_additive": True,
    }
    assert sum(
        properties[name]["x-generation-steering"][
            "soft_target_nonwhitespace_chars"
        ]
        for name in _CELL_NAMES
    ) == 1090
    assert "hard-validates 900-1100" in cells["description"]
    shape_prompt = AuthorWriter._writer_shape_prompt(context)
    assert "no separate numeric block quota is exposed" in shape_prompt
    assert "soft range" not in shape_prompt
    assert "prose-cell sum is exactly 1090" in shape_prompt
    assert "Only r2u4 may write decisive action" in shape_prompt
    context.chapter_plan = SimpleNamespace(
        segments=[
            SimpleNamespace(
                order=index,
                purpose=f"purpose-{index}",
                target_chars=137 + index,
                events=[],
            )
            for index in range(1, 5)
        ],
        required_end_states=[],
        stop_condition=[],
    )
    provider_surface = "\n".join(
        [
            json.dumps(schema, ensure_ascii=False),
            shape_prompt,
            AuthorWriter._final_directive(context),
        ]
    )
    assert "1090" in provider_surface
    assert "1030" not in provider_surface
    assert "软长度参考" not in provider_surface


def test_provider_narrative_cells_join_verbatim_in_frozen_order() -> None:
    payload = json.loads(_candidate_json())
    payload.pop("narrative_text")
    payload["narrative_cells"] = {}
    for name in reversed(_CELL_NAMES):
        payload["narrative_cells"][name] = f"<{name}>。"

    candidate = AuthorWriter._parse(json.dumps(payload, ensure_ascii=False))

    assert candidate.narrative_text == "\n\n".join(
        "".join(f"<{name}>。" for name in _CELL_NAMES_BY_BLOCK[block_name])
        for block_name in _BLOCK_NAMES
    )
    assert "narrative_cells" not in candidate.model_dump(mode="json")


def test_provider_narrative_cells_reject_ambiguous_or_incomplete_shape() -> None:
    payload = json.loads(_candidate_json())
    payload["narrative_cells"] = _narrative_cells()
    with pytest.raises(Exception, match="ambiguous"):
        AuthorWriter._parse(json.dumps(payload, ensure_ascii=False))

    payload.pop("narrative_text")
    payload["narrative_cells"].pop("c2u2")
    with pytest.raises(Exception, match="frozen shape"):
        AuthorWriter._parse(json.dumps(payload, ensure_ascii=False))

    payload["narrative_cells"] = _narrative_cells()
    payload["narrative_cells"]["c2u2"] = " \n\t "
    with pytest.raises(Exception, match="frozen shape"):
        AuthorWriter._parse(json.dumps(payload, ensure_ascii=False))

    payload["narrative_cells"] = _narrative_cells()
    payload["narrative_cells"]["c2u2"] = {
        "sentence_1": "错误对象。",
        "sentence_2": "错误对象。",
    }
    with pytest.raises(Exception, match="frozen shape"):
        AuthorWriter._parse(json.dumps(payload, ensure_ascii=False))

    payload["narrative_cells"] = _narrative_cells()
    payload["narrative_cells"]["c2u2"] = ["错误数组。"]
    with pytest.raises(Exception, match="frozen shape"):
        AuthorWriter._parse(json.dumps(payload, ensure_ascii=False))

    payload["narrative_cells"] = _narrative_cells()
    payload["narrative_cells"]["extra"] = "越权单元。"
    with pytest.raises(Exception, match="frozen shape"):
        AuthorWriter._parse(json.dumps(payload, ensure_ascii=False))


def test_primary_block_contract_uses_only_joined_aggregate_length() -> None:
    context = _context()
    context.section_budget_plan = _budget()
    payload = json.loads(_candidate_json())
    payload.pop("narrative_text")
    payload["narrative_cells"] = _narrative_cells(
        [4, 176, 90, 90, 90, 90, 90, 90, 90, 90]
    )

    passed, codes = AuthorWriter._writer_primary_contract(
        json.dumps(payload, ensure_ascii=False),
        context,
    )
    assert passed is True
    assert codes == []

    legacy_passed, legacy_codes = AuthorWriter._writer_primary_contract(
        _candidate_json(),
        context,
    )
    assert legacy_passed is False
    assert legacy_codes == ["WRITER_BLOCKS_MISSING"]

    payload["narrative_cells"] = _narrative_cells([89] * 10)
    short_passed, short_codes = AuthorWriter._writer_primary_contract(
        json.dumps(payload, ensure_ascii=False),
        context,
    )
    assert short_passed is False
    assert short_codes == ["WRITER_BLOCK_TOTAL_OUT_OF_RANGE"]

    payload["narrative_cells"] = _narrative_cells([111] * 10)
    long_passed, long_codes = AuthorWriter._writer_primary_contract(
        json.dumps(payload, ensure_ascii=False),
        context,
    )
    assert long_passed is False
    assert long_codes == ["WRITER_BLOCK_TOTAL_OUT_OF_RANGE"]

    payload["narrative_cells"] = {
        name: value + " " * 20
        for name, value in _narrative_cells([89] * 10).items()
    }
    whitespace_passed, whitespace_codes = AuthorWriter._writer_primary_contract(
        json.dumps(payload, ensure_ascii=False),
        context,
    )
    assert whitespace_passed is False
    assert whitespace_codes == ["WRITER_BLOCK_TOTAL_OUT_OF_RANGE"]


@pytest.mark.asyncio
async def test_writer_result_records_prose_free_cell_diagnostics(monkeypatch) -> None:
    payload = json.loads(_candidate_json())
    payload.pop("narrative_text")
    payload["narrative_cells"] = _narrative_cells([90] * 10)
    for name in _CELL_NAMES:
        payload["narrative_cells"][name] += "。"
    response = json.dumps(payload, ensure_ascii=False)
    chat = AsyncMock(return_value=_response(response, prompt=12, completion=40))
    monkeypatch.setattr("story.writer.llm_client.chat", chat)
    context = _context()
    context.section_budget_plan = _budget()

    result = await AuthorWriter().generate(
        context,
        SectionGoal(objective="完成既定事件", desired_length=900),
    )

    assert result.primary_output_contract_pass is True
    assert result.writer_block_nonspace_lengths == [94, 94, 96, 96, 96, 96, 96, 96, 94, 94]
    assert len(result.writer_cell_nonspace_lengths) == 52
    assert sum(result.writer_cell_nonspace_lengths) == 952
    assert result.writer_cell_sentence_boundary_counts == [1] * 52


def test_repair_prompt_schema_uses_each_frozen_provider_template() -> None:
    plan = SimpleNamespace(
        patch_templates=[
                SimpleNamespace(
                    provider_text_required=True,
                    patch_id="expand-frozen",
                    min_chars=292,
                    target_chars=355,
                    max_chars=450,
            )
        ]
    )

    schema = AuthorWriter._repair_output_schema(plan)
    patches = schema["properties"]["patches"]
    item = patches["prefixItems"][0]

    assert patches["minItems"] == patches["maxItems"] == 1
    assert schema["required"] == ["schema_version", "patches"]
    assert schema["properties"]["schema_version"]["const"] == 1
    assert item["properties"]["patch_id"]["const"] == "expand-frozen"
    patch_text = item["properties"]["patch_text"]
    assert patch_text["required"] == ["beat_1", "beat_2", "beat_3"]
    assert patch_text["additionalProperties"] is False
    assert patch_text["x-joined-length-contract"] == {
        "count": "non-whitespace Unicode characters",
        "min": 292,
        "target": 355,
        "max": 450,
        "minimum_is_hard": True,
        "target_is_advisory": True,
        "maximum_is_hard": True,
    }
    assert [
        patch_text["properties"][name]["x-generation-steering"][
            "soft_target_nonwhitespace_chars"
        ]
        for name in patch_text["required"]
    ] == [119, 118, 118]
    assert all(
        patch_text["properties"][name]["minLength"] == 1
        and "maxLength" not in patch_text["properties"][name]
        and patch_text["properties"][name]["pattern"]
        == "^[^0-9零〇一二两三四五六七八九十百千万]*$"
        for name in patch_text["required"]
    )


def test_repair_cells_join_verbatim_in_frozen_order() -> None:
    plan = SimpleNamespace(
        patch_templates=[
            SimpleNamespace(
                provider_text_required=True,
                patch_id="expand-frozen",
            )
        ]
    )
    content = json.dumps(
        {
            "schema_version": 1,
            "patches": [
                {
                    "patch_id": "expand-frozen",
                    "patch_text": {
                        "beat_3": "收束。",
                        "beat_1": "动作。",
                        "beat_2": "感知。",
                    },
                }
            ],
        },
        ensure_ascii=False,
    )

    parsed = AuthorWriter._parse_provider_repair_patches(content, plan)

    assert parsed.patches[0].patch_text == "动作。感知。收束。"


@pytest.mark.parametrize(
    "patch_text",
    [
        {"beat_1": "动作。", "beat_2": "感知。"},
        {
            "beat_1": "动作。",
            "beat_2": "感知。",
            "beat_3": "收束。",
            "extra": "越权。",
        },
        {"beat_1": "动作。", "beat_2": 3, "beat_3": "收束。"},
        {"beat_1": "动作。", "beat_2": " \n\t ", "beat_3": "收束。"},
        "旧标量形状必须拒绝。",
    ],
)
def test_repair_cells_reject_nonexact_wire_shape(patch_text: object) -> None:
    plan = SimpleNamespace(
        patch_templates=[
            SimpleNamespace(
                provider_text_required=True,
                patch_id="expand-frozen",
            )
        ]
    )
    content = json.dumps(
        {
            "schema_version": 1,
            "patches": [
                {
                    "patch_id": "expand-frozen",
                    "patch_text": patch_text,
                }
            ],
        },
        ensure_ascii=False,
    )

    with pytest.raises(Exception, match="repair cells"):
        AuthorWriter._parse_provider_repair_patches(content, plan)


@pytest.mark.asyncio
async def test_format_only_recovery_reuses_dynamic_scalar_schema_and_contract(
    monkeypatch,
) -> None:
    recovered_content = _cell_candidate_json([90] * 10)
    malformed = "not-json"
    chat = AsyncMock(
        side_effect=[
            _response(malformed, prompt=10, completion=5),
            _response(recovered_content, prompt=8, completion=4),
        ]
    )
    monkeypatch.setattr("story.writer.llm_client.chat", chat)
    context = _context()
    context.section_budget_plan = _budget()

    result = await AuthorWriter().generate(
        context,
        SectionGoal(objective="完成既定事件", desired_length=900),
    )

    primary_system = chat.await_args_list[0].kwargs["system_prompt"]
    primary_user = chat.await_args_list[0].kwargs["user_prompt"]
    recovery_system = chat.await_args_list[1].kwargs["system_prompt"]
    assert '"narrative_cells"' in primary_system
    assert '"o1u1"' in primary_system
    assert "numeric_block_quota_exposed" in primary_system
    assert "soft range 88-99" not in primary_system
    assert "o1u1≈20, o1u2≈20, o1u3≈21, o1u4≈21" in primary_system
    assert "o2u1≈21, o2u2≈21, o2u3≈21, o2u4≈21" in primary_system
    assert "d1u1≈21, d1u2≈21, d1u3≈21" in primary_system
    assert "Every one of the fifty-two values must be a nonblank string" in primary_system
    assert chat.await_args_list[0].kwargs["temperature"] == 0.4
    assert primary_user.index("FINAL OUTPUT LOCK") < primary_user.index(
        "最终单元锁"
    )
    assert primary_user.endswith("立即停止。")
    assert '"narrative_cells"' in recovery_system
    assert '"sentence_1"' not in recovery_system
    assert '"narrative_text"' not in recovery_system
    assert '"minLength":1' in recovery_system
    assert all(
        call.kwargs["response_format"] == {"type": "json_object"}
        for call in chat.await_args_list
    )
    assert result.primary_output_contract_pass is False
    assert result.audit_codes == ["WRITER_FORMAT_RECOVERY_USED"]
    assert result.writer_block_nonspace_lengths == [90] * 10
    assert len(result.writer_cell_nonspace_lengths) == 52
    assert sum(result.writer_cell_nonspace_lengths) == 900


@pytest.mark.asyncio
async def test_format_only_recovery_rechecks_joined_aggregate_contract(
    monkeypatch,
) -> None:
    recovered_content = _cell_candidate_json([89] * 10)
    chat = AsyncMock(
        side_effect=[
            _response("not-json", prompt=10, completion=5),
            _response(recovered_content, prompt=8, completion=4),
        ]
    )
    monkeypatch.setattr("story.writer.llm_client.chat", chat)
    config = ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key="test-only",
        base_url="https://provider.invalid/v1",
        model="glm-5.2",
        thinking_mode="disabled",
        max_retries=0,
        source="provider_file",
    )
    monkeypatch.setattr("story.writer.resolve_provider_runtime", lambda: config)
    context = _context()
    context.section_budget_plan = _budget()

    with pytest.raises(ProviderError) as caught:
        await AuthorWriter().generate(
            context,
            SectionGoal(objective="完成既定事件", desired_length=900),
        )

    assert chat.await_count == 2
    assert caught.value.code == "PROVIDER_OUTPUT_INVALID"
    assert caught.value.provider_stage == "writer_json_repair"
    assert caught.value.provider_call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery", [False, True])
async def test_legacy_writer_envelope_cannot_bypass_live_shape_contract(
    monkeypatch,
    recovery: bool,
) -> None:
    responses = (
        [
            _response("not-json", prompt=10, completion=5),
            _response(_candidate_json(), prompt=8, completion=4),
        ]
        if recovery
        else [_response(_candidate_json(), prompt=10, completion=5)]
    )
    chat = AsyncMock(side_effect=responses)
    config = ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key="test-only",
        base_url="https://provider.invalid/v1",
        model="glm-5.2",
        thinking_mode="disabled",
        max_retries=0,
        source="provider_file",
    )
    monkeypatch.setattr("story.writer.llm_client.chat", chat)
    monkeypatch.setattr("story.writer.resolve_provider_runtime", lambda: config)
    context = _context()
    context.section_budget_plan = _budget()

    with pytest.raises(ProviderError) as caught:
        await AuthorWriter().generate(
            context,
            SectionGoal(objective="完成既定事件", desired_length=900),
        )

    assert chat.await_count == (2 if recovery else 1)
    assert caught.value.code == "PROVIDER_OUTPUT_INVALID"
    assert caught.value.provider_stage == (
        "writer_json_repair" if recovery else "writer"
    )
    assert caught.value.provider_call_count == (2 if recovery else 1)


@pytest.mark.asyncio
async def test_oversize_valid_patch_stays_on_the_hard_validator_path(
    monkeypatch,
) -> None:
    payload = {
        "provider_patch_requests": [
            {
                "patch_id": "expand-frozen",
                "target_chars": 355,
                "max_chars": 450,
            }
        ]
    }
    response = json.dumps(
        {
            "schema_version": 1,
            "patches": [
                {
                    "patch_id": "expand-frozen",
                    "patch_text": _repair_cells("潮" * 451),
                }
            ],
        },
        ensure_ascii=False,
    )
    chat = AsyncMock(return_value=_response(response, prompt=12, completion=8))
    monkeypatch.setattr("story.writer.llm_client.chat", chat)
    monkeypatch.setattr(
        "story.writer.repair_patch_prompt_payload",
        lambda _plan, _text: payload,
    )
    plan = SimpleNamespace(
        patch_templates=[
                SimpleNamespace(
                    provider_text_required=True,
                    patch_id="expand-frozen",
                    min_chars=292,
                    target_chars=355,
                    max_chars=450,
            )
        ]
    )

    result = await AuthorWriter().repair(
        AuthorWriter()._parse(_candidate_json()),
        plan,
    )

    assert chat.await_count == 1
    assert chat.await_args.kwargs["response_format"] == {"type": "json_object"}
    assert result.structured_output_repair_count == 0
    assert len(result.provider_repair_patches.patches[0].patch_text) == 451


def test_dynamic_schemas_do_not_mutate_pydantic_base_schemas() -> None:
    writer_base = WriterCandidate.model_json_schema()
    patch_base = ProviderRepairPatchSet.model_json_schema()
    context = _context()
    context.section_budget_plan = _budget()
    plan = SimpleNamespace(
        patch_templates=[
                SimpleNamespace(
                    provider_text_required=True,
                    patch_id="expand-frozen",
                    min_chars=292,
                    target_chars=355,
                    max_chars=450,
            )
        ]
    )

    AuthorWriter._writer_output_schema(context)
    AuthorWriter._repair_output_schema(plan)

    assert WriterCandidate.model_json_schema() == writer_base
    assert ProviderRepairPatchSet.model_json_schema() == patch_base


@pytest.mark.asyncio
async def test_invalid_writer_json_gets_one_format_only_repair(monkeypatch) -> None:
    malformed = '{"narrative_text":"修复后的正文保持原意。",'
    chat = AsyncMock(
        side_effect=[
            _response(
                malformed,
                prompt=100,
                completion=30,
                provider="custom",
                model="glm-5.2",
                source="provider_file",
                fingerprint="0123456789abcdef",
            ),
            _response(
                _candidate_json(),
                prompt=40,
                completion=35,
                provider="custom",
                model="glm-5.2",
                source="provider_file",
                fingerprint="fedcba9876543210",
            ),
        ]
    )
    monkeypatch.setattr("story.writer.llm_client.chat", chat)

    result = await AuthorWriter().generate(
        _context(),
        SectionGoal(objective="完成既定事件", desired_length=900),
    )

    assert chat.await_count == 2
    assert result.structured_output_repair_count == 1
    assert result.candidate.narrative_text == "修复后的正文保持原意。"
    assert result.usage["prompt_tokens"] == 140
    assert result.usage["completion_tokens"] == 65
    assert result.provider == "custom"
    assert result.provider_model == "glm-5.2"
    assert result.provider_source == "provider_file"
    assert result.provider_config_fingerprint == "fedcba9876543210"
    second = chat.await_args_list[1].kwargs
    assert second["agent_id"] == "author_writer_json_repair"
    assert second["temperature"] == 0.0
    assert all(
        call.kwargs["response_format"] == {"type": "json_object"}
        for call in chat.await_args_list
    )
    assert "frozen context" not in second["user_prompt"]
    assert json.loads(second["user_prompt"])["malformed_output"] == malformed


@pytest.mark.asyncio
async def test_second_invalid_json_fails_without_full_writer_retry(monkeypatch) -> None:
    chat = AsyncMock(
        side_effect=[
            _response("not-json", prompt=10, completion=2),
            _response(
                "still-not-json",
                prompt=8,
                completion=2,
                provider="custom",
                model="glm-5.2",
                source="provider_file",
                fingerprint="repair-call-fingerprint",
            ),
        ]
    )
    config = ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key="test-only",
        base_url="https://provider.invalid/v1",
        model="glm-5.2",
        thinking_mode="disabled",
        max_retries=0,
    )
    monkeypatch.setattr("story.writer.llm_client.chat", chat)
    monkeypatch.setattr("story.writer.resolve_provider_runtime", lambda: config)

    with pytest.raises(ProviderError) as caught:
        await AuthorWriter().generate(
            _context(),
            SectionGoal(objective="完成既定事件", desired_length=900),
        )

    assert chat.await_count == 2
    assert caught.value.code == "PROVIDER_OUTPUT_INVALID"
    assert caught.value.http_category == "output_invalid"
    assert caught.value.config.config_fingerprint == "repair-call-fingerprint"
    assert caught.value.config.source == "provider_file"
    assert caught.value.provider_stage == "writer_json_repair"
    assert caught.value.provider_primary_calls == 1
    assert caught.value.structured_output_repair_calls == 1
    assert caught.value.provider_call_count == 2
    assert "test-only" not in str(caught.value)
    assert "provider.invalid" not in str(caught.value)


@pytest.mark.asyncio
async def test_direct_writer_provider_failure_is_annotated(monkeypatch) -> None:
    config = ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key="test-only",
        base_url="https://provider.invalid/v1",
        model="glm-5.2",
        thinking_mode="disabled",
        max_retries=0,
        source="provider_file",
    )
    failure = ProviderError(
        code="PROVIDER_UNAVAILABLE",
        message="untrusted raw response",
        http_status=502,
        http_category="unavailable",
        config=config,
    )
    chat = AsyncMock(side_effect=failure)
    monkeypatch.setattr("story.writer.llm_client.chat", chat)

    with pytest.raises(ProviderError) as caught:
        await AuthorWriter().generate(
            _context(),
            SectionGoal(objective="完成既定事件", desired_length=900),
        )

    assert chat.await_count == 1
    assert caught.value.provider_stage == "writer"
    assert caught.value.provider_primary_calls == 1
    assert caught.value.structured_output_repair_calls == 0
    assert caught.value.provider_call_count == 1


@pytest.mark.asyncio
async def test_planner_transport_and_invalid_output_have_one_call_telemetry(
    monkeypatch,
) -> None:
    config = ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key="test-only",
        base_url="https://provider.invalid/v1",
        model="glm-5.2",
        thinking_mode="disabled",
        max_retries=0,
        source="provider_file",
    )
    transport = ProviderError(
        code="PROVIDER_TIMEOUT",
        message="untrusted timeout body",
        http_status=504,
        http_category="timeout",
        config=config,
    )
    chat = AsyncMock(side_effect=transport)
    monkeypatch.setattr("story.writer.llm_client.chat", chat)
    writer = AuthorWriter()

    with pytest.raises(ProviderError) as caught_transport:
        await writer.plan(
            _context(),
            SectionGoal(objective="完成既定事件", desired_length=900),
        )

    assert caught_transport.value.provider_stage == "planner"
    assert caught_transport.value.provider_call_count == 1

    chat.reset_mock()
    chat.side_effect = None
    chat.return_value = _response(
        "not-json",
        prompt=10,
        completion=2,
        provider="custom",
        model="glm-5.2",
        source="provider_file",
        fingerprint="0123456789abcdef",
    )
    with pytest.raises(ProviderError) as caught_invalid:
        await writer.plan(
            _context(),
            SectionGoal(objective="完成既定事件", desired_length=900),
        )

    assert caught_invalid.value.code == "PROVIDER_OUTPUT_INVALID"
    assert caught_invalid.value.provider_stage == "planner"
    assert caught_invalid.value.provider_primary_calls == 1
    assert caught_invalid.value.structured_output_repair_calls == 0
    assert caught_invalid.value.provider_call_count == 1
    assert chat.await_args.kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_patch_json_repair_uses_the_repair_calls_runtime_receipt(
    monkeypatch,
) -> None:
    chat = AsyncMock(
        side_effect=[
            _response(
                "not-json",
                prompt=12,
                completion=3,
                provider="custom",
                model="glm-5.2",
                source="provider_file",
                fingerprint="first-patch-call",
            ),
            _response(
                json.dumps(
                    {
                        "schema_version": 1,
                        "patches": [
                            {
                                "patch_id": "expand-1",
                                "patch_text": _repair_cells("潮" * 30),
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                prompt=6,
                completion=4,
                provider="custom",
                model="glm-5.2",
                source="provider_file",
                fingerprint="patch-format-repair-call",
            ),
        ]
    )
    monkeypatch.setattr("story.writer.llm_client.chat", chat)
    monkeypatch.setattr(
        "story.writer.repair_patch_prompt_payload",
        lambda _plan, _text: {},
    )
    writer = AuthorWriter()

    plan = SimpleNamespace(
        patch_templates=[
            SimpleNamespace(
                provider_text_required=True,
                patch_id="expand-1",
                min_chars=1,
                target_chars=30,
                max_chars=80,
            )
        ]
    )
    result = await writer.repair(
        writer._parse(_candidate_json()),
        plan,
    )

    assert chat.await_count == 2
    assert all(
        call.kwargs["response_format"] == {"type": "json_object"}
        for call in chat.await_args_list
    )
    assert result.structured_output_repair_count == 1
    assert result.provider_config_fingerprint == "patch-format-repair-call"
    recovery_system = chat.await_args_list[1].kwargs["system_prompt"]
    assert '"beat_1"' in recovery_system
    assert '"x-joined-length-contract"' in recovery_system
    assert result.provider_repair_patches is not None
    assert result.provider_repair_patches.patches[0].patch_text == "潮" * 30


@pytest.mark.asyncio
async def test_valid_number_free_patch_uses_one_repair_call(monkeypatch) -> None:
    payload = {
        "provider_patch_requests": [
            {
                "patch_id": "expand-1",
                "patch_text_lexical_contract": {
                    "scope": "patch_text_only",
                    "allowed_number_tokens": [],
                    "forbidden_pattern": (
                        "[0-9零〇一二两三四五六七八九十百千万]"
                    ),
                    "self_check_before_return": True,
                },
            }
        ]
    }
    response = json.dumps(
        {
            "schema_version": 1,
            "patches": [
                {
                    "patch_id": "expand-1",
                    "patch_text": _repair_cells(
                        "海风贴着石墙缓慢移动，他们反复确认眼前动作。"
                    ),
                }
            ],
        },
        ensure_ascii=False,
    )
    chat = AsyncMock(return_value=_response(response, prompt=12, completion=8))
    monkeypatch.setattr("story.writer.llm_client.chat", chat)
    monkeypatch.setattr(
        "story.writer.repair_patch_prompt_payload",
        lambda _plan, _text: payload,
    )
    writer = AuthorWriter()

    result = await writer.repair(
        writer._parse(_candidate_json()),
        SimpleNamespace(
            patch_templates=[
                SimpleNamespace(
                    provider_text_required=True,
                    patch_id="expand-1",
                    min_chars=1,
                    target_chars=30,
                    max_chars=80,
                )
            ]
        ),
    )

    assert chat.await_count == 1
    assert result.structured_output_repair_count == 0
    assert result.provider_repair_patches is not None
    assert result.provider_repair_patches.patches[0].patch_id == "expand-1"
    sent = json.loads(chat.await_args.kwargs["user_prompt"])
    assert sent["provider_patch_requests"][0][
        "patch_text_lexical_contract"
    ]["scope"] == "patch_text_only"
