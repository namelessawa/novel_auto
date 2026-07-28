from __future__ import annotations

from scripts.run_final_acceptance import (
    _is_actionable_secret_finding,
    _overall_verdict,
)


def _gates(status: str = "passed") -> dict[str, dict[str, str]]:
    return {f"P{index}": {"status": status} for index in range(9)}


def test_final_runner_fails_closed_on_p6_failure() -> None:
    gates = _gates()
    gates["P6"] = {"status": "failed"}
    gates["P7"] = {"status": "not_run"}
    gates["P8"] = {"status": "not_run"}

    assert _overall_verdict(
        gates,
        offline_status="passed",
        secret_status="passed",
    ) == "NOVEL_AUTO_FINAL_FAIL"


def test_final_runner_never_turns_missing_gate_into_candidate() -> None:
    gates = _gates()
    gates["P8"] = {"status": "not_run"}

    assert _overall_verdict(
        gates,
        offline_status="passed",
        secret_status="passed",
    ) == "NOVEL_AUTO_FINAL_FAIL"


def test_final_runner_candidate_requires_all_automated_gates() -> None:
    assert _overall_verdict(
        _gates(),
        offline_status="passed",
        secret_status="passed",
    ) == "NOVEL_AUTO_FINAL_CANDIDATE"


def test_final_runner_secret_or_offline_failure_is_final_fail() -> None:
    assert _overall_verdict(
        _gates(),
        offline_status="failed",
        secret_status="passed",
    ) == "NOVEL_AUTO_FINAL_FAIL"


def test_pre_existing_public_endpoint_does_not_hide_task_scope_gate() -> None:
    changed = {"docs/FINAL_ACCEPTANCE.md"}
    baseline = {
        "scope": "tracked",
        "path": "docs/iter/pre-existing-provider-report.json",
        "kind": "exact_base_url",
    }
    task_file = {
        "scope": "tracked",
        "path": "docs/FINAL_ACCEPTANCE.md",
        "kind": "exact_base_url",
    }
    artifact = {
        "scope": "artifact",
        "path": "report.json",
        "kind": "exact_api_key",
    }

    assert _is_actionable_secret_finding(baseline, changed) is False
    assert _is_actionable_secret_finding(task_file, changed) is True
    assert _is_actionable_secret_finding(artifact, changed) is True
    assert _overall_verdict(
        _gates(),
        offline_status="passed",
        secret_status="failed",
    ) == "NOVEL_AUTO_FINAL_FAIL"
