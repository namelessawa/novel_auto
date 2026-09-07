"""P0-3 / P0-7: the confirmation state machine and the revision freeze.

Confirmation and generation are distinct states, and a confirmation freezes
every authority the Author chain reads.  Generation must fail closed when a
frozen authority moved, never silently bind to the newer revision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import novel_manager
from api import pipeline_routes
from api.pipeline_routes import ConfirmAndGenerateRequest, RetryChapterRequest
from auth.models import User
from sections.section_store import _clear_for_tests
from story.models import StoryBibleUpdate
from story.persistence import CanonicalStateStore
from story.production_models import BookOutlineUpdate
from story.production_persistence import BookOutlineStore
from story.service import AuthorGenerationService
from story.stateful_pipeline.chroma_repository import ChromaMemoryRepository
from story.stateful_pipeline.models import (
    ChapterPipelinePhase,
    ChapterPipelineState,
)
from story.stateful_pipeline.persistence import PipelineStateStore
from story.stateful_pipeline.service import (
    ConfirmationRequiredError,
    ConfirmationStaleError,
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
# P0-3: confirm and generate are separate states
# ---------------------------------------------------------------------------


def test_confirm_moves_chapter_to_confirmed(env):
    service: StatefulPipelineService = env["service"]

    before = service.get_pipeline_state(NOVEL_ID, 1)
    assert before is None

    confirmation = service.confirm_chapter(NOVEL_ID, 1, _preference(1))

    state = service.get_pipeline_state(NOVEL_ID, 1)
    assert state is not None
    assert state.phase == ChapterPipelinePhase.CONFIRMED
    assert state.phase != ChapterPipelinePhase.AWAITING_CONFIRMATION
    frozen = state.frozen_confirmation()
    assert frozen is not None
    assert frozen.model_dump(exclude={"confirmed_at"}) == confirmation.model_dump(
        exclude={"confirmed_at"}
    )


@pytest.mark.asyncio
async def test_confirmed_chapter_generates_without_conflict(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    # The synchronous gate must accept a CONFIRMED chapter (no 409 at the API).
    state = service.assert_generation_allowed(NOVEL_ID, 1)
    assert state.phase == ChapterPipelinePhase.CONFIRMED

    result = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert result.phase == ChapterPipelinePhase.COMPLETED


@pytest.mark.asyncio
async def test_unconfirmed_generation_raises_and_costs_no_writer_call(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    with pytest.raises(ConfirmationRequiredError):
        service.assert_generation_allowed(NOVEL_ID, 2)
    with pytest.raises(ConfirmationRequiredError):
        await service.run_chapter_pipeline(NOVEL_ID, 2, author_service=author)

    assert env["writer"].generate_calls == 0


# ---------------------------------------------------------------------------
# P0-7: the confirmation freezes content, not just a revision number
# ---------------------------------------------------------------------------


def test_confirmation_freezes_synopsis_content(env):
    service: StatefulPipelineService = env["service"]

    service.update_synopsis(NOVEL_ID, 1, title="旧标题", synopsis="第一版细纲。")
    confirmation = service.confirm_chapter(NOVEL_ID, 1, _preference(1))

    assert confirmation.synopsis_revision == 2
    assert confirmation.synopsis_title == "旧标题"
    assert confirmation.synopsis_text == "第一版细纲。"

    service.update_synopsis(
        NOVEL_ID, 1, title="新标题", synopsis="第二版细纲，陈晨拿到铜钥匙。"
    )
    assert service.get_synopsis(NOVEL_ID, 1).revision == 3

    # The frozen snapshot still carries revision 2 content.
    state = service.get_pipeline_state(NOVEL_ID, 1)
    assert state.synopsis_revision == 2
    assert state.synopsis_title == "旧标题"
    assert state.synopsis_text == "第一版细纲。"


@pytest.mark.asyncio
async def test_synopsis_edit_after_confirmation_fails_closed(env):
    """Scenario 8: confirm revision 2, edit to 3, generate must not use 3."""

    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    service.update_synopsis(NOVEL_ID, 1, synopsis="第二版细纲，陈晨拿到铜钥匙。")
    confirmation = service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    assert confirmation.synopsis_revision == 2

    service.update_synopsis(NOVEL_ID, 1, synopsis="第三版细纲，储物柜被强行撬开。")
    assert service.get_synopsis(NOVEL_ID, 1).revision == 3

    with pytest.raises(ConfirmationStaleError) as excinfo:
        service.assert_generation_allowed(NOVEL_ID, 1)
    assert "synopsis_revision" in str(excinfo.value)

    with pytest.raises(ConfirmationStaleError):
        await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    # Fail closed: no Writer call and the chapter never used revision 3.
    assert env["writer"].generate_calls == 0
    state = service.get_pipeline_state(NOVEL_ID, 1)
    assert state.phase == ChapterPipelinePhase.CONFIRMED
    assert state.synopsis_revision == 2
    assert "第三版细纲" not in state.synopsis_text


@pytest.mark.asyncio
async def test_story_bible_edit_after_confirmation_fails_closed(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    bible = author.bibles.load()
    author.bibles.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            premise=bible.premise,
            theme=bible.theme,
            setting_summary="改写后的城市设定。",
        )
    )

    with pytest.raises(ConfirmationStaleError) as excinfo:
        await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    assert "story_bible_revision" in str(excinfo.value)
    assert env["writer"].generate_calls == 0


@pytest.mark.asyncio
async def test_outline_edit_after_confirmation_fails_closed(env):
    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    store = BookOutlineStore(env["data_dir"])
    current = store.load()
    store.update(BookOutlineUpdate(expected_revision=current.revision, logline="改写后的主线。"))

    with pytest.raises(ConfirmationStaleError) as excinfo:
        await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)

    assert "outline_revision" in str(excinfo.value)
    assert env["writer"].generate_calls == 0


@pytest.mark.asyncio
async def test_canon_moved_by_another_commit_fails_closed(env):
    """A confirmation frozen before another chapter committed cannot be used."""

    service: StatefulPipelineService = env["service"]
    author: AuthorGenerationService = env["author"]

    # Confirm chapter 2 first, then commit chapter 1: canon advances underneath.
    service.confirm_chapter(NOVEL_ID, 2, _preference(2))
    canon_before = CanonicalStateStore(env["data_dir"]).load().revision

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    first = await service.run_chapter_pipeline(NOVEL_ID, 1, author_service=author)
    assert first.phase == ChapterPipelinePhase.COMPLETED
    assert CanonicalStateStore(env["data_dir"]).load().revision > canon_before

    with pytest.raises(ConfirmationStaleError) as excinfo:
        await service.run_chapter_pipeline(NOVEL_ID, 2, author_service=author)

    assert "canon_revision" in str(excinfo.value)
    # Only chapter 1 consumed a Writer call.
    assert env["writer"].generate_calls == 1

    # Re-confirming chapter 2 against the new authorities works.
    service.confirm_chapter(NOVEL_ID, 2, _preference(2))
    second = await service.run_chapter_pipeline(NOVEL_ID, 2, author_service=author)
    assert second.phase == ChapterPipelinePhase.COMPLETED
    assert env["writer"].generate_calls == 2


def test_every_authority_revision_is_frozen(env):
    service: StatefulPipelineService = env["service"]

    confirmation = service.confirm_chapter(NOVEL_ID, 1, _preference(1))

    assert confirmation.story_bible_revision >= 1
    assert confirmation.canon_revision >= 1
    assert confirmation.story_thread_revision >= 1
    assert confirmation.memory_revision >= 1
    assert confirmation.outline_revision >= 1
    assert confirmation.information_schema_revision >= 0
    drift = confirmation.revisions().drift(confirmation.revisions())
    assert drift == []


# ---------------------------------------------------------------------------
# API level: confirmation gate returns 409 without ever queueing a Writer
# ---------------------------------------------------------------------------


def _user(user_id: str) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@local",
        has_password=False,
        save_my_works=True,
        created_at=datetime.fromtimestamp(0, tz=timezone.utc),
    )


@pytest.fixture
def api(monkeypatch, env, tmp_path):
    """Bind the pipeline routes to the seeded domain without an HTTP server.

    The route handlers are plain coroutines, so calling them directly keeps the
    HTTPException semantics while avoiding a TestClient portal (whose socket
    pair is only reclaimed by GC and trips ``-W error`` at session end).
    """

    root = str(tmp_path / "users_root")
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", root)
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", str(Path(root) / "users"))
    monkeypatch.setattr(
        novel_manager, "_LEGACY_NOVELS_DIR", str(Path(root) / "novels")
    )
    novel = novel_manager.create_novel(USER_ID, "铜钥匙")
    novel_id = novel["id"]

    # Point the cached pipeline service at the seeded domain.
    pipeline_routes._service_cache[(USER_ID, novel_id)] = env["service"]

    submitted: list[dict] = []

    class _StubTaskManager:
        def submit(self, **kwargs):
            submitted.append(kwargs)
            return SimpleNamespace(id="task_stub")

    import tasks.task_manager as task_manager_module

    monkeypatch.setattr(
        task_manager_module, "get_task_manager", lambda: _StubTaskManager()
    )

    user = _user(USER_ID)

    def confirm(chapter: int, count: int = 0):
        return pipeline_routes.confirm_chapter(
            novel_id=novel_id,
            request=ConfirmAndGenerateRequest(
                chapter=chapter,
                foreshadow_mode="fixed",
                foreshadow_count=count,
            ),
            user=user,
        )

    def retry(chapter: int, count: int = 0):
        return pipeline_routes.retry_chapter(
            novel_id=novel_id,
            chapter=chapter,
            request=RetryChapterRequest(
                foreshadow_mode="fixed",
                foreshadow_count=count,
            ),
            user=user,
        )

    def generate(chapter: int):
        return pipeline_routes.generate_chapter(
            novel_id=novel_id, chapter=chapter, user=user
        )

    def status(chapter: int):
        return pipeline_routes.get_pipeline_status(
            novel_id=novel_id, chapter=chapter, user=user
        )

    yield SimpleNamespace(
        novel_id=novel_id,
        user=user,
        submitted=submitted,
        env=env,
        confirm=confirm,
        retry=retry,
        generate=generate,
        status=status,
    )
    pipeline_routes._service_cache.clear()


@pytest.mark.asyncio
async def test_api_generate_without_confirm_returns_409_and_no_writer_call(api):
    with pytest.raises(HTTPException) as excinfo:
        await api.generate(1)

    assert excinfo.value.status_code == 409
    assert "confirm" in str(excinfo.value.detail).lower()
    assert api.submitted == []
    assert api.env["writer"].generate_calls == 0


@pytest.mark.asyncio
async def test_api_confirm_then_generate_is_not_rejected(api):
    payload = await api.confirm(1)
    assert payload["confirmed"] is True
    assert payload["phase"] == ChapterPipelinePhase.CONFIRMED.value
    assert payload["binding"]["outline_revision"] >= 1

    body = await api.generate(1)
    assert body["status"] == "queued"
    # Nothing is committed until the Author journal says so.
    assert body["committed"] is False
    assert len(api.submitted) == 1

    status = await api.status(1)
    assert status.phase == ChapterPipelinePhase.CONFIRMED.value
    assert status.committed is False


@pytest.mark.asyncio
async def test_api_reports_committed_only_after_real_author_commit(api):
    env = api.env
    service: StatefulPipelineService = env["service"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    result = await service.run_chapter_pipeline(
        NOVEL_ID, 1, author_service=env["author"]
    )
    assert result.phase == ChapterPipelinePhase.COMPLETED
    assert result.committed_manuscript is True

    status = await api.status(1)
    assert status.phase == ChapterPipelinePhase.COMPLETED.value
    assert status.committed is True
    assert status.committed_char_count == result.committed_char_count
    assert status.committed_canonical_revision == result.committed_canonical_revision

    body = await api.generate(1)
    assert body["status"] == "already_completed"
    assert body["committed"] is True
    assert body["transaction_id"] == result.author_transaction_id
    assert body["section_id"] == result.committed_section_id
    # A completed chapter is never silently regenerated.
    assert api.submitted == []
    assert env["writer"].generate_calls == 1


@pytest.mark.asyncio
async def test_api_retry_refused_before_first_attempt(api):
    with pytest.raises(HTTPException) as excinfo:
        await api.retry(1)

    assert excinfo.value.status_code == 409
    assert api.submitted == []


@pytest.mark.asyncio
async def test_api_retry_creates_a_new_attempt(api):
    env = api.env
    service: StatefulPipelineService = env["service"]

    service.confirm_chapter(NOVEL_ID, 1, _preference(1))
    first = await service.run_chapter_pipeline(
        NOVEL_ID, 1, author_service=env["author"]
    )
    assert first.attempt == 1

    body = await api.retry(1)
    assert body["attempt"] == 2
    assert body["phase"] == ChapterPipelinePhase.CONFIRMED.value

    queued = await api.generate(1)
    assert queued["status"] == "queued"
    assert queued["attempt"] == 2
    assert len(api.submitted) == 1


@pytest.mark.asyncio
async def test_api_completed_chapter_reports_real_commit_evidence(api):
    data_dir = api.env["data_dir"]

    # A COMPLETED phase with no Author commit evidence must not claim success.
    store = PipelineStateStore(data_dir)
    store.save(
        ChapterPipelineState(
            novel_id=NOVEL_ID,
            chapter_number=1,
            phase=ChapterPipelinePhase.COMPLETED,
        )
    )

    body = await api.generate(1)
    assert body["status"] == "already_completed"
    assert body["committed"] is False
    assert api.submitted == []
    assert api.env["writer"].generate_calls == 0

    status = await api.status(1)
    assert status.phase == ChapterPipelinePhase.COMPLETED.value
    assert status.committed is False
