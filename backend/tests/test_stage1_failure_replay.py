from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.replay_stage1_event_failures import replay_fixture


FIXTURE = Path(__file__).parent / "fixtures" / "stage1_event_repair_failures.json"


def test_stage1_failure_fixture_is_frozen_and_sanitized() -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    payload = json.loads(raw)

    assert payload["case_count"] == len(payload["cases"]) == 24
    assert len({case["case_id"] for case in payload["cases"]}) == 24
    assert "http://" not in raw and "https://" not in raw
    assert ":\\" not in raw
    assert "api_key" not in raw.lower()
    for case in payload["cases"]:
        digest = hashlib.sha256(
            case["original_candidate"]["narrative_text"].encode("utf-8")
        ).hexdigest()
        assert digest == case["original_sha256"]


def test_offline_event_repair_gate_recovers_at_least_22_of_24() -> None:
    report = replay_fixture(FIXTURE)
    summary = report["summary"]

    assert summary["case_count"] == 24
    assert summary["recovered_count"] >= 22
    assert summary["repair_success_rate"] >= 0.90
    assert summary["repair_regression_count"] == 0
    assert summary["bad_commit_count"] == 0
    assert summary["gate"]["passed"] is True
    assert all(case["final_contract_accepted"] for case in report["cases"])
