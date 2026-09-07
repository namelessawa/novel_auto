"""Stateful chapter generation pipeline.

Orchestration, confirmation and derived retrieval on top of the single official
Author production chain: StoryBible + CanonicalState + StoryThreads feed
``AuthorGenerationService``, which owns the Writer, NarrativeContract,
validator, repair and the atomic commit boundary.
"""

from story.stateful_pipeline.author_bridge import (
    AuthorChapterCommit,
    AuthorCommitMissingError,
    ChapterAnchorMissingError,
    ChapterIntent,
    author_request_id,
    build_section_goal,
    resolve_chapter_intent,
    verify_author_commit,
)
from story.stateful_pipeline.models import (
    AuthorityRevisions,
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
    CommitPendingError,
    ConfirmationRequiredError,
    ConfirmationStaleError,
    PipelineError,
    StatefulPipelineService,
)

__all__ = [
    "AuthorChapterCommit",
    "AuthorCommitMissingError",
    "AuthorityRevisions",
    "ChapterAnchorMissingError",
    "ChapterConfirmation",
    "ChapterGenerationPreference",
    "ChapterInformation",
    "ChapterIntent",
    "ChapterPipelinePhase",
    "ChapterPipelineState",
    "ChapterSynopsis",
    "CommitPendingError",
    "ConfirmationRequiredError",
    "ConfirmationStaleError",
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
    "author_request_id",
    "build_section_goal",
    "resolve_chapter_intent",
    "verify_author_commit",
]
