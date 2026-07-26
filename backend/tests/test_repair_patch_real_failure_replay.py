from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.replay_repair_patch_failures import replay_fixture


FIXTURE = (
    Path(__file__).parent / "fixtures" / "repair_patch_real_failures.json"
)
FIXTURE_SHA256 = "6bcf279b9ed1019102e5aec18ffd1c9c0580f30f6a0013a5dde2f46652666daf"


def test_final_real_reject_fixture_is_frozen_and_sanitized() -> None:
    fixture_bytes = FIXTURE.read_bytes()
    canonical_bytes = fixture_bytes.replace(b"\r\n", b"\n")
    raw = canonical_bytes.decode("utf-8")
    payload = json.loads(raw)

    assert hashlib.sha256(canonical_bytes).hexdigest() == FIXTURE_SHA256
    assert payload["case_count"] == len(payload["cases"]) == 6
    assert len({case["case_id"] for case in payload["cases"]}) == 6
    assert "http://" not in raw and "https://" not in raw
    assert ":\\" not in raw
    assert "api_key" not in raw.lower()
    for case in payload["cases"]:
        original = case["original_candidate"]["narrative_text"]
        provider_repair = case["provider_repair_output"]["narrative_text"]
        assert hashlib.sha256(original.encode("utf-8")).hexdigest() == (
            case["original_sha256"]
        )
        assert hashlib.sha256(provider_repair.encode("utf-8")).hexdigest() == (
            case["provider_repair_sha256"]
        )


def test_final_six_real_rejects_receive_correct_local_patches() -> None:
    report = replay_fixture(FIXTURE)
    summary = report["summary"]

    assert summary["case_count"] == 6
    assert summary["passed_count"] == 6
    assert summary["success_rate"] == 1.0
    assert summary["patch_failure_count"] == 0
    assert summary["validator_failure_count"] == 0
    assert summary["repair_regression_count"] == 0
    assert summary["gate"]["passed"] is True
    assert all(
        item["patch_count"] >= 1 and item["patch_accepted"]
        for item in report["cases"]
    )
