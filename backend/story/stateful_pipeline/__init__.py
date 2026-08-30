"""Stateful chapter generation pipeline.

Multi-LLM pipeline with deterministic foreshadow selection,
information extraction, and ChromaDB memory integration.
"""

from story.stateful_pipeline.models import (
    ChapterConfirmation,
    ChapterGenerationPreference,
    ChapterInformation,
    ChapterPipelinePhase,
    ChapterPipelineState,
    ChapterSynopsis,
    ForeshadowMode,
    ForeshadowRecord,
    ForeshadowSelectionReceipt,
    ForeshadowSelectionState,
    ForeshadowStatus,
    InformationField,
    InformationSchema,
    MemoryIntegrationRecord,
    SelectionRollResult,
    TransferContext,
)
from story.stateful_pipeline.foreshadow_selection import (
    ForeshadowSelectionService,
)
from story.stateful_pipeline.service import (
    ConfirmationRequiredError,
    PipelineError,
    StatefulPipelineService,
)

__all__ = [
    "ChapterConfirmation",
    "ChapterGenerationPreference",
    "ChapterInformation",
    "ChapterPipelinePhase",
    "ChapterPipelineState",
    "ChapterSynopsis",
    "ConfirmationRequiredError",
    "ForeshadowMode",
    "ForeshadowRecord",
    "ForeshadowSelectionReceipt",
    "ForeshadowSelectionService",
    "ForeshadowSelectionState",
    "ForeshadowStatus",
    "InformationField",
    "InformationSchema",
    "MemoryIntegrationRecord",
    "PipelineError",
    "SelectionRollResult",
    "StatefulPipelineService",
    "TransferContext",
]
