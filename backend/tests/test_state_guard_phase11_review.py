from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.run_blind_state_guard_review import (
    build_probe_messages,
    execute_sharded_checkpoint,
)
from scripts.state_guard_review_workflow import (
    PRODUCTION_FEATURE_DEFAULTS,
    atomic_write_json,
    build_partial_review_gate,
    build_review_tasks,
    create_task_checkpoint,
    export_human_review_package,
    file_hash,
    freeze_file,
    import_human_review,
    load_blind_packet,
    merge_review_parts,
    require_real_replay_gate,
    stable_hash,
)


ROOT = Path(__file__).resolve().parents[2]
PACKET_PATH = (
    ROOT
    / "docs"
    / "iter"
    / "state_guard_adjudication"
    / "phase9-blind-packet-v1.json"
)


def _packet() -> dict:
    return load_blind_packet(PACKET_PATH)


def _result(case_id: str, decision: str = "accept") -> dict:
    reject = decision == "reject"
    return {
        "case_id": case_id,
        "endpoint_complete": not reject,
        "ungrounded_change": False,
        "ledger_matches": True,
        "knowledge_leak": False,
        "repair_changed_fact": False,
        "decision": decision,
        "error_types": ["event_endpoint_unfulfilled"] if reject else [],
        "confidence": 0.9,
        "rationale": "根据正文终态与账本作出的独立判断。",
    }


def _reply(results: list[dict], *, usage: int = 10) -> dict:
    content = (
        json.dumps(results[0], ensure_ascii=False)
        if len(results) == 1
        else json.dumps({"results": results}, ensure_ascii=False)
    )
    return {
        "content": content,
        "usage": {
            "input_tokens": max(usage - 2, 0),
            "output_tokens": min(2, usage),
            "total_tokens": usage,
        },
    }


def _checkpoint(tmp_path: Path, *, batch_size: int = 1, reviewer_id: str = "reviewer-a"):
    checkpoint = tmp_path / reviewer_id
    index = create_task_checkpoint(
        PACKET_PATH,
        checkpoint,
        reviewer_id=reviewer_id,
        reviewer_type="independent_model",
        batch_size=batch_size,
        shuffle_seed=17,
        prompt_hash="a" * 64,
    )
    atomic_write_json(checkpoint / "packet.ref.json", _packet())
    return checkpoint, index


def _part(packet: dict, reviewer_id: str, case_ids: list[str]) -> dict:
    results = [
        _result(case_id, "accept" if index < 12 else "reject")
        for index, case_id in enumerate(case_ids)
    ]
    part = {
        "schema_version": "state-guard-partial-review-v1",
        "packet_id": packet["packet_id"],
        "packet_hash": packet["packet_sha256"],
        "reviewer_id": reviewer_id,
        "reviewer_type": "human",
        "evidence_mode": "human",
        "model_family": "",
        "model_name": "",
        "provider_name": "",
        "blind_key_accessed": False,
        "review_started_at": "2026-07-21T01:00:00Z",
        "review_finished_at": "2026-07-21T02:00:00Z",
        "source": {"fixture": "test-only"},
        "results": results,
        "usage": {
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "uncertain_usage_upper_bound": 0,
        },
    }
    part["part_id"] = f"part-{stable_hash(part)[:16]}"
    part["part_sha256"] = stable_hash(part)
    return part


def _merged(packet: dict, reviewer_id: str, decisions: list[str] | None = None) -> dict:
    case_ids = [case["case_id"] for case in packet["cases"]]
    if decisions is None:
        decisions = ["accept"] * 12 + ["reject"] * 13
    results = [_result(case_id, decision) for case_id, decision in zip(case_ids, decisions)]
    coverage = {
        "reviewer_id": reviewer_id,
        "completed": len(results),
        "missing": len(case_ids) - len(results),
        "missing_case_ids": case_ids[len(results) :],
        "decisive": sum(row["decision"] != "ambiguous" for row in results),
        "accepts": sum(row["decision"] == "accept" for row in results),
        "rejects": sum(row["decision"] == "reject" for row in results),
        "ambiguous": sum(row["decision"] == "ambiguous" for row in results),
        "valid_for_gate": len(results) >= 20,
    }
    coverage["coverage_sha256"] = stable_hash(coverage)
    review = {
        "schema_version": "state-guard-merged-review-v1",
        "packet_id": packet["packet_id"],
        "packet_hash": packet["packet_sha256"],
        "reviewer_id": reviewer_id,
        "reviewer_type": "human",
        "evidence_mode": "human",
        "model_family": "",
        "model_name": "",
        "provider_name": "",
        "blind_key_accessed": False,
        "review_started_at": "2026-07-21T01:00:00Z",
        "review_finished_at": "2026-07-21T02:00:00Z",
        "part_sources": [],
        "coverage": coverage,
        "usage": {
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "uncertain_usage_upper_bound": 0,
        },
        "results": results,
    }
    review["review_sha256"] = stable_hash(review)
    return review


@pytest.mark.parametrize("batch_size,expected", [(1, 25), (2, 13), (3, 9)])
def test_packet_stably_splits_into_one_to_three_case_tasks(batch_size, expected) -> None:
    packet = _packet()
    first_tasks, first_index = build_review_tasks(
        packet,
        reviewer_id="stable-reviewer",
        reviewer_type="human",
        batch_size=batch_size,
        shuffle_seed=99,
        prompt_hash="b" * 64,
        created_at="2026-07-21T01:00:00Z",
    )
    second_tasks, second_index = build_review_tasks(
        packet,
        reviewer_id="stable-reviewer",
        reviewer_type="human",
        batch_size=batch_size,
        shuffle_seed=99,
        prompt_hash="b" * 64,
        created_at="2026-07-22T01:00:00Z",
    )

    assert len(first_tasks) == expected
    assert all(1 <= len(task["case_ids"]) <= 3 for task in first_tasks)
    assert [task["task_id"] for task in first_tasks] == [
        task["task_id"] for task in second_tasks
    ]
    assert [task["task_sha256"] for task in first_tasks] == [
        task["task_sha256"] for task in second_tasks
    ]
    assert first_index["definition_sha256"] == second_index["definition_sha256"]


def test_one_invalid_case_does_not_discard_valid_sibling(tmp_path) -> None:
    checkpoint, index = _checkpoint(tmp_path, batch_size=2)
    case_a, case_b = index["tasks"][0]["case_ids"]
    bad = _result(case_b)
    bad["confidence"] = 2
    calls = iter([_reply([_result(case_a), bad])])

    final, _ = execute_sharded_checkpoint(
        checkpoint,
        call_fn=lambda messages, tokens: next(calls),
        evidence_mode="recorded",
        authorized_budget=0,
        max_calls=1,
        max_input_tokens=100,
        max_output_tokens=100,
        retry_invalid=False,
        resume=False,
    )

    first = final["tasks"][0]
    assert first["case_statuses"][case_a] == "complete"
    assert first["case_statuses"][case_b] == "invalid"
    assert (checkpoint / "completed" / f"{case_a}.json").is_file()
    assert not (checkpoint / "completed" / f"{case_b}.json").exists()


def test_resume_never_repeats_completed_case(tmp_path) -> None:
    checkpoint, index = _checkpoint(tmp_path)
    first_case = index["tasks"][0]["case_ids"][0]
    execute_sharded_checkpoint(
        checkpoint,
        call_fn=lambda messages, tokens: _reply([_result(first_case)]),
        evidence_mode="recorded",
        authorized_budget=0,
        max_calls=1,
        max_input_tokens=100,
        max_output_tokens=100,
        retry_invalid=False,
        resume=False,
    )
    seen: list[str] = []

    def second_call(messages, tokens):
        seen.append(messages[-1]["content"])
        payload = json.loads(messages[-1]["content"])
        case_id = payload["cases"][0]["case_id"]
        return _reply([_result(case_id)])

    execute_sharded_checkpoint(
        checkpoint,
        call_fn=second_call,
        evidence_mode="recorded",
        authorized_budget=0,
        max_calls=2,
        max_input_tokens=100,
        max_output_tokens=100,
        retry_invalid=False,
        resume=True,
    )
    assert seen
    assert all(first_case not in prompt for prompt in seen)


def test_provider_probe_contains_no_blind_case() -> None:
    packet_text = PACKET_PATH.read_text(encoding="utf-8")
    messages = build_probe_messages()
    probe = json.dumps(messages, ensure_ascii=False)
    assert "sg-" not in probe
    assert all(case["prose"] not in probe for case in json.loads(packet_text)["cases"])


def test_empty_final_content_marks_only_current_task_provider_failed(tmp_path) -> None:
    checkpoint, _ = _checkpoint(tmp_path)
    final, _ = execute_sharded_checkpoint(
        checkpoint,
        call_fn=lambda messages, tokens: {
            "content": "",
            "usage": {"input_tokens": 1, "output_tokens": 0, "total_tokens": 1},
        },
        evidence_mode="recorded",
        authorized_budget=0,
        max_calls=1,
        max_input_tokens=100,
        max_output_tokens=100,
        retry_invalid=True,
        resume=False,
    )
    assert final["tasks"][0]["status"] == "provider_failed"
    assert final["tasks"][1]["status"] == "pending"


def test_malformed_batch_retries_only_current_cases_and_keeps_valid_result(tmp_path) -> None:
    checkpoint, index = _checkpoint(tmp_path, batch_size=2)
    case_a, case_b = index["tasks"][0]["case_ids"]
    invalid = _result(case_b)
    invalid.pop("ledger_matches")
    prompts: list[str] = []
    replies = iter([_reply([_result(case_a), invalid]), _reply([_result(case_b)])])

    def call(messages, tokens):
        prompts.append(messages[-1]["content"])
        return next(replies)

    final, _ = execute_sharded_checkpoint(
        checkpoint,
        call_fn=call,
        evidence_mode="recorded",
        authorized_budget=0,
        max_calls=2,
        max_input_tokens=100,
        max_output_tokens=100,
        retry_invalid=True,
        resume=False,
    )
    assert final["tasks"][0]["status"] == "complete"
    assert case_a in prompts[0] and case_b in prompts[0]
    assert case_b in prompts[1] and case_a not in prompts[1]
    assert all(
        marker not in prompts[1].casefold()
        for marker in ("expected_final_decision", "baseline_decision", "blind-key")
    )


def test_each_case_gets_at_most_one_format_retry(tmp_path) -> None:
    checkpoint, _ = _checkpoint(tmp_path)
    calls = 0

    def malformed(messages, tokens):
        nonlocal calls
        calls += 1
        return {"content": "not-json", "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}

    final, _ = execute_sharded_checkpoint(
        checkpoint,
        call_fn=malformed,
        evidence_mode="recorded",
        authorized_budget=0,
        max_calls=10,
        max_input_tokens=100,
        max_output_tokens=100,
        retry_invalid=True,
        resume=False,
    )
    assert calls >= 2
    assert final["tasks"][0]["attempts"] == 1
    assert next(iter(final["tasks"][0]["case_attempts"].values())) == 2
    assert final["tasks"][0]["status"] == "needs_human_review"


def test_budget_85_percent_stops_opening_new_tasks(tmp_path) -> None:
    checkpoint, index = _checkpoint(tmp_path)
    first_case = index["tasks"][0]["case_ids"][0]
    calls = 0

    def provider(messages, tokens):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "content": '{"probe":"ok","json_supported":true,"length_probe":"0123456789"}',
                "usage": {"input_tokens": 3500, "output_tokens": 3500, "total_tokens": 7000},
            }
        return _reply([_result(first_case)], usage=1500)

    final, _ = execute_sharded_checkpoint(
        checkpoint,
        call_fn=provider,
        evidence_mode="provider",
        authorized_budget=10_000,
        max_calls=20,
        max_input_tokens=100,
        max_output_tokens=100,
        retry_invalid=False,
        resume=False,
    )
    assert calls == 2
    assert final["budget"]["warning_70_percent"] is True
    assert final["budget"]["stop_opening_new_cases_85_percent"] is True
    assert final["usage"]["completed_cases"] == 1


def test_unknown_provider_call_uses_conservative_bound(tmp_path) -> None:
    checkpoint, _ = _checkpoint(tmp_path)

    def fails(messages, tokens):
        raise TimeoutError("test timeout")

    final, code = execute_sharded_checkpoint(
        checkpoint,
        call_fn=fails,
        evidence_mode="provider",
        authorized_budget=10_000,
        max_calls=2,
        max_input_tokens=120,
        max_output_tokens=80,
        retry_invalid=False,
        resume=False,
    )
    assert code == 4
    assert final["budget"]["uncertain_usage_upper_bound"] == 200
    assert final["usage"]["provider_calls"] == 1


def test_zero_new_budget_blocks_before_provider_call(tmp_path) -> None:
    checkpoint, _ = _checkpoint(tmp_path)
    calls = 0

    def forbidden_call(messages, tokens):
        nonlocal calls
        calls += 1
        raise AssertionError("must not be called")

    final, code = execute_sharded_checkpoint(
        checkpoint,
        call_fn=forbidden_call,
        evidence_mode="provider",
        authorized_budget=0,
        max_calls=100,
        max_input_tokens=6000,
        max_output_tokens=800,
        retry_invalid=True,
        resume=False,
    )
    assert code == 3
    assert calls == 0
    assert final["usage"]["provider_calls"] == 0
    assert final["budget"]["old_spent_budget_upper_bound"] == 62140


def test_human_markdown_csv_and_json_do_not_leak_labels(tmp_path) -> None:
    package = tmp_path / "human"
    manifest = export_human_review_package(
        PACKET_PATH, package, reviewer_id="human-a", shuffle_seed=4
    )
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in package.iterdir()
        if path.suffix in {".md", ".csv", ".json"}
    ).casefold()
    assert manifest["reviewer_type"] == "human"
    assert manifest["case_count"] == 25
    assert all(
        marker not in combined
        for marker in (
            "expected_final_decision",
            "baseline_decision",
            "candidate_decision",
            "verifier_safe",
            "phase9-hn-",
            "phase9-fp-",
        )
    )


def test_human_package_text_hash_is_crlf_portable(tmp_path) -> None:
    path = tmp_path / "instructions.md"
    path.write_bytes("第一行\n第二行\n".encode("utf-8"))
    lf_hash = file_hash(path)
    path.write_bytes("第一行\r\n第二行\r\n".encode("utf-8"))
    assert file_hash(path) == lf_hash


def test_filled_human_csv_import_validates_complete_coverage(tmp_path) -> None:
    package = tmp_path / "human"
    manifest = export_human_review_package(
        PACKET_PATH, package, reviewer_id="human-a", shuffle_seed=4
    )
    with (package / "review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "case_id", "endpoint_complete", "ungrounded_change", "ledger_matches",
            "knowledge_leak", "repair_changed_fact", "decision", "error_types",
            "confidence", "rationale",
        ))
        writer.writeheader()
        for case_id in manifest["case_ids"]:
            row = _result(case_id)
            writer.writerow(row)
    part = import_human_review(package, package / "review.csv")
    assert part["reviewer_type"] == "human"
    assert len(part["results"]) == 25
    assert part["usage"]["provider_calls"] == 0


def test_partial_reviewer_files_merge_and_report_coverage(tmp_path) -> None:
    packet = _packet()
    ids = [case["case_id"] for case in packet["cases"]]
    first = _part(packet, "human-a", ids[:11])
    second = _part(packet, "human-a", ids[11:21])
    first_path, second_path = tmp_path / "a1.json", tmp_path / "a2.json"
    atomic_write_json(first_path, first)
    atomic_write_json(second_path, second)
    merged, coverage = merge_review_parts(PACKET_PATH, [first_path, second_path])
    assert coverage["completed"] == 21
    assert coverage["missing"] == 4
    assert coverage["decisive"] == 21
    assert coverage["valid_for_gate"] is True
    assert len(merged["part_sources"]) == 2


def test_duplicate_case_across_partial_files_is_rejected(tmp_path) -> None:
    packet = _packet()
    case_id = packet["cases"][0]["case_id"]
    paths = []
    for name in ("a1.json", "a2.json"):
        path = tmp_path / name
        atomic_write_json(path, _part(packet, "human-a", [case_id]))
        paths.append(path)
    with pytest.raises(ValueError, match="duplicate case"):
        merge_review_parts(PACKET_PATH, paths)


def test_partial_reviewer_metadata_mismatch_is_rejected(tmp_path) -> None:
    packet = _packet()
    ids = [case["case_id"] for case in packet["cases"]]
    paths = []
    for name, reviewer, case_id in (
        ("a.json", "human-a", ids[0]),
        ("b.json", "human-b", ids[1]),
    ):
        path = tmp_path / name
        atomic_write_json(path, _part(packet, reviewer, [case_id]))
        paths.append(path)
    with pytest.raises(ValueError, match="metadata mismatch"):
        merge_review_parts(PACKET_PATH, paths)


def test_gold_hash_is_stable_for_same_frozen_reviews() -> None:
    packet = _packet()
    reviews = [_merged(packet, "human-b"), _merged(packet, "human-a")]
    first = build_partial_review_gate(packet, reviews)
    second = build_partial_review_gate(packet, list(reversed(reviews)))
    assert first[2]["gold_sha256"] == second[2]["gold_sha256"]
    assert first[0]["review_gate"]["passed"] is True


def test_frozen_gold_cannot_be_silently_overwritten(tmp_path) -> None:
    path = tmp_path / "gold.json"
    freeze_file(path, {"value": 1})
    freeze_file(path, {"value": 1})
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        freeze_file(path, {"value": 2})


def test_real_replay_gate_rejects_blocked_report(tmp_path) -> None:
    path = tmp_path / "gate.json"
    atomic_write_json(
        path,
        {"review_gate": {"passed": False, "decision": "BLOCK_REAL_REPLAY"}},
    )
    with pytest.raises(PermissionError, match="BLOCK_REAL_REPLAY"):
        require_real_replay_gate(path)


def test_typed_and_canonical_feature_defaults_remain_disabled() -> None:
    assert PRODUCTION_FEATURE_DEFAULTS == {
        "STATE_GUARD_TYPED_DECISION_ENABLE": False,
        "STATE_GUARD_CANONICAL_FACTS_ENABLE": False,
    }


def test_any_hard_contradiction_accept_fails_gate() -> None:
    packet = _packet()
    reviews = [_merged(packet, "human-a"), _merged(packet, "human-b")]
    hard_case = packet["cases"][0]["case_id"]
    report, _, _ = build_partial_review_gate(
        packet,
        reviews,
        hard_contradiction_case_ids={hard_case},
    )
    check = report["review_gate"]["checks"]["hard_contradictions_accepted"]
    assert check["passed"] is False
    assert check["case_ids"] == [hard_case]
    assert report["review_gate"]["decision"] == "BLOCK_REAL_REPLAY"


def test_recorded_response_transport_is_not_valid_independent_evidence(tmp_path) -> None:
    packet = _packet()
    review = _merged(packet, "model-a")
    review["reviewer_type"] = "independent_model"
    review["evidence_mode"] = "recorded"
    review["model_family"] = "fixture"
    review["model_name"] = "fixture"
    review.pop("review_sha256")
    review["review_sha256"] = stable_hash(review)
    with pytest.raises(ValueError, match="mock/recorded"):
        build_partial_review_gate(packet, [review, _merged(packet, "human-b")])
