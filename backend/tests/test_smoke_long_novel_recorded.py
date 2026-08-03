from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.smoke_long_novel_recorded import (
    DEFAULT_CHAPTER_COUNT,
    DEFAULT_SECTIONS_PER_CHAPTER,
    FAILURE_SENTINEL,
    REJECTED_SENTINEL,
    main,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_recorded_long_novel_cli_and_artifacts_fail_closed(
    tmp_path: Path,
    capsys,
) -> None:
    output = tmp_path / "recorded-long-novel"
    result = main(
        [
            "--output-dir",
            str(output),
            "--chapters",
            "3",
            "--sections-per-chapter",
            "2",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0, captured.err
    public_result = json.loads(captured.out)
    assert public_result["ok"] is True
    assert public_result["chapter_count"] == 3
    assert public_result["section_count"] == 6

    manuscript_path = output / "manuscript.txt"
    evidence_path = output / "evidence.json"
    summary_path = output / "summary.json"
    assert manuscript_path.is_file()
    assert evidence_path.is_file()
    assert summary_path.is_file()
    assert (output / "state" / "production_spec.json").is_file()

    manuscript = manuscript_path.read_text(encoding="utf-8")
    evidence_text = evidence_path.read_text(encoding="utf-8")
    summary_text = summary_path.read_text(encoding="utf-8")
    evidence = json.loads(evidence_text)
    summary = json.loads(summary_text)
    assert FAILURE_SENTINEL not in manuscript
    assert REJECTED_SENTINEL not in manuscript
    assert FAILURE_SENTINEL not in evidence_text
    assert REJECTED_SENTINEL not in evidence_text
    assert "第0001章第01节潮声记" in manuscript
    assert "第0001章第01节潮声记" not in evidence_text
    assert "第0001章第01节潮声记" not in summary_text

    assert evidence["schema_version"] == "recorded-long-novel-evidence-v1"
    assert summary["schema_version"] == "recorded-long-novel-summary-v1"
    assert evidence["provider_calls"] == 0
    assert evidence["network_calls"] == 0
    assert all(evidence["gates"].values())
    assert all(summary["gates"].values())
    metrics = evidence["metrics"]
    assert metrics["service_restart_count"] >= 3
    assert metrics["pause_resume_count"] >= 2
    assert metrics["duplicate_section_count"] == 0
    assert metrics["duplicate_transaction_count"] == 0
    assert metrics["recovery_duplicate_count"] == 0
    assert metrics["hard_fact_bad_commit_count"] == 0
    assert metrics["state_bad_commit_count"] == 0
    assert metrics["thread_bad_commit_count"] == 0
    assert metrics["rejected_prose_count"] == 0
    assert metrics["thread_liveness_violation_count"] == 0
    assert metrics["style_snapshot_mismatch_count"] == 0
    assert metrics["planned_total_deviation_ratio"] <= 0.10
    assert metrics["chapter_range_ratio"] >= 0.95
    assert metrics["canonical_revision_final"] == 7

    retry = evidence["retry"]
    assert retry["new_attempt"] is True
    assert retry["new_transaction"] is True
    assert retry["attempt_numbers"] == [1, 2]
    assert retry["final_statuses"] == ["failed", "committed"]
    assert len(set(retry["transaction_ids"])) == 2

    transition = evidence["style_transition"]
    assert transition["applies_from_chapter_ordinal"] == 2
    chapter_styles = [
        chapter["style_profile_id"] for chapter in evidence["chapters"]
    ]
    assert chapter_styles[0] == transition["initial_style_profile_id"]
    assert chapter_styles[1:] == [
        transition["custom_style_profile_id"],
        transition["custom_style_profile_id"],
    ]

    assert summary["artifacts"]["manuscript.txt"]["sha256"] == _sha256(
        manuscript_path
    )
    assert summary["artifacts"]["evidence.json"]["sha256"] == _sha256(
        evidence_path
    )
    assert public_result["summary_sha256"] == _sha256(summary_path)

    protected = {
        path.relative_to(output).as_posix(): _sha256(path)
        for path in output.rglob("*")
        if path.is_file()
    }
    repeated = main(
        [
            "--output-dir",
            str(output),
            "--chapters",
            "3",
            "--sections-per-chapter",
            "2",
        ]
    )
    repeated_output = capsys.readouterr()
    assert repeated == 2
    assert json.loads(repeated_output.err)["error_type"] == "FileExistsError"
    assert {
        path.relative_to(output).as_posix(): _sha256(path)
        for path in output.rglob("*")
        if path.is_file()
    } == protected


def test_recorded_long_novel_hard_defaults() -> None:
    assert DEFAULT_CHAPTER_COUNT == 30
    assert DEFAULT_SECTIONS_PER_CHAPTER >= 2
