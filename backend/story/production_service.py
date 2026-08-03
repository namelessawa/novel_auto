"""Durable serial coordinator for whole-book author production.

This layer deliberately owns no prose generation logic.  A ``SectionRunner``
receives a completely frozen request and must return only a formally committed
section.  The production coordinator journals the attempt before invoking the
runner, so a restart can replay the same transaction ID without duplicating a
Canon commit.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from pydantic import Field, model_validator

from nf_core.provider_runtime import ProviderConfigurationError, ProviderError
from story.models import (
    CanonicalState,
    MemoryRecord,
    MemoryRepositoryState,
    SectionGoal,
    StoryBible,
    StoryThreadRepository,
    utc_now,
)
from story.narrative_contract import LengthConstraint, NarrativeContractInput
from story.persistence import (
    CanonicalStateStore,
    MemoryRepository,
    RevisionConflict,
    StoryBibleStore,
    StoryThreadStore,
)
from story.production_models import (
    BookOutline,
    ChapterOutline,
    CommittedProductionSection,
    GenerationJob,
    NovelProductionSpec,
    ProductionChapterRecord,
    ProductionContextSnapshot,
    ProductionModel,
    ProductionSectionAttempt,
    ProductionStartOutcome,
    StyleProfile,
    non_whitespace_char_count,
)
from story.production_persistence import (
    ActiveStyleStore,
    BookOutlineStore,
    GenerationJobStore,
    ProductionChapterStore,
    ProductionEventStore,
    ProductionSectionAttemptStore,
    ProductionSpecStore,
    StyleProfileStore,
    ensure_production_domain,
)


class ProductionServiceError(RuntimeError):
    pass


class ProductionLeaseConflict(ProductionServiceError):
    pass


class StaleProductionContract(ProductionServiceError):
    pass


class SectionCommitPending(ProductionServiceError):
    """The underlying journal may have committed; replay the same attempt."""


class InjectedProductionCrash(BaseException):
    """Test-only process-death signal deliberately not caught by the service."""


class SectionRunResult(ProductionModel):
    transaction_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    committed: bool = False
    content: str = ""
    summary: str = ""
    char_count: int = Field(default=0, ge=0)
    canonical_revision_after: int = Field(default=0, ge=0)
    story_bible_revision: int = Field(default=0, ge=0)
    validation_passed: bool = False
    repair_performed: bool = False
    provider: str = ""
    provider_model: str = ""
    provider_source: str = ""
    provider_config_fingerprint: str = ""
    provider_config_fingerprints: list[str] = Field(default_factory=list)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    error_code: str = ""

    @model_validator(mode="after")
    def _committed_result_is_self_consistent(self) -> "SectionRunResult":
        if self.committed:
            if not self.content or not self.validation_passed:
                raise ValueError("committed result requires validated content")
            if self.char_count != non_whitespace_char_count(self.content):
                raise ValueError("section result char_count does not match content")
            if self.canonical_revision_after < 1 or self.story_bible_revision < 1:
                raise ValueError("committed result requires authority revisions")
        elif self.content:
            raise ValueError("uncommitted result cannot expose candidate prose")
        return self


class SectionRunRequest(ProductionModel):
    transaction_id: str = Field(min_length=1)
    section_id: str = Field(min_length=1)
    goal: SectionGoal
    snapshot: ProductionContextSnapshot


class SectionRunner(Protocol):
    async def run_section(self, request: SectionRunRequest) -> SectionRunResult: ...


FaultInjector = Callable[
    [str, ProductionSectionAttempt, SectionRunResult | None],
    None,
]


@dataclass(frozen=True)
class _AuthorityView:
    spec: NovelProductionSpec
    outline: BookOutline
    bible: StoryBible
    state: CanonicalState
    threads: StoryThreadRepository
    memories: MemoryRepositoryState


_RUN_LOCKS: dict[str, asyncio.Lock] = {}
_RUN_LOCKS_GUARD = threading.Lock()
_START_LOCKS: dict[str, threading.RLock] = {}


def _run_lock(data_dir: str) -> asyncio.Lock:
    key = os.path.realpath(data_dir)
    with _RUN_LOCKS_GUARD:
        return _RUN_LOCKS.setdefault(key, asyncio.Lock())


def _start_lock(data_dir: str) -> threading.RLock:
    key = os.path.realpath(data_dir)
    with _RUN_LOCKS_GUARD:
        return _START_LOCKS.setdefault(key, threading.RLock())


def production_boundary_lock(data_dir: str) -> threading.RLock:
    """Shared cross-thread lock for job start and next-chapter contracts."""

    return _start_lock(data_dir)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _distribute(total: int, count: int) -> list[int]:
    quotient, remainder = divmod(total, count)
    return [
        quotient + (1 if index < remainder else 0)
        for index in range(count)
    ]


def _material_spec(spec: NovelProductionSpec) -> dict[str, Any]:
    return spec.model_dump(
        mode="json",
        exclude={
            "revision",
            "active_style_profile_id",
            "production_status",
            "created_at",
            "updated_at",
        },
    )


def _safe_failure(exc: Exception) -> tuple[str, str]:
    code = type(exc).__name__.upper()[:80]
    first_line = str(exc).splitlines()[0][:240] if str(exc) else code
    if re.search(
        r"(?i)(api[_ -]?key|authorization|bearer\s+\S+|\bsk-[A-Za-z0-9_-]+)",
        first_line,
    ):
        first_line = "section runner failed; sensitive detail withheld"
    return code, first_line


class WholeBookProductionService:
    """One durable serial production loop per novel."""

    def __init__(
        self,
        *,
        user_id: str,
        novel_id: str,
        data_dir: str,
        section_runner: SectionRunner,
        title: str = "",
        owner_id: str | None = None,
        lease_seconds: float = 90.0,
        provider_retry_limit: int = 2,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.user_id = user_id
        self.novel_id = novel_id
        self.data_dir = os.path.realpath(os.path.abspath(data_dir))
        required_documents = (
            "production_spec.json",
            "book_outline.json",
            "style_profiles.json",
            "active_style.json",
            "production_migration.json",
        )
        if not all(
            os.path.isfile(os.path.join(self.data_dir, filename))
            for filename in required_documents
        ):
            ensure_production_domain(self.data_dir, title=title)
        self.section_runner = section_runner
        self.owner_id = owner_id or f"worker_{uuid.uuid4().hex[:16]}"
        self.lease_seconds = max(0.0, float(lease_seconds))
        self.provider_retry_limit = max(0, int(provider_retry_limit))
        self.fault_injector = fault_injector
        self.jobs = GenerationJobStore(self.data_dir)
        self.events = ProductionEventStore(self.data_dir)
        self.attempts = ProductionSectionAttemptStore(self.data_dir)
        self.chapters = ProductionChapterStore(self.data_dir)
        self.specs = ProductionSpecStore(
            self.data_dir,
            lambda: (_ for _ in ()).throw(KeyError("production_spec")),
        )
        self.outlines = BookOutlineStore(self.data_dir)
        self.styles = StyleProfileStore(self.data_dir)
        self.active_styles = ActiveStyleStore(
            self.data_dir,
            lambda: (_ for _ in ()).throw(KeyError("active_style")),
        )
        self.bibles = StoryBibleStore(self.data_dir)
        self.states = CanonicalStateStore(self.data_dir)
        self.threads = StoryThreadStore(self.data_dir)
        self.memories = MemoryRepository(self.data_dir)
        self._lock = _run_lock(self.data_dir)

    def start(
        self,
        *,
        expected_spec_revision: int,
        expected_outline_revision: int,
    ) -> ProductionStartOutcome:
        with _start_lock(self.data_dir):
            all_jobs = self.jobs.list_all()
            unfinished = [
                job
                for job in all_jobs
                if job.status not in {"cancelled", "completed"}
            ]
            if unfinished:
                return ProductionStartOutcome(job=unfinished[-1], existing=True)
            completed = [job for job in all_jobs if job.status == "completed"]
            if completed:
                latest = completed[-1]
                if (
                    latest.requested_spec_revision == expected_spec_revision
                    and latest.requested_outline_revision
                    == expected_outline_revision
                ):
                    return ProductionStartOutcome(job=latest, existing=True)
                raise ValueError(
                    "the book is already completed; a new job cannot replace "
                    "committed chapters"
                )

            spec = self.specs.load()
            outline = self.outlines.load()
            if spec.revision != expected_spec_revision:
                raise RevisionConflict(expected_spec_revision, spec.revision)
            if outline.revision != expected_outline_revision:
                raise RevisionConflict(expected_outline_revision, outline.revision)
            if outline.status not in {"ready", "locked"}:
                raise ValueError("book outline must be ready before production starts")
            errors = outline.validation_errors_for(spec)
            if errors:
                raise ValueError("; ".join(errors))
            bible = self.bibles.load()
            publish_errors = bible.publish_errors()
            if publish_errors:
                raise ValueError("StoryBible is not publishable: " + "; ".join(publish_errors))
            state = self.states.load()
            binding = self.active_styles.load()
            style = self._binding_profile(binding)
            job = GenerationJob(
                id=f"job_{uuid.uuid4().hex[:20]}",
                novel_id=self.novel_id,
                status="queued",
                requested_spec_revision=spec.revision,
                requested_outline_revision=outline.revision,
                requested_style_profile_id=style.id,
                requested_style_revision=style.revision,
                requested_style_prompt_hash=style.prompt_hash,
                requested_story_bible_revision=bible.revision,
                requested_canonical_revision=state.revision,
                requested_spec_snapshot=spec,
                requested_style_snapshot=style,
                last_committed_canonical_revision=state.revision,
            )
            job = self.jobs.create(job)
            self.events.append(
                job.id,
                "job_status",
                dedupe_key=f"{job.id}:created",
                payload={"status": job.status, "revision": job.revision},
            )
            return ProductionStartOutcome(job=job, existing=False)

    def get_job(self, job_id: str | None = None) -> GenerationJob:
        if job_id:
            return self.jobs.load(job_id)
        rows = self.jobs.list_all()
        if not rows:
            raise KeyError("no production job")
        return rows[-1]

    def pause(self, job_id: str, *, expected_revision: int) -> GenerationJob:
        job = self.jobs.load(job_id)
        if job.revision != expected_revision:
            raise RevisionConflict(expected_revision, job.revision)
        if job.status == "queued":
            paused = self.jobs.transition(
                job.id,
                expected_revision=job.revision,
                status="paused",
            )
        elif job.status == "running":
            paused = self.jobs.transition(
                job.id,
                expected_revision=job.revision,
                status="pausing",
            )
        elif job.status in {"pausing", "paused"}:
            return job
        else:
            raise ValueError(f"job cannot pause from {job.status}")
        self.events.append(
            job.id,
            "job_status",
            dedupe_key=f"{job.id}:pause:{paused.revision}",
            payload={"status": paused.status, "revision": paused.revision},
        )
        return paused

    def resume(self, job_id: str, *, expected_revision: int) -> GenerationJob:
        job = self.jobs.load(job_id)
        if job.revision != expected_revision:
            raise RevisionConflict(expected_revision, job.revision)
        if job.status != "paused":
            raise ValueError(f"job cannot resume from {job.status}")
        resumed = self.jobs.transition(
            job.id,
            expected_revision=job.revision,
            status="queued",
            updates={
                "lease_owner": "",
                "lease_expiry": "",
                "heartbeat": "",
                "failure_code": "",
                "failure_message": "",
            },
        )
        self.events.append(
            job.id,
            "job_status",
            dedupe_key=f"{job.id}:resume:{resumed.revision}",
            payload={"status": resumed.status, "revision": resumed.revision},
        )
        return resumed

    def cancel(self, job_id: str, *, expected_revision: int) -> GenerationJob:
        job = self.jobs.load(job_id)
        if job.revision != expected_revision:
            raise RevisionConflict(expected_revision, job.revision)
        if job.status in {"cancelled", "completed"}:
            return job
        target = (
            "cancelling"
            if job.status in {"running", "pausing"}
            else "cancelled"
        )
        cancelled = self.jobs.transition(
            job.id,
            expected_revision=job.revision,
            status=target,
            updates={
                "lease_owner": "" if target == "cancelled" else job.lease_owner,
                "lease_expiry": "" if target == "cancelled" else job.lease_expiry,
                "heartbeat": "" if target == "cancelled" else job.heartbeat,
            },
        )
        self.events.append(
            job.id,
            "job_status",
            dedupe_key=f"{job.id}:cancel:{cancelled.revision}",
            payload={"status": cancelled.status, "revision": cancelled.revision},
        )
        return cancelled

    def pause_recoverable(
        self,
        job_id: str,
        *,
        failure_code: str,
        failure_message: str,
    ) -> GenerationJob:
        """Pause an idle driver while retaining an in-flight transaction.

        This is used only after the section runner reports a commit-pending
        condition repeatedly.  Resume must replay the same transaction rather
        than create a second Canon write.
        """

        current = self.jobs.load(job_id)
        if current.status == "paused":
            return current
        if current.status == "running":
            current = self.jobs.transition(
                current.id,
                expected_revision=current.revision,
                status="pausing",
                updates={
                    "failure_code": failure_code,
                    "failure_message": failure_message,
                },
            )
        if current.status in {"queued", "pausing"}:
            current = self.jobs.transition(
                current.id,
                expected_revision=current.revision,
                status="paused",
                updates={
                    "failure_code": failure_code,
                    "failure_message": failure_message,
                    "lease_owner": "",
                    "lease_expiry": "",
                    "heartbeat": "",
                },
            )
        self.events.append(
            current.id,
            "paused",
            dedupe_key=f"{current.id}:recoverable-paused:{current.revision}",
            chapter_id=current.current_chapter_id,
            section_id=current.current_section_id,
            transaction_id=current.active_transaction_id,
            payload={
                "status": current.status,
                "failure_code": failure_code,
                "revision": current.revision,
                "replay_same_transaction": True,
            },
        )
        return current

    def retry_failed(
        self,
        job_id: str,
        *,
        expected_revision: int,
    ) -> GenerationJob:
        job = self.jobs.load(job_id)
        if job.revision != expected_revision:
            raise RevisionConflict(expected_revision, job.revision)
        if job.status != "failed" or not job.failed_chapter_id:
            raise ValueError("only a failed chapter can be retried")
        attempts = dict(job.chapter_attempts)
        attempts[job.failed_chapter_id] = attempts.get(job.failed_chapter_id, 1) + 1
        chapter = self.chapters.load(job.failed_chapter_id)
        if chapter.status == "failed":
            self.chapters.save_next(
                chapter.model_copy(
                    update={
                        "revision": chapter.revision + 1,
                        "status": "generating",
                        "failure_code": "",
                        "failure_message": "",
                        "updated_at": utc_now(),
                    }
                ),
                expected_revision=chapter.revision,
            )
        retried = self.jobs.transition(
            job.id,
            expected_revision=job.revision,
            status="queued",
            updates={
                "chapter_attempts": attempts,
                "retry_count": job.retry_count + 1,
                "failed_chapter_id": "",
                "failure_code": "",
                "failure_message": "",
                "lease_owner": "",
                "lease_expiry": "",
                "heartbeat": "",
            },
        )
        self.events.append(
            job.id,
            "job_status",
            dedupe_key=f"{job.id}:retry:{retried.retry_count}",
            chapter_id=job.failed_chapter_id,
            payload={
                "status": retried.status,
                "retry_count": retried.retry_count,
            },
        )
        return retried

    async def run(
        self,
        job_id: str,
        *,
        max_sections: int | None = None,
    ) -> GenerationJob:
        processed = 0
        async with self._lock:
            job = self.jobs.load(job_id)
            if job.status in {"paused", "cancelled", "completed", "failed"}:
                return job
            job = self._claim_lease(job)
            if job.status == "queued":
                job = self.jobs.transition(
                    job.id,
                    expected_revision=job.revision,
                    status="running",
                )
                self.events.append(
                    job.id,
                    "job_status",
                    dedupe_key=f"{job.id}:running:{job.revision}",
                    payload={"status": "running", "revision": job.revision},
                )

            # One full scan is the restart boundary.  Normal section progress
            # below is merged incrementally from the just-committed attempt.
            job = self._reconcile_full(job.id)
            while True:
                inflight = self._active_attempt(job)
                if inflight is None:
                    job = self._finish_boundary_request(job)
                    if job.status in {"paused", "cancelled", "completed", "failed"}:
                        return job
                    try:
                        authorities = self._load_fresh_authorities(job)
                        chapter = self._next_chapter(job, authorities.outline)
                        if chapter is None:
                            return self._complete(job)
                        job, record = self._ensure_chapter(
                            job,
                            chapter,
                            authorities,
                        )
                        next_ordinal = len(record.sections) + 1
                        if next_ordinal > record.expected_section_count:
                            job = self._reconcile_full(job.id)
                            continue
                        inflight = self._create_attempt(
                            job,
                            record,
                            next_ordinal,
                            authorities,
                        )
                    except Exception as exc:
                        return self._fail(job.id, exc, chapter_id=job.current_chapter_id)

                committed = await self._execute_attempt(inflight)
                if committed is None:
                    return self.jobs.load(job.id)
                job = self._merge_committed_attempt(committed)
                processed += 1
                job = self._finish_boundary_request(job)
                if job.status in {"paused", "cancelled", "completed", "failed"}:
                    return job
                if max_sections is not None and processed >= max(0, max_sections):
                    return self._release_lease(job)

    async def recover_active_jobs(self) -> list[GenerationJob]:
        recovered: list[GenerationJob] = []
        for job in self.jobs.list_all():
            if job.status in {"queued", "running", "pausing", "cancelling"}:
                try:
                    recovered.append(await self.run(job.id))
                except ProductionLeaseConflict:
                    continue
        return recovered

    def list_chapters(
        self,
        *,
        committed_only: bool = True,
    ) -> list[ProductionChapterRecord]:
        return self.chapters.list_all(committed_only=committed_only)

    def get_chapter(
        self,
        chapter_id: str,
        *,
        committed_only: bool = True,
    ) -> ProductionChapterRecord:
        chapter = self.chapters.load(chapter_id)
        if committed_only and chapter.status != "committed":
            raise KeyError(chapter_id)
        return chapter

    def _binding_profile(self, binding) -> StyleProfile:
        profile = binding.profile_snapshot or self.styles.get(
            binding.style_profile_id
        )
        if (
            profile.revision != binding.profile_revision
            or profile.prompt_hash != binding.prompt_hash
        ):
            raise ValueError("active style binding snapshot does not match its hash")
        return profile

    def _claim_lease(self, job: GenerationJob) -> GenerationJob:
        now = datetime.now(timezone.utc)
        expiry = _parse_time(job.lease_expiry)
        if (
            job.lease_owner
            and job.lease_owner != self.owner_id
            and expiry is not None
            and expiry > now
        ):
            raise ProductionLeaseConflict(
                f"job {job.id} is leased by another production worker"
            )
        return self._save_job(
            job.id,
            lease_owner=self.owner_id,
            lease_expiry=(now + timedelta(seconds=self.lease_seconds)).isoformat(),
            heartbeat=now.isoformat(),
        )

    def _heartbeat(self, job: GenerationJob) -> GenerationJob:
        now = datetime.now(timezone.utc)
        return self._save_job(
            job.id,
            lease_owner=self.owner_id,
            lease_expiry=(now + timedelta(seconds=self.lease_seconds)).isoformat(),
            heartbeat=now.isoformat(),
        )

    def _release_lease(self, job: GenerationJob) -> GenerationJob:
        return self._save_job(
            job.id,
            lease_owner="",
            lease_expiry="",
            heartbeat="",
        )

    def _save_job(self, job_id: str, **updates: Any) -> GenerationJob:
        current = self.jobs.load(job_id)
        payload = current.model_dump(mode="python")
        payload.update(updates)
        payload.update(revision=current.revision + 1, updated_at=utc_now())
        return self.jobs.save_next(
            GenerationJob.model_validate(payload),
            expected_revision=current.revision,
        )

    def _load_fresh_authorities(self, job: GenerationJob) -> _AuthorityView:
        spec = self.specs.load()
        outline = self.outlines.load()
        bible = self.bibles.load()
        state = self.states.load()
        threads = self.threads.load()
        memories = self.memories.load()
        if outline.revision != job.requested_outline_revision:
            raise StaleProductionContract("book outline revision changed")
        if (
            job.requested_spec_snapshot is not None
            and _material_spec(spec) != _material_spec(job.requested_spec_snapshot)
        ):
            raise StaleProductionContract("production scale contract changed")
        if (
            job.requested_spec_snapshot is None
            and spec.revision != job.requested_spec_revision
        ):
            raise StaleProductionContract("production spec revision changed")
        if bible.revision != job.requested_story_bible_revision:
            raise StaleProductionContract("StoryBible revision changed")
        if state.revision != job.last_committed_canonical_revision:
            raise StaleProductionContract("CanonicalState revision chain changed")
        return _AuthorityView(
            spec=spec,
            outline=outline,
            bible=bible,
            state=state,
            threads=threads,
            memories=memories,
        )

    def _next_chapter(
        self,
        job: GenerationJob,
        outline: BookOutline,
    ) -> ChapterOutline | None:
        completed = set(job.completed_chapter_ids)
        for chapter in sorted(outline.chapters, key=lambda item: item.ordinal):
            if chapter.id not in completed:
                return chapter
        return None

    def _ensure_chapter(
        self,
        job: GenerationJob,
        chapter: ChapterOutline,
        authorities: _AuthorityView,
    ) -> tuple[GenerationJob, ProductionChapterRecord]:
        with production_boundary_lock(self.data_dir):
            if self.chapters.exists(chapter.id):
                return job, self.chapters.load(chapter.id)
            binding = self.active_styles.load()
            if binding.applies_from_chapter_ordinal <= chapter.ordinal:
                style = self._binding_profile(binding)
            elif job.requested_style_snapshot is not None:
                style = job.requested_style_snapshot
            else:
                style = self.styles.get(job.requested_style_profile_id)
            spec = authorities.spec
            section_count = self._section_count(
                chapter.target_chars,
                spec.section_target_chars,
            )
            volume = next(
                volume
                for volume in authorities.outline.volumes
                if volume.id == chapter.volume_id
            )
            record = self.chapters.create(
                ProductionChapterRecord(
                    job_id=job.id,
                    chapter_id=chapter.id,
                    chapter_ordinal=chapter.ordinal,
                    volume_id=volume.id,
                    title=chapter.title,
                    expected_section_count=section_count,
                    production_spec_revision=spec.revision,
                    outline_revision=authorities.outline.revision,
                    chapter_outline=chapter,
                    style_profile=style,
                    canonical_revision_start=job.last_committed_canonical_revision,
                )
            )
        attempts = dict(job.chapter_attempts)
        attempts.setdefault(chapter.id, 1)
        job = self._save_job(
            job.id,
            current_volume_id=volume.id,
            current_volume_ordinal=volume.ordinal,
            current_chapter_id=chapter.id,
            current_chapter_ordinal=chapter.ordinal,
            current_section_id="",
            current_section_ordinal=0,
            chapter_attempts=attempts,
        )
        self.events.append(
            job.id,
            "chapter_started",
            dedupe_key=f"{job.id}:{chapter.id}:started",
            chapter_id=chapter.id,
            payload={
                "chapter_ordinal": chapter.ordinal,
                "section_count": section_count,
                "style_profile_id": style.id,
                "style_revision": style.revision,
            },
        )
        return job, record

    @staticmethod
    def _section_count(chapter_chars: int, section_chars: int) -> int:
        requested = max(1, math.ceil(chapter_chars / min(section_chars, 10_000)))
        maximum = max(1, chapter_chars // 200)
        return min(requested, maximum)

    def _create_attempt(
        self,
        job: GenerationJob,
        record: ProductionChapterRecord,
        section_ordinal: int,
        authorities: _AuthorityView,
    ) -> ProductionSectionAttempt:
        spec = authorities.spec
        outline = authorities.outline
        count = record.expected_section_count
        targets = _distribute(record.chapter_outline.target_chars, count)
        minimums = _distribute(spec.accepted_chapter_min_chars, count)
        maximums = _distribute(spec.accepted_chapter_max_chars, count)
        attempt_number = job.chapter_attempts.get(record.chapter_id, 1)
        digest = hashlib.sha256(
            (
                f"{job.id}:{record.chapter_id}:{section_ordinal}:"
                f"{attempt_number}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        transaction_id = f"prod_{digest}"
        section_id = f"{record.chapter_id}_s{section_ordinal:03d}"
        snapshot = ProductionContextSnapshot(
            job_id=job.id,
            job_revision=job.revision,
            production_spec=spec,
            outline_revision=outline.revision,
            chapter_outline=record.chapter_outline,
            style_profile=record.style_profile,
            story_bible_revision=authorities.bible.revision,
            canonical_state_revision=authorities.state.revision,
            story_thread_revision=authorities.threads.revision,
            memory_revision=authorities.memories.revision,
            chapter_attempt=attempt_number,
            section_ordinal=section_ordinal,
            section_target_chars=targets[section_ordinal - 1],
            section_min_chars=minimums[section_ordinal - 1],
            section_max_chars=maximums[section_ordinal - 1],
        )
        attempt = self.attempts.create(
            ProductionSectionAttempt(
                id=f"attempt_{digest}",
                job_id=job.id,
                chapter_id=record.chapter_id,
                chapter_ordinal=record.chapter_ordinal,
                section_id=section_id,
                section_ordinal=section_ordinal,
                attempt_number=attempt_number,
                transaction_id=transaction_id,
                snapshot=snapshot,
            )
        )
        self._save_job(
            job.id,
            current_section_id=section_id,
            current_section_ordinal=section_ordinal,
            active_transaction_id=transaction_id,
        )
        self.events.append(
            job.id,
            "section_started",
            dedupe_key=f"{transaction_id}:started",
            chapter_id=record.chapter_id,
            section_id=section_id,
            transaction_id=transaction_id,
            payload={
                "section_ordinal": section_ordinal,
                "attempt_number": attempt_number,
                "target_chars": snapshot.section_target_chars,
            },
        )
        return attempt

    def _request_for(self, attempt: ProductionSectionAttempt) -> SectionRunRequest:
        snapshot = attempt.snapshot
        chapter = snapshot.chapter_outline
        count = self._section_count(
            chapter.target_chars,
            snapshot.production_spec.section_target_chars,
        )
        event_rows = [
            event
            for index, event in enumerate(chapter.required_events)
            if index % count == snapshot.section_ordinal - 1
        ]
        end_states = (
            chapter.required_end_states
            if snapshot.section_ordinal == count
            else []
        )
        goal = SectionGoal(
            section_id=attempt.section_id,
            objective=(
                f"{chapter.objective} "
                f"[section {snapshot.section_ordinal}/{count}]"
            ),
            viewpoint_character_id=chapter.viewpoint_character_id,
            location_id=chapter.location_id,
            involved_characters=chapter.involved_characters,
            target_threads=chapter.target_threads,
            desired_length=snapshot.section_target_chars,
            narrative_constraints=NarrativeContractInput(
                required_events=event_rows,
                required_end_state=end_states,
                forbidden_additions=chapter.prohibited_additions,
                length_constraint=LengthConstraint(
                    min_chars=snapshot.section_min_chars,
                    max_chars=snapshot.section_max_chars,
                ),
            ),
        )
        return SectionRunRequest(
            transaction_id=attempt.transaction_id,
            section_id=attempt.section_id,
            goal=goal,
            snapshot=snapshot,
        )

    async def _execute_attempt(
        self,
        attempt: ProductionSectionAttempt,
    ) -> ProductionSectionAttempt | None:
        request = self._request_for(attempt)
        try:
            result = await self.section_runner.run_section(request)
        except SectionCommitPending:
            self.events.append(
                attempt.job_id,
                "job_status",
                dedupe_key=f"{attempt.transaction_id}:commit-pending",
                chapter_id=attempt.chapter_id,
                section_id=attempt.section_id,
                transaction_id=attempt.transaction_id,
                payload={"status": "commit_pending"},
            )
            raise
        except (ProviderConfigurationError, ProviderError) as exc:
            self._handle_provider_failure(attempt, exc)
            return None
        except Exception as exc:
            code, message = _safe_failure(exc)
            self._save_failed_attempt(attempt, code=code, message=message)
            self._fail(attempt.job_id, exc, chapter_id=attempt.chapter_id)
            return None

        if result.transaction_id != attempt.transaction_id:
            raise SectionCommitPending(
                "committed section identity could not be reconciled safely"
            )
        if not result.committed:
            self.events.append(
                attempt.job_id,
                "validation",
                dedupe_key=f"{attempt.transaction_id}:validation",
                chapter_id=attempt.chapter_id,
                section_id=attempt.section_id,
                transaction_id=attempt.transaction_id,
                payload={
                    "accepted": False,
                    "error_code": result.error_code or "SECTION_REJECTED",
                },
            )
            current = self.attempts.load(attempt.id)
            self.attempts.save_next(
                current.model_copy(
                    update={
                        "revision": current.revision + 1,
                        "status": "rejected",
                        "error_code": result.error_code or "SECTION_REJECTED",
                        "error_message": "section output was rejected before commit",
                        "updated_at": utc_now(),
                    }
                ),
                expected_revision=current.revision,
            )
            self._fail(
                attempt.job_id,
                ValueError(result.error_code or "section rejected"),
                chapter_id=attempt.chapter_id,
            )
            return None
        if result.section_id != attempt.section_id:
            raise SectionCommitPending(
                "committed section position could not be reconciled safely"
            )
        if (
            result.canonical_revision_after
            != attempt.snapshot.canonical_state_revision + 1
        ):
            raise SectionCommitPending(
                "committed CanonicalState revision could not be reconciled safely"
            )
        if result.story_bible_revision != attempt.snapshot.story_bible_revision:
            raise SectionCommitPending(
                "committed StoryBible revision could not be reconciled safely"
            )

        self.events.append(
            attempt.job_id,
            "validation",
            dedupe_key=f"{attempt.transaction_id}:validation",
            chapter_id=attempt.chapter_id,
            section_id=attempt.section_id,
            transaction_id=attempt.transaction_id,
            payload={
                "accepted": True,
                "canonical_revision": result.canonical_revision_after,
            },
        )
        if result.repair_performed:
            self.events.append(
                attempt.job_id,
                "repair",
                dedupe_key=f"{attempt.transaction_id}:repair",
                chapter_id=attempt.chapter_id,
                section_id=attempt.section_id,
                transaction_id=attempt.transaction_id,
                payload={"performed": True, "accepted": True},
            )

        if self.fault_injector is not None:
            self.fault_injector("after_runner_commit", attempt, result)
        current = self.attempts.load(attempt.id)
        committed = self.attempts.save_next(
            current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "status": "committed",
                    "committed_content": result.content,
                    "section_summary": result.summary,
                    "char_count": result.char_count,
                    "canonical_revision_after": result.canonical_revision_after,
                    "story_bible_revision": result.story_bible_revision,
                    "validation_passed": result.validation_passed,
                    "repair_performed": result.repair_performed,
                    "provider": result.provider,
                    "provider_model": result.provider_model,
                    "provider_source": result.provider_source,
                    "provider_config_fingerprint": (
                        result.provider_config_fingerprint
                    ),
                    "provider_config_fingerprints": (
                        result.provider_config_fingerprints
                    ),
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "latency_ms": result.latency_ms,
                    "updated_at": utc_now(),
                }
            ),
            expected_revision=current.revision,
        )
        self.events.append(
            attempt.job_id,
            "section_committed",
            dedupe_key=f"{attempt.transaction_id}:committed",
            chapter_id=attempt.chapter_id,
            section_id=attempt.section_id,
            transaction_id=attempt.transaction_id,
            payload={
                "char_count": result.char_count,
                "canonical_revision": result.canonical_revision_after,
                "repair_performed": result.repair_performed,
                "provider": result.provider,
                "model": result.provider_model,
                "source": result.provider_source,
                "config_fingerprint": result.provider_config_fingerprint,
            },
        )
        if self.fault_injector is not None:
            self.fault_injector("after_attempt_committed", attempt, result)
        return committed

    def _handle_provider_failure(
        self,
        attempt: ProductionSectionAttempt,
        exc: ProviderConfigurationError | ProviderError,
    ) -> None:
        """Journal a Provider failure without exposing prose or credentials.

        Authentication/configuration failures pause immediately.  Transient
        429/5xx-style failures receive a bounded number of fresh production
        attempts; exhaustion pauses at the same safe section boundary. Invalid
        structured output has already consumed its single format-only repair
        and therefore pauses without a fresh full-Writer attempt. A resume
        always receives a new transaction ID.
        """

        if isinstance(exc, ProviderError):
            code = exc.code
            message = exc.message
            retryable = exc.http_category in {
                "rate_limit",
                "timeout",
                "unavailable",
            }
            category = exc.http_category
            upstream_status = exc.upstream_status
            provider = exc.config.provider
            provider_model = exc.config.model
            provider_source = exc.config.source
            provider_config_fingerprint = exc.config.config_fingerprint
        else:
            code = "PROVIDER_CONFIG_INVALID"
            message = "Provider configuration is unavailable or invalid"
            retryable = False
            category = "configuration"
            upstream_status = None
            provider = ""
            provider_model = ""
            provider_source = ""
            provider_config_fingerprint = ""

        self._save_failed_attempt(
            attempt,
            code=code,
            message=message,
            provider=provider,
            provider_model=provider_model,
            provider_source=provider_source,
            provider_config_fingerprint=provider_config_fingerprint,
        )
        provider_failures = [
            row
            for row in self.attempts.list_all(
                job_id=attempt.job_id,
                chapter_id=attempt.chapter_id,
            )
            if row.section_ordinal == attempt.section_ordinal
            and row.error_code.startswith("PROVIDER_")
        ]
        current = self.jobs.load(attempt.job_id)
        chapter_attempts = dict(current.chapter_attempts)
        chapter_attempts[attempt.chapter_id] = max(
            chapter_attempts.get(attempt.chapter_id, 1),
            attempt.attempt_number,
        ) + 1
        event_payload: dict[str, Any] = {
            "failure_code": code,
            "category": category,
            "attempt": len(provider_failures),
            "retry_limit": self.provider_retry_limit,
        }
        if provider:
            event_payload.update(
                {
                    "provider": provider,
                    "model": provider_model,
                    "source": provider_source,
                    "config_fingerprint": provider_config_fingerprint,
                }
            )
        if upstream_status is not None:
            event_payload["upstream_status"] = upstream_status

        if retryable and len(provider_failures) <= self.provider_retry_limit:
            self._save_job(
                current.id,
                chapter_attempts=chapter_attempts,
                active_transaction_id="",
                failure_code=code,
                failure_message=message,
            )
            self.events.append(
                attempt.job_id,
                "job_status",
                dedupe_key=(
                    f"{attempt.transaction_id}:provider-retry:"
                    f"{len(provider_failures)}"
                ),
                chapter_id=attempt.chapter_id,
                section_id=attempt.section_id,
                transaction_id=attempt.transaction_id,
                payload={**event_payload, "status": "retrying"},
            )
            return

        current = self.jobs.load(attempt.job_id)
        if current.status == "running":
            current = self.jobs.transition(
                current.id,
                expected_revision=current.revision,
                status="pausing",
                updates={
                    "chapter_attempts": chapter_attempts,
                    "active_transaction_id": "",
                    "failure_code": code,
                    "failure_message": message,
                },
            )
        if current.status in {"queued", "pausing"}:
            current = self.jobs.transition(
                current.id,
                expected_revision=current.revision,
                status="paused",
                updates={
                    "chapter_attempts": chapter_attempts,
                    "active_transaction_id": "",
                    "failure_code": code,
                    "failure_message": message,
                    "lease_owner": "",
                    "lease_expiry": "",
                    "heartbeat": "",
                },
            )
        self.events.append(
            attempt.job_id,
            "paused",
            dedupe_key=f"{attempt.transaction_id}:provider-paused",
            chapter_id=attempt.chapter_id,
            section_id=attempt.section_id,
            transaction_id=attempt.transaction_id,
            payload={**event_payload, "status": "paused", "revision": current.revision},
        )

    def _save_failed_attempt(
        self,
        attempt: ProductionSectionAttempt,
        *,
        code: str,
        message: str,
        provider: str = "",
        provider_model: str = "",
        provider_source: str = "",
        provider_config_fingerprint: str = "",
    ) -> None:
        current = self.attempts.load(attempt.id)
        self.attempts.save_next(
            current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "status": "failed",
                    "error_code": code,
                    "error_message": message,
                    "provider": provider,
                    "provider_model": provider_model,
                    "provider_source": provider_source,
                    "provider_config_fingerprint": provider_config_fingerprint,
                    "provider_config_fingerprints": (
                        [provider_config_fingerprint]
                        if provider_config_fingerprint
                        else []
                    ),
                    "updated_at": utc_now(),
                }
            ),
            expected_revision=current.revision,
        )

    def _active_attempt(
        self, job: GenerationJob
    ) -> ProductionSectionAttempt | None:
        transaction_id = job.active_transaction_id
        if not transaction_id:
            return None
        if transaction_id.startswith("prod_"):
            attempt_id = f"attempt_{transaction_id.removeprefix('prod_')}"
            if self.attempts.exists(attempt_id):
                attempt = self.attempts.load(attempt_id)
                if attempt.job_id == job.id and attempt.status == "in_progress":
                    return attempt
        return None

    @staticmethod
    def _committed_section(
        attempt: ProductionSectionAttempt,
    ) -> CommittedProductionSection:
        return CommittedProductionSection(
            id=attempt.section_id,
            ordinal=attempt.section_ordinal,
            transaction_id=attempt.transaction_id,
            attempt_number=attempt.attempt_number,
            content=attempt.committed_content,
            summary=attempt.section_summary,
            char_count=attempt.char_count,
            canonical_revision=attempt.canonical_revision_after,
            story_bible_revision=attempt.story_bible_revision,
            repair_performed=attempt.repair_performed,
            provider=attempt.provider,
            provider_model=attempt.provider_model,
            provider_source=attempt.provider_source,
            provider_config_fingerprint=(
                attempt.provider_config_fingerprint
            ),
            provider_config_fingerprints=(
                attempt.provider_config_fingerprints
            ),
            prompt_tokens=attempt.prompt_tokens,
            completion_tokens=attempt.completion_tokens,
            latency_ms=attempt.latency_ms,
            committed_at=attempt.updated_at,
        )

    def _merge_committed_attempt(
        self,
        attempt: ProductionSectionAttempt,
    ) -> GenerationJob:
        """Incrementally apply one durable committed attempt.

        If the process dies anywhere in this method, the next ``run`` performs
        one full scan and reconstructs the same derived chapter/job state.
        """

        if attempt.status != "committed":
            raise ValueError("only a committed attempt can advance production")
        chapter = self.chapters.load(attempt.chapter_id)
        existing = next(
            (
                section
                for section in chapter.sections
                if section.transaction_id == attempt.transaction_id
            ),
            None,
        )
        if existing is None:
            if attempt.section_ordinal != len(chapter.sections) + 1:
                return self._fail(
                    attempt.job_id,
                    ValueError("committed section order is not contiguous"),
                    chapter_id=attempt.chapter_id,
                )
            section = self._committed_section(attempt)
            chapter = self.chapters.save_next(
                chapter.model_copy(
                    update={
                        "revision": chapter.revision + 1,
                        "sections": [*chapter.sections, section],
                        "char_count": chapter.char_count + section.char_count,
                        "updated_at": utc_now(),
                    }
                ),
                expected_revision=chapter.revision,
            )

        current = self.jobs.load(attempt.job_id)
        if attempt.canonical_revision_after != (
            current.last_committed_canonical_revision + 1
        ):
            return self._fail(
                attempt.job_id,
                ValueError("committed CanonicalState revision is not the next revision"),
                chapter_id=attempt.chapter_id,
            )
        if self.states.load().revision != attempt.canonical_revision_after:
            return self._fail(
                attempt.job_id,
                ValueError("persisted CanonicalState does not match committed attempt"),
                chapter_id=attempt.chapter_id,
            )
        now = datetime.now(timezone.utc)
        job = self._save_job(
            current.id,
            prompt_tokens_total=current.prompt_tokens_total + attempt.prompt_tokens,
            completion_tokens_total=(
                current.completion_tokens_total + attempt.completion_tokens
            ),
            latency_total_ms=current.latency_total_ms + attempt.latency_ms,
            repair_total=current.repair_total + int(attempt.repair_performed),
            last_committed_canonical_revision=attempt.canonical_revision_after,
            active_transaction_id="",
            failure_code="",
            failure_message="",
            lease_owner=self.owner_id,
            lease_expiry=(
                now + timedelta(seconds=self.lease_seconds)
            ).isoformat(),
            heartbeat=now.isoformat(),
        )
        if (
            chapter.status == "generating"
            and len(chapter.sections) == chapter.expected_section_count
        ):
            job = self._commit_chapter(job.id, chapter)
            if job.status == "failed":
                return job
            committed = self.chapters.load(chapter.chapter_id)
            completed_ids = list(job.completed_chapter_ids)
            if committed.chapter_id not in completed_ids:
                completed_ids.append(committed.chapter_id)
                chapter_order = {
                    item.id: item.ordinal for item in self.outlines.load().chapters
                }
                completed_ids.sort(key=lambda chapter_id: chapter_order[chapter_id])
                job = self._save_job(
                    job.id,
                    completed_chapter_ids=completed_ids,
                )
            outline = self.outlines.load()
            job = self.jobs.load(job.id)
            if job.status in {"pausing", "cancelling"}:
                # A control request received while the final Runner call was
                # in flight wins at this safe boundary.  The just-validated
                # chapter remains committed; resume may then mark the book
                # complete without re-running prose generation.
                return job
            if len(job.completed_chapter_ids) == len(outline.chapters):
                return self._complete(job)
        return job

    def _reconcile_full(self, job_id: str) -> GenerationJob:
        job = self.jobs.load(job_id)
        all_attempts = self.attempts.list_all(job_id=job_id)
        committed_attempts = [
            attempt
            for attempt in all_attempts
            if attempt.status == "committed"
        ]
        by_slot: dict[tuple[str, int], ProductionSectionAttempt] = {}
        for attempt in committed_attempts:
            slot = (attempt.chapter_id, attempt.section_ordinal)
            if slot in by_slot and by_slot[slot].transaction_id != attempt.transaction_id:
                return self._fail(
                    job_id,
                    ValueError("multiple committed transactions target one section"),
                    chapter_id=attempt.chapter_id,
                )
            by_slot[slot] = attempt

        job_chapters = [
            item for item in self.chapters.list_all() if item.job_id == job_id
        ]
        for chapter in job_chapters:
            rows = sorted(
                (
                    attempt
                    for (chapter_id, _), attempt in by_slot.items()
                    if chapter_id == chapter.chapter_id
                ),
                key=lambda item: item.section_ordinal,
            )
            sections = [self._committed_section(attempt) for attempt in rows]
            if [item.model_dump() for item in sections] != [
                item.model_dump() for item in chapter.sections
            ]:
                chapter = self.chapters.save_next(
                    chapter.model_copy(
                        update={
                            "revision": chapter.revision + 1,
                            "sections": sections,
                            "char_count": sum(item.char_count for item in sections),
                            "updated_at": utc_now(),
                        }
                    ),
                    expected_revision=chapter.revision,
                )
            if (
                chapter.status == "generating"
                and len(chapter.sections) == chapter.expected_section_count
            ):
                job = self._commit_chapter(job_id, chapter)
                chapter = self.chapters.load(chapter.chapter_id)
            if chapter.status == "committed":
                self._ensure_chapter_memory(chapter)
                self._ensure_outline_chapter_committed(chapter)

        committed_attempts.sort(key=lambda item: item.canonical_revision_after)
        expected_revisions = list(
            range(
                job.requested_canonical_revision + 1,
                job.requested_canonical_revision + len(committed_attempts) + 1,
            )
        )
        actual_revisions = [
            attempt.canonical_revision_after for attempt in committed_attempts
        ]
        if actual_revisions != expected_revisions:
            return self._fail(
                job_id,
                ValueError("committed CanonicalState revisions are not contiguous"),
                chapter_id=job.current_chapter_id,
            )
        job_chapters = [
            item for item in self.chapters.list_all() if item.job_id == job_id
        ]
        committed_chapters = [
            chapter for chapter in job_chapters if chapter.status == "committed"
        ]
        inflight = next(
            (
                attempt
                for attempt in reversed(all_attempts)
                if attempt.status == "in_progress"
            ),
            None,
        )
        current = self.jobs.load(job_id)
        derived = {
            "completed_chapter_ids": [
                chapter.chapter_id for chapter in committed_chapters
            ],
            "prompt_tokens_total": sum(
                attempt.prompt_tokens for attempt in committed_attempts
            ),
            "completion_tokens_total": sum(
                attempt.completion_tokens for attempt in committed_attempts
            ),
            "latency_total_ms": sum(
                attempt.latency_ms for attempt in committed_attempts
            ),
            "repair_total": sum(
                int(attempt.repair_performed) for attempt in committed_attempts
            ),
            "last_committed_canonical_revision": (
                actual_revisions[-1]
                if actual_revisions
                else current.requested_canonical_revision
            ),
            "active_transaction_id": (
                inflight.transaction_id if inflight is not None else ""
            ),
        }
        if any(getattr(current, key) != value for key, value in derived.items()):
            current = self._save_job(job_id, **derived)
        outline = self.outlines.load()
        if (
            len(current.completed_chapter_ids) == len(outline.chapters)
            and outline.chapters
            and current.status not in {"completed", "cancelled"}
        ):
            if current.status in {"pausing", "cancelling"}:
                return self._finish_boundary_request(current)
            return self._complete(current)
        return current

    def _commit_chapter(
        self,
        job_id: str,
        chapter: ProductionChapterRecord,
    ) -> GenerationJob:
        spec = self.specs.load()
        if not (
            spec.accepted_chapter_min_chars
            <= chapter.char_count
            <= spec.accepted_chapter_max_chars
        ):
            return self._fail(
                job_id,
                ValueError("committed section total is outside chapter range"),
                chapter_id=chapter.chapter_id,
            )
        summary_parts = [
            section.summary.strip() or section.content[:80]
            for section in chapter.sections
        ]
        chapter_summary = " ".join(summary_parts)[:2_000]
        self._ensure_chapter_memory(
            chapter.model_copy(update={"summary": chapter_summary})
        )
        committed = self.chapters.save_next(
            chapter.model_copy(
                update={
                    "revision": chapter.revision + 1,
                    "status": "committed",
                    "summary": chapter_summary,
                    "canonical_revision_end": chapter.sections[-1].canonical_revision,
                    "repair_total": sum(
                        int(section.repair_performed)
                        for section in chapter.sections
                    ),
                    "validation_passed": True,
                    "committed_at": utc_now(),
                    "updated_at": utc_now(),
                }
            ),
            expected_revision=chapter.revision,
        )
        self._ensure_outline_chapter_committed(committed)
        self.events.append(
            job_id,
            "chapter_committed",
            dedupe_key=f"{job_id}:{committed.chapter_id}:committed",
            chapter_id=committed.chapter_id,
            payload={
                "char_count": committed.char_count,
                "section_count": len(committed.sections),
                "style_profile_id": committed.style_profile.id,
                "style_revision": committed.style_profile.revision,
                "committed_at": committed.committed_at,
            },
        )
        if self.fault_injector is not None:
            synthetic = self.attempts.list_all(
                job_id=job_id,
                chapter_id=committed.chapter_id,
            )[-1]
            self.fault_injector("after_chapter_committed", synthetic, None)
        return self.jobs.load(job_id)

    def _ensure_chapter_memory(
        self,
        chapter: ProductionChapterRecord,
    ) -> None:
        """Persist one deterministic retrieval memory per completed chapter."""

        if not chapter.sections:
            return
        summary = chapter.summary.strip() or " ".join(
            section.summary.strip() or section.content[:80]
            for section in chapter.sections
        )[:2_000]
        memory_id = f"production_summary_{chapter.chapter_id}"
        expected = MemoryRecord(
            id=memory_id,
            type="event",
            section_id=chapter.sections[-1].id,
            entities=chapter.chapter_outline.involved_characters,
            summary=summary,
            evidence=(
                f"Committed chapter {chapter.chapter_id}; "
                f"{len(chapter.sections)} committed sections."
            ),
            importance=8,
            source_refs=chapter.chapter_outline.target_threads,
            created_at_revision=chapter.sections[-1].canonical_revision,
        )
        with self.memories.lock:
            state = self.memories.load()
            existing = state.records.get(memory_id)
            if existing is not None:
                if existing.model_dump(mode="json") != expected.model_dump(mode="json"):
                    raise StaleProductionContract(
                        "chapter summary memory conflicts with committed chapter"
                    )
                return
            records = dict(state.records)
            records[memory_id] = expected
            self.memories.save(
                state.model_copy(
                    update={
                        "revision": state.revision + 1,
                        "records": records,
                        "updated_at": utc_now(),
                    }
                )
            )

    def _ensure_outline_chapter_committed(
        self,
        committed: ProductionChapterRecord,
    ) -> None:
        outline = self.outlines.load()
        updated_chapters = [
            item.model_copy(
                update={
                    "status": "committed",
                    "committed_section_ids": [
                        section.id for section in committed.sections
                    ],
                }
            )
            if item.id == committed.chapter_id
            else item
            for item in outline.chapters
        ]
        if any(
            item.id == committed.chapter_id and item.status != "committed"
            for item in outline.chapters
        ):
            progressed = BookOutline.model_validate(
                {
                    **outline.model_dump(mode="python"),
                    "progress_revision": outline.progress_revision + 1,
                    "chapters": updated_chapters,
                    "updated_at": utc_now(),
                }
            )
            self.outlines.save_progress(
                progressed,
                expected_progress_revision=outline.progress_revision,
            )

    def _finish_boundary_request(self, job: GenerationJob) -> GenerationJob:
        job = self.jobs.load(job.id)
        if job.status == "pausing":
            job = self.jobs.transition(
                job.id,
                expected_revision=job.revision,
                status="paused",
                updates={"lease_owner": "", "lease_expiry": "", "heartbeat": ""},
            )
            self.events.append(
                job.id,
                "paused",
                dedupe_key=f"{job.id}:paused:{job.revision}",
                payload={"status": "paused", "revision": job.revision},
            )
        elif job.status == "cancelling":
            job = self.jobs.transition(
                job.id,
                expected_revision=job.revision,
                status="cancelled",
                updates={"lease_owner": "", "lease_expiry": "", "heartbeat": ""},
            )
            self.events.append(
                job.id,
                "job_status",
                dedupe_key=f"{job.id}:cancelled:{job.revision}",
                payload={"status": "cancelled", "revision": job.revision},
            )
        return job

    def _complete(self, job: GenerationJob) -> GenerationJob:
        current = self.jobs.load(job.id)
        if current.status == "completed":
            return current
        payload = current.model_dump(mode="python")
        now = utc_now()
        payload.update(
            status="completed",
            revision=current.revision + 1,
            completed_at=now,
            updated_at=now,
            lease_owner="",
            lease_expiry="",
            heartbeat="",
            active_transaction_id="",
        )
        completed = self.jobs.save_next(
            GenerationJob.model_validate(payload),
            expected_revision=current.revision,
        )
        self.events.append(
            completed.id,
            "completed",
            dedupe_key=f"{completed.id}:completed",
            payload={
                "status": "completed",
                "completed_chapters": len(completed.completed_chapter_ids),
            },
        )
        return completed

    def _fail(
        self,
        job_id: str,
        exc: Exception,
        *,
        chapter_id: str,
    ) -> GenerationJob:
        code, message = _safe_failure(exc)
        if chapter_id and self.chapters.exists(chapter_id):
            chapter = self.chapters.load(chapter_id)
            if chapter.status != "committed":
                self.chapters.save_next(
                    chapter.model_copy(
                        update={
                            "revision": chapter.revision + 1,
                            "status": "failed",
                            "failure_code": code,
                            "failure_message": message,
                            "updated_at": utc_now(),
                        }
                    ),
                    expected_revision=chapter.revision,
                )
        current = self.jobs.load(job_id)
        if current.status == "failed":
            return current
        if current.status in {"cancelled", "completed"}:
            return current
        failed = self.jobs.transition(
            current.id,
            expected_revision=current.revision,
            status="failed",
            updates={
                "failed_chapter_id": chapter_id,
                "failure_code": code,
                "failure_message": message,
                "lease_owner": "",
                "lease_expiry": "",
                "heartbeat": "",
                "active_transaction_id": "",
            },
        )
        self.events.append(
            failed.id,
            "failed",
            dedupe_key=f"{failed.id}:failed:{failed.revision}",
            chapter_id=chapter_id,
            payload={
                "failure_code": code,
                "message": message,
                "revision": failed.revision,
            },
        )
        return failed


__all__ = [
    "InjectedProductionCrash",
    "ProductionLeaseConflict",
    "ProductionServiceError",
    "SectionCommitPending",
    "SectionRunRequest",
    "SectionRunResult",
    "SectionRunner",
    "StaleProductionContract",
    "WholeBookProductionService",
    "production_boundary_lock",
]
