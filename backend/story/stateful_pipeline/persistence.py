"""Persistence layer for stateful pipeline data.

Uses the same AtomicModelStore pattern as the main story persistence.
All files are stored in the novel's data directory under 'pipeline/' subdirectory.
"""

from __future__ import annotations

import json
import os

from story.stateful_pipeline.models import (
    ChapterInformation,
    ChapterPipelineState,
    ChapterSynopsis,
    ForeshadowRecord,
    ForeshadowSelectionReceipt,
    ForeshadowSelectionState,
    InformationSchema,
    MemoryIntegrationRecord,
    TransferContext,
)


class PipelineStoreError(RuntimeError):
    pass


def _remove_file(path: str) -> None:
    """Delete one derived artifact if present (explicit retry purge only)."""

    if os.path.isfile(path):
        os.remove(path)


# ---------------------------------------------------------------------------
# Synopsis Store
# ---------------------------------------------------------------------------


class SynopsisStore:
    """Store chapter synopses (first two chapters have dedicated synopsis)."""

    def __init__(self, data_dir: str):
        self._dir = os.path.join(data_dir, "pipeline")
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, chapter: int) -> str:
        return os.path.join(self._dir, f"synopsis_ch{chapter}.json")

    def load(self, novel_id: str, chapter: int) -> ChapterSynopsis | None:
        path = self._path(chapter)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return ChapterSynopsis.model_validate(data)

    def save(self, synopsis: ChapterSynopsis) -> ChapterSynopsis:
        path = self._path(synopsis.chapter_number)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(synopsis.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        return synopsis

    def load_all(self, novel_id: str) -> list[ChapterSynopsis]:
        """Load all existing synopses."""
        results = []
        if not os.path.isdir(self._dir):
            return results
        for fname in sorted(os.listdir(self._dir)):
            if fname.startswith("synopsis_ch") and fname.endswith(".json"):
                try:
                    chapter = int(fname.replace("synopsis_ch", "").replace(".json", ""))
                    s = self.load(novel_id, chapter)
                    if s:
                        results.append(s)
                except (ValueError, Exception):
                    continue
        return results


# ---------------------------------------------------------------------------
# Information Schema Store
# ---------------------------------------------------------------------------


class InformationSchemaStore:
    """Store the information extraction schema (one per novel)."""

    def __init__(self, data_dir: str):
        self._dir = os.path.join(data_dir, "pipeline")
        os.makedirs(self._dir, exist_ok=True)

    def _path(self) -> str:
        return os.path.join(self._dir, "information_schema.json")

    def load(self, novel_id: str) -> InformationSchema | None:
        path = self._path()
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return InformationSchema.model_validate(data)

    def save(self, schema: InformationSchema) -> InformationSchema:
        path = self._path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(schema.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        return schema


# ---------------------------------------------------------------------------
# Foreshadow Store
# ---------------------------------------------------------------------------


class ForeshadowStore:
    """Store foreshadow records and selection state."""

    def __init__(self, data_dir: str):
        self._dir = os.path.join(data_dir, "pipeline")
        os.makedirs(self._dir, exist_ok=True)

    def _records_path(self) -> str:
        return os.path.join(self._dir, "foreshadows.json")

    def _state_path(self) -> str:
        return os.path.join(self._dir, "foreshadow_state.json")

    def _receipt_path(self, chapter: int) -> str:
        return os.path.join(self._dir, f"foreshadow_receipt_ch{chapter}.json")

    def load_records(self, novel_id: str) -> list[ForeshadowRecord]:
        path = self._records_path()
        if not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [ForeshadowRecord.model_validate(r) for r in data]

    def save_records(self, records: list[ForeshadowRecord]) -> None:
        path = self._records_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump(mode="json") for r in records], f, ensure_ascii=False, indent=2)

    def load_state(self, novel_id: str) -> ForeshadowSelectionState:
        path = self._state_path()
        if not os.path.isfile(path):
            return ForeshadowSelectionState(novel_id=novel_id)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return ForeshadowSelectionState.model_validate(data)

    def save_state(self, state: ForeshadowSelectionState) -> None:
        path = self._state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    def load_receipt(self, novel_id: str, chapter: int) -> ForeshadowSelectionReceipt | None:
        path = self._receipt_path(chapter)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return ForeshadowSelectionReceipt.model_validate(data)

    def save_receipt(self, receipt: ForeshadowSelectionReceipt) -> None:
        path = self._receipt_path(receipt.chapter)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(receipt.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    def delete_receipt(self, novel_id: str, chapter: int) -> None:
        _remove_file(self._receipt_path(chapter))


# ---------------------------------------------------------------------------
# Chapter Information Store
# ---------------------------------------------------------------------------


class ChapterInformationStore:
    """Store extracted chapter information."""

    def __init__(self, data_dir: str):
        self._dir = os.path.join(data_dir, "pipeline", "information")
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, chapter: int) -> str:
        return os.path.join(self._dir, f"chapter_{chapter}.json")

    def load(self, novel_id: str, chapter: int) -> ChapterInformation | None:
        path = self._path(chapter)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return ChapterInformation.model_validate(data)

    def save(self, info: ChapterInformation) -> ChapterInformation:
        path = self._path(info.chapter_number)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(info.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        return info

    def load_recent(self, novel_id: str, chapter: int, count: int = 3) -> list[ChapterInformation]:
        """Load the most recent N committed chapter informations."""
        results = []
        for ch in range(max(1, chapter - count), chapter):
            info = self.load(novel_id, ch)
            if info:
                results.append(info)
        return results

    def delete(self, novel_id: str, chapter: int) -> None:
        _remove_file(self._path(chapter))


# ---------------------------------------------------------------------------
# Transfer Context Store
# ---------------------------------------------------------------------------


class TransferContextStore:
    """Store transfer context for chapters."""

    def __init__(self, data_dir: str):
        self._dir = os.path.join(data_dir, "pipeline")
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, chapter: int) -> str:
        return os.path.join(self._dir, f"transfer_ch{chapter}.json")

    def load(self, novel_id: str, chapter: int) -> TransferContext | None:
        path = self._path(chapter)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return TransferContext.model_validate(data)

    def save(self, ctx: TransferContext) -> TransferContext:
        path = self._path(ctx.target_chapter)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ctx.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        return ctx

    def delete(self, novel_id: str, chapter: int) -> None:
        _remove_file(self._path(chapter))


# ---------------------------------------------------------------------------
# Pipeline State Store
# ---------------------------------------------------------------------------


class PipelineStateStore:
    """Store current chapter pipeline state."""

    def __init__(self, data_dir: str):
        self._dir = os.path.join(data_dir, "pipeline")
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, chapter: int) -> str:
        return os.path.join(self._dir, f"pipeline_state_ch{chapter}.json")

    def load(self, novel_id: str, chapter: int) -> ChapterPipelineState | None:
        path = self._path(chapter)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return ChapterPipelineState.model_validate(data)

    def save(self, state: ChapterPipelineState) -> ChapterPipelineState:
        path = self._path(state.chapter_number)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        return state

    def get_current_chapter(self, novel_id: str) -> int:
        """Determine the current chapter number (highest pipeline state or 1)."""
        if not os.path.isdir(self._dir):
            return 1
        max_chapter = 0
        for fname in os.listdir(self._dir):
            if fname.startswith("pipeline_state_ch") and fname.endswith(".json"):
                try:
                    ch = int(fname.replace("pipeline_state_ch", "").replace(".json", ""))
                    max_chapter = max(max_chapter, ch)
                except ValueError:
                    continue
        return max_chapter + 1 if max_chapter > 0 else 1


# ---------------------------------------------------------------------------
# Memory Integration Store
# ---------------------------------------------------------------------------


class MemoryIntegrationStore:
    """Store memory integration records (what was written to ChromaDB)."""

    def __init__(self, data_dir: str):
        self._dir = os.path.join(data_dir, "pipeline", "integration")
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, chapter: int) -> str:
        return os.path.join(self._dir, f"integration_ch{chapter}.json")

    def load(self, novel_id: str, chapter: int) -> MemoryIntegrationRecord | None:
        path = self._path(chapter)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return MemoryIntegrationRecord.model_validate(data)

    def save(self, record: MemoryIntegrationRecord) -> MemoryIntegrationRecord:
        path = self._path(record.chapter_number)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        return record

    def delete(self, novel_id: str, chapter: int) -> None:
        _remove_file(self._path(chapter))


# ---------------------------------------------------------------------------
# Pacing Store
# ---------------------------------------------------------------------------


class PacingStore:
    """Store pacing state and per-chapter pacing receipts."""

    def __init__(self, data_dir: str):
        self._dir = os.path.join(data_dir, "pipeline")
        os.makedirs(self._dir, exist_ok=True)

    def _state_path(self) -> str:
        return os.path.join(self._dir, "pacing_state.json")

    def _receipt_path(self, chapter: int) -> str:
        return os.path.join(self._dir, f"pacing_receipt_ch{chapter}.json")

    def load_state(self, novel_id: str):
        from story.stateful_pipeline.pacing import PacingState

        path = self._state_path()
        if not os.path.isfile(path):
            return PacingState(novel_id=novel_id)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return PacingState.model_validate(data)

    def save_state(self, state) -> None:
        path = self._state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    def load_receipt(self, novel_id: str, chapter: int):
        from story.stateful_pipeline.pacing import PacingReceipt

        path = self._receipt_path(chapter)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return PacingReceipt.model_validate(data)

    def save_receipt(self, receipt) -> None:
        path = self._receipt_path(receipt.chapter)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(receipt.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
