from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.validate_styles import _configure_provider


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "p6_seed_20260727_writer_invalid_json.json"
)


def _provider_file(tmp_path: Path, *, model: str) -> Path:
    path = tmp_path / "coding.txt"
    path.write_text(
        f"KEY=test-only-key\nURL=https://example.invalid/v1\nMODEL={model}\n",
        encoding="utf-8",
    )
    return path


def test_frozen_glm_invalid_json_failure_selects_non_reasoning_structured_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    evidence = json.loads(FIXTURE.read_text(encoding="utf-8"))
    monkeypatch.delenv("LLM_THINKING_MODE", raising=False)

    configured = _configure_provider(
        _provider_file(tmp_path, model=evidence["model"])
    )

    expected = evidence["expected_configuration"]["structured_output_thinking_mode"]
    assert configured["thinking_mode"] == expected
    assert os.environ["LLM_THINKING_MODE"] == expected


def test_explicit_thinking_mode_is_never_overwritten(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_THINKING_MODE", "operator-choice")

    configured = _configure_provider(
        _provider_file(tmp_path, model="glm-5.2")
    )

    assert configured["thinking_mode"] == "operator-choice"
    assert os.environ["LLM_THINKING_MODE"] == "operator-choice"
