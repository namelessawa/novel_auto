"""Backend connectivity integration test: full 3-chapter pipeline.

Verifies every module boundary of the stateful pipeline works together,
using the shared mock_llm fixture (no real provider):

  StoryBible/Canon setup → synopsis LLM → schema LLM → confirm gate →
  foreshadow decisions (count roll + selection receipt) → pacing →
  simplified writer → foreshadow extraction → information extraction →
  split integration → ChromaDB upsert → transfer context (ch3) →
  idempotent re-run (no duplicated side effects)

The test is fully deterministic: FIXED foreshadow mode consumes no RNG,
no foreshadow is old enough to be eligible (age < 8), and chapters 1-3
are below the conflict/climax earliest-chapter thresholds, so pacing is
always 'flat'.
"""

from __future__ import annotations

import shutil
import tempfile

import pytest

from story.models import StoryBible
from story.persistence import CanonicalStateStore, StoryBibleStore
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
    PacingStore,
    SynopsisStore,
    TransferContextStore,
)
from story.stateful_pipeline.service import StatefulPipelineService

NOVEL_ID = "integration-novel"

# 240 chars of prose — above MIN_VALID_PROSE_CHARS (200).
PROSE = "这是用于集成测试的章节正文内容。" * 30


@pytest.fixture
def pipeline_env():
    """Windows-safe temp dir with bible/canon/chroma/service wired up."""
    data_dir = tempfile.mkdtemp(prefix="pipeline_integration_")
    chroma_dir = tempfile.mkdtemp(prefix="pipeline_integration_chroma_")

    bible = StoryBible(title="集成测试小说", genre="都市生活", premise="主角在城市中生活")
    StoryBibleStore(data_dir).save(bible)
    canon = CanonicalStateStore(data_dir).load()

    chroma = ChromaMemoryRepository(persist_dir=chroma_dir)
    service = StatefulPipelineService(data_dir=data_dir, chroma_repo=chroma)

    yield {
        "data_dir": data_dir,
        "bible": bible,
        "canon": canon,
        "chroma": chroma,
        "service": service,
    }

    shutil.rmtree(data_dir, ignore_errors=True)
    shutil.rmtree(chroma_dir, ignore_errors=True)


def _synopsis_response() -> dict:
    return {
        "chapters": [
            {"chapter": 1, "title": "第一章 清晨", "synopsis": "主角开始新的一天，遇到邻居。" * 5},
            {"chapter": 2, "title": "第二章 变故", "synopsis": "工作出现变故，主角做出决定。" * 5},
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
        "characters": [{"name": "李明", "status": "active"}],
        "locations": [{"name": "写字楼"}],
        "events": [],
    }


def _integration_response(field_hint: str) -> list:
    return [{"content": f"整合记忆文档：{field_hint}", "entities": ["李明"]}]


def _transfer_response() -> dict:
    return {
        "recent_context": "前两章主角经历了工作变故。",
        "foreshadow_to_consider": "",
        "continuity_constraints": ["保持人物一致"],
        "important_entities": ["李明"],
    }


def _queue_full_run(mock_llm) -> None:
    """Queue all 17 LLM responses for the deterministic 3-chapter run."""
    mock_llm.set_responses([
        _synopsis_response(),                    # 1. synopsis
        _schema_response(),                      # 2. schema generator
        # --- chapter 1 (fixed count=1) ---
        f"<prose>{PROSE}</prose>",               # 3. writer
        _foreshadow_response("第一章伏笔：神秘钥匙"),  # 4. foreshadow extract
        _information_response(),                 # 5. information extract
        _integration_response("ch1-a"),          # 6. integration field A
        _integration_response("ch1-b"),          # 7. integration field B
        # --- chapter 2 (fixed count=0, no foreshadow call) ---
        f"<prose>{PROSE}</prose>",               # 8. writer
        _information_response(),                 # 9. information extract
        _integration_response("ch2-a"),          # 10. integration A
        _integration_response("ch2-b"),          # 11. integration B
        # --- chapter 3 (transfer first, then fixed count=1) ---
        _transfer_response(),                    # 12. transfer
        f"<prose>{PROSE}</prose>",               # 13. writer
        _foreshadow_response("第三章伏笔：旧照片"),  # 14. foreshadow extract
        _information_response(),                 # 15. information extract
        _integration_response("ch3-a"),          # 16. integration A
        _integration_response("ch3-b"),          # 17. integration B
    ])


async def _run_chapter(service, bible, canon, chapter: int, count: int):
    """Confirm + run one chapter with FIXED foreshadow count."""
    preference = ChapterGenerationPreference(
        novel_id=NOVEL_ID,
        chapter_number=chapter,
        foreshadow_mode=ForeshadowMode.FIXED,
        foreshadow_fixed_count=count,
    )
    confirmation = service.confirm_chapter(
        novel_id=NOVEL_ID,
        chapter=chapter,
        preference=preference,
        bible=bible,
        canon=canon,
        style_revision=1,
    )
    return await service.run_chapter_pipeline(
        novel_id=NOVEL_ID,
        chapter=chapter,
        confirmation=confirmation,
        bible=bible,
        canon=canon,
        style_prefix="以冷静的第三人称叙事。",
        chapter_goal=f"推进第{chapter}章剧情",
    )


@pytest.mark.asyncio
async def test_three_chapter_pipeline_connectivity(mock_llm, pipeline_env):
    """Full 3-chapter run: every module boundary crossed successfully."""
    env = pipeline_env
    service: StatefulPipelineService = env["service"]
    data_dir = env["data_dir"]
    _queue_full_run(mock_llm)

    # --- Step 1: synopsis generation (LLM role → SynopsisStore) ---
    synopses = await service.generate_initial_synopses(
        novel_id=NOVEL_ID, story_bible=env["bible"], genre="都市生活"
    )
    assert len(synopses) == 2
    store_syn = SynopsisStore(data_dir).load(NOVEL_ID, 1)
    assert store_syn is not None and store_syn.title == "第一章 清晨"

    # --- Step 2: schema generation (LLM role → InformationSchemaStore) ---
    schema = await service.ensure_schema(
        novel_id=NOVEL_ID,
        story_bible=env["bible"],
        genre="都市生活",
        synopses=synopses,
    )
    assert schema.field_keys == ["characters", "locations", "events"]

    # --- Step 3: run chapters 1..3 through the full pipeline ---
    state1 = await _run_chapter(service, env["bible"], env["canon"], 1, count=1)
    assert state1.phase == ChapterPipelinePhase.COMPLETED

    state2 = await _run_chapter(service, env["bible"], env["canon"], 2, count=0)
    assert state2.phase == ChapterPipelinePhase.COMPLETED

    state3 = await _run_chapter(service, env["bible"], env["canon"], 3, count=1)
    assert state3.phase == ChapterPipelinePhase.COMPLETED

    # --- Verify LLM call order matches the wired pipeline ---
    agent_ids = [kw.get("agent_id") for kw in mock_llm.call_kwargs]
    assert agent_ids == [
        "pipeline_synopsis",
        "pipeline_schema_generator",
        # ch1
        "pipeline_simplified_writer",
        "pipeline_foreshadow_extractor",
        "pipeline_information_extractor",
        "pipeline_integration",
        "pipeline_integration",
        # ch2 (no foreshadow call: fixed count 0)
        "pipeline_simplified_writer",
        "pipeline_information_extractor",
        "pipeline_integration",
        "pipeline_integration",
        # ch3 (transfer BEFORE writer)
        "pipeline_transfer",
        "pipeline_simplified_writer",
        "pipeline_foreshadow_extractor",
        "pipeline_information_extractor",
        "pipeline_integration",
        "pipeline_integration",
    ]

    # --- Pacing: receipts persisted, all flat (chapters < 16/21) ---
    pacing_store = PacingStore(data_dir)
    for chapter in (1, 2, 3):
        receipt = pacing_store.load_receipt(NOVEL_ID, chapter)
        assert receipt is not None
        assert receipt.selected_mode.value == "flat"

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

    # --- Selection receipts exist for every chapter (connectivity fix) ---
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

    # --- Transfer context: ch3 only, sources are ch1+ch2 ---
    transfer = TransferContextStore(data_dir).load(NOVEL_ID, 3)
    assert transfer is not None
    assert transfer.source_chapters == [1, 2]
    assert TransferContextStore(data_dir).load(NOVEL_ID, 1) is None

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

    # --- Writer received style prefix and pacing instruction ---
    writer_calls = [
        (sys_p, user_p)
        for (sys_p, user_p), kw in zip(mock_llm.calls, mock_llm.call_kwargs)
        if kw.get("agent_id") == "pipeline_simplified_writer"
    ]
    assert len(writer_calls) == 3
    for _sys, user in writer_calls:
        assert "以冷静的第三人称叙事。" in user  # style prefix applied
        assert "平淡叙事" in user  # pacing mode instruction applied
    # transfer context reached the ch3 writer prompt
    assert "前两章主角经历了工作变故" in writer_calls[2][1]

    # --- Style prefix NOT leaked to other roles ---
    for (sys_p, user_p), kw in zip(mock_llm.calls, mock_llm.call_kwargs):
        if kw.get("agent_id") in (
            "pipeline_foreshadow_extractor",
            "pipeline_information_extractor",
            "pipeline_integration",
            "pipeline_transfer",
        ):
            assert "以冷静的第三人称叙事。" not in sys_p + user_p


@pytest.mark.asyncio
async def test_rerun_chapter_is_idempotent(mock_llm, pipeline_env):
    """Re-running a completed chapter duplicates no persistent side effect."""
    env = pipeline_env
    service: StatefulPipelineService = env["service"]
    data_dir = env["data_dir"]
    _queue_full_run(mock_llm)

    await service.generate_initial_synopses(
        novel_id=NOVEL_ID, story_bible=env["bible"], genre="都市生活"
    )
    synopses = SynopsisStore(data_dir).load_all(NOVEL_ID)
    await service.ensure_schema(
        novel_id=NOVEL_ID, story_bible=env["bible"], genre="都市生活", synopses=synopses
    )
    await _run_chapter(service, env["bible"], env["canon"], 1, count=1)
    await _run_chapter(service, env["bible"], env["canon"], 2, count=0)
    await _run_chapter(service, env["bible"], env["canon"], 3, count=1)

    docs_before = await env["chroma"].count(NOVEL_ID)
    records_before = len(ForeshadowStore(data_dir).load_records(NOVEL_ID))

    # Re-run chapter 3: transfer/info/integration are cached or skipped;
    # only writer + foreshadow extraction consume LLM calls again.
    calls_before = len(mock_llm.call_kwargs)
    mock_llm.set_responses([
        f"<prose>{PROSE}</prose>",
        _foreshadow_response("第三章伏笔：旧照片"),
    ])
    state = await _run_chapter(service, env["bible"], env["canon"], 3, count=1)
    assert state.phase == ChapterPipelinePhase.COMPLETED

    rerun_agents = [kw.get("agent_id") for kw in mock_llm.call_kwargs[calls_before:]]
    assert rerun_agents == [
        "pipeline_simplified_writer",
        "pipeline_foreshadow_extractor",
    ]

    # No duplicated foreshadow records (deterministic id dedup)
    assert len(ForeshadowStore(data_dir).load_records(NOVEL_ID)) == records_before
    # No duplicated Chroma documents (integration skipped: record committed)
    assert await env["chroma"].count(NOVEL_ID) == docs_before
    # Receipt not re-rolled
    receipt = ForeshadowStore(data_dir).load_receipt(NOVEL_ID, 3)
    assert receipt.new_foreshadow_count == 1


@pytest.mark.asyncio
async def test_generation_blocked_without_confirmation(mock_llm, pipeline_env):
    """No confirmation → Novel LLM call count must be 0 (spec §38)."""
    from story.stateful_pipeline.service import ConfirmationRequiredError

    env = pipeline_env
    service: StatefulPipelineService = env["service"]
    mock_llm.set_responses([])

    with pytest.raises(ConfirmationRequiredError):
        await service.run_chapter_pipeline(
            novel_id=NOVEL_ID,
            chapter=1,
            confirmation=None,
            bible=env["bible"],
            canon=env["canon"],
            style_prefix="",
            chapter_goal="test",
        )

    writer_calls = [
        kw for kw in mock_llm.call_kwargs
        if kw.get("agent_id") == "pipeline_simplified_writer"
    ]
    assert len(writer_calls) == 0
