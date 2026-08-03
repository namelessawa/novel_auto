from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from scripts import smoke_long_novel_provider as smoke


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fake_provider(path: Path) -> bytes:
    payload = (
        "LLM_PROVIDER=custom\n"
        "CUSTOM_API_KEY=test-only-provider-credential-0123456789\n"
        "CUSTOM_BASE_URL=https://provider.invalid/openai/v1\n"
        "CUSTOM_MODEL=glm-5.2\n"
        "LLM_THINKING_MODE=disabled\n"
        "LLM_MAX_RETRIES=0\n"
    ).encode("utf-8")
    path.write_bytes(payload)
    return payload


def _mock_result(config) -> dict:
    return {
        "manuscript": "# Mock book\n\n## 第1章\n\n离线已提交文本。\n",
        "evidence": {
            "schema_version": "provider-product-smoke-evidence-v1",
            "outcome": "passed",
            "provider_runtime": smoke._safe_provider_diagnostics(config),
            "metrics": {
                "chapter_count": 3,
                "section_count": 3,
                "transaction_count": 3,
                "planner_calls": 0,
                "full_writer_retries": 0,
                "rejected_prose_published_count": 0,
            },
            "gates": {"offline_mock": True},
            "chapters": [
                {
                    "chapter_id": f"chapter_{ordinal:04d}",
                    "ordinal": ordinal,
                    "char_count": 1_000,
                    "style_profile_id": (
                        "preset_literary" if ordinal < 3 else "style_mock"
                    ),
                }
                for ordinal in range(1, 4)
            ],
        },
    }


def test_module_top_level_imports_only_stdlib() -> None:
    source_path = Path(smoke.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    allowed_roots = {
        "__future__",
        "argparse",
        "asyncio",
        "hashlib",
        "importlib",
        "json",
        "os",
        "pathlib",
        "re",
        "shutil",
        "sys",
        "tempfile",
        "typing",
        "uuid",
    }
    imported_roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_roots.add((node.module or "").split(".", 1)[0])
    assert imported_roots <= allowed_roots
    assert "story" not in imported_roots
    assert "nf_core" not in imported_roots


def test_mock_provider_cli_publishes_secret_free_artifacts_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    provider_file = tmp_path / "mock-provider.env"
    original = _write_fake_provider(provider_file)
    output = tmp_path / "provider-product-smoke"
    calls: list[tuple[str, str, Path]] = []

    async def fake_execute(config, data_dir: Path) -> dict:
        calls.append((config.provider, config.model, data_dir))
        assert config.thinking_mode == "disabled"
        assert config.max_retries == 0
        return _mock_result(config)

    monkeypatch.setattr(smoke, "_execute_product_smoke", fake_execute)
    result = smoke.main(
        [
            "--provider-file",
            str(provider_file),
            "--output-dir",
            str(output),
        ]
    )
    captured = capsys.readouterr()
    assert result == 0, captured.err
    public = json.loads(captured.out)
    assert public["ok"] is True
    assert public["provider"] == "custom"
    assert public["model"] == "glm-5.2"
    assert public["chapter_count"] == 3
    assert calls and calls[0][:2] == ("custom", "glm-5.2")
    assert not calls[0][2].exists()
    assert provider_file.read_bytes() == original

    expected_files = {
        "artifact-sha256.json",
        "evidence.json",
        "manuscript.md",
        "summary.json",
    }
    assert {path.name for path in output.iterdir()} == expected_files
    evidence_text = (output / "evidence.json").read_text(encoding="utf-8")
    evidence = json.loads(evidence_text)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    hashes = json.loads(
        (output / "artifact-sha256.json").read_text(encoding="utf-8")
    )
    assert evidence["provider_file_unchanged"] is True
    assert evidence["provider_runtime"]["source"] == "provider_file"
    assert evidence["provider_runtime"]["credential_present"] is True
    assert len(evidence["provider_runtime"]["key_fingerprint"]) == 8
    assert "test-only-provider-credential" not in evidence_text
    assert "https://provider.invalid" not in evidence_text
    assert summary["gates"] == {"offline_mock": True}
    for name, metadata in hashes["artifacts"].items():
        assert metadata["sha256"] == _sha256(output / name)

    before = {
        path.name: _sha256(path) for path in output.iterdir() if path.is_file()
    }
    repeated = smoke.main(
        [
            "--provider-file",
            str(provider_file),
            "--output-dir",
            str(output),
        ]
    )
    repeated_output = capsys.readouterr()
    assert repeated == 2
    assert json.loads(repeated_output.err)["error_type"] == "FileExistsError"
    assert {
        path.name: _sha256(path) for path in output.iterdir() if path.is_file()
    } == before


def test_exact_and_generic_secret_scan_fails_without_reflecting_values(
    tmp_path: Path,
) -> None:
    exact_key = "exact-test-key-material-987654321"
    exact_url = "https://private-provider.invalid/v1"
    (tmp_path / "key.txt").write_text(exact_key, encoding="utf-8")
    (tmp_path / "url.txt").write_text(exact_url, encoding="utf-8")
    (tmp_path / "generic.txt").write_text(
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        encoding="utf-8",
    )
    report = smoke.scan_artifacts(
        tmp_path,
        exact_values={"provider_key": exact_key, "provider_base_url": exact_url},
    )
    assert {row["label"] for row in report["exact_hits"]} == {
        "provider_key",
        "provider_base_url",
    }
    assert report["generic_hits"] == [
        {"file": "generic.txt", "pattern": "bearer_credential"}
    ]
    assert exact_key not in json.dumps(report)
    assert exact_url not in json.dumps(report)
    with pytest.raises(smoke.ArtifactLeakError, match="not published"):
        smoke.assert_artifacts_secret_free(
            tmp_path,
            exact_values={
                "provider_key": exact_key,
                "provider_base_url": exact_url,
            },
        )


def test_exclusive_output_cleans_staging_and_never_overwrites(tmp_path: Path) -> None:
    output = tmp_path / "artifacts"
    with smoke.ExclusiveArtifactOutput(output) as publication:
        smoke._atomic_write(publication.staging_dir / "safe.txt", b"safe")
        assert publication.publish() == output
    assert (output / "safe.txt").read_bytes() == b"safe"

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        with smoke.ExclusiveArtifactOutput(output):
            raise AssertionError("unreachable")
    assert (output / "safe.txt").read_bytes() == b"safe"
    assert not list(tmp_path.glob(".artifacts.staging-*"))
    assert not (tmp_path / ".artifacts.publish.lock").exists()


def test_evidence_rejects_prose_prompt_sample_and_endpoint_fields() -> None:
    safe = {
        "provider": "custom",
        "model": "glm-5.2",
        "prompt_tokens_total": 12,
        "manuscript_sha256": "0" * 64,
    }
    smoke._assert_evidence_is_metadata_only(safe)
    for forbidden in (
        "api_key",
        "base_url",
        "content",
        "narrative_text",
        "optional_user_sample",
        "prompt",
    ):
        with pytest.raises(
            smoke.ProductSmokeInvariantError,
            match="forbidden field",
        ):
            smoke._assert_evidence_is_metadata_only({forbidden: "must not appear"})


@pytest.mark.asyncio
async def test_offline_recorded_outputs_drive_the_complete_product_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nf_core.provider_runtime import ProviderRuntimeConfig
    from story.outline_generator import (
        GeneratedBookOutline,
        OutlineGenerationResult,
        WholeBookOutlineGenerator,
    )
    from story.production_models import ChapterOutline, VolumeOutline
    from story.models import WriterCandidate
    from story.writer import AuthorWriter, WriterResult

    proposal = GeneratedBookOutline(
        logline="守灯人核验三份档案并作出公开真相的选择。",
        global_arc="发现异常、核验代价、公开真相。",
        volumes=[
            VolumeOutline(
                id="volume_001",
                ordinal=1,
                title="潮汐档案",
                objective="核验档案并完成选择。",
                opening_state="异常尚未核验。",
                closing_state="真相已经公开。",
                target_chapters=3,
                target_chars=3_000,
            )
        ],
        chapters=[
            ChapterOutline(
                id=f"chapter_{ordinal:04d}",
                ordinal=ordinal,
                volume_id="volume_001",
                title=f"第{ordinal}份档案",
                objective="林岚核验现有档案并承担这一步的确定后果。",
                viewpoint_character_id="林岚",
                involved_characters=["林岚"],
                target_chars=1_000,
            )
            for ordinal in range(1, 4)
        ],
        ending_target="林岚公开真相并承担后果。",
    )
    outline_calls = 0
    writer_styles: list[dict] = []

    async def recorded_outline(self, *, spec, bible) -> OutlineGenerationResult:
        nonlocal outline_calls
        outline_calls += 1
        assert spec.chapter_count == 3
        assert not bible.publish_errors()
        return OutlineGenerationResult(
            proposal=proposal,
            provider_calls=1,
            repair_performed=False,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

    async def recorded_writer(self, context, goal) -> WriterResult:
        style_slot = json.loads(context.slots["style_contract"])
        writer_styles.append(style_slot)
        assert "optional_user_sample" not in style_slot
        unit = "林岚沿档案编号逐项核验潮痕，确认记录后承担选择的后果。"
        narrative = (unit * ((goal.desired_length // len(unit)) + 1))[
            : goal.desired_length
        ]
        return WriterResult(
            candidate=WriterCandidate(
                narrative_text=narrative,
                title="核验",
                section_summary="林岚核验档案并承担已确认的后果。",
            ),
            usage={"prompt_tokens": 11, "completion_tokens": 17, "total_tokens": 28},
            provider=config.provider,
            provider_model=config.model,
            provider_source=config.source,
            provider_config_fingerprint=config.config_fingerprint,
        )

    monkeypatch.setattr(WholeBookOutlineGenerator, "generate", recorded_outline)
    monkeypatch.setattr(AuthorWriter, "generate", recorded_writer)
    config = ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key="offline-recorded-key-material-123456789",
        base_url="https://offline.invalid/v1",
        model="glm-5.2",
        thinking_mode="disabled",
        max_retries=0,
        source="offline_test",
    )
    result = await smoke._execute_product_smoke(config, tmp_path / "novel")

    assert outline_calls == 1
    assert len(writer_styles) == 3
    assert result["manuscript"].count("## 第") == 3
    evidence = result["evidence"]
    assert all(evidence["gates"].values())
    assert evidence["metrics"]["chapter_count"] == 3
    assert evidence["metrics"]["section_count"] == 3
    assert evidence["metrics"]["planner_calls"] == 0
    assert evidence["metrics"]["section_provider_calls"] == 3
    assert evidence["metrics"]["provider_calls_total"] == 4
    assert all(row["writer_calls"] == 1 for row in evidence["transactions"])
    assert all(row["provider_calls"] == 1 for row in evidence["transactions"])
    assert evidence["metrics"]["full_writer_retries"] == 0
    assert [row["style_profile_id"] for row in evidence["chapters"][:2]] == [
        "preset_literary",
        "preset_literary",
    ]
    assert evidence["chapters"][2]["style_profile_id"].startswith(
        "style_provider_smoke_"
    )
    serialized = json.dumps(evidence, ensure_ascii=False)
    assert "雨落在旧码头" not in serialized
    assert "林岚沿档案编号" not in serialized
    assert "https://offline.invalid" not in serialized
    assert "offline-recorded-key" not in serialized
