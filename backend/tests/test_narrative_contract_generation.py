from __future__ import annotations

from pathlib import Path

import pytest

from sections.section_store import _clear_for_tests
from story.models import (
    SectionGoal,
    StateDeltaOperation,
    StoryBibleUpdate,
    ValidationReport,
    WriterCandidate,
)
from story.narrative_contract import (
    AllowedEntities,
    EntityReference,
    LengthConstraint,
    NarrativeContractInput,
    RequiredEndState,
    RequiredEvent,
)
from story.service import AuthorGenerationService, GenerationRejected
from story.writer import AuthorWriter, WriterResult


class ContractWriter:
    def __init__(self, first: WriterCandidate, repaired: WriterCandidate):
        self.first = first
        self.repaired = repaired
        self.generate_calls = 0
        self.repair_calls = 0
        self.repair_report = None

    async def generate(self, context, goal):
        self.generate_calls += 1
        assert "narrative_contract" in context.slots
        assert "subordinate_to_facts" in context.slots["narrative_contract"]
        assert "SERVER_ONLY_NEVER_EXPOSE" not in context.prompt
        return WriterResult(self.first, {"total_tokens": 10})

    async def repair(self, candidate, report):
        self.repair_calls += 1
        self.repair_report = report
        return WriterResult(self.repaired, {"repair_tokens": 5, "total_tokens": 5})


@pytest.fixture(autouse=True)
def clear_sections():
    _clear_for_tests()
    yield
    _clear_for_tests()


def _candidate(text: str) -> WriterCandidate:
    return WriterCandidate(
        narrative_text=text,
        title="交付",
        section_summary="沈砚完成交信。",
    )


def _goal() -> SectionGoal:
    return SectionGoal(
        objective="沈砚把信交给调查员。",
        viewpoint_character_id="shen",
        involved_characters=["shen", "lin"],
        desired_length=200,
        narrative_constraints=NarrativeContractInput(
            allowed_entities=AllowedEntities(
                characters=[
                    EntityReference(id="shen", name="沈砚"),
                    EntityReference(id="lin", name="林秋"),
                    EntityReference(id="investigator", name="调查员"),
                ]
            ),
            required_events=[
                RequiredEvent(
                    id="handover",
                    actor="shen",
                    action="交信",
                    target="investigator",
                    evidence_patterns=[
                        r"沈砚把信交给调查员",
                        r"SERVER_ONLY_NEVER_EXPOSE",
                    ],
                )
            ],
            required_end_state=[
                RequiredEndState(
                    id="holder",
                    path="/items/letter/holder",
                    expected="investigator",
                    evidence_patterns=[r"调查员接过信"],
                    wrong_state_patterns=[r"林秋拿着信"],
                )
            ],
            length_constraint=LengthConstraint(min_chars=10, max_chars=300),
        ),
    )


def _service(tmp_path: Path, writer: ContractWriter, *, style_key: str = ""):
    service = AuthorGenerationService(
        user_id="contract",
        novel_id="contract_novel",
        data_dir=str(tmp_path),
        title="契约测试",
        writer=writer,
    )
    bible = service.bibles.load()
    service.bibles.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            premise="旧信必须交给调查员。",
            theme="诚实",
            setting_summary="灯塔内。",
            style_contract={"key": style_key} if style_key else {},
        )
    )
    return service


@pytest.mark.asyncio
async def test_repair_fixes_prose_and_both_validators_rerun(tmp_path: Path) -> None:
    writer = ContractWriter(
        _candidate("林秋拿着信，两人只讨论是否交出去。"),
        _candidate("沈砚把信交给调查员，调查员接过信，林秋关上空抽屉。"),
    )
    service = _service(tmp_path, writer)

    transaction = await service.run(_goal(), request_id="repair_success")

    assert transaction.committed is True
    assert transaction.writer_calls == 2
    assert transaction.repair_performed is True
    assert len(transaction.narrative_validation_history) == 2
    assert transaction.narrative_validation_history[0].accepted is False
    assert transaction.narrative_validation_history[1].accepted is True
    assert len(transaction.validation_history) == 2
    assert writer.repair_report.repair_context["missing_required_events"]
    assert writer.repair_report.repair_context["wrong_end_states"]
    assert service.sections.count() == 1


@pytest.mark.asyncio
async def test_repair_still_fails_and_transaction_never_commits(tmp_path: Path) -> None:
    bad = _candidate("林秋拿着信，两人只讨论是否交出去。")
    service = _service(tmp_path, ContractWriter(bad, bad))

    with pytest.raises(GenerationRejected) as exc:
        await service.run(_goal(), request_id="repair_reject")

    assert exc.value.transaction.phase == "rejected"
    assert exc.value.transaction.narrative_validation_report.accepted is False
    assert service.states.load().revision == 1
    assert service.sections.count() == 0


@pytest.mark.asyncio
async def test_style_rule_yields_to_fact_and_does_not_trigger_third_call(
    tmp_path: Path,
) -> None:
    prose = _candidate("沈砚把信交给调查员，调查员接过信。")
    writer = ContractWriter(prose, prose)
    service = _service(tmp_path, writer, style_key="hot_blooded")

    transaction = await service.run(_goal(), request_id="style_yields")

    assert transaction.committed is True
    assert transaction.narrative_validation_report.accepted is True
    assert transaction.writer_calls == 1
    assert transaction.style_validation_report["evaluated"] is True
    assert transaction.style_validation_report["passed"] is False
    assert "NarrativeContract > StoryBible / CanonicalState > StyleContract" in (
        AuthorWriter.SYSTEM_PROMPT
    )
    assert "允许少满足一项风格特征，不允许新增事实" in AuthorWriter.SYSTEM_PROMPT


def test_staging_rechecks_narrative_contract_and_refuses_bypass(tmp_path: Path) -> None:
    bad = _candidate("林秋拿着信，两人没有交信。")
    service = _service(tmp_path, ContractWriter(bad, bad))
    prepared = service.prepare(_goal(), request_id="stage_bypass")
    state_report = service.validate(prepared, bad)

    with pytest.raises(ValueError, match="cannot stage"):
        service._stage(prepared, prepared.transaction, bad, state_report)

    assert service.sections.count() == 0


def test_staging_rechecks_authority_report_and_refuses_forged_pass(
    tmp_path: Path,
) -> None:
    candidate = _candidate("沈砚把信交给调查员，调查员接过信。").model_copy(
        update={
            "state_delta": [
                StateDeltaOperation(
                    op="set",
                    path="/story_bible/theme",
                    value="被 Writer 改写",
                    evidence="沈砚把信交给调查员",
                )
            ]
        }
    )
    service = _service(tmp_path, ContractWriter(candidate, candidate))
    prepared = service.prepare(_goal(), request_id="stage_authority_bypass")

    with pytest.raises(ValueError, match="cannot stage"):
        service._stage(
            prepared,
            prepared.transaction,
            candidate,
            ValidationReport(accepted=True),
        )

    assert service.sections.count() == 0
