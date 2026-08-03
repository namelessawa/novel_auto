from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_final_long_novel_acceptance as acceptance


class FakeProviderConfig:
    provider = "custom"
    model = "glm-5.2"
    thinking_mode = "disabled"
    max_retries = 0
    source = "provider_file"
    api_key = "test-only-exact-provider-key-123456"
    base_url = "https://test-provider.invalid/v1"

    def diagnostics(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "source": self.source,
            "thinking_mode": self.thinking_mode,
            "retries": self.max_retries,
            "credential_present": True,
            "config_fingerprint": "a1b2c3d4e5f60708",
            "key_fingerprint": "1234abcd",
        }


def _identity(source: str = "SOURCE") -> dict[str, str]:
    return {
        "branch": acceptance.EXPECTED_BRANCH,
        "head": acceptance.BASELINE_HEAD,
        "baseline_head": acceptance.BASELINE_HEAD,
        "source_tree_sha256": source,
    }


def _user_and_previous(tmp_path: Path) -> tuple[Path, Path, Path]:
    user_root = tmp_path / "user-root"
    user_root.mkdir()
    provider_file = user_root / "coding.txt"
    provider_file.write_text(
        "KEY=test-only-exact-provider-key-123456\n"
        "URL=https://test-provider.invalid/v1\n"
        "MODEL=glm-5.2\n",
        encoding="utf-8",
    )
    (user_root / ".env").write_text("SAFE_TEST_VALUE=1\n", encoding="utf-8")
    (user_root / "config.json").write_text("{}\n", encoding="utf-8")
    previous = tmp_path / "previous-evidence"
    previous.mkdir()
    (previous / "receipt.json").write_text('{"status":"frozen"}\n', encoding="utf-8")
    return user_root, previous, provider_file


def _state(*, source: str = "SOURCE") -> dict:
    return {
        "git": _identity(source),
        "authorized_source_tree_sha256": source,
        "authorized_head": acceptance.BASELINE_HEAD,
        "protected": {},
        "provider_runtime": acceptance._safe_provider(FakeProviderConfig()),
        "phases": {
            phase: {"status": "not_started"} for phase in acceptance.PHASES
        },
    }


def _section(*, length: int = 1_000) -> dict:
    return {
        "initial_narrative_length": length - 100,
        "initial_length_report": {"chars": length - 100},
        "narrative_length": length,
        "writer_block_nonspace_lengths": [100] * 10,
        "writer_cell_nonspace_lengths": [19] * 51 + [31],
        "writer_cell_sentence_boundary_counts": [1] * 52,
        "repair_patch_nonspace_lengths": [300, 122],
        "repair_patch_total_nonspace_chars": 422,
        "repair_patch_max_nonspace_chars": 300,
        "required_events_completed": 1,
        "required_events_total": 1,
        "end_states_reached": 1,
        "end_states_total": 1,
        "repair_audit_codes": [],
        "repair_patch_codes": [],
        "narrative_violation_codes": [],
        "state_violation_codes": [],
        "transaction_id": "tx",
        "section_id": "section",
        "committed": True,
        "runtime_provider": "custom",
        "runtime_provider_model": "glm-5.2",
        "runtime_provider_source": "provider_file",
        "runtime_provider_config_fingerprint": "a1b2c3d4e5f60708",
        "planner_calls": 0,
        "writer_calls": 1,
        "structured_output_repair_count": 0,
    }


def _provider_failure_row() -> dict:
    return {
        "section": 1,
        "attempt": 1,
        "provider_failure": True,
        "provider_code": "PROVIDER_OUTPUT_INVALID",
        "provider_http_category": "output_invalid",
        "provider_stage": "writer_json_repair",
        "planner_calls": 0,
        "writer_calls": 1,
        "structured_output_repair_count": 1,
        "provider_call_count": 2,
        "provider_call_count_known": True,
        "transaction_phase": "failed",
        "runtime_provider": "custom",
        "runtime_provider_model": "glm-5.2",
        "runtime_provider_source": "provider_file",
        "runtime_provider_config_fingerprint": "a1b2c3d4e5f60708",
    }


def _matrix(*, count: int, first_pass: int, repairs: int = 0) -> dict:
    sections = [_section() for _ in range(count)]
    for index, section in enumerate(sections, start=1):
        section["transaction_id"] = f"tx_{index:02d}"
        section["section_id"] = f"section_{index:02d}"
        if index > count - repairs:
            section["writer_calls"] = 2
    return {
        "combinations": [{"integrity": [], "sections": sections}],
        "summary": {
            "attempted": count,
            "committed": count,
            "contract_pass": count,
            "writer_first_pass_pass": first_pass,
            "repairs": repairs,
            "repair_success": repairs,
            "provider_calls": count + repairs,
            "planner_calls": 0,
            "writer_retries": 0,
            "provider_errors": 0,
            "data_integrity_violations": [],
            "hard_fact_error_commits": 0,
            "state_conflict_commits": 0,
            "illegal_thread_change_commits": 0,
            "evidenceless_state_delta_commits": 0,
        },
    }


def _topology_matrix(stage: str) -> dict:
    styles = ["literary"] if stage == "g1" else list(acceptance.HISTORICAL_STYLES)
    sections_per_combo = 1 if stage == "g1" else 3
    sections = []
    combinations = []
    ordinal = 0
    for style in styles:
        combination_sections = []
        for _ in range(sections_per_combo):
            ordinal += 1
            section = _section()
            section["transaction_id"] = f"tx_{stage}_{ordinal:02d}"
            section["section_id"] = f"section_{stage}_{ordinal:02d}"
            section["writer_first_pass_pass"] = ordinal <= (1 if stage == "g1" else 9)
            section["repair_performed"] = stage == "g2" and ordinal > 9
            section["repair_success"] = section["repair_performed"]
            section["writer_calls"] = 2 if section["repair_performed"] else 1
            combination_sections.append(section)
            sections.append(section)
        combinations.append(
            {
                "run_id": f"run_{stage}_{style}",
                "theme": "action_conflict",
                "style": style,
                "summary": {},
                "integrity": [],
                "sections": combination_sections,
            }
        )
    repairs = 0 if stage == "g1" else 6
    return {
        "config": {
            "themes": ["action_conflict"],
            "styles": styles,
            "seed": 20260727,
            "provider": "custom",
            "model": "glm-5.2",
            "thinking_mode": "disabled",
            "sections_per_combo": sections_per_combo,
            "desired_length": 900,
            "checkpoint_every": 1,
            "runtime_rebuild_every": 2,
            "id_namespace": stage,
        },
        "evidence_boundary": {
            "deterministic": True,
            "recorded": False,
            "real_provider": True,
            "human_review": False,
            "llm_judge": False,
        },
        "combinations": combinations,
        "summary": {
            "attempted": len(sections),
            "committed": len(sections),
            "contract_pass": len(sections),
            "writer_first_pass_pass": 1 if stage == "g1" else 9,
            "repairs": repairs,
            "repair_success": repairs,
            "provider_calls": len(sections) + repairs,
            "planner_calls": 0,
            "writer_retries": 0,
            "provider_errors": 0,
            "data_integrity_violations": [],
            "hard_fact_error_commits": 0,
            "state_conflict_commits": 0,
            "illegal_thread_change_commits": 0,
            "evidenceless_state_delta_commits": 0,
        },
    }


def _product_evidence(manuscript_sha256: str, manuscript_bytes: int) -> dict:
    gates = {
        key: True
        for key in (
            "provider_contract",
            "three_committed_chapters",
            "single_section_per_chapter",
            "chapter_lengths_in_range",
            "style_applies_only_to_third",
            "planner_zero",
            "full_writer_retry_zero",
            "provider_call_accounting",
            "formal_transactions",
            "provider_receipts_bound_to_transactions",
            "attempts_committed_only",
            "no_rejected_prose_published",
            "unique_transactions_and_sections",
            "canonical_revision_contiguous",
            "outline_progress_committed",
            "no_job_retry",
            "pause_resume_once",
            "event_sequence_contiguous",
        )
    }
    metrics = {
        "chapter_count": 3,
        "section_count": 3,
        "transaction_count": 3,
        "attempt_count": 3,
        "planner_calls": 0,
        "section_provider_calls": 3,
        "provider_calls_total": 4,
        "full_writer_retries": 0,
        "repair_total": 0,
        "duplicate_section_count": 0,
        "duplicate_transaction_count": 0,
        "rejected_prose_published_count": 0,
        "canonical_revision_final": 3,
        "production_event_count": 9,
    }
    return {
        "schema_version": "provider-product-smoke-evidence-v1",
        "outcome": "passed",
        "provider_runtime": {
            **acceptance._safe_provider(FakeProviderConfig()),
            "key_fingerprint": "1234abcd",
        },
        "outline": {
            "provider_calls": 1,
            "repair_performed": False,
            "revision": 1,
            "final_progress_revision": 4,
            "chapter_count": 3,
        },
        "job": {
            "job_id": "job_1",
            "status": "completed",
            "revision": 4,
            "prompt_tokens_total": 30,
            "completion_tokens_total": 60,
            "latency_total_ms": 120,
            "repair_total": 0,
            "retry_count": 0,
            "active_transaction_id_present": False,
        },
        "style_transition": {
            "initial_style_profile_id": "preset_literary",
            "custom_style_profile_id": "custom_cold",
            "custom_style_revision": 1,
            "custom_style_prompt_hash": "A" * 64,
            "applies_from_chapter_ordinal": 3,
            "sample_excluded_from_prompt": True,
        },
        "control": {"pause_count": 1, "resume_count": 1, "safe_boundary": True},
        "metrics": metrics,
        "transactions": [
            {
                "transaction_id": f"tx_{index}",
                "provider": "custom",
                "model": "glm-5.2",
                "source": "provider_file",
                "config_fingerprint": "a1b2c3d4e5f60708",
                "structured_output_repair_count": 0,
                "planner_calls": 0,
                "writer_calls": 1,
                "provider_calls": 1,
                "full_writer_retry_count": 0,
                "committed": True,
            }
            for index in range(1, 4)
        ],
        "chapters": [
            {
                "chapter_id": f"chapter_{index}",
                "ordinal": index,
                "section_count": 1,
                "char_count": 900,
                "style_profile_id": (
                    "preset_literary" if index < 3 else "custom_cold"
                ),
                "style_revision": 1,
                "style_prompt_hash": "B" * 64,
                "canonical_revision_start": index - 1,
                "canonical_revision_end": index,
                "repair_total": 0,
                "transaction_ids": [f"tx_{index}"],
            }
            for index in range(1, 4)
        ],
        "gates": gates,
        "secret_scan": {
            "exact_key_hits": 0,
            "exact_base_url_hits": 0,
            "generic_secret_hits": 0,
        },
        "artifacts": {
            "manuscript_sha256": manuscript_sha256,
            "manuscript_bytes": manuscript_bytes,
        },
    }


def test_frozen_cycle_constants_and_cli_require_explicit_roots() -> None:
    assert acceptance.CYCLE_ID == "p6-provider-init-final-20260730"
    assert acceptance.BASELINE_HEAD == "834120c860fe05f796ccfa3f65c0b981e777df9a"
    assert acceptance.EXPECTED_BRANCH == "codex/final-long-novel-custom-style-20260730"
    assert acceptance.PHASES == (
        "offline",
        "probe",
        "g1",
        "g2",
        "product",
        "final",
    )
    with pytest.raises(SystemExit):
        acceptance.build_parser().parse_args(["--phase", "offline"])


def test_offline_commands_and_internal_checks_are_frozen_in_serial_order(
    tmp_path: Path,
) -> None:
    commands = acceptance._offline_external_commands(tmp_path)
    assert [name for name, _ in commands] == list(acceptance.OFFLINE_CHECK_NAMES[:9])
    assert commands[0][1][-3:] == ["-q", "-W", "error"]
    assert commands[1][1][-3:] == ["backend", "scripts", "core"]
    assert commands[2][1][-4:] == ["-q", "backend", "scripts", "core"]
    assert commands[6][1] == ["git", "diff", "--check"]
    long_command = commands[8][1]
    assert long_command[long_command.index("--chapters") + 1] == "30"
    assert long_command[long_command.index("--sections-per-chapter") + 1] == "2"
    assert acceptance.OFFLINE_CHECK_NAMES[-3:] == (
        "exact_secret_scan",
        "generic_secret_scan",
        "untracked_sensitive_files",
    )


def test_phase_order_is_strict_and_no_phase_can_be_reused() -> None:
    state = _state()
    acceptance._require_phase(state, "offline")
    with pytest.raises(acceptance.AcceptanceError, match="blocked by"):
        acceptance._require_phase(state, "probe")
    state["phases"]["offline"] = {"status": "passed"}
    acceptance._require_phase(state, "probe")
    state["phases"]["probe"] = {"status": "passed"}
    with pytest.raises(acceptance.AcceptanceError, match="blocked by"):
        acceptance._require_phase(state, "g2")
    state["phases"]["g1"] = {"status": "passed"}
    acceptance._require_phase(state, "g2")
    state["phases"]["g2"] = {"status": "failed"}
    with pytest.raises(acceptance.AcceptanceError, match="cannot be reused"):
        acceptance._require_phase(state, "g2")
    with pytest.raises(acceptance.AcceptanceError, match="blocked by"):
        acceptance._require_phase(state, "product")


def test_g1_g2_reuse_strict_assessment_and_add_transaction_anomaly_gate() -> None:
    expected_runtime = acceptance._safe_provider(FakeProviderConfig())
    g1 = acceptance.assess_matrix(
        "g1",
        _matrix(count=1, first_pass=1),
        expected_runtime=expected_runtime,
    )
    assert g1["status"] == "passed"
    assert g1["checks"]["transaction_anomalies_zero"] is True
    assert g1["checks"]["runtime_receipts_match_expected"] is True

    g2 = acceptance.assess_matrix(
        "g2",
        _matrix(count=15, first_pass=9, repairs=6),
        expected_runtime=expected_runtime,
    )
    assert g2["status"] == "passed"
    assert g2["metrics"]["length_in_range"] == 15
    assert g2["metrics"]["transaction_anomalies"] == 0
    assert g2["metrics"]["runtime_receipts_checked"] == 15

    anomaly = _matrix(count=1, first_pass=1)
    anomaly["combinations"][0]["integrity"] = ["duplicate_transaction"]
    rejected = acceptance.assess_matrix(
        "g1",
        anomaly,
        expected_runtime=expected_runtime,
    )
    assert rejected["status"] == "failed"
    assert rejected["checks"]["transaction_anomalies_zero"] is False
    assert rejected["metrics"]["transaction_anomalies"] == 1


def test_matrix_failure_evidence_drops_raw_error_material() -> None:
    matrix = _topology_matrix("g1")
    matrix["combinations"][0]["failures"] = [
        {
            **_provider_failure_row(),
            "message": "raw secret and upstream response must be omitted",
            "raw_response": "secret payload",
        }
    ]

    sanitized = acceptance._sanitize_matrix(matrix)
    failure = sanitized["combinations"][0]["failures"][0]

    assert "message" not in failure
    assert "raw_response" not in failure
    assert failure == {
        "attempt": 1,
        "planner_calls": 0,
        "provider_call_count": 2,
        "provider_call_count_known": True,
        "provider_code": "PROVIDER_OUTPUT_INVALID",
        "provider_failure": True,
        "provider_http_category": "output_invalid",
        "provider_stage": "writer_json_repair",
        "runtime_provider": "custom",
        "runtime_provider_config_fingerprint": "a1b2c3d4e5f60708",
        "runtime_provider_model": "glm-5.2",
        "runtime_provider_source": "provider_file",
        "section": 1,
        "structured_output_repair_count": 1,
        "transaction_phase": "failed",
        "writer_calls": 1,
    }
    acceptance._metadata_only_json(sanitized)


def test_writer_shape_receipt_rejects_noninteger_or_partial_diagnostics() -> None:
    matrix = _topology_matrix("g1")
    section = matrix["combinations"][0]["sections"][0]
    section["writer_cell_nonspace_lengths"] = ["raw prose must not pass"]

    with pytest.raises(acceptance.AcceptanceError, match="is malformed"):
        acceptance._sanitize_matrix(matrix)

    section["writer_cell_nonspace_lengths"] = [1] * 51
    with pytest.raises(acceptance.AcceptanceError, match="invalid cardinality"):
        acceptance._sanitize_matrix(matrix)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_call_count", 3),
        ("provider_call_count_known", False),
        ("provider_http_category", "auth"),
        ("provider_stage", "unknown"),
        ("runtime_provider_source", ""),
    ],
)
def test_matrix_failure_contract_rejects_invalid_counts_or_metadata(
    field: str,
    value: object,
) -> None:
    row = _provider_failure_row()
    row[field] = value

    with pytest.raises(acceptance.AcceptanceError):
        acceptance._safe_matrix_failure(
            row,
            expected_runtime=acceptance._safe_provider(FakeProviderConfig()),
        )


def test_matrix_failure_contract_rejects_runtime_drift_and_fails_assessment() -> None:
    expected_runtime = acceptance._safe_provider(FakeProviderConfig())
    drifted = _provider_failure_row()
    drifted["runtime_provider_config_fingerprint"] = "ffffffffffffffff"
    with pytest.raises(acceptance.AcceptanceError):
        acceptance._safe_matrix_failure(
            drifted,
            expected_runtime=expected_runtime,
        )

    matrix = _topology_matrix("g1")
    matrix["combinations"][0]["failures"] = [_provider_failure_row()]
    assessment = acceptance.assess_matrix(
        "g1",
        matrix,
        expected_runtime=expected_runtime,
    )
    assert assessment["status"] == "failed"
    assert assessment["checks"]["failure_rows_zero"] is False
    assert (
        assessment["checks"]["provider_error_summary_matches_failure_rows"]
        is False
    )


def test_runtime_receipts_are_persisted_and_missing_or_drifted_values_fail() -> None:
    expected_runtime = acceptance._safe_provider(FakeProviderConfig())
    matrix = _topology_matrix("g1")
    accepted = acceptance.assess_matrix(
        "g1",
        matrix,
        expected_runtime=expected_runtime,
    )
    assert accepted["status"] == "passed"
    assert accepted["metrics"]["runtime_receipt_mismatches"] == 0
    sanitized_section = acceptance._sanitize_matrix(matrix)["combinations"][0][
        "sections"
    ][0]
    assert sanitized_section["initial_narrative_length"] == 900
    assert "initial_length_report" not in sanitized_section
    assert sanitized_section["writer_block_nonspace_lengths"] == [100] * 10
    assert sanitized_section["writer_cell_nonspace_lengths"] == [19] * 51 + [31]
    assert sanitized_section["writer_cell_sentence_boundary_counts"] == [1] * 52
    assert sanitized_section["repair_patch_nonspace_lengths"] == [300, 122]
    assert sanitized_section["repair_patch_total_nonspace_chars"] == 422
    assert sanitized_section["repair_patch_max_nonspace_chars"] == 300
    assert {
        key: sanitized_section[key]
        for key in (
            "runtime_provider",
            "runtime_provider_model",
            "runtime_provider_source",
            "runtime_provider_config_fingerprint",
        )
    } == {
        "runtime_provider": "custom",
        "runtime_provider_model": "glm-5.2",
        "runtime_provider_source": "provider_file",
        "runtime_provider_config_fingerprint": "a1b2c3d4e5f60708",
    }

    drifted = _topology_matrix("g1")
    drifted["combinations"][0]["sections"][0][
        "runtime_provider_config_fingerprint"
    ] = "ffffffffffffffff"
    drifted_assessment = acceptance.assess_matrix(
        "g1",
        drifted,
        expected_runtime=expected_runtime,
    )
    assert drifted_assessment["status"] == "failed"
    assert drifted_assessment["checks"]["runtime_receipts_match_expected"] is False
    assert drifted_assessment["metrics"]["runtime_receipt_mismatches"] == 1

    missing = _topology_matrix("g1")
    del missing["combinations"][0]["sections"][0]["runtime_provider_source"]
    missing_assessment = acceptance.assess_matrix(
        "g1",
        missing,
        expected_runtime=expected_runtime,
    )
    assert missing_assessment["status"] == "failed"
    assert missing_assessment["checks"]["runtime_receipts_match_expected"] is False
    assert missing_assessment["metrics"]["runtime_receipt_missing_fields"] == 1


def test_exact_redaction_and_scans_never_reflect_secret_values(tmp_path: Path) -> None:
    key = "live-provider-key-material-123456789"
    endpoint = "https://private-provider.invalid/v1"
    redactor = acceptance.ExactRedactor(api_key=key, base_url=endpoint)
    redacted, counts = redactor.redact(
        f"Authorization={key}; endpoint={endpoint}"
    )
    assert key not in redacted
    assert endpoint not in redacted
    assert counts == {"provider_key": 1, "provider_base_url": 1}

    leaked = tmp_path / "leaked.txt"
    leaked.write_text(f"{key}\n{endpoint}\n", encoding="utf-8")
    exact = acceptance.scan_exact_secrets(
        [leaked],
        exact_values=redactor.exact_values,
        display_root=tmp_path,
    )
    assert exact["status"] == "failed"
    serialized = json.dumps(exact)
    assert key not in serialized
    assert endpoint not in serialized

    generic_path = tmp_path / "generic.txt"
    generic_path.write_text(
        "sk-" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + "1234567890",
        encoding="utf-8",
    )
    generic = acceptance.scan_generic_secrets(
        [generic_path], display_root=tmp_path
    )
    assert generic["status"] == "failed"
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in json.dumps(generic)


def test_cycle_initialization_is_exclusive_and_protection_drift_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_root, previous, provider_file = _user_and_previous(tmp_path)
    evidence_root = tmp_path / "evidence"
    monkeypatch.setattr(acceptance, "_repo_identity", lambda **kwargs: _identity())
    state = acceptance._initialize_cycle(
        evidence_root=evidence_root,
        user_root=user_root,
        previous_evidence_root=previous,
        provider_file=provider_file,
        config=FakeProviderConfig(),
    )
    assert evidence_root.is_dir()
    assert state["protected"]["files"]["coding.txt"]["sha256"]
    with pytest.raises(acceptance.AcceptanceError, match="already exists"):
        acceptance._initialize_cycle(
            evidence_root=evidence_root,
            user_root=user_root,
            previous_evidence_root=previous,
            provider_file=provider_file,
            config=FakeProviderConfig(),
        )

    (user_root / ".env").write_text("DRIFTED=1\n", encoding="utf-8")
    with pytest.raises(acceptance.AcceptanceError, match="drifted"):
        acceptance._verify_protected(
            state["protected"],
            user_root=user_root,
            previous_evidence_root=previous,
        )


def test_offline_phase_uses_mock_subprocess_serially_and_publishes_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_root, previous, _ = _user_and_previous(tmp_path)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    state = _state()
    state["protected"] = acceptance._protected_snapshot(user_root, previous)
    commands_seen: list[tuple[str, ...]] = []

    monkeypatch.setattr(
        acceptance,
        "_source_tree_hash",
        lambda **kwargs: "SOURCE",
    )
    monkeypatch.setattr(
        acceptance,
        "_repo_identity",
        lambda **kwargs: _identity(),
    )
    monkeypatch.setattr(acceptance, "_source_paths", lambda **kwargs: [])
    monkeypatch.setattr(
        acceptance,
        "_untracked_sensitive_files",
        lambda **kwargs: {"status": "passed", "finding_count": 0, "findings": []},
    )

    def fake_runner(command, cwd: Path) -> acceptance.CommandExecution:
        del cwd
        command_tuple = tuple(str(item) for item in command)
        commands_seen.append(command_tuple)
        stdout = "offline check passed"
        if any(part.endswith("smoke_author_mode_recorded.py") for part in command_tuple):
            stdout = json.dumps(
                {"steps": {"authority": True}, "metrics": {"provider_calls": 0}}
            )
        if any(part.endswith("smoke_long_novel_recorded.py") for part in command_tuple):
            output = Path(command_tuple[command_tuple.index("--output-dir") + 1])
            output.mkdir(parents=True)
            (output / "summary.json").write_text(
                json.dumps({"gates": {"thirty_by_two": True}, "metrics": {}}),
                encoding="utf-8",
            )
            (output / "evidence.json").write_text(
                json.dumps({"gates": {"thirty_by_two": True}, "provider_calls": 0}),
                encoding="utf-8",
            )
            stdout = json.dumps({"ok": True, "output_dir": str(output.resolve())})
        return acceptance.CommandExecution(
            command=command_tuple,
            returncode=0,
            stdout=stdout,
            stderr="",
            duration_seconds=0.01,
        )

    receipt = acceptance._run_offline_phase(
        evidence_root=evidence_root,
        state=state,
        redactor=acceptance.ExactRedactor(
            api_key=FakeProviderConfig.api_key,
            base_url=FakeProviderConfig.base_url,
        ),
        user_root=user_root,
        previous_evidence_root=previous,
        runner=fake_runner,
    )
    assert receipt["status"] == "passed"
    assert [item["name"] for item in receipt["checks"]] == list(
        acceptance.OFFLINE_CHECK_NAMES
    )
    assert len(commands_seen) == 9
    assert (evidence_root / "offline" / "receipt.json").is_file()
    assert (evidence_root / "recorded-author-state").exists() is False
    assert state["authorized_source_tree_sha256"] == "SOURCE"
    recorded_checks = {
        item["name"]: item
        for item in receipt["checks"]
        if item["name"] in {"recorded_author_smoke", "recorded_long_30x2_smoke"}
    }
    assert set(recorded_checks) == {
        "recorded_author_smoke",
        "recorded_long_30x2_smoke",
    }
    assert all(item["raw_output_persisted"] is False for item in recorded_checks.values())
    for name in recorded_checks:
        log = (evidence_root / "offline" / "logs" / f"{name}.log").read_text(
            encoding="utf-8"
        )
        assert str(tmp_path) not in log
        assert "final-long-offline-" not in log


def test_probe_command_is_strict_and_phase_artifacts_are_not_reusable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_root, previous, provider_file = _user_and_previous(tmp_path)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    state = _state()
    state["protected"] = acceptance._protected_snapshot(user_root, previous)
    state["phases"]["offline"] = {"status": "passed"}
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(acceptance, "_repo_identity", lambda **kwargs: _identity())
    monkeypatch.setattr(
        acceptance,
        "_source_tree_hash",
        lambda **kwargs: "SOURCE",
    )
    monkeypatch.setattr(acceptance, "_source_paths", lambda **kwargs: [])

    def fake_runner(command, cwd: Path) -> acceptance.CommandExecution:
        del cwd
        seen.append(tuple(command))
        return acceptance.CommandExecution(
            command=tuple(command),
            returncode=0,
            stdout=(
                '[RUNTIME] {"provider":"custom","model":"glm-5.2",'
                '"source":"provider_file","thinking_mode":"disabled",'
                '"retries":0,"credential_present":true,'
                '"config_fingerprint":"a1b2c3d4e5f60708"}\n'
                "[OK] quota healthy. content_len=2 tokens=3"
            ),
            stderr="",
            duration_seconds=0.01,
        )

    receipt = acceptance._run_probe_phase(
        evidence_root=evidence_root,
        state=state,
        redactor=acceptance.ExactRedactor(
            api_key=FakeProviderConfig.api_key,
            base_url=FakeProviderConfig.base_url,
        ),
        config=FakeProviderConfig(),
        provider_file=provider_file,
        user_root=user_root,
        previous_evidence_root=previous,
        runner=fake_runner,
    )
    assert receipt["status"] == "passed"
    command = seen[0]
    assert command[command.index("--provider") + 1] == "custom"
    assert command[command.index("--expect-model") + 1] == "glm-5.2"
    assert command[command.index("--expect-thinking-mode") + 1] == "disabled"
    assert command[command.index("--expect-max-retries") + 1] == "0"
    persisted = json.dumps(receipt)
    assert str(provider_file.resolve()) not in persisted
    assert "[PROTECTED_PROVIDER_FILE]" in persisted
    with pytest.raises(acceptance.AcceptanceError, match="cannot be reused"):
        acceptance._run_probe_phase(
            evidence_root=evidence_root,
            state=state,
            redactor=acceptance.ExactRedactor(
                api_key=FakeProviderConfig.api_key,
                base_url=FakeProviderConfig.base_url,
            ),
            config=FakeProviderConfig(),
            provider_file=provider_file,
            user_root=user_root,
            previous_evidence_root=previous,
            runner=fake_runner,
        )


def test_evidence_json_rejects_secrets_prompts_raw_response_and_prose() -> None:
    acceptance._metadata_only_json(
        {
            "prompt_tokens": 12,
            "manuscript_sha256": "0" * 64,
            "provider": "custom",
        }
    )
    for field in (
        "api_key",
        "authorization",
        "base_url",
        "content",
        "headers",
        "narrative_text",
        "prompt",
        "raw_response",
        "response",
        "response_body",
        "text",
        "url",
    ):
        with pytest.raises(acceptance.AcceptanceError, match="forbidden field"):
            acceptance._metadata_only_json({field: "must not persist"})
    with pytest.raises(acceptance.AcceptanceError, match="prose or raw payload"):
        acceptance._metadata_only_json(
            {"alternate_unknown_field": "The room fell silent before dawn."}
        )
    with pytest.raises(acceptance.AcceptanceError, match="prose or raw payload"):
        acceptance._metadata_only_json({"alternate_unknown_field": "夜色落进空屋。"})


def test_provider_binding_rejects_substitution_and_runtime_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_root, _, provider_file = _user_and_previous(tmp_path)
    substituted = tmp_path / "other-coding.txt"
    substituted.write_text("not inspected by binding check\n", encoding="utf-8")
    with pytest.raises(acceptance.AcceptanceError, match="user-root coding.txt"):
        acceptance._assert_provider_binding(
            provider_file=substituted,
            user_root=user_root,
        )
    provider_loaded = False

    def forbidden_load(path: Path):
        nonlocal provider_loaded
        provider_loaded = True
        raise AssertionError(f"substituted file was read: {path.name}")

    monkeypatch.setattr(acceptance, "_load_provider", forbidden_load)
    args = SimpleNamespace(
        phase="probe",
        provider_file=substituted,
        user_root=user_root,
        previous_evidence_root=tmp_path / "previous",
        evidence_root=tmp_path / "evidence",
    )
    with pytest.raises(acceptance.AcceptanceError, match="user-root coding.txt"):
        acceptance.run_phase(args)
    assert provider_loaded is False

    class ChangedConfig(FakeProviderConfig):
        def diagnostics(self) -> dict:
            value = super().diagnostics()
            value["config_fingerprint"] = "DIFFERENT"
            return value

    class DifferentProcessSaltConfig(FakeProviderConfig):
        def diagnostics(self) -> dict:
            value = super().diagnostics()
            value["key_fingerprint"] = "different-process-salt"
            return value

    frozen_runtime = acceptance._safe_provider(FakeProviderConfig())
    assert "key_fingerprint" not in frozen_runtime
    acceptance._assert_provider_binding(
        provider_file=provider_file,
        user_root=user_root,
        config=DifferentProcessSaltConfig(),
        state={"provider_runtime": frozen_runtime},
    )

    with pytest.raises(acceptance.AcceptanceError, match="runtime changed"):
        acceptance._assert_provider_binding(
            provider_file=provider_file,
            user_root=user_root,
            config=ChangedConfig(),
            state={"provider_runtime": frozen_runtime},
        )

    safe_command = acceptance._safe_command(
        [
            "runner",
            "--provider-file",
            str(provider_file),
            "--user-root",
            str(user_root),
            "--previous-evidence-root",
            str(tmp_path / "previous"),
            "--data-dir",
            str(tmp_path / "recorded-data"),
            f"--output-dir={tmp_path / 'provider-output'}",
            "--evidence-root",
            str(tmp_path / "evidence"),
        ]
    )
    serialized = json.dumps(safe_command)
    assert str(provider_file) not in serialized
    assert str(user_root) not in serialized
    assert str(tmp_path / "previous") not in serialized
    assert str(tmp_path / "recorded-data") not in serialized
    assert str(tmp_path / "provider-output") not in serialized
    assert str(tmp_path / "evidence") not in serialized


def test_phase_claim_and_abandoned_staging_block_duplicate_execution(
    tmp_path: Path,
) -> None:
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    first = acceptance._stage_dir(evidence_root, "g1")
    assert first.is_dir()
    assert (evidence_root / ".g1.claim").is_file()
    with pytest.raises(acceptance.AcceptanceError, match="cannot be reused"):
        acceptance._stage_dir(evidence_root, "g1")

    other_root = tmp_path / "other-evidence"
    other_root.mkdir()
    (other_root / ".g2.staging-interrupted").mkdir()
    with pytest.raises(acceptance.AcceptanceError, match="cannot be reused"):
        acceptance._stage_dir(other_root, "g2")


def test_completed_phase_tree_drift_fails_closed(tmp_path: Path) -> None:
    evidence_root = tmp_path / "evidence"
    offline = evidence_root / "offline"
    offline.mkdir(parents=True)
    (evidence_root / ".offline.claim").write_text("claimed\n", encoding="utf-8")
    receipt = offline / "receipt.json"
    receipt.write_text('{"status":"passed"}\n', encoding="utf-8")
    state = _state()
    state["phases"]["offline"] = {
        "status": "passed",
        "artifact_tree": acceptance._tree_hash(offline),
    }
    acceptance._verify_completed_artifacts(state, evidence_root=evidence_root)
    receipt.write_text('{"status":"tampered"}\n', encoding="utf-8")
    with pytest.raises(acceptance.AcceptanceError, match="artifacts drifted"):
        acceptance._verify_completed_artifacts(state, evidence_root=evidence_root)


def test_transaction_ids_and_exact_matrix_topology_are_recomputed() -> None:
    g2 = _topology_matrix("g2")
    assert acceptance._matrix_identity_passes("g2", g2) is True

    for key, value in (
        ("seed", 1),
        ("checkpoint_every", 2),
        ("runtime_rebuild_every", 3),
    ):
        wrong_identity = _topology_matrix("g2")
        wrong_identity["config"][key] = value
        assert acceptance._matrix_identity_passes("g2", wrong_identity) is False

    wrong_shape = _topology_matrix("g2")
    wrong_shape["combinations"] = [
        {
            **wrong_shape["combinations"][0],
            "sections": [
                section
                for combination in wrong_shape["combinations"]
                for section in combination["sections"]
            ],
        }
    ]
    assert acceptance._matrix_identity_passes("g2", wrong_shape) is False

    duplicate = _topology_matrix("g2")
    duplicate["combinations"][1]["sections"][0]["transaction_id"] = (
        duplicate["combinations"][0]["sections"][0]["transaction_id"]
    )
    assessment = acceptance.assess_matrix("g2", duplicate)
    assert assessment["status"] == "failed"
    assert assessment["metrics"]["direct_identifier_anomalies"] == 1

    null_ids = _topology_matrix("g2")
    null_ids["combinations"][0]["sections"][0]["transaction_id"] = None
    null_ids["combinations"][0]["sections"][1]["section_id"] = None
    assessment = acceptance.assess_matrix("g2", null_ids)
    assert assessment["status"] == "failed"
    assert assessment["metrics"]["direct_identifier_anomalies"] == 2

    null_run = _topology_matrix("g2")
    null_run["combinations"][0]["run_id"] = None
    assert acceptance._matrix_identity_passes("g2", null_run) is False


def test_g2_rejects_transaction_reuse_from_g1_with_mock_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_root, previous, provider_file = _user_and_previous(tmp_path)
    evidence_root = tmp_path / "evidence"
    g1_root = evidence_root / "g1"
    g1_root.mkdir(parents=True)
    g1 = _topology_matrix("g1")
    (g1_root / "matrix-evidence.json").write_text(
        json.dumps(acceptance._sanitize_matrix(g1)), encoding="utf-8"
    )
    state = _state()
    state["protected"] = acceptance._protected_snapshot(user_root, previous)
    for phase in ("offline", "probe", "g1"):
        state["phases"][phase] = {"status": "passed"}
    monkeypatch.setattr(acceptance, "_repo_identity", lambda **kwargs: _identity())
    monkeypatch.setattr(acceptance, "_source_tree_hash", lambda **kwargs: "SOURCE")
    monkeypatch.setattr(acceptance, "_source_paths", lambda **kwargs: [])

    g2 = _topology_matrix("g2")
    g2["combinations"][0]["sections"][0]["transaction_id"] = (
        g1["combinations"][0]["sections"][0]["transaction_id"]
    )
    g2["combinations"][0]["sections"][0]["section_id"] = (
        g1["combinations"][0]["sections"][0]["section_id"]
    )
    g2["combinations"][0]["run_id"] = g1["combinations"][0]["run_id"]
    seen: list[tuple[str, ...]] = []

    def fake_runner(command, cwd: Path) -> acceptance.CommandExecution:
        del cwd
        command_tuple = tuple(command)
        seen.append(command_tuple)
        output = Path(command_tuple[command_tuple.index("--output-dir") + 1])
        output.mkdir(parents=True)
        (output / "stage1-matrix.json").write_text(
            json.dumps(g2), encoding="utf-8"
        )
        return acceptance.CommandExecution(
            command=command_tuple,
            returncode=0,
            stdout="matrix complete",
            stderr="",
            duration_seconds=0.01,
        )

    receipt = acceptance._run_matrix_phase(
        phase="g2",
        evidence_root=evidence_root,
        state=state,
        redactor=acceptance.ExactRedactor(
            api_key=FakeProviderConfig.api_key,
            base_url=FakeProviderConfig.base_url,
        ),
        config=FakeProviderConfig(),
        provider_file=provider_file,
        user_root=user_root,
        previous_evidence_root=previous,
        runner=fake_runner,
    )
    assert receipt["status"] == "failed"
    assert receipt["assessment"]["checks"]["run_reuse_with_g1_zero"] is False
    assert receipt["assessment"]["checks"]["transaction_reuse_with_g1_zero"] is False
    assert receipt["assessment"]["checks"]["section_reuse_with_g1_zero"] is False
    assert receipt["assessment"]["metrics"]["runs_reused_from_g1"] == 1
    assert receipt["assessment"]["metrics"]["transactions_reused_from_g1"] == 1
    assert receipt["assessment"]["metrics"]["sections_reused_from_g1"] == 1
    assert "--resume" not in seen[0]
    assert seen[0][seen[0].index("--model") + 1] == "glm-5.2"
    assert seen[0][seen[0].index("--id-namespace") + 1] == "g2"


def test_secret_in_subprocess_output_aborts_and_removes_probe_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_root, previous, provider_file = _user_and_previous(tmp_path)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    state = _state()
    state["protected"] = acceptance._protected_snapshot(user_root, previous)
    state["phases"]["offline"] = {"status": "passed"}
    monkeypatch.setattr(acceptance, "_repo_identity", lambda **kwargs: _identity())
    monkeypatch.setattr(acceptance, "_source_tree_hash", lambda **kwargs: "SOURCE")
    monkeypatch.setattr(acceptance, "_source_paths", lambda **kwargs: [])

    def leaking_runner(command, cwd: Path) -> acceptance.CommandExecution:
        del cwd
        return acceptance.CommandExecution(
            command=tuple(command),
            returncode=0,
            stdout=f"[OK] quota healthy. leaked={FakeProviderConfig.api_key}",
            stderr="",
            duration_seconds=0.01,
        )

    with pytest.raises(acceptance.SecretLeakError):
        acceptance._run_probe_phase(
            evidence_root=evidence_root,
            state=state,
            redactor=acceptance.ExactRedactor(
                api_key=FakeProviderConfig.api_key,
                base_url=FakeProviderConfig.base_url,
            ),
            config=FakeProviderConfig(),
            provider_file=provider_file,
            user_root=user_root,
            previous_evidence_root=previous,
            runner=leaking_runner,
        )
    assert not (evidence_root / "probe").exists()
    assert not list(evidence_root.glob(".probe.staging-*"))
    assert state["phases"]["probe"]["reason"] == "secret_scan_failed"
    assert all(
        FakeProviderConfig.api_key.encode("utf-8") not in path.read_bytes()
        for path in evidence_root.rglob("*")
        if path.is_file()
    )


def test_product_artifacts_require_exact_files_and_matching_hashes(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    manuscript = artifacts / "manuscript.md"
    manuscript.write_text("# Book\n\nCommitted chapter.\n", encoding="utf-8")
    evidence = _product_evidence(
        acceptance._sha256_file(manuscript), manuscript.stat().st_size
    )
    evidence_path = artifacts / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    summary = {
        "schema_version": "provider-product-smoke-summary-v1",
        "ok": True,
        "provider": evidence["provider_runtime"],
        "metrics": evidence["metrics"],
        "gates": evidence["gates"],
        "artifact_hashes": {
            "manuscript.md": acceptance._sha256_file(manuscript),
            "evidence.json": acceptance._sha256_file(evidence_path),
        },
    }
    summary_path = artifacts / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    hashes = {
        path.name: {
            "sha256": acceptance._sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in (manuscript, evidence_path, summary_path)
    }
    (artifacts / "artifact-sha256.json").write_text(
        json.dumps({"schema_version": "artifact-sha256-v1", "artifacts": hashes}),
        encoding="utf-8",
    )
    assert acceptance._validate_product_artifacts(artifacts, evidence) is True

    (artifacts / "raw-response.txt").write_text("must never publish", encoding="utf-8")
    with pytest.raises(acceptance.AcceptanceError, match="unexpected artifact"):
        acceptance._validate_product_artifacts(artifacts, evidence)

    unsafe_evidence = dict(evidence)
    unsafe_evidence["novel_output"] = "narrative prose under an alternate key"
    with pytest.raises(acceptance.AcceptanceError, match="top-level schema"):
        acceptance._validate_product_evidence(unsafe_evidence)

    miscounted_evidence = json.loads(json.dumps(evidence))
    miscounted_evidence["transactions"][0]["provider_calls"] = 2
    assert acceptance._validate_product_evidence(miscounted_evidence) is False


def test_ignored_nested_sensitive_file_is_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_git(*args: str, **kwargs) -> str:
        del kwargs
        return "nested/.env\0" if "--ignored" in args else ""

    monkeypatch.setattr(acceptance, "_git", fake_git)
    result = acceptance._untracked_sensitive_files(user_root=tmp_path)
    assert result["status"] == "failed"
    assert "nested/.env" in result["findings"]


def test_final_report_records_final_pass_and_all_required_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_root, previous, _ = _user_and_previous(tmp_path)
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    state = _state()
    state["protected"] = acceptance._protected_snapshot(user_root, previous)
    for phase in acceptance.PHASES[:-1]:
        phase_root = evidence_root / phase
        phase_root.mkdir()
        (phase_root / "receipt.json").write_text(
            '{"status":"passed"}\n', encoding="utf-8"
        )
        state["phases"][phase] = {"status": "passed"}
    product_artifacts = evidence_root / "product" / "artifacts"
    product_artifacts.mkdir()
    (product_artifacts / "manuscript.md").write_text(
        "# Committed manuscript\n", encoding="utf-8"
    )
    monkeypatch.setattr(acceptance, "_repo_identity", lambda **kwargs: _identity())
    monkeypatch.setattr(acceptance, "_source_tree_hash", lambda **kwargs: "SOURCE")
    monkeypatch.setattr(acceptance, "_source_paths", lambda **kwargs: [])

    report = acceptance._run_final_phase(
        evidence_root=evidence_root,
        state=state,
        redactor=acceptance.ExactRedactor(
            api_key=FakeProviderConfig.api_key,
            base_url=FakeProviderConfig.base_url,
        ),
        user_root=user_root,
        previous_evidence_root=previous,
    )
    assert report["verdict"] == "FINAL_LONG_NOVEL_PASS"
    assert report["phases"]["final"]["status"] == "passed"
    assert state["phases"]["final"]["status"] == "passed"
    assert all((evidence_root / name).is_file() for name in acceptance.FINAL_FILENAMES)


def test_legacy_runner_is_only_a_compatibility_entry() -> None:
    legacy = (
        Path(acceptance.__file__).with_name("run_final_acceptance.py")
        .read_text(encoding="utf-8")
    )
    assert "codex/novel-auto-final-goal-20260728" not in legacy
    assert "historical seed failed" not in legacy
    assert "run_final_long_novel_acceptance" in legacy
