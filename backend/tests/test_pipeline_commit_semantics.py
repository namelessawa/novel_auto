"""P0-2 / P0-8: COMMITTING is a real Author commit, COMPLETED is earned.

These tests pin the commit boundary: the pipeline may only report COMPLETED
after the Author transaction journal, the official manuscript and the advanced
authorities were all re-read from disk.  Anything less ends in FAILED, and a
crash after the Author commit replays without paying for a second Writer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sections.section_store import _clear_for_tests
from story.models import GenerationTransaction
from story.persistence import (
    CanonicalStateStore,
    MemoryRepository,
    StoryThreadStore,
)
from story.service import AuthorGenerationService
from story.stateful_pipeline.author_bridge import (
    AuthorCommitMissingError,
    verify_author_commit,
)
from story.stateful_pipeline.chroma_repository import ChromaMemoryRepository
from story.stateful_pipeline.models import ChapterPipelinePhase
from story.stateful_pipeline.persistence import PipelineStateStore
from story.stateful_pipeline.service import (
    PipelineError,
    StatefulPipelineService,
)

from tests.test_pipeline_author_bridge import (
    NOVEL_ID,
    USER_ID,
    RecordingWriter,
    _preference,
    _publish_bible,
    _seed_canon,
    _seed_outline,
    _seed_thread,
)


@pytest.fixture(autouse=True)
def clear_sections():
    _clear_for_tests()
    yield
    _clear_for_tests()


@pytest.fixture
def env(tmp_path: Path):
    data_dir = str(tmp_path)
    writer = RecordingWriter()
    author = AuthorGenerationService(
        user_id=USER_ID,
        novel_id=NOVEL_ID,
        data_dir=data_dir,
        title="铜钥匙",
        writer=writer,
        enable_llm_planner=False,
    )
    _publish_bible(author)
    _seed_canon(data_dir)
    _seed_thread(data_dir)
    _seed_outline(data_dir, "铜钥匙")
    service = StatefulPipelineService(
        data_dir=data_dir,
        chroma_repo=ChromaMemoryRepository(persist_dir=str(tmp_path / "chroma")),
    )
    return {
        "data_dir": data_dir,
        "service": service,
        "author": author,
        "writer": writer,
    }


# ---------------------------------------------------------------------------
# COMPLETED is backed by the Author journal, the manuscript and the authorities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completed_requires_verified_author_commit(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]
    data_dir = env["data_dir"]

    canon_before = CanonicalStateStore(data_dir).load().revision
    threads_before = StoryThreadStore(data_dir).load().revision
    memories_before = MemoryRepository(data_dir).load().revision

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    result = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    assert result.phase == ChapterPipelinePhase.COMPLETED
    assert result.committed_manuscript is True

    transaction = author.transactions.load(result.author_transaction_id)
    assert isinstance(transaction, GenerationTransaction)
    assert transaction.committed is True
    assert transaction.phase == "committed"
    assert transaction.section_id == result.committed_section_id

    section = author.sections.get_by_id(result.committed_section_id)
    assert section is not None
    assert section.transaction_id == result.author_transaction_id
    assert section.word_count == result.committed_char_count

    assert CanonicalStateStore(data_dir).load().revision == canon_before + 1
    assert StoryThreadStore(data_dir).load().revision >= threads_before
    assert MemoryRepository(data_dir).load().revision >= memories_before


# ---------------------------------------------------------------------------
# A rejected candidate ends in FAILED, never COMPLETED, and mutates nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejected_candidate_fails_without_touching_authorities(tmp_path: Path):
    data_dir = str(tmp_path)
    writer = RecordingWriter(violate_contract=True)
    author = AuthorGenerationService(
        user_id=USER_ID,
        novel_id=NOVEL_ID,
        data_dir=data_dir,
        title="铜钥匙",
        writer=writer,
        enable_llm_planner=False,
    )
    _publish_bible(author)
    _seed_canon(data_dir)
    _seed_thread(data_dir)
    _seed_outline(data_dir, "铜钥匙")
    service = StatefulPipelineService(
        data_dir=data_dir,
        chroma_repo=ChromaMemoryRepository(persist_dir=str(tmp_path / "chroma")),
    )

    canon_before = CanonicalStateStore(data_dir).load()
    threads_before = StoryThreadStore(data_dir).load()

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    result = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    # COMMITTING must never degrade into COMPLETED without a manuscript.
    assert result.phase == ChapterPipelinePhase.FAILED
    assert result.committed_manuscript is False
    assert result.committed_section_id == ""
    assert result.committed_char_count == 0
    assert result.committed_canonical_revision is None
    assert result.error_message

    assert author.sections.count() == 0
    assert CanonicalStateStore(data_dir).load().revision == canon_before.revision
    assert StoryThreadStore(data_dir).load().revision == threads_before.revision


@pytest.mark.asyncio
async def test_derived_stage_failure_never_reports_completed(env, monkeypatch):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    async def _boom(*args, **kwargs):
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr(service, "_integrate_memory", _boom)

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    result = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    assert result.phase == ChapterPipelinePhase.FAILED
    assert "chroma unavailable" in (result.error_message or "")
    assert result.committed_section_id == ""
    assert env["writer"].generate_calls == 1


# ---------------------------------------------------------------------------
# Crash recovery: replay after the Author commit costs no second Writer call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_after_author_commit_never_rewrites(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]
    data_dir = env["data_dir"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    first = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert first.phase == ChapterPipelinePhase.COMPLETED
    prose = author.sections.get_by_id(first.committed_section_id).content
    canon_after = CanonicalStateStore(data_dir).load().revision

    # Simulate a crash that lost the pipeline state right before the final
    # verification: the Author journal already committed this attempt.
    store = PipelineStateStore(data_dir)
    store.save(
        first.model_copy(
            update={
                "phase": ChapterPipelinePhase.COMMITTING,
                "committed_section_id": "",
                "committed_char_count": 0,
                "committed_canonical_revision": None,
                "committed_at": None,
            }
        )
    )

    replayed = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    assert replayed.phase == ChapterPipelinePhase.COMPLETED
    assert replayed.committed_manuscript is True
    assert replayed.author_transaction_id == first.author_transaction_id
    assert replayed.committed_section_id == first.committed_section_id
    # No second Writer call and no second CanonicalState mutation.
    assert env["writer"].generate_calls == 1
    assert CanonicalStateStore(data_dir).load().revision == canon_after
    assert author.sections.get_by_id(replayed.committed_section_id).content == prose
    assert len(author.transactions.list_all()) == 1


# ---------------------------------------------------------------------------
# verify_author_commit fails closed on every missing piece of evidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_author_commit_rejects_incomplete_evidence(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    result = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    transaction = author.transactions.load(result.author_transaction_id)
    prose = author.sections.get_by_id(result.committed_section_id).content
    base = result.committed_canonical_revision - 1

    commit = verify_author_commit(transaction, prose=prose, canonical_revision_before=base)
    assert commit.committed is True
    assert commit.canonical_revision_after == base + 1

    with pytest.raises(AuthorCommitMissingError):
        verify_author_commit(transaction, prose="   ", canonical_revision_before=base)
    with pytest.raises(AuthorCommitMissingError):
        verify_author_commit(transaction, prose=prose, canonical_revision_before=base + 1)
    with pytest.raises(AuthorCommitMissingError):
        verify_author_commit(
            transaction.model_copy(update={"committed": False, "phase": "validated"}),
            prose=prose,
            canonical_revision_before=base,
        )
    with pytest.raises(AuthorCommitMissingError):
        verify_author_commit(
            transaction.model_copy(update={"validation_report": None}),
            prose=prose,
            canonical_revision_before=base,
        )


# ---------------------------------------------------------------------------
# A COMPLETED record whose manuscript vanished cannot be replayed as success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completed_without_readable_manuscript_fails_closed(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]
    data_dir = env["data_dir"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    first = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert first.phase == ChapterPipelinePhase.COMPLETED

    author.sections.remove_by_transaction_id(first.author_transaction_id)

    with pytest.raises(PipelineError):
        await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert env["writer"].generate_calls == 1
    # The stale COMPLETED record is still what is persisted; only an explicit
    # retry may produce a new attempt.
    assert PipelineStateStore(data_dir).load(NOVEL_ID, 1).phase == (
        ChapterPipelinePhase.COMPLETED
    )


@pytest.mark.asyncio
async def test_committed_prose_is_available_through_the_service(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    result = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    prose = service.committed_chapter_prose(NOVEL_ID, 1, author)
    assert prose.strip()
    assert prose == author.sections.get_by_id(result.committed_section_id).content
    assert service.committed_chapter_prose(NOVEL_ID, 2, author) == ""


@pytest.mark.asyncio
async def test_writer_is_never_called_twice_for_one_attempt(env):
    """One attempt = one Writer call on the official Author chain."""

    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]
    writer: RecordingWriter = env["writer"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    result = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert result.phase == ChapterPipelinePhase.COMPLETED

    transaction = author.transactions.load(result.author_transaction_id)
    assert transaction.writer_calls == 1
    assert writer.generate_calls == 1
