from __future__ import annotations

import json
import os
from pathlib import Path

from nf_core.provider_runtime import (
    ProviderRuntimeConfig,
    reset_stage_provider_config,
    set_stage_provider_config,
)
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
    guard = set_stage_provider_config(
        ProviderRuntimeConfig.from_explicit(
            provider="custom",
            api_key="guard",
            base_url="https://guard.invalid/v1",
            model="guard-model",
        )
    )
    try:
        configured = _configure_provider(
            _provider_file(tmp_path, model=evidence["model"])
        )
    finally:
        reset_stage_provider_config(guard)

    expected = evidence["expected_configuration"]["structured_output_thinking_mode"]
    assert isinstance(configured, ProviderRuntimeConfig)
    assert configured.thinking_mode == expected
    assert "LLM_THINKING_MODE" not in os.environ


def test_explicit_thinking_mode_is_never_overwritten(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_THINKING_MODE", "operator-choice")
    provider_file = _provider_file(tmp_path, model="glm-5.2")
    provider_file.write_text(
        provider_file.read_text(encoding="utf-8")
        + "THINKING_MODE=file-choice\n",
        encoding="utf-8",
    )
    guard = set_stage_provider_config(
        ProviderRuntimeConfig.from_explicit(
            provider="custom",
            api_key="guard",
            base_url="https://guard.invalid/v1",
            model="guard-model",
        )
    )
    try:
        configured = _configure_provider(provider_file)
    finally:
        reset_stage_provider_config(guard)

    assert configured.thinking_mode == "file-choice"
    assert os.environ["LLM_THINKING_MODE"] == "operator-choice"
