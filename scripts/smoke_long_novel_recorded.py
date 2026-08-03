"""Provider-free deterministic whole-book production acceptance smoke.

The default run produces 30 chapters with two sections each.  It exercises
durable service reconstruction, two pause/resume cycles, a crash after the
underlying Canon commit, one failed-section retry, and a next-chapter style
switch.  It never reads Provider configuration and never performs network or
LLM calls.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
for _import_root in (REPO_ROOT, REPO_ROOT / "backend"):
    if str(_import_root) not in sys.path:
        sys.path.insert(0, str(_import_root))

from story.models import (  # noqa: E402
    CanonicalState,
    StoryThread,
    StoryThreadRepository,
    utc_now,
)
from story.persistence import CanonicalStateStore, StoryThreadStore  # noqa: E402
from story.production_models import (  # noqa: E402
    BookOutlineUpdate,
    ChapterOutline,
    NovelProductionSpecUpdate,
    StyleProfileCreate,
    VolumeOutline,
    non_whitespace_char_count,
)
from story.production_persistence import (  # noqa: E402
    BookOutlineStore,
    ProductionEventStore,
    ProductionSectionAttemptStore,
    ProductionSpecStore,
    ensure_production_domain,
)
from story.production_service import (  # noqa: E402
    InjectedProductionCrash,
    SectionRunRequest,
    SectionRunResult,
    WholeBookProductionService,
)


DEFAULT_CHAPTER_COUNT = 30
DEFAULT_SECTIONS_PER_CHAPTER = 2
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / ".tmp" / "smoke-long-novel-recorded-final-20260730"
)
EVIDENCE_SCHEMA_VERSION = "recorded-long-novel-evidence-v1"
SUMMARY_SCHEMA_VERSION = "recorded-long-novel-summary-v1"
FAILURE_SENTINEL = "FAILED_CANDIDATE_MUST_NOT_ENTER_MANUSCRIPT"
REJECTED_SENTINEL = "REJECTED_CANDIDATE_MUST_NOT_ENTER_MANUSCRIPT"
MAIN_THREAD_ID = "thread_main_arc"
CUSTOM_STYLE_ID = "style_recorded_next_chapter"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _stable_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _prepare_output_dir(output_dir: Path) -> tuple[Path, Path]:
    output = output_dir.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # mkdir is the exclusive run claim.  Existing complete or partial output is
    # evidence and must never be silently reused or overwritten.
    output.mkdir(exist_ok=False)
    state_dir = output / "state"
    state_dir.mkdir()
    return output, state_dir


def _fact_material(state: CanonicalState) -> dict[str, Any]:
    return state.model_dump(
        mode="json",
        exclude={"revision", "world_time", "updated_at"},
    )


def _section_content(request: SectionRunRequest) -> str:
    chapter = request.snapshot.chapter_outline.ordinal
    section = request.snapshot.section_ordinal
    prefix = f"第{chapter:04d}章第{section:02d}节潮声记"
    target = request.snapshot.section_target_chars
    remaining = target - non_whitespace_char_count(prefix)
    if remaining < 0:
        raise AssertionError("recorded section prefix exceeds its target")
    return prefix + ("潮" * remaining)


class RecordedSectionRunner:
    """Idempotent local runner with an in-memory replay ledger."""

    def __init__(
        self,
        data_dir: Path,
        *,
        fail_once_for: tuple[int, int],
    ) -> None:
        self.data_dir = str(data_dir)
        self.fail_once_for = fail_once_for
        self.failed_slots: set[tuple[int, int]] = set()
        self.results: dict[str, SectionRunResult] = {}
        self.calls: list[str] = []
        self.commit_transactions: set[str] = set()
        self.commit_count = 0
        self.replay_call_count = 0
        self.duplicate_commit_count = 0
        self.hard_fact_bad_commit_count = 0
        self.state_bad_commit_count = 0
        self.thread_bad_commit_count = 0
        self.thread_liveness_violation_count = 0

    async def run_section(self, request: SectionRunRequest) -> SectionRunResult:
        self.calls.append(request.transaction_id)
        replay = self.results.get(request.transaction_id)
        if replay is not None:
            self.replay_call_count += 1
            return replay

        slot = (
            request.snapshot.chapter_outline.ordinal,
            request.snapshot.section_ordinal,
        )
        if slot == self.fail_once_for and slot not in self.failed_slots:
            self.failed_slots.add(slot)
            raise RuntimeError(f"{FAILURE_SENTINEL} {REJECTED_SENTINEL}")

        if request.transaction_id in self.commit_transactions:
            self.duplicate_commit_count += 1
            raise AssertionError("recorded runner attempted a duplicate commit")

        states = CanonicalStateStore(self.data_dir)
        current = states.load()
        if current.revision != request.snapshot.canonical_state_revision:
            self.state_bad_commit_count += 1
            raise AssertionError("recorded Canon revision is stale")
        before_facts = _fact_material(current)
        updated = current.model_copy(
            update={
                "revision": current.revision + 1,
                "world_time": current.world_time + 1,
                "updated_at": utc_now(),
            }
        )
        if updated.revision != current.revision + 1:
            self.state_bad_commit_count += 1
            raise AssertionError("recorded Canon revision did not advance once")
        if _fact_material(updated) != before_facts:
            self.hard_fact_bad_commit_count += 1
            raise AssertionError("recorded runner changed a hard fact")
        states.save_next(updated, expected_revision=current.revision)

        thread_store = StoryThreadStore(self.data_dir)
        with thread_store.lock:
            repository = thread_store.load()
            if repository.revision != request.snapshot.story_thread_revision:
                self.thread_bad_commit_count += 1
                raise AssertionError("recorded thread revision is stale")
            target_ids = list(request.goal.target_threads)
            if not target_ids:
                self.thread_liveness_violation_count += 1
                raise AssertionError("recorded section has no target story thread")
            threads = dict(repository.threads)
            for thread_id in target_ids:
                thread = threads.get(thread_id)
                if thread is None:
                    self.thread_bad_commit_count += 1
                    raise AssertionError("recorded section targets an unknown thread")
                threads[thread_id] = thread.model_copy(
                    update={
                        "status": "advancing",
                        "last_advanced_revision": updated.revision,
                        "updated_at_revision": updated.revision,
                        "evidence": [
                            *thread.evidence,
                            f"recorded:{request.section_id}",
                        ],
                    }
                )
            thread_store.save(
                repository.model_copy(
                    update={
                        "revision": repository.revision + 1,
                        "threads": threads,
                        "updated_at": utc_now(),
                    }
                )
            )
            if any(
                threads[thread_id].last_advanced_revision != updated.revision
                for thread_id in target_ids
            ):
                self.thread_liveness_violation_count += 1
                raise AssertionError("recorded story thread was not advanced")

        content = _section_content(request)
        result = SectionRunResult(
            transaction_id=request.transaction_id,
            section_id=request.section_id,
            committed=True,
            content=content,
            summary=(
                f"chapter {slot[0]} section {slot[1]} recorded commit"
            ),
            char_count=non_whitespace_char_count(content),
            canonical_revision_after=updated.revision,
            story_bible_revision=request.snapshot.story_bible_revision,
            validation_passed=True,
            repair_performed=slot[1] % 2 == 0,
            prompt_tokens=11,
            completion_tokens=17,
            latency_ms=23,
        )
        self.results[request.transaction_id] = result
        self.commit_transactions.add(request.transaction_id)
        self.commit_count += 1
        return result


class CrashOnce:
    def __init__(self, slot: tuple[int, int]) -> None:
        self.slot = slot
        self.triggered = False

    def __call__(self, phase, attempt, _result) -> None:
        current_slot = (attempt.chapter_ordinal, attempt.section_ordinal)
        if (
            phase == "after_runner_commit"
            and current_slot == self.slot
            and not self.triggered
        ):
            self.triggered = True
            raise InjectedProductionCrash()


def _configure_book(
    data_dir: Path,
    *,
    chapter_count: int,
    sections_per_chapter: int,
) -> None:
    ensure_production_domain(str(data_dir), title="录制潮汐长篇")
    section_chars = 500
    chapter_chars = section_chars * sections_per_chapter
    accepted_delta = max(1, chapter_chars // 20)
    total_chars = chapter_count * chapter_chars
    volume_count = min(3, chapter_count)

    spec_store = ProductionSpecStore(
        str(data_dir),
        lambda: (_ for _ in ()).throw(AssertionError("spec must exist")),
    )
    spec = spec_store.load()
    spec_store.update(
        NovelProductionSpecUpdate(
            expected_revision=spec.revision,
            title="录制潮汐长篇",
            premise="守潮人沿连续章节追查城市遗忘机制。",
            genre="确定性验收",
            theme="记忆与责任",
            central_question="城市能否在保留真相后继续前行？",
            target_total_chars=total_chars,
            volume_count=volume_count,
            chapter_count=chapter_count,
            target_chapter_chars=chapter_chars,
            accepted_chapter_min_chars=chapter_chars - accepted_delta,
            accepted_chapter_max_chars=chapter_chars + accepted_delta,
            section_target_chars=section_chars,
            ending_direction="公开机制并承担结果。",
            production_status="ready",
        )
    )

    base, remainder = divmod(chapter_count, volume_count)
    volumes: list[VolumeOutline] = []
    chapters: list[ChapterOutline] = []
    chapter_ordinal = 1
    for volume_ordinal in range(1, volume_count + 1):
        owned = base + (1 if volume_ordinal <= remainder else 0)
        volume_id = f"volume_{volume_ordinal:03d}"
        volumes.append(
            VolumeOutline(
                id=volume_id,
                ordinal=volume_ordinal,
                title=f"第{volume_ordinal}卷",
                objective=f"完成第{volume_ordinal}阶段的因果推进",
                opening_state="阶段开始",
                closing_state="阶段闭合",
                target_chapters=owned,
                target_chars=owned * chapter_chars,
            )
        )
        for _ in range(owned):
            chapters.append(
                ChapterOutline(
                    id=f"chapter_{chapter_ordinal:04d}",
                    ordinal=chapter_ordinal,
                    volume_id=volume_id,
                    title=f"第{chapter_ordinal}章",
                    objective=f"推进第{chapter_ordinal}个连续目标",
                    target_threads=[MAIN_THREAD_ID],
                    target_chars=chapter_chars,
                )
            )
            chapter_ordinal += 1

    outline_store = BookOutlineStore(str(data_dir))
    outline = outline_store.load()
    outline_store.update(
        BookOutlineUpdate(
            expected_revision=outline.revision,
            logline="守潮人追索一条贯穿全书的记忆因果链。",
            global_arc="发现、追查、选择、承担。",
            volumes=volumes,
            chapters=chapters,
            ending_target="主线按计划闭合。",
            major_turning_points=["确认代价", "公开机制"],
            central_conflict_progression=["怀疑", "求证", "承担"],
            thread_schedule={MAIN_THREAD_ID: [chapter.id for chapter in chapters]},
            status="ready",
        )
    )

    thread_store = StoryThreadStore(str(data_dir))
    with thread_store.lock:
        repository = thread_store.load()
        thread_store.save(
            StoryThreadRepository(
                revision=repository.revision + 1,
                threads={
                    MAIN_THREAD_ID: StoryThread(
                        id=MAIN_THREAD_ID,
                        type="mystery",
                        description="贯穿整书的遗忘机制主线",
                        promised_question="谁维持了遗忘机制？",
                        status="open",
                        target_start_revision=1,
                        target_end_revision=1
                        + chapter_count * sections_per_chapter,
                        opened_at_revision=1,
                    )
                },
            )
        )


def _new_service(
    data_dir: Path,
    runner: RecordedSectionRunner,
    crash_once: CrashOnce,
    owner_id: str,
) -> WholeBookProductionService:
    return WholeBookProductionService(
        user_id="recorded_user",
        novel_id="recorded_long_novel",
        data_dir=str(data_dir),
        section_runner=runner,
        owner_id=owner_id,
        lease_seconds=0,
        fault_injector=crash_once,
    )


def _start(service: WholeBookProductionService):
    spec = service.specs.load()
    outline = service.outlines.load()
    return service.start(
        expected_spec_revision=spec.revision,
        expected_outline_revision=outline.revision,
    )


def _activate_custom_style(
    service: WholeBookProductionService,
    *,
    applies_from_chapter_ordinal: int,
) -> str:
    custom = service.styles.create(
        StyleProfileCreate(
            name="录制冷潮自定义",
            base_preset_key="noir_cold",
            narrative_voice="有限第三人称",
            sentence_length_tendency="短句与中句交替",
            paragraph_density="中等",
            pacing="逐段收紧",
            derived_style_anchors=["物件先于判断", "停顿后推进动作"],
            deterministic_rules=["不得改变事实或章节长度契约"],
        ),
        profile_id=CUSTOM_STYLE_ID,
    )
    active = service.active_styles.load()
    service.active_styles.activate(
        custom,
        applies_from_chapter_ordinal=applies_from_chapter_ordinal,
        expected_revision=active.revision,
    )
    spec = service.specs.load()
    service.specs.update(
        NovelProductionSpecUpdate(
            expected_revision=spec.revision,
            active_style_profile_id=custom.id,
        )
    )
    return custom.id


def _build_manuscript(chapters) -> str:
    blocks: list[str] = []
    for chapter in chapters:
        blocks.append(
            f"第{chapter.chapter_ordinal:04d}章 {chapter.title}\n\n"
            f"{chapter.manuscript_text()}"
        )
    return "\n\n".join(blocks).rstrip() + "\n"


def _chapter_evidence(chapters) -> list[dict[str, Any]]:
    return [
        {
            "chapter_id": chapter.chapter_id,
            "ordinal": chapter.chapter_ordinal,
            "status": chapter.status,
            "char_count": chapter.char_count,
            "section_count": len(chapter.sections),
            "canonical_revision_start": chapter.canonical_revision_start,
            "canonical_revision_end": chapter.canonical_revision_end,
            "style_profile_id": chapter.style_profile.id,
            "style_revision": chapter.style_profile.revision,
            "style_prompt_hash": chapter.style_profile.prompt_hash,
            "section_artifacts": [
                {
                    "section_id": section.id,
                    "ordinal": section.ordinal,
                    "transaction_id": section.transaction_id,
                    "attempt_number": section.attempt_number,
                    "char_count": section.char_count,
                    "canonical_revision": section.canonical_revision,
                    "content_sha256": _sha256_bytes(
                        section.content.encode("utf-8")
                    ),
                }
                for section in chapter.sections
            ],
        }
        for chapter in chapters
    ]


def _attempt_evidence(attempts) -> list[dict[str, Any]]:
    return [
        {
            "attempt_id": attempt.id,
            "chapter_id": attempt.chapter_id,
            "chapter_ordinal": attempt.chapter_ordinal,
            "section_id": attempt.section_id,
            "section_ordinal": attempt.section_ordinal,
            "attempt_number": attempt.attempt_number,
            "transaction_id": attempt.transaction_id,
            "status": attempt.status,
            "canonical_revision_after": attempt.canonical_revision_after,
            "style_profile_id": attempt.snapshot.style_profile.id,
            "style_revision": attempt.snapshot.style_profile.revision,
            "style_prompt_hash": attempt.snapshot.style_profile.prompt_hash,
            "error_code": attempt.error_code,
        }
        for attempt in attempts
    ]


async def run_recorded_smoke(
    output_dir: Path,
    *,
    chapter_count: int = DEFAULT_CHAPTER_COUNT,
    sections_per_chapter: int = DEFAULT_SECTIONS_PER_CHAPTER,
) -> dict[str, Any]:
    """Run the recorded acceptance and atomically publish its artifacts."""

    if chapter_count < 3:
        raise ValueError("chapter_count must be at least 3")
    if sections_per_chapter < 2:
        raise ValueError("sections_per_chapter must be at least 2")
    output, data_dir = _prepare_output_dir(output_dir)
    started_at = time.perf_counter()
    _configure_book(
        data_dir,
        chapter_count=chapter_count,
        sections_per_chapter=sections_per_chapter,
    )

    failure_slot = (2, 2)
    crash_slot = (3, 1)
    runner = RecordedSectionRunner(data_dir, fail_once_for=failure_slot)
    crash_once = CrashOnce(crash_slot)
    owner_ids: list[str] = []

    def reconstruct_service() -> WholeBookProductionService:
        owner_id = f"recorded_owner_{len(owner_ids):02d}"
        owner_ids.append(owner_id)
        return _new_service(data_dir, runner, crash_once, owner_id)

    service = reconstruct_service()
    started = _start(service)
    duplicate_start = _start(service)
    if not duplicate_start.existing or duplicate_start.job.id != started.job.id:
        raise AssertionError("duplicate production start created a second job")
    job = started.job

    total_sections = chapter_count * sections_per_chapter
    pause_thresholds = [1, max(3, total_sections // 2)]
    paused_thresholds: set[int] = set()
    pause_cycles: list[dict[str, Any]] = []
    crash_restarts = 0
    retry_evidence: dict[str, Any] | None = None
    style_after_chapter = max(1, chapter_count // 2)
    custom_style_id = ""
    style_activation_count = 0
    guard = 0

    while True:
        guard += 1
        if guard > total_sections * 6 + 50:
            raise AssertionError("recorded smoke exceeded its deterministic loop guard")
        job = service.get_job(job.id)
        if job.status == "completed":
            break
        if job.status == "failed":
            failed_attempts = [
                attempt
                for attempt in service.attempts.list_all(job_id=job.id)
                if attempt.status in {"failed", "rejected"}
            ]
            if retry_evidence is not None or len(failed_attempts) != 1:
                raise AssertionError("unexpected recorded failure cardinality")
            failed_attempt = failed_attempts[0]
            retry_evidence = {
                "chapter_id": failed_attempt.chapter_id,
                "section_id": failed_attempt.section_id,
                "failed_attempt_id": failed_attempt.id,
                "failed_attempt_number": failed_attempt.attempt_number,
                "failed_transaction_id": failed_attempt.transaction_id,
                "failed_status": failed_attempt.status,
                "failed_content_retained": bool(failed_attempt.committed_content),
            }
            job = service.retry_failed(
                job.id,
                expected_revision=job.revision,
            )

        try:
            job = await service.run(job.id, max_sections=1)
        except InjectedProductionCrash:
            crash_restarts += 1
            service = reconstruct_service()
            continue

        if job.status == "failed":
            continue
        committed_attempt_count = len(
            [
                attempt
                for attempt in service.attempts.list_all(job_id=job.id)
                if attempt.status == "committed"
            ]
        )
        completed_chapter_count = len(job.completed_chapter_ids)

        if (
            not custom_style_id
            and completed_chapter_count >= style_after_chapter
        ):
            custom_style_id = _activate_custom_style(
                service,
                applies_from_chapter_ordinal=style_after_chapter + 1,
            )
            style_activation_count += 1

        for threshold in pause_thresholds:
            if (
                threshold not in paused_thresholds
                and committed_attempt_count >= threshold
                and job.status == "running"
            ):
                requested = service.pause(
                    job.id,
                    expected_revision=job.revision,
                )
                paused = await service.run(requested.id, max_sections=1)
                if paused.status != "paused":
                    raise AssertionError("pause was not applied at a safe boundary")
                service = reconstruct_service()
                resumed = service.resume(
                    paused.id,
                    expected_revision=paused.revision,
                )
                pause_cycles.append(
                    {
                        "threshold": threshold,
                        "paused_revision": paused.revision,
                        "resumed_revision": resumed.revision,
                        "owner_after_resume": owner_ids[-1],
                    }
                )
                paused_thresholds.add(threshold)
                job = resumed
                break

    elapsed_seconds = time.perf_counter() - started_at
    chapters = service.list_chapters(committed_only=True)
    attempts = ProductionSectionAttemptStore(str(data_dir)).list_all(job_id=job.id)
    events = ProductionEventStore(str(data_dir)).after(job.id)
    final_state = CanonicalStateStore(str(data_dir)).load()
    final_threads = StoryThreadStore(str(data_dir)).load()
    spec = service.specs.load()

    if retry_evidence is None:
        raise AssertionError("controlled failure did not occur")
    retried_slot = [
        attempt
        for attempt in attempts
        if (
            attempt.chapter_id == retry_evidence["chapter_id"]
            and attempt.section_id == retry_evidence["section_id"]
        )
    ]
    retry_evidence.update(
        {
            "attempt_count": len(retried_slot),
            "attempt_numbers": [
                attempt.attempt_number for attempt in retried_slot
            ],
            "transaction_ids": [
                attempt.transaction_id for attempt in retried_slot
            ],
            "final_statuses": [attempt.status for attempt in retried_slot],
            "new_attempt": len({attempt.id for attempt in retried_slot}) == 2,
            "new_transaction": (
                len({attempt.transaction_id for attempt in retried_slot}) == 2
            ),
        }
    )

    committed_sections = [
        section
        for chapter in chapters
        for section in chapter.sections
    ]
    section_ids = [section.id for section in committed_sections]
    transaction_ids = [
        section.transaction_id for section in committed_sections
    ]
    canonical_revisions = [
        section.canonical_revision for section in committed_sections
    ]
    expected_canonical_revisions = list(
        range(
            job.requested_canonical_revision + 1,
            job.requested_canonical_revision + len(committed_sections) + 1,
        )
    )
    chapter_ordinals = [chapter.chapter_ordinal for chapter in chapters]
    planned_total_chars = spec.target_total_chars
    actual_total_chars = sum(chapter.char_count for chapter in chapters)
    total_deviation_ratio = (
        abs(actual_total_chars - planned_total_chars) / planned_total_chars
    )
    chapters_in_range = [
        chapter
        for chapter in chapters
        if (
            spec.accepted_chapter_min_chars
            <= chapter.char_count
            <= spec.accepted_chapter_max_chars
        )
    ]
    chapter_range_ratio = len(chapters_in_range) / chapter_count
    initial_style_id = job.requested_style_profile_id

    style_snapshot_mismatch_count = 0
    for chapter in chapters:
        expected_style_id = (
            initial_style_id
            if chapter.chapter_ordinal <= style_after_chapter
            else custom_style_id
        )
        if chapter.style_profile.id != expected_style_id:
            style_snapshot_mismatch_count += 1
        chapter_attempts = [
            attempt
            for attempt in attempts
            if attempt.chapter_id == chapter.chapter_id
        ]
        style_snapshot_mismatch_count += sum(
            1
            for attempt in chapter_attempts
            if (
                attempt.snapshot.style_profile.id
                != chapter.style_profile.id
                or attempt.snapshot.style_profile.prompt_hash
                != chapter.style_profile.prompt_hash
            )
        )

    manuscript = _build_manuscript(chapters)
    sentinel_occurrences = sum(
        manuscript.count(sentinel)
        for sentinel in (FAILURE_SENTINEL, REJECTED_SENTINEL)
    )
    noncommitted_prose_count = sum(
        1
        for attempt in attempts
        if attempt.status != "committed" and attempt.committed_content
    )
    rejected_prose_count = sentinel_occurrences + noncommitted_prose_count
    final_thread = final_threads.threads.get(MAIN_THREAD_ID)
    final_thread_liveness_violations = int(
        final_thread is None
        or final_thread.last_advanced_revision != final_state.revision
    )
    thread_liveness_violation_count = (
        runner.thread_liveness_violation_count
        + final_thread_liveness_violations
    )
    event_dedupe_keys = [
        event.dedupe_key for event in events if event.dedupe_key
    ]

    metrics = {
        "chapter_count": len(chapters),
        "section_count": len(committed_sections),
        "minimum_sections_per_chapter": min(
            (len(chapter.sections) for chapter in chapters),
            default=0,
        ),
        "service_owner_count": len(owner_ids),
        "service_restart_count": len(owner_ids) - 1,
        "pause_resume_count": len(pause_cycles),
        "crash_restart_count": crash_restarts,
        "retry_count": job.retry_count,
        "style_activation_count": style_activation_count,
        "duplicate_section_count": len(section_ids) - len(set(section_ids)),
        "duplicate_transaction_count": (
            len(transaction_ids) - len(set(transaction_ids))
        ),
        "recovery_duplicate_count": runner.duplicate_commit_count,
        "replay_call_count": runner.replay_call_count,
        "hard_fact_bad_commit_count": runner.hard_fact_bad_commit_count,
        "state_bad_commit_count": runner.state_bad_commit_count,
        "thread_bad_commit_count": runner.thread_bad_commit_count,
        "rejected_prose_count": rejected_prose_count,
        "thread_liveness_violation_count": thread_liveness_violation_count,
        "style_snapshot_mismatch_count": style_snapshot_mismatch_count,
        "planned_total_chars": planned_total_chars,
        "actual_total_chars": actual_total_chars,
        "planned_total_deviation_ratio": total_deviation_ratio,
        "chapters_in_range": len(chapters_in_range),
        "chapter_range_ratio": chapter_range_ratio,
        "canonical_revision_initial": job.requested_canonical_revision,
        "canonical_revision_final": final_state.revision,
        "provider_calls": 0,
        "network_calls": 0,
        "elapsed_seconds": round(elapsed_seconds, 3),
    }
    gates = {
        "job_completed": job.status == "completed",
        "chapter_count_exact": len(chapters) == chapter_count,
        "at_least_two_sections_per_chapter": all(
            len(chapter.sections) >= 2 for chapter in chapters
        ),
        "service_restarts_at_least_three": len(owner_ids) - 1 >= 3,
        "pause_resume_at_least_two": len(pause_cycles) >= 2,
        "crash_recovery_exercised": (
            crash_once.triggered
            and crash_restarts == 1
            and runner.replay_call_count >= 1
        ),
        "retry_created_new_attempt": bool(retry_evidence["new_attempt"]),
        "retry_created_new_transaction": bool(
            retry_evidence["new_transaction"]
        ),
        "custom_style_activated_once": (
            style_activation_count == 1 and bool(custom_style_id)
        ),
        "custom_style_only_from_next_chapter": (
            style_snapshot_mismatch_count == 0
        ),
        "duplicate_sections_zero": len(section_ids) == len(set(section_ids)),
        "duplicate_transactions_zero": (
            len(transaction_ids) == len(set(transaction_ids))
        ),
        "canonical_revision_contiguous": (
            canonical_revisions == expected_canonical_revisions
            and final_state.revision
            == job.requested_canonical_revision + total_sections
        ),
        "chapter_order_contiguous": chapter_ordinals
        == list(range(1, chapter_count + 1)),
        "hard_fact_bad_commits_zero": runner.hard_fact_bad_commit_count == 0,
        "state_bad_commits_zero": runner.state_bad_commit_count == 0,
        "thread_bad_commits_zero": runner.thread_bad_commit_count == 0,
        "recovery_duplicates_zero": runner.duplicate_commit_count == 0,
        "rejected_prose_zero": rejected_prose_count == 0,
        "planned_total_deviation_within_ten_percent": (
            total_deviation_ratio <= 0.10
        ),
        "chapter_range_rate_at_least_95_percent": chapter_range_ratio >= 0.95,
        "thread_liveness_violations_zero": (
            thread_liveness_violation_count == 0
        ),
        "style_snapshot_mismatches_zero": (
            style_snapshot_mismatch_count == 0
        ),
        "event_sequences_contiguous": [
            event.sequence for event in events
        ]
        == list(range(1, len(events) + 1)),
        "event_dedupe_keys_unique": len(event_dedupe_keys)
        == len(set(event_dedupe_keys)),
        "provider_calls_zero": True,
    }
    failed_gates = sorted(name for name, passed in gates.items() if not passed)
    if failed_gates:
        raise AssertionError(
            "recorded long-novel gates failed: " + ", ".join(failed_gates)
        )

    manuscript_path = output / "manuscript.txt"
    evidence_path = output / "evidence.json"
    summary_path = output / "summary.json"
    _atomic_write(manuscript_path, manuscript.encode("utf-8"))

    authority_hashes = {
        name: _sha256_file(data_dir / name)
        for name in (
            "production_spec.json",
            "book_outline.json",
            "story_bible.json",
            "canonical_state.json",
            "story_threads.json",
            "active_style.json",
            "style_profiles.json",
        )
    }
    evidence = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "evidence_source": "deterministic_recorded_section_runner",
        "literary_quality_claimed": False,
        "provider_calls": 0,
        "network_calls": 0,
        "configuration": {
            "chapter_count": chapter_count,
            "sections_per_chapter": sections_per_chapter,
            "style_applies_after_chapter": style_after_chapter,
            "failure_slot": list(failure_slot),
            "crash_slot": list(crash_slot),
        },
        "job": {
            "job_id": job.id,
            "status": job.status,
            "revision": job.revision,
            "requested_spec_revision": job.requested_spec_revision,
            "requested_outline_revision": job.requested_outline_revision,
            "requested_style_profile_id": job.requested_style_profile_id,
            "requested_style_revision": job.requested_style_revision,
            "requested_style_prompt_hash": job.requested_style_prompt_hash,
            "retry_count": job.retry_count,
        },
        "service_owners": owner_ids,
        "pause_cycles": pause_cycles,
        "retry": retry_evidence,
        "style_transition": {
            "initial_style_profile_id": initial_style_id,
            "custom_style_profile_id": custom_style_id,
            "applies_from_chapter_ordinal": style_after_chapter + 1,
        },
        "metrics": metrics,
        "gates": gates,
        "chapters": _chapter_evidence(chapters),
        "attempts": _attempt_evidence(attempts),
        "event_type_distribution": dict(
            sorted(Counter(event.type for event in events).items())
        ),
        "authority_sha256": authority_hashes,
        "manuscript": {
            "filename": manuscript_path.name,
            "sha256": _sha256_file(manuscript_path),
            "bytes": manuscript_path.stat().st_size,
            "contains_only_committed_chapters": True,
        },
    }
    evidence_bytes = _stable_json_bytes(evidence)
    if any(
        sentinel.encode("utf-8") in evidence_bytes
        for sentinel in (FAILURE_SENTINEL, REJECTED_SENTINEL)
    ):
        raise AssertionError("failure sentinel leaked into public evidence")
    _atomic_write(evidence_path, evidence_bytes)

    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "ok": True,
        "evidence_source": evidence["evidence_source"],
        "literary_quality_claimed": False,
        "provider_calls": 0,
        "network_calls": 0,
        "job_status": job.status,
        "metrics": metrics,
        "gates": gates,
        "artifacts": {
            "manuscript.txt": {
                "sha256": _sha256_file(manuscript_path),
                "bytes": manuscript_path.stat().st_size,
            },
            "evidence.json": {
                "sha256": _sha256_file(evidence_path),
                "bytes": evidence_path.stat().st_size,
            },
        },
    }
    summary_bytes = _stable_json_bytes(summary)
    if any(
        section.content.encode("utf-8") in summary_bytes
        for section in committed_sections
    ):
        raise AssertionError("manuscript prose leaked into summary")
    _atomic_write(summary_path, summary_bytes)
    return {
        **summary,
        "output_dir": str(output),
        "summary_sha256": _sha256_file(summary_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Exclusive artifact directory; the run fails if it already exists.",
    )
    parser.add_argument(
        "--chapters",
        type=int,
        default=DEFAULT_CHAPTER_COUNT,
    )
    parser.add_argument(
        "--sections-per-chapter",
        type=int,
        default=DEFAULT_SECTIONS_PER_CHAPTER,
    )
    return parser


def _run_in_isolated_loop(awaitable):
    """Run CLI work without replacing a caller's current event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(awaitable)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())
        loop.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _run_in_isolated_loop(
            run_recorded_smoke(
                args.output_dir,
                chapter_count=args.chapters,
                sections_per_chapter=args.sections_per_chapter,
            )
        )
    except (AssertionError, FileExistsError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "output_dir": result["output_dir"],
                "summary_sha256": result["summary_sha256"],
                "chapter_count": result["metrics"]["chapter_count"],
                "section_count": result["metrics"]["section_count"],
                "elapsed_seconds": result["metrics"]["elapsed_seconds"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
