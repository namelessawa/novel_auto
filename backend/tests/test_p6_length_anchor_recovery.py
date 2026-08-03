from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from story.ending_validator import EndingCompletionValidator
from story.event_execution import EventExecutionPlan
from story.models import WriterCandidate
from story.narrative_contract import (
    NarrativeContract,
    narrative_char_count,
)
from story.narrative_validator import NarrativeContractValidator
from story.repair_patch import (
    ProviderRepairPatch,
    ProviderRepairPatchSet,
    RepairPatchValidator,
)
from story.repair_plan import (
    LengthAdjustment,
    RepairPlan,
    RepairPreserveSpan,
    build_server_patch_templates,
    repair_patch_prompt_payload,
)
from story.section_budget import SectionBudgetPlanBuilder
from story.service import AuthorGenerationService
from story.writer import AuthorWriter
from story.writing_plan import (
    SectionWritingPlan,
    StyleLengthContract,
    WritingPlanPart,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "p6_length_anchor_recovery_656.json"
)
FIXTURE_SHA256 = (
    "f31b74bab56a1ed90beba3fd5640d5cc60f50c5adfcbb38b540fcf576473df42"
)
ORIGINAL_SHA256 = (
    "a79b12089a5ad78ee2aba4ba41936a4f3f466940114ec8b423ec8849cae18d2e"
)


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _context(
    *,
    original_text: str | None = None,
) -> tuple[str, WriterCandidate, NarrativeContract, EventExecutionPlan, RepairPlan]:
    payload = _payload()
    candidate = WriterCandidate.model_validate(payload["original_candidate"])
    original = original_text if original_text is not None else candidate.narrative_text
    contract = NarrativeContract.model_validate(payload["narrative_contract"])
    event_plan = EventExecutionPlan.model_validate(payload["event_execution_plan"])
    plan = RepairPlan.model_validate(payload["repair_plan"])
    templates = build_server_patch_templates(
        plan=plan,
        original_narrative=original,
        contract_hash=contract.contract_hash,
    )
    plan = plan.model_copy(update={"patch_templates": templates})
    return original, candidate, contract, event_plan, plan


def _expand_template(plan: RepairPlan):
    return next(
        item for item in plan.patch_templates if item.patch_type == "expand"
    )


def _expand_templates(plan: RepairPlan):
    return [
        item for item in plan.patch_templates if item.patch_type == "expand"
    ]


def _provider_patch_text() -> str:
    return _payload()["provider_repair_output"]["patches"][0]["patch_text"]


def _provider_patch_set(
    plan: RepairPlan,
    *,
    first_patch_text: str | None = None,
) -> ProviderRepairPatchSet:
    templates = _expand_templates(plan)
    source = _provider_patch_text()
    quotient, remainder = divmod(len(source), len(templates))
    chunks: list[str] = []
    offset = 0
    for index in range(len(templates)):
        size = quotient + int(index < remainder)
        chunks.append(source[offset : offset + size])
        offset += size
    if first_patch_text is not None:
        chunks[0] = first_patch_text
    return ProviderRepairPatchSet(
        patches=[
            ProviderRepairPatch(
                patch_id=template.patch_id,
                patch_text=chunk,
            )
            for template, chunk in zip(templates, chunks, strict=True)
        ]
    )


def _apply(
    *,
    original: str,
    contract: NarrativeContract,
    event_plan: EventExecutionPlan,
    plan: RepairPlan,
    patch_id: str | None = None,
    patch_text: str | None = None,
    provider_set: ProviderRepairPatchSet | None = None,
):
    if provider_set is None:
        provider_set = (
            ProviderRepairPatchSet(
                patches=[
                    ProviderRepairPatch(
                        patch_id=patch_id,
                        patch_text=(patch_text or _provider_patch_text()),
                    )
                ]
            )
            if patch_id is not None
            else _provider_patch_set(
                plan,
                first_patch_text=patch_text,
            )
        )
    return RepairPatchValidator().validate_and_apply(
        original_text=original,
        patch_set=None,
        provider_patch_set=provider_set,
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )


def _synthetic_plan(
    text: str,
    *,
    preserve: list[RepairPreserveSpan],
) -> RepairPlan:
    current = narrative_char_count(text)
    plan = RepairPlan(
        transaction_id="synthetic-offset",
        original_contract_hash="synthetic-contract",
        length_adjustment=LengthAdjustment(
            current_chars=current,
            min_chars=current + 40,
            max_chars=current + 120,
            action="add",
            target_chars=80,
            desired_final_chars=current + 80,
        ),
        must_preserve_spans=preserve,
        repair_instruction="expand existing material only",
    )
    return plan.model_copy(
        update={
            "patch_templates": build_server_patch_templates(
                plan=plan,
                original_narrative=text,
                contract_hash=plan.original_contract_hash,
            )
        }
    )


def _length_only_plan(
    text: str,
    *,
    contract_hash: str = "length-only-contract",
) -> RepairPlan:
    current = narrative_char_count(text)
    plan = RepairPlan(
        transaction_id=f"length-only-{current}",
        original_contract_hash=contract_hash,
        length_adjustment=LengthAdjustment(
            current_chars=current,
            min_chars=900,
            max_chars=1100,
            action="add",
            target_chars=max(0, 1030 - current),
            desired_final_chars=1030,
            max_add_chars=max(0, 1100 - current),
        ),
        repair_instruction="expand existing material only",
    )
    return plan.model_copy(
        update={
            "patch_templates": build_server_patch_templates(
                plan=plan,
                original_narrative=text,
                contract_hash=contract_hash,
            )
        }
    )


def test_frozen_656_character_failure_fixture_is_new_and_sanitized() -> None:
    fixture_bytes = FIXTURE.read_bytes()
    payload = json.loads(fixture_bytes.decode("utf-8"))
    narrative = payload["original_candidate"]["narrative_text"]

    assert hashlib.sha256(fixture_bytes).hexdigest() == FIXTURE_SHA256
    assert len(narrative) == narrative_char_count(narrative) == 656
    assert hashlib.sha256(narrative.encode("utf-8")).hexdigest() == ORIGINAL_SHA256
    assert payload["source_transaction_sha256"] == (
        "b7e9ebbfb0b2d8c14ed5212ba67e801325038c379a86c24224a922cd65bd4792"
    )
    raw = fixture_bytes.decode("utf-8").lower()
    assert "api_key" not in raw
    assert "http://" not in raw and "https://" not in raw
    assert ":\\" not in raw


def test_server_template_owns_every_security_sensitive_field() -> None:
    original, _, contract, _, plan = _context()
    templates = _expand_templates(plan)
    template = templates[0]

    assert template.patch_id
    assert template.patch_type == "expand"
    assert template.insertion_offset is not None
    assert len({item.patch_id for item in templates}) == len(templates) == 1
    assert [item.min_chars for item in templates] == [244]
    assert [item.target_chars for item in templates] == [324]
    assert [item.max_chars for item in templates] == [444]
    assert sum(item.min_chars for item in templates) == 244
    assert sum(item.target_chars for item in templates) == 324
    assert sum(item.max_chars for item in templates) == 444
    assert template.preserve
    assert template.purpose
    assert template.original_narrative_sha256 == hashlib.sha256(
        original.encode("utf-8")
    ).hexdigest()
    assert template.contract_hash == contract.contract_hash
    assert template.provider_text_required is True


@pytest.mark.parametrize(
    ("current", "expected_minima", "expected_targets", "expected_maxima"),
    [
        (288, [306, 306], [356, 356], [406, 406]),
        (395, [253, 252], [303, 302], [353, 352]),
        (432, [234, 234], [284, 284], [334, 334]),
        (543, [179, 178], [229, 228], [279, 278]),
        (608, [292], [371], [450]),
    ],
)
def test_failed_attempt_repair_budget_centers_inside_frozen_aggregate_ceiling(
    current: int,
    expected_minima: list[int],
    expected_targets: list[int],
    expected_maxima: list[int],
) -> None:
    text = "潮" * current
    plan = _length_only_plan(text)
    templates = _expand_templates(plan)

    required = 900 - current
    requested = 1030 - current
    count = (requested + 449) // 450
    authorized_max = min(1100 - current, 450 * count)
    centered = min(requested, (required + authorized_max) // 2)

    assert [item.min_chars for item in templates] == expected_minima
    assert [item.target_chars for item in templates] == expected_targets
    assert [item.max_chars for item in templates] == expected_maxima
    assert sum(expected_targets) == max(required, centered)
    assert sum(expected_minima) == required
    assert sum(expected_maxima) == authorized_max
    assert all(
        1 <= item.min_chars <= item.target_chars <= item.max_chars <= 450
        for item in templates
    )


def test_repair_budget_arithmetic_is_feasible_across_failed_length_band() -> None:
    for current in [288, 395, *range(432, 609)]:
        templates = _expand_templates(_length_only_plan("潮" * current))
        required = 900 - current
        final_headroom = 1100 - current

        assert templates
        assert len(templates) <= 8
        assert sum(item.min_chars for item in templates) >= required
        assert required <= sum(item.max_chars for item in templates)
        assert sum(item.max_chars for item in templates) <= final_headroom
        assert all(
            1 <= item.min_chars <= item.target_chars <= item.max_chars <= 450
            for item in templates
        )


def test_one_character_advisory_request_keeps_positive_template_target() -> None:
    text = "潮" * 900
    plan = RepairPlan(
        transaction_id="one-character-request",
        original_contract_hash="one-character-contract",
        length_adjustment=LengthAdjustment(
            current_chars=900,
            min_chars=900,
            max_chars=901,
            action="add",
            target_chars=1,
            desired_final_chars=901,
            max_add_chars=1,
        ),
        repair_instruction="expand existing material only",
    )

    templates = build_server_patch_templates(
        plan=plan,
        original_narrative=text,
        contract_hash=plan.original_contract_hash,
    )

    assert [item.min_chars for item in templates] == [1]
    assert [item.target_chars for item in templates] == [1]
    assert [item.max_chars for item in templates] == [1]


def test_repair_arithmetic_rejects_stale_original_length_telemetry() -> None:
    text = "潮" * 608
    stale = RepairPlan(
        transaction_id="stale-length-telemetry",
        original_contract_hash="stale-length-contract",
        length_adjustment=LengthAdjustment(
            current_chars=395,
            min_chars=900,
            max_chars=1100,
            action="add",
            target_chars=635,
            desired_final_chars=1030,
            max_add_chars=705,
        ),
        repair_instruction="expand existing material only",
    )

    with pytest.raises(
        ValueError,
        match="current_chars does not match original narrative",
    ):
        build_server_patch_templates(
            plan=stale,
            original_narrative=text,
            contract_hash=stale.original_contract_hash,
        )


def test_prompt_and_schema_freeze_cap_sum_not_raw_final_headroom() -> None:
    original = "潮" * 608
    plan = _length_only_plan(original)

    payload = repair_patch_prompt_payload(plan, original)
    schema = AuthorWriter._repair_output_schema(plan)

    assert payload["aggregate_patch_text_budget"]["max_chars"] == 450
    assert 1100 - narrative_char_count(original) == 492
    assert [
        item["properties"]["patch_text"]["x-joined-length-contract"]["max"]
        for item in schema["properties"]["patches"]["prefixItems"]
    ] == [450]


def test_prompt_rejects_preloaded_template_maxima_above_final_headroom() -> None:
    original = "潮" * 608
    plan = _length_only_plan(original)
    first = _expand_template(plan)
    unsafe_second = first.model_copy(
        update={"patch_id": f"{first.patch_id}-unsafe-sibling"}
    )
    unsafe = plan.model_copy(
        update={"patch_templates": [first, unsafe_second]}
    )

    with pytest.raises(
        ValueError,
        match="maxima exceed frozen final headroom",
    ):
        repair_patch_prompt_payload(unsafe, original)


def test_deterministic_delete_that_opens_length_gap_authorizes_frozen_expand() -> None:
    _, _, contract, event_plan, _ = _context()
    unsupported = "错" * 100
    original = "潮" * 400 + unsupported + "风" * 450
    plan = RepairPlan(
        transaction_id="delete-opens-length-gap",
        original_contract_hash=contract.contract_hash,
        unsupported_additions=[
            {
                "code": "UNSUPPORTED_ADDITION",
                "evidence": unsupported,
                "message": "remove frozen unsupported span",
            }
        ],
        length_adjustment=LengthAdjustment(
            current_chars=950,
            min_chars=900,
            max_chars=1100,
            action="none",
            desired_final_chars=980,
        ),
        repair_instruction="remove unsupported material and restore length",
    )
    plan = plan.model_copy(
        update={
            "patch_templates": build_server_patch_templates(
                plan=plan,
                original_narrative=original,
                contract_hash=contract.contract_hash,
            )
        }
    )
    delete_template = next(
        item for item in plan.patch_templates if item.patch_type == "delete"
    )
    expand_template = _expand_template(plan)

    assert delete_template.server_patch_text == ""
    assert expand_template.target_chars == 130
    assert expand_template.max_chars == 250

    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=ProviderRepairPatchSet(
            patches=[
                ProviderRepairPatch(
                    patch_id=expand_template.patch_id,
                    patch_text="雾" * 130,
                )
            ]
        ),
    )
    codes = {item.code for item in result.report.violations}

    assert result.report.accepted is True
    assert narrative_char_count(result.narrative_text) == 980
    assert "EXPAND_NOT_AUTHORIZED" not in codes


def test_repair_prompt_freezes_aggregate_bounds_and_advisory_targets() -> None:
    original, _, _, _, plan = _context()

    payload = repair_patch_prompt_payload(plan, original)
    requests = payload["provider_patch_requests"]
    aggregate = payload["aggregate_patch_text_budget"]

    assert len(requests) == 1
    assert requests[0]["min_chars"] == 244
    assert requests[0]["target_chars"] == 324
    assert requests[0]["max_chars"] == 444
    assert requests[0]["minimum_is_hard"] is True
    assert requests[0]["target_is_advisory"] is True
    assert requests[0]["maximum_is_hard"] is True
    assert requests[0]["drafting_requirement"] == "mandatory"
    assert requests[0]["patch_text_shape"] == "required_object_cells"
    assert requests[0]["cell_names"] == ["beat_1", "beat_2", "beat_3"]
    assert requests[0]["cell_count"] == 3
    assert requests[0]["cell_target_chars"] == [108, 108, 108]
    assert requests[0]["cell_targets_are_advisory"] is True
    assert requests[0]["punctuation_included"] is True
    assert aggregate == {
        "count_non_whitespace_unicode_characters": True,
        "min_chars": 244,
        "target_chars": 324,
        "max_chars": 444,
        "minimum_is_hard": True,
        "target_is_advisory": True,
        "maximum_is_hard": True,
        "uneven_per_patch_allocation_allowed": True,
    }
    assert payload["minimum_style_constraints"] == []
    assert "uneven distribution is allowed only" in payload["final_instruction"]
    assert "one complete developed beat per cell" in payload["final_instruction"]
    schema = AuthorWriter._repair_output_schema(plan)
    patch_schema = schema["properties"]["patches"]["prefixItems"][0]
    assert patch_schema["properties"]["patch_text"][
        "x-joined-length-contract"
    ] == {
        "count": "non-whitespace Unicode characters",
        "min": 244,
        "target": 324,
        "max": 444,
        "minimum_is_hard": True,
        "target_is_advisory": True,
        "maximum_is_hard": True,
    }


def test_aggregate_expansion_can_land_exactly_on_final_floor() -> None:
    original, _, contract, event_plan, plan = _context()
    templates = _expand_templates(plan)
    required_total = (
        plan.length_adjustment.min_chars - narrative_char_count(original)
    )
    chunk_sizes = [required_total // len(templates)] * len(templates)
    for index in range(required_total % len(templates)):
        chunk_sizes[index] += 1
    provider_set = ProviderRepairPatchSet(
        patches=[
            ProviderRepairPatch(
                patch_id=template.patch_id,
                patch_text=("潮" if index % 2 == 0 else "风") * size,
            )
            for index, (template, size) in enumerate(
                zip(
                    templates,
                    chunk_sizes,
                    strict=True,
                )
            )
        ]
    )

    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=provider_set,
    )

    assert result.report.accepted is True
    assert narrative_char_count(result.narrative_text) == 900


def test_one_character_below_aggregate_floor_rejects_atomically() -> None:
    original, _, contract, event_plan, plan = _context()
    templates = _expand_templates(plan)
    required_total = (
        plan.length_adjustment.min_chars - narrative_char_count(original) - 1
    )
    chunk_sizes = [required_total // len(templates)] * len(templates)
    for index in range(required_total % len(templates)):
        chunk_sizes[index] += 1
    provider_set = ProviderRepairPatchSet(
        patches=[
            ProviderRepairPatch(
                patch_id=template.patch_id,
                patch_text=("潮" if index % 2 == 0 else "风") * size,
            )
            for index, (template, size) in enumerate(
                zip(
                    templates,
                    chunk_sizes,
                    strict=True,
                )
            )
        ]
    )

    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=provider_set,
    )

    assert result.report.accepted is False
    assert "EXPAND_TOO_SMALL" in {
        item.code for item in result.report.violations
    }
    assert "PATCH_FINAL_TOO_SHORT" in {
        item.code for item in result.report.violations
    }
    assert result.narrative_text == original


def test_attempt11_balanced_patch_minimums_reject_cross_patch_borrowing() -> None:
    _, _, contract, event_plan, _ = _context()
    original = "潮" * 288
    plan = _length_only_plan(
        original,
        contract_hash=contract.contract_hash,
    )
    first, second = _expand_templates(plan)

    assert [first.min_chars, second.min_chars] == [306, 306]
    assert [first.target_chars, second.target_chars] == [356, 356]
    assert [first.max_chars, second.max_chars] == [406, 406]
    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=ProviderRepairPatchSet(
            patches=[
                ProviderRepairPatch(
                    patch_id=first.patch_id,
                    patch_text="风" * 305,
                ),
                ProviderRepairPatch(
                    patch_id=second.patch_id,
                    patch_text="雾" * 307,
                ),
            ]
        ),
    )

    assert result.report.accepted is False
    assert "EXPAND_TOO_SMALL" in {
        item.code for item in result.report.violations
    }
    assert result.narrative_text == original

    accepted = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=ProviderRepairPatchSet(
            patches=[
                ProviderRepairPatch(
                    patch_id=first.patch_id,
                    patch_text="风" * 306,
                ),
                ProviderRepairPatch(
                    patch_id=second.patch_id,
                    patch_text="雾" * 306,
                ),
            ]
        ),
    )
    assert accepted.report.accepted is True
    assert narrative_char_count(accepted.narrative_text) == 900


@pytest.mark.parametrize(
    ("first_chars", "second_chars", "expected_final"),
    [
        (353, 282, 1030),
        (283, 352, 1030),
        (353, 352, 1100),
        (350, 255, 1000),
    ],
)
def test_uneven_patch_allocation_is_governed_by_aggregate_bounds(
    first_chars: int,
    second_chars: int,
    expected_final: int,
) -> None:
    _, _, contract, event_plan, _ = _context()
    original = "潮" * 395
    plan = _length_only_plan(
        original,
        contract_hash=contract.contract_hash,
    )
    first, second = _expand_templates(plan)
    provider_set = ProviderRepairPatchSet(
        patches=[
            ProviderRepairPatch(
                patch_id=first.patch_id,
                patch_text="风" * first_chars,
            ),
            ProviderRepairPatch(
                patch_id=second.patch_id,
                patch_text="雾" * second_chars,
            ),
        ]
    )

    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=provider_set,
    )

    assert result.report.accepted is True
    assert narrative_char_count(result.narrative_text) == expected_final


def test_one_character_above_frozen_patch_max_rejects_without_final_overflow() -> None:
    _, _, contract, event_plan, _ = _context()
    original = "潮" * 395
    plan = _length_only_plan(
        original,
        contract_hash=contract.contract_hash,
    )
    first, second = _expand_templates(plan)
    provider_set = ProviderRepairPatchSet(
        patches=[
            ProviderRepairPatch(
                patch_id=first.patch_id,
                patch_text="风" * (first.max_chars + 1),
            ),
            ProviderRepairPatch(
                patch_id=second.patch_id,
                patch_text="雾" * second.target_chars,
            ),
        ]
    )

    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=provider_set,
    )
    codes = {item.code for item in result.report.violations}

    assert result.report.accepted is False
    assert codes & {"PATCH_TOO_LONG", "EXPAND_TOO_LARGE"}
    assert "PATCH_FINAL_TOO_LONG" not in codes
    assert result.narrative_text == original


def test_changed_240_character_provider_anchor_cannot_break_template_apply() -> None:
    original, _, contract, event_plan, plan = _context()
    raw_patch = _payload()["provider_repair_output"]["patches"][0]
    returned = _provider_patch_set(plan).model_dump(mode="json")["patches"]
    returned[0]["anchor"] = raw_patch["anchor"]
    content = json.dumps(
        {
            "schema_version": 1,
            "patches": returned,
        },
        ensure_ascii=False,
    )
    provider_set = AuthorWriter._parse_provider_repair_patches(content)

    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=provider_set,
    )

    assert result.report.accepted is True
    assert "PATCH_ANCHOR_NOT_FOUND" not in {
        item.code for item in result.report.violations
    }
    assert "patches[0].anchor" in AuthorWriter._repair_ignored_fields(content)


def test_provider_response_needs_no_anchor() -> None:
    original, _, contract, event_plan, plan = _context()
    response = _provider_patch_set(plan)

    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=response,
    )

    assert result.report.accepted is True


def test_malicious_provider_patch_type_is_ignored_and_audited() -> None:
    _, _, _, _, plan = _context()
    content = json.dumps(
        {
            "schema_version": 1,
            "patches": [
                {
                    "patch_id": _expand_template(plan).patch_id,
                    "patch_text": _provider_patch_text(),
                    "patch_type": "delete",
                    "target_events": ["invented"],
                }
            ],
        },
        ensure_ascii=False,
    )

    parsed = AuthorWriter._parse_provider_repair_patches(content)

    assert parsed.patches[0].patch_text == _provider_patch_text()
    assert AuthorWriter._repair_ignored_fields(content) == [
        "patches[0].patch_type",
        "patches[0].target_events",
    ]


def test_unknown_provider_patch_id_is_rejected() -> None:
    original, _, contract, event_plan, plan = _context()
    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=ProviderRepairPatchSet(
            patches=[
                ProviderRepairPatch(
                    patch_id="unknown-patch",
                    patch_text=_provider_patch_text(),
                )
            ]
        ),
    )

    assert "PATCH_ID_UNKNOWN" in {
        item.code for item in result.report.violations
    }
    assert result.narrative_text == original


def test_duplicate_provider_patch_id_is_rejected() -> None:
    original, _, contract, event_plan, plan = _context()
    patch_id = _expand_template(plan).patch_id
    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=ProviderRepairPatchSet(
            patches=[
                ProviderRepairPatch(
                    patch_id=patch_id,
                    patch_text=_provider_patch_text(),
                ),
                ProviderRepairPatch(
                    patch_id=patch_id,
                    patch_text="潮气贴着石壁缓慢移动。",
                ),
            ]
        ),
    )

    assert "PATCH_ID_DUPLICATE" in {
        item.code for item in result.report.violations
    }
    assert result.narrative_text == original


def test_missing_required_provider_patch_id_is_rejected() -> None:
    original, _, contract, event_plan, plan = _context()
    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        provider_set=ProviderRepairPatchSet(),
    )

    assert "PATCH_ID_MISSING" in {
        item.code for item in result.report.violations
    }
    assert result.narrative_text == original


def test_original_trailing_whitespace_is_hash_and_offset_safe() -> None:
    original, _, contract, event_plan, plan = _context(
        original_text=_payload()["original_candidate"]["narrative_text"] + " \t  "
    )
    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
    )

    assert result.report.accepted is True
    assert result.narrative_text.endswith(" \t  ")


def test_crlf_and_lf_choose_the_same_semantic_insertion_paragraph() -> None:
    lf = "潮声贴着石壁。\n林秋接过旧信并收好。\n两人停在灯下。"
    crlf = lf.replace("\n", "\r\n")
    lf_plan = _synthetic_plan(
        lf,
        preserve=[
            RepairPreserveSpan(
                text="林秋接过旧信并收好。",
                reason="end state reached",
                state_id="end_1",
            )
        ],
    )
    crlf_plan = _synthetic_plan(
        crlf,
        preserve=[
            RepairPreserveSpan(
                text="林秋接过旧信并收好。",
                reason="end state reached",
                state_id="end_1",
            )
        ],
    )

    lf_template = _expand_template(lf_plan)
    crlf_template = _expand_template(crlf_plan)

    assert lf[lf_template.insertion_offset :] == "林秋接过旧信并收好。\n两人停在灯下。"
    assert crlf[crlf_template.insertion_offset :] == (
        "林秋接过旧信并收好。\r\n两人停在灯下。"
    )


def test_repeated_traditional_sentence_does_not_require_unique_anchor() -> None:
    text = "風聲停了。\n風聲停了。\n林秋收好舊信。"
    plan = _synthetic_plan(
        text,
        preserve=[
            RepairPreserveSpan(
                text="林秋收好舊信。",
                reason="end state reached",
                state_id="end_1",
            )
        ],
    )
    template = _expand_template(plan)

    assert text.count("風聲停了。") == 2
    assert template.exact_anchor == ""
    assert template.insertion_offset == text.index("林秋收好舊信。")


def test_end_state_in_last_paragraph_forces_expand_before_it() -> None:
    text = "潮气落在石阶。\n沈砚把信递出。\n林秋接过旧信并收好。"
    evidence = "林秋接过旧信并收好。"
    plan = _synthetic_plan(
        text,
        preserve=[
            RepairPreserveSpan(
                text=evidence,
                reason="end state reached",
                state_id="end_1",
            )
        ],
    )

    assert _expand_template(plan).insertion_offset == text.index(evidence)


def test_expand_offset_never_splits_preserved_evidence() -> None:
    original, _, _, _, plan = _context()
    template = _expand_template(plan)

    for preserved in plan.must_preserve_spans:
        if not preserved.text:
            continue
        start = original.index(preserved.text)
        end = start + len(preserved.text)
        assert not start < template.insertion_offset < end


def test_frozen_656_text_recovers_into_accepted_length_range() -> None:
    original, _, contract, event_plan, plan = _context()
    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
    )

    assert result.report.accepted is True
    assert 900 <= narrative_char_count(result.narrative_text) <= 1100


def test_frozen_event_and_end_state_still_pass_after_expand() -> None:
    original, _, contract, event_plan, plan = _context()
    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
    )
    report = NarrativeContractValidator().validate(
        contract,
        result.narrative_text,
        event_execution_plan=event_plan,
    )

    assert all(item.status == "completed" for item in report.event_results)
    assert all(item.reached for item in report.end_state_results)
    assert {
        item.code for item in report.violations
    } <= {"NARRATIVE_TOO_SHORT"}


def test_expand_changes_only_narrative_not_state_thread_or_memory() -> None:
    original, candidate, contract, event_plan, plan = _context()
    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
    )
    repaired = candidate.model_copy(
        update={"narrative_text": result.narrative_text}
    )

    for field in (
        "state_delta",
        "threads_opened",
        "threads_advanced",
        "threads_resolved",
        "memory_records",
        "section_summary",
        "title",
        "consistency_notes",
    ):
        assert getattr(repaired, field) == getattr(candidate, field)


def test_expand_before_terminal_state_has_no_post_resolution_expansion() -> None:
    original, _, contract, event_plan, plan = _context()
    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
    )
    narrative = NarrativeContractValidator().validate(
        contract,
        result.narrative_text,
        event_execution_plan=event_plan,
    )
    ending = EndingCompletionValidator().validate(
        narrative_text=result.narrative_text,
        contract=contract,
        narrative_report=narrative,
        phase="repaired",
    )

    assert ending.accepted is True
    assert ending.violation_code != "POST_RESOLUTION_EXPANSION"


def test_original_hash_mismatch_rejects_offset_application() -> None:
    original, _, contract, event_plan, plan = _context()
    changed = "改" + original[1:]
    result = _apply(
        original=changed,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
    )

    assert "ORIGINAL_NARRATIVE_HASH_MISMATCH" in {
        item.code for item in result.report.violations
    }
    assert result.narrative_text == changed


def test_provider_cannot_expand_frozen_text_beyond_1100() -> None:
    original, _, contract, event_plan, plan = _context()
    result = _apply(
        original=original,
        contract=contract,
        event_plan=event_plan,
        plan=plan,
        patch_text="潮" * 601,
    )

    assert result.report.accepted is False
    assert {
        item.code for item in result.report.violations
    } & {"PATCH_TOO_LONG", "EXPAND_TOO_LARGE"}
    assert result.narrative_text == original


def test_default_planner_provider_path_remains_disabled() -> None:
    init_source = inspect.getsource(AuthorGenerationService.__init__)

    assert (
        'env_bool("AUTHOR_LLM_PLANNER_EXPERIMENTAL", default=False)'
        in init_source
    )


def test_full_retry_provider_path_remains_absent() -> None:
    assert not hasattr(AuthorWriter, "retry")


def test_service_contains_only_one_repair_await() -> None:
    run_source = inspect.getsource(AuthorGenerationService.run)

    assert run_source.count("await self.repair(") == 1


def test_900_1100_writer_budget_targets_safe_center() -> None:
    writing_plan = SectionWritingPlan(
        section_id="safe-center",
        target_chars=1000,
        min_chars=900,
        max_chars=1100,
        structure=[
            WritingPlanPart(
                part="opening",
                target_chars=200,
                purpose="open",
            ),
            WritingPlanPart(
                part="development",
                target_chars=280,
                purpose="develop",
            ),
            WritingPlanPart(
                part="conflict",
                target_chars=280,
                purpose="conflict",
            ),
            WritingPlanPart(
                part="resolution",
                target_chars=240,
                purpose="resolve",
            ),
        ],
        style_adaptation=StyleLengthContract(
            key="literary",
            instruction="existing material only",
        ),
    )

    budget = SectionBudgetPlanBuilder().build(
        writing_plan=writing_plan,
        style_contract={"key": "literary"},
    )

    assert budget.target_chars == 1030
    assert 1030 <= budget.target_chars <= 1050


def test_provider_repair_schema_exposes_only_patch_id_and_patch_text() -> None:
    schema = ProviderRepairPatch.model_json_schema()

    assert set(schema["properties"]) == {"patch_id", "patch_text"}
    assert set(schema["required"]) == {"patch_id", "patch_text"}
