from __future__ import annotations

import hashlib

import pytest

from story.models import CanonicalState, SectionGoal, StoryBible
from story.narrative_contract import (
    AllowedEntities,
    EntityReference,
    ForbiddenOutcome,
    LengthConstraint,
    NarrativeContract,
    NarrativeContractBuilder,
    RequiredEndState,
    RequiredEvent,
    RequiredFact,
    TimeConstraint,
)
from story.narrative_validator import NarrativeContractValidator
from tests.narrative_contract_fixtures import (
    lighthouse_constraints,
    real_style_samples,
)


def _contract(**updates) -> NarrativeContract:
    payload = {
        "section_id": "s1",
        "story_bible_revision": 1,
        "canonical_state_revision": 1,
        "allowed_entities": AllowedEntities(
            characters=[
                EntityReference(id="shen", name="沈砚"),
                EntityReference(id="lin", name="林秋"),
                EntityReference(id="investigator", name="调查员", max_count=1),
            ]
        ),
        "required_facts": [],
        "required_events": [],
        "required_end_state": [],
        "time_constraints": [],
        "forbidden_outcomes": [],
        "length_constraint": LengthConstraint(min_chars=10, max_chars=2000),
    }
    payload.update(updates)
    return NarrativeContract(**payload)


def _codes(report) -> set[str]:
    return {item.code for item in report.violations}


def test_required_fact_and_event_missing() -> None:
    report = NarrativeContractValidator().validate(
        _contract(
            required_facts=[
                RequiredFact(
                    id="warning",
                    statement="港务处收到警告",
                    evidence_patterns=[r"港务处收到警告"],
                )
            ],
            required_events=[
                RequiredEvent(
                    id="handover",
                    actor="shen",
                    action="交信",
                    target="investigator",
                    evidence_patterns=[r"沈砚把信交给调查员"],
                )
            ],
        ),
        "沈砚站在门边，什么也没有做。",
    )
    assert report.accepted is False
    assert {"REQUIRED_FACT_MISSING", "REQUIRED_EVENT_MISSING"} <= _codes(report)
    assert report.missing_required_events == ["handover"]


def test_wrong_end_state_requires_completed_evidence() -> None:
    report = NarrativeContractValidator().validate(
        _contract(
            required_end_state=[
                RequiredEndState(
                    id="holder",
                    path="/items/letter/holder",
                    expected="investigator",
                    evidence_patterns=[r"调查员接过信"],
                    wrong_state_patterns=[r"林秋拿着信"],
                )
            ]
        ),
        "两人说应该交信。最后林秋拿着信，打开了门。",
    )
    assert "END_STATE_WRONG_HOLDER" in _codes(report)
    assert report.end_state_results[0].reached is False


def test_path_only_end_states_use_conservative_semantic_completion() -> None:
    contract = _contract(
        allowed_entities=AllowedEntities(
            characters=[EntityReference(id="lin", name="林秋")],
            items=[EntityReference(id="letter", name="旧信", aliases=["信纸"])],
        ),
        required_end_state=[
            RequiredEndState(
                id="holder",
                path="/items/letter/holder",
                expected="lin",
            ),
            RequiredEndState(
                id="action",
                path="/characters/lin/action",
                expected="亲手打开灯塔门",
            ),
            RequiredEndState(
                id="light",
                path="/world/lighthouse/light",
                expected="on",
            ),
        ],
    )
    prose = "林秋接过旧信并收好。林秋亲手打开灯塔门。塔灯重新亮起。"
    report = NarrativeContractValidator().validate(contract, prose)
    assert report.accepted is True
    assert report.required_end_state_coverage == 1.0


def test_unknown_character_kinship_casualty_date_and_injury() -> None:
    text = (
        "门外站着两个人。沈砚说父亲在港难前两日压下警告，三百条人命因此消失。"
        "他一拳砸向林秋，碎片割破虎口，血顺着手腕流下。"
    )
    report = NarrativeContractValidator().validate(_contract(), text)
    assert {
        "NARRATIVE_CHARACTER_ADDED",
        "UNSUPPORTED_KINSHIP_ADDED",
        "NARRATIVE_RELATION_ADDED",
        "UNSUPPORTED_CASUALTY_ADDED",
        "UNSUPPORTED_DATE_ADDED",
        "UNSUPPORTED_INJURY_ADDED",
    } <= _codes(report)


def test_unknown_named_character_is_rejected_but_known_alias_is_allowed() -> None:
    validator = NarrativeContractValidator()
    unknown = validator.validate(_contract(), "一个名叫周明的水手推门进来。")
    assert {"NARRATIVE_ENTITY_UNKNOWN", "NARRATIVE_CHARACTER_ADDED"} <= _codes(
        unknown
    )

    known_contract = _contract(
        allowed_entities=AllowedEntities(
            characters=[EntityReference(id="lin", name="林秋", aliases=["小秋"])]
        )
    )
    known = validator.validate(known_contract, "一个名叫小秋的人推门进来。")
    assert "NARRATIVE_ENTITY_UNKNOWN" not in _codes(known)


def test_time_constraint_mutated_and_causal_link_weakened() -> None:
    report = NarrativeContractValidator().validate(
        _contract(
            time_constraints=[
                TimeConstraint(
                    id="dawn",
                    description="天亮前交信，否则档案室拆除",
                    required_patterns=[r"天亮前"],
                    mutation_patterns=[r"下周拆"],
                    causal_patterns=[r"档案室.{0,10}拆.{0,10}线索断掉"],
                    weakened_patterns=[r"下周拆"],
                )
            ]
        ),
        "调查员说天亮前要答复，但档案室下周拆。",
    )
    assert {"TIME_CONSTRAINT_MUTATED", "CAUSAL_LINK_WEAKENED"} <= _codes(report)


def test_forbidden_outcome_mentioned_even_when_not_executed() -> None:
    report = NarrativeContractValidator().validate(
        _contract(
            forbidden_outcomes=[
                ForbiddenOutcome(
                    id="burn",
                    description="不得烧信",
                    patterns=[r"把信烧了"],
                )
            ]
        ),
        "沈砚道：你若要护他，我陪你把信烧了。林秋最终没有烧。",
    )
    assert "FORBIDDEN_OUTCOME_MENTIONED" in _codes(report)


def test_length_too_short_and_too_long_use_one_counter() -> None:
    validator = NarrativeContractValidator()
    contract = _contract(length_constraint=LengthConstraint(min_chars=10, max_chars=20))
    assert "NARRATIVE_TOO_SHORT" in _codes(validator.validate(contract, "短句。"))
    assert "NARRATIVE_TOO_LONG" in _codes(
        validator.validate(contract, "这是一段确定超过二十个非空白字符的正文内容用于测试。")
    )


def test_valid_contract_reports_full_coverage() -> None:
    contract = _contract(
        required_facts=[
            RequiredFact(id="f", statement="警告存在", evidence_patterns=[r"警告存在"])
        ],
        required_events=[
            RequiredEvent(id="e", actor="shen", action="交信", evidence_patterns=[r"沈砚交信"])
        ],
        required_end_state=[
            RequiredEndState(
                id="end", path="/items/letter/holder", expected="investigator",
                evidence_patterns=[r"调查员接过信"],
            )
        ],
    )
    report = NarrativeContractValidator().validate(
        contract,
        "警告存在。沈砚交信，调查员接过信，事件到此完成。",
    )
    assert report.accepted is True
    assert report.contract_coverage == 1.0
    assert report.required_event_coverage == 1.0


_REAL_SAMPLE_HASHES = {
    "literary": "3ede664097fdaa23fd6c781bc2f1ccf7d6a4b232634f763ceac52526d3a24111",
    "noir_cold": "57c3c437cb18f25e2d2e497357c4d8d72ee8d99bdaf272e5def7e9cb58e6f7a7",
    "hot_blooded": "ef72b072c35ef9aaf78ceb30f28aa91c603fff385c0cd408a2a8d7741f916501",
    "warm_healing": "de09349937c477a695cd0629cd06f81388f5b116705ad95da62f53f5fb778ddd",
    "classical_chapter": "7b6d76fd4c7dff028ce693aca332d75976cf17f0d73a0dae3f0b0a19ca89f0ea",
}


@pytest.mark.parametrize(
    ("style_key", "expected_codes"),
    [
        (
            "literary",
            {"END_STATE_WRONG_HOLDER", "REQUIRED_EVENT_MISSING"},
        ),
        (
            "noir_cold",
            {"TIME_CONSTRAINT_MUTATED", "CAUSAL_LINK_WEAKENED"},
        ),
        (
            "hot_blooded",
            {
                "UNSUPPORTED_CASUALTY_ADDED",
                "UNSUPPORTED_KINSHIP_ADDED",
                "UNSUPPORTED_BACKSTORY_ADDED",
                "UNSUPPORTED_INJURY_ADDED",
                "NARRATIVE_RELATION_ADDED",
            },
        ),
        ("warm_healing", {"NARRATIVE_CHARACTER_ADDED"}),
        (
            "classical_chapter",
            {
                "UNSUPPORTED_KINSHIP_ADDED",
                "UNSUPPORTED_DATE_ADDED",
                "UNSUPPORTED_ORGANIZATION_ADDED",
                "FORBIDDEN_OUTCOME_MENTIONED",
                "REQUIRED_EVENT_MISSING",
                "END_STATE_WRONG_HOLDER",
                "NARRATIVE_TOO_SHORT",
            },
        ),
    ],
)
def test_five_real_style_outputs_are_immutable_regression_fixtures(
    style_key: str,
    expected_codes: set[str],
) -> None:
    text = real_style_samples()[style_key]
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == _REAL_SAMPLE_HASHES[
        style_key
    ]
    contract = NarrativeContractBuilder().build(
        story_bible=StoryBible(
            premise="旧港旧信关系到十二年前港难。",
            theme="责任与诚实",
            setting_summary="无超自然力量的旧港灯塔。",
        ),
        canonical_state=CanonicalState(
            world={"locations": [{"id": "lighthouse", "name": "旧灯塔"}]},
            characters={
                "shen_yan": {"name": "沈砚"},
                "lin_qiu": {"name": "林秋"},
            },
            items={
                "letter": {"name": "旧信"},
                "lighthouse_light": {"name": "灯"},
            },
        ),
        section_goal=SectionGoal(
            section_id=f"real_{style_key}",
            objective="完成固定灯塔交信事件链。",
            viewpoint_character_id="shen_yan",
            involved_characters=["shen_yan", "lin_qiu"],
            desired_length=1000,
            narrative_constraints=lighthouse_constraints(),
        ),
        story_threads=[],
    )
    report = NarrativeContractValidator().validate(contract, text)
    actual_codes = {item.code for item in report.violations}

    assert report.accepted is False
    assert expected_codes <= actual_codes
