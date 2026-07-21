"""Versioned, loss-aware capture for one NarrativeStateGuard decision.

The trace is intentionally scoped to one Tick.  It contains no provider headers,
credentials or whole-novel history.  Missing payloads stay explicit so calibration
tools can exclude unsupported denominators instead of inventing evidence.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TRACE_SCHEMA_VERSION = "state-guard-trace-v1"


class TracePayloadCompleteness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_original_draft: bool
    has_declared_ledger: bool
    has_verifier_payload: bool
    has_repair_full_text: bool
    has_deterministic_checks: bool
    has_required_end_states: bool
    has_location_context: bool
    has_critic_payload: bool
    repair_required: bool
    critic_required: bool
    missing_fields: list[str] = Field(default_factory=list)


class StateGuardDecisionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["state-guard-trace-v1"] = TRACE_SCHEMA_VERSION
    trace_id: str
    fixture_id: str | None = None
    tick: int = 0

    previous_typed_state: dict[str, Any] = Field(default_factory=dict)
    previous_legacy_state: dict[str, Any] = Field(default_factory=dict)
    canonical_facts_before: list[dict[str, Any]] = Field(default_factory=list)

    required_events: list[dict[str, Any]] = Field(default_factory=list)
    required_end_states: list[dict[str, Any]] = Field(default_factory=list)
    location_context: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_boundaries: list[dict[str, Any]] = Field(default_factory=list)

    original_draft: str
    guard_input_draft: str
    original_declared_typed_state: dict[str, Any] = Field(default_factory=dict)
    original_declared_raw_state: dict[str, Any] = Field(default_factory=dict)
    original_declared_legacy_state: dict[str, Any] = Field(default_factory=dict)

    critic_input: dict[str, Any] = Field(default_factory=dict)
    critic_output: dict[str, Any] = Field(default_factory=dict)
    critic_skip_reason: str = ""
    verifier_rounds: list[dict[str, Any]] = Field(default_factory=list)
    repair_rounds: list[dict[str, Any]] = Field(default_factory=list)
    deterministic_checks: list[dict[str, Any]] = Field(default_factory=list)
    canonical_facts_after_candidate: list[dict[str, Any]] = Field(
        default_factory=list
    )

    final_text: str
    final_typed_state: dict[str, Any] = Field(default_factory=dict)
    final_legacy_state: dict[str, Any] = Field(default_factory=dict)
    final_decision: Literal["accept", "reject"]
    rejection_category: str | None = None
    payload_completeness: TracePayloadCompleteness

    # Compatibility/operational projections retained as declared schema fields.
    # Calibration uses the complete round arrays above; existing runtime readers
    # may continue to consume before/after and the bounded repair guards.
    attempted: bool = True
    repair_attempted: bool = False
    repair_retry_attempted: bool = False
    adopted: bool = False
    repair_retry_adopted: bool = False
    repair_guard: dict[str, Any] = Field(default_factory=dict)
    repair_retry_guard: dict[str, Any] = Field(default_factory=dict)
    repair_declared: list[Any] = Field(default_factory=list)
    repair_retry_declared: list[Any] = Field(default_factory=list)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    after_retry: dict[str, Any] = Field(default_factory=dict)
    reject_reason: str = ""
    known_entities: list[str] = Field(default_factory=list)
    entity_names: dict[str, str] = Field(default_factory=dict)
    tracking_character_id: str = ""


def build_trace_id(
    *, tick: int, original_draft: str, declared_state: dict[str, Any]
) -> str:
    encoded = json.dumps(
        {
            "tick": tick,
            "original_draft": original_draft,
            "declared_state": declared_state,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sgt_" + hashlib.sha256(encoded).hexdigest()[:24]


def flatten_required_end_states(
    required_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "event_id": str(event.get("id", "") or ""),
            "requirement": str(requirement or ""),
        }
        for event in required_events
        for requirement in (event.get("required_end_states") or [])
        if str(requirement or "").strip()
    ]


def finalise_trace(
    trace: dict[str, Any],
    *,
    final_text: str,
    final_legacy_state: dict[str, Any],
    final_typed_state: dict[str, Any] | None,
    accepted: bool,
    rejection_category: str | None,
) -> dict[str, Any]:
    """Validate and return a JSON-safe completed trace."""

    completed = dict(trace)
    completed.update(
        {
            "final_text": final_text,
            "final_typed_state": final_typed_state or {},
            "final_legacy_state": final_legacy_state,
            "final_decision": "accept" if accepted else "reject",
            "rejection_category": None if accepted else rejection_category,
        }
    )
    verifier_rounds = completed.get("verifier_rounds") or []
    repair_rounds = completed.get("repair_rounds") or []
    deterministic_checks = completed.get("deterministic_checks") or []
    repair_required = bool(completed.get("repair_attempted"))
    critic_required = not bool(completed.get("critic_skip_reason"))
    completeness_values = {
        "has_original_draft": bool(completed.get("original_draft")),
        "has_declared_ledger": bool(
            completed.get("original_declared_typed_state")
            or completed.get("original_declared_raw_state")
            or completed.get("original_declared_legacy_state")
        ),
        "has_verifier_payload": bool(verifier_rounds)
        and all(
            isinstance(item, dict)
            and bool(item.get("input"))
            and "raw_output" in item
            for item in verifier_rounds
        ),
        "has_repair_full_text": (not repair_required)
        or (
            bool(repair_rounds)
            and all(
                isinstance(item, dict)
                and bool((item.get("raw_output") or {}).get("narrative_text"))
                for item in repair_rounds
            )
        ),
        "has_deterministic_checks": bool(deterministic_checks),
        "has_required_end_states": bool(completed.get("required_end_states")),
        "has_location_context": bool(completed.get("location_context")),
        "has_critic_payload": (not critic_required)
        or bool(completed.get("critic_output")),
        "repair_required": repair_required,
        "critic_required": critic_required,
    }
    required_flags = (
        "has_original_draft",
        "has_declared_ledger",
        "has_verifier_payload",
        "has_repair_full_text",
        "has_deterministic_checks",
        "has_required_end_states",
        "has_location_context",
        "has_critic_payload",
    )
    completeness_values["missing_fields"] = [
        name for name in required_flags if not completeness_values[name]
    ]
    completed["payload_completeness"] = completeness_values
    strict_payload = {
        key: value
        for key, value in completed.items()
        if key in StateGuardDecisionTrace.model_fields
    }
    validated = StateGuardDecisionTrace.model_validate(strict_payload)
    payload = validated.model_dump(mode="json")
    return payload


__all__ = [
    "TRACE_SCHEMA_VERSION",
    "StateGuardDecisionTrace",
    "TracePayloadCompleteness",
    "build_trace_id",
    "finalise_trace",
    "flatten_required_end_states",
]
