"""Backend connectivity integration test: full 3-chapter pipeline.

Verifies every module boundary of the converged pipeline works together,
without a real provider:

  StoryBible/Canon/Thread/BookOutline setup → synopsis LLM → schema LLM →
  confirm freeze → foreshadow decisions (count roll + selection receipt) →
  Author production (Writer → NarrativeContract → Validator → Repair →
  transaction commit) → foreshadow extraction → information extraction →
  split integration → ChromaDB upsert → idempotent re-run

The pipeline-owned LLM roles run through the shared ``mock_llm`` fixture; the
official Writer is a recording stand-in so every real Author validator, the
repair gate and the commit journal stay in the path.

The test is deterministic: FIXED foreshadow mode consumes no RNG, and no
foreshadow is old enough to be eligible (age < 8).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sections.section_store import _clear_for_tests
from story.persistence import CanonicalStateStore, StoryThreadStore
from story.service import AuthorGenerationService
from story.stateful_pipeline.chroma_repository import ChromaMemoryRepository
from story.stateful_pipeline.models import (
    ChapterGenerationPreference,
    ChapterPipelinePhase,
    ForeshadowMode,
    ForeshadowStatus,
)
from story.stateful_pipeline.persistence import (
    ChapterInformationStore,
    ForeshadowStore,
    MemoryIntegrationStore,
    SynopsisStore,
)
from story.stateful_pipeline.service import (
    ConfirmationRequiredError,
    StatefulPipelineService,
)

from tests.test_pipeline_author_bridge import (
    CHAPTER_OBJECTIVES,
    NOVEL_ID,
    USER_ID,
    RecordingWriter,
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
def pipeline_env(tmp_path: Path):
    """Windows-safe temp dir with every authority and both services wired up."""
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
    yield {
        "data_dir": data_dir,
        "service": service,
        "author": author,
        "writer": writer,
        "chroma": service._chroma,
        "bible": author.bibles.load(),
    }


def _synopsis_response() -> dict:
    return {
        "chapters": [
            {"chapter": 1, "title": "第一章 钥匙", "synopsis": "陈晨在旧仓库清点遗物时找到铜钥匙。" * 3},
            {"chapter": 2, "title": "第二章 房东", "synopsis": "陈晨向房东追问储物柜的来历。" * 3},
        ]
    }


def _schema_response() -> list:
    return [
        {"key": "characters", "name": "人物", "description": "出场人物"},
        {"key": "locations", "name": "地点", "description": "场景地点"},
        {"key": "events", "name": "事件", "description": "关键事件"},
    ]


def _foreshadow_response(summary: str) -> list:
    return [{"source_text": "原文引用片段", "summary": summary}]


def _information_response() -> dict:
    # 2 non-empty fields → 2 split-integration calls; 1 empty field skipped.
    return {
        "characters": [{"name": "陈晨", "status": "active"}],
        "locations": [{"name": "旧仓库"}],
        "events": [],
    }


def _integration_response(field_hint: str) -> list:
    return [{"content": f"整合记忆文档：{field_hint}", "entities": ["陈晨"]}]


def _queue_full_run(mock_llm) -> None:
    """Queue every pipeline-owned LLM response for the 3-chapter run.

    The official Writer is not an LLM role here, so it consumes nothing.
    """
    mock_llm.set_responses([
        _synopsis_response(),                       # 1. synopsis
        _schema_response(),                         # 2. schema generator
        # --- chapter 1 (fixed count=1) ---
        _foreshadow_response("第一章伏笔：铜钥匙的刻痕"),  # 3. foreshadow extract
        _information_response(),                    # 4. information extract
        _integration_response("ch1-a"),              # 5. integration field A
        _integration_response("ch1-b"),              # 6. integration field B
        # --- chapter 2 (fixed count=0, no foreshadow call) ---
        _information_response(),                    # 7. information extract
        _integration_response("ch2-a"),              # 8. integration A
        _integration_response("ch2-b"),              # 9. integration B
        # --- chapter 3 (fixed count=1) ---
        _foreshadow_response("第三章伏笔：储物柜里的旧照片"),  # 10. foreshadow extract
        _information_response(),                    # 11. information extract
        _integration_response("ch3-a"),              # 12. integration A
        _integration_response("ch3-b"),              # 13. integration B
    ])


async def _run_chapter(env, chapter: int, count: int):
    """Confirm + run one chapter with a FIXED foreshadow count."""
    service: StatefulPipelineService = env["service"]
    service.confirm_chapter(NOVEL_ID, chapter, _preference(chapter, count))
    return await service.run_chapter_pipeline(
        NOVEL_ID, chapter, author_service=env["author"]
    )


def _preference(chapter: int, count: int) -> ChapterGenerationPreference:
    return ChapterGenerationPreference(
        novel_id=NOVEL_ID,
        chapter_number=chapter,
        foreshadow_mode=ForeshadowMode.FIXED,
        foreshadow_fixed_count=count,
    )


@pytest.mark.asyncio
async def test_three_chapter_pipeline_connectivity(mock_llm, pipeline_env):
    """Full 3-chapter run: every module boundary crossed successfully."""
    env = pipeline_env
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]
    data_dir = env["data_dir"]
    _queue_full_run(mock_llm)

    # --- Step 1: synopsis generation (LLM role → SynopsisStore) ---
    synopses = await service.generate_initial_synopses(
        novel_id=NOVEL_ID, story_bible=env["bible"], genre="都市悬疑"
    )
    assert len(synopses) == 2
    store_syn = SynopsisStore(data_dir).load(NOVEL_ID, 1)
    assert store_syn is not None and store_syn.title == "第一章 钥匙"

    # The frozen StoryBible projection reached the synopsis prompt.
    synopsis_prompt = mock_llm.calls[0][1]
    assert "陈晨在旧仓库继承了一把来历不明的铜钥匙。" in synopsis_prompt
    assert "一座旧城区仓库改建的出租楼，共五层。" in synopsis_prompt

    # --- Step 2: schema generation (LLM role → InformationSchemaStore) ---
    schema = await service.ensure_schema(
        novel_id=NOVEL_ID,
        story_bible=env["bible"],
        genre="都市悬疑",
        synopses=synopses,
    )
    assert schema.field_keys == ["characters", "locations", "events"]

    # --- Step 3: run chapters 1..3 through the full pipeline ---
    canon_revision = CanonicalStateStore(data_dir).load().revision
    committed = []
    for chapter, count in ((1, 1), (2, 0), (3, 1)):
        before = canon_revision
        state = await _run_chapter(env, chapter, count)
        assert state.phase == ChapterPipelinePhase.COMPLETED, state.error_message
        assert state.committed_manuscript is True
        committed.append(state)
        canon_revision = CanonicalStateStore(data_dir).load().revision
        assert canon_revision == before + 1

    # --- Every chapter really committed an official Author section ---
    assert [item.committed_canonical_revision for item in committed] == [3, 4, 5]
    for state in committed:
        section = author.sections.get_by_id(state.committed_section_id)
        assert section is not None
        assert section.generation_mode == "author"
        assert section.content.strip()
        transaction = author.transactions.load(state.author_transaction_id)
        assert transaction.committed is True
        assert transaction.narrative_validation_report.accepted is True
        assert transaction.validation_report.accepted is True

    # --- Verify pipeline-owned LLM call order ---
    agent_ids = [kw.get("agent_id") for kw in mock_llm.call_kwargs]
    assert agent_ids == [
        "pipeline_synopsis",
        "pipeline_schema_generator",
        # ch1
        "pipeline_foreshadow_extractor",
        "pipeline_information_extractor",
        "pipeline_integration",
        "pipeline_integration",
        # ch2 (no foreshadow call: fixed count 0)
        "pipeline_information_extractor",
        "pipeline_integration",
        "pipeline_integration",
        # ch3
        "pipeline_foreshadow_extractor",
        "pipeline_information_extractor",
        "pipeline_integration",
        "pipeline_integration",
    ]
    # The simplified writer is no longer part of the official chain.
    assert "pipeline_simplified_writer" not in agent_ids
    # Continuity now comes from the Author ContextBuilder, not a Transfer LLM.
    assert "pipeline_transfer" not in agent_ids
    assert env["writer"].generate_calls == 3

    # --- Each chapter goal is anchored in the BookOutline ---
    for index, chapter in enumerate((1, 2, 3), start=1):
        goal = env["writer"].goals[index - 1]
        assert CHAPTER_OBJECTIVES[chapter] in goal.objective
        assert goal.production_chapter_ordinal == chapter
        assert f"推进第{chapter}章剧情" not in goal.objective

    # --- Foreshadow records: ch1 + ch3, deterministic ids, MINIMUM_AGE=8 ---
    fstore = ForeshadowStore(data_dir)
    records = fstore.load_records(NOVEL_ID)
    assert len(records) == 2
    by_id = {r.id for r in records}
    assert f"{NOVEL_ID}:ch1:f1" in by_id
    assert f"{NOVEL_ID}:ch3:f1" in by_id
    for r in records:
        assert r.status == ForeshadowStatus.ACTIVE
        assert r.current_probability == 0.02
        assert r.next_eligible_chapter == r.source_chapter + 8

    # --- Selection receipts exist for every chapter ---
    for chapter in (1, 2, 3):
        receipt = fstore.load_receipt(NOVEL_ID, chapter)
        assert receipt is not None
        assert receipt.applied_to_records is True
        assert receipt.collision_winner is None  # none eligible at age < 8
    assert fstore.load_receipt(NOVEL_ID, 1).new_foreshadow_count == 1
    assert fstore.load_receipt(NOVEL_ID, 2).new_foreshadow_count == 0
    assert fstore.load_receipt(NOVEL_ID, 3).new_foreshadow_count == 1

    # --- Information: schema keys frozen, per-chapter files ---
    info_store = ChapterInformationStore(data_dir)
    for chapter in (1, 2, 3):
        info = info_store.load(NOVEL_ID, chapter)
        assert info is not None
        assert info.schema_revision == 1
        assert set(info.data.keys()) == {"characters", "locations", "events"}

    # --- Integration records committed + ChromaDB documents ---
    istore = MemoryIntegrationStore(data_dir)
    total_docs = 0
    for chapter in (1, 2, 3):
        rec = istore.load(NOVEL_ID, chapter)
        assert rec is not None and rec.status == "committed"
        assert rec.document_count == 2  # 2 non-empty fields → 2 docs
        total_docs += rec.document_count
    assert await env["chroma"].count(NOVEL_ID) == total_docs == 6

    # --- Deterministic Chroma ids ---
    rec1 = istore.load(NOVEL_ID, 1)
    assert all(doc_id.startswith(f"{NOVEL_ID}:1:1:") for doc_id in rec1.document_ids)

    # --- StoryThreads advanced through the official commit boundary ---
    thread = StoryThreadStore(data_dir).load().threads["thread_copper_key"]
    assert thread.status == "advancing"
    assert thread.evidence


@pytest.mark.asyncio
async def test_rerun_chapter_is_idempotent(mock_llm, pipeline_env):
    """Re-running a completed chapter duplicates no persistent side effect."""
    env = pipeline_env
    service: StatefulPipelineService = env["service"]
    data_dir = env["data_dir"]
    author: AuthorGenerationService = env["author"]
    _queue_full_run(mock_llm)

    synopses = await service.generate_initial_synopses(
        novel_id=NOVEL_ID, story_bible=env["bible"], genre="都市悬疑"
    )
    await service.ensure_schema(
        novel_id=NOVEL_ID,
        story_bible=env["bible"],
        genre="都市悬疑",
        synopses=synopses,
    )
    for chapter, count in ((1, 1), (2, 0), (3, 1)):
        await _run_chapter(env, chapter, count)

    docs_before = await env["chroma"].count(NOVEL_ID)
    records_before = len(ForeshadowStore(data_dir).load_records(NOVEL_ID))
    canon_before = CanonicalStateStore(data_dir).load().revision
    threads_before = StoryThreadStore(data_dir).load().revision
    calls_before = len(mock_llm.call_kwargs)
    prose_before = author.sections.get_by_id(
        service.get_pipeline_state(NOVEL_ID, 3).committed_section_id
    ).content

    # Re-running a completed chapter is a pure read: no LLM role, no Writer,
    # no authority mutation.  Deliberately not re-confirmed — a completed
    # chapter is replayed, never silently regenerated.
    state = await service.run_chapter_pipeline(
        NOVEL_ID, 3, author_service=author
    )

    assert state.phase == ChapterPipelinePhase.COMPLETED
    assert mock_llm.call_kwargs[calls_before:] == []
    assert env["writer"].generate_calls == 3
    assert len(ForeshadowStore(data_dir).load_records(NOVEL_ID)) == records_before
    assert await env["chroma"].count(NOVEL_ID) == docs_before
    assert CanonicalStateStore(data_dir).load().revision == canon_before
    assert StoryThreadStore(data_dir).load().revision == threads_before
    assert author.sections.get_by_id(state.committed_section_id).content == prose_before
    receipt = ForeshadowStore(data_dir).load_receipt(NOVEL_ID, 3)
    assert receipt.new_foreshadow_count == 1


@pytest.mark.asyncio
async def test_generation_blocked_without_confirmation(mock_llm, pipeline_env):
    """No confirmation → Writer and pipeline LLM call count must both be 0."""
    env = pipeline_env
    service: StatefulPipelineService = env["service"]
    mock_llm.set_responses([])

    with pytest.raises(ConfirmationRequiredError):
        await service.run_chapter_pipeline(
            NOVEL_ID, 1, author_service=env["author"]
        )

    assert env["writer"].generate_calls == 0
    assert mock_llm.call_kwargs == []
    assert env["author"].transactions.list_all() == []
