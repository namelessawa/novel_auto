"""Atomic persistence and idempotent migration for whole-book production."""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

from novel_presets.style_presets import STYLE_PRESETS, StylePreset
from story.migrations import ensure_story_domain
from story.models import StoryBible, utc_now
from story.persistence import (
    AtomicModelStore,
    PersistenceError,
    RevisionConflict,
    StoryBibleStore,
)
from story.production_models import (
    BookOutline,
    BookOutlineUpdate,
    GenerationJob,
    GenerationJobUpdate,
    JobStatus,
    NovelProductionSpec,
    NovelProductionSpecUpdate,
    ProductionChapterRecord,
    ProductionModel,
    ProductionSectionAttempt,
    StyleProfile,
    StyleProfileCreate,
    StyleProfileUpdate,
)


T = TypeVar("T", bound=BaseModel)


class ProductionDocumentStore(AtomicModelStore[T], Generic[T]):
    """Named production-domain facade over the common atomic JSON store.

    ``AtomicModelStore`` performs a validated temporary-file write followed by
    flush, fsync and ``os.replace``.  It also retains ``.bak`` last-good files
    and quarantines invalid documents before either recovery or fail-closed.
    """


class StyleProfileCollection(ProductionModel):
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    profiles: dict[str, StyleProfile] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("profiles")
    @classmethod
    def _keys_match_profile_ids(
        cls, value: dict[str, StyleProfile]
    ) -> dict[str, StyleProfile]:
        if any(key != profile.id for key, profile in value.items()):
            raise ValueError("style profile map keys must match profile IDs")
        return value


class ActiveStyleBinding(ProductionModel):
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    style_profile_id: str = Field(min_length=1)
    profile_revision: int = Field(ge=1)
    prompt_hash: str = Field(min_length=64, max_length=64)
    profile_snapshot: StyleProfile | None = None
    applies_from_chapter_ordinal: int = Field(default=1, ge=1)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("prompt_hash")
    @classmethod
    def _valid_sha256(cls, value: str) -> str:
        lowered = value.lower()
        if any(char not in "0123456789abcdef" for char in lowered):
            raise ValueError("prompt_hash must be hexadecimal")
        return lowered


ProductionEventType = str


class ProductionEvent(ProductionModel):
    schema_version: int = Field(default=1, ge=1)
    job_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    type: ProductionEventType = Field(min_length=1)
    dedupe_key: str = ""
    chapter_id: str = ""
    section_id: str = ""
    transaction_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class ProductionEventLog(ProductionModel):
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    job_id: str = Field(min_length=1)
    events: list[ProductionEvent] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("events")
    @classmethod
    def _sequences_are_contiguous(
        cls, value: list[ProductionEvent]
    ) -> list[ProductionEvent]:
        if [event.sequence for event in value] != list(range(1, len(value) + 1)):
            raise ValueError("production event sequences must be contiguous")
        dedupe_keys = [event.dedupe_key for event in value if event.dedupe_key]
        if len(dedupe_keys) != len(set(dedupe_keys)):
            raise ValueError("production event dedupe keys must be unique")
        return value


class ProductionMigrationReport(ProductionModel):
    schema_version: int = Field(default=1, ge=1)
    migration_version: int = Field(default=1, ge=1)
    status: str = "created"
    created_files: list[str] = Field(default_factory=list)
    preserved_files: list[str] = Field(default_factory=list)
    active_style_profile_id: str = ""
    completed_at: str = Field(default_factory=utc_now)


class ProductionSpecStore(ProductionDocumentStore[NovelProductionSpec]):
    def __init__(
        self,
        data_dir: str,
        default_factory: Callable[[], NovelProductionSpec],
    ) -> None:
        super().__init__(
            data_dir,
            "production_spec.json",
            NovelProductionSpec,
            default_factory,
        )

    def update(self, patch: NovelProductionSpecUpdate) -> NovelProductionSpec:
        with self.lock:
            current = self.load()
            if current.revision != patch.expected_revision:
                raise RevisionConflict(patch.expected_revision, current.revision)
            payload = current.model_dump(mode="python")
            payload.update(
                patch.model_dump(
                    exclude={"expected_revision"},
                    exclude_none=True,
                    mode="python",
                )
            )
            payload.update(
                revision=current.revision + 1,
                created_at=current.created_at,
                updated_at=utc_now(),
            )
            return self.save(NovelProductionSpec.model_validate(payload))


class BookOutlineStore(ProductionDocumentStore[BookOutline]):
    def __init__(self, data_dir: str) -> None:
        super().__init__(
            data_dir,
            "book_outline.json",
            BookOutline,
            BookOutline,
        )

    def update(self, patch: BookOutlineUpdate) -> BookOutline:
        with self.lock:
            current = self.load()
            if current.revision != patch.expected_revision:
                raise RevisionConflict(patch.expected_revision, current.revision)
            payload = current.model_dump(mode="python")
            payload.update(
                patch.model_dump(
                    exclude={"expected_revision"},
                    exclude_none=True,
                    mode="python",
                )
            )
            payload.update(
                revision=current.revision + 1,
                created_at=current.created_at,
                updated_at=utc_now(),
            )
            return self.save(BookOutline.model_validate(payload))

    def save_progress(
        self,
        value: BookOutline,
        *,
        expected_progress_revision: int,
    ) -> BookOutline:
        """Save system-owned progress without consuming the user edit revision."""

        with self.lock:
            current = self.load()
            if current.progress_revision != expected_progress_revision:
                raise RevisionConflict(
                    expected_progress_revision,
                    current.progress_revision,
                )
            if value.revision != current.revision:
                raise RevisionConflict(value.revision, current.revision)
            if value.progress_revision != current.progress_revision + 1:
                raise ValueError("outline progress revision must increment exactly once")
            return self.save(value)


_STYLE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,96}$")


class StyleProfileStore(ProductionDocumentStore[StyleProfileCollection]):
    def __init__(self, data_dir: str) -> None:
        super().__init__(
            data_dir,
            "style_profiles.json",
            StyleProfileCollection,
            StyleProfileCollection,
        )

    def list(self) -> list[StyleProfile]:
        return sorted(
            self.load().profiles.values(),
            key=lambda profile: (not profile.read_only, profile.name, profile.id),
        )

    def get(self, profile_id: str) -> StyleProfile:
        try:
            return self.load().profiles[profile_id]
        except KeyError:
            raise KeyError(profile_id) from None

    def create(
        self,
        request: StyleProfileCreate,
        *,
        profile_id: str | None = None,
    ) -> StyleProfile:
        style_id = profile_id or f"style_{uuid.uuid4().hex[:16]}"
        if not _STYLE_ID_RE.fullmatch(style_id):
            raise ValueError("invalid style profile ID")
        with self.lock:
            collection = self.load()
            if style_id in collection.profiles:
                raise ValueError("style profile already exists")
            now = utc_now()
            profile = StyleProfile.model_validate(
                {
                    **request.model_dump(mode="python"),
                    "id": style_id,
                    "revision": 1,
                    "prompt_hash": "",
                    "source": "user",
                    "read_only": False,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            profiles = dict(collection.profiles)
            profiles[profile.id] = profile
            self.save(
                collection.model_copy(
                    update={
                        "revision": collection.revision + 1,
                        "profiles": profiles,
                        "updated_at": now,
                    }
                )
            )
            return profile

    def copy(
        self,
        source_profile_id: str,
        *,
        name: str,
        profile_id: str | None = None,
    ) -> StyleProfile:
        source = self.get(source_profile_id)
        create_fields = set(StyleProfileCreate.model_fields)
        payload = {
            key: value
            for key, value in source.model_dump(mode="python").items()
            if key in create_fields
        }
        payload["name"] = name
        return self.create(
            StyleProfileCreate.model_validate(payload),
            profile_id=profile_id,
        )

    def update(
        self,
        profile_id: str,
        patch: StyleProfileUpdate,
    ) -> StyleProfile:
        with self.lock:
            collection = self.load()
            try:
                current = collection.profiles[profile_id]
            except KeyError:
                raise KeyError(profile_id) from None
            if current.read_only:
                raise PermissionError("read-only preset profile cannot be updated")
            if current.revision != patch.expected_revision:
                raise RevisionConflict(patch.expected_revision, current.revision)
            payload = current.model_dump(mode="python")
            payload.update(
                patch.model_dump(
                    exclude={"expected_revision"},
                    exclude_none=True,
                    mode="python",
                )
            )
            payload.update(
                revision=current.revision + 1,
                prompt_hash="",
                created_at=current.created_at,
                updated_at=utc_now(),
            )
            updated = StyleProfile.model_validate(payload)
            profiles = dict(collection.profiles)
            profiles[profile_id] = updated
            self.save(
                collection.model_copy(
                    update={
                        "revision": collection.revision + 1,
                        "profiles": profiles,
                        "updated_at": updated.updated_at,
                    }
                )
            )
            return updated

    def delete(self, profile_id: str, *, expected_revision: int) -> None:
        with self.lock:
            collection = self.load()
            try:
                current = collection.profiles[profile_id]
            except KeyError:
                raise KeyError(profile_id) from None
            if current.read_only:
                raise PermissionError("read-only preset profile cannot be deleted")
            if current.revision != expected_revision:
                raise RevisionConflict(expected_revision, current.revision)
            profiles = dict(collection.profiles)
            del profiles[profile_id]
            self.save(
                collection.model_copy(
                    update={
                        "revision": collection.revision + 1,
                        "profiles": profiles,
                        "updated_at": utc_now(),
                    }
                )
            )


class ActiveStyleStore(ProductionDocumentStore[ActiveStyleBinding]):
    def __init__(
        self,
        data_dir: str,
        default_factory: Callable[[], ActiveStyleBinding],
    ) -> None:
        super().__init__(
            data_dir,
            "active_style.json",
            ActiveStyleBinding,
            default_factory,
        )

    def activate(
        self,
        profile: StyleProfile,
        *,
        applies_from_chapter_ordinal: int,
        expected_revision: int,
    ) -> ActiveStyleBinding:
        with self.lock:
            current = self.load()
            if current.revision != expected_revision:
                raise RevisionConflict(expected_revision, current.revision)
            return self.save(
                ActiveStyleBinding(
                    revision=current.revision + 1,
                    style_profile_id=profile.id,
                    profile_revision=profile.revision,
                    prompt_hash=profile.prompt_hash,
                    profile_snapshot=profile,
                    applies_from_chapter_ordinal=applies_from_chapter_ordinal,
                    updated_at=utc_now(),
                )
            )


_DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
ACTIVE_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {"queued", "running", "pausing", "paused", "cancelling"}
)
_JOB_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    "draft": frozenset({"queued", "cancelled"}),
    "queued": frozenset(
        {"running", "paused", "cancelling", "cancelled", "failed"}
    ),
    "running": frozenset({"pausing", "cancelling", "failed", "completed"}),
    "pausing": frozenset({"paused", "cancelling", "failed"}),
    "paused": frozenset({"queued", "running", "cancelling", "cancelled"}),
    "failed": frozenset({"queued", "cancelling", "cancelled"}),
    "cancelling": frozenset({"cancelled", "failed"}),
    "cancelled": frozenset(),
    "completed": frozenset(),
}


class GenerationJobStore:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = os.path.realpath(os.path.abspath(data_dir))
        self.root = os.path.join(self.data_dir, "generation_jobs")

    def _store(self, job_id: str) -> ProductionDocumentStore[GenerationJob]:
        if not _DOCUMENT_ID_RE.fullmatch(job_id):
            raise ValueError("invalid generation job ID")
        return ProductionDocumentStore(
            self.data_dir,
            os.path.join("generation_jobs", f"{job_id}.json"),
            GenerationJob,
            lambda: (_ for _ in ()).throw(KeyError(job_id)),
        )

    def exists(self, job_id: str) -> bool:
        return self._store(job_id).exists()

    def load(self, job_id: str) -> GenerationJob:
        if not self.exists(job_id):
            raise KeyError(job_id)
        return self._store(job_id).load()

    def create(self, job: GenerationJob) -> GenerationJob:
        store = self._store(job.id)
        with store.lock:
            if store.exists():
                raise ValueError("generation job already exists")
            if job.revision != 1:
                raise ValueError("new generation job must start at revision 1")
            return store.save(job)

    def save_next(
        self,
        value: GenerationJob,
        *,
        expected_revision: int,
    ) -> GenerationJob:
        store = self._store(value.id)
        with store.lock:
            current = self.load(value.id)
            if current.revision != expected_revision:
                raise RevisionConflict(expected_revision, current.revision)
            if value.revision != current.revision + 1:
                raise ValueError("generation job revision must increment exactly once")
            return store.save(value)

    def update(
        self,
        job_id: str,
        patch: GenerationJobUpdate,
    ) -> GenerationJob:
        current = self.load(job_id)
        if current.revision != patch.expected_revision:
            raise RevisionConflict(patch.expected_revision, current.revision)
        payload = current.model_dump(mode="python")
        payload.update(
            patch.model_dump(
                exclude={"expected_revision"},
                exclude_none=True,
                mode="python",
            )
        )
        payload.update(revision=current.revision + 1, updated_at=utc_now())
        return self.save_next(
            GenerationJob.model_validate(payload),
            expected_revision=current.revision,
        )

    def transition(
        self,
        job_id: str,
        *,
        expected_revision: int,
        status: JobStatus,
        updates: dict[str, Any] | None = None,
    ) -> GenerationJob:
        current = self.load(job_id)
        if current.revision != expected_revision:
            raise RevisionConflict(expected_revision, current.revision)
        if status not in _JOB_TRANSITIONS[current.status]:
            raise ValueError(
                f"invalid generation job transition: {current.status} -> {status}"
            )
        now = utc_now()
        payload = current.model_dump(mode="python")
        payload.update(updates or {})
        payload.update(status=status, revision=current.revision + 1, updated_at=now)
        if status == "running":
            payload["started_at"] = current.started_at or now
            if current.status in {"paused", "failed"}:
                payload["resumed_at"] = now
        elif status == "paused":
            payload["paused_at"] = now
        elif status == "failed":
            payload["failed_at"] = now
        elif status == "completed":
            payload["completed_at"] = now
        elif status == "cancelling":
            payload["cancellation_requested"] = True
        elif status == "cancelled":
            payload["cancellation_requested"] = True
            payload["cancelled_at"] = now
        return self.save_next(
            GenerationJob.model_validate(payload),
            expected_revision=current.revision,
        )

    def list_all(self) -> list[GenerationJob]:
        if not os.path.isdir(self.root):
            return []
        jobs: list[GenerationJob] = []
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json") or name.endswith(".bak"):
                continue
            try:
                jobs.append(self.load(name[:-5]))
            except (KeyError, PersistenceError, ValueError):
                continue
        return sorted(jobs, key=lambda job: (job.created_at, job.id))

    def find_active(self) -> GenerationJob | None:
        active = [job for job in self.list_all() if job.status in ACTIVE_JOB_STATUSES]
        if not active:
            return None
        return sorted(active, key=lambda job: (job.created_at, job.id))[-1]


class ProductionEventStore:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = os.path.realpath(os.path.abspath(data_dir))
        self.root = os.path.join(self.data_dir, "production_events")

    def _store(self, job_id: str) -> ProductionDocumentStore[ProductionEventLog]:
        if not _DOCUMENT_ID_RE.fullmatch(job_id):
            raise ValueError("invalid generation job ID")
        return ProductionDocumentStore(
            self.data_dir,
            os.path.join("production_events", f"{job_id}.json"),
            ProductionEventLog,
            lambda: ProductionEventLog(job_id=job_id),
        )

    def load(self, job_id: str) -> ProductionEventLog:
        return self._store(job_id).load()

    def append(
        self,
        job_id: str,
        event_type: ProductionEventType,
        *,
        dedupe_key: str = "",
        chapter_id: str = "",
        section_id: str = "",
        transaction_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> ProductionEvent:
        store = self._store(job_id)
        with store.lock:
            log = store.load()
            if dedupe_key:
                for event in log.events:
                    if event.dedupe_key == dedupe_key:
                        return event
            event = ProductionEvent(
                job_id=job_id,
                sequence=len(log.events) + 1,
                type=event_type,
                dedupe_key=dedupe_key,
                chapter_id=chapter_id,
                section_id=section_id,
                transaction_id=transaction_id,
                payload=payload or {},
            )
            store.save(
                log.model_copy(
                    update={
                        "revision": log.revision + 1,
                        "events": [*log.events, event],
                        "updated_at": utc_now(),
                    }
                )
            )
            return event

    def after(self, job_id: str, sequence: int = 0) -> list[ProductionEvent]:
        return [
            event
            for event in self.load(job_id).events
            if event.sequence > max(0, sequence)
        ]


class ProductionSectionAttemptStore:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = os.path.realpath(os.path.abspath(data_dir))
        self.root = os.path.join(self.data_dir, "production_attempts")

    def _store(
        self, attempt_id: str
    ) -> ProductionDocumentStore[ProductionSectionAttempt]:
        if not _DOCUMENT_ID_RE.fullmatch(attempt_id):
            raise ValueError("invalid production attempt ID")
        return ProductionDocumentStore(
            self.data_dir,
            os.path.join("production_attempts", f"{attempt_id}.json"),
            ProductionSectionAttempt,
            lambda: (_ for _ in ()).throw(KeyError(attempt_id)),
        )

    def exists(self, attempt_id: str) -> bool:
        return self._store(attempt_id).exists()

    def load(self, attempt_id: str) -> ProductionSectionAttempt:
        if not self.exists(attempt_id):
            raise KeyError(attempt_id)
        return self._store(attempt_id).load()

    def create(
        self, attempt: ProductionSectionAttempt
    ) -> ProductionSectionAttempt:
        store = self._store(attempt.id)
        with store.lock:
            if store.exists():
                existing = store.load()
                if existing.transaction_id == attempt.transaction_id:
                    return existing
                raise ValueError("production attempt already exists")
            if attempt.revision != 1:
                raise ValueError("new production attempt must start at revision 1")
            return store.save(attempt)

    def save_next(
        self,
        value: ProductionSectionAttempt,
        *,
        expected_revision: int,
    ) -> ProductionSectionAttempt:
        store = self._store(value.id)
        with store.lock:
            current = store.load()
            if current.revision != expected_revision:
                raise RevisionConflict(expected_revision, current.revision)
            if value.revision != current.revision + 1:
                raise ValueError("attempt revision must increment exactly once")
            return store.save(value)

    def list_all(
        self,
        *,
        job_id: str | None = None,
        chapter_id: str | None = None,
    ) -> list[ProductionSectionAttempt]:
        if not os.path.isdir(self.root):
            return []
        attempts: list[ProductionSectionAttempt] = []
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json") or name.endswith(".bak"):
                continue
            try:
                attempt = self.load(name[:-5])
            except (KeyError, PersistenceError, ValueError):
                continue
            if job_id is not None and attempt.job_id != job_id:
                continue
            if chapter_id is not None and attempt.chapter_id != chapter_id:
                continue
            attempts.append(attempt)
        return sorted(
            attempts,
            key=lambda item: (
                item.chapter_ordinal,
                item.section_ordinal,
                item.attempt_number,
                item.id,
            ),
        )

    def inflight(self, job_id: str) -> ProductionSectionAttempt | None:
        rows = [
            attempt
            for attempt in self.list_all(job_id=job_id)
            if attempt.status == "in_progress"
        ]
        return rows[-1] if rows else None


class ProductionChapterStore:
    def __init__(self, data_dir: str) -> None:
        self.data_dir = os.path.realpath(os.path.abspath(data_dir))
        self.root = os.path.join(self.data_dir, "production_chapters")

    def _store(
        self, chapter_id: str
    ) -> ProductionDocumentStore[ProductionChapterRecord]:
        if not _DOCUMENT_ID_RE.fullmatch(chapter_id):
            raise ValueError("invalid production chapter ID")
        return ProductionDocumentStore(
            self.data_dir,
            os.path.join("production_chapters", f"{chapter_id}.json"),
            ProductionChapterRecord,
            lambda: (_ for _ in ()).throw(KeyError(chapter_id)),
        )

    def exists(self, chapter_id: str) -> bool:
        return self._store(chapter_id).exists()

    def load(self, chapter_id: str) -> ProductionChapterRecord:
        if not self.exists(chapter_id):
            raise KeyError(chapter_id)
        return self._store(chapter_id).load()

    def create(
        self, chapter: ProductionChapterRecord
    ) -> ProductionChapterRecord:
        store = self._store(chapter.chapter_id)
        with store.lock:
            if store.exists():
                existing = store.load()
                if existing.job_id == chapter.job_id:
                    return existing
                raise ValueError("production chapter already exists")
            if chapter.revision != 1:
                raise ValueError("new production chapter must start at revision 1")
            return store.save(chapter)

    def save_next(
        self,
        value: ProductionChapterRecord,
        *,
        expected_revision: int,
    ) -> ProductionChapterRecord:
        store = self._store(value.chapter_id)
        with store.lock:
            current = store.load()
            if current.revision != expected_revision:
                raise RevisionConflict(expected_revision, current.revision)
            if value.revision != current.revision + 1:
                raise ValueError("chapter revision must increment exactly once")
            return store.save(value)

    def list_all(
        self,
        *,
        committed_only: bool = False,
    ) -> list[ProductionChapterRecord]:
        if not os.path.isdir(self.root):
            return []
        chapters: list[ProductionChapterRecord] = []
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json") or name.endswith(".bak"):
                continue
            try:
                chapter = self.load(name[:-5])
            except (KeyError, PersistenceError, ValueError):
                continue
            if committed_only and chapter.status != "committed":
                continue
            chapters.append(chapter)
        return sorted(chapters, key=lambda item: (item.chapter_ordinal, item.chapter_id))


class ProductionMigrationStore(ProductionDocumentStore[ProductionMigrationReport]):
    def __init__(self, data_dir: str) -> None:
        super().__init__(
            data_dir,
            "production_migration.json",
            ProductionMigrationReport,
            ProductionMigrationReport,
        )


def _profile_from_preset(preset: StylePreset) -> StyleProfile:
    return StyleProfile(
        id=f"preset_{preset.key}",
        revision=1,
        name=preset.label,
        base_preset_key=preset.key,
        description=preset.description,
        derived_style_anchors=[preset.narrator_addendum],
        must_do_rules=[preset.final_checklist],
        forbidden_rules=[preset.conflict_policy],
        deterministic_rules=list(preset.det_rules),
        read_only=True,
        source="preset",
    )


def _legacy_profile(
    bible: StoryBible,
    preset_profiles: dict[str, StyleProfile],
) -> StyleProfile | None:
    snapshot = bible.style_contract
    if not snapshot:
        return None
    key = str(snapshot.get("key") or "").strip()
    preset_id = f"preset_{key}"
    # A bare preset key has no additional frozen contract to preserve.
    if set(snapshot).issubset({"key", "version", "prompt_hash"}) and (
        preset_id in preset_profiles
    ):
        return None
    anchor = str(
        snapshot.get("narrator_addendum")
        or snapshot.get("prompt")
        or snapshot.get("description")
        or ""
    ).strip()
    if not anchor:
        anchor = json_safe_style_snapshot(snapshot)
    return StyleProfile(
        id="legacy_frozen_style",
        revision=1,
        name="Legacy frozen style",
        base_preset_key=key,
        description="Frozen expression contract migrated from StoryBible.",
        derived_style_anchors=[anchor] if anchor else [],
        deterministic_rules=[
            str(item) for item in snapshot.get("det_rules", []) if str(item).strip()
        ],
        read_only=True,
        source="legacy",
    )


def json_safe_style_snapshot(snapshot: dict[str, Any]) -> str:
    """Return a deterministic compact legacy anchor without executing content."""

    import json

    return json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _default_spec(bible: StoryBible, title: str) -> NovelProductionSpec:
    return NovelProductionSpec(
        title=(title or bible.title or "Untitled novel").strip(),
        premise=(
            bible.premise
            or bible.source_seed
            or "A long-form story awaiting a confirmed premise."
        ),
        genre=bible.genre,
        theme=bible.theme or "Theme awaiting confirmation.",
        central_question=bible.central_question,
        ending_direction=bible.ending_direction,
    )


def ensure_production_domain(
    data_dir: str,
    *,
    title: str = "",
) -> ProductionMigrationReport:
    """Create the production domain once without rewriting legacy authorities."""

    data_dir = os.path.realpath(os.path.abspath(data_dir))
    os.makedirs(data_dir, exist_ok=True)
    ensure_story_domain(data_dir, title=title)
    report_store = ProductionMigrationStore(data_dir)

    bible = StoryBibleStore(data_dir).load()
    preset_profiles = {
        profile.id: profile
        for profile in (
            _profile_from_preset(STYLE_PRESETS[key]) for key in sorted(STYLE_PRESETS)
        )
    }
    legacy = _legacy_profile(bible, preset_profiles)
    if legacy is not None:
        preset_profiles[legacy.id] = legacy

    preferred_key = str(bible.style_contract.get("key") or "literary")
    preferred_id = f"preset_{preferred_key}"
    if legacy is not None:
        active_profile = legacy
    else:
        active_profile = preset_profiles.get(
            preferred_id,
            preset_profiles.get("preset_literary") or next(iter(preset_profiles.values())),
        )

    spec_store = ProductionSpecStore(
        data_dir,
        lambda: _default_spec(bible, title),
    )
    outline_store = BookOutlineStore(data_dir)
    style_store = StyleProfileStore(data_dir)
    active_store = ActiveStyleStore(
        data_dir,
        lambda: ActiveStyleBinding(
            style_profile_id=active_profile.id,
            profile_revision=active_profile.revision,
            prompt_hash=active_profile.prompt_hash,
            profile_snapshot=active_profile,
        ),
    )

    required = {
        "production_spec.json": spec_store,
        "book_outline.json": outline_store,
        "style_profiles.json": style_store,
        "active_style.json": active_store,
    }
    if all(store.exists() for store in required.values()) and report_store.exists():
        # Validation is deliberate: an existing but corrupt document is not current.
        for store in required.values():
            store.load()
        return report_store.load()

    created_files: list[str] = []
    if not style_store.exists():
        style_store.save(StyleProfileCollection(profiles=preset_profiles))
        created_files.append("style_profiles.json")
    else:
        style_store.load()
    if not active_store.exists():
        active_store.save(active_store.load())
        created_files.append("active_style.json")
    else:
        active_store.load()
    if not spec_store.exists():
        spec = spec_store.load().model_copy(
            update={"active_style_profile_id": active_store.load().style_profile_id}
        )
        spec_store.save(spec)
        created_files.append("production_spec.json")
    else:
        spec_store.load()
    if not outline_store.exists():
        outline_store.save(outline_store.load())
        created_files.append("book_outline.json")
    else:
        outline_store.load()

    preserved = [
        filename
        for filename in (
            "story_bible.json",
            "canonical_state.json",
            "story_threads.json",
            "memory_records.json",
            "tick_sections.jsonl",
        )
        if os.path.exists(os.path.join(data_dir, filename))
    ]
    report = ProductionMigrationReport(
        status="created" if created_files else "already_current",
        created_files=created_files,
        preserved_files=preserved,
        active_style_profile_id=active_store.load().style_profile_id,
    )
    report_store.save(report)
    return report


__all__ = [
    "ACTIVE_JOB_STATUSES",
    "ActiveStyleBinding",
    "ActiveStyleStore",
    "BookOutlineStore",
    "GenerationJobStore",
    "PersistenceError",
    "ProductionDocumentStore",
    "ProductionChapterStore",
    "ProductionEvent",
    "ProductionEventLog",
    "ProductionEventStore",
    "ProductionMigrationReport",
    "ProductionSectionAttemptStore",
    "ProductionSpecStore",
    "RevisionConflict",
    "StyleProfileCollection",
    "StyleProfileStore",
    "ensure_production_domain",
]
