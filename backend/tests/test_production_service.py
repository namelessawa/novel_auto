from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest

from story.persistence import CanonicalStateStore
from story.production_models import (
    BookOutlineUpdate,
    ChapterOutline,
    NovelProductionSpecUpdate,
    StyleProfileCreate,
    VolumeOutline,
)
from story.production_persistence import (
    BookOutlineStore,
    ProductionSectionAttemptStore,
    ProductionSpecStore,
    ensure_production_domain,
)
from story.production_service import (
    InjectedProductionCrash,
    SectionRunRequest,
    SectionRunResult,
    WholeBookProductionService,
)


class RecordedSectionRunner:
    """Idempotent committed-section stand-in for restart tests."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = str(data_dir)
        self.results: dict[str, SectionRunResult] = {}
        self.calls: list[str] = []
        self.commit_count = 0
        self.fail_once_for: set[tuple[int, int]] = set()
        self.failed_slots: set[tuple[int, int]] = set()
        self.on_commit: Callable[[SectionRunRequest], None] | None = None

    async def run_section(self, request: SectionRunRequest) -> SectionRunResult:
        self.calls.append(request.transaction_id)
        existing = self.results.get(request.transaction_id)
        if existing is not None:
            return existing
        slot = (
            request.snapshot.chapter_outline.ordinal,
            request.snapshot.section_ordinal,
        )
        if slot in self.fail_once_for and slot not in self.failed_slots:
            self.failed_slots.add(slot)
            raise RuntimeError("recorded provider failure")

        states = CanonicalStateStore(self.data_dir)
        current = states.load()
        assert current.revision == request.snapshot.canonical_state_revision
        updated = current.model_copy(
            update={
                "revision": current.revision + 1,
                "world_time": current.world_time + 1,
            }
        )
        states.save_next(updated, expected_revision=current.revision)
        content = "潮" * request.snapshot.section_target_chars
        result = SectionRunResult(
            transaction_id=request.transaction_id,
            section_id=request.section_id,
            committed=True,
            content=content,
            summary=(
                f"第{request.snapshot.chapter_outline.ordinal}章"
                f"第{request.snapshot.section_ordinal}节"
            ),
            char_count=len(content),
            canonical_revision_after=updated.revision,
            story_bible_revision=request.snapshot.story_bible_revision,
            validation_passed=True,
            repair_performed=request.snapshot.section_ordinal == 2,
            prompt_tokens=11,
            completion_tokens=17,
            latency_ms=23,
        )
        self.results[request.transaction_id] = result
        self.commit_count += 1
        if self.on_commit is not None:
            self.on_commit(request)
        return result


def _configure_book(
    tmp_path: Path,
    *,
    chapter_count: int,
    volume_count: int,
) -> None:
    ensure_production_domain(str(tmp_path), title="潮汐之城")
    spec_store = ProductionSpecStore(
        str(tmp_path),
        lambda: (_ for _ in ()).throw(AssertionError("spec must exist")),
    )
    spec = spec_store.load()
    spec_store.update(
        NovelProductionSpecUpdate(
            expected_revision=spec.revision,
            target_total_chars=chapter_count * 1_000,
            volume_count=volume_count,
            chapter_count=chapter_count,
            target_chapter_chars=1_000,
            accepted_chapter_min_chars=1_000,
            accepted_chapter_max_chars=1_000,
            section_target_chars=500,
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
                objective=f"完成第{volume_ordinal}阶段",
                opening_state="阶段开始",
                closing_state="阶段闭合",
                target_chapters=owned,
                target_chars=owned * 1_000,
            )
        )
        for _ in range(owned):
            chapters.append(
                ChapterOutline(
                    id=f"chapter_{chapter_ordinal:04d}",
                    ordinal=chapter_ordinal,
                    volume_id=volume_id,
                    title=f"第{chapter_ordinal}章",
                    objective=f"推进第{chapter_ordinal}个目标",
                    target_chars=1_000,
                )
            )
            chapter_ordinal += 1

    outline_store = BookOutlineStore(str(tmp_path))
    outline = outline_store.load()
    outline_store.update(
        BookOutlineUpdate(
            expected_revision=outline.revision,
            logline="城市用遗忘换取潮汐平静。",
            global_arc="发现、追查、承担。",
            volumes=volumes,
            chapters=chapters,
            ending_target="公开真相并承担代价。",
            status="ready",
        )
    )


def _service(
    tmp_path: Path,
    runner: RecordedSectionRunner,
    *,
    owner_id: str,
    fault=None,
) -> WholeBookProductionService:
    return WholeBookProductionService(
        user_id="user_1",
        novel_id="novel_tide",
        data_dir=str(tmp_path),
        section_runner=runner,
        owner_id=owner_id,
        lease_seconds=0,
        fault_injector=fault,
    )


def _start(service: WholeBookProductionService):
    spec = service.specs.load()
    outline = service.outlines.load()
    return service.start(
        expected_spec_revision=spec.revision,
        expected_outline_revision=outline.revision,
    )


@pytest.mark.asyncio
async def test_thirty_chapters_are_serial_and_resume_across_three_restarts(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path, chapter_count=30, volume_count=3)
    runner = RecordedSectionRunner(tmp_path)
    service = _service(tmp_path, runner, owner_id="worker_0")
    started = _start(service)
    duplicate = _start(service)
    assert started.existing is False
    assert duplicate.existing is True
    assert duplicate.job.id == started.job.id

    job = started.job
    started_at = time.perf_counter()
    for restart in range(4):
        service = _service(
            tmp_path,
            runner,
            owner_id=f"worker_{restart}",
        )
        job = await service.run(job.id, max_sections=15)
    elapsed = time.perf_counter() - started_at

    assert job.status == "completed"
    assert elapsed < 60
    assert runner.commit_count == 60
    assert len(set(runner.results)) == 60
    assert CanonicalStateStore(str(tmp_path)).load().revision == 61
    chapters = service.list_chapters()
    assert len(chapters) == 30
    assert all(len(chapter.sections) == 2 for chapter in chapters)
    assert all(chapter.char_count == 1_000 for chapter in chapters)
    assert len(
        {
            section.transaction_id
            for chapter in chapters
            for section in chapter.sections
        }
    ) == 60
    assert job.prompt_tokens_total == 60 * 11
    assert job.completion_tokens_total == 60 * 17
    assert job.repair_total == 30
    attempts = ProductionSectionAttemptStore(str(tmp_path)).list_all(job_id=job.id)
    assert all(attempt.snapshot.book_outline is None for attempt in attempts)
    assert all(
        attempt.snapshot.outline_revision == job.requested_outline_revision
        for attempt in attempts
    )
    chapter_bytes = {
        path.name: path.read_bytes()
        for path in (tmp_path / "production_chapters").glob("*.json")
    }
    repeated = _start(service)
    assert repeated.existing is True
    assert repeated.job.id == job.id
    assert {
        path.name: path.read_bytes()
        for path in (tmp_path / "production_chapters").glob("*.json")
    } == chapter_bytes


@pytest.mark.asyncio
async def test_pause_is_applied_after_commit_and_resume_does_not_duplicate(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path, chapter_count=2, volume_count=1)
    runner = RecordedSectionRunner(tmp_path)
    service = _service(tmp_path, runner, owner_id="pause_worker")
    job = _start(service).job

    def request_pause(_: SectionRunRequest) -> None:
        current = service.get_job(job.id)
        service.pause(job.id, expected_revision=current.revision)
        runner.on_commit = None

    runner.on_commit = request_pause
    paused = await service.run(job.id)
    assert paused.status == "paused"
    assert runner.commit_count == 1
    assert CanonicalStateStore(str(tmp_path)).load().revision == 2

    resumed = service.resume(job.id, expected_revision=paused.revision)
    finished = await service.run(resumed.id)
    assert finished.status == "completed"
    assert runner.commit_count == 4
    assert len(set(runner.results)) == 4
    assert CanonicalStateStore(str(tmp_path)).load().revision == 5


@pytest.mark.asyncio
async def test_cancel_at_safe_boundary_preserves_committed_section(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path, chapter_count=2, volume_count=1)
    runner = RecordedSectionRunner(tmp_path)
    service = _service(tmp_path, runner, owner_id="cancel_worker")
    job = _start(service).job

    def request_cancel(_: SectionRunRequest) -> None:
        current = service.get_job(job.id)
        service.cancel(job.id, expected_revision=current.revision)
        runner.on_commit = None

    runner.on_commit = request_cancel
    cancelled = await service.run(job.id)
    assert cancelled.status == "cancelled"
    assert runner.commit_count == 1
    partial = service.list_chapters(committed_only=False)[0]
    assert partial.status == "generating"
    assert len(partial.sections) == 1
    assert service.list_chapters(committed_only=True) == []
    assert CanonicalStateStore(str(tmp_path)).load().revision == 2


@pytest.mark.asyncio
async def test_failed_section_retry_uses_new_attempt_and_transaction(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path, chapter_count=1, volume_count=1)
    runner = RecordedSectionRunner(tmp_path)
    runner.fail_once_for.add((1, 1))
    service = _service(tmp_path, runner, owner_id="retry_worker")
    job = _start(service).job

    failed = await service.run(job.id)
    assert failed.status == "failed"
    assert failed.failed_chapter_id == "chapter_0001"
    assert CanonicalStateStore(str(tmp_path)).load().revision == 1
    first_attempt = ProductionSectionAttemptStore(str(tmp_path)).list_all(
        job_id=job.id
    )[0]
    assert first_attempt.status == "failed"
    assert first_attempt.committed_content == ""

    retried = service.retry_failed(job.id, expected_revision=failed.revision)
    completed = await service.run(retried.id)
    assert completed.status == "completed"
    attempts = ProductionSectionAttemptStore(str(tmp_path)).list_all(job_id=job.id)
    same_slot = [item for item in attempts if item.section_ordinal == 1]
    assert [item.attempt_number for item in same_slot] == [1, 2]
    assert len({item.transaction_id for item in same_slot}) == 2
    assert same_slot[0].status == "failed"
    assert same_slot[1].status == "committed"
    assert CanonicalStateStore(str(tmp_path)).load().revision == 3


@pytest.mark.asyncio
async def test_crash_after_underlying_commit_replays_same_transaction_once(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path, chapter_count=1, volume_count=1)
    runner = RecordedSectionRunner(tmp_path)
    crashed = False

    def crash_once(phase, _attempt, _result) -> None:
        nonlocal crashed
        if phase == "after_runner_commit" and not crashed:
            crashed = True
            raise InjectedProductionCrash()

    service = _service(
        tmp_path,
        runner,
        owner_id="crashed_worker",
        fault=crash_once,
    )
    job = _start(service).job
    with pytest.raises(InjectedProductionCrash):
        await service.run(job.id)
    assert runner.commit_count == 1
    assert CanonicalStateStore(str(tmp_path)).load().revision == 2
    inflight = ProductionSectionAttemptStore(str(tmp_path)).inflight(job.id)
    assert inflight is not None

    recovered_service = _service(
        tmp_path,
        runner,
        owner_id="recovery_worker",
    )
    recovered = await recovered_service.run(job.id)
    assert recovered.status == "completed"
    assert runner.commit_count == 2
    assert len(runner.calls) == 3
    assert runner.calls[0] == runner.calls[1]
    assert CanonicalStateStore(str(tmp_path)).load().revision == 3
    assert ProductionSectionAttemptStore(str(tmp_path)).inflight(job.id) is None


@pytest.mark.asyncio
async def test_style_activation_only_changes_the_next_chapter_snapshot(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path, chapter_count=2, volume_count=1)
    runner = RecordedSectionRunner(tmp_path)
    service = _service(tmp_path, runner, owner_id="style_worker")
    job = _start(service).job
    halfway = await service.run(job.id, max_sections=2)
    assert halfway.status == "running"
    first = service.get_chapter("chapter_0001")

    custom = service.styles.create(
        StyleProfileCreate(
            name="冷潮自定义",
            base_preset_key="noir_cold",
            narrative_voice="有限第三人称",
            pacing="快速收紧",
            derived_style_anchors=["物件先于判断"],
        ),
        profile_id="style_next_chapter",
    )
    active = service.active_styles.load()
    service.active_styles.activate(
        custom,
        applies_from_chapter_ordinal=2,
        expected_revision=active.revision,
    )
    finished = await service.run(halfway.id)
    second = service.get_chapter("chapter_0002")

    assert finished.status == "completed"
    assert first.style_profile.id != custom.id
    assert second.style_profile.id == custom.id
    assert second.style_profile.prompt_hash == custom.prompt_hash
    first_attempts = ProductionSectionAttemptStore(str(tmp_path)).list_all(
        job_id=job.id,
        chapter_id="chapter_0001",
    )
    second_attempts = ProductionSectionAttemptStore(str(tmp_path)).list_all(
        job_id=job.id,
        chapter_id="chapter_0002",
    )
    assert all(
        item.snapshot.style_profile.id == first.style_profile.id
        for item in first_attempts
    )
    assert all(
        item.snapshot.style_profile.id == custom.id
        for item in second_attempts
    )


@pytest.mark.asyncio
async def test_outline_revision_change_fails_before_any_section_commit(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path, chapter_count=1, volume_count=1)
    runner = RecordedSectionRunner(tmp_path)
    service = _service(tmp_path, runner, owner_id="stale_worker")
    job = _start(service).job
    outline = service.outlines.load()
    service.outlines.update(
        BookOutlineUpdate(
            expected_revision=outline.revision,
            logline="并发改写后的梗概",
        )
    )

    failed = await service.run(job.id)
    assert failed.status == "failed"
    assert runner.commit_count == 0
    assert CanonicalStateStore(str(tmp_path)).load().revision == 1
