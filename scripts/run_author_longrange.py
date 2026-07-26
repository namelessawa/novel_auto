"""Run resumable author-mode long-range validation with recorded or real Writer.

Stage 0 is provider-free and exercises contract validation, repair, recovery,
stale revision rejection and the five immutable real-style samples.  Real mode
uses the configured AuthorWriter but keeps the same checkpoint and budget gates.
Credentials are process-only and are never persisted.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "backend"), str(ROOT / "scripts")]

DEFAULT_THEMES = "reality_mystery,action_conflict,warm_relationship"
DEFAULT_STYLES = "literary,noir_cold,warm_healing,hot_blooded,classical_chapter"


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(text, encoding="utf-8")
    os.replace(partial, path)


def _atomic_json(path: Path, payload: Any) -> None:
    _atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _safe_error(exc: Exception) -> dict[str, str]:
    return {
        "type": type(exc).__name__,
        "message": "generation failed; provider response omitted",
    }


def _request_id(index: int, failures: list[dict[str, Any]]) -> tuple[str, int]:
    prior_failures = sum(int(item.get("section", -1)) == index for item in failures)
    request_id = f"section_{index:04d}"
    if prior_failures:
        request_id += f"_retry_{prior_failures:02d}"
    return request_id, prior_failures


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _ngrams(text: str, size: int = 4) -> set[str]:
    compact = "".join(text.split())
    return {
        compact[index : index + size]
        for index in range(max(0, len(compact) - size + 1))
    }


def _overlap(left: str, right: str) -> float:
    current = _ngrams(left)
    previous = _ngrams(right)
    return round(len(current & previous) / len(current), 4) if current else 0.0


def _style_snapshot(style_key: str) -> dict[str, Any]:
    from novel_presets.style_presets import get_style_preset

    return get_style_preset(style_key).to_snapshot()


def _constraints(index: int, *, min_chars: int, max_chars: int):
    from story.narrative_contract import (
        AllowedEntities,
        EntityReference,
        LengthConstraint,
        NarrativeContractInput,
        RequiredEndState,
        RequiredEvent,
    )

    if index == 1:
        actor = "shen_yan"
        action = "把旧信交给林秋"
        event_evidence = (
            r"沈砚[\s\S]{0,500}(?:林秋[\s\S]{0,140}"
            r"(?:接|接过|收下|放进|塞进|滑进)|"
            r"(?:接过|收下)[\s\S]{0,40}(?:旧信|信纸|信封|封套|油纸封))"
        )
        keywords = ["沈砚", "林秋", "旧信", "接"]
    else:
        actor = "lin_qiu"
        action = f"核对旧信第{index}处记录并继续保管"
        event_evidence = (
            rf"林秋[\s\S]{{0,500}}(?:核对|复核|读|查看)[\s\S]{{0,160}}"
            rf"(?:旧信|信纸|第{index}处|第{index}节)"
        )
        keywords = ["林秋", "旧信", "核对"]
    holder_evidence = (
        r"林秋[\s\S]{0,600}(?:旧信|信纸|信封|封套|油纸封|将信)[\s\S]{0,120}"
        r"(?:接过|收下|放进|塞进|滑进|装进|收好|保管|抽屉|口袋|衣袋|侧袋)"
    )
    return NarrativeContractInput(
        allowed_entities=AllowedEntities(
            characters=[
                EntityReference(id="shen_yan", name="沈砚"),
                EntityReference(id="lin_qiu", name="林秋"),
            ],
            locations=[EntityReference(id="lighthouse", name="旧灯塔")],
            items=[
                EntityReference(
                    id="letter",
                    name="旧信",
                    aliases=["信纸", "信封", "封套", "油纸封"],
                )
            ],
        ),
        required_events=[
            RequiredEvent(
                id=f"handover_{index}",
                actor=actor,
                action=action,
                target="lin_qiu" if index == 1 else "letter",
                evidence_patterns=[event_evidence],
                keywords=keywords,
                min_keyword_matches=len(keywords),
            )
        ],
        required_end_state=[
            RequiredEndState(
                id=f"end_{index}",
                path="/items/letter/holder",
                expected="lin_qiu",
                evidence_patterns=[holder_evidence],
                wrong_state_patterns=[r"沈砚仍把旧信藏在怀里"],
            )
        ],
        length_constraint=LengthConstraint(min_chars=min_chars, max_chars=max_chars),
    )


def _goal(index: int, *, desired_length: int):
    from story.models import SectionGoal

    objective = (
        "推进旧信责任线：沈砚把旧信交给林秋"
        if index == 1
        else f"推进旧信责任线：林秋核对第{index}处记录并继续保管旧信"
    )
    return SectionGoal(
        objective=objective,
        viewpoint_character_id="shen_yan",
        location_id="lighthouse",
        involved_characters=["shen_yan", "lin_qiu"],
        desired_length=desired_length,
        narrative_constraints=_constraints(
            index,
            min_chars=(
                desired_length
                if desired_length >= 900
                else max(80, desired_length // 2)
            ),
            max_chars=(
                desired_length + 200
                if desired_length >= 900
                else max(240, desired_length * 2)
            ),
        ),
    )


def _recorded_valid_text(index: int, desired_length: int) -> str:
    if index == 1:
        event = "沈砚把旧信交给林秋，林秋接过旧信，并把它放进桌上的防潮袋。"
    else:
        event = (
            f"林秋核对旧信第{index}处记录并继续保管，把信封收好后放进抽屉。"
        )
    base = (
        "暴雨后的旧灯塔仍带着潮湿盐味。沈砚先核对旧信上的既有记录，"
        "没有添加新的责任人或日期；林秋逐行复核，两人只讨论当前证据。"
        f"{event}"
        "这次行动推进了公开真相的责任线，没有改变两人的既有关系。"
    )
    padding = "灯光扫过桌面，两人继续核对已经确认的事实。"
    while sum(not char.isspace() for char in base) < max(80, desired_length // 2):
        base += padding
    return base


def _candidate(text: str, index: int):
    from story.models import StateDeltaOperation, WriterCandidate

    state_delta = []
    if index == 1 and "沈砚把旧信交给林秋" in text:
        state_delta = [
            StateDeltaOperation(
                op="set",
                path="/items/letter/holder",
                value="lin_qiu",
                evidence="沈砚把旧信交给林秋，林秋接过旧信",
            )
        ]

    return WriterCandidate(
        narrative_text=text,
        title=f"交接 {index}",
        section_summary=f"沈砚与林秋完成第{index}次旧信交接。",
        state_delta=state_delta,
    )


class RecordedLongRangeWriter:
    def __init__(self, *, repair_every: int = 4) -> None:
        self.repair_every = repair_every
        self.last_index = 0
        self.last_length = 300
        self.generate_calls = 0
        self.repair_calls = 0

    async def generate(self, context, goal):
        from story.writer import WriterResult

        self.generate_calls += 1
        match = re.search(r"第(\d+)(?:次|处)", goal.objective)
        self.last_index = int(match.group(1)) if match else self.generate_calls
        self.last_length = goal.desired_length
        valid = _recorded_valid_text(self.last_index, self.last_length)
        if self.repair_every and self.last_index % self.repair_every == 0:
            text = "沈砚仍把旧信藏在怀里，并说父亲会替他们处理。" + valid
        else:
            text = valid
        return WriterResult(
            _candidate(text, self.last_index),
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "repair_tokens": 0,
                "total_tokens": 0,
            },
        )

    async def repair(self, candidate, report):
        from story.repair_patch import RepairPatchSet
        from story.repair_plan import repair_patch_prompt_payload
        from story.writer import WriterResult

        self.repair_calls += 1
        return WriterResult(
            candidate,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "repair_tokens": 0,
                "total_tokens": 0,
            },
            repair_patches=RepairPatchSet.model_validate(
                {
                    "patches": repair_patch_prompt_payload(
                        report,
                        candidate.narrative_text,
                    )["suggested_patch_templates"]
                }
            ),
        )


@dataclass
class RunLimits:
    max_sections: int
    max_total_tokens: int
    max_cost: float
    prompt_cost_per_million: float
    completion_cost_per_million: float


def _estimated_cost(usage: dict[str, int], limits: RunLimits) -> float:
    return round(
        int(usage.get("prompt_tokens", 0)) * limits.prompt_cost_per_million / 1_000_000
        + int(usage.get("completion_tokens", 0))
        * limits.completion_cost_per_million
        / 1_000_000,
        8,
    )


def _initialise_service(data_dir: Path, *, style: str, theme: str, writer=None):
    from story.models import CanonicalState
    from story.service import AuthorGenerationService

    service = AuthorGenerationService(
        user_id="author_longrange",
        novel_id=data_dir.parent.name,
        data_dir=str(data_dir),
        title="长程正文契约验证",
        writer=writer,
    )
    bible = service.bibles.load()
    if bible.revision == 1:
        theme_seed = {
            "reality_mystery": "旧灯塔里，两名维护者逐节核对并交接一封关系港难的旧信。",
            "action_conflict": "高风险撤离前，两名维护者必须保护旧信并逐节核对关键记录。",
            "warm_relationship": "两名多年搭档在照料灯塔的日常中共同核对并保管一封旧信。",
        }.get(theme, f"围绕 {theme} 连续核对并保管一封旧信。")
        service.bibles.initialise_from_user_inputs(
            title="长程正文契约验证",
            source_seed=theme_seed,
            theme_key=theme,
            theme_label=theme,
            positioning="连续现实主义悬疑",
            references="只参考节奏，不复制表达",
            style_contract=_style_snapshot(style),
            preset_seed=False,
        )
        service.states.save(
            CanonicalState(
                revision=1,
                world={"locations": [{"id": "lighthouse", "name": "旧灯塔"}]},
                characters={
                    "shen_yan": {"name": "沈砚", "location": "lighthouse"},
                    "lin_qiu": {"name": "林秋", "location": "lighthouse"},
                },
                items={
                    "letter": {
                        "name": "旧信",
                        "aliases": ["信纸", "信封", "封套", "油纸封"],
                        "owners": ["shen_yan"],
                        "holder": "shen_yan",
                        "location": "lighthouse",
                    }
                },
                relationships={
                    "shen_yan:lin_qiu": {"description": "共同维护灯塔的多年搭档"}
                },
            )
        )
    return service


def _section_metrics(
    transaction,
    service,
    previous_text: str,
    latency: float,
    *,
    provider: str = "recorded",
    model: str = "recorded",
) -> dict:
    narrative = transaction.narrative_validation_report
    authority = transaction.validation_report
    candidate = transaction.candidate
    text = candidate.narrative_text if candidate else ""
    contract = transaction.narrative_contract
    patches = (
        transaction.repair_patches.patches
        if transaction.repair_patches
        else []
    )
    slot = next(
        (
            item
            for item in (transaction.context_manifest.slots if transaction.context_manifest else [])
            if item.name == "relevant_long_term_memories"
        ),
        None,
    )
    threads = service.threads.load().threads
    memories = service.memories.load().records
    state = service.states.load()
    style = transaction.style_validation_report or {}
    narrative_codes = [
        item.code for item in (narrative.violations if narrative else [])
    ]
    state_codes = [
        item.code for item in (authority.violations if authority else [])
    ]
    proposal_codes = [
        item.code for item in (authority.proposal_drops if authority else [])
    ]
    completed_event_ids = [
        item.event_id
        for item in (narrative.event_results if narrative else [])
        if item.status == "completed"
    ]
    missing_event_ids = [
        item.event_id
        for item in (narrative.event_results if narrative else [])
        if item.status != "completed"
    ]
    committed_delta = (
        list(authority.validated_delta)
        if authority and transaction.committed
        else []
    )
    validated_delta_keys = {
        item.model_dump_json() for item in (authority.validated_delta if authority else [])
    }
    rejected_delta = [
        item
        for item in (candidate.state_delta if candidate else [])
        if item.model_dump_json() not in validated_delta_keys
    ]
    committed_thread_changes = (
        list(authority.thread_changes)
        if authority and transaction.committed
        else []
    )
    thread_change_counts = {
        action: sum(
            item.action == action for item in committed_thread_changes
        )
        for action in ("opened", "advanced", "resolved")
    }
    memory_selected_ids = list(slot.reference_ids) if slot else []
    item_codes = {
        "ITEM_OWNER_CONFLICT",
        "ITEM_UNKNOWN",
        "ITEM_TARGET_UNKNOWN",
        "ITEM_TRANSFER_UNNARRATED",
    }
    character_codes = {
        "CHARACTER_UNKNOWN",
        "DEAD_CHARACTER_REVIVAL",
        "LOCATION_UNKNOWN",
        "LOCATION_JUMP",
        "NARRATIVE_CHARACTER_ADDED",
    }
    knowledge_codes = {
        "KNOWLEDGE_CHARACTER_UNKNOWN",
        "READER_KNOWLEDGE_REVEALED_AGAIN",
    }
    relationship_codes = {
        code
        for code in [*narrative_codes, *state_codes]
        if "RELATION" in code
    }
    all_codes = [*narrative_codes, *state_codes, *proposal_codes]
    return {
        "section_id": transaction.section_id,
        "transaction_id": transaction.id,
        "phase": transaction.phase,
        "committed": transaction.committed,
        "story_bible_revision": transaction.story_bible_revision,
        "canonical_revision_before": transaction.canonical_state_revision,
        "canonical_revision_after": state.revision,
        "provider": provider,
        "model": model,
        "contract_hash": contract.contract_hash if contract else "",
        "required_events": [
            item.id for item in (contract.required_events if contract else [])
        ],
        "completed_events": completed_event_ids,
        "missing_events": missing_event_ids,
        "end_states": [
            item.model_dump(mode="json")
            for item in (narrative.end_state_results if narrative else [])
        ],
        "contract_result": bool(narrative and narrative.accepted),
        "narrative_contract_pass": bool(narrative and narrative.accepted),
        "narrative_violation_codes": narrative_codes,
        "narrative_validation_history_codes": [
            [item.code for item in report.violations]
            for report in transaction.narrative_validation_history
        ],
        "contract_coverage": narrative.contract_coverage if narrative else 0.0,
        "required_fact_coverage": narrative.required_fact_coverage if narrative else 0.0,
        "required_event_coverage": narrative.required_event_coverage if narrative else 0.0,
        "required_end_state_coverage": (
            narrative.required_end_state_coverage if narrative else 0.0
        ),
        "event_completion": [
            {
                "event_id": item.event_id,
                "status": item.status,
                "actor_matched": item.actor_matched,
                "target_matched": item.target_matched,
                "action_matched": item.action_matched,
                "violation_code": item.violation_code,
            }
            for item in (narrative.event_results if narrative else [])
        ],
        "required_events_completed": sum(
            item.status == "completed"
            for item in (narrative.event_results if narrative else [])
        ),
        "required_events_total": len(narrative.event_results) if narrative else 0,
        "end_states_reached": sum(
            item.reached for item in (narrative.end_state_results if narrative else [])
        ),
        "end_states_total": len(narrative.end_state_results) if narrative else 0,
        "unsupported_entity_count": sum(
            item.code.startswith("NARRATIVE_")
            for item in (narrative.violations if narrative else [])
        ),
        "unsupported_fact_count": len(narrative.unsupported_additions) if narrative else 0,
        "time_constraint_violation_count": sum(
            item.code.startswith("TIME_") or item.code == "CAUSAL_LINK_WEAKENED"
            for item in (narrative.violations if narrative else [])
        ),
        "canonical_revision": state.revision,
        "canonical_state_sha256": hashlib.sha256(
            state.model_dump_json().encode("utf-8")
        ).hexdigest(),
        "delta_count": len(candidate.state_delta) if candidate else 0,
        "proposed_delta": [
            item.model_dump(mode="json")
            for item in (candidate.state_delta if candidate else [])
        ],
        "committed_delta_count": len(committed_delta),
        "committed_delta": [
            item.model_dump(mode="json") for item in committed_delta
        ],
        "rejected_delta": [
            item.model_dump(mode="json") for item in rejected_delta
        ],
        "validated_delta_count": len(authority.validated_delta) if authority else 0,
        "dropped_delta_count": authority.dropped_delta_count if authority else 0,
        "dropped_thread_change_count": (
            authority.dropped_thread_change_count if authority else 0
        ),
        "proposal_drop_codes": proposal_codes,
        "rejected_delta_count": len(candidate.state_delta) - len(authority.validated_delta)
        if candidate and authority
        else 0,
        "evidenceless_state_delta_commits": sum(
            not item.evidence.strip() for item in committed_delta
        ),
        "thread_proposals": {
            "opened": len(candidate.threads_opened) if candidate else 0,
            "advanced": len(candidate.threads_advanced) if candidate else 0,
            "resolved": len(candidate.threads_resolved) if candidate else 0,
        },
        "thread_changes": thread_change_counts,
        "committed_thread_changes": [
            item.model_dump(mode="json") for item in committed_thread_changes
        ],
        "illegal_thread_change_commits": sum(
            (
                item.action == "resolved"
                and not item.thread.resolution_evidence
            )
            or (
                item.action in {"opened", "advanced"}
                and not item.thread.evidence
            )
            for item in committed_thread_changes
        ),
        "state_conflict_count": sum(
            item.severity == "high" for item in (authority.violations if authority else [])
        ),
        "state_violation_codes": state_codes,
        "state_validation_history_codes": [
            [item.code for item in report.violations]
            for report in transaction.validation_history
        ],
        "stale_context_count": int(transaction.phase == "stale_context"),
        "recovery_count": transaction.recovery_count,
        "threads_open": sum(
            item.status not in {"resolved", "abandoned"} for item in threads.values()
        ),
        "threads_advancing": sum(item.status == "advancing" for item in threads.values()),
        "threads_resolved": sum(item.status == "resolved" for item in threads.values()),
        "threads_stale": sum(item.status == "stale" for item in threads.values()),
        "threads_created_per_section": len(candidate.threads_opened) if candidate else 0,
        "threads_opened_count": thread_change_counts["opened"],
        "threads_advanced_count": thread_change_counts["advanced"],
        "threads_resolved_count": thread_change_counts["resolved"],
        "threads_resolved_with_evidence": sum(
            bool(item.resolution_evidence) for item in (candidate.threads_resolved if candidate else [])
        ),
        "main_conflict_progress": int(bool(candidate and candidate.threads_advanced)),
        "memory_records_total": len(memories),
        "memory_records_selected": slot.selected_count if slot else 0,
        "memory_selected_ids": memory_selected_ids,
        "memory_reference_hit": int(bool(memory_selected_ids)),
        "memory_reference_hit_rate": (
            round(len(memory_selected_ids) / max(1, min(12, len(memories))), 4)
            if memories
            else 0.0
        ),
        "relevant_memory_precision_sample": None,
        "memory_records_added": (
            len(candidate.memory_records) + 1
            if candidate and transaction.committed
            else 0
        ),
        "memory_record_ids_added": (
            [
                *[item.id for item in candidate.memory_records],
                f"section_summary_{transaction.section_id}",
            ]
            if candidate and transaction.committed
            else []
        ),
        "memory_growth_per_section": (
            len(candidate.memory_records) + 1
            if candidate and transaction.committed
            else 0
        ),
        "character_continuity_errors": sum(
            code in character_codes for code in all_codes
        ),
        "knowledge_boundary_errors": sum(
            code in knowledge_codes for code in all_codes
        ),
        "relationship_conflicts": len(relationship_codes),
        "item_owner_conflict": sum(
            code == "ITEM_OWNER_CONFLICT" for code in all_codes
        ),
        "item_state_conflict": sum(code in item_codes for code in all_codes),
        "style_contract_pass": style.get("passed"),
        "style_rewrite_rate": int(transaction.repair_performed),
        "style_drift_warning": bool(style.get("findings")),
        "blind_style_classification_accuracy": None,
        "opening_overlap": _overlap(text[:120], previous_text[:120]),
        "consecutive_ngram_overlap": _overlap(text, previous_text),
        "repeated_scene_rate": None,
        "repeated_dialogue_rate": None,
        "same_resolution_pattern_rate": None,
        "narrative_length": sum(not char.isspace() for char in text),
        "section_writing_plan": (
            transaction.section_writing_plan.model_dump(mode="json")
            if transaction.section_writing_plan
            else {}
        ),
        "section_budget_plan": (
            transaction.section_budget_plan.model_dump(mode="json")
            if transaction.section_budget_plan
            else {}
        ),
        "initial_length_report": (
            transaction.initial_length_report.model_dump(mode="json")
            if transaction.initial_length_report
            else {}
        ),
        "final_length_report": (
            transaction.final_length_report.model_dump(mode="json")
            if transaction.final_length_report
            else {}
        ),
        "initial_ending_report": (
            transaction.initial_ending_report.model_dump(mode="json")
            if transaction.initial_ending_report
            else {}
        ),
        "final_ending_report": (
            transaction.final_ending_report.model_dump(mode="json")
            if transaction.final_ending_report
            else {}
        ),
        "final_balance_report": (
            transaction.final_balance_report.model_dump(mode="json")
            if transaction.final_balance_report
            else {}
        ),
        "prompt_tokens": int(transaction.usage.get("prompt_tokens", 0)),
        "completion_tokens": int(transaction.usage.get("completion_tokens", 0)),
        "repair_tokens": int(transaction.usage.get("repair_tokens", 0)),
        "total_tokens": int(transaction.usage.get("total_tokens", 0)),
        "latency_seconds": round(latency, 4),
        "provider_errors": 0,
        "retry_count": 0,
        "writer_calls": transaction.writer_calls,
        "repair_used": transaction.repair_performed,
        "repair_performed": transaction.repair_performed,
        "repair_plan_counts": {
            "missing_events": len(transaction.repair_plan.missing_events),
            "incomplete_events": len(transaction.repair_plan.incomplete_events),
            "wrong_actor_events": len(transaction.repair_plan.wrong_actor_events),
            "wrong_target_events": len(transaction.repair_plan.wrong_target_events),
            "wrong_end_states": len(transaction.repair_plan.wrong_end_states),
            "unsupported_additions": len(transaction.repair_plan.unsupported_additions),
        }
        if transaction.repair_plan
        else {},
        "repair_ignored_fields": list(transaction.repair_ignored_fields),
        "repair_audit_codes": list(transaction.repair_audit_codes),
        "repair_patch_count": (
            len(patches)
        ),
        "repair_patch_insert_count": sum(
            item.patch_type == "insert" for item in patches
        ),
        "repair_patch_replace_count": sum(
            item.patch_type == "replace" for item in patches
        ),
        "repair_patch_delete_count": sum(
            item.patch_type == "delete" for item in patches
        ),
        "repair_patch_expand_count": sum(
            item.patch_type == "expand" for item in patches
        ),
        "repair_patch_compact_count": sum(
            item.patch_type == "compact" for item in patches
        ),
        "repair_patch_target_events": sorted(
            {
                event_id
                for patch in patches
                for event_id in patch.target_events
            }
        ),
        "repair_patch_target_end_states": sorted(
            {
                state_id
                for patch in patches
                for state_id in patch.target_end_states
            }
        ),
        "repair_patch_types": (
            [
                item.patch_type
                for item in transaction.repair_patches.patches
            ]
            if transaction.repair_patches
            else []
        ),
        "repair_patch_accepted": (
            transaction.repair_patch_report.accepted
            if transaction.repair_patch_report
            else None
        ),
        "repair_patch_codes": (
            [
                item.code
                for item in transaction.repair_patch_report.violations
            ]
            if transaction.repair_patch_report
            else []
        ),
        "repair_patch_char_delta": (
            transaction.repair_patch_report.char_delta
            if transaction.repair_patch_report
            else 0
        ),
        "repair_enforced_removals": list(transaction.repair_enforced_removals),
        "repair_enforced_removal_count": len(
            transaction.repair_enforced_removals
        ),
        "repair_success": bool(
            transaction.repair_performed
            and narrative
            and narrative.accepted
            and authority
            and authority.accepted
        ),
    }


def _rejection_evidence(transaction) -> dict[str, Any]:
    candidate = transaction.candidate
    history = list(transaction.candidate_history)
    original = history[0] if history else candidate
    repaired = history[-1] if len(history) >= 2 else candidate
    return {
        "schema_version": 1,
        "section_id": transaction.section_id,
        "transaction_id": transaction.id,
        "phase": transaction.phase,
        "original_narrative": (
            original.narrative_text if original is not None else ""
        ),
        "repair_patches": (
            transaction.repair_patches.model_dump(mode="json")
            if transaction.repair_patches
            else None
        ),
        "repair_patch_report": (
            transaction.repair_patch_report.model_dump(mode="json")
            if transaction.repair_patch_report
            else None
        ),
        "repair_after_narrative": (
            repaired.narrative_text if repaired is not None else ""
        ),
        "final_narrative_report": (
            transaction.narrative_validation_report.model_dump(mode="json")
            if transaction.narrative_validation_report
            else None
        ),
        "narrative_validation_history": [
            item.model_dump(mode="json")
            for item in transaction.narrative_validation_history
        ],
        "final_state_report": (
            transaction.validation_report.model_dump(mode="json")
            if transaction.validation_report
            else None
        ),
        "state_validation_history": [
            item.model_dump(mode="json")
            for item in transaction.validation_history
        ],
        "final_reject_reason": transaction.error,
    }


def _checkpoint(report: dict[str, Any], output_dir: Path, every: int) -> None:
    checkpoint = {
        "schema_version": 1,
        "run_id": report["run_id"],
        "next_section": len(report["sections"]) + 1,
        "committed_transaction_ids": [
            item["transaction_id"] for item in report["sections"] if item["committed"]
        ],
        "total_tokens": report["summary"]["total_tokens"],
        "estimated_cost": report["summary"]["estimated_cost"],
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    _atomic_json(output_dir / "checkpoint.json", checkpoint)
    _atomic_json(output_dir / "report.json", report)
    if report["sections"] and len(report["sections"]) % max(1, every) == 0:
        _atomic_json(
            output_dir / "checkpoints" / f"section_{len(report['sections']):04d}.json",
            checkpoint,
        )


def _real_sample_replay() -> dict[str, Any]:
    from story.models import CanonicalState, SectionGoal, StoryBible
    from story.narrative_contract import NarrativeContractBuilder
    from story.narrative_validator import NarrativeContractValidator
    from tests.narrative_contract_fixtures import (
        lighthouse_constraints,
        real_style_samples,
    )

    contract = NarrativeContractBuilder().build(
        story_bible=StoryBible(
            premise="旧港旧信关系到港难。",
            theme="责任与诚实",
            setting_summary="无超自然力量的旧港灯塔。",
        ),
        canonical_state=CanonicalState(
            world={"locations": [{"id": "lighthouse", "name": "旧灯塔"}]},
            characters={
                "shen_yan": {"name": "沈砚"},
                "lin_qiu": {"name": "林秋"},
            },
        ),
        section_goal=SectionGoal(
            section_id="stage0_real_samples",
            objective="完成固定灯塔交信事件链",
            viewpoint_character_id="shen_yan",
            involved_characters=["shen_yan", "lin_qiu"],
            desired_length=1000,
            narrative_constraints=lighthouse_constraints(),
        ),
        story_threads=[],
    )
    validator = NarrativeContractValidator()
    out = {}
    for style, text in real_style_samples().items():
        report = validator.validate(contract, text)
        out[style] = {
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "accepted": report.accepted,
            "codes": [item.code for item in report.violations],
            "contract_coverage": report.contract_coverage,
        }
    return out


async def _run_recovery_probes(
    output_dir: Path, *, style: str, theme: str
) -> dict[str, Any]:
    """Exercise clean staged recovery and stale staged rejection in isolation."""
    from sections.section_store import _clear_for_tests
    from story.models import StoryBibleUpdate

    results: dict[str, Any] = {}
    clean_dir = output_dir / "probes" / "clean_recovery" / "runtime"
    _clear_for_tests()
    service = _initialise_service(
        clean_dir,
        style=style,
        theme=theme,
        writer=RecordedLongRangeWriter(repair_every=0),
    )
    if not service.transactions.exists("recovery_probe"):
        prepared = service.prepare(
            _goal(1, desired_length=300), request_id="recovery_probe"
        )
        generated = await service.generate(prepared)
        transaction = service._record_generated(prepared.transaction, generated)
        authority_report = service.validate(prepared, generated.candidate)
        service._stage(
            prepared,
            transaction,
            generated.candidate,
            authority_report,
        )
        del service
        _clear_for_tests()
        service = _initialise_service(
            clean_dir,
            style=style,
            theme=theme,
            writer=RecordedLongRangeWriter(repair_every=0),
        )
    recovered = service.transactions.load("recovery_probe")
    results["clean_staged_recovery"] = {
        "passed": recovered.committed
        and recovered.recovery_count == 1
        and service.sections.count() == 1,
        "phase": recovered.phase,
        "recovery_count": recovered.recovery_count,
        "section_count": service.sections.count(),
    }

    stale_dir = output_dir / "probes" / "stale_recovery" / "runtime"
    _clear_for_tests()
    stale_service = _initialise_service(
        stale_dir,
        style=style,
        theme=theme,
        writer=RecordedLongRangeWriter(repair_every=0),
    )
    if not stale_service.transactions.exists("stale_recovery_probe"):
        prepared = stale_service.prepare(
            _goal(1, desired_length=300), request_id="stale_recovery_probe"
        )
        generated = await stale_service.generate(prepared)
        transaction = stale_service._record_generated(prepared.transaction, generated)
        authority_report = stale_service.validate(prepared, generated.candidate)
        stale_service._stage(
            prepared,
            transaction,
            generated.candidate,
            authority_report,
        )
        bible = stale_service.bibles.load()
        stale_service.bibles.update(
            StoryBibleUpdate(
                expected_revision=bible.revision,
                title=bible.title,
                premise=bible.premise,
                theme="恢复前已变更的主题",
                setting_summary=bible.setting_summary,
            )
        )
        del stale_service
        _clear_for_tests()
        stale_service = _initialise_service(
            stale_dir,
            style=style,
            theme=theme,
            writer=RecordedLongRangeWriter(repair_every=0),
        )
    stale = stale_service.transactions.load("stale_recovery_probe")
    results["stale_staged_rejected"] = {
        "passed": stale.phase == "stale_context"
        and stale_service.sections.count() == 0
        and stale_service.states.load().revision == 1,
        "phase": stale.phase,
        "error_code": stale.error_code,
        "section_count": stale_service.sections.count(),
        "canonical_revision": stale_service.states.load().revision,
    }
    return results


async def run_sequence(
    *,
    output_dir: Path,
    mode: str,
    style: str,
    theme: str,
    seed: int,
    desired_length: int,
    checkpoint_every: int,
    limits: RunLimits,
    resume: bool,
    provider: str = "recorded",
    model: str = "recorded",
    runtime_rebuild_every: int | None = None,
    inject_failure: str = "",
    stop_on_gate_failure: bool = False,
) -> dict[str, Any]:
    from sections.section_store import _clear_for_tests
    from story.service import GenerationRejected

    random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"
    expected_identity = {
        "mode": mode,
        "theme": theme,
        "style": style,
        "seed": seed,
        "desired_length": desired_length,
        "provider": provider,
        "model": model,
        "inject_failure": inject_failure,
    }
    rebuild_every = (
        checkpoint_every
        if runtime_rebuild_every is None
        else max(0, runtime_rebuild_every)
    )
    if resume and report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        actual_identity = {
            key: report.get("config", {}).get(key) for key in expected_identity
        }
        if actual_identity != expected_identity:
            raise ValueError(
                "resume configuration mismatch: mode/theme/style/seed/provider/model "
                "and desired_length must match the existing run"
            )
        report["config"].update(
            {
                "max_sections": limits.max_sections,
                "max_total_tokens": limits.max_total_tokens,
                "max_cost": limits.max_cost,
                "checkpoint_every": checkpoint_every,
                "runtime_rebuild_every": rebuild_every,
                "stop_on_gate_failure": stop_on_gate_failure,
            }
        )
        report["summary"]["stop_reason"] = ""
    else:
        report = {
            "schema_version": 1,
            "run_id": f"author-{mode}-{theme}-{style}-{seed}",
            "stage": "stage0" if mode == "recorded" else "real_pilot",
            "evidence_boundary": {
                "deterministic": True,
                "recorded": mode == "recorded",
                "real_provider": mode == "real",
                "human_review": False,
                "llm_judge": False,
            },
            "config": {
                "mode": mode,
                "theme": theme,
                "style": style,
                "seed": seed,
                "desired_length": desired_length,
                "max_sections": limits.max_sections,
                "max_total_tokens": limits.max_total_tokens,
                "max_cost": limits.max_cost,
                "checkpoint_every": checkpoint_every,
                "runtime_rebuild_every": rebuild_every,
                "inject_failure": inject_failure,
                "stop_on_gate_failure": stop_on_gate_failure,
                "provider": provider,
                "model": model,
            },
            "sections": [],
            "failures": [],
            "recovery_evidence": {},
            "real_sample_replay": {},
            "summary": {
                "attempted": 0,
                "committed": 0,
                "contract_pass": 0,
                "repairs": 0,
                "hard_rejects": 0,
                "total_tokens": 0,
                "estimated_cost": 0.0,
                "runtime_rebuilds": 0,
                "provider_errors": 0,
                "stop_reason": "",
            },
        }
    runtime_dir = output_dir / "runtime"
    writer = RecordedLongRangeWriter() if mode == "recorded" else None
    _clear_for_tests()
    service = _initialise_service(
        runtime_dir,
        style=style,
        theme=theme,
        writer=writer,
    )
    previous_text = ""
    existing_sections = service.sections.list_all()
    if existing_sections:
        previous_text = existing_sections[-1].content
    start_index = len(report["sections"]) + 1
    injection_kind = ""
    injection_section = 1
    if inject_failure:
        raw_kind, _, raw_section = inject_failure.partition(":")
        injection_kind = raw_kind.strip().lower()
        if injection_kind not in {"", "provider_error", "runtime_rebuild"}:
            raise ValueError(
                "--inject-failure supports provider_error[:section] or "
                "runtime_rebuild[:section]"
            )
        if raw_section:
            injection_section = max(1, int(raw_section))

    for index in range(start_index, limits.max_sections + 1):
        total_tokens = int(report["summary"]["total_tokens"])
        estimate = desired_length * (6 if mode == "real" else 0)
        if limits.max_total_tokens and total_tokens + estimate > limits.max_total_tokens:
            report["summary"]["stop_reason"] = "max_total_tokens"
            break
        if limits.max_cost and float(report["summary"]["estimated_cost"]) >= limits.max_cost:
            report["summary"]["stop_reason"] = "max_cost"
            break
        goal = _goal(index, desired_length=desired_length)
        started = time.perf_counter()
        request_id, prior_failures = _request_id(index, report["failures"])
        try:
            if injection_kind == "provider_error" and index == injection_section:
                already_injected = any(
                    item.get("injected_failure") == inject_failure
                    for item in report["failures"]
                )
                if not already_injected:
                    raise RuntimeError("injected provider failure")
            transaction = await service.run(goal, request_id=request_id)
        except GenerationRejected as exc:
            transaction = exc.transaction
        except Exception as exc:
            failure = {
                "section": index,
                "attempt": prior_failures + 1,
                "injected_failure": (
                    inject_failure
                    if injection_kind == "provider_error" and index == injection_section
                    else ""
                ),
                **_safe_error(exc),
            }
            report["failures"].append(failure)
            report["summary"]["provider_errors"] += int(mode == "real")
            _atomic_json(
                output_dir
                / "failures"
                / f"section_{index:04d}_attempt_{prior_failures + 1:02d}.json",
                failure,
            )
            report["summary"]["stop_reason"] = "generation_error"
            _checkpoint(report, output_dir, checkpoint_every)
            break
        latency = time.perf_counter() - started
        metrics = _section_metrics(
            transaction,
            service,
            previous_text,
            latency,
            provider=provider,
            model=model,
        )
        rejection_path = (
            Path("rejections")
            / f"section_{index:04d}_{transaction.id}.json"
        )
        metrics["rejection_evidence_file"] = (
            rejection_path.as_posix()
            if transaction.phase == "rejected"
            else ""
        )
        metrics["estimated_cost"] = _estimated_cost(transaction.usage, limits)
        report["sections"].append(metrics)
        report["summary"]["attempted"] += 1
        report["summary"]["committed"] += int(transaction.committed)
        report["summary"]["contract_pass"] += int(metrics["narrative_contract_pass"])
        report["summary"]["repairs"] += int(transaction.repair_performed)
        report["summary"]["hard_rejects"] += int(transaction.phase == "rejected")
        report["summary"]["total_tokens"] += metrics["total_tokens"]
        report["summary"]["estimated_cost"] = round(
            report["summary"]["estimated_cost"] + metrics["estimated_cost"], 8
        )
        if transaction.candidate:
            current_text = transaction.candidate.narrative_text
            _atomic_text(
                output_dir / "samples" / f"section_{index:04d}.txt",
                current_text,
            )
            if transaction.repair_performed and transaction.candidate_history:
                _atomic_text(
                    output_dir / "samples" / f"section_{index:04d}_repair_before.txt",
                    transaction.candidate_history[0].narrative_text,
                )
                _atomic_text(
                    output_dir / "samples" / f"section_{index:04d}_repair_after.txt",
                    current_text,
                )
            if transaction.committed:
                previous_text = current_text
        if transaction.phase == "rejected":
            _atomic_json(
                output_dir / rejection_path,
                _rejection_evidence(transaction),
            )
        _checkpoint(report, output_dir, checkpoint_every)
        if stop_on_gate_failure and (
            not transaction.committed
            or not metrics["narrative_contract_pass"]
            or metrics["state_conflict_count"]
        ):
            report["summary"]["stop_reason"] = "gate_failure"
            break
        if limits.max_total_tokens and report["summary"]["total_tokens"] >= limits.max_total_tokens:
            report["summary"]["stop_reason"] = "max_total_tokens"
            break
        if limits.max_cost and report["summary"]["estimated_cost"] >= limits.max_cost:
            report["summary"]["stop_reason"] = "max_cost"
            break
        injected_rebuild = (
            injection_kind == "runtime_rebuild" and index == injection_section
        )
        scheduled_rebuild = bool(rebuild_every and index % rebuild_every == 0)
        if (injected_rebuild or scheduled_rebuild) and index < limits.max_sections:
            del service
            _clear_for_tests()
            writer = RecordedLongRangeWriter() if mode == "recorded" else None
            service = _initialise_service(
                runtime_dir,
                style=style,
                theme=theme,
                writer=writer,
            )
            report["summary"]["runtime_rebuilds"] += 1

    if mode == "recorded":
        report["real_sample_replay"] = _real_sample_replay()
        report["recovery_evidence"] = {
            "runtime_rebuilds": report["summary"]["runtime_rebuilds"],
            "section_ids_unique": len({item["section_id"] for item in report["sections"]})
            == len(report["sections"]),
            "canonical_revision_contiguous": service.states.load().revision
            == 1 + report["summary"]["committed"],
        }
        report["recovery_evidence"].update(
            await _run_recovery_probes(output_dir, style=style, theme=theme)
        )
    report["summary"]["contract_pass_rate"] = round(
        report["summary"]["contract_pass"] / report["summary"]["attempted"], 4
    ) if report["summary"]["attempted"] else 0.0
    report["summary"]["repair_rate"] = round(
        report["summary"]["repairs"] / report["summary"]["attempted"], 4
    ) if report["summary"]["attempted"] else 0.0
    report["summary"]["completed_at"] = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )
    _checkpoint(report, output_dir, checkpoint_every)
    secret = os.environ.get("CUSTOM_API_KEY", "")
    rendered = json.dumps(report, ensure_ascii=False)
    if secret and secret in rendered:
        raise RuntimeError("credential leak guard rejected long-range report")
    return report


def _configure_real_provider(args: argparse.Namespace) -> dict[str, str]:
    from validate_styles import _configure_provider

    provider = _configure_provider(args.provider_file.resolve())
    if args.model:
        os.environ["CUSTOM_MODEL"] = args.model
    if args.provider and args.provider != "custom":
        raise ValueError("--provider currently accepts custom for provider-file isolation")
    os.environ.setdefault("LLM_MAX_RETRIES", "1")
    print(
        json.dumps(
            {
                "provider": provider["provider"],
                "model": args.model or provider["model"],
                "credential_persisted": False,
            },
            ensure_ascii=False,
        )
    )
    return {
        "provider": str(provider["provider"]),
        "model": str(args.model or provider["model"]),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("recorded", "real"), default="recorded")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--checkpoint-every", type=int, default=5)
    parser.add_argument(
        "--runtime-rebuild-every",
        type=int,
        default=0,
        help="rebuild the runtime every N attempts; 0 follows checkpoint cadence",
    )
    parser.add_argument(
        "--inject-failure",
        default="",
        help="provider_error[:section] or runtime_rebuild[:section]",
    )
    parser.add_argument("--stop-on-gate-failure", action="store_true")
    parser.add_argument("--max-sections", type=int, default=20)
    parser.add_argument("--max-total-tokens", type=int, default=0)
    parser.add_argument("--max-cost", type=float, default=0.0)
    parser.add_argument("--provider", default="custom")
    parser.add_argument("--provider-file", type=Path, default=ROOT / "coding.txt")
    parser.add_argument("--model", default="")
    parser.add_argument("--theme", default=DEFAULT_THEMES.split(",")[0])
    parser.add_argument("--style", default=DEFAULT_STYLES.split(",")[0])
    parser.add_argument("--seed", type=int, default=20260722)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--desired-length", type=int, default=400)
    parser.add_argument("--prompt-cost-per-million", type=float, default=0.0)
    parser.add_argument("--completion-cost-per-million", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    provider_metadata = {"provider": "recorded", "model": "recorded"}
    if args.mode == "real":
        provider_metadata = _configure_real_provider(args)
    limits = RunLimits(
        max_sections=max(1, args.max_sections),
        max_total_tokens=max(0, args.max_total_tokens),
        max_cost=max(0.0, args.max_cost),
        prompt_cost_per_million=max(0.0, args.prompt_cost_per_million),
        completion_cost_per_million=max(0.0, args.completion_cost_per_million),
    )
    report = asyncio.run(
        run_sequence(
            output_dir=args.output_dir.resolve(),
            mode=args.mode,
            style=args.style,
            theme=args.theme,
            seed=args.seed,
            desired_length=max(200, args.desired_length),
            checkpoint_every=max(1, args.checkpoint_every),
            limits=limits,
            resume=args.resume,
            provider=provider_metadata["provider"],
            model=provider_metadata["model"],
            runtime_rebuild_every=(
                None if args.runtime_rebuild_every <= 0 else args.runtime_rebuild_every
            ),
            inject_failure=args.inject_failure,
            stop_on_gate_failure=args.stop_on_gate_failure,
        )
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if not report["summary"]["stop_reason"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
