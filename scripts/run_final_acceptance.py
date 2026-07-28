"""Run the fail-closed Novel Auto final acceptance and publish local evidence."""

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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVIDENCE_ROOT = ROOT / ".tmp" / "final-goal-20260728"
BASE_HEAD = "b87371a3dad3a885615e3bab490a39a15f39b410"
EXPECTED_BRANCH = "codex/novel-auto-final-goal-20260728"
REQUIRED_DELIVERABLES = (
    "docs/FINAL_GOAL.md",
    "docs/FINAL_ARCHITECTURE.md",
    "docs/FINAL_ACCEPTANCE.md",
    "docs/FINAL_MIGRATION_ROLLBACK.md",
    "docs/iter/final-goal-20260728.md",
    "README.md",
    "CHANGELOG.md",
    "scripts/run_final_acceptance.py",
)
P6_ATTEMPTS = (
    "seed-20260727",
    "seed-20260727-attempt-02",
    "seed-20260727-attempt-03",
)
FINAL_OUTPUT_NAMES = {
    "manifest.json",
    "report.json",
    "report.md",
    "artifact-sha256.json",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(text, encoding="utf-8", newline="\n")
    os.replace(partial, path)


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def _source_tree_hash() -> str:
    paths = _git(
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ).split("\0")
    digest = hashlib.sha256()
    for raw in sorted(item for item in paths if item):
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


def _provider_values(run_state: dict[str, Any]) -> dict[str, str]:
    user_root = Path(
        str(run_state.get("user_owned_state", {}).get("root") or "")
    )
    provider_file = user_root / "coding.txt"
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
    redacted = text
    for name in ("KEY", "URL"):
        value = provider_values.get(name, "")
        if value:
            redacted = redacted.replace(value, f"[REDACTED_{name}]")
    return redacted


def _is_actionable_secret_finding(
    finding: dict[str, str],
    changed_values: set[str],
) -> bool:
    """Gate artifacts and task-scope files while retaining baseline evidence."""
    return (
        finding.get("scope") == "artifact"
        or finding.get("path", "") in changed_values
    )


def _offline_specs() -> dict[str, list[str]]:
    npm = shutil.which("npm") or "npm"
    return {
        "backend_tests": [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/",
            "-q",
            "-W",
            "error",
        ],
        "ruff": [sys.executable, "-m", "ruff", "check", "backend", "scripts"],
        "compileall": [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "backend",
            "scripts",
        ],
        "author_ui": [npm, "--prefix", "frontend", "run", "test:author"],
        "frontend_build": [npm, "--prefix", "frontend", "run", "build"],
        "npm_production_audit": [
            npm,
            "--prefix",
            "frontend",
            "audit",
            "--omit=dev",
        ],
        "git_diff_check": ["git", "diff", "--check"],
    }


def _run_one_check(
    name: str,
    command: list[str],
    *,
    log_dir: Path,
    evidence_root: Path,
    provider_values: dict[str, str],
) -> tuple[str, dict[str, Any]]:
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
    duration = round(time.perf_counter() - started, 3)
    output = _redact(
        "\n".join(part for part in (result.stdout, result.stderr) if part),
        provider_values,
    )
    log_path = log_dir / f"{name}.log"
    _atomic_text(log_path, output)
    passed_match = re.search(r"(\d+)\s+passed", output)
    return name, {
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "duration_seconds": duration,
        "passed": int(passed_match.group(1)) if passed_match else None,
        "command": command,
        "log": log_path.relative_to(evidence_root).as_posix(),
        "log_sha256": _sha256_file(log_path),
    }


def _run_offline(
    evidence_root: Path,
    *,
    provider_values: dict[str, str],
    resume: bool,
) -> dict[str, Any]:
    offline_dir = evidence_root / "offline"
    result_path = offline_dir / "final-offline.json"
    source_hash = _source_tree_hash()
    existing = _read_json(result_path, {})
    if (
        resume
        and existing.get("source_tree_sha256") == source_hash
        and existing.get("status") == "passed"
    ):
        return {**existing, "reused": True}

    log_dir = offline_dir / "logs"
    results: dict[str, Any] = {}
    specs = _offline_specs()
    with ThreadPoolExecutor(max_workers=len(specs)) as executor:
        futures = {
            executor.submit(
                _run_one_check,
                name,
                command,
                log_dir=log_dir,
                evidence_root=evidence_root,
                provider_values=provider_values,
            ): name
            for name, command in specs.items()
        }
        for future in as_completed(futures):
            name, payload = future.result()
            results[name] = payload
    payload = {
        "schema_version": "novel-auto-final-offline-v1",
        "created_at": _now(),
        "source_tree_sha256": source_hash,
        "status": (
            "passed"
            if all(item["status"] == "passed" for item in results.values())
            else "failed"
        ),
        "reused": False,
        "checks": dict(sorted(results.items())),
    }
    _atomic_json(result_path, payload)
    return payload


def _scan_secrets(
    evidence_root: Path,
    *,
    provider_values: dict[str, str],
) -> dict[str, Any]:
    exact_values = {
        "api_key": provider_values.get("KEY", ""),
        "base_url": provider_values.get("URL", ""),
    }
    findings: list[dict[str, str]] = []
    baseline_findings: list[dict[str, str]] = []
    tracked_values = {
        value for value in _git("ls-files", "-z").split("\0") if value
    }
    changed_values = {
        value
        for value in _git(
            "diff",
            "--name-only",
            f"{BASE_HEAD}...HEAD",
            "-z",
        ).split("\0")
        if value
    }
    changed_values.update(
        value
        for value in _git("diff", "--name-only", "-z").split("\0")
        if value
    )
    changed_values.update(
        value
        for value in _git(
            "diff",
            "--cached",
            "--name-only",
            "-z",
        ).split("\0")
        if value
    )
    changed_values.update(
        value
        for value in _git(
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
        ).split("\0")
        if value and not value.startswith(".tmp/")
    )
    tracked = [ROOT / value for value in sorted(tracked_values)]
    artifacts = [
        path
        for path in evidence_root.rglob("*")
        if path.is_file() and path.name != "secret-scan.json"
    ]
    for scope, paths in (("tracked", tracked), ("artifact", artifacts)):
        for path in paths:
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            for kind, value in exact_values.items():
                if value and value.encode("utf-8") in raw:
                    relative = (
                        path.relative_to(ROOT).as_posix()
                        if path.is_relative_to(ROOT)
                        else path.name
                    )
                    finding = {
                        "scope": scope,
                        "path": relative,
                        "kind": f"exact_{kind}",
                    }
                    if _is_actionable_secret_finding(finding, changed_values):
                        findings.append(finding)
                    else:
                        baseline_findings.append(finding)
    diff = "\n".join(
        (
            _git("diff", f"{BASE_HEAD}...HEAD", "--", check=False),
            _git("diff", "--", check=False),
        )
    )
    generic_hits = re.findall(r"sk-[A-Za-z0-9_-]{20,}", diff)
    payload = {
        "schema_version": "novel-auto-secret-scan-v1",
        "created_at": _now(),
        "status": "passed" if not findings and not generic_hits else "failed",
        "branch_files_scanned": len(changed_values),
        "baseline_tracked_files_scanned": len(tracked),
        "artifact_files_scanned": len(artifacts),
        "exact_api_key_hits": sum(
            item["kind"] == "exact_api_key" for item in findings
        ),
        "exact_base_url_hits": sum(
            item["kind"] == "exact_base_url" for item in findings
        ),
        "actionable_diff_secret_hits": len(generic_hits),
        "findings": findings,
        "pre_existing_baseline_findings": baseline_findings,
        "pre_existing_baseline_finding_count": len(baseline_findings),
        "baseline_findings_affect_gate": False,
        "secret_values_persisted": False,
    }
    _atomic_json(evidence_root / "secret-scan.json", payload)
    return payload


def _collect_p6(evidence_root: Path) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    known_tokens = 0
    recorded_calls = 0
    latencies: list[float] = []
    for name in P6_ATTEMPTS:
        path = evidence_root / "p6" / name / "stage1-matrix.json"
        matrix = _read_json(path, {})
        if not matrix:
            continue
        summary = matrix.get("summary", {})
        sections = [
            section
            for combination in matrix.get("combinations", [])
            for section in combination.get("sections", [])
        ]
        known_tokens += int(summary.get("total_tokens", 0))
        recorded_calls += int(summary.get("provider_calls", 0))
        latencies.extend(
            float(item.get("latency_seconds", 0.0))
            for item in sections
            if float(item.get("latency_seconds", 0.0)) > 0
        )
        attempts.append(
            {
                "name": name,
                "artifact": path.relative_to(evidence_root).as_posix(),
                "sha256": _sha256_file(path),
                "config": matrix.get("config", {}),
                "summary": summary,
            }
        )
    latencies.sort()
    p95 = (
        latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        if latencies
        else 0.0
    )
    return {
        "status": "failed",
        "reason": "historical seed failed after maximum two repair rounds",
        "classification": [
            "PROVIDER_ERROR",
            "WRITER_EXECUTION_FAILURE",
            "REPAIR_FAILURE",
            "VALIDATOR_TRUE_REJECTION",
        ],
        "attempts": attempts,
        "quota_smoke_calls": 3,
        "quota_smoke_evidence": "execution log; response bodies not persisted",
        "recorded_matrix_provider_calls": recorded_calls,
        "inferred_unrecorded_provider_calls": 1,
        "total_provider_calls_lower_bound": recorded_calls + 4,
        "known_total_tokens": known_tokens,
        "unknown_token_calls": 4,
        "known_mean_latency_seconds": (
            round(sum(latencies) / len(latencies), 4) if latencies else 0.0
        ),
        "known_p95_latency_seconds": round(p95, 4),
        "planner_provider_calls": 0,
        "full_retry_provider_calls": 0,
        "hard_fact_state_thread_bad_commits": 0,
        "repair_rounds_used": 2,
        "repair_round_limit": 2,
        "seed_20260728": "not_run_due_to_historical_seed_failure",
    }


def _overall_verdict(
    gates: dict[str, dict[str, Any]],
    *,
    offline_status: str,
    secret_status: str,
    human_review_status: str = "not_started",
) -> str:
    if offline_status != "passed" or secret_status != "passed":
        return "NOVEL_AUTO_FINAL_FAIL"
    if any(item.get("status") == "failed" for item in gates.values()):
        return "NOVEL_AUTO_FINAL_FAIL"
    if any(item.get("status") == "blocked" for item in gates.values()):
        return "NOVEL_AUTO_FINAL_BLOCKED"
    if all(gates.get(f"P{index}", {}).get("status") == "passed" for index in range(9)):
        return (
            "NOVEL_AUTO_FINAL_PASS"
            if human_review_status == "passed"
            else "NOVEL_AUTO_FINAL_CANDIDATE"
        )
    return "NOVEL_AUTO_FINAL_FAIL"


def _artifact_inventory(evidence_root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(evidence_root.rglob("*")):
        if not path.is_file() or path.name in FINAL_OUTPUT_NAMES:
            continue
        items.append(
            {
                "path": path.relative_to(evidence_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return items


def _render_report(report: dict[str, Any]) -> str:
    lines = [
        "# Novel Auto final acceptance",
        "",
        f"Verdict: `{report['verdict']}`",
        "",
        f"- Branch: `{report['git']['branch']}`",
        f"- Base HEAD: `{report['git']['base_head']}`",
        f"- Evaluated HEAD: `{report['git']['head']}`",
        f"- Offline Gate: `{report['offline']['status']}`",
        f"- Secret scan: `{report['secret_scan']['status']}`",
        "",
        "## Gates",
        "",
        "| Gate | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for gate, value in sorted(report["gates"].items()):
        lines.append(
            f"| {gate} | {value.get('status', 'unknown')} | "
            f"{value.get('detail', '')} |"
        )
    p6 = report["phase_results"]["P6"]
    lines.extend(
        [
            "",
            "## P6 hard stop",
            "",
            f"- Reason: {p6['reason']}",
            f"- Known provider tokens: {p6['known_total_tokens']}",
            f"- Provider-call lower bound: {p6['total_provider_calls_lower_bound']}",
            f"- Planner/Retry provider calls: "
            f"{p6['planner_provider_calls']}/{p6['full_retry_provider_calls']}",
            f"- Bad fact/state/thread commits: "
            f"{p6['hard_fact_state_thread_bad_commits']}",
            "",
            "P7 and P8 were not entered because P6 is a strict prerequisite.",
            "",
            "## Recovery",
            "",
            "See `recovery.md`. The P6 repair-round limit is exhausted; recovery "
            "preserves checkpoints but does not authorize another real rerun.",
            "",
        ]
    )
    return "\n".join(lines)


def _recovery_text(branch: str, head: str) -> str:
    return "\n".join(
        [
            "# Recovery instructions",
            "",
            f"Branch: `{branch}`",
            f"Evidence evaluated at: `{head}`",
            "",
            "1. Fetch the branch and check it out without merging main.",
            "2. Run `python scripts/run_final_acceptance.py --resume` to verify "
            "the same source tree and reuse a matching green offline receipt.",
            "3. Inspect `p6/seed-20260727-attempt-03/` and the frozen P6 fixtures.",
            "4. Do not resume P7/P8: the P6 two-repair-round allowance is exhausted.",
            "5. A further real P6 attempt requires a new explicitly authorized "
            "development cycle, new evidence directory, and unchanged historical seed.",
            "",
        ]
    )


def run(*, evidence_root: Path, resume: bool) -> dict[str, Any]:
    evidence_root.mkdir(parents=True, exist_ok=True)
    run_state_path = evidence_root / "run-state.json"
    run_state = _read_json(run_state_path, {})
    provider_values = _provider_values(run_state)
    offline = _run_offline(
        evidence_root,
        provider_values=provider_values,
        resume=resume,
    )
    p6 = _collect_p6(evidence_root)
    gates = dict(run_state.get("gates", {}))
    gates["P6"] = {
        "status": "failed",
        "detail": p6["reason"],
    }
    gates["P7"] = {
        "status": "not_run",
        "detail": "strictly skipped because P6 failed",
    }
    gates["P8"] = {
        "status": "not_run",
        "detail": "strictly skipped because P6 failed",
    }
    deliverables = {
        item: (ROOT / item).is_file() for item in REQUIRED_DELIVERABLES
    }
    branch = _git("branch", "--show-current")
    head = _git("rev-parse", "HEAD")
    _atomic_text(evidence_root / "recovery.md", _recovery_text(branch, head))
    secret_scan = _scan_secrets(
        evidence_root,
        provider_values=provider_values,
    )
    p9_passed = (
        offline["status"] == "passed"
        and secret_scan["status"] == "passed"
        and all(deliverables.values())
        and branch == EXPECTED_BRANCH
    )
    gates["P9"] = {
        "status": "passed" if p9_passed else "failed",
        "detail": (
            "final runner, docs, offline Gate, secret scan and recovery delivered"
            if p9_passed
            else "final delivery prerequisites are incomplete"
        ),
    }
    verdict = _overall_verdict(
        gates,
        offline_status=offline["status"],
        secret_status=secret_scan["status"],
    )
    run_state.update(
        {
            "updated_at": _now(),
            "status": "complete",
            "verdict": verdict,
            "gates": gates,
            "next_gate": None,
            "phase_results": {
                **run_state.get("phase_results", {}),
                "P6": p6,
                "P7": {"status": "not_run_due_to_p6_failure"},
                "P8": {"status": "not_run_due_to_p6_failure"},
                "P9": {
                    "status": gates["P9"]["status"],
                    "offline": offline,
                    "secret_scan_status": secret_scan["status"],
                    "deliverables": deliverables,
                },
            },
            "resume": {
                "command": (
                    f"cd /d {ROOT} && python scripts\\run_final_acceptance.py "
                    "--resume"
                ),
                "note": (
                    "Verifies the completed FAIL evidence; does not authorize "
                    "another P6 real-provider attempt."
                ),
            },
        }
    )
    _atomic_json(run_state_path, run_state)
    manifest = {
        "schema_version": "novel-auto-final-manifest-v1",
        "created_at": _now(),
        "evidence_root": str(evidence_root),
        "artifact_count": 0,
        "artifacts": _artifact_inventory(evidence_root),
    }
    manifest["artifact_count"] = len(manifest["artifacts"])
    _atomic_json(evidence_root / "manifest.json", manifest)
    report = {
        "schema_version": "novel-auto-final-report-v1",
        "created_at": _now(),
        "verdict": verdict,
        "git": {
            "branch": branch,
            "base_head": BASE_HEAD,
            "head": head,
            "commits": _git(
                "log",
                "--reverse",
                "--format=%H%x09%s",
                f"{BASE_HEAD}..HEAD",
            ).splitlines(),
            "changed_files": _git(
                "diff",
                "--name-status",
                f"{BASE_HEAD}...HEAD",
            ).splitlines(),
        },
        "gates": gates,
        "phase_results": {
            **run_state.get("phase_results", {}),
            "P6": p6,
        },
        "offline": offline,
        "secret_scan": secret_scan,
        "deliverables": deliverables,
        "human_review_status": "not_started_due_to_p6_failure",
        "manifest": {
            "path": "manifest.json",
            "sha256": _sha256_file(evidence_root / "manifest.json"),
            "artifact_count": manifest["artifact_count"],
        },
        "user_owned_files_included": False,
        "main_merged": False,
        "unfinished": [
            "Mini seed 20260727 did not pass after two repair rounds.",
            "Mini seed 20260728, P7 Full Matrix, P8 real long-run and human review were not run.",
        ],
    }
    _atomic_json(evidence_root / "report.json", report)
    _atomic_text(evidence_root / "report.md", _render_report(report))
    key_artifacts = [
        "manifest.json",
        "report.json",
        "report.md",
        "secret-scan.json",
        "run-state.json",
        "recovery.md",
        "p6/seed-20260727/stage1-matrix.json",
        "p6/seed-20260727-attempt-02/stage1-matrix.json",
        "p6/seed-20260727-attempt-03/stage1-matrix.json",
    ]
    hashes = {
        relative: _sha256_file(evidence_root / relative)
        for relative in key_artifacts
        if (evidence_root / relative).is_file()
    }
    _atomic_json(
        evidence_root / "artifact-sha256.json",
        {
            "schema_version": "novel-auto-final-artifact-sha256-v1",
            "created_at": _now(),
            "artifacts": hashes,
        },
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=DEFAULT_EVIDENCE_ROOT,
    )
    args = parser.parse_args()
    report = run(
        evidence_root=args.evidence_root.resolve(),
        resume=args.resume,
    )
    print(f"VERDICT: {report['verdict']}")
    print(f"REPORT: {args.evidence_root / 'report.json'}")
    return 0 if report["verdict"] in {
        "NOVEL_AUTO_FINAL_PASS",
        "NOVEL_AUTO_FINAL_CANDIDATE",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
