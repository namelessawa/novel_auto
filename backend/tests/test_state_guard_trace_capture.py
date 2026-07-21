from __future__ import annotations

import pytest

from agents.narrative_state_guard import NarrativeStateGuard
from narrative.state_guard_trace import StateGuardDecisionTrace


def _verdict(*, safe: bool, met: bool) -> dict:
    return {
        "safe": safe,
        "event_checks": [{
            "event_id": "evt_enter",
            "requirement": "alice enters city_gate_inner",
            "met": met,
            "prose_evidence": ["Alice跨过内门"] if met else [],
            "ledger_evidence_paths": [
                "characters.alice.location"
            ] if met else [],
        }],
        "event_fulfillment_conflicts": [] if safe else ["终态未完成"],
        "entity_grounding_conflicts": [],
        "prior_state_conflicts": [],
        "internal_conflicts": [],
        "ledger_conflicts": [],
        "fact_changes_from_original": [],
        "reason": "完整终态" if safe else "仍在门外",
    }


@pytest.mark.asyncio
async def test_complete_guard_trace_keeps_original_and_verifier_payload(
    mock_llm,
) -> None:
    original = "Alice跨过内门，门闩在她身后落下。"
    typed = {
        "schema_version": "1",
        "time_marker": "tick-1",
        "characters": {
            "alice": {
                "location_id": "city_gate_inner",
                "movement_status": "arrived",
                "destination_location_id": None,
                "alive_status": "alive",
                "injuries": [],
                "supporting_character_ids": [],
                "carried_by_character_id": None,
                "knowledge_fact_ids": [],
            }
        },
        "items": {},
        "newly_known_fact_ids": {},
        "active_open_loop_ids": [],
    }
    legacy = {"characters": {"alice": {"location": "city_gate_inner"}}}
    mock_llm.set_responses([_verdict(safe=True, met=True)])

    out = await NarrativeStateGuard().guard(
        narrative_text=original,
        previous_state={"characters": {"alice": {"location": "city_gate_outer"}}},
        declared_state=legacy,
        required_events=[{
            "id": "evt_enter",
            "description": "Alice must enter.",
            "required_end_states": ["alice enters city_gate_inner"],
        }],
        original_narrator_draft=original,
        original_declared_typed_state=typed,
        original_declared_raw_state=typed,
        critic_input={"draft_text": original},
        critic_skip_reason="length_gate",
        location_context=[
            {"location_id": "city_gate_inner", "contains": []}
        ],
        knowledge_boundaries=[
            {"character_id": "alice", "known_facts": []}
        ],
        tick=1,
    )

    validated = StateGuardDecisionTrace.model_validate(out.trace)
    assert validated.original_draft == original
    assert validated.guard_input_draft == original
    assert validated.original_declared_typed_state == typed
    assert validated.original_declared_raw_state == typed
    assert validated.verifier_rounds[0]["input"]["narrative_text"] == original
    assert validated.verifier_rounds[0]["raw_output"]["safe"] is True
    assert validated.payload_completeness.has_original_draft is True
    assert validated.payload_completeness.has_verifier_payload is True
    assert validated.payload_completeness.has_repair_full_text is True
    assert validated.payload_completeness.has_required_end_states is True
    assert validated.payload_completeness.has_location_context is True
    assert validated.payload_completeness.has_critic_payload is True


@pytest.mark.asyncio
async def test_complete_guard_trace_keeps_every_repair_full_text(mock_llm) -> None:
    original = "Alice仍停在外堡门洞，内城门紧闭。"
    repaired = "Alice跨过内门，内城门在她身后关上。"
    state = {"characters": {"alice": {"location": "city_gate_inner"}}}
    repair_payload = {
        "narrative_text": repaired,
        "continuity_state": state,
        "repairs": ["补齐进入内门终态"],
    }
    mock_llm.set_responses([
        _verdict(safe=False, met=False),
        repair_payload,
        _verdict(safe=True, met=True),
    ])

    out = await NarrativeStateGuard().guard(
        narrative_text=original,
        previous_state={"characters": {"alice": {"location": "city_gate_outer"}}},
        declared_state={"characters": {"alice": {"location": "outer_fortification"}}},
        required_events=[{
            "id": "evt_enter",
            "required_end_states": ["alice enters city_gate_inner"],
        }],
        critic_skip_reason="critic_disabled",
        location_context=[{"location_id": "city_gate_inner"}],
        tick=2,
    )

    validated = StateGuardDecisionTrace.model_validate(out.trace)
    assert out.safe is True
    assert out.adopted is True
    assert len(validated.verifier_rounds) == 2
    assert len(validated.repair_rounds) == 1
    assert validated.repair_rounds[0]["input"]["narrative_text"] == original
    assert validated.repair_rounds[0]["raw_output"] == repair_payload
    assert validated.final_text == repaired
    assert validated.payload_completeness.has_repair_full_text is True


def test_payload_loss_is_explicit_in_trace_model() -> None:
    payload = {
        "schema_version": "state-guard-trace-v1",
        "trace_id": "sgt_missing_payload",
        "tick": 3,
        "required_events": [],
        "required_end_states": [],
        "original_draft": "",
        "guard_input_draft": "",
        "final_text": "",
        "final_decision": "reject",
        "payload_completeness": {
            "has_original_draft": False,
            "has_declared_ledger": False,
            "has_verifier_payload": False,
            "has_repair_full_text": False,
            "has_deterministic_checks": False,
            "has_required_end_states": False,
            "has_location_context": False,
            "has_critic_payload": False,
            "repair_required": True,
            "critic_required": True,
            "missing_fields": [
                "has_original_draft",
                "has_declared_ledger",
                "has_verifier_payload",
                "has_repair_full_text",
            ],
        },
    }

    trace = StateGuardDecisionTrace.model_validate(payload)
    assert trace.payload_completeness.has_original_draft is False
    assert "has_repair_full_text" in trace.payload_completeness.missing_fields
