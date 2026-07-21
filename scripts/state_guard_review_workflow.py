"""Phase 11 primitives for sharded and human StateGuard review.

This module never loads an adjudication key or provider secret.  It owns only the
label-blind packet boundary, deterministic task definitions, local result schemas,
human package validation, partial-review merging and independent-review Gate.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import random
import re
import statistics
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TASK_SCHEMA = "state-guard-blind-review-task-v1"
INDEX_SCHEMA = "state-guard-blind-review-index-v1"
CASE_RESULT_SCHEMA = "state-guard-blind-review-case-result-v1"
PART_SCHEMA = "state-guard-partial-review-v1"
MERGED_SCHEMA = "state-guard-merged-review-v1"
HUMAN_PACKAGE_SCHEMA = "state-guard-human-review-package-v1"
GOLD_SCHEMA = "state-guard-gold-labels-v1"

DECISIONS = ("accept", "reject", "ambiguous")
REVIEWER_TYPES = ("human", "independent_model", "project_agent")
EVIDENCE_MODES = ("human", "provider", "recorded", "mock")
TASK_STATUSES = {
    "pending",
    "running",
    "complete",
    "invalid",
    "provider_failed",
    "budget_blocked",
    "needs_human_review",
}
ALLOWED_ERROR_TYPES = (
    "event_endpoint_unfulfilled",
    "location_mismatch",
    "item_holder_conflict",
    "item_condition_conflict",
    "knowledge_leak",
    "new_ungrounded_fact",
    "ledger_wrong_type",
    "ledger_missing_field",
    "repair_fact_change",
    "evidence_extraction_failure",
    "reasonable_omission",
)
FORBIDDEN_REVIEW_MARKERS = (
    "hard_negative",
    "probable_fp",
    "expected_accept",
    "expected_reject",
    "expected_final_decision",
    "baseline_decision",
    "candidate_decision",
    "final_decision",
    "verifier_safe",
    "deterministic_gate",
    "typed_candidate",
)
PRODUCTION_FEATURE_DEFAULTS = {
    "STATE_GUARD_TYPED_DECISION_ENABLE": False,
    "STATE_GUARD_CANONICAL_FACTS_ENABLE": False,
}
QUESTION_FIELDS = (
    "endpoint_complete",
    "ungrounded_change",
    "ledger_matches",
    "knowledge_leak",
    "repair_changed_fact",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def file_hash(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.casefold() in {".md", ".csv", ".json", ".txt"}:
        # Git may materialize text as CRLF on Windows.  Review-package integrity is
        # content based, so normalize line endings before hashing on every platform.
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.remove(temp_name)
        except OSError:
            pass
        raise


def validate_hashed_payload(
    payload: dict[str, Any], hash_field: str, label: str
) -> str:
    without_hash = dict(payload)
    stored = without_hash.pop(hash_field, None)
    if not stored or stored != stable_hash(without_hash):
        raise ValueError(f"{label} hash mismatch")
    return str(stored)


def assert_label_blind(value: Any, *, label: str = "review artifact") -> None:
    text = json.dumps(value, ensure_ascii=False).casefold()
    leaked = [marker for marker in FORBIDDEN_REVIEW_MARKERS if marker in text]
    if leaked:
        raise ValueError(f"{label} leaks forbidden markers: {leaked}")


def load_blind_packet(path: Path) -> dict[str, Any]:
    packet = json.loads(path.read_text(encoding="utf-8"))
    if packet.get("schema_version") != "state-guard-adjudication-packet-v1":
        raise ValueError("unsupported blind packet schema")
    validate_hashed_payload(packet, "packet_sha256", "blind packet")
    cases = packet.get("cases") or []
    case_ids = [str(case.get("case_id") or "") for case in cases]
    if not case_ids or any(not value for value in case_ids):
        raise ValueError("blind packet contains an empty case ID")
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("blind packet contains duplicate case IDs")
    if packet.get("case_count") != len(cases):
        raise ValueError("blind packet case_count mismatch")
    assert_label_blind(packet, label="blind packet")
    return packet


class ReviewCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    endpoint_complete: bool | None
    ungrounded_change: bool | None
    ledger_matches: bool | None
    knowledge_leak: bool | None
    repair_changed_fact: bool | None
    decision: str
    error_types: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        if value not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        return value

    @field_validator("error_types")
    @classmethod
    def validate_error_types(cls, values: list[str]) -> list[str]:
        unknown = sorted(set(values) - set(ALLOWED_ERROR_TYPES))
        if unknown:
            raise ValueError(f"unknown error types: {unknown}")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_decisive_questions(self) -> "ReviewCaseResult":
        required = (
            self.endpoint_complete,
            self.ungrounded_change,
            self.ledger_matches,
            self.knowledge_leak,
        )
        if self.decision != "ambiguous" and any(value is None for value in required):
            raise ValueError("decisive result requires four non-repair booleans")
        return self


def validate_model_case_result(
    payload: dict[str, Any], expected_case_id: str
) -> dict[str, Any]:
    result = ReviewCaseResult.model_validate(payload)
    if result.case_id != expected_case_id:
        raise ValueError(
            f"case ID mismatch: expected {expected_case_id}, got {result.case_id}"
        )
    if any(getattr(result, field) is None for field in QUESTION_FIELDS):
        raise ValueError("model result requires all five boolean questions")
    return result.model_dump(mode="json")


def _task_hash_payload(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in task.items()
        if key not in {"created_at", "task_sha256"}
    }


def _index_definition_payload(index: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": index["schema_version"],
        "packet_id": index["packet_id"],
        "packet_hash": index["packet_hash"],
        "reviewer_id": index["reviewer_id"],
        "reviewer_type": index["reviewer_type"],
        "batch_size": index["batch_size"],
        "shuffle_seed": index["shuffle_seed"],
        "prompt_hash": index["prompt_hash"],
        "tasks": [
            {
                "task_id": row["task_id"],
                "case_ids": row["case_ids"],
                "input_path": row["input_path"],
                "input_sha256": row["input_sha256"],
            }
            for row in index["tasks"]
        ],
    }


def refresh_index_hashes(index: dict[str, Any]) -> dict[str, Any]:
    index.pop("definition_sha256", None)
    index.pop("checkpoint_sha256", None)
    index["definition_sha256"] = stable_hash(_index_definition_payload(index))
    index["checkpoint_sha256"] = stable_hash(index)
    return index


def validate_task_index(index: dict[str, Any]) -> None:
    if index.get("schema_version") != INDEX_SCHEMA:
        raise ValueError("unsupported task index schema")
    checkpoint = dict(index)
    stored_checkpoint = checkpoint.pop("checkpoint_sha256", None)
    if stored_checkpoint != stable_hash(checkpoint):
        raise ValueError("task index checkpoint hash mismatch")
    if index.get("definition_sha256") != stable_hash(
        _index_definition_payload(index)
    ):
        raise ValueError("task index definition hash mismatch")
    if index.get("task_count") != len(index.get("tasks") or []):
        raise ValueError("task index task_count mismatch")
    if any(row.get("status") not in TASK_STATUSES for row in index["tasks"]):
        raise ValueError("task index contains an invalid status")


def build_review_tasks(
    packet: dict[str, Any],
    *,
    reviewer_id: str,
    reviewer_type: str,
    batch_size: int = 1,
    shuffle_seed: int = 0,
    prompt_hash: str,
    created_at: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if reviewer_type not in REVIEWER_TYPES:
        raise ValueError(f"unsupported reviewer type: {reviewer_type}")
    if not reviewer_id or len(reviewer_id) < 3:
        raise ValueError("reviewer_id must contain at least three characters")
    if batch_size not in {1, 2, 3}:
        raise ValueError("batch_size must be 1, 2 or 3")
    cases = list(packet.get("cases") or [])
    seed_material = (
        f"{packet['packet_sha256']}|{reviewer_id}|{reviewer_type}|"
        f"{batch_size}|{shuffle_seed}"
    )
    randomizer = random.Random(int(hashlib.sha256(seed_material.encode()).hexdigest()[:16], 16))
    randomizer.shuffle(cases)
    created = created_at or now_utc()
    tasks: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    for offset in range(0, len(cases), batch_size):
        group = cases[offset : offset + batch_size]
        case_ids = [case["case_id"] for case in group]
        questions = list(group[0].get("questions") or [])
        task_cases = [
            {key: value for key, value in case.items() if key != "questions"}
            for case in group
        ]
        task_identity = stable_hash(
            {
                "packet_hash": packet["packet_sha256"],
                "reviewer_id": reviewer_id,
                "reviewer_type": reviewer_type,
                "batch_size": batch_size,
                "shuffle_seed": shuffle_seed,
                "case_ids": case_ids,
            }
        )
        task_id = f"brt-{task_identity[:16]}"
        task = {
            "schema_version": TASK_SCHEMA,
            "packet_id": packet["packet_id"],
            "packet_hash": packet["packet_sha256"],
            "task_id": task_id,
            "reviewer_id": reviewer_id,
            "reviewer_type": reviewer_type,
            "case_ids": case_ids,
            "cases": task_cases,
            "questions": questions,
            "prompt_hash": prompt_hash,
            "created_at": created,
        }
        task["task_sha256"] = stable_hash(_task_hash_payload(task))
        assert_label_blind(task, label=f"task {task_id}")
        tasks.append(task)
        input_path = f"tasks/{task_id}.json"
        index_rows.append(
            {
                "task_id": task_id,
                "case_ids": case_ids,
                "status": "pending",
                "input_path": input_path,
                "input_sha256": task["task_sha256"],
                "result_path": None,
                "result_paths": {},
                "attempts": 0,
                "invalid_attempts": 0,
                "case_attempts": {case_id: 0 for case_id in case_ids},
                "case_statuses": {case_id: "pending" for case_id in case_ids},
                "last_error": None,
            }
        )
    index = {
        "schema_version": INDEX_SCHEMA,
        "packet_id": packet["packet_id"],
        "packet_hash": packet["packet_sha256"],
        "reviewer_id": reviewer_id,
        "reviewer_type": reviewer_type,
        "batch_size": batch_size,
        "shuffle_seed": shuffle_seed,
        "prompt_hash": prompt_hash,
        "created_at": created,
        "task_count": len(tasks),
        "run_status": "pending",
        "resume_count": 0,
        "tasks": index_rows,
        "budget": {
            "old_spent_budget_upper_bound": 62140,
            "new_authorized_budget": 0,
            "current_run_exact_input_tokens": 0,
            "current_run_exact_output_tokens": 0,
            "current_run_exact_usage": 0,
            "uncertain_usage_upper_bound": 0,
            "warning_70_percent": False,
            "stop_opening_new_cases_85_percent": False,
            "provider_calls_allowed": False,
        },
        "usage": {
            "provider_calls": 0,
            "recorded_calls": 0,
            "retries": 0,
            "completed_cases": 0,
        },
    }
    refresh_index_hashes(index)
    return tasks, index


def create_task_checkpoint(
    packet_path: Path,
    checkpoint_dir: Path,
    *,
    reviewer_id: str,
    reviewer_type: str,
    batch_size: int,
    shuffle_seed: int,
    prompt_hash: str,
) -> dict[str, Any]:
    packet = load_blind_packet(packet_path)
    index_path = checkpoint_dir / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        validate_task_index(index)
        expected = {
            "packet_hash": packet["packet_sha256"],
            "reviewer_id": reviewer_id,
            "reviewer_type": reviewer_type,
            "batch_size": batch_size,
            "shuffle_seed": shuffle_seed,
            "prompt_hash": prompt_hash,
        }
        mismatches = {
            key: (index.get(key), value)
            for key, value in expected.items()
            if index.get(key) != value
        }
        if mismatches:
            raise ValueError(f"existing checkpoint definition mismatch: {mismatches}")
        return index
    tasks, index = build_review_tasks(
        packet,
        reviewer_id=reviewer_id,
        reviewer_type=reviewer_type,
        batch_size=batch_size,
        shuffle_seed=shuffle_seed,
        prompt_hash=prompt_hash,
    )
    for task in tasks:
        atomic_write_json(checkpoint_dir / "tasks" / f"{task['task_id']}.json", task)
    atomic_write_json(index_path, index)
    return index


def load_task(path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    task = json.loads(path.read_text(encoding="utf-8"))
    if task.get("schema_version") != TASK_SCHEMA:
        raise ValueError("unsupported review task schema")
    task_hash = task.get("task_sha256")
    if task_hash != stable_hash(_task_hash_payload(task)):
        raise ValueError("review task hash mismatch")
    if expected_sha256 and task_hash != expected_sha256:
        raise ValueError("review task does not match its index")
    assert_label_blind(task, label="review task")
    return task


def write_task_index(path: Path, index: dict[str, Any]) -> None:
    refresh_index_hashes(index)
    atomic_write_json(path, index)


def _pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _human_instructions(reviewer_id: str, packet_hash: str) -> str:
    return f"""# StateGuard 独立人工盲审说明

- Reviewer ID: `{reviewer_id}`
- Packet hash: `{packet_hash}`
- Reviewer type: `human`

请只依据 `cases.md` 中的前态、必达终态、正文、声明账本、地点关系、
知识边界和 repair 作答。不要请求或查看 blind key、expected label、系统决定、
verifier 输出、baseline/candidate 决定或其他 reviewer 的答案。

可填写 `review.csv` 或 `review.json`。每个案例必须只出现一次；无法判断时将
decision 写为 `ambiguous`，不要猜测。错误类型可用逗号分隔。置信度范围为
0–1，理由不能为空。完成后请确认 `blind_key_accessed` 仍为 `false`。
"""


def _human_cases_markdown(packet: dict[str, Any], ordered_ids: list[str]) -> str:
    by_id = {case["case_id"]: case for case in packet["cases"]}
    lines = ["# StateGuard 人工盲审案例", ""]
    for ordinal, case_id in enumerate(ordered_ids, start=1):
        case = by_id[case_id]
        repairs = case.get("repair_attempts") or []
        lines.extend(
            [
                f"## Case {ordinal:02d} — `{case_id}`",
                "",
                "### 上一状态",
                "",
                "```json",
                _pretty(case.get("previous_state") or {}),
                "```",
                "",
                "### 必达终态",
                "",
                "```json",
                _pretty(case.get("required_end_states") or []),
                "```",
                "",
                "### 正文",
                "",
                str(case.get("prose") or ""),
                "",
                "### 声明账本",
                "",
                "```json",
                _pretty(case.get("declared_ledger") or {}),
                "```",
                "",
                "### Repair",
                "",
                _pretty(repairs) if repairs else "无。",
                "",
                "### 必要地点关系",
                "",
                "```json",
                _pretty(case.get("location_relations") or []),
                "```",
                "",
                "### 必要知识边界",
                "",
                "```json",
                _pretty(case.get("knowledge_boundaries") or []),
                "```",
                "",
                "### 请填写",
                "",
                "- 终态是否完成：是 / 否 / 无法判断",
                "- 是否有无来源状态变化：是 / 否 / 无法判断",
                "- 账本是否匹配正文：是 / 否 / 无法判断",
                "- 是否有知识越权：是 / 否 / 无法判断",
                "- Repair 是否改变事实：是 / 否 / 不适用 / 无法判断",
                "- 最终决定：accept / reject / ambiguous",
                "- 错误类型：",
                "- 置信度：",
                "- 理由：",
                "",
            ]
        )
    return "\n".join(lines)


CSV_FIELDS = (
    "case_id",
    "endpoint_complete",
    "ungrounded_change",
    "ledger_matches",
    "knowledge_leak",
    "repair_changed_fact",
    "decision",
    "error_types",
    "confidence",
    "rationale",
)


def _blank_csv(case_ids: list[str]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for case_id in case_ids:
        writer.writerow({"case_id": case_id})
    return stream.getvalue()


def export_human_review_package(
    packet_path: Path,
    out_dir: Path,
    *,
    reviewer_id: str,
    shuffle_seed: int = 0,
) -> dict[str, Any]:
    packet = load_blind_packet(packet_path)
    case_ids = [case["case_id"] for case in packet["cases"]]
    seed_material = f"{packet['packet_sha256']}|human|{reviewer_id}|{shuffle_seed}"
    randomizer = random.Random(int(hashlib.sha256(seed_material.encode()).hexdigest()[:16], 16))
    randomizer.shuffle(case_ids)
    instructions = _human_instructions(reviewer_id, packet["packet_sha256"])
    cases_md = _human_cases_markdown(packet, case_ids)
    review_json = {
        "schema_version": "state-guard-human-review-template-v1",
        "packet_id": packet["packet_id"],
        "packet_hash": packet["packet_sha256"],
        "reviewer_id": reviewer_id,
        "reviewer_type": "human",
        "blind_key_accessed": False,
        "results": [
            {
                "case_id": case_id,
                "endpoint_complete": None,
                "ungrounded_change": None,
                "ledger_matches": None,
                "knowledge_leak": None,
                "repair_changed_fact": None,
                "decision": "ambiguous",
                "error_types": [],
                "confidence": 0.0,
                "rationale": "",
            }
            for case_id in case_ids
        ],
    }
    assert_label_blind(review_json, label="human JSON template")
    atomic_write_text(out_dir / "instructions.md", instructions)
    atomic_write_text(out_dir / "cases.md", cases_md)
    atomic_write_text(out_dir / "review.csv", _blank_csv(case_ids))
    atomic_write_json(out_dir / "review.json", review_json)
    immutable_files = {
        name: file_hash(out_dir / name)
        for name in ("instructions.md", "cases.md")
    }
    manifest = {
        "schema_version": HUMAN_PACKAGE_SCHEMA,
        "packet_id": packet["packet_id"],
        "packet_hash": packet["packet_sha256"],
        "reviewer_id": reviewer_id,
        "reviewer_type": "human",
        "blind_key_accessed": False,
        "shuffle_seed": shuffle_seed,
        "case_count": len(case_ids),
        "case_ids": case_ids,
        "immutable_files": immutable_files,
        "mutable_review_files": ["review.csv", "review.json"],
        "created_at": now_utc(),
    }
    manifest["manifest_sha256"] = stable_hash(manifest)
    assert_label_blind(manifest, label="human manifest")
    atomic_write_json(out_dir / "manifest.json", manifest)
    return manifest


def load_human_manifest(package_dir: Path) -> dict[str, Any]:
    manifest_path = package_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != HUMAN_PACKAGE_SCHEMA:
        raise ValueError("unsupported human package schema")
    validate_hashed_payload(manifest, "manifest_sha256", "human package manifest")
    if manifest.get("reviewer_type") != "human":
        raise ValueError("human package reviewer_type must be human")
    if manifest.get("blind_key_accessed") is not False:
        raise ValueError("human package declares blind-key access")
    for filename, expected_hash in (manifest.get("immutable_files") or {}).items():
        path = package_dir / filename
        if not path.is_file() or file_hash(path) != expected_hash:
            raise ValueError(f"human package immutable file mismatch: {filename}")
    assert_label_blind(manifest, label="human package manifest")
    return manifest


def _parse_optional_bool(value: Any, field: str) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().casefold()
    if normalized in {"true", "yes", "y", "1", "是"}:
        return True
    if normalized in {"false", "no", "n", "0", "否"}:
        return False
    if normalized in {"", "unknown", "ambiguous", "n/a", "na", "无法判断", "不适用"}:
        return None
    raise ValueError(f"invalid boolean value for {field}: {value!r}")


def _parse_error_types(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return _parse_error_types(decoded)
    if isinstance(value, list):
        values = [str(item).strip() for item in value if str(item).strip()]
    else:
        values = [
            item.strip()
            for item in re.split(r"[,;，；]", str(value or ""))
            if item.strip()
        ]
    unknown = sorted(set(values) - set(ALLOWED_ERROR_TYPES))
    if unknown:
        raise ValueError(f"unknown error types: {unknown}")
    return list(dict.fromkeys(values))


def _normalize_human_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "case_id": str(row.get("case_id") or "").strip(),
        "endpoint_complete": _parse_optional_bool(
            row.get("endpoint_complete"), "endpoint_complete"
        ),
        "ungrounded_change": _parse_optional_bool(
            row.get("ungrounded_change"), "ungrounded_change"
        ),
        "ledger_matches": _parse_optional_bool(
            row.get("ledger_matches"), "ledger_matches"
        ),
        "knowledge_leak": _parse_optional_bool(
            row.get("knowledge_leak"), "knowledge_leak"
        ),
        "repair_changed_fact": _parse_optional_bool(
            row.get("repair_changed_fact"), "repair_changed_fact"
        ),
        "decision": str(row.get("decision") or "").strip().casefold(),
        "error_types": _parse_error_types(row.get("error_types")),
        "confidence": float(row.get("confidence")),
        "rationale": str(row.get("rationale") or "").strip(),
    }
    return ReviewCaseResult.model_validate(payload).model_dump(mode="json")


def import_human_review(
    package_dir: Path,
    input_path: Path,
    *,
    allow_partial: bool = False,
    review_started_at: str | None = None,
    review_finished_at: str | None = None,
) -> dict[str, Any]:
    manifest = load_human_manifest(package_dir)
    raw = input_path.read_bytes()
    if input_path.suffix.casefold() == ".csv":
        rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    elif input_path.suffix.casefold() == ".json":
        value = json.loads(raw.decode("utf-8"))
        if value.get("reviewer_id") != manifest["reviewer_id"]:
            raise ValueError("review JSON reviewer_id mismatch")
        if value.get("reviewer_type") != "human":
            raise ValueError("review JSON reviewer_type must be human")
        if value.get("blind_key_accessed") is not False:
            raise ValueError("review JSON declares blind-key access")
        rows = value.get("results") or []
    else:
        raise ValueError("human review input must be CSV or JSON")
    results = [_normalize_human_row(dict(row)) for row in rows]
    result_ids = [row["case_id"] for row in results]
    if len(result_ids) != len(set(result_ids)):
        raise ValueError("human review contains duplicate cases")
    expected = set(manifest["case_ids"])
    supplied = set(result_ids)
    extra = sorted(supplied - expected)
    missing = sorted(expected - supplied)
    if extra or (missing and not allow_partial):
        raise ValueError(
            f"human review coverage mismatch; missing={missing}, extra={extra}"
        )
    ordered = [
        next(result for result in results if result["case_id"] == case_id)
        for case_id in manifest["case_ids"]
        if case_id in supplied
    ]
    started = review_started_at or manifest["created_at"]
    finished = review_finished_at or now_utc()
    if datetime.fromisoformat(finished.replace("Z", "+00:00")) < datetime.fromisoformat(
        started.replace("Z", "+00:00")
    ):
        raise ValueError("review_finished_at precedes review_started_at")
    part = {
        "schema_version": PART_SCHEMA,
        "packet_id": manifest["packet_id"],
        "packet_hash": manifest["packet_hash"],
        "reviewer_id": manifest["reviewer_id"],
        "reviewer_type": "human",
        "evidence_mode": "human",
        "model_family": "",
        "model_name": "",
        "provider_name": "",
        "blind_key_accessed": False,
        "review_started_at": started,
        "review_finished_at": finished,
        "source": {
            "manifest_sha256": manifest["manifest_sha256"],
            "input_filename": input_path.name,
            "input_sha256": hashlib.sha256(raw).hexdigest(),
        },
        "results": ordered,
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


def validate_review_part(part: dict[str, Any]) -> None:
    if part.get("schema_version") != PART_SCHEMA:
        raise ValueError("unsupported partial review schema")
    validate_hashed_payload(part, "part_sha256", "partial review")
    if part.get("reviewer_type") not in REVIEWER_TYPES:
        raise ValueError("partial review has invalid reviewer_type")
    if part.get("evidence_mode") not in EVIDENCE_MODES:
        raise ValueError("partial review has invalid evidence_mode")
    if part.get("blind_key_accessed") is not False:
        raise ValueError("partial review declares blind-key access")
    result_ids: list[str] = []
    for row in part.get("results") or []:
        result = ReviewCaseResult.model_validate(row)
        result_ids.append(result.case_id)
    if len(result_ids) != len(set(result_ids)):
        raise ValueError("partial review contains duplicate cases")


def _load_part(path: Path) -> dict[str, Any]:
    part = json.loads(path.read_text(encoding="utf-8"))
    validate_review_part(part)
    part["_source_path"] = str(path)
    return part


def merge_review_parts(
    packet_path: Path, part_paths: Iterable[Path]
) -> tuple[dict[str, Any], dict[str, Any]]:
    packet = load_blind_packet(packet_path)
    parts = [_load_part(path) for path in part_paths]
    if not parts:
        raise ValueError("at least one partial review is required")
    metadata_fields = (
        "packet_id",
        "packet_hash",
        "reviewer_id",
        "reviewer_type",
        "evidence_mode",
        "model_family",
        "model_name",
        "provider_name",
        "blind_key_accessed",
    )
    baseline = parts[0]
    for part in parts[1:]:
        mismatches = [
            field for field in metadata_fields if part.get(field) != baseline.get(field)
        ]
        if mismatches:
            raise ValueError(f"partial reviewer metadata mismatch: {mismatches}")
    if baseline["packet_hash"] != packet["packet_sha256"]:
        raise ValueError("partial reviews do not match blind packet")
    by_id: dict[str, dict[str, Any]] = {}
    part_sources: list[dict[str, Any]] = []
    for part in parts:
        for result in part["results"]:
            case_id = result["case_id"]
            if case_id in by_id:
                raise ValueError(f"duplicate case across partial reviews: {case_id}")
            by_id[case_id] = result
        part_sources.append(
            {
                "part_id": part["part_id"],
                "part_sha256": part["part_sha256"],
                "source_path": part.pop("_source_path"),
                "review_started_at": part["review_started_at"],
                "review_finished_at": part["review_finished_at"],
                "case_count": len(part["results"]),
            }
        )
    packet_ids = [case["case_id"] for case in packet["cases"]]
    extra = sorted(set(by_id) - set(packet_ids))
    if extra:
        raise ValueError(f"partial reviews contain unknown cases: {extra}")
    results = [by_id[case_id] for case_id in packet_ids if case_id in by_id]
    completed = len(results)
    decisive = sum(row["decision"] != "ambiguous" for row in results)
    coverage = {
        "reviewer_id": baseline["reviewer_id"],
        "completed": completed,
        "missing": len(packet_ids) - completed,
        "missing_case_ids": [case_id for case_id in packet_ids if case_id not in by_id],
        "decisive": decisive,
        "accepts": sum(row["decision"] == "accept" for row in results),
        "rejects": sum(row["decision"] == "reject" for row in results),
        "ambiguous": sum(row["decision"] == "ambiguous" for row in results),
        "valid_for_gate": completed >= 20 and decisive >= 20,
    }
    merged = {
        "schema_version": MERGED_SCHEMA,
        "packet_id": baseline["packet_id"],
        "packet_hash": baseline["packet_hash"],
        "reviewer_id": baseline["reviewer_id"],
        "reviewer_type": baseline["reviewer_type"],
        "evidence_mode": baseline["evidence_mode"],
        "model_family": baseline.get("model_family", ""),
        "model_name": baseline.get("model_name", ""),
        "provider_name": baseline.get("provider_name", ""),
        "blind_key_accessed": False,
        "review_started_at": min(part["review_started_at"] for part in parts),
        "review_finished_at": max(part["review_finished_at"] for part in parts),
        "part_sources": part_sources,
        "coverage": coverage,
        "usage": {
            key: sum((part.get("usage") or {}).get(key, 0) or 0 for part in parts)
            for key in (
                "provider_calls",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "uncertain_usage_upper_bound",
            )
        },
        "results": results,
    }
    coverage["coverage_sha256"] = stable_hash(coverage)
    merged["review_sha256"] = stable_hash(merged)
    coverage_report = dict(coverage)
    coverage_report["review_sha256"] = merged["review_sha256"]
    return merged, coverage_report


def validate_merged_review(review: dict[str, Any]) -> None:
    if review.get("schema_version") != MERGED_SCHEMA:
        raise ValueError("unsupported merged review schema")
    validate_hashed_payload(review, "review_sha256", "merged review")
    if review.get("reviewer_type") not in REVIEWER_TYPES:
        raise ValueError("merged review has invalid reviewer_type")
    if review.get("evidence_mode") not in EVIDENCE_MODES:
        raise ValueError("merged review has invalid evidence_mode")
    if review.get("blind_key_accessed") is not False:
        raise ValueError("merged review declares blind-key access")
    ids = []
    for row in review.get("results") or []:
        ids.append(ReviewCaseResult.model_validate(row).case_id)
    if len(ids) != len(set(ids)):
        raise ValueError("merged review contains duplicate cases")


def _review_identity(review: dict[str, Any]) -> tuple[str, str]:
    if review["reviewer_type"] == "human":
        return "human", review["reviewer_id"]
    return (
        review["reviewer_type"],
        f"{review.get('model_family', '').casefold()}::{review.get('model_name', '').casefold()}",
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def cohens_kappa(left: list[str], right: list[str]) -> float | None:
    if len(left) != len(right):
        raise ValueError("reviewer vectors have different lengths")
    if not left:
        return None
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    expected = sum(
        (left.count(label) / len(left)) * (right.count(label) / len(right))
        for label in DECISIONS
    )
    if abs(expected - 1.0) < 1e-12:
        return 1.0 if abs(observed - 1.0) < 1e-12 else None
    return round((observed - expected) / (1.0 - expected), 6)


def build_partial_review_gate(
    packet: dict[str, Any],
    primary_reviews: list[dict[str, Any]],
    *,
    adjudicator: dict[str, Any] | None = None,
    hard_contradiction_case_ids: set[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if len(primary_reviews) != 2:
        raise ValueError("exactly two primary reviews are required")
    primary_reviews = sorted(primary_reviews, key=lambda review: review["reviewer_id"])
    for review in primary_reviews:
        validate_merged_review(review)
        if review["packet_hash"] != packet["packet_sha256"]:
            raise ValueError("review packet hash mismatch")
        if review["reviewer_type"] not in {"human", "independent_model"}:
            raise ValueError("project-agent review cannot enter independent Gate")
        if review["evidence_mode"] not in {"human", "provider"}:
            raise ValueError("mock/recorded review cannot enter independent Gate")
    if _review_identity(primary_reviews[0]) == _review_identity(primary_reviews[1]):
        raise ValueError("independent reviewer identities are not distinct")
    packet_ids = [case["case_id"] for case in packet["cases"]]
    maps = [
        {row["case_id"]: row for row in review["results"]}
        for review in primary_reviews
    ]
    overlap = [case_id for case_id in packet_ids if all(case_id in value for value in maps)]
    decisive_overlap = [
        case_id
        for case_id in overlap
        if maps[0][case_id]["decision"] != "ambiguous"
        and maps[1][case_id]["decision"] != "ambiguous"
    ]
    left_vector = [maps[0][case_id]["decision"] for case_id in decisive_overlap]
    right_vector = [maps[1][case_id]["decision"] for case_id in decisive_overlap]
    agreement = _ratio(
        sum(left == right for left, right in zip(left_vector, right_vector)),
        len(decisive_overlap),
    )
    kappa = cohens_kappa(left_vector, right_vector)
    per_question: dict[str, Any] = {}
    for field in QUESTION_FIELDS:
        comparable = [
            case_id
            for case_id in overlap
            if maps[0][case_id][field] is not None
            and maps[1][case_id][field] is not None
        ]
        per_question[field] = {
            "comparable": len(comparable),
            "raw_agreement": _ratio(
                sum(maps[0][case_id][field] == maps[1][case_id][field] for case_id in comparable),
                len(comparable),
            ),
        }
    taxonomy_agreement = _ratio(
        sum(
            set(maps[0][case_id]["error_types"])
            == set(maps[1][case_id]["error_types"])
            for case_id in overlap
        ),
        len(overlap),
    )
    per_error_type_agreement = {
        error_type: _ratio(
            sum(
                (error_type in maps[0][case_id]["error_types"])
                == (error_type in maps[1][case_id]["error_types"])
                for case_id in overlap
            ),
            len(overlap),
        )
        for error_type in ALLOWED_ERROR_TYPES
    }
    disagreement_ids = [
        case_id
        for case_id in overlap
        if maps[0][case_id]["decision"] != maps[1][case_id]["decision"]
        or set(maps[0][case_id]["error_types"])
        != set(maps[1][case_id]["error_types"])
    ]
    adjudicator_map: dict[str, dict[str, Any]] = {}
    if adjudicator:
        validate_merged_review(adjudicator)
        if adjudicator["packet_hash"] != packet["packet_sha256"]:
            raise ValueError("adjudicator packet hash mismatch")
        if _review_identity(adjudicator) in {
            _review_identity(primary_reviews[0]),
            _review_identity(primary_reviews[1]),
        }:
            raise ValueError("adjudicator identity duplicates a primary reviewer")
        adjudicator_map = {row["case_id"]: row for row in adjudicator["results"]}
        extra = sorted(set(adjudicator_map) - set(disagreement_ids))
        if extra:
            raise ValueError(f"adjudicator contains non-disagreement cases: {extra}")
    gold_cases: list[dict[str, Any]] = []
    for case_id in overlap:
        left = maps[0][case_id]
        right = maps[1][case_id]
        disagrees = case_id in disagreement_ids
        adjudicated = adjudicator_map.get(case_id)
        if disagrees and adjudicated:
            decision = adjudicated["decision"]
            error_types = adjudicated["error_types"]
            confidence = adjudicated["confidence"]
        elif disagrees:
            decision = "ambiguous"
            error_types = sorted(set(left["error_types"]) | set(right["error_types"]))
            confidence = round((left["confidence"] + right["confidence"]) / 2, 6)
        else:
            decision = left["decision"]
            error_types = sorted(set(left["error_types"]) | set(right["error_types"]))
            confidence = round((left["confidence"] + right["confidence"]) / 2, 6)
        gold_cases.append(
            {
                "case_id": case_id,
                "gold_decision": decision,
                "gold_error_types": error_types,
                "reviewer_decisions": [
                    {
                        "reviewer_id": primary_reviews[0]["reviewer_id"],
                        "decision": left["decision"],
                        "confidence": left["confidence"],
                    },
                    {
                        "reviewer_id": primary_reviews[1]["reviewer_id"],
                        "decision": right["decision"],
                        "confidence": right["confidence"],
                    },
                ],
                "adjudicated": adjudicated is not None,
                "adjudicator_id": adjudicator["reviewer_id"] if adjudicated else None,
                "confidence": confidence,
            }
        )
    decisive = [case for case in gold_cases if case["gold_decision"] != "ambiguous"]
    accepts = sum(case["gold_decision"] == "accept" for case in decisive)
    rejects = sum(case["gold_decision"] == "reject" for case in decisive)
    hard_ids = hard_contradiction_case_ids or set()
    hard_accepts = sorted(
        case["case_id"]
        for case in gold_cases
        if case["case_id"] in hard_ids and case["gold_decision"] == "accept"
    )
    checks = {
        "valid_independent_reviewers": {
            "value": 2,
            "minimum": 2,
            "passed": True,
        },
        "overlapping_decisive": {
            "value": len(decisive_overlap),
            "minimum": 20,
            "passed": len(decisive_overlap) >= 20,
        },
        "gold_decisive": {
            "value": len(decisive),
            "minimum": 20,
            "passed": len(decisive) >= 20,
        },
        "gold_accepts": {
            "value": accepts,
            "minimum": 8,
            "passed": accepts >= 8,
        },
        "gold_rejects": {
            "value": rejects,
            "minimum": 8,
            "passed": rejects >= 8,
        },
        "raw_agreement": {
            "value": agreement,
            "minimum": 0.80,
            "passed": agreement is not None and agreement >= 0.80,
        },
        "cohens_kappa": {
            "value": kappa,
            "minimum": 0.60,
            "passed": kappa is not None and kappa >= 0.60,
        },
        "unresolved_ambiguous_rate": {
            "value": _ratio(len(gold_cases) - len(decisive), len(gold_cases)),
            "maximum": 0.30,
            "passed": bool(gold_cases)
            and (len(gold_cases) - len(decisive)) / len(gold_cases) <= 0.30,
        },
        "hard_contradictions_accepted": {
            "value": len(hard_accepts),
            "maximum": 0,
            "passed": not hard_accepts,
            "case_ids": hard_accepts,
        },
    }
    gate_passed = all(check["passed"] for check in checks.values())
    gold = {
        "schema_version": GOLD_SCHEMA,
        "packet_id": packet["packet_id"],
        "packet_hash": packet["packet_sha256"],
        "reviewer_ids": [review["reviewer_id"] for review in primary_reviews],
        "adjudicator_id": adjudicator["reviewer_id"] if adjudicator else None,
        "cases": gold_cases,
    }
    gold["gold_sha256"] = stable_hash(gold)
    disagreement_cases = [
        case for case in packet["cases"] if case["case_id"] in set(disagreement_ids)
    ]
    disagreement = {
        "schema_version": "state-guard-adjudication-packet-v1",
        "packet_id": f"{packet['packet_id']}:phase11-disagreement-v1",
        "reviewer_instructions": (
            "仅独立审查本包案例；本包不含前两名 reviewer 的答案、系统决定或隐藏标签。"
        ),
        "case_count": len(disagreement_cases),
        "cases": disagreement_cases,
    }
    disagreement["packet_sha256"] = stable_hash(disagreement)
    assert_label_blind(disagreement, label="disagreement packet")
    confidence_values = sorted(
        row["confidence"]
        for review in primary_reviews
        for row in review["results"]
    )
    report = {
        "schema_version": "state-guard-partial-adjudication-report-v1",
        "packet_id": packet["packet_id"],
        "packet_hash": packet["packet_sha256"],
        "reviewers": [
            {
                "reviewer_id": review["reviewer_id"],
                "reviewer_type": review["reviewer_type"],
                "evidence_mode": review["evidence_mode"],
                "coverage": review["coverage"],
            }
            for review in primary_reviews
        ],
        "overlap": len(overlap),
        "overlapping_decisive": len(decisive_overlap),
        "raw_agreement": agreement,
        "cohens_kappa": kappa,
        "per_question_agreement": per_question,
        "error_taxonomy_agreement": taxonomy_agreement,
        "per_error_type_agreement": per_error_type_agreement,
        "confidence_distribution": {
            "count": len(confidence_values),
            "min": min(confidence_values) if confidence_values else None,
            "median": (
                round(statistics.median(confidence_values), 6)
                if confidence_values
                else None
            ),
            "mean": (
                round(statistics.fmean(confidence_values), 6)
                if confidence_values
                else None
            ),
            "max": max(confidence_values) if confidence_values else None,
            "below_0_6": sum(value < 0.6 for value in confidence_values),
            "at_least_0_8": sum(value >= 0.8 for value in confidence_values),
        },
        "disagreement_case_count": len(disagreement_ids),
        "gold_summary": {
            "decisive": len(decisive),
            "accepts": accepts,
            "rejects": rejects,
            "ambiguous": len(gold_cases) - len(decisive),
            "adjudications": sum(case["adjudicated"] for case in gold_cases),
        },
        "review_gate": {
            "checks": checks,
            "passed": gate_passed,
            "decision": "PASS_INDEPENDENT_REVIEW_GATE" if gate_passed else "BLOCK_REAL_REPLAY",
            "behavior_change_allowed": False,
        },
        "gold_sha256": gold["gold_sha256"],
    }
    report["report_sha256"] = stable_hash(report)
    return report, disagreement, gold


def freeze_file(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing != text:
            raise FileExistsError(f"refusing to overwrite frozen artifact: {path}")
        return
    atomic_write_text(path, text)


def require_real_replay_gate(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    gate = report.get("review_gate") or {}
    if not gate.get("passed") or gate.get("decision") != "PASS_INDEPENDENT_REVIEW_GATE":
        raise PermissionError("BLOCK_REAL_REPLAY: independent review Gate has not passed")
    return report
