from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from sections.section_store import _clear_for_tests
from story.models import CanonicalState, StoryBibleUpdate
from story.simulation_gateway import SimulationNarrativeGateway


@pytest.fixture(autouse=True)
def clear_sections():
    _clear_for_tests()
    yield
    _clear_for_tests()


def _gateway(tmp_path: Path) -> SimulationNarrativeGateway:
    gateway = SimulationNarrativeGateway(
        user_id="alice",
        novel_id="simulation",
        data_dir=str(tmp_path),
        title="潮门",
    )
    bible = gateway.service.bibles.load()
    gateway.service.bibles.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            premise="守灯人调查旧港难。",
            theme="责任与真相",
            setting_summary="没有超自然力量的旧港。",
            immutable_world_rules=["死亡不可逆", "世界不存在超自然力量"],
        )
    )
    gateway.service.states.save(
        CanonicalState(
            world={
                "locations": [
                    {"id": "lighthouse", "name": "灯塔"},
                    {"id": "archive", "name": "档案室"},
                ]
            },
            characters={
                "shen_yan": {
                    "name": "沈砚",
                    "alive": True,
                    "location": "lighthouse",
                }
            },
        )
    )
    return gateway


@pytest.mark.asyncio
async def test_simulation_candidate_uses_shared_validator_and_commits_projection(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path)
    fact = SimpleNamespace(
        fact_id="fact_location",
        subject_id="shen_yan",
        predicate="character_location",
        value={"state": "arrived", "location_id": "archive"},
    )
    projection = SimpleNamespace(facts=[fact])

    accepted = await gateway(
        3,
        "沈砚离开灯塔，抵达档案室。他决定为查清真相承担责任。",
        viewpoint_character_id="shen_yan",
        state_projection=projection,
    )

    assert accepted is True
    assert gateway.service.states.load().characters["shen_yan"]["location"] == "archive"
    assert gateway.service.states.load().revision == 2
    section = gateway.service.sections.get_last()
    assert section is not None
    assert section.generation_mode == "simulation"
    assert section.validation_report["accepted"] is True
    transaction = gateway.service.transactions.load("simulation_tick_00000003")
    assert transaction.narrative_validation_report is not None
    assert transaction.narrative_validation_report.accepted is True
    assert transaction.narrative_contract is not None
    assert transaction.narrative_contract.required_events == []
    assert (tmp_path / "narratives" / "tick_000003.txt").is_file()


@pytest.mark.asyncio
async def test_simulation_candidate_rejection_has_no_official_half_commit(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path)

    accepted = await gateway(
        4,
        "死去的旧王忽然复活，并用超自然力量抹平了所有代价。",
        state_projection=SimpleNamespace(facts=[]),
    )

    assert accepted is False
    assert gateway.service.states.load().revision == 1
    assert gateway.service.sections.count() == 0
    assert not (tmp_path / "narratives" / "tick_000004.txt").exists()
    transaction = gateway.service.transactions.load("simulation_tick_00000004")
    assert transaction.phase == "rejected"
    assert transaction.validation_report is not None
    assert "IMMUTABLE_RULE_REVIVAL" in {
        item.code for item in transaction.validation_report.violations
    }
