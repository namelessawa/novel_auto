from __future__ import annotations

import hashlib
import json
from pathlib import Path


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "p6_seed_20260727_final_repair_reject.json"
)
FIXTURE_SHA256 = "9abc51f5c2be8725c1b8e164ae675b6eb6910ef8f0a38a8f387b14159f00be2b"


def test_final_p6_failure_is_frozen_and_cannot_be_counted_as_pass() -> None:
    canonical = FIXTURE.read_bytes().replace(b"\r\n", b"\n")
    evidence = json.loads(canonical)

    assert hashlib.sha256(canonical).hexdigest() == FIXTURE_SHA256
    assert evidence["maximum_repair_rounds_exhausted"] is True
    assert evidence["expected_verdict"] == "NOVEL_AUTO_FINAL_FAIL"
    assert evidence["committed"] is False
    assert evidence["required_events_completed"] == evidence["required_events_total"]
    assert (
        evidence["required_end_states_reached"]
        == evidence["required_end_states_total"]
    )
    assert evidence["repair_patch_violation_codes"] == [
        "PATCH_ANCHOR_NOT_FOUND"
    ]
    assert evidence["state_conflict_commits"] == 0
    assert evidence["illegal_thread_change_commits"] == 0
    assert evidence["evidenceless_state_delta_commits"] == 0
