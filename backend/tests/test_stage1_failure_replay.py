from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.replay_stage1_event_failures import replay_fixture


FIXTURE = Path(__file__).parent / "fixtures" / "stage1_event_repair_failures.json"
FIXTURE_SHA256 = "8ec6567bc2c9cff0e96956a865e8a53e49c9e55961af9f91307a29d00646eae6"


def test_stage1_failure_fixture_is_frozen_and_sanitized() -> None:
    fixture_bytes = FIXTURE.read_bytes()
    canonical_bytes = fixture_bytes.replace(b"\r\n", b"\n")
    raw = canonical_bytes.decode("utf-8")
    payload = json.loads(raw)

    assert hashlib.sha256(canonical_bytes).hexdigest() == FIXTURE_SHA256
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


def test_offline_patch_repair_gate_recovers_all_24() -> None:
    report = replay_fixture(FIXTURE)
    summary = report["summary"]

    assert summary["case_count"] == 24
    assert summary["recovered_count"] == 24
    assert summary["repair_success_rate"] >= 0.90
    assert summary["repair_regression_count"] == 0
    assert summary["bad_commit_count"] == 0
    assert summary["gate"]["passed"] is True
    assert all(case["final_contract_accepted"] for case in report["cases"])
