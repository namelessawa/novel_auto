from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from scripts.replay_runtime_sequence import (
    ReplayFixture,
    load_fixture,
    run_replay,
    run_replay_async,
)
from tick_runtime import TickRuntime


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "runtime_replay"
    / "mock_full_runtime_v1.json"
)


def test_full_runtime_mock_replay_exercises_production_path(tmp_path) -> None:
    report = run_replay(
        FIXTURE,
        work_dir=tmp_path / "accepted",
        max_calls=10,
    )

    assert report["expectations"]["all_passed"] is True
    assert report["expectations"]["required_end_states_passed"] is True
    assert report["unused_fixture_responses"] == {}
    assert len(report["ticks"]) == 1
    tick = report["ticks"][0]
    assert tick["final_accepted"] is True
    assert tick["state_guard_reported_safe"] is True
    assert tick["deterministic_gate_passed"] is True
    assert tick["repair_attempted"] is False
    assert tick["failure_category"] == ""
    assert any(item.startswith("state_patches(applied=1") for item in tick["agents_called"])

    execution = report["execution"]
    assert execution == {
        "execution_path": "full_runtime",
        "tick_runtime_exercised": True,
        "orchestrator_exercised": True,
        "action_resolver_exercised": True,
        "narrator_exercised": True,
        "critic_exercised": False,
        "state_guard_exercised": True,
        "persistence_exercised": True,
        "canonical_fact_sidecar_exercised": True,
        "canonical_reconciliation_exercised": True,
    }
    assert (tmp_path / "accepted" / "narratives" / "tick_000001.txt").is_file()
    assert (tmp_path / "accepted" / "canonical_facts.json").is_file()
    assert (tmp_path / "accepted" / "ticks.db").is_file()
    assert report["telemetry"]["action_resolver_calls"] == 1
    assert report["telemetry"]["call_count"] == 6


def _rejected_fixture() -> ReplayFixture:
    payload = load_fixture(FIXTURE).model_dump(mode="json")
    payload["fixture_id"] = "map_gate_full_runtime_rejected_tick_1"
    payload["expected_acceptance"] = "reject"
    failed_verdict = {
        "content": {
            "safe": False,
            "event_checks": [
                {
                    "event_id": "evt_map_gate",
                    "requirement": "本段结束前：地图由 alice 持有",
                    "met": False,
                    "prose_evidence": [],
                    "ledger_evidence_paths": [],
                }
            ],
            "event_fulfillment_conflicts": ["地图持有终态未兑现"],
            "entity_grounding_conflicts": [],
            "prior_state_conflicts": [],
            "internal_conflicts": [],
            "ledger_conflicts": [],
            "fact_changes_from_original": [],
            "reason": "要求未完成。",
        }
    }
    original_narrator = payload["responses_by_agent"]["narrator"][0]["content"]
    failed_state = original_narrator["continuity_state"]
    repair = {
        "content": {
            "narrative_text": original_narrator["narrative_text"],
            "continuity_state": failed_state,
            "repairs": ["未能修复地图持有证据"],
        }
    }
    payload["responses_by_agent"]["narrative_state_verifier"] = [
        failed_verdict,
        failed_verdict,
        failed_verdict,
    ]
    payload["responses_by_agent"]["narrative_state_repair"] = [repair, repair]
    return ReplayFixture.model_validate(payload)


def test_rejected_tick_does_not_project_guarded_narrative_facts(tmp_path) -> None:
    fixture = _rejected_fixture()
    report = asyncio.run(
        run_replay_async(
            fixture,
            work_dir=tmp_path / "rejected",
            max_calls=12,
        )
    )

    tick = report["ticks"][0]
    assert tick["final_accepted"] is False
    assert tick["repair_attempted"] is True
    assert tick["repair_adopted"] is False
    assert tick["failure_category"] == "event_endpoint_unfulfilled"
    assert not (tmp_path / "rejected" / "narratives" / "tick_000001.txt").exists()

    facts = tick["canonical_facts_after"]
    assert facts  # Event/CharacterAction/StatePatch facts still persist.
    assert not any(
        ref["kind"] == "guarded_narrative"
        for fact in facts
        for ref in fact["source_refs"]
    )
    assert not any(fact["predicate"] == "item_condition" for fact in facts)
    assert report["expectations"]["all_passed"] is True


def test_mock_replay_fact_and_call_evidence_is_repeatable(tmp_path) -> None:
    first = run_replay(FIXTURE, work_dir=tmp_path / "first", max_calls=10)
    second = run_replay(FIXTURE, work_dir=tmp_path / "second", max_calls=10)

    assert first["fixture_sha256"] == second["fixture_sha256"]
    assert first["ticks"][0]["fact_diff"] == second["ticks"][0]["fact_diff"]
    assert first["expectations"] == second["expectations"]
    assert [
        (call["agent_id"], call["prompt_sha256"], call["response_sha256"])
        for call in first["llm_calls"]
    ] == [
        (call["agent_id"], call["prompt_sha256"], call["response_sha256"])
        for call in second["llm_calls"]
    ]


def test_replay_directory_override_is_restricted_to_replay_identity(tmp_path) -> None:
    with pytest.raises(ValueError, match="restricted"):
        TickRuntime(
            user_id="real-user",
            novel_id="novel",
            _replay_data_dir=str(tmp_path),
        )
