"""Atomic, revision-aware persistence for author-mode story data."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel

from story.models import (
    CanonicalState,
    ContextManifest,
    GenerationModeConfig,
    GenerationModeUpdate,
    GenerationTransaction,
    MemoryDiscardManifest,
    MemoryRecord,
    MemoryRepositoryState,
    MemorySelectionManifest,
    MigrationReport,
    StoryBible,
    StoryBibleUpdate,
    StoryThreadRepository,
    utc_now,
)


class PersistenceError(RuntimeError):
    pass


class DataCorruptionError(PersistenceError):
    pass


class RevisionConflict(PersistenceError):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"revision conflict: expected {expected}, actual {actual}")
        self.expected = expected
        self.actual = actual


T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_PERMISSION_RETRY_DELAYS = (0.01, 0.02, 0.04, 0.08)


def _retry_permission_error(operation: Callable[[], R]) -> R:
    """Retry transient Windows sharing violations without hiding real I/O errors."""

    for delay in (*_PERMISSION_RETRY_DELAYS, None):
        try:
            return operation()
        except PermissionError:
            if delay is None:
                raise
            time.sleep(delay)
    raise AssertionError("permission retry loop exhausted without returning")


def _shared_lock(path: str) -> threading.RLock:
    key = os.path.realpath(path)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


class AtomicModelStore(Generic[T]):
    """One validated JSON document with last-good backup and quarantine copies."""

    def __init__(
        self,
        data_dir: str,
        filename: str,
        model_type: type[T],
        default_factory: Callable[[], T],
    ) -> None:
        self.data_dir = os.path.realpath(os.path.abspath(data_dir))
        self.path = os.path.realpath(os.path.join(self.data_dir, filename))
        self.backup_path = self.path + ".bak"
        self.model_type = model_type
        self.default_factory = default_factory
        self.lock = _shared_lock(self.path)
        self._assert_safe(self.path)

    def _assert_safe(self, path: str) -> None:
        if os.path.commonpath([os.path.realpath(path), self.data_dir]) != self.data_dir:
            raise ValueError("story store path escaped novel data directory")

    def exists(self) -> bool:
        return os.path.isfile(self.path)

    def load(self) -> T:
        with self.lock:
            if not os.path.isfile(self.path):
                return self.default_factory()
            try:
                return self._read_validated(self.path)
            except OSError:
                # An inaccessible file is not corrupt.  Never quarantine it or
                # silently fall back to a stale backup revision.
                raise
            except Exception as exc:
                quarantine = self._quarantine_copy(self.path)
                if os.path.isfile(self.backup_path):
                    try:
                        return self._read_validated(self.backup_path)
                    except OSError:
                        raise
                    except Exception:
                        self._quarantine_copy(self.backup_path)
                raise DataCorruptionError(
                    f"{os.path.basename(self.path)} is invalid; preserved at {quarantine}"
                ) from exc

    def save(self, value: T) -> T:
        validated = self.model_type.model_validate(value.model_dump(mode="json"))
        with self.lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            if os.path.isfile(self.path):
                try:
                    self._read_validated(self.path)
                except OSError:
                    raise
                except Exception as exc:
                    quarantine = self._quarantine_copy(self.path)
                    raise DataCorruptionError(
                        f"refusing to overwrite invalid {os.path.basename(self.path)}; "
                        f"preserved at {quarantine}"
                    ) from exc
                self._atomic_copy(self.path, self.backup_path)
            self._atomic_write(validated.model_dump(mode="json"), self.path)
        return validated

    def _read_validated(self, path: str) -> T:
        def read_payload() -> object:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)

        payload = _retry_permission_error(read_payload)
        return self.model_type.model_validate(payload)

    def _atomic_write(self, payload: object, target: str) -> None:
        target_dir = os.path.dirname(target)
        os.makedirs(target_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=f".{os.path.basename(target)}.", suffix=".tmp", dir=target_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            _retry_permission_error(lambda: os.replace(tmp, target))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _atomic_copy(self, source: str, target: str) -> None:
        target_dir = os.path.dirname(target)
        os.makedirs(target_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=f".{os.path.basename(target)}.", suffix=".tmp", dir=target_dir
        )
        os.close(fd)
        try:
            _retry_permission_error(lambda: shutil.copy2(source, tmp))
            _retry_permission_error(lambda: os.replace(tmp, target))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _quarantine_copy(self, source: str) -> str:
        quarantine_dir = os.path.join(self.data_dir, "quarantine")
        os.makedirs(quarantine_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = os.path.join(
            quarantine_dir, f"{os.path.basename(source)}.{stamp}.corrupt"
        )
        _retry_permission_error(lambda: shutil.copy2(source, target))
        return target


class StoryBibleStore(AtomicModelStore[StoryBible]):
    def __init__(self, data_dir: str) -> None:
        super().__init__(data_dir, "story_bible.json", StoryBible, StoryBible)

    def update(self, patch: StoryBibleUpdate) -> StoryBible:
        with self.lock:
            current = self.load()
            if current.revision != patch.expected_revision:
                raise RevisionConflict(patch.expected_revision, current.revision)
            payload = patch.model_dump(exclude={"expected_revision"})
            provenance = dict(current.field_provenance)
            provenance.update({key: "user_input" for key in payload})
            updated = current.model_copy(
                update={
                    **payload,
                    "field_provenance": provenance,
                    "revision": current.revision + 1,
                    "updated_at": utc_now(),
                    "migration": current.migration.model_copy(
                        update={"source": "user_confirmed", "needs_confirmation": False}
                    ),
                }
            )
            return self.save(updated)

    def initialise_from_user_inputs(
        self,
        *,
        title: str,
        source_seed: str,
        theme_key: str,
        theme_label: str,
        positioning: str,
        references: str,
        style_contract: dict,
        preset_seed: bool,
    ) -> StoryBible:
        """Persist bootstrap inputs before any LLM task starts.

        A second identical bootstrap is idempotent.  A different request may
        not overwrite the already confirmed contract; callers must use the
        revision-aware StoryBible PUT endpoint instead.
        """

        with self.lock:
            current = self.load()
            references_list = [references] if references else []
            style_key = str(style_contract.get("key") or "")
            if current.source_seed or current.field_provenance.get("source_seed"):
                existing = (
                    current.title,
                    current.source_seed,
                    current.theme_key,
                    current.positioning,
                    current.reference_preferences,
                    str(current.style_contract.get("key") or ""),
                )
                requested = (
                    title,
                    source_seed,
                    theme_key,
                    positioning,
                    references_list,
                    style_key,
                )
                if existing != requested:
                    raise RevisionConflict(current.revision, current.revision)
                return current

            inferred_fields = [
                "central_question",
                "setting_summary",
                "immutable_world_rules",
                "protagonist_contracts",
                "main_conflicts",
            ]
            if not theme_key:
                inferred_fields.append("theme")
            provenance = {
                "source_seed": "preset_derived" if preset_seed else "user_input",
                "title": "user_input",
                "theme_key": "user_input",
                "positioning": "user_input",
                "reference_preferences": "user_input",
                "style_contract": "preset_derived" if style_key else "user_input",
                "premise": "preset_derived" if preset_seed else "user_input",
            }
            if theme_key:
                provenance["theme"] = "preset_derived"
            bible = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "title": title,
                    "source_seed": source_seed,
                    "theme_key": theme_key,
                    "positioning": positioning,
                    "reference_preferences": references_list,
                    "premise": source_seed,
                    "theme": theme_label or "待从用户种子确认的主题",
                    "setting_summary": current.setting_summary or "待由世界初始化补充的背景。",
                    "style_contract": style_contract,
                    "field_provenance": provenance,
                    "updated_at": utc_now(),
                    "migration": current.migration.model_copy(
                        update={
                            "source": "user_confirmed",
                            "inferred_fields": inferred_fields,
                            "needs_confirmation": True,
                        }
                    ),
                }
            )
            return self.save(bible)

    def update_style(
        self,
        *,
        expected_revision: int,
        style_contract: dict,
        positioning: str,
        references: str,
    ) -> StoryBible:
        with self.lock:
            current = self.load()
            if current.revision != expected_revision:
                raise RevisionConflict(expected_revision, current.revision)
            provenance = dict(current.field_provenance)
            provenance.update(
                {
                    "style_contract": "preset_derived"
                    if style_contract.get("key")
                    else "user_input",
                    "positioning": "user_input",
                    "reference_preferences": "user_input",
                }
            )
            return self.save(
                current.model_copy(
                    update={
                        "revision": current.revision + 1,
                        "style_contract": style_contract,
                        "positioning": positioning,
                        "reference_preferences": [references] if references else [],
                        "field_provenance": provenance,
                        "updated_at": utc_now(),
                    }
                )
            )


class CanonicalStateStore(AtomicModelStore[CanonicalState]):
    def __init__(self, data_dir: str) -> None:
        super().__init__(data_dir, "canonical_state.json", CanonicalState, CanonicalState)

    def save_next(self, value: CanonicalState, expected_revision: int) -> CanonicalState:
        with self.lock:
            current = self.load()
            if current.revision != expected_revision:
                raise RevisionConflict(expected_revision, current.revision)
            if value.revision != expected_revision + 1:
                raise ValueError("canonical state commit must increment revision exactly once")
            return self.save(value)


class StoryThreadStore(AtomicModelStore[StoryThreadRepository]):
    def __init__(self, data_dir: str) -> None:
        super().__init__(
            data_dir,
            "story_threads.json",
            StoryThreadRepository,
            StoryThreadRepository,
        )


@dataclass(frozen=True)
class MemorySelectionResult:
    selected: list[MemoryRecord]
    selections: list[MemorySelectionManifest]
    discarded: list[MemoryDiscardManifest]


def _canonical_value(state: CanonicalState, path: str):
    value = state.model_dump(mode="python")
    for raw in path.strip("/").split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or key not in value:
            return None, False
        value = value[key]
    return value, True


def _memory_conflicts(
    record: MemoryRecord,
    state: CanonicalState | None,
) -> list[str]:
    if state is None:
        return []
    conflicts: list[str] = []
    for claim in record.canonical_claims:
        actual, exists = _canonical_value(state, claim.path)
        if not exists:
            conflicts.append(claim.path)
            continue
        if claim.operator == "contains":
            if isinstance(actual, dict):
                matched = claim.expected in actual or claim.expected in actual.values()
            elif isinstance(actual, (list, tuple, set, str)):
                matched = claim.expected in actual
            else:
                matched = False
        else:
            matched = actual == claim.expected
        if not matched:
            conflicts.append(claim.path)
    return conflicts


class MemoryRepository(AtomicModelStore[MemoryRepositoryState]):
    def __init__(self, data_dir: str) -> None:
        super().__init__(
            data_dir,
            "memory_records.json",
            MemoryRepositoryState,
            MemoryRepositoryState,
        )

    def recent(self, limit: int = 8) -> list:
        records = list(self.load().records.values())
        records.sort(key=lambda item: (item.created_at_revision, item.importance), reverse=True)
        return records[: max(0, limit)]

    def relevant(self, entity_ids: set[str], thread_ids: set[str], limit: int = 12) -> list:
        return self.select_relevant(
            entity_ids,
            thread_ids,
            canonical_state=None,
            canonical_revision=None,
            limit=limit,
        ).selected

    def select_relevant(
        self,
        entity_ids: set[str],
        thread_ids: set[str],
        *,
        canonical_state: CanonicalState | None,
        canonical_revision: int | None,
        limit: int = 12,
    ) -> MemorySelectionResult:
        candidates = []
        discarded: list[MemoryDiscardManifest] = []
        for record in self.load().records.values():
            if record.canon_status != "confirmed":
                discarded.append(
                    MemoryDiscardManifest(
                        memory_id=record.id,
                        reason=f"canon_status_{record.canon_status}",
                        memory_revision=record.created_at_revision,
                        canon_status=record.canon_status,
                    )
                )
                continue
            if (
                canonical_revision is not None
                and record.created_at_revision > canonical_revision
            ):
                discarded.append(
                    MemoryDiscardManifest(
                        memory_id=record.id,
                        reason="future_canonical_revision",
                        memory_revision=record.created_at_revision,
                        canon_status=record.canon_status,
                    )
                )
                continue
            conflicts = _memory_conflicts(record, canonical_state)
            if conflicts:
                discarded.append(
                    MemoryDiscardManifest(
                        memory_id=record.id,
                        reason="canonical_conflict",
                        memory_revision=record.created_at_revision,
                        canon_status=record.canon_status,
                        conflicting_paths=conflicts,
                    )
                )
                continue
            matched_entities = sorted(entity_ids.intersection(record.entities))
            matched_threads = sorted(thread_ids.intersection(record.source_refs))
            overlap = len(matched_entities)
            thread_overlap = len(matched_threads)
            score = record.importance * 10 + overlap * 25 + thread_overlap * 30
            if overlap or thread_overlap or record.importance >= 8:
                reasons = []
                if matched_entities:
                    reasons.append("entity_match")
                if matched_threads:
                    reasons.append("thread_match")
                if record.importance >= 8:
                    reasons.append("high_importance")
                candidates.append(
                    (
                        score,
                        record.created_at_revision,
                        record.id,
                        record,
                        MemorySelectionManifest(
                            memory_id=record.id,
                            selection_reason="+".join(reasons),
                            matched_entities=matched_entities,
                            matched_threads=matched_threads,
                            memory_revision=record.created_at_revision,
                            canon_status=record.canon_status,
                            score=score,
                        ),
                    )
                )
            else:
                discarded.append(
                    MemoryDiscardManifest(
                        memory_id=record.id,
                        reason="not_relevant",
                        memory_revision=record.created_at_revision,
                        canon_status=record.canon_status,
                    )
                )
        candidates.sort(reverse=True)
        selected_rows = candidates[: max(0, limit)]
        for row in candidates[max(0, limit) :]:
            discarded.append(
                MemoryDiscardManifest(
                    memory_id=row[3].id,
                    reason="rank_limit",
                    memory_revision=row[3].created_at_revision,
                    canon_status=row[3].canon_status,
                )
            )
        discarded.sort(key=lambda item: (item.reason, item.memory_id))
        return MemorySelectionResult(
            selected=[row[3] for row in selected_rows],
            selections=[row[4] for row in selected_rows],
            discarded=discarded,
        )


class GenerationModeStore(AtomicModelStore[GenerationModeConfig]):
    def __init__(self, data_dir: str) -> None:
        def _default() -> GenerationModeConfig:
            requested = os.environ.get("GENERATION_MODE", "author").strip().lower()
            mode = requested if requested in {"author", "simulation"} else "author"
            return GenerationModeConfig(mode=mode)

        super().__init__(
            data_dir, "generation_mode.json", GenerationModeConfig, _default
        )

    def update(self, patch: GenerationModeUpdate) -> GenerationModeConfig:
        with self.lock:
            current = self.load()
            if current.revision != patch.expected_revision:
                raise RevisionConflict(patch.expected_revision, current.revision)
            return self.save(
                current.model_copy(
                    update={
                        "mode": patch.mode,
                        "revision": current.revision + 1,
                        "updated_at": utc_now(),
                    }
                )
            )


class ContextManifestStore(AtomicModelStore[ContextManifest]):
    def __init__(self, data_dir: str, novel_id: str = "unknown") -> None:
        super().__init__(
            data_dir,
            "context_manifest.json",
            ContextManifest,
            lambda: ContextManifest(
                novel_id=novel_id,
                section_id="none",
                story_bible_revision=1,
                canonical_state_revision=1,
                total_chars=0,
                total_token_estimate=0,
                max_context_chars=0,
                max_context_token_estimate=0,
            ),
        )


class MigrationReportStore(AtomicModelStore[MigrationReport]):
    def __init__(self, data_dir: str) -> None:
        super().__init__(
            data_dir,
            "story_migration.json",
            MigrationReport,
            lambda: MigrationReport(status="created"),
        )


class GenerationTransactionStore:
    _ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,96}$")

    def __init__(self, data_dir: str) -> None:
        self.data_dir = os.path.realpath(os.path.abspath(data_dir))
        self.root = os.path.join(self.data_dir, "generation_transactions")

    def _store(self, transaction_id: str) -> AtomicModelStore[GenerationTransaction]:
        if not self._ID_RE.match(transaction_id):
            raise ValueError("invalid generation transaction id")
        return AtomicModelStore(
            self.data_dir,
            os.path.join("generation_transactions", f"{transaction_id}.json"),
            GenerationTransaction,
            lambda: (_ for _ in ()).throw(KeyError(transaction_id)),
        )

    def exists(self, transaction_id: str) -> bool:
        return self._store(transaction_id).exists()

    def load(self, transaction_id: str) -> GenerationTransaction:
        if not self.exists(transaction_id):
            raise KeyError(transaction_id)
        return self._store(transaction_id).load()

    def save(self, transaction: GenerationTransaction) -> GenerationTransaction:
        return self._store(transaction.id).save(transaction)

    def list_pending(self) -> list[GenerationTransaction]:
        if not os.path.isdir(self.root):
            return []
        pending: list[GenerationTransaction] = []
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json") or name.endswith(".bak"):
                continue
            transaction_id = name[:-5]
            try:
                tx = self.load(transaction_id)
            except (KeyError, PersistenceError, ValueError):
                continue
            if tx.phase in {"validated", "committing"} and not tx.committed:
                pending.append(tx)
        return pending

    def list_all(self) -> list[GenerationTransaction]:
        if not os.path.isdir(self.root):
            return []
        transactions: list[GenerationTransaction] = []
        for name in sorted(os.listdir(self.root)):
            if not name.endswith(".json") or name.endswith(".bak"):
                continue
            try:
                transactions.append(self.load(name[:-5]))
            except (KeyError, PersistenceError, ValueError):
                continue
        return transactions


__all__ = [
    "AtomicModelStore",
    "CanonicalStateStore",
    "ContextManifestStore",
    "DataCorruptionError",
    "GenerationModeStore",
    "GenerationTransactionStore",
    "MemoryRepository",
    "MigrationReportStore",
    "PersistenceError",
    "RevisionConflict",
    "StoryBibleStore",
    "StoryThreadStore",
]
