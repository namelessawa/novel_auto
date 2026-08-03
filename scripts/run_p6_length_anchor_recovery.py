"""Run the fail-closed P6 length/anchor recovery acceptance cycle.

The runner owns one immutable evidence directory.  It never exposes a force
flag, never reuses the previous P6 failure receipt, and authorizes the two real
provider stages only when the current source tree has a green offline receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CYCLE_ID = "p6-length-anchor-recovery-20260729"
BASE_HEAD = "89a15e2ab5fed5407c1dd9b7a397ec7bbadd2390"
EXPECTED_BRANCH = "codex/p6-length-anchor-recovery-20260729"
DEFAULT_EVIDENCE_ROOT = ROOT / ".tmp" / CYCLE_ID
REGRESSION_TEST = ROOT / "backend/tests/test_p6_length_anchor_recovery.py"
REGRESSION_FIXTURE = ROOT / "backend/tests/fixtures/p6_length_anchor_recovery_656.json"
HISTORICAL_STYLES = (
    "literary",
    "noir_cold",
    "warm_healing",
    "hot_blooded",
    "classical_chapter",
)
FINAL_OUTPUT_NAMES = {
    "artifact-sha256.json",
    "manifest.json",
    "recovery.md",
    "report.json",
    "report.md",
}


class CycleError(RuntimeError):
    """A fail-closed cycle precondition or state transition failure."""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(text, encoding="utf-8", newline="\n")
    os.replace(partial, path)


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise CycleError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def _source_tree_hash() -> str:
    names = _git(
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ).split("\0")
    digest = hashlib.sha256()
    for raw in sorted(name for name in names if name):
        relative = Path(raw)
        if relative.parts and relative.parts[0] == ".tmp":
            continue
        if relative.parts[:2] in {
            ("frontend", "dist"),
            ("frontend", "node_modules"),
        }:
            continue
        path = ROOT / relative
        if not path.is_file():
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest().upper()


def _provider_values(provider_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not provider_file.is_file():
        return values
    for raw in provider_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = (part.strip() for part in line.split("=", 1))
        values[name.upper()] = value
    return values


def _redact(text: str, provider_values: dict[str, str]) -> str:
    result = text
    for name in ("KEY", "URL"):
        value = provider_values.get(name, "")
        if value:
            result = result.replace(value, f"[REDACTED_{name}]")
    return result


def _snapshot_files(root: Path, relative_paths: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for relative in relative_paths:
        path = root / relative
        result[relative] = {
            "exists": path.is_file(),
            "sha256": _sha256_file(path) if path.is_file() else "",
        }
    return result


def _snapshot_previous_evidence(root: Path) -> dict[str, Any]:
    required = [
        "report.json",
        "manifest.json",
        "artifact-sha256.json",
        "p6/seed-20260727/stage1-matrix.json",
        "p6/seed-20260727-attempt-02/stage1-matrix.json",
        "p6/seed-20260727-attempt-03/stage1-matrix.json",
    ]
    snapshot = _snapshot_files(root, required)
    missing = [name for name, item in snapshot.items() if not item["exists"]]
    if missing:
        raise CycleError(f"previous P6 evidence is incomplete: {missing}")
    return snapshot


def _previous_source_hash(root: Path) -> str:
    receipt = _read_json(root / "offline/final-offline.json", {})
    return str(receipt.get("source_tree_sha256") or "")


def _user_snapshot(user_root: Path) -> dict[str, Any]:
    status = subprocess.run(
        ["git", "status", "--short", "--branch"],
        cwd=user_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    protected = _snapshot_files(
        user_root,
        [
            "scripts/openai_compatible_chat.py",
            "coding.txt",
            "config.json",
            ".env",
            "docs/iter/style-generation-samples-glm52-20260722.md",
        ],
    )
    return {
        "root": str(user_root),
        "status": status.stdout.replace("\r\n", "\n").strip(),
        "protected_files": protected,
    }


def _assert_snapshot_unchanged(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    label: str,
) -> None:
    if expected != actual:
        raise CycleError(f"{label} changed during the recovery cycle")


def _assert_git_identity() -> dict[str, Any]:
    branch = _git("branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise CycleError(f"expected branch {EXPECTED_BRANCH}, got {branch}")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_HEAD, "HEAD"],
        cwd=ROOT,
        check=False,
    )
    if ancestor.returncode:
        raise CycleError("base HEAD is not an ancestor of the current HEAD")
    merges = _git("rev-list", "--merges", f"{BASE_HEAD}..HEAD", check=False)
    if merges:
        raise CycleError("a merge commit exists after the frozen base HEAD")
    return {
        "branch": branch,
        "base_head": BASE_HEAD,
        "head": _git("rev-parse", "HEAD"),
        "source_tree_sha256": _source_tree_hash(),
        "merge_commits_after_base": [],
    }


def _regression_inventory() -> dict[str, Any]:
    if not REGRESSION_TEST.is_file() or not REGRESSION_FIXTURE.is_file():
        raise CycleError("required recovery regression test or fixture is missing")
    text = REGRESSION_TEST.read_text(encoding="utf-8")
    count = len(re.findall(r"^def test_|^async def test_", text, flags=re.MULTILINE))
    if count < 20:
        raise CycleError(f"expected at least 20 explicit regressions, found {count}")
    return {
        "test": REGRESSION_TEST.relative_to(ROOT).as_posix(),
        "test_sha256": _sha256_file(REGRESSION_TEST),
        "fixture": REGRESSION_FIXTURE.relative_to(ROOT).as_posix(),
        "fixture_sha256": _sha256_file(REGRESSION_FIXTURE),
        "explicit_test_count": count,
    }


def _initialize(
    evidence_root: Path,
    *,
    previous_evidence_root: Path,
    user_root: Path,
) -> dict[str, Any]:
    state_path = evidence_root / "cycle-state.json"
    if state_path.exists():
        state = _read_json(state_path, {})
        if state.get("cycle_id") != CYCLE_ID:
            raise CycleError("evidence root belongs to a different cycle")
        return state
    if evidence_root.resolve() == previous_evidence_root.resolve():
        raise CycleError("new cycle must not reuse the previous evidence root")
    evidence_root.mkdir(parents=True, exist_ok=True)
    git = _assert_git_identity()
    previous_hash = _previous_source_hash(previous_evidence_root)
    if previous_hash and previous_hash == git["source_tree_sha256"]:
        raise CycleError("source tree hash is unchanged from the failed cycle")
    state = {
        "schema_version": "p6-length-anchor-cycle-v1",
        "cycle_id": CYCLE_ID,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "initialized",
        "git_at_start": git,
        "regressions": _regression_inventory(),
        "previous_evidence_root": str(previous_evidence_root.resolve()),
        "previous_source_tree_sha256": previous_hash,
        "previous_evidence_snapshot": _snapshot_previous_evidence(
            previous_evidence_root
        ),
        "user_snapshot": _user_snapshot(user_root),
        "offline_attempts": [],
        "g1": {"status": "not_started"},
        "g2": {"status": "not_started"},
    }
    _atomic_json(state_path, state)
    return state


def _load_and_verify(
    evidence_root: Path,
    *,
    previous_evidence_root: Path,
    user_root: Path,
) -> dict[str, Any]:
    state = _initialize(
        evidence_root,
        previous_evidence_root=previous_evidence_root,
        user_root=user_root,
    )
    _assert_git_identity()
    _assert_snapshot_unchanged(
        state["previous_evidence_snapshot"],
        _snapshot_previous_evidence(previous_evidence_root),
        label="previous P6 evidence",
    )
    _assert_snapshot_unchanged(
        state["user_snapshot"],
        _user_snapshot(user_root),
        label="user-owned files",
    )
    _regression_inventory()
    return state


def _offline_specs() -> list[tuple[str, list[str]]]:
    npm = shutil.which("npm") or "npm"
    return [
        (
            "backend_tests",
            [sys.executable, "-m", "pytest", "backend/tests/", "-q", "-W", "error"],
        ),
        ("ruff", [sys.executable, "-m", "ruff", "check", "backend", "scripts"]),
        (
            "compileall",
            [sys.executable, "-m", "compileall", "-q", "backend", "scripts"],
        ),
        ("author_ui", [npm, "--prefix", "frontend", "run", "test:author"]),
        ("frontend_build", [npm, "--prefix", "frontend", "run", "build"]),
        (
            "npm_production_audit",
            [npm, "--prefix", "frontend", "audit", "--omit=dev"],
        ),
        ("git_diff_check", ["git", "diff", "--check"]),
        ("recorded_smoke", [sys.executable, "scripts/smoke_author_mode_recorded.py"]),
    ]


def _run_command(
    command: list[str],
    *,
    log_path: Path,
    provider_values: dict[str, str],
) -> dict[str, Any]:
    started = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    output = _redact(
        "\n".join(part for part in (result.stdout, result.stderr) if part),
        provider_values,
    )
    _atomic_text(log_path, output)
    passed = re.search(r"(\d+)\s+passed", output)
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "command": command,
        "passed": int(passed.group(1)) if passed else None,
        "log": log_path.as_posix(),
        "log_sha256": _sha256_file(log_path),
    }


def _run_recorded_100(
    attempt_dir: Path,
    *,
    provider_values: dict[str, str],
) -> dict[str, Any]:
    output_dir = attempt_dir / "recorded-100"
    common = [
        sys.executable,
        "scripts/run_author_longrange.py",
        "--mode",
        "recorded",
        "--checkpoint-every",
        "10",
        "--runtime-rebuild-every",
        "5",
        "--desired-length",
        "300",
        "--seed",
        "20260728",
        "--theme",
        "reality_mystery",
        "--style",
        "literary",
        "--stop-on-gate-failure",
        "--output-dir",
        str(output_dir),
    ]
    first = _run_command(
        [*common, "--max-sections", "50"],
        log_path=attempt_dir / "logs/recorded-050.log",
        provider_values=provider_values,
    )
    second = {
        "status": "not_run",
        "returncode": None,
    }
    if first["status"] == "passed":
        second = _run_command(
            [*common, "--max-sections", "100", "--resume"],
            log_path=attempt_dir / "logs/recorded-100.log",
            provider_values=provider_values,
        )
    report_path = output_dir / "report.json"
    report = _read_json(report_path, {})
    summary = report.get("summary", {})
    checks = {
        "first_50_passed": first["status"] == "passed",
        "resume_100_passed": second["status"] == "passed",
        "committed_100": summary.get("committed") == 100,
        "semantic_recall_7_of_7": (
            summary.get("semantic_recall_pass") == 7
            and summary.get("semantic_recall_total") == 7
        ),
        "thread_liveness_violations_zero": (
            summary.get("thread_liveness_violations") == 0
        ),
        "planner_calls_zero": summary.get("planner_calls") == 0,
        "writer_retries_zero": summary.get("writer_retries") == 0,
        "p2_gate_passed": report.get("p2_gate", {}).get("passed") is True,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "first": first,
        "second": second,
        "report": report_path.as_posix(),
        "report_sha256": _sha256_file(report_path) if report_path.is_file() else "",
        "summary": {
            key: summary.get(key)
            for key in (
                "committed",
                "semantic_recall_pass",
                "semantic_recall_total",
                "thread_liveness_violations",
                "planner_calls",
                "writer_retries",
            )
        },
    }


def _secret_scan(
    evidence_root: Path,
    *,
    provider_values: dict[str, str],
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    values = {
        "api_key": provider_values.get("KEY", ""),
        "base_url": provider_values.get("URL", ""),
    }
    files = [
        path
        for path in evidence_root.rglob("*")
        if path.is_file() and path.name != "secret-scan.json"
    ]
    for path in files:
        raw = path.read_bytes()
        for kind, value in values.items():
            if value and value.encode("utf-8") in raw:
                findings.append(
                    {
                        "scope": "artifact",
                        "path": path.relative_to(evidence_root).as_posix(),
                        "kind": f"exact_{kind}",
                    }
                )
    diff = "\n".join(
        (
            _git("diff", f"{BASE_HEAD}...HEAD", "--", check=False),
            _git("diff", "--", check=False),
        )
    )
    generic = re.findall(r"sk-[A-Za-z0-9_-]{20,}", diff)
    payload = {
        "schema_version": "p6-length-anchor-secret-scan-v1",
        "created_at": _now(),
        "status": "passed" if not findings and not generic else "failed",
        "artifact_files_scanned": len(files),
        "exact_secret_hits": len(findings),
        "generic_diff_secret_hits": len(generic),
        "findings": findings,
        "secret_values_persisted": False,
    }
    _atomic_json(evidence_root / "secret-scan.json", payload)
    return payload


def _run_offline(
    evidence_root: Path,
    state: dict[str, Any],
    *,
    provider_values: dict[str, str],
) -> dict[str, Any]:
    git = _assert_git_identity()
    source_hash = git["source_tree_sha256"]
    for attempt in state["offline_attempts"]:
        if attempt["source_tree_sha256"] == source_hash:
            return attempt
    attempt_dir = evidence_root / "offline" / source_hash[:16]
    attempt_dir.mkdir(parents=True, exist_ok=False)
    checks: dict[str, Any] = {}
    for name, command in _offline_specs():
        checks[name] = _run_command(
            command,
            log_path=attempt_dir / f"logs/{name}.log",
            provider_values=provider_values,
        )
    recorded = _run_recorded_100(
        attempt_dir,
        provider_values=provider_values,
    )
    secret = _secret_scan(evidence_root, provider_values=provider_values)
    status = (
        "passed"
        if all(item["status"] == "passed" for item in checks.values())
        and recorded["status"] == "passed"
        and secret["status"] == "passed"
        else "failed"
    )
    attempt = {
        "schema_version": "p6-length-anchor-offline-v1",
        "created_at": _now(),
        "status": status,
        "git": git,
        "source_tree_sha256": source_hash,
        "checks": checks,
        "recorded_100": recorded,
        "secret_scan": secret,
    }
    receipt = attempt_dir / "offline-receipt.json"
    _atomic_json(receipt, attempt)
    attempt["receipt"] = receipt.relative_to(evidence_root).as_posix()
    attempt["receipt_sha256"] = _sha256_file(receipt)
    state["offline_attempts"].append(attempt)
    state["status"] = "offline_passed" if status == "passed" else "offline_failed"
    state["updated_at"] = _now()
    _atomic_json(evidence_root / "cycle-state.json", state)
    return attempt


def _flatten_sections(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        section
        for combination in matrix.get("combinations", [])
        for section in combination.get("sections", [])
    ]


def _violation_count(sections: list[dict[str, Any]], code: str) -> int:
    count = 0
    for section in sections:
        values: list[str] = []
        for key in (
            "repair_audit_codes",
            "repair_patch_codes",
            "narrative_violation_codes",
            "state_violation_codes",
        ):
            values.extend(str(item) for item in section.get(key, []))
        count += sum(item == code for item in values)
    return count


def _bad_commit_count(summary: dict[str, Any]) -> int:
    direct = sum(
        int(summary.get(key, 0) or 0)
        for key in (
            "hard_fact_error_commits",
            "state_conflict_commits",
            "illegal_thread_change_commits",
            "evidenceless_state_delta_commits",
        )
    )
    return direct + len(summary.get("data_integrity_violations", []))


def assess_g1(matrix: dict[str, Any]) -> dict[str, Any]:
    summary = matrix.get("summary", {})
    sections = _flatten_sections(matrix)
    final = sections[-1] if sections else {}
    length = int(final.get("narrative_length", 0) or 0)
    checks = {
        "attempted_1": summary.get("attempted") == 1,
        "committed_1": summary.get("committed") == 1,
        "contract_1": summary.get("contract_pass") == 1,
        "length_900_1100": 900 <= length <= 1100,
        "required_events_pass": (
            final.get("required_events_completed") == final.get("required_events_total")
            and int(final.get("required_events_total", 0) or 0) > 0
        ),
        "required_end_states_pass": (
            final.get("end_states_reached") == final.get("end_states_total")
            and int(final.get("end_states_total", 0) or 0) > 0
        ),
        "anchor_failures_zero": _violation_count(
            sections, "PATCH_ANCHOR_NOT_FOUND"
        )
        == 0,
        "post_resolution_expansion_zero": _violation_count(
            sections, "POST_RESOLUTION_EXPANSION"
        )
        == 0,
        "planner_calls_zero": summary.get("planner_calls") == 0,
        "full_retry_calls_zero": summary.get("writer_retries") == 0,
        "provider_calls_at_most_2": int(summary.get("provider_calls", 0) or 0) <= 2,
        "bad_commits_zero": _bad_commit_count(summary) == 0,
        "provider_errors_zero": summary.get("provider_errors") == 0,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "metrics": {
            "attempted": summary.get("attempted", 0),
            "committed": summary.get("committed", 0),
            "contract_pass": summary.get("contract_pass", 0),
            "narrative_length": length,
            "writer_first_pass": summary.get("writer_first_pass_pass", 0),
            "repairs": summary.get("repairs", 0),
            "repair_success": summary.get("repair_success", 0),
            "provider_calls": summary.get("provider_calls", 0),
            "planner_calls": summary.get("planner_calls", 0),
            "full_retry_calls": summary.get("writer_retries", 0),
            "total_tokens": summary.get("total_tokens", 0),
            "mean_latency_seconds": summary.get("mean_latency_seconds", 0.0),
            "anchor_failures": _violation_count(
                sections, "PATCH_ANCHOR_NOT_FOUND"
            ),
            "post_resolution_expansions": _violation_count(
                sections, "POST_RESOLUTION_EXPANSION"
            ),
            "bad_commits": _bad_commit_count(summary),
        },
    }


def assess_g2(matrix: dict[str, Any]) -> dict[str, Any]:
    summary = matrix.get("summary", {})
    sections = _flatten_sections(matrix)
    repairs = int(summary.get("repairs", 0) or 0)
    repair_success = int(summary.get("repair_success", 0) or 0)
    repair_success_rate = 1.0 if repairs == 0 else repair_success / repairs
    lengths = [
        int(section.get("narrative_length", 0) or 0) for section in sections
    ]
    in_range = sum(900 <= value <= 1100 for value in lengths)
    provider_calls = int(summary.get("provider_calls", 0) or 0)
    checks = {
        "attempted_15": summary.get("attempted") == 15,
        "committed_at_least_14": int(summary.get("committed", 0) or 0) >= 14,
        "contract_at_least_14": (
            int(summary.get("contract_pass", 0) or 0) >= 14
        ),
        "length_in_range_at_least_14": in_range >= 14,
        "writer_first_pass_at_least_9": (
            int(summary.get("writer_first_pass_pass", 0) or 0) >= 9
        ),
        "repair_dependency_at_most_6": repairs <= 6,
        "repair_success_at_least_90pct": repair_success_rate >= 0.90,
        "planner_calls_zero": summary.get("planner_calls") == 0,
        "full_retry_calls_zero": summary.get("writer_retries") == 0,
        "provider_calls_at_most_2_per_section": provider_calls <= 30,
        "anchor_failures_zero": _violation_count(
            sections, "PATCH_ANCHOR_NOT_FOUND"
        )
        == 0,
        "post_resolution_expansion_zero": _violation_count(
            sections, "POST_RESOLUTION_EXPANSION"
        )
        == 0,
        "bad_commits_zero": _bad_commit_count(summary) == 0,
        "provider_errors_zero": summary.get("provider_errors") == 0,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "metrics": {
            "attempted": summary.get("attempted", 0),
            "committed": summary.get("committed", 0),
            "contract_pass": summary.get("contract_pass", 0),
            "length_in_range": in_range,
            "writer_first_pass": summary.get("writer_first_pass_pass", 0),
            "repairs": repairs,
            "repair_success": repair_success,
            "repair_success_rate": round(repair_success_rate, 4),
            "provider_calls": provider_calls,
            "planner_calls": summary.get("planner_calls", 0),
            "full_retry_calls": summary.get("writer_retries", 0),
            "prompt_tokens": summary.get("prompt_tokens", 0),
            "completion_tokens": summary.get("completion_tokens", 0),
            "repair_tokens": summary.get("repair_tokens", 0),
            "total_tokens": summary.get("total_tokens", 0),
            "mean_latency_seconds": summary.get("mean_latency_seconds", 0.0),
            "anchor_failures": _violation_count(
                sections, "PATCH_ANCHOR_NOT_FOUND"
            ),
            "post_resolution_expansions": _violation_count(
                sections, "POST_RESOLUTION_EXPANSION"
            ),
            "bad_commits": _bad_commit_count(summary),
            "provider_errors": summary.get("provider_errors", 0),
        },
    }


def _green_offline_for_current_source(state: dict[str, Any]) -> dict[str, Any]:
    source_hash = _source_tree_hash()
    matches = [
        item
        for item in state.get("offline_attempts", [])
        if item.get("source_tree_sha256") == source_hash
        and item.get("status") == "passed"
    ]
    if not matches:
        raise CycleError("current source tree has no green offline receipt")
    return matches[-1]


def _run_real_stage(
    evidence_root: Path,
    state: dict[str, Any],
    *,
    stage: str,
    provider_file: Path,
    provider_values: dict[str, str],
) -> dict[str, Any]:
    if stage not in {"g1", "g2"}:
        raise CycleError(f"unsupported real stage: {stage}")
    if state[stage]["status"] != "not_started":
        return state[stage]
    offline = _green_offline_for_current_source(state)
    if stage == "g2" and state["g1"]["status"] != "passed":
        raise CycleError("G2 is forbidden until G1 passes")
    run_dir = evidence_root / stage / "run"
    if run_dir.exists():
        raise CycleError(f"{stage.upper()} evidence already exists without a receipt")
    started = {
        "schema_version": f"p6-length-anchor-{stage}-v1",
        "started_at": _now(),
        "status": "running",
        "authorized_source_tree_sha256": offline["source_tree_sha256"],
        "authorized_head": _git("rev-parse", "HEAD"),
        "provider_file": str(provider_file.resolve()),
        "credential_persisted": False,
    }
    stage_dir = evidence_root / stage
    _atomic_json(stage_dir / "attempt.json", started)
    styles = "literary" if stage == "g1" else ",".join(HISTORICAL_STYLES)
    sections = "1" if stage == "g1" else "3"
    command = [
        sys.executable,
        "scripts/run_author_stage1_matrix.py",
        "--provider-file",
        str(provider_file.resolve()),
        "--themes",
        "action_conflict",
        "--styles",
        styles,
        "--sections-per-combo",
        sections,
        "--checkpoint-every",
        "1",
        "--runtime-rebuild-every",
        "2",
        "--combo-retries",
        "0",
        "--desired-length",
        "900",
        "--seed",
        "20260727",
        "--output-dir",
        str(run_dir),
    ]
    execution = _run_command(
        command,
        log_path=stage_dir / "provider-run.log",
        provider_values=provider_values,
    )
    matrix_path = run_dir / "stage1-matrix.json"
    matrix = _read_json(matrix_path, {})
    assessment = assess_g1(matrix) if stage == "g1" else assess_g2(matrix)
    receipt = {
        **started,
        "completed_at": _now(),
        "status": assessment["status"],
        "execution": execution,
        "assessment": assessment,
        "matrix": matrix_path.relative_to(evidence_root).as_posix(),
        "matrix_sha256": _sha256_file(matrix_path) if matrix_path.is_file() else "",
    }
    _atomic_json(stage_dir / "attempt.json", receipt)
    state[stage] = receipt
    state["status"] = f"{stage}_{receipt['status']}"
    state["updated_at"] = _now()
    _atomic_json(evidence_root / "cycle-state.json", state)
    return receipt


def _artifact_inventory(evidence_root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(evidence_root.rglob("*")):
        if not path.is_file() or path.name in FINAL_OUTPUT_NAMES:
            continue
        result.append(
            {
                "path": path.relative_to(evidence_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return result


def _render_report(report: dict[str, Any]) -> str:
    offline = report["offline"]
    g1 = report["g1"]
    g2 = report["g2"]
    lines = [
        "# P6 length and anchor recovery",
        "",
        f"VERDICT: `{report['verdict']}`",
        "",
        f"- Branch: `{report['git']['branch']}`",
        f"- Base HEAD: `{report['git']['base_head']}`",
        f"- Final HEAD: `{report['git']['head']}`",
        f"- Source tree SHA-256: `{report['git']['source_tree_sha256']}`",
        f"- Offline Gate: `{offline.get('status', 'not_run')}`",
        f"- G1: `{g1.get('status', 'not_started')}`",
        f"- G2: `{g2.get('status', 'not_started')}`",
        "",
        "## Real-provider metrics",
        "",
        f"- G1: `{json.dumps(g1.get('assessment', {}).get('metrics', {}), ensure_ascii=False)}`",
        f"- G2: `{json.dumps(g2.get('assessment', {}).get('metrics', {}), ensure_ascii=False)}`",
        "",
        "## Safety",
        "",
        f"- Previous P6 evidence unchanged: `{report['safety']['previous_evidence_unchanged']}`",
        f"- User-owned files unchanged: `{report['safety']['user_files_unchanged']}`",
        f"- Main merged: `{report['safety']['main_merged']}`",
        f"- Secret scan: `{report['secret_scan'].get('status', 'missing')}`",
        "",
        "See `recovery.md` for replay and inspection instructions.",
        "",
    ]
    return "\n".join(lines)


def _finalize(
    evidence_root: Path,
    state: dict[str, Any],
    *,
    previous_evidence_root: Path,
    user_root: Path,
    provider_values: dict[str, str],
) -> dict[str, Any]:
    git = _assert_git_identity()
    previous_unchanged = (
        state["previous_evidence_snapshot"]
        == _snapshot_previous_evidence(previous_evidence_root)
    )
    user_unchanged = state["user_snapshot"] == _user_snapshot(user_root)
    offline_matches = [
        item
        for item in state.get("offline_attempts", [])
        if item.get("source_tree_sha256") == git["source_tree_sha256"]
    ]
    offline = offline_matches[-1] if offline_matches else {"status": "not_run"}
    g1 = state.get("g1", {"status": "not_started"})
    g2 = state.get("g2", {"status": "not_started"})
    secret = _secret_scan(evidence_root, provider_values=provider_values)
    passed = (
        offline.get("status") == "passed"
        and g1.get("status") == "passed"
        and g2.get("status") == "passed"
        and secret.get("status") == "passed"
        and previous_unchanged
        and user_unchanged
    )
    verdict = (
        "P6_LENGTH_ANCHOR_RECOVERY_PASS"
        if passed
        else "P6_LENGTH_ANCHOR_RECOVERY_FAIL"
    )
    state["status"] = "complete"
    state["verdict"] = verdict
    state["updated_at"] = _now()
    _atomic_json(evidence_root / "cycle-state.json", state)
    recovery = "\n".join(
        [
            "# Recovery instructions",
            "",
            f"Branch: `{EXPECTED_BRANCH}`",
            f"Base HEAD: `{BASE_HEAD}`",
            f"Evaluated HEAD: `{git['head']}`",
            "",
            f"1. `git fetch origin {EXPECTED_BRANCH}`",
            f"2. `git switch {EXPECTED_BRANCH}`",
            "3. Inspect `report.json`, `cycle-state.json`, and the immutable G1/G2 receipts.",
            "4. Re-run only offline verification after a source change; do not repeat G1 or G2 in this cycle.",
            "5. Do not merge main, run seed 20260728, P7, P8, or human review from this receipt.",
            "",
        ]
    )
    _atomic_text(evidence_root / "recovery.md", recovery)
    artifacts = _artifact_inventory(evidence_root)
    manifest = {
        "schema_version": "p6-length-anchor-manifest-v1",
        "created_at": _now(),
        "cycle_id": CYCLE_ID,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    _atomic_json(evidence_root / "manifest.json", manifest)
    report = {
        "schema_version": "p6-length-anchor-final-report-v1",
        "created_at": _now(),
        "cycle_id": CYCLE_ID,
        "verdict": verdict,
        "git": {
            **git,
            "commits": _git(
                "log",
                "--reverse",
                "--format=%H%x09%s",
                f"{BASE_HEAD}..HEAD",
            ).splitlines(),
            "changed_files": _git(
                "diff", "--name-status", f"{BASE_HEAD}...HEAD"
            ).splitlines(),
        },
        "offline": offline,
        "g1": g1,
        "g2": g2,
        "secret_scan": secret,
        "safety": {
            "previous_evidence_unchanged": previous_unchanged,
            "user_files_unchanged": user_unchanged,
            "main_merged": False,
            "seed_20260728_run": False,
            "p7_run": False,
            "p8_run": False,
            "human_review_run": False,
        },
        "manifest": {
            "path": "manifest.json",
            "sha256": _sha256_file(evidence_root / "manifest.json"),
            "artifact_count": len(artifacts),
        },
    }
    _atomic_json(evidence_root / "report.json", report)
    _atomic_text(evidence_root / "report.md", _render_report(report))
    hashes = {
        name: _sha256_file(evidence_root / name)
        for name in (
            "cycle-state.json",
            "manifest.json",
            "recovery.md",
            "report.json",
            "report.md",
            "secret-scan.json",
        )
    }
    for stage in ("g1", "g2"):
        path = evidence_root / stage / "attempt.json"
        if path.is_file():
            hashes[f"{stage}/attempt.json"] = _sha256_file(path)
    _atomic_json(
        evidence_root / "artifact-sha256.json",
        {
            "schema_version": "p6-length-anchor-artifact-sha256-v1",
            "created_at": _now(),
            "hashes": hashes,
        },
    )
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("offline", "g1", "g2", "final"),
        required=True,
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=DEFAULT_EVIDENCE_ROOT,
    )
    parser.add_argument("--previous-evidence-root", type=Path, required=True)
    parser.add_argument("--user-root", type=Path, required=True)
    parser.add_argument("--provider-file", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    evidence_root = args.evidence_root.resolve()
    previous_evidence_root = args.previous_evidence_root.resolve()
    user_root = args.user_root.resolve()
    provider_file = args.provider_file.resolve()
    provider_values = _provider_values(provider_file)
    try:
        state = _load_and_verify(
            evidence_root,
            previous_evidence_root=previous_evidence_root,
            user_root=user_root,
        )
        if args.phase == "offline":
            result = _run_offline(
                evidence_root,
                state,
                provider_values=provider_values,
            )
        elif args.phase in {"g1", "g2"}:
            result = _run_real_stage(
                evidence_root,
                state,
                stage=args.phase,
                provider_file=provider_file,
                provider_values=provider_values,
            )
        else:
            result = _finalize(
                evidence_root,
                state,
                previous_evidence_root=previous_evidence_root,
                user_root=user_root,
                provider_values=provider_values,
            )
    except (CycleError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    status = str(result.get("status") or "")
    verdict = str(result.get("verdict") or "")
    if status == "passed" or verdict == "P6_LENGTH_ANCHOR_RECOVERY_PASS":
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
