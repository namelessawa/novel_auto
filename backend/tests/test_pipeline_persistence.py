"""Tests for pipeline persistence layer and ChromaDB adapter.

Covers: synopsis/schema storage, foreshadow records, selection receipts,
pipeline state, ChromaDB idempotency, and multi-novel isolation.
"""

from __future__ import annotations

import tempfile

import pytest

from story.stateful_pipeline.models import (
    ChapterInformation,
    ChapterPipelinePhase,
    ChapterPipelineState,
    ChapterSynopsis,
    ForeshadowRecord,
    ForeshadowSelectionReceipt,
    ForeshadowSelectionState,
    InformationField,
    InformationSchema,
    MemoryIntegrationRecord,
    TransferContext,
)
from story.stateful_pipeline.persistence import (
    ChapterInformationStore,
    ForeshadowStore,
    MemoryIntegrationStore,
    PipelineStateStore,
    SynopsisStore,
    TransferContextStore,
)


@pytest.fixture
def tmp_data_dir():
    """Temp directory that tolerates Windows file locking issues."""
    import shutil
    d = tempfile.mkdtemp()
    yield d
    # Cleanup with error tolerance for Windows file locks
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Synopsis Store Tests
# ---------------------------------------------------------------------------


class TestSynopsisStore:
    def test_save_and_load(self, tmp_data_dir):
        store = SynopsisStore(tmp_data_dir)
        synopsis = ChapterSynopsis(
            novel_id="test-novel",
            chapter_number=1,
            title="第一章",
            synopsis="这是第一章的梗概",
        )
        store.save(synopsis)

        loaded = store.load("test-novel", 1)
        assert loaded is not None
        assert loaded.title == "第一章"
        assert loaded.synopsis == "这是第一章的梗概"
        assert loaded.revision == 1

    def test_update_creates_new_revision(self, tmp_data_dir):
        store = SynopsisStore(tmp_data_dir)
        synopsis = ChapterSynopsis(
            novel_id="test-novel",
            chapter_number=1,
            title="第一章",
            synopsis="原始梗概",
        )
        store.save(synopsis)

        # Update
        updated = synopsis.model_copy(update={
            "synopsis": "修改后的梗概",
            "revision": 2,
        })
        store.save(updated)

        loaded = store.load("test-novel", 1)
        assert loaded.revision == 2
        assert loaded.synopsis == "修改后的梗概"

    def test_load_nonexistent(self, tmp_data_dir):
        store = SynopsisStore(tmp_data_dir)
        assert store.load("test-novel", 999) is None

    def test_load_all(self, tmp_data_dir):
        store = SynopsisStore(tmp_data_dir)
        for ch in [1, 2, 3]:
            store.save(ChapterSynopsis(
                novel_id="test-novel",
                chapter_number=ch,
                title=f"第{ch}章",
            ))

        all_synopses = store.load_all("test-novel")
        assert len(all_synopses) == 3


# ---------------------------------------------------------------------------
# Information Schema Store Tests
# ---------------------------------------------------------------------------


class TestInformationSchemaStore:
    def test_save_and_load(self, tmp_data_dir):
        from story.stateful_pipeline.persistence import InformationSchemaStore
        store = InformationSchemaStore(tmp_data_dir)

        schema = InformationSchema(
            novel_id="test-novel",
            revision=1,
            fields=[
                InformationField(key="characters", name="人物", description="角色"),
                InformationField(key="locations", name="场景", description="地点"),
            ],
            source="user_defined",
        )
        store.save(schema)

        loaded = store.load("test-novel")
        assert loaded is not None
        assert len(loaded.fields) == 2
        assert loaded.field_keys == ["characters", "locations"]

    def test_schema_revision_updates(self, tmp_data_dir):
        from story.stateful_pipeline.persistence import InformationSchemaStore
        store = InformationSchemaStore(tmp_data_dir)

        schema = InformationSchema(
            novel_id="test-novel",
            revision=1,
            fields=[InformationField(key="characters", name="人物")],
        )
        store.save(schema)

        updated = schema.model_copy(update={
            "revision": 2,
            "fields": [
                InformationField(key="characters", name="人物"),
                InformationField(key="events", name="事件"),
            ],
        })
        store.save(updated)

        loaded = store.load("test-novel")
        assert loaded.revision == 2
        assert len(loaded.fields) == 2


# ---------------------------------------------------------------------------
# Foreshadow Store Tests
# ---------------------------------------------------------------------------


class TestForeshadowStore:
    def test_save_and_load_records(self, tmp_data_dir):
        store = ForeshadowStore(tmp_data_dir)

        records = [
            ForeshadowRecord(
                id="f1",
                novel_id="test-novel",
                source_chapter=5,
                summary="伏笔1",
                current_probability=0.02,
            ),
            ForeshadowRecord(
                id="f2",
                novel_id="test-novel",
                source_chapter=10,
                summary="伏笔2",
                current_probability=0.04,
            ),
        ]
        store.save_records(records)

        loaded = store.load_records("test-novel")
        assert len(loaded) == 2
        assert loaded[0].id == "f1"
        assert loaded[1].current_probability == 0.04

    def test_save_and_load_state(self, tmp_data_dir):
        store = ForeshadowStore(tmp_data_dir)

        state = ForeshadowSelectionState(
            novel_id="test-novel",
            consecutive_selection_count=2,
            discard_unlocked=False,
        )
        store.save_state(state)

        loaded = store.load_state("test-novel")
        assert loaded.consecutive_selection_count == 2
        assert loaded.discard_unlocked is False

    def test_save_and_load_receipt(self, tmp_data_dir):
        store = ForeshadowStore(tmp_data_dir)

        receipt = ForeshadowSelectionReceipt(
            novel_id="test-novel",
            chapter=15,
            eligible_foreshadow_ids=["f1", "f2"],
            collision_winner="f1",
        )
        store.save_receipt(receipt)

        loaded = store.load_receipt("test-novel", 15)
        assert loaded is not None
        assert loaded.collision_winner == "f1"

    def test_receipt_isolation_by_chapter(self, tmp_data_dir):
        store = ForeshadowStore(tmp_data_dir)

        receipt_15 = ForeshadowSelectionReceipt(
            novel_id="test-novel",
            chapter=15,
            collision_winner="f1",
        )
        receipt_20 = ForeshadowSelectionReceipt(
            novel_id="test-novel",
            chapter=20,
            collision_winner="f2",
        )
        store.save_receipt(receipt_15)
        store.save_receipt(receipt_20)

        assert store.load_receipt("test-novel", 15).collision_winner == "f1"
        assert store.load_receipt("test-novel", 20).collision_winner == "f2"


# ---------------------------------------------------------------------------
# Pipeline State Store Tests
# ---------------------------------------------------------------------------


class TestPipelineStateStore:
    def test_save_and_load(self, tmp_data_dir):
        store = PipelineStateStore(tmp_data_dir)

        state = ChapterPipelineState(
            novel_id="test-novel",
            chapter_number=3,
            phase=ChapterPipelinePhase.WRITING,
            synopsis_revision=2,
        )
        store.save(state)

        loaded = store.load("test-novel", 3)
        assert loaded is not None
        assert loaded.phase == ChapterPipelinePhase.WRITING
        assert loaded.synopsis_revision == 2

    def test_get_current_chapter(self, tmp_data_dir):
        store = PipelineStateStore(tmp_data_dir)

        # No states: current chapter is 1
        assert store.get_current_chapter("test-novel") == 1

        # Save state for chapter 3
        store.save(ChapterPipelineState(
            novel_id="test-novel",
            chapter_number=3,
        ))
        assert store.get_current_chapter("test-novel") == 4


# ---------------------------------------------------------------------------
# Chapter Information Store Tests
# ---------------------------------------------------------------------------


class TestChapterInformationStore:
    def test_save_and_load(self, tmp_data_dir):
        store = ChapterInformationStore(tmp_data_dir)

        info = ChapterInformation(
            novel_id="test-novel",
            chapter_number=5,
            schema_revision=1,
            data={
                "characters": [{"name": "主角", "status": "active"}],
                "locations": [{"name": "城市"}],
            },
        )
        store.save(info)

        loaded = store.load("test-novel", 5)
        assert loaded is not None
        assert "characters" in loaded.data
        assert loaded.data["characters"][0]["name"] == "主角"

    def test_load_recent(self, tmp_data_dir):
        store = ChapterInformationStore(tmp_data_dir)

        for ch in [1, 2, 3, 4, 5]:
            store.save(ChapterInformation(
                novel_id="test-novel",
                chapter_number=ch,
                schema_revision=1,
                data={"field": []},
            ))

        recent = store.load_recent("test-novel", 6, count=3)
        assert len(recent) == 3
        chapters = [i.chapter_number for i in recent]
        assert chapters == [3, 4, 5]


# ---------------------------------------------------------------------------
# Transfer Context Store Tests
# ---------------------------------------------------------------------------


class TestTransferContextStore:
    def test_save_and_load(self, tmp_data_dir):
        store = TransferContextStore(tmp_data_dir)

        ctx = TransferContext(
            novel_id="test-novel",
            target_chapter=5,
            recent_context="最近章节摘要",
            foreshadow_to_consider="伏笔建议",
            source_chapters=[2, 3, 4],
        )
        store.save(ctx)

        loaded = store.load("test-novel", 5)
        assert loaded is not None
        assert loaded.recent_context == "最近章节摘要"
        assert loaded.source_chapters == [2, 3, 4]


# ---------------------------------------------------------------------------
# Memory Integration Store Tests
# ---------------------------------------------------------------------------


class TestMemoryIntegrationStore:
    def test_save_and_load(self, tmp_data_dir):
        store = MemoryIntegrationStore(tmp_data_dir)

        record = MemoryIntegrationRecord(
            novel_id="test-novel",
            chapter_number=5,
            schema_revision=1,
            document_ids=["doc1", "doc2"],
            document_count=2,
            status="committed",
        )
        store.save(record)

        loaded = store.load("test-novel", 5)
        assert loaded is not None
        assert loaded.document_count == 2
        assert loaded.status == "committed"


# ---------------------------------------------------------------------------
# ChromaDB Repository Tests
# ---------------------------------------------------------------------------


class TestChromaMemoryRepository:
    @pytest.fixture
    def chroma_repo(self, tmp_data_dir):
        """Create a ChromaDB repository in a temp directory."""
        from story.stateful_pipeline.chroma_repository import ChromaMemoryRepository
        return ChromaMemoryRepository(persist_dir=tmp_data_dir)

    @pytest.mark.asyncio
    async def test_upsert_and_query(self, chroma_repo):
        """Test basic upsert and query operations."""
        documents = [
            {"content": "主角是一个勇敢的战士", "field": "characters", "entities": ["主角"]},
            {"content": "故事发生在一个古老的城堡", "field": "locations", "entities": ["城堡"]},
        ]

        ids = await chroma_repo.upsert_documents(
            novel_id="novel-a",
            chapter=1,
            schema_revision=1,
            documents=documents,
        )

        assert len(ids) == 2
        assert all(id.startswith("novel-a:1:1:") for id in ids)

        # Query should return results
        results = await chroma_repo.query("novel-a", "战士", top_k=5)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_idempotent_upsert(self, chroma_repo):
        """Upserting same chapter twice should not create duplicates."""
        documents = [
            {"content": "测试内容", "field": "test", "entities": []},
        ]

        # First upsert
        ids1 = await chroma_repo.upsert_documents(
            novel_id="novel-b",
            chapter=1,
            schema_revision=1,
            documents=documents,
        )

        # Second upsert (same data)
        ids2 = await chroma_repo.upsert_documents(
            novel_id="novel-b",
            chapter=1,
            schema_revision=1,
            documents=documents,
        )

        assert ids1 == ids2  # Same IDs
        count = await chroma_repo.count("novel-b")
        assert count == 1  # Only one document

    @pytest.mark.asyncio
    async def test_novel_isolation(self, chroma_repo):
        """Documents from novel A should not appear in novel B queries."""
        await chroma_repo.upsert_documents(
            novel_id="novel-a",
            chapter=1,
            schema_revision=1,
            documents=[{"content": "小说A的内容", "field": "test", "entities": []}],
        )

        await chroma_repo.upsert_documents(
            novel_id="novel-b",
            chapter=1,
            schema_revision=1,
            documents=[{"content": "小说B的内容", "field": "test", "entities": []}],
        )

        # Query novel-a should only get novel-a content
        results_a = await chroma_repo.query("novel-a", "内容", top_k=10)
        for r in results_a:
            assert r["metadata"]["novel_id"] == "novel-a"

        # Query novel-b should only get novel-b content
        results_b = await chroma_repo.query("novel-b", "内容", top_k=10)
        for r in results_b:
            assert r["metadata"]["novel_id"] == "novel-b"

    @pytest.mark.asyncio
    async def test_rebuild_from_source(self, chroma_repo):
        """Rebuild ChromaDB from chapter information."""
        chapter_informations = [
            {
                "chapter_number": 1,
                "data": {
                    "characters": [{"name": "主角", "description": "勇敢的战士"}],
                    "locations": [{"name": "城堡"}],
                },
            },
            {
                "chapter_number": 2,
                "data": {
                    "characters": [{"name": "反派"}],
                },
            },
        ]

        count = await chroma_repo.rebuild(
            novel_id="novel-rebuild",
            chapter_informations=chapter_informations,
            schema_revision=1,
        )

        assert count > 0
        total = await chroma_repo.count("novel-rebuild")
        assert total == count

    @pytest.mark.asyncio
    async def test_clear_novel(self, chroma_repo):
        """Clear all documents for a novel."""
        await chroma_repo.upsert_documents(
            novel_id="novel-clear",
            chapter=1,
            schema_revision=1,
            documents=[{"content": "test", "field": "test", "entities": []}],
        )

        count_before = await chroma_repo.count("novel-clear")
        assert count_before > 0

        deleted = await chroma_repo.clear_novel("novel-clear")
        assert deleted == count_before

        count_after = await chroma_repo.count("novel-clear")
        assert count_after == 0
