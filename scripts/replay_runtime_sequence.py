"""Deterministic full-runtime Tick replay for Phase 8/9.

Iteration 10 implements the zero-cost ``mock`` mode.  Iteration 11 adds an explicit
``recorded`` fixture mode, stable evidence hashing and completed-checkpoint reuse.
The harness uses the real ``TickRuntime`` assembly and ``Orchestrator.run_tick``
path; only the LLM transport is replaced by fixture responses routed by production
``agent_id``.

Phase 9 binds the complete, versioned Guard decision trace to CanonicalFact
before/after snapshots.  It still does not call a provider in mock/recorded mode.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for entry in (str(BACKEND), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from memory.tick_state import TickState  # noqa: E402
from memory_system.models import (  # noqa: E402
    CharacterProfile,
    CharacterState,
    Event,
    WorldState,
)
from narrative.canonical_facts import (  # noqa: E402
    CanonicalFact,
    CanonicalFactStore,
)
from narrative.canonical_reconciliation import reconcile_all  # noqa: E402
from nf_core.action_resolver import ActionResolver  # noqa: E402
from nf_core.llm_client import LLMResponse  # noqa: E402
from nf_core.token_budget import get_global_tracker  # noqa: E402
from tick_runtime import TickRuntime  # noqa: E402


class ReplayInitialState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    novel_title: str = "Phase 8 replay"
    world_state: dict[str, Any]
    character_profiles: list[dict[str, Any]]
    character_states: list[dict[str, Any]]
    continuity_state: dict[str, Any] = Field(default_factory=dict)
    continuity_audit: dict[str, Any] = Field(default_factory=dict)


class ReplayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: Any
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)


class ExpectedFactTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: str
    predicate: str
    value: Any


class ReplayFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_version: Literal["1"]
    fixture_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    initial_state: ReplayInitialState
    canonical_facts_before: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]]
    responses_by_agent: dict[str, list[ReplayResponse]]
    expected_required_end_states: list[str] = Field(default_factory=list)
    expected_fact_transitions: list[ExpectedFactTransition] = Field(default_factory=list)
    expected_acceptance: Literal["accept", "reject", "ambiguous"]
    labels: list[str] = Field(default_factory=list)
    response_provenance: Literal["synthetic", "sanitized_recorded"] = "synthetic"
    source_artifacts: list[str] = Field(default_factory=list)
    force_critic: bool = False


class ReplayFixtureOverlay(BaseModel):
    """Small RFC 7396-style patch over a versioned fixture in the same folder."""

    model_config = ConfigDict(extra="forbid")

    fixture_overlay_version: Literal["1"]
    base_fixture: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,120}$")
    merge_patch: dict[str, Any]


class GuardReplayCase(BaseModel):
    """One complete recorded Guard case expanded over a pinned runtime fixture."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    title: str
    previous_continuity_state: dict[str, Any] = Field(default_factory=dict)
    previous_continuity_audit: dict[str, Any] = Field(default_factory=dict)
    narrator_response: ReplayResponse
    critic_responses: dict[str, list[ReplayResponse]] = Field(default_factory=dict)
    verifier_responses: list[ReplayResponse] = Field(min_length=1)
    repair_responses: list[ReplayResponse] = Field(default_factory=list)
    required_end_states: list[str] = Field(min_length=1)
    expected_final_decision: Literal["accept", "reject", "ambiguous"]
    expected_error_types: list[str] = Field(default_factory=list)
    force_critic: bool = False


class GuardReplaySuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guard_replay_suite_version: Literal["1"]
    suite_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    base_fixture: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,120}$")
    response_provenance: Literal["synthetic", "sanitized_recorded"]
    cases: list[GuardReplayCase] = Field(min_length=1)


class CountingActionResolver(ActionResolver):
    """Production resolver with one measurement-only invocation counter."""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def resolve(self, *args, **kwargs):
        self.call_count += 1
        return super().resolve(*args, **kwargs)


class FixtureLLMRouter:
    """Route fixture responses by the same agent IDs used in production."""

    def __init__(
        self,
        responses: dict[str, list[ReplayResponse]],
        *,
        max_calls: int,
    ) -> None:
        self._queues = {key: list(items) for key, items in responses.items()}
        self.max_calls = max_calls
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self, system_prompt: str, user_prompt: str, **kwargs
    ) -> LLMResponse:
        if len(self.calls) >= self.max_calls:
            raise RuntimeError(f"replay max_calls exceeded: {self.max_calls}")
        agent_id = str(kwargs.get("agent_id", "unknown"))
        queue = self._queues.get(agent_id)
        if not queue:
            raise RuntimeError(f"no replay response remains for agent_id={agent_id}")
        item = queue.pop(0)
        started = time.perf_counter()
        content = (
            json.dumps(item.content, ensure_ascii=False)
            if isinstance(item.content, (dict, list))
            else str(item.content)
        )
        duration = time.perf_counter() - started
        self.calls.append(
            {
                "agent_id": agent_id,
                "tick": int(kwargs.get("tick", -1)),
                "priority": str(kwargs.get("priority", "medium")),
                "duration_sec": round(duration, 6),
                "prompt_sha256": hashlib.sha256(
                    (system_prompt + "\n" + user_prompt).encode("utf-8")
                ).hexdigest(),
                "response_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "prompt_tokens": item.prompt_tokens,
                "completion_tokens": item.completion_tokens,
                "cached_tokens": item.cached_tokens,
            }
        )
        # The transport is replaced, so mirror LLMClient's budget side effect.
        try:
            get_global_tracker().record(
                agent_id=agent_id,
                priority=str(kwargs.get("priority", "medium")),
                prompt_tokens=item.prompt_tokens,
                completion_tokens=item.completion_tokens,
                cached_tokens=item.cached_tokens,
                tick=int(kwargs.get("tick", -1)),
                model="fixture",
            )
        except Exception:
            pass
        return LLMResponse(
            content=content,
            usage_prompt_tokens=item.prompt_tokens,
            usage_completion_tokens=item.completion_tokens,
            usage_cached_tokens=item.cached_tokens,
        )

    def remaining(self) -> dict[str, int]:
        return {key: len(items) for key, items in self._queues.items() if items}


@contextmanager
def _patched_chat(router: FixtureLLMRouter):
    import nf_core.llm_client as llm_module

    original = llm_module.llm_client.chat
    llm_module.llm_client.chat = router  # type: ignore[method-assign]
    try:
        yield
    finally:
        llm_module.llm_client.chat = original  # type: ignore[method-assign]


@contextmanager
def _deterministic_runtime_scope(*, force_critic: bool = False):
    """Enable the production guard and make runtime-generated IDs repeatable."""
    import agents.orchestrator as orchestrator_module

    env_values = {"NARRATOR_STATE_VERIFY_ENABLE": "1"}
    if force_critic:
        env_values.update({
            "CRITIC_MIN_NARRATIVE_LEN": "1",
            "CRITIC_IMPORTANCE_MIN": "0",
            "CRITIC_ENABLE_LLM": "1",
        })
    previous_env = {name: os.environ.get(name) for name in env_values}
    original_uuid4 = orchestrator_module.uuid.uuid4
    original_collect_affected = (
        orchestrator_module.Orchestrator._collect_affected_characters
    )
    counter = 0

    def next_uuid() -> uuid.UUID:
        nonlocal counter
        counter += 1
        return uuid.UUID(int=counter)

    def sorted_affected(orchestrator, events):
        return sorted(original_collect_affected(orchestrator, events))

    for name, value in env_values.items():
        os.environ[name] = value
    orchestrator_module.uuid.uuid4 = next_uuid
    orchestrator_module.Orchestrator._collect_affected_characters = sorted_affected
    try:
        yield
    finally:
        orchestrator_module.uuid.uuid4 = original_uuid4
        orchestrator_module.Orchestrator._collect_affected_characters = (
            original_collect_affected
        )
        for name, value in previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def load_fixture(path: Path) -> ReplayFixture:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "fixture_overlay_version" in payload:
        overlay = ReplayFixtureOverlay.model_validate(payload)
        parent = path.resolve().parent
        base_path = (parent / overlay.base_fixture).resolve()
        if base_path.parent != parent:
            raise ValueError("replay overlay base must remain in the same directory")
        base_payload = json.loads(base_path.read_text(encoding="utf-8"))
        if "fixture_overlay_version" in base_payload:
            raise ValueError("nested replay fixture overlays are not supported")
        payload = _merge_patch(base_payload, overlay.merge_patch)
    return ReplayFixture.model_validate(payload)


def load_guard_replay_suite(path: Path) -> GuardReplaySuite:
    return GuardReplaySuite.model_validate_json(path.read_text(encoding="utf-8"))


def _fixture_from_guard_case(
    *,
    suite: GuardReplaySuite,
    case: GuardReplayCase,
    suite_path: Path,
) -> ReplayFixture:
    parent = suite_path.resolve().parent
    base_path = (parent / suite.base_fixture).resolve()
    if base_path.parent != parent:
        raise ValueError("guard suite base must remain in the same directory")
    payload = load_fixture(base_path).model_dump(mode="json")
    payload["fixture_id"] = case.case_id
    payload["initial_state"]["continuity_state"] = (
        case.previous_continuity_state
    )
    payload["initial_state"]["continuity_audit"] = (
        case.previous_continuity_audit
    )
    payload["events"][0]["description"] = case.title
    payload["events"][0]["consequences"] = list(case.required_end_states)
    responses = payload["responses_by_agent"]
    responses["narrator"] = [case.narrator_response.model_dump(mode="json")]
    responses["narrative_state_verifier"] = [
        item.model_dump(mode="json") for item in case.verifier_responses
    ]
    if case.repair_responses:
        responses["narrative_state_repair"] = [
            item.model_dump(mode="json") for item in case.repair_responses
        ]
    else:
        responses.pop("narrative_state_repair", None)
    for agent_id, items in case.critic_responses.items():
        responses[agent_id] = [item.model_dump(mode="json") for item in items]
    payload["expected_required_end_states"] = list(case.required_end_states)
    payload["expected_fact_transitions"] = []
    payload["expected_acceptance"] = case.expected_final_decision
    payload["labels"] = [
        "phase9_guard_suite",
        *case.expected_error_types,
    ]
    payload["response_provenance"] = suite.response_provenance
    payload["source_artifacts"] = [
        suite.base_fixture,
        suite_path.name,
        case.case_id,
    ]
    payload["force_critic"] = case.force_critic
    return ReplayFixture.model_validate(payload)


def _merge_patch(target: Any, patch: Any) -> Any:
    if not isinstance(patch, dict):
        return patch
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = _merge_patch(result.get(key), value)
    return result


def _fixture_sha256(fixture: ReplayFixture) -> str:
    return hashlib.sha256(
        fixture.model_dump_json(exclude_none=False).encode("utf-8")
    ).hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp.json", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _seed_replay_directory(
    work_dir: Path, fixture: ReplayFixture
) -> None:
    if work_dir.exists() and any(work_dir.iterdir()):
        raise FileExistsError(f"replay work directory is not empty: {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)
    state = TickState(str(work_dir))
    state.set_novel_title(fixture.initial_state.novel_title)
    state.set_world_state(
        WorldState.model_validate(fixture.initial_state.world_state)
    )
    for raw in fixture.initial_state.character_profiles:
        state.upsert_character_profile(CharacterProfile.model_validate(raw))
    for raw in fixture.initial_state.character_states:
        state.upsert_character_state(CharacterState.model_validate(raw))
    if fixture.initial_state.continuity_state:
        state.set_narrative_continuity_state(
            fixture.initial_state.continuity_state,
            audit=fixture.initial_state.continuity_audit or None,
        )
    state.save()

    if fixture.canonical_facts_before:
        store = CanonicalFactStore(str(work_dir))
        for raw in fixture.canonical_facts_before:
            store.append(CanonicalFact.model_validate(raw))
        store.save()


def _fact_payloads(store: CanonicalFactStore) -> list[dict[str, Any]]:
    return sorted(
        (fact.model_dump(mode="json") for fact in store.all_facts()),
        key=lambda item: item["fact_id"],
    )


def _fact_diff(
    before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    old = {item["fact_id"]: item for item in before}
    new = {item["fact_id"]: item for item in after}
    diff: list[dict[str, Any]] = []
    for fact_id in sorted(set(old) | set(new)):
        if fact_id not in old:
            diff.append({"change": "added", "fact": new[fact_id]})
        elif fact_id not in new:
            diff.append({"change": "removed", "fact": old[fact_id]})
        elif old[fact_id] != new[fact_id]:
            diff.append(
                {
                    "change": "updated",
                    "fact_id": fact_id,
                    "before": old[fact_id],
                    "after": new[fact_id],
                }
            )
    return diff


def _classify_failure(guard_trace: dict[str, Any], accepted: bool) -> str:
    if accepted:
        return ""
    stages = [
        guard_trace.get("after_retry") or {},
        guard_trace.get("after") or {},
        guard_trace.get("before") or {},
    ]
    findings = [
        str(item)
        for stage in stages
        for item in (stage.get("event_fulfillment_conflicts") or [])
    ]
    joined = " ".join(findings)
    if "缺少正文/账本实证" in joined or "缺少逐条核验" in joined:
        return "evidence_extraction_failure"
    if findings:
        return "event_endpoint_unfulfilled"
    if guard_trace.get("reject_reason"):
        return "state_guard_rejected"
    return "narrator_not_accepted"


def _expectations(
    fixture: ReplayFixture,
    facts_after: list[dict[str, Any]],
    accepted: bool,
    tick_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    actual_decision = "accept" if accepted else "reject"
    acceptance_ok = (
        fixture.expected_acceptance == "ambiguous"
        or fixture.expected_acceptance == actual_decision
    )
    current = {
        (item["subject_id"], item["predicate"]): item
        for item in facts_after
        if item.get("status") == "active"
    }
    fact_checks = []
    for expected in fixture.expected_fact_transitions:
        actual = current.get((expected.subject_id, expected.predicate))
        passed = actual is not None and actual.get("value") == expected.value
        fact_checks.append(
            {
                "subject_id": expected.subject_id,
                "predicate": expected.predicate,
                "expected": expected.value,
                "actual": actual.get("value") if actual else None,
                "passed": passed,
            }
        )
    actual_required_end_states = sorted(
        {
            str(requirement)
            for row in tick_rows
            for event in (row.get("guard_trace") or {}).get("required_events", [])
            for requirement in (event.get("required_end_states") or [])
        }
    )
    expected_required_end_states = sorted(set(fixture.expected_required_end_states))
    required_states_ok = actual_required_end_states == expected_required_end_states
    return {
        "expected_acceptance": fixture.expected_acceptance,
        "actual_acceptance": actual_decision,
        "acceptance_passed": acceptance_ok,
        "fact_checks": fact_checks,
        "expected_required_end_states": expected_required_end_states,
        "actual_required_end_states": actual_required_end_states,
        "required_end_states_passed": required_states_ok,
        "all_passed": (
            acceptance_ok
            and required_states_ok
            and all(item["passed"] for item in fact_checks)
        ),
    }


def _stable_evidence_payload(report: dict[str, Any]) -> dict[str, Any]:
    """Select deterministic evidence and exclude paths, latency and timestamps."""
    return {
        "schema_version": report["schema_version"],
        "fixture_version": report["fixture_version"],
        "fixture_id": report["fixture_id"],
        "fixture_sha256": report["fixture_sha256"],
        "mode": report["mode"],
        "response_provenance": report["response_provenance"],
        "execution": report["execution"],
        "labels": report["labels"],
        "ticks": [
            {
                key: row[key]
                for key in (
                    "tick",
                    "event_ids",
                    "events_generated",
                    "agents_called",
                    "narrator_should_narrate",
                    "narrator_skip_reason",
                    "narrator_consistency_flags",
                    "state_guard_reported_safe",
                    "deterministic_gate_passed",
                    "final_accepted",
                    "repair_attempted",
                    "repair_adopted",
                    "fact_diff",
                    "reconciliation_summary",
                    "failure_category",
                    "continuity_state_schema",
                    "typed_ledger_valid",
                    "typed_authoritative_eligible",
                    "continuity_issue_codes",
                    "continuity_raw_audit_retained",
                    "guard_trace",
                )
                if key in row
            }
            for row in report["ticks"]
        ],
        "expectations": report["expectations"],
        "calls": [
            {
                key: call[key]
                for key in (
                    "agent_id",
                    "tick",
                    "priority",
                    "prompt_sha256",
                    "response_sha256",
                    "prompt_tokens",
                    "completion_tokens",
                    "cached_tokens",
                )
            }
            for call in report["llm_calls"]
        ],
        "unused_fixture_responses": report["unused_fixture_responses"],
    }


def _evidence_sha256(report: dict[str, Any]) -> str:
    encoded = json.dumps(
        _stable_evidence_payload(report),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_completed_checkpoint(
    path: Path,
    *,
    fixture_sha256: str,
    mode: Literal["mock", "recorded"],
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("checkpoint_status") != "complete":
        raise ValueError(f"replay checkpoint is not complete: {path}")
    if payload.get("fixture_sha256") != fixture_sha256:
        raise ValueError("replay checkpoint fixture hash does not match")
    if payload.get("mode") != mode:
        raise ValueError("replay checkpoint mode does not match")
    expected_hash = payload.get("evidence_sha256")
    if not expected_hash or _evidence_sha256(payload) != expected_hash:
        raise ValueError("replay checkpoint evidence hash does not match")
    result = json.loads(json.dumps(payload, ensure_ascii=False))
    result["resume"] = {
        "checkpoint_reused": True,
        "provider_calls_this_run": 0,
        "scope": "completed_checkpoint_only",
    }
    return result


async def run_replay_async(
    fixture: ReplayFixture,
    *,
    work_dir: Path,
    max_calls: int = 40,
    checkpoint_path: Path | None = None,
    mode: Literal["mock", "recorded"] = "mock",
    resume: bool = False,
) -> dict[str, Any]:
    fixture_sha256 = _fixture_sha256(fixture)
    if resume:
        if checkpoint_path is None or not checkpoint_path.is_file():
            raise FileNotFoundError("--resume requires an existing checkpoint file")
        return _load_completed_checkpoint(
            checkpoint_path,
            fixture_sha256=fixture_sha256,
            mode=mode,
        )
    _seed_replay_directory(work_dir, fixture)
    router = FixtureLLMRouter(fixture.responses_by_agent, max_calls=max_calls)
    runtime = TickRuntime(
        user_id="__replay__",
        novel_id=fixture.fixture_id,
        _replay_data_dir=str(work_dir),
    )
    if fixture.force_critic:
        # Pytest normally disables Critic to keep legacy unit fixtures small.
        # A Phase 9 recorded fixture may explicitly opt into the production Critic
        # component while still routing every response through the fixture router.
        from agents.narrative_critic import NarrativeCritic

        runtime.narrator._enable_critic = True
        runtime.narrator._critic = NarrativeCritic()
    resolver = CountingActionResolver()
    runtime.action_resolver = resolver
    runtime.orchestrator._action_resolver = resolver
    facts_before = _fact_payloads(runtime.canonical_fact_store)
    event_models = [Event.model_validate(raw) for raw in fixture.events]
    events_by_tick: dict[int, list[Event]] = {}
    for event in event_models:
        events_by_tick.setdefault(max(1, int(event.tick)), []).append(event)

    report: dict[str, Any] = {
        "schema_version": "runtime-replay-v2",
        "fixture_version": fixture.fixture_version,
        "fixture_id": fixture.fixture_id,
        "fixture_sha256": fixture_sha256,
        "mode": mode,
        "response_provenance": fixture.response_provenance,
        "source_artifacts": fixture.source_artifacts,
        "checkpoint_status": "in_progress",
        "execution": {
            "execution_path": "full_runtime",
            "tick_runtime_exercised": True,
            "orchestrator_exercised": False,
            "action_resolver_exercised": False,
            "narrator_exercised": False,
            "critic_exercised": False,
            "state_guard_exercised": False,
            "persistence_exercised": False,
            "canonical_fact_sidecar_exercised": False,
            "canonical_reconciliation_exercised": False,
        },
        "labels": fixture.labels,
        "ticks": [],
        "resume": {
            "checkpoint_reused": False,
            "provider_calls_this_run": 0,
            "scope": "completed_checkpoint_only",
        },
    }

    started = time.perf_counter()
    try:
        with _deterministic_runtime_scope(
            force_critic=fixture.force_critic
        ), _patched_chat(router):
            tick_count = max(events_by_tick, default=1)
            for target_tick in range(1, tick_count + 1):
                for event in events_by_tick.get(target_tick, []):
                    runtime.orchestrator.inject_event(event)
                tick_started = time.perf_counter()
                summary = await runtime.orchestrator.run_tick()
                tick_duration = time.perf_counter() - tick_started
                narrator_out = runtime.orchestrator.last_narrator_output
                guard_trace = (
                    narrator_out.continuity_guard_trace if narrator_out else {}
                )
                initial_guard = guard_trace.get("before") or {}
                narrative_path = (
                    work_dir / "narratives" / f"tick_{summary.tick:06d}.txt"
                )
                accepted = bool(
                    summary.narrator_produced_text and narrative_path.is_file()
                )
                facts_after_tick = _fact_payloads(runtime.canonical_fact_store)
                if guard_trace:
                    # StateGuard runs before accepted narrative projection.  Bind
                    # the resulting snapshots here, after the real Orchestrator
                    # has completed projection and persistence.
                    guard_trace = json.loads(json.dumps(
                        guard_trace, ensure_ascii=False
                    ))
                    guard_trace["fixture_id"] = fixture.fixture_id
                    guard_trace["canonical_facts_before"] = facts_before
                    guard_trace["canonical_facts_after_candidate"] = (
                        facts_after_tick
                    )
                continuity_audit = (
                    runtime.tick_state.get_narrative_continuity_audit()
                )
                reconciliation = reconcile_all(
                    runtime.canonical_fact_store,
                    character_states=runtime.tick_state.list_character_states(),
                    legacy_facts=runtime.fact_ledger.active_facts(),
                    knowledge_graph=runtime.knowledge_graph.to_dict(),
                    continuity_state=(
                        runtime.tick_state.get_narrative_continuity_state()
                    ),
                ).to_dict()
                report["ticks"].append(
                    {
                        "tick": summary.tick,
                        "event_ids": [
                            event.id for event in events_by_tick.get(target_tick, [])
                        ],
                        "events_generated": summary.events_generated,
                        "agents_called": summary.agents_called,
                        "narrator_produced": any(
                            call["agent_id"] == "narrator" for call in router.calls
                        ),
                        "narrator_should_narrate": bool(
                            narrator_out and narrator_out.should_narrate
                        ),
                        "narrator_skip_reason": (
                            narrator_out.skip_reason if narrator_out else ""
                        ),
                        "narrator_consistency_flags": list(
                            narrator_out.consistency_flags
                            if narrator_out else []
                        ),
                        "state_guard_reported_safe": bool(
                            initial_guard.get("reported_safe")
                        ),
                        "deterministic_gate_passed": bool(initial_guard.get("safe")),
                        "final_accepted": accepted,
                        "repair_attempted": bool(
                            guard_trace.get("repair_attempted")
                        ),
                        "repair_adopted": bool(guard_trace.get("adopted")),
                        "canonical_facts_before": facts_before,
                        "canonical_facts_after": facts_after_tick,
                        "fact_diff": _fact_diff(facts_before, facts_after_tick),
                        "reconciliation_findings": reconciliation["issues"],
                        "reconciliation_summary": reconciliation,
                        "token_usage": asdict(runtime.token_budget.snapshot),
                        "latency": {
                            "tick_total_sec": round(tick_duration, 6),
                        },
                        "failure_category": _classify_failure(
                            guard_trace, accepted
                        ),
                        "continuity_state_schema": str(
                            continuity_audit.get("source_schema") or ""
                        ),
                        "typed_ledger_valid": bool(
                            continuity_audit.get("source_schema") == "typed_v1"
                            and not continuity_audit.get("issues")
                        ),
                        "typed_authoritative_eligible": bool(
                            continuity_audit.get("authoritative_eligible")
                        ),
                        "continuity_issue_codes": [
                            str(issue.get("code") or "")
                            for issue in (continuity_audit.get("issues") or [])
                            if isinstance(issue, dict)
                        ],
                        "continuity_raw_audit_retained": (
                            "raw_payload" in continuity_audit
                        ),
                        "guard_trace": guard_trace,
                    }
                )
                facts_before = facts_after_tick
                if checkpoint_path is not None:
                    _atomic_write_json(checkpoint_path, report)
    finally:
        runtime.close()

    facts_after = _fact_payloads(runtime.canonical_fact_store)
    accepted_final = bool(report["ticks"] and report["ticks"][-1]["final_accepted"])
    report["expectations"] = _expectations(
        fixture, facts_after, accepted_final, report["ticks"]
    )
    report["llm_calls"] = router.calls
    report["unused_fixture_responses"] = router.remaining()
    execution = report["execution"]
    execution.update(
        {
            "orchestrator_exercised": bool(report["ticks"]),
            "action_resolver_exercised": resolver.call_count > 0,
            "narrator_exercised": any(
                call["agent_id"] == "narrator" for call in router.calls
            ),
            "critic_exercised": any(
                call["agent_id"].startswith("narrative_critic:")
                for call in router.calls
            ),
            "state_guard_exercised": any(
                (row.get("guard_trace") or {}).get("attempted")
                for row in report["ticks"]
            ),
            "persistence_exercised": all(
                (work_dir / name).exists()
                for name in ("tick_state.json", "ticks.db", "canonical_facts.json")
            ),
            "canonical_fact_sidecar_exercised": (
                work_dir / "canonical_facts.json"
            ).is_file(),
            "canonical_reconciliation_exercised": all(
                "reconciliation_summary" in row for row in report["ticks"]
            ),
        }
    )
    report["telemetry"] = {
        "duration_sec": round(time.perf_counter() - started, 6),
        "call_count": len(router.calls),
        "token_usage": asdict(runtime.token_budget.snapshot),
        "action_resolver_calls": resolver.call_count,
    }
    report["artifact_paths"] = {
        "work_dir": str(work_dir.resolve()),
        "tick_state": str((work_dir / "tick_state.json").resolve()),
        "canonical_facts": str((work_dir / "canonical_facts.json").resolve()),
        "ticks_db": str((work_dir / "ticks.db").resolve()),
    }
    report["checkpoint_status"] = "complete"
    report["evidence_sha256"] = _evidence_sha256(report)
    if checkpoint_path is not None:
        _atomic_write_json(checkpoint_path, report)
    return report


def run_replay(
    fixture_path: Path,
    *,
    work_dir: Path,
    max_calls: int = 40,
    checkpoint_path: Path | None = None,
    mode: Literal["mock", "recorded"] = "mock",
    resume: bool = False,
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path)
    return asyncio.run(
        run_replay_async(
            fixture,
            work_dir=work_dir,
            max_calls=max_calls,
            checkpoint_path=checkpoint_path,
            mode=mode,
            resume=resume,
        )
    )


async def run_guard_replay_suite_async(
    suite_path: Path,
    *,
    work_dir: Path,
    max_calls: int = 40,
    checkpoint_path: Path | None = None,
    mode: Literal["mock", "recorded"] = "recorded",
) -> dict[str, Any]:
    """Run every suite case through the full production runtime component graph."""

    if work_dir.exists() and any(work_dir.iterdir()):
        raise FileExistsError(f"replay suite work directory is not empty: {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)
    suite = load_guard_replay_suite(suite_path)
    reports: list[dict[str, Any]] = []
    for case in suite.cases:
        fixture = _fixture_from_guard_case(
            suite=suite,
            case=case,
            suite_path=suite_path,
        )
        report = await run_replay_async(
            fixture,
            work_dir=work_dir / case.case_id,
            max_calls=max_calls,
            mode=mode,
        )
        report["expected_error_types"] = list(case.expected_error_types)
        reports.append(report)

    traces = [
        row["guard_trace"]
        for report in reports
        for row in report["ticks"]
        if row.get("guard_trace")
    ]
    completeness_fields = (
        "has_original_draft",
        "has_declared_ledger",
        "has_verifier_payload",
        "has_repair_full_text",
        "has_deterministic_checks",
        "has_required_end_states",
        "has_location_context",
        "has_critic_payload",
    )
    completeness = {
        field: sum(
            bool((trace.get("payload_completeness") or {}).get(field))
            for trace in traces
        )
        for field in completeness_fields
    }
    expected_rejects = sum(
        case.expected_final_decision == "reject" for case in suite.cases
    )
    expected_accepts = sum(
        case.expected_final_decision == "accept" for case in suite.cases
    )
    actual_rejects = sum(
        not report["ticks"][-1]["final_accepted"] for report in reports
    )
    actual_accepts = len(reports) - actual_rejects
    summary = {
        "case_count": len(reports),
        "expected_accepts": expected_accepts,
        "expected_rejects": expected_rejects,
        "actual_accepts": actual_accepts,
        "actual_rejects": actual_rejects,
        "signal_backed_accepts": sum(
            case.expected_final_decision == "accept"
            and bool(report["ticks"][-1].get("guard_trace"))
            for case, report in zip(suite.cases, reports)
        ),
        "signal_backed_rejects": sum(
            case.expected_final_decision == "reject"
            and bool(report["ticks"][-1].get("guard_trace"))
            for case, report in zip(suite.cases, reports)
        ),
        "critic_exercised_cases": sum(
            report["execution"]["critic_exercised"] for report in reports
        ),
        "all_expectations_passed": all(
            report["expectations"]["all_passed"] for report in reports
        ),
        "complete_trace_count": sum(
            not (trace.get("payload_completeness") or {}).get("missing_fields")
            for trace in traces
        ),
        "trace_count": len(traces),
        "completeness_counts": completeness,
        "provider_calls": 0,
        "model_tokens": None,
        "fixture_transport_calls": sum(
            report["telemetry"]["call_count"] for report in reports
        ),
    }
    stable = {
        "suite_version": suite.guard_replay_suite_version,
        "suite_id": suite.suite_id,
        "suite_sha256": hashlib.sha256(
            suite_path.read_bytes()
        ).hexdigest(),
        "mode": mode,
        "summary": summary,
        "cases": [
            {
                "fixture_id": report["fixture_id"],
                "evidence_sha256": report["evidence_sha256"],
                "expected_error_types": report["expected_error_types"],
            }
            for report in reports
        ],
    }
    evidence_sha256 = hashlib.sha256(json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    result = {
        "schema_version": "state-guard-replay-suite-v1",
        "suite_version": suite.guard_replay_suite_version,
        "suite_id": suite.suite_id,
        "suite_sha256": stable["suite_sha256"],
        "mode": mode,
        "response_provenance": suite.response_provenance,
        "checkpoint_status": "complete",
        "summary": summary,
        "cases": reports,
        "evidence_sha256": evidence_sha256,
    }
    if checkpoint_path is not None:
        _atomic_write_json(checkpoint_path, result)
    return result


def run_guard_replay_suite(
    suite_path: Path,
    *,
    work_dir: Path,
    max_calls: int = 40,
    checkpoint_path: Path | None = None,
    mode: Literal["mock", "recorded"] = "recorded",
) -> dict[str, Any]:
    return asyncio.run(run_guard_replay_suite_async(
        suite_path,
        work_dir=work_dir,
        max_calls=max_calls,
        checkpoint_path=checkpoint_path,
        mode=mode,
    ))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", help="Versioned replay fixture JSON")
    parser.add_argument(
        "--mode",
        choices=("mock", "recorded"),
        default="mock",
        help="Fixture transport provenance; neither mode calls a provider",
    )
    parser.add_argument("--work-dir", required=True, help="New empty replay directory")
    parser.add_argument("--out", required=True, help="Replay report/checkpoint JSON")
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse and validate an already-complete --out checkpoint",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_calls < 1:
        raise SystemExit("--max-calls must be positive")
    fixture_path = Path(args.fixture).resolve()
    fixture_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    is_suite = "guard_replay_suite_version" in fixture_payload
    if is_suite:
        if args.resume:
            raise SystemExit("--resume is not yet supported for guard replay suites")
        report = run_guard_replay_suite(
            fixture_path,
            work_dir=Path(args.work_dir).resolve(),
            max_calls=args.max_calls,
            checkpoint_path=Path(args.out).resolve(),
            mode=args.mode,
        )
        output = {
            "out": str(Path(args.out).resolve()),
            "suite_id": report["suite_id"],
            "mode": report["mode"],
            "evidence_sha256": report["evidence_sha256"],
            **report["summary"],
        }
        print(json.dumps(output, ensure_ascii=False))
        return 0 if report["summary"]["all_expectations_passed"] else 1

    report = run_replay(
        fixture_path,
        work_dir=Path(args.work_dir).resolve(),
        max_calls=args.max_calls,
        checkpoint_path=Path(args.out).resolve(),
        mode=args.mode,
        resume=args.resume,
    )
    print(
        json.dumps(
            {
                "out": str(Path(args.out).resolve()),
                "fixture_id": report["fixture_id"],
                "mode": report["mode"],
                "checkpoint_reused": report["resume"]["checkpoint_reused"],
                "evidence_sha256": report["evidence_sha256"],
                "ticks": len(report["ticks"]),
                "accepted": sum(row["final_accepted"] for row in report["ticks"]),
                "calls": report["telemetry"]["call_count"],
                "tokens": report["telemetry"]["token_usage"][
                    "total_prompt_tokens"
                ]
                + report["telemetry"]["token_usage"][
                    "total_completion_tokens"
                ],
                "expectations_passed": report["expectations"]["all_passed"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["expectations"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
