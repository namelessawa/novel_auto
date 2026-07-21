from __future__ import annotations

from pathlib import Path

import pytest

from sections.section_store import _clear_for_tests
from story.models import (
    SectionGoal,
    StateDeltaOperation,
    StoryBibleUpdate,
    WriterCandidate,
)
from story.persistence import StoryBibleStore
from story.service import (
    AuthorGenerationService,
    CommitPendingError,
    GenerationRejected,
)
from story.writer import WriterResult


class FakeWriter:
    def __init__(self, generated: WriterCandidate, repaired: WriterCandidate | None = None):
        self.generated = generated
        self.repaired = repaired or generated
        self.generate_calls = 0
        self.repair_calls = 0

    async def generate(self, context, goal):
        self.generate_calls += 1
        assert "story_bible" in context.slots
        return WriterResult(
            self.generated,
            {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )

    async def repair(self, candidate, report):
        self.repair_calls += 1
        return WriterResult(
            self.repaired,
            {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
        )


@pytest.fixture(autouse=True)
def clear_sections():
    _clear_for_tests()
    yield
    _clear_for_tests()


def _goal() -> SectionGoal:
    return SectionGoal(objective="让主角以一次选择回应身份与牺牲。")


def _valid_candidate(text: str = "") -> WriterCandidate:
    narrative = text or ("主角确认自己的身份，并选择为同伴承担牺牲的代价。" * 20)
    return WriterCandidate(
        narrative_text=narrative,
        title="代价",
        section_summary="主角以牺牲回应身份冲突。",
    )


def _service(tmp_path: Path, writer: FakeWriter) -> AuthorGenerationService:
    service = AuthorGenerationService(
        user_id="alice",
        novel_id="novel",
        data_dir=str(tmp_path),
        title="测试小说",
        writer=writer,
    )
    bible = service.bibles.load()
    service.bibles.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            premise="一名失忆者守护旧城。",
            theme="身份与牺牲",
            setting_summary="封闭的旧城。",
            immutable_world_rules=["死亡不可逆"],
        )
    )
    return service


@pytest.mark.asyncio
async def test_author_service_commits_one_writer_call_and_persists_long_memory(
    tmp_path: Path,
) -> None:
    writer = FakeWriter(_valid_candidate())
    service = _service(tmp_path, writer)

    tx = await service.run(_goal(), request_id="req_one")

    assert tx.committed is True
    assert tx.writer_calls == 1
    assert tx.repair_performed is False
    assert tx.story_bible_revision == 2
    assert service.states.load().revision == 2
    assert service.sections.count() == 1
    assert "section_summary_" + tx.section_id in service.memories.load().records
    assert service.manifests.load().slots[0].name == "story_bible"
    assert writer.generate_calls == 1

    retried = await service.run(_goal(), request_id="req_one")
    assert retried.id == tx.id
    assert service.sections.count() == 1
    assert writer.generate_calls == 1


@pytest.mark.asyncio
async def test_author_service_repairs_once_then_commits(tmp_path: Path) -> None:
    bad = _valid_candidate("旧王复活，身份与牺牲失去意义。" * 12).model_copy(
        update={
            "state_delta": [
                StateDeltaOperation(
                    op="set",
                    path="/story_bible/theme",
                    value="升级",
                    evidence="失去意义",
                )
            ]
        }
    )
    writer = FakeWriter(bad, _valid_candidate())
    service = _service(tmp_path, writer)

    tx = await service.run(_goal(), request_id="req_repair")

    assert tx.committed is True
    assert tx.writer_calls == 2
    assert tx.repair_performed is True
    assert writer.generate_calls == 1
    assert writer.repair_calls == 1
    assert tx.usage["total_tokens"] == 200


@pytest.mark.asyncio
async def test_author_service_rejects_after_single_failed_repair_without_half_commit(
    tmp_path: Path,
) -> None:
    bad = _valid_candidate("旧王复活，身份与牺牲失去意义。" * 12).model_copy(
        update={
            "state_delta": [
                StateDeltaOperation(
                    op="set",
                    path="/story_bible/theme",
                    value="升级",
                    evidence="失去意义",
                )
            ]
        }
    )
    writer = FakeWriter(bad, bad)
    service = _service(tmp_path, writer)

    with pytest.raises(GenerationRejected) as error:
        await service.run(_goal(), request_id="req_reject")

    assert error.value.transaction.phase == "rejected"
    assert error.value.transaction.writer_calls == 2
    assert service.states.load().revision == 1
    assert service.sections.count() == 0
    assert writer.repair_calls == 1


@pytest.mark.asyncio
async def test_commit_failure_recovers_without_duplicate_section(
    tmp_path: Path, monkeypatch
) -> None:
    writer = FakeWriter(_valid_candidate())
    service = _service(tmp_path, writer)
    original_save = service.memories.save
    calls = {"count": 0}

    def fail_once(value):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("simulated disk interruption")
        return original_save(value)

    monkeypatch.setattr(service.memories, "save", fail_once)
    with pytest.raises(CommitPendingError):
        await service.run(_goal(), request_id="req_recover")

    assert service.states.load().revision == 2
    assert service.sections.count() == 0

    # A fresh process/runtime scans the journal and rolls the staged transaction forward.
    recovered = AuthorGenerationService(
        user_id="alice",
        novel_id="novel",
        data_dir=str(tmp_path),
        title="测试小说",
        writer=FakeWriter(_valid_candidate()),
    )
    transaction = recovered.transactions.load("req_recover")
    assert transaction.committed is True
    assert recovered.sections.count() == 1
    assert recovered.states.load().revision == 2
    assert recovered.memories.load().revision == 2


@pytest.mark.asyncio
async def test_story_bible_is_unchanged_after_generation_commit(tmp_path: Path) -> None:
    writer = FakeWriter(_valid_candidate())
    service = _service(tmp_path, writer)
    before = StoryBibleStore(str(tmp_path)).load()
    await service.run(_goal(), request_id="req_bible_unchanged")
    after = StoryBibleStore(str(tmp_path)).load()
    assert before.revision == 2
    assert before.theme == "身份与牺牲"
    assert after == before
