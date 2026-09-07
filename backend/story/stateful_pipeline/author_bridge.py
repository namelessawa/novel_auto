"""Bridge the stateful pipeline into the single official Author production chain.

The pipeline owns confirmation, chapter orchestration and derived retrieval
only.  Prose is planned, written, validated, repaired and committed solely by
:class:`story.service.AuthorGenerationService`.  This module therefore never
touches CanonicalState, StoryThreadRepository, MemoryRepository or the official
section store — it converts a confirmed chapter into a frozen
:class:`~story.models.SectionGoal` and reports the Author commit evidence back.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from story.models import GenerationTransaction, SectionGoal
from story.narrative_contract import LengthConstraint, NarrativeContractInput
from story.production_models import BookOutline, ChapterOutline

# A chapter must be anchored in a durable long-range plan.  Without either a
# user-frozen synopsis or a BookOutline objective the pipeline would degrade
# into local autoregression, so it refuses instead of inventing a goal.
DEFAULT_CHAPTER_LENGTH = 1800
MAX_SECTION_LENGTH = 10_000
MIN_SECTION_LENGTH = 200


class ChapterAnchorMissingError(RuntimeError):
    """A chapter has neither a frozen synopsis nor a BookOutline objective."""


class AuthorCommitMissingError(RuntimeError):
    """The Author chain finished without a verifiable committed manuscript."""


@dataclass(frozen=True)
class ChapterIntent:
    """Resolved long-range goal for one chapter."""

    chapter: int
    objective: str
    title: str
    viewpoint_character_id: str
    location_id: str
    involved_characters: tuple[str, ...]
    target_threads: tuple[str, ...]
    desired_length: int
    narrative_constraints: NarrativeContractInput
    outline_chapter_id: str
    anchors: tuple[str, ...]


def outline_chapter_for(outline: BookOutline | None, chapter: int) -> ChapterOutline | None:
    if outline is None:
        return None
    return next(
        (item for item in outline.chapters if item.ordinal == chapter),
        None,
    )


def _length_band(target: int) -> tuple[int, int, int]:
    desired = max(MIN_SECTION_LENGTH, min(MAX_SECTION_LENGTH, target))
    return (
        max(MIN_SECTION_LENGTH, desired - max(200, desired // 10)),
        desired,
        min(MAX_SECTION_LENGTH, desired + max(300, desired // 10)),
    )


def resolve_chapter_intent(
    *,
    chapter: int,
    synopsis_title: str = "",
    synopsis_text: str = "",
    outline: BookOutline | None = None,
    foreshadow_hint: str = "",
) -> ChapterIntent:
    """Resolve one chapter goal: frozen synopsis + BookOutline anchor.

    The BookOutline objective is the long-range anchor and always contributes
    when the chapter exists there; a user-frozen synopsis refines it.  Falling
    back to a generic "推进第N章剧情" string is deliberately impossible.
    """

    outline_chapter = outline_chapter_for(outline, chapter)
    synopsis_text = synopsis_text.strip()
    foreshadow_hint = foreshadow_hint.strip()
    anchors: list[str] = []
    objective_parts: list[str] = []
    if outline_chapter is not None and outline_chapter.objective.strip():
        objective_parts.append(outline_chapter.objective.strip())
        anchors.append("book_outline")
    if synopsis_text:
        objective_parts.append(f"本章细纲：{synopsis_text}")
        anchors.append("chapter_synopsis")
    if not objective_parts:
        raise ChapterAnchorMissingError(
            f"第 {chapter} 章缺少远期大纲锚点：既没有冻结的章节细纲，"
            f"BookOutline 中也没有本章目标；拒绝生成无锚点章节"
        )
    if foreshadow_hint:
        objective_parts.append(f"本章需呼应的伏笔：{foreshadow_hint}")
        anchors.append("foreshadow_selection")

    if outline_chapter is not None:
        minimum, desired, maximum = _length_band(outline_chapter.target_chars)
        constraints = NarrativeContractInput(
            required_events=list(outline_chapter.required_events),
            required_end_state=list(outline_chapter.required_end_states),
            forbidden_additions=list(outline_chapter.prohibited_additions),
            length_constraint=LengthConstraint(
                min_chars=minimum,
                max_chars=maximum,
            ),
        )
        desired_length = desired
        title = outline_chapter.title
        viewpoint = outline_chapter.viewpoint_character_id
        location = outline_chapter.location_id
        involved = tuple(outline_chapter.involved_characters)
        threads = tuple(outline_chapter.target_threads)
        outline_chapter_id = outline_chapter.id
    else:
        minimum, desired, maximum = _length_band(DEFAULT_CHAPTER_LENGTH)
        constraints = NarrativeContractInput(
            length_constraint=LengthConstraint(
                min_chars=minimum,
                max_chars=maximum,
            ),
        )
        desired_length = desired
        title = synopsis_title
        viewpoint = ""
        location = ""
        involved = ()
        threads = ()
        outline_chapter_id = ""

    return ChapterIntent(
        chapter=chapter,
        objective="\n".join(objective_parts),
        title=title or synopsis_title,
        viewpoint_character_id=viewpoint,
        location_id=location,
        involved_characters=involved,
        target_threads=threads,
        desired_length=desired_length,
        narrative_constraints=constraints,
        outline_chapter_id=outline_chapter_id,
        anchors=tuple(anchors),
    )


def build_section_goal(intent: ChapterIntent) -> SectionGoal:
    """One pipeline chapter maps to one official Author section.

    The section id is deliberately left unset: ``AuthorGenerationService``
    derives it from the production ordinals below.
    """

    return SectionGoal(
        production_chapter_ordinal=intent.chapter,
        production_section_ordinal=1,
        objective=intent.objective,
        viewpoint_character_id=intent.viewpoint_character_id,
        location_id=intent.location_id,
        involved_characters=list(intent.involved_characters),
        target_threads=list(intent.target_threads),
        desired_length=intent.desired_length,
        narrative_constraints=intent.narrative_constraints,
    )


def author_request_id(novel_id: str, chapter: int, attempt: int) -> str:
    """Deterministic transaction id: a replay never starts a second Writer."""

    digest = hashlib.sha256(
        f"pipeline:{novel_id}:{chapter}:{attempt}".encode("utf-8")
    ).hexdigest()[:24]
    return f"pipeline_{digest}"


@dataclass(frozen=True)
class AuthorChapterCommit:
    """Verified evidence that the Author chain really committed this chapter."""

    transaction_id: str
    section_id: str
    committed: bool
    prose: str
    char_count: int
    canonical_revision_before: int
    canonical_revision_after: int
    story_bible_revision: int
    repair_performed: bool
    writer_calls: int
    validation_passed: bool


def verify_author_commit(
    transaction: GenerationTransaction,
    *,
    prose: str,
    canonical_revision_before: int,
) -> AuthorChapterCommit:
    """Fail closed unless the Author journal produced a committed manuscript.

    ``COMMITTING → COMPLETED`` is only legal when every authority the Author
    commit boundary owns actually moved forward and official prose exists.
    """

    if not transaction.committed or transaction.phase != "committed":
        raise AuthorCommitMissingError(
            f"Author transaction {transaction.id} did not commit "
            f"(phase={transaction.phase}, error={transaction.error_code or transaction.error})"
        )
    if not prose.strip():
        raise AuthorCommitMissingError(
            f"Author transaction {transaction.id} committed without official prose"
        )
    if transaction.target_canonical_revision <= canonical_revision_before:
        raise AuthorCommitMissingError(
            "CanonicalState revision did not advance: "
            f"{canonical_revision_before} → {transaction.target_canonical_revision}"
        )
    narrative = transaction.narrative_validation_report
    authority = transaction.validation_report
    if (
        narrative is None
        or not narrative.accepted
        or authority is None
        or not authority.accepted
    ):
        raise AuthorCommitMissingError(
            f"Author transaction {transaction.id} lacks accepted validation evidence"
        )
    return AuthorChapterCommit(
        transaction_id=transaction.id,
        section_id=transaction.section_id,
        committed=True,
        prose=prose,
        char_count=sum(1 for char in prose if not char.isspace()),
        canonical_revision_before=canonical_revision_before,
        canonical_revision_after=transaction.target_canonical_revision,
        story_bible_revision=transaction.story_bible_revision,
        repair_performed=transaction.repair_performed,
        writer_calls=transaction.writer_calls,
        validation_passed=True,
    )


__all__ = [
    "AuthorChapterCommit",
    "AuthorCommitMissingError",
    "ChapterAnchorMissingError",
    "ChapterIntent",
    "author_request_id",
    "build_section_goal",
    "outline_chapter_for",
    "resolve_chapter_intent",
    "verify_author_commit",
]
