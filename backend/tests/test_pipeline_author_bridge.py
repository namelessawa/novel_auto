"""P0 bridge tests: the stateful pipeline must run on Author production.

Every assertion here is about the *official* chain: the pipeline hands a frozen
chapter goal to ``AuthorGenerationService``, and only a verified Author commit
may produce ``COMPLETED``.  No real provider is used — a recording Writer stands
in for ``AuthorWriter`` while every validator, repair gate and the transaction
journal stay real.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sections.section_store import _clear_for_tests
from story.models import (
    MemoryRecord,
    StateDeltaOperation,
    StoryBibleUpdate,
    StoryThread,
    WriterCandidate,
)
from story.persistence import CanonicalStateStore, StoryThreadStore
from story.production_models import BookOutlineUpdate, ChapterOutline, VolumeOutline
from story.production_persistence import BookOutlineStore, ensure_production_domain
from story.service import AuthorGenerationService
from story.stateful_pipeline.chroma_repository import ChromaMemoryRepository
from story.stateful_pipeline.models import (
    ChapterGenerationPreference,
    ChapterPipelinePhase,
    ForeshadowMode,
)
from story.stateful_pipeline.persistence import PipelineStateStore
from story.stateful_pipeline.service import (
    ConfirmationRequiredError,
    PipelineError,
    StatefulPipelineService,
)
from story.writer import WriterResult

NOVEL_ID = "pipeline-novel"
USER_ID = "alice"

CHAPTER_OBJECTIVES = {
    1: "陈晨清点旧仓库留下的钥匙",
    2: "陈晨向房东追问储物柜的来历",
    3: "陈晨必须第一次使用铜钥匙打开储物柜",
}

PAD_SENTENCE = "陈晨把注意力收回眼前，逐条核对已经发生过的事情，没有急着下结论。"


@pytest.fixture(autouse=True)
def clear_sections():
    _clear_for_tests()
    yield
    _clear_for_tests()


class RecordingWriter:
    """Stand-in for AuthorWriter that records the frozen Author context."""

    def __init__(self, *, violate_contract: bool = False) -> None:
        self.violate_contract = violate_contract
        self.contexts: list = []
        self.goals: list = []
        self.generate_calls = 0
        self.repair_calls = 0

    async def generate(self, context, goal):
        self.generate_calls += 1
        self.contexts.append(context)
        self.goals.append(goal)
        return WriterResult(
            self._candidate(goal),
            {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        )

    async def repair(self, candidate, report):
        self.repair_calls += 1
        return WriterResult(
            candidate,
            {"prompt_tokens": 4, "completion_tokens": 4, "total_tokens": 8},
        )

    def _candidate(self, goal) -> WriterCandidate:
        # Echoing the objective keeps the deterministic event matcher satisfied
        # without weakening any validator.
        anchor = goal.objective.splitlines()[0]
        if self.violate_contract:
            narrative = "一段与本章目标完全无关的文字。" * 60
        else:
            narrative = f"{anchor}。"
            while len(narrative) < goal.desired_length:
                narrative += PAD_SENTENCE
        return WriterCandidate(
            narrative_text=narrative,
            title=anchor[:12],
            section_summary=anchor[:40],
            state_delta=[
                StateDeltaOperation(
                    op="set",
                    path="/characters/chen_chen/status",
                    value="holding_copper_key",
                    evidence=anchor,
                    confidence=1.0,
                )
            ],
            threads_advanced=[
                StoryThread(
                    id="thread_copper_key",
                    description="铜钥匙与储物柜的来历",
                    evidence=[anchor],
                )
            ],
            memory_records=[
                MemoryRecord(
                    id=f"memory_{goal.section_id}",
                    summary=anchor[:60],
                    evidence=anchor,
                    entities=["chen_chen"],
                )
            ],
        )


def _publish_bible(author: AuthorGenerationService) -> None:
    bible = author.bibles.load()
    author.bibles.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            title="铜钥匙",
            premise="陈晨在旧仓库继承了一把来历不明的铜钥匙。",
            theme="记忆与继承",
            central_question="被藏起来的过去是否应该被打开？",
            genre="都市悬疑",
            setting_summary="一座旧城区仓库改建的出租楼，共五层。",
            immutable_world_rules=["死亡不可逆", "出租楼只有五层"],
            forbidden_deviations=["不得引入超自然力量"],
            protagonist_contracts=["陈晨是女性，三十二岁，仓库管理员"],
            main_conflicts=["陈晨与房东之间关于储物柜归属的争执"],
            ending_direction="陈晨打开储物柜并承担其中的真相。",
        )
    )


def _seed_canon(data_dir: str) -> None:
    store = CanonicalStateStore(data_dir)
    canon = store.load()
    updated = canon.model_copy(
        update={
            "revision": canon.revision + 1,
            "characters": {
                "chen_chen": {
                    "name": "陈晨",
                    "gender": "female",
                    "role": "protagonist",
                    "status": "active",
                },
                "landlord": {
                    "name": "周房东",
                    "gender": "male",
                    "role": "antagonist",
                    "status": "active",
                },
            },
            "world": {
                "locations": [
                    {"id": "warehouse", "name": "旧仓库", "floor_count": 5},
                ]
            },
            "relationships": {
                "chen_chen|landlord": {"description": "租户与房东，彼此不信任"}
            },
        }
    )
    store.save_next(updated, expected_revision=canon.revision)


def _seed_thread(data_dir: str) -> None:
    store = StoryThreadStore(data_dir)
    repository = store.load()
    thread = StoryThread(
        id="thread_copper_key",
        type="mystery",
        description="铜钥匙与储物柜的来历",
        promised_question="储物柜里到底藏着什么？",
        involved_characters=["chen_chen", "landlord"],
        status="open",
        advance_condition="陈晨使用铜钥匙打开储物柜",
    )
    repository = repository.model_copy(
        update={"threads": {**repository.threads, thread.id: thread}}
    )
    store.save(repository)


def _seed_outline(data_dir: str, title: str) -> None:
    ensure_production_domain(data_dir, title=title)
    store = BookOutlineStore(data_dir)
    chapters = [
        ChapterOutline(
            id=f"ch{ordinal:03d}",
            ordinal=ordinal,
            volume_id="vol_1",
            title=f"第{ordinal}章",
            objective=CHAPTER_OBJECTIVES[ordinal],
            viewpoint_character_id="chen_chen",
            location_id="warehouse",
            involved_characters=["chen_chen", "landlord"],
            target_threads=["thread_copper_key"],
            target_chars=600,
        )
        for ordinal in (1, 2, 3)
    ]
    current = store.load()
    store.update(
        BookOutlineUpdate(
            expected_revision=current.revision,
            volumes=[
                VolumeOutline(
                    id="vol_1",
                    ordinal=1,
                    title="第一卷",
                    objective="陈晨继承铜钥匙并追查储物柜",
                    target_chapters=3,
                    target_chars=1800,
                )
            ],
            chapters=chapters,
            status="ready",
        )
    )


@pytest.fixture
def env(tmp_path: Path):
    data_dir = str(tmp_path)
    chroma_dir = str(tmp_path / "chroma")
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
        chroma_repo=ChromaMemoryRepository(persist_dir=chroma_dir),
    )
    return {
        "data_dir": data_dir,
        "service": service,
        "author": author,
        "writer": writer,
    }


def _preference(chapter: int) -> ChapterGenerationPreference:
    return ChapterGenerationPreference(
        novel_id=NOVEL_ID,
        chapter_number=chapter,
        foreshadow_mode=ForeshadowMode.FIXED,
        foreshadow_fixed_count=0,
    )


# ---------------------------------------------------------------------------
# 1 + 3: confirm → generate → real committed manuscript
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_then_generate_commits_official_manuscript(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    confirmation = service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    state = service.get_pipeline_state(NOVEL_ID, 1)
    assert state is not None
    assert state.phase == ChapterPipelinePhase.CONFIRMED
    assert confirmation.story_bible_revision >= 2
    assert confirmation.outline_revision >= 2

    result = await service.run_chapter_pipeline(
        NOVEL_ID, 1, author_service=author
    )

    assert result.phase == ChapterPipelinePhase.COMPLETED
    # P0-2: COMPLETED is backed by the Author commit journal, not the phase.
    assert result.committed_manuscript is True
    assert result.author_transaction_id
    assert result.committed_char_count > 0

    transaction = author.transactions.load(result.author_transaction_id)
    assert transaction.committed is True
    assert transaction.phase == "committed"

    section = author.sections.get_by_id(result.committed_section_id)
    assert section is not None
    assert section.content.strip()
    assert section.generation_mode == "author"
    assert section.chapter == 1
    assert env["writer"].generate_calls == 1


# ---------------------------------------------------------------------------
# 2: no confirmation → no Writer call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generation_without_confirmation_never_calls_writer(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    with pytest.raises(ConfirmationRequiredError):
        await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    with pytest.raises(ConfirmationRequiredError):
        service.assert_generation_allowed(NOVEL_ID, 1)

    assert env["writer"].generate_calls == 0
    assert author.transactions.list_all() == []


# ---------------------------------------------------------------------------
# 4: CanonicalState really advances and the fact is written
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_canon_revision_and_fact_advance_after_commit(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]
    store = CanonicalStateStore(env["data_dir"])
    before = store.load().revision

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    result = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    after = store.load()
    assert after.revision > before
    assert after.revision == result.committed_canonical_revision
    assert after.characters["chen_chen"]["status"] == "holding_copper_key"
    # Untouched canonical facts survive the commit.
    assert after.characters["chen_chen"]["gender"] == "female"


# ---------------------------------------------------------------------------
# 5: StoryThreads really advance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_story_thread_advances_after_commit(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]
    store = StoryThreadStore(env["data_dir"])
    before = store.load()
    assert before.threads["thread_copper_key"].status == "open"

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    result = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert result.phase == ChapterPipelinePhase.COMPLETED

    after = store.load()
    thread = after.threads["thread_copper_key"]
    assert thread.status == "advancing"
    assert thread.evidence
    assert after.revision >= before.revision


# ---------------------------------------------------------------------------
# 6: chapter 3 is anchored in the BookOutline, never a generic fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chapter_three_goal_comes_from_book_outline(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    for chapter in (1, 2, 3):
        service.confirm_chapter(NOVEL_ID, chapter, _preference(chapter))
        result = await service.run_chapter_pipeline(
            NOVEL_ID, chapter, author_service=author
        )
        assert result.phase == ChapterPipelinePhase.COMPLETED, result.error_message
        # Each commit advances canon, so the next chapter must re-confirm.

    goals = env["writer"].goals
    assert len(goals) == 3
    third = goals[2]
    assert CHAPTER_OBJECTIVES[3] in third.objective
    assert "推进第3章剧情" not in third.objective
    assert third.production_chapter_ordinal == 3

    # The outline anchor reaches the frozen Author context handed to the Writer.
    context = env["writer"].contexts[2]
    assert CHAPTER_OBJECTIVES[3] in context.prompt
    contract = context.narrative_contract
    assert contract is not None
    assert any(
        CHAPTER_OBJECTIVES[3] in event.action or CHAPTER_OBJECTIVES[3] in event.description
        for event in contract.required_events
    )


@pytest.mark.asyncio
async def test_chapter_without_any_anchor_fails_closed(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    service.confirm_chapter(NOVEL_ID, 9, _preference(9))
    result = await service.run_chapter_pipeline(NOVEL_ID, 9, author_service=author)

    assert result.phase == ChapterPipelinePhase.FAILED
    assert "大纲锚点" in (result.error_message or "")
    assert env["writer"].generate_calls == 0


# ---------------------------------------------------------------------------
# 7: StoryBible fields reach the Author context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_story_bible_fields_reach_author_context(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    context = env["writer"].contexts[0]
    bible_slot = context.slots["story_bible"]
    for expected in (
        "陈晨在旧仓库继承了一把来历不明的铜钥匙。",  # premise
        "一座旧城区仓库改建的出租楼，共五层。",  # setting_summary
        "死亡不可逆",  # immutable_world_rules
        "陈晨是女性，三十二岁，仓库管理员",  # protagonist_contracts
        "陈晨与房东之间关于储物柜归属的争执",  # main_conflicts
        "陈晨打开储物柜并承担其中的真相。",  # ending_direction
    ):
        assert expected in bible_slot
    # The pipeline never dumps the raw canon JSON into the prompt.
    assert "schema_version" not in context.slots["canonical_state"]


# ---------------------------------------------------------------------------
# P0-6: canonical facts constrain the official generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_canonical_facts_constrain_writer_context(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    context = env["writer"].contexts[0]
    contract = context.narrative_contract
    assert contract is not None

    character_ids = {item.id for item in contract.allowed_entities.characters}
    assert {"chen_chen", "landlord"} <= character_ids
    location_ids = {item.id for item in contract.allowed_entities.locations}
    assert "warehouse" in location_ids

    canon_slot = context.slots["canonical_state"]
    assert '"gender": "female"' in canon_slot
    assert '"floor_count": 5' in canon_slot
    assert "周房东" in canon_slot

    protected = {item.id for item in contract.protected_relationships}
    assert protected


# ---------------------------------------------------------------------------
# 9: a completed chapter is idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completed_chapter_rerun_changes_nothing(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]
    canon_store = CanonicalStateStore(env["data_dir"])
    thread_store = StoryThreadStore(env["data_dir"])

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    first = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert first.phase == ChapterPipelinePhase.COMPLETED
    prose_before = author.sections.get_by_id(first.committed_section_id).content

    canon_before = canon_store.load()
    threads_before = thread_store.load()
    calls_before = env["writer"].generate_calls

    second = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    assert second.phase == ChapterPipelinePhase.COMPLETED
    assert env["writer"].generate_calls == calls_before == 1
    assert canon_store.load().revision == canon_before.revision
    assert thread_store.load().revision == threads_before.revision
    assert author.sections.get_by_id(second.committed_section_id).content == prose_before
    assert second.committed_section_id == first.committed_section_id


# ---------------------------------------------------------------------------
# 10: the Author validator is still on the official path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contract_violation_is_rejected_and_never_completes(tmp_path: Path):
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
        chroma_repo=ChromaMemoryRepository(persist_dir=str(tmp_path / "chroma"))
    )

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    result = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    assert result.phase == ChapterPipelinePhase.FAILED
    assert result.committed_manuscript is False
    assert result.committed_section_id == ""
    assert writer.generate_calls == 1
    # The rejection came from the real Author validator chain.
    transactions = author.transactions.list_all()
    assert len(transactions) == 1
    assert transactions[0].phase == "rejected"
    assert transactions[0].committed is False
    assert author.sections.count() == 0
    assert CanonicalStateStore(data_dir).load().revision == 2


# ---------------------------------------------------------------------------
# P0-8: explicit retry creates a new attempt and re-runs the whole chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_creates_new_attempt_and_reruns_full_chain(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]
    data_dir = env["data_dir"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    first = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert first.attempt == 1
    canon_after_first = CanonicalStateStore(data_dir).load().revision

    confirmation = service.retry_chapter(NOVEL_ID, 1, _preference(1))
    retried_state = service.get_pipeline_state(NOVEL_ID, 1)
    assert retried_state.phase == ChapterPipelinePhase.CONFIRMED
    assert retried_state.attempt == 2
    assert retried_state.committed_section_id == ""
    # The retry re-freezes against the authorities the first commit produced.
    assert confirmation.canon_revision == canon_after_first

    second = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    assert second.phase == ChapterPipelinePhase.COMPLETED
    assert second.attempt == 2
    assert env["writer"].generate_calls == 2
    assert second.author_transaction_id != first.author_transaction_id
    assert CanonicalStateStore(data_dir).load().revision == canon_after_first + 1
    assert len(author.transactions.list_all()) == 2


@pytest.mark.asyncio
async def test_retry_is_refused_while_chapter_is_in_flight(env):
    service: StatefulPipelineService = env["service"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    with pytest.raises(PipelineError):
        service.retry_chapter(NOVEL_ID, 1, _preference(1))


# ---------------------------------------------------------------------------
# Failed chapters require an explicit retry, never a silent re-run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_chapter_requires_explicit_retry(env, monkeypatch):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))

    async def _boom(*args, **kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(author, "run", _boom)
    failed = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert failed.phase == ChapterPipelinePhase.FAILED
    assert "provider exploded" in (failed.error_message or "")

    with pytest.raises(PipelineError):
        await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    with pytest.raises(PipelineError):
        service.assert_generation_allowed(NOVEL_ID, 1)
    assert env["writer"].generate_calls == 0


# ---------------------------------------------------------------------------
# A completed chapter whose manuscript disappeared fails closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completed_state_without_manuscript_fails_closed(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]
    data_dir = env["data_dir"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    first = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert first.phase == ChapterPipelinePhase.COMPLETED

    store = PipelineStateStore(data_dir)
    store.save(first.model_copy(update={"committed_section_id": ""}))

    with pytest.raises(PipelineError):
        await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert env["writer"].generate_calls == 1
