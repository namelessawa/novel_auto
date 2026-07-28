from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path

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
)
from story.section_budget import SectionBudgetPlanBuilder
from story.service import AuthorGenerationService
from story.writer import AuthorWriter
from story.writing_plan import SectionWritingPlan


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


def _provider_patch_text() -> str:
    return _payload()["provider_repair_output"]["patches"][0]["patch_text"]


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
        provider_set = ProviderRepairPatchSet(
            patches=[
                ProviderRepairPatch(
                    patch_id=patch_id or _expand_template(plan).patch_id,
                    patch_text=(
                        patch_text if patch_text is not None else _provider_patch_text()
                    ),
                )
            ]
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
    template = _expand_template(plan)

    assert template.patch_id
    assert template.patch_type == "expand"
    assert template.insertion_offset is not None
    assert template.target_chars == 344
    assert template.max_chars == 444
    assert template.preserve
    assert template.purpose
    assert template.original_narrative_sha256 == hashlib.sha256(
        original.encode("utf-8")
    ).hexdigest()
    assert template.contract_hash == contract.contract_hash
    assert template.provider_text_required is True


def test_changed_240_character_provider_anchor_cannot_break_template_apply() -> None:
    original, _, contract, event_plan, plan = _context()
    raw_patch = _payload()["provider_repair_output"]["patches"][0]
    content = json.dumps(
        {
            "schema_version": 1,
            "patches": [
                {
                    "patch_id": _expand_template(plan).patch_id,
                    "patch_text": raw_patch["patch_text"],
                    "anchor": raw_patch["anchor"],
                }
            ],
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
    response = ProviderRepairPatchSet(
        patches=[
            ProviderRepairPatch(
                patch_id=_expand_template(plan).patch_id,
                patch_text=_provider_patch_text(),
            )
        ]
    )

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
        patch_text="潮" * 445,
    )

    assert result.report.accepted is False
    assert {
        item.code for item in result.report.violations
    } & {"PATCH_TOO_LONG", "EXPAND_TOO_LARGE"}
    assert result.narrative_text == original


def test_default_planner_provider_path_remains_disabled() -> None:
    init_source = inspect.getsource(AuthorGenerationService.__init__)

    assert 'AUTHOR_LLM_PLANNER_EXPERIMENTAL", "0"' in init_source


def test_full_retry_provider_path_remains_absent() -> None:
    assert not hasattr(AuthorWriter, "retry")


def test_service_contains_only_one_repair_await() -> None:
    tree = ast.parse(inspect.getsource(AuthorGenerationService))
    repair_awaits = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "repair"
    ]

    assert len(repair_awaits) == 1


def test_900_1100_writer_budget_targets_safe_center() -> None:
    writing_plan = SectionWritingPlan(
        section_id="safe-center",
        requested_chars=1000,
        target_chars=1000,
        min_chars=900,
        max_chars=1100,
        hard_max_chars=1100,
        segment_budgets=[],
        stop_conditions=[],
        style_adaptation={
            "key": "literary",
            "instruction": "",
            "forbidden_expansion": [],
        },
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
