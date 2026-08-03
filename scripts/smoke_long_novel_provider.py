"""Real-provider smoke for the recoverable whole-book Author product path.

This module is deliberately safe to import: only Python's standard library is
loaded at module import time.  ``main`` parses the CLI before the provider
runtime or any Author/LLM generation module is imported.  The only credential
source is the explicitly supplied, read-only ``--provider-file``.

The script is an acceptance runner, not a fixture.  Importing it never performs
network I/O, and it must never be invoked from the offline test suite without
mocking ``_execute_product_smoke``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Sequence


EXPECTED_PROVIDER = "custom"
EXPECTED_MODEL = "glm-5.2"
EXPECTED_THINKING_MODE = "disabled"
EXPECTED_SDK_RETRIES = 0
CHAPTER_COUNT = 3
TARGET_CHAPTER_CHARS = 1_000
MIN_CHAPTER_CHARS = 900
MAX_CHAPTER_CHARS = 1_100

_GENERIC_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "openai_style_key",
        re.compile(r"(?i)(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{12,}"),
    ),
    (
        "bearer_credential",
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{12,}"),
    ),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|secret)\b"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9._~+/-]{12,}"
        ),
    ),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "github_token",
        re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{20,}"),
    ),
    (
        "aws_access_key",
        re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
    ),
    (
        "google_api_key",
        re.compile(r"(?<![A-Za-z0-9_-])AIza[A-Za-z0-9_-]{30,}"),
    ),
    (
        "slack_token",
        re.compile(r"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{20,}"),
    ),
)


class ArtifactLeakError(RuntimeError):
    """A staged public artifact contains credential-like material."""


class ProductSmokeInvariantError(RuntimeError):
    """The real product path did not satisfy a hard acceptance invariant."""


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a three-chapter real-provider smoke through the complete "
            "whole-book Author production path."
        )
    )
    parser.add_argument(
        "--provider-file",
        required=True,
        type=Path,
        help="Read-only provider configuration file; the sole credential source.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="New, non-existing directory to publish acceptance artifacts into.",
    )
    return parser.parse_args(argv)


def _configure_import_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    backend_root = project_root / "backend"
    for path in (str(project_root), str(backend_root)):
        if path not in sys.path:
            sys.path.insert(0, path)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_json(path: Path, value: Any) -> None:
    payload = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    _atomic_write(path, payload)


class ExclusiveArtifactOutput:
    """Own one sibling staging directory and publish it without overwriting."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir.expanduser().resolve()
        self.parent = self.output_dir.parent
        self.staging_dir = self.parent / (
            f".{self.output_dir.name}.staging-{uuid.uuid4().hex}"
        )
        self.lock_path = self.parent / f".{self.output_dir.name}.publish.lock"
        self._lock_fd: int | None = None
        self._published = False

    def __enter__(self) -> "ExclusiveArtifactOutput":
        self.parent.mkdir(parents=True, exist_ok=True)
        if self.output_dir.exists():
            raise FileExistsError(
                f"refusing to overwrite existing output: {self.output_dir}"
            )
        self._lock_fd = os.open(
            self.lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        try:
            os.mkdir(self.staging_dir)
        except BaseException:
            self._release_lock()
            raise
        return self

    def publish(self) -> Path:
        if self._published:
            return self.output_dir
        if self.output_dir.exists():
            raise FileExistsError(
                f"refusing to overwrite existing output: {self.output_dir}"
            )
        os.rename(self.staging_dir, self.output_dir)
        self._published = True
        return self.output_dir

    def _release_lock(self) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if not self._published and self.staging_dir.exists():
            resolved = self.staging_dir.resolve()
            if resolved.parent == self.parent and resolved.name.startswith(
                f".{self.output_dir.name}.staging-"
            ):
                shutil.rmtree(resolved)
        self._release_lock()


def scan_artifacts(
    root: Path,
    *,
    exact_values: dict[str, str],
) -> dict[str, Any]:
    """Scan staged files without ever reflecting the sensitive values."""

    root = root.resolve()
    exact_hits: list[dict[str, str]] = []
    generic_hits: list[dict[str, str]] = []
    scanned_files = 0
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        scanned_files += 1
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        for label, secret in exact_values.items():
            if secret and secret.encode("utf-8") in raw:
                exact_hits.append({"file": relative, "label": label})
        text = raw.decode("utf-8", errors="ignore")
        for label, pattern in _GENERIC_SECRET_PATTERNS:
            if pattern.search(text):
                generic_hits.append({"file": relative, "pattern": label})
    return {
        "scanned_files": scanned_files,
        "exact_hits": exact_hits,
        "generic_hits": generic_hits,
    }


def assert_artifacts_secret_free(
    root: Path,
    *,
    exact_values: dict[str, str],
) -> dict[str, int]:
    report = scan_artifacts(root, exact_values=exact_values)
    if report["exact_hits"] or report["generic_hits"]:
        raise ArtifactLeakError(
            "staged artifacts failed the credential scan; output was not published"
        )
    return {
        "scanned_files": int(report["scanned_files"]),
        "exact_hit_count": 0,
        "generic_hit_count": 0,
    }


def _safe_provider_diagnostics(config: Any) -> dict[str, Any]:
    diagnostics = config.diagnostics()
    allowed = {
        "provider",
        "model",
        "source",
        "thinking_mode",
        "retries",
        "credential_present",
        "config_fingerprint",
        "key_fingerprint",
    }
    return {key: diagnostics[key] for key in sorted(allowed & diagnostics.keys())}


def _assert_provider_contract(config: Any) -> None:
    failures: list[str] = []
    if config.provider != EXPECTED_PROVIDER:
        failures.append(f"provider must be {EXPECTED_PROVIDER}")
    if config.model != EXPECTED_MODEL:
        failures.append(f"model must be {EXPECTED_MODEL}")
    if config.thinking_mode != EXPECTED_THINKING_MODE:
        failures.append("thinking mode must be disabled")
    if config.max_retries != EXPECTED_SDK_RETRIES:
        failures.append("SDK retries must be zero")
    if failures:
        raise ProductSmokeInvariantError("; ".join(failures))


def _assert_evidence_is_metadata_only(evidence: dict[str, Any]) -> None:
    forbidden_keys = {
        "api_key",
        "base_url",
        "content",
        "narrative_text",
        "optional_user_sample",
        "prompt",
        "system_prompt",
        "user_prompt",
    }

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in forbidden_keys:
                    raise ProductSmokeInvariantError(
                        f"evidence contains forbidden field {key!r}"
                    )
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(evidence)


def _build_manuscript(title: str, chapters: Sequence[Any]) -> str:
    blocks = [f"# {title}"]
    for chapter in chapters:
        if chapter.status != "committed":
            continue
        blocks.append(
            f"## 第{chapter.chapter_ordinal}章 {chapter.title}\n\n"
            f"{chapter.manuscript_text()}"
        )
    return "\n\n".join(blocks).rstrip() + "\n"


async def _execute_product_smoke(config: Any, data_dir: Path) -> dict[str, Any]:
    """Run the real outline + Author + production chain inside one fresh domain."""

    from story.models import StoryBibleUpdate
    from story.outline_generator import WholeBookOutlineGenerator
    from story.production_adapter import AuthorProductionSectionRunner
    from story.production_models import (
        BookOutlineUpdate,
        NovelProductionSpecUpdate,
        StyleProfileCreate,
    )
    from story.production_persistence import (
        ActiveStyleStore,
        BookOutlineStore,
        ProductionSpecStore,
        StyleProfileStore,
        ensure_production_domain,
    )
    from story.production_service import WholeBookProductionService
    from story.service import AuthorGenerationService

    user_id = f"provider_smoke_{uuid.uuid4().hex[:12]}"
    novel_id = f"novel_{uuid.uuid4().hex[:16]}"
    title = "潮汐档案"
    author = AuthorGenerationService(
        user_id=user_id,
        novel_id=novel_id,
        data_dir=str(data_dir),
        title=title,
        enable_llm_planner=False,
    )
    original_bible = author.bibles.load()
    bible = author.bibles.update(
        StoryBibleUpdate(
            expected_revision=original_bible.revision,
            title=title,
            source_seed="守灯人发现潮汐正在抹去城市的共同记忆。",
            theme_key="memory_and_choice",
            positioning="三章闭环的近未来悬疑故事",
            premise="守灯人必须在保存真相与保护城市之间作出选择。",
            theme="记忆、责任与选择",
            central_question="被保存的真相是否值得整座城市承担代价？",
            genre="近未来悬疑",
            setting_summary="一座由潮汐档案维持公共记忆的海港城。",
            immutable_world_rules=[
                "潮汐只会抹去未经档案确认的公共记忆。",
                "已经发生的死亡不可逆转。",
            ],
            forbidden_deviations=["不得引入时间旅行或复活。"],
            protagonist_contracts=["守灯人林岚负责核验潮汐档案。"],
            main_conflicts=["公开真相会破坏城市短暂的安宁。"],
            ending_direction="林岚公开真相并承担由此产生的后果。",
        )
    )
    if bible.publish_errors():
        raise ProductSmokeInvariantError("new StoryBible is not publishable")

    ensure_production_domain(str(data_dir), title=title)
    styles = StyleProfileStore(str(data_dir))
    active_styles = ActiveStyleStore(
        str(data_dir),
        lambda: (_ for _ in ()).throw(AssertionError("active style is missing")),
    )
    preset = styles.get("preset_literary")
    binding = active_styles.load()
    binding = active_styles.activate(
        preset,
        applies_from_chapter_ordinal=1,
        expected_revision=binding.revision,
    )

    specs = ProductionSpecStore(
        str(data_dir),
        lambda: (_ for _ in ()).throw(AssertionError("production spec is missing")),
    )
    initial_spec = specs.load()
    spec = specs.update(
        NovelProductionSpecUpdate(
            expected_revision=initial_spec.revision,
            title=title,
            premise=bible.premise,
            genre=bible.genre,
            theme=bible.theme,
            central_question=bible.central_question,
            target_total_chars=CHAPTER_COUNT * TARGET_CHAPTER_CHARS,
            volume_count=1,
            chapter_count=CHAPTER_COUNT,
            target_chapter_chars=TARGET_CHAPTER_CHARS,
            accepted_chapter_min_chars=MIN_CHAPTER_CHARS,
            accepted_chapter_max_chars=MAX_CHAPTER_CHARS,
            section_target_chars=MAX_CHAPTER_CHARS,
            ending_direction=bible.ending_direction,
            production_status="ready",
            active_style_profile_id=preset.id,
        )
    )

    outline_result = await WholeBookOutlineGenerator().generate(
        spec=spec,
        bible=bible,
    )
    outlines = BookOutlineStore(str(data_dir))
    original_outline = outlines.load()
    proposal = outline_result.proposal
    outline = outlines.update(
        BookOutlineUpdate(
            expected_revision=original_outline.revision,
            logline=proposal.logline,
            global_arc=proposal.global_arc,
            volumes=proposal.volumes,
            chapters=proposal.chapters,
            ending_target=proposal.ending_target,
            major_turning_points=proposal.major_turning_points,
            central_conflict_progression=proposal.central_conflict_progression,
            thread_schedule=proposal.thread_schedule,
            character_arc_schedule=proposal.character_arc_schedule,
            status="ready",
        )
    )
    outline_errors = outline.validation_errors_for(spec)
    if outline_errors:
        raise ProductSmokeInvariantError(
            "strict generated outline failed after persistence"
        )

    production = WholeBookProductionService(
        user_id=user_id,
        novel_id=novel_id,
        data_dir=str(data_dir),
        section_runner=AuthorProductionSectionRunner(author),
        owner_id=f"provider_smoke_worker_{uuid.uuid4().hex[:12]}",
        lease_seconds=0,
    )
    started = production.start(
        expected_spec_revision=spec.revision,
        expected_outline_revision=outline.revision,
    )
    if started.existing:
        raise ProductSmokeInvariantError("fresh product smoke reused an existing job")
    job = await production.run(started.job.id, max_sections=2)
    first_chapters = production.list_chapters(committed_only=True)
    if len(first_chapters) != 2 or job.active_transaction_id:
        raise ProductSmokeInvariantError(
            "first production slice did not stop at a safe two-chapter boundary"
        )

    sample = "雨落在旧码头，守灯人停住脚步，听潮声越过封闭的档案门。"
    custom = styles.create(
        StyleProfileCreate(
            name="冷潮短句",
            base_preset_key="literary",
            description="克制、清醒，以动作和可感知细节推进。",
            narrative_voice="有限第三人称，避免全知判断。",
            sentence_length_tendency="短句为主，关键处允许一处舒展长句。",
            paragraph_density="偏疏朗",
            pacing="稳健但不拖延",
            emotional_intensity=5,
            imagery_preference="潮声、灯影与锈迹",
            rhythm_instructions="段落收束在动作或确定后果上。",
            must_do_rules=["先写可观察动作，再写人物判断。"],
            forbidden_rules=["不得借风格新增人物、事件或世界规则。"],
            optional_user_sample=sample,
            derived_style_anchors=["短句占优", "段末落在动作后果"],
            deterministic_rules=["事实与情节权威优先于表达偏好"],
        ),
        profile_id=f"style_provider_smoke_{uuid.uuid4().hex[:12]}",
    )
    if sample in custom.prompt_text() or "optional_user_sample" in custom.prompt_text():
        raise ProductSmokeInvariantError("custom style sample entered the Writer prompt")
    binding = active_styles.activate(
        custom,
        applies_from_chapter_ordinal=3,
        expected_revision=binding.revision,
    )
    current_spec = specs.load()
    specs.update(
        NovelProductionSpecUpdate(
            expected_revision=current_spec.revision,
            active_style_profile_id=custom.id,
        )
    )

    pause_requested = production.pause(job.id, expected_revision=job.revision)
    paused = await production.run(job.id, max_sections=0)
    if pause_requested.status != "pausing" or paused.status != "paused":
        raise ProductSmokeInvariantError("job did not pause at the safe boundary")
    resumed = production.resume(job.id, expected_revision=paused.revision)
    if resumed.status != "queued":
        raise ProductSmokeInvariantError("paused job did not resume to queued")
    completed = await production.run(job.id)
    if completed.status != "completed":
        raise ProductSmokeInvariantError(
            f"production ended in unexpected status {completed.status!r}"
        )

    chapters = production.list_chapters(committed_only=True)
    attempts = production.attempts.list_all(job_id=job.id)
    transactions = sorted(
        author.transactions.list_all(),
        key=lambda transaction: (
            transaction.production_context.chapter_outline.ordinal
            if transaction.production_context is not None
            else 0,
            transaction.id,
        ),
    )
    sections = sorted(author.sections.list_all(), key=lambda item: (item.chapter, item.section))
    final_outline = outlines.load()
    events = production.events.load(job.id).events
    section_provider_calls = sum(
        transaction.planner_calls
        + transaction.writer_calls
        + transaction.structured_output_repair_count
        for transaction in transactions
    )
    provider_calls_total = outline_result.provider_calls + section_provider_calls

    def expected_writer_calls(transaction: Any) -> int:
        provider_repair_expected = bool(
            transaction.repair_performed
            and transaction.repair_plan is not None
            and any(
                template.provider_text_required
                for template in transaction.repair_plan.patch_templates
            )
        )
        return 1 + int(provider_repair_expected)

    gates = {
        "provider_contract": (
            config.provider == EXPECTED_PROVIDER
            and config.model == EXPECTED_MODEL
            and config.thinking_mode == EXPECTED_THINKING_MODE
            and config.max_retries == EXPECTED_SDK_RETRIES
        ),
        "three_committed_chapters": len(chapters) == CHAPTER_COUNT,
        "single_section_per_chapter": all(
            chapter.expected_section_count == 1 and len(chapter.sections) == 1
            for chapter in chapters
        ),
        "chapter_lengths_in_range": all(
            MIN_CHAPTER_CHARS <= chapter.char_count <= MAX_CHAPTER_CHARS
            for chapter in chapters
        ),
        "style_applies_only_to_third": (
            len(chapters) == CHAPTER_COUNT
            and [chapter.style_profile.id for chapter in chapters[:2]]
            == [preset.id, preset.id]
            and chapters[2].style_profile.id == custom.id
            and binding.applies_from_chapter_ordinal == 3
        ),
        "planner_zero": all(transaction.planner_calls == 0 for transaction in transactions),
        "full_writer_retry_zero": all(
            transaction.writer_retry_count == 0
            and not transaction.writer_retry_performed
            for transaction in transactions
        ),
        "provider_call_accounting": (
            1 <= outline_result.provider_calls <= 2
            and len(transactions) == CHAPTER_COUNT
            and all(
                transaction.writer_calls == expected_writer_calls(transaction)
                and 0 <= transaction.structured_output_repair_count <= 1
                for transaction in transactions
            )
            and section_provider_calls
            == sum(
                transaction.planner_calls
                + transaction.writer_calls
                + transaction.structured_output_repair_count
                for transaction in transactions
            )
            and provider_calls_total
            == outline_result.provider_calls + section_provider_calls
        ),
        "formal_transactions": (
            len(transactions) == CHAPTER_COUNT
            and all(
                transaction.committed and transaction.phase == "committed"
                for transaction in transactions
            )
        ),
        "provider_receipts_bound_to_transactions": (
            len(transactions) == CHAPTER_COUNT
            and all(
                transaction.provider == config.provider
                and transaction.provider_model == config.model
                and bool(transaction.provider_source)
                and transaction.provider_config_fingerprint
                == config.config_fingerprint
                for transaction in transactions
            )
            and all(
                attempt.provider == config.provider
                and attempt.provider_model == config.model
                and bool(attempt.provider_source)
                and attempt.provider_config_fingerprint
                == config.config_fingerprint
                for attempt in attempts
            )
        ),
        "attempts_committed_only": (
            len(attempts) == CHAPTER_COUNT
            and all(attempt.status == "committed" for attempt in attempts)
            and all(attempt.committed_content for attempt in attempts)
        ),
        "no_rejected_prose_published": all(
            attempt.status == "committed" or not attempt.committed_content
            for attempt in attempts
        ),
        "unique_transactions_and_sections": (
            len({item.id for item in transactions}) == len(transactions)
            and len({item.id for item in sections}) == len(sections)
            and len({item.transaction_id for item in sections}) == len(sections)
        ),
        "canonical_revision_contiguous": (
            len(transactions) == CHAPTER_COUNT
            and all(
                transaction.target_canonical_revision
                == transaction.canonical_state_revision + 1
                for transaction in transactions
            )
            and all(
                transactions[index].canonical_state_revision
                == transactions[index - 1].target_canonical_revision
                for index in range(1, len(transactions))
            )
            and completed.last_committed_canonical_revision
            == transactions[-1].target_canonical_revision
        ),
        "outline_progress_committed": (
            final_outline.status in {"ready", "locked", "completed"}
            and all(chapter.status == "committed" for chapter in final_outline.chapters)
            and all(len(chapter.committed_section_ids) == 1 for chapter in final_outline.chapters)
            and final_outline.progress_revision
            == outline.progress_revision + CHAPTER_COUNT
        ),
        "no_job_retry": (
            completed.retry_count == 0
            and set(completed.chapter_attempts.values()) == {1}
        ),
        "pause_resume_once": (
            pause_requested.status == "pausing"
            and paused.status == "paused"
            and resumed.status == "queued"
        ),
        "event_sequence_contiguous": [event.sequence for event in events]
        == list(range(1, len(events) + 1)),
    }
    failed_gates = sorted(key for key, passed in gates.items() if not passed)
    if failed_gates:
        raise ProductSmokeInvariantError(
            "product smoke hard gates failed: " + ", ".join(failed_gates)
        )

    manuscript = _build_manuscript(title, chapters)
    if manuscript.count("## 第") != CHAPTER_COUNT:
        raise ProductSmokeInvariantError("committed-only manuscript is incomplete")
    chapter_rows = [
        {
            "chapter_id": chapter.chapter_id,
            "ordinal": chapter.chapter_ordinal,
            "section_count": len(chapter.sections),
            "char_count": chapter.char_count,
            "style_profile_id": chapter.style_profile.id,
            "style_revision": chapter.style_profile.revision,
            "style_prompt_hash": chapter.style_profile.prompt_hash,
            "canonical_revision_start": chapter.canonical_revision_start,
            "canonical_revision_end": chapter.canonical_revision_end,
            "repair_total": chapter.repair_total,
            "transaction_ids": [section.transaction_id for section in chapter.sections],
        }
        for chapter in chapters
    ]
    evidence = {
        "schema_version": "provider-product-smoke-evidence-v1",
        "outcome": "passed",
        "provider_runtime": _safe_provider_diagnostics(config),
        "outline": {
            "provider_calls": outline_result.provider_calls,
            "repair_performed": outline_result.repair_performed,
            "revision": outline.revision,
            "final_progress_revision": final_outline.progress_revision,
            "chapter_count": len(final_outline.chapters),
        },
        "job": {
            "job_id": completed.id,
            "status": completed.status,
            "revision": completed.revision,
            "prompt_tokens_total": completed.prompt_tokens_total,
            "completion_tokens_total": completed.completion_tokens_total,
            "latency_total_ms": completed.latency_total_ms,
            "repair_total": completed.repair_total,
            "retry_count": completed.retry_count,
            "active_transaction_id_present": bool(completed.active_transaction_id),
        },
        "style_transition": {
            "initial_style_profile_id": preset.id,
            "custom_style_profile_id": custom.id,
            "custom_style_revision": custom.revision,
            "custom_style_prompt_hash": custom.prompt_hash,
            "applies_from_chapter_ordinal": binding.applies_from_chapter_ordinal,
            "sample_excluded_from_prompt": True,
        },
        "control": {
            "pause_count": 1,
            "resume_count": 1,
            "safe_boundary": True,
        },
        "metrics": {
            "chapter_count": len(chapters),
            "section_count": len(sections),
            "transaction_count": len(transactions),
            "attempt_count": len(attempts),
            "planner_calls": sum(item.planner_calls for item in transactions),
            "section_provider_calls": section_provider_calls,
            "provider_calls_total": provider_calls_total,
            "full_writer_retries": sum(item.writer_retry_count for item in transactions),
            "repair_total": sum(int(item.repair_performed) for item in transactions),
            "duplicate_section_count": len(sections) - len({item.id for item in sections}),
            "duplicate_transaction_count": len(transactions)
            - len({item.id for item in transactions}),
            "rejected_prose_published_count": 0,
            "canonical_revision_final": completed.last_committed_canonical_revision,
            "production_event_count": len(events),
        },
        "transactions": [
            {
                "transaction_id": transaction.id,
                "provider": transaction.provider,
                "model": transaction.provider_model,
                "source": transaction.provider_source,
                "config_fingerprint": (
                    transaction.provider_config_fingerprint
                ),
                "structured_output_repair_count": (
                    transaction.structured_output_repair_count
                ),
                "planner_calls": transaction.planner_calls,
                "writer_calls": transaction.writer_calls,
                "provider_calls": (
                    transaction.planner_calls
                    + transaction.writer_calls
                    + transaction.structured_output_repair_count
                ),
                "full_writer_retry_count": transaction.writer_retry_count,
                "committed": transaction.committed,
            }
            for transaction in transactions
        ],
        "chapters": chapter_rows,
        "gates": gates,
        "secret_scan": {
            "exact_key_hits": 0,
            "exact_base_url_hits": 0,
            "generic_secret_hits": 0,
        },
    }
    _assert_evidence_is_metadata_only(evidence)
    return {"manuscript": manuscript, "evidence": evidence}


def _write_artifacts(staging_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    manuscript = str(result["manuscript"])
    evidence = dict(result["evidence"])
    manuscript_path = staging_dir / "manuscript.md"
    evidence_path = staging_dir / "evidence.json"
    summary_path = staging_dir / "summary.json"
    hashes_path = staging_dir / "artifact-sha256.json"

    _atomic_write(manuscript_path, manuscript.encode("utf-8"))
    evidence["artifacts"] = {
        "manuscript_sha256": _sha256_file(manuscript_path),
        "manuscript_bytes": manuscript_path.stat().st_size,
    }
    _assert_evidence_is_metadata_only(evidence)
    _atomic_json(evidence_path, evidence)
    summary = {
        "schema_version": "provider-product-smoke-summary-v1",
        "ok": True,
        "provider": evidence["provider_runtime"],
        "metrics": evidence["metrics"],
        "gates": evidence["gates"],
        "artifact_hashes": {
            "manuscript.md": _sha256_file(manuscript_path),
            "evidence.json": _sha256_file(evidence_path),
        },
    }
    _assert_evidence_is_metadata_only(summary)
    _atomic_json(summary_path, summary)
    artifact_hashes = {
        path.name: {
            "sha256": _sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in (manuscript_path, evidence_path, summary_path)
    }
    _atomic_json(
        hashes_path,
        {
            "schema_version": "artifact-sha256-v1",
            "artifacts": artifact_hashes,
        },
    )
    return {
        "summary": summary,
        "summary_sha256": _sha256_file(summary_path),
        "artifact_count": 4,
    }


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    output = ExclusiveArtifactOutput(args.output_dir)
    with output:
        _configure_import_path()
        provider_runtime = importlib.import_module("nf_core.provider_runtime")
        provider_file = args.provider_file.expanduser().resolve()
        before_digest = _sha256_file(provider_file)
        before_stat = provider_file.stat()
        config = provider_runtime.ProviderRuntimeConfig.from_provider_file(provider_file)
        _assert_provider_contract(config)

        with tempfile.TemporaryDirectory(prefix="novel-provider-product-smoke-") as work:
            data_dir = Path(work) / "isolated-novel"
            with provider_runtime.stage_provider_scope(config):
                llm_module = importlib.import_module("nf_core.llm_client")
                llm_module.llm_client.reload(config=config)
                try:
                    result = await _execute_product_smoke(config, data_dir)
                finally:
                    await llm_module.llm_client.aclose()

        after_stat = provider_file.stat()
        if (
            _sha256_file(provider_file) != before_digest
            or after_stat.st_size != before_stat.st_size
            or after_stat.st_mtime_ns != before_stat.st_mtime_ns
        ):
            raise ProductSmokeInvariantError("provider file changed during the smoke")
        result["evidence"]["provider_file_unchanged"] = True
        artifact_result = _write_artifacts(output.staging_dir, result)
        scan = assert_artifacts_secret_free(
            output.staging_dir,
            exact_values={
                "provider_key": config.api_key,
                "provider_base_url": config.base_url,
            },
        )
        published = output.publish()
        return {
            "ok": True,
            "output_dir": str(published),
            "summary_sha256": artifact_result["summary_sha256"],
            "artifact_count": artifact_result["artifact_count"],
            "scanned_files": scan["scanned_files"],
            "chapter_count": result["evidence"]["metrics"]["chapter_count"],
            "provider": result["evidence"]["provider_runtime"]["provider"],
            "model": result["evidence"]["provider_runtime"]["model"],
        }


def _run_in_isolated_loop(awaitable: Any) -> Any:
    """Run CLI work without replacing a caller's current event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(awaitable)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())
        loop.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        public_result = _run_in_isolated_loop(_run(args))
    except Exception as exc:
        error = {
            "ok": False,
            "error_type": type(exc).__name__,
            "message": "provider product smoke failed closed; no output was published",
        }
        print(json.dumps(error, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(public_result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
