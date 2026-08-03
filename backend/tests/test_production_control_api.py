from __future__ import annotations

import asyncio
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import novel_manager
from api import production_control_routes
from auth import get_current_user
from auth.models import User
from story.production_runtime import (
    close_all_production_runtimes,
    get_production_runtime,
)
from story.production_service import SectionRunRequest, SectionRunResult
from backend.tests.test_production_runtime import SuccessfulRunner, _configure_book


def _user(user_id: str) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@local",
        has_password=False,
        save_my_works=True,
        created_at=datetime.fromtimestamp(0, tz=timezone.utc),
    )


@contextmanager
def _client(user_id: str) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(production_control_routes.router)
    app.dependency_overrides[get_current_user] = lambda: _user(user_id)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def isolated_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = str(tmp_path / "data")
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", root)
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", os.path.join(root, "users"))
    monkeypatch.setattr(
        novel_manager,
        "_LEGACY_NOVELS_DIR",
        os.path.join(root, "novels"),
    )
    yield
    cleanup_loop = asyncio.new_event_loop()
    try:
        cleanup_loop.run_until_complete(close_all_production_runtimes())
    finally:
        cleanup_loop.close()


def _create_novel(user_id: str = "alice"):
    novel = novel_manager.create_novel(user_id, "潮汐之城")
    data_dir = Path(novel_manager.get_novel_data_dir(user_id, novel["id"]))
    _configure_book(data_dir)
    return novel, data_dir, f"/api/novels/{novel['id']}"


def _wait_for_status(service, statuses: set[str], timeout: float = 5) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = service.get_job().status
        if status in statuses:
            return status
        time.sleep(0.02)
    return service.get_job().status


class BlockingRunner:
    def __init__(self, data_dir: Path) -> None:
        self.inner = SuccessfulRunner(data_dir)
        self.entered = threading.Event()
        self.release = threading.Event()

    async def run_section(self, request: SectionRunRequest) -> SectionRunResult:
        self.entered.set()
        await asyncio.to_thread(self.release.wait)
        return await self.inner.run_section(request)


class FailOnceRunner:
    def __init__(self, data_dir: Path) -> None:
        self.inner = SuccessfulRunner(data_dir)
        self.failed_transaction = ""

    async def run_section(self, request: SectionRunRequest) -> SectionRunResult:
        if not self.failed_transaction:
            self.failed_transaction = request.transaction_id
            raise RuntimeError("recorded section failure")
        return await self.inner.run_section(request)


def _start_payload(runtime) -> dict[str, int]:
    return {
        "expected_spec_revision": runtime.service.specs.load().revision,
        "expected_outline_revision": runtime.service.outlines.load().revision,
    }


def test_main_wires_the_production_control_surface() -> None:
    from main import app

    paths = {route.path for route in app.routes}
    assert {
        "/api/novels/{novel_id}/production/start",
        "/api/novels/{novel_id}/production/status",
        "/api/novels/{novel_id}/production/events",
        "/api/novels/{novel_id}/chapters",
        "/api/novels/{novel_id}/chapters/{chapter_id}",
    } <= paths


def test_tenant_and_missing_job_are_404(isolated_api) -> None:
    novel, data_dir, prefix = _create_novel()
    get_production_runtime(
        "alice",
        novel["id"],
        data_dir=str(data_dir),
        section_runner=SuccessfulRunner(data_dir),
    )

    with _client("alice") as client:
        missing = client.get(prefix + "/production/status")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "PRODUCTION_JOB_NOT_FOUND"

    with _client("bob") as client:
        hidden = client.get(prefix + "/production/status")
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "NOVEL_NOT_FOUND"


def test_start_is_idempotent_pause_is_safe_and_reads_are_committed_only(
    isolated_api,
) -> None:
    novel, data_dir, prefix = _create_novel()
    runner = BlockingRunner(data_dir)
    runtime = get_production_runtime(
        "alice",
        novel["id"],
        data_dir=str(data_dir),
        section_runner=runner,
    )
    payload = _start_payload(runtime)

    with _client("alice") as client:
        first = client.post(prefix + "/production/start", json=payload)
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body["existing"] is False
        assert runner.entered.wait(3)

        duplicate = client.post(prefix + "/production/start", json=payload)
        assert duplicate.status_code == 200
        assert duplicate.json()["existing"] is True
        assert duplicate.json()["job"]["id"] == first_body["job"]["id"]

        assert client.get(prefix + "/chapters").json()["chapters"] == []
        hidden = client.get(prefix + "/chapters/chapter_0001")
        assert hidden.status_code == 404
        assert hidden.json()["detail"]["code"] == "COMMITTED_CHAPTER_NOT_FOUND"

        events = client.get(
            prefix + "/production/events",
            params={"job_id": first_body["job"]["id"], "follow": "false"},
        )
        assert events.status_code == 200
        assert "event: job_status" in events.text
        assert "event: section_started" in events.text

        current = runtime.service.get_job()
        stale = client.post(
            prefix + "/production/pause",
            json={"job_id": current.id, "expected_revision": current.revision - 1},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"

        requested = client.post(
            prefix + "/production/pause",
            json={"job_id": current.id, "expected_revision": current.revision},
        )
        assert requested.status_code == 200
        assert requested.json()["job"]["status"] == "pausing"
        runner.release.set()
        assert _wait_for_status(runtime.service, {"paused"}) == "paused"
        assert len(runtime.service.list_chapters(committed_only=True)) == 1
        committed_transaction = runner.inner.transactions[0]

        paused = runtime.service.get_job()
        resume_stale = client.post(
            prefix + "/production/resume",
            json={"job_id": paused.id, "expected_revision": paused.revision - 1},
        )
        assert resume_stale.status_code == 409
        resumed = client.post(
            prefix + "/production/resume",
            json={"job_id": paused.id, "expected_revision": paused.revision},
        )
        assert resumed.status_code == 200
        assert _wait_for_status(runtime.service, {"completed"}) == "completed"
        assert runner.inner.transactions == [committed_transaction]

        rows = client.get(prefix + "/chapters")
        assert rows.status_code == 200
        assert rows.json()["count"] == 1
        chapter_row = rows.json()["chapters"][0]
        assert "content" not in chapter_row["sections"][0]
        assert chapter_row["transaction_ids"] == [committed_transaction]
        assert chapter_row["transaction_id"] == committed_transaction
        assert chapter_row["committed_transaction_id"] == committed_transaction
        assert chapter_row["story_bible_revision_start"] >= 1
        assert (
            chapter_row["story_bible_revision_end"]
            == chapter_row["story_bible_revision"]
        )
        assert (
            chapter_row["canonical_revision_end"]
            == chapter_row["canonical_revision"]
            == chapter_row["canonical_state_revision"]
        )
        assert chapter_row["repair_total"] == 0
        assert chapter_row["repair_performed"] is False
        assert chapter_row["style_profile_name"]
        assert chapter_row["style_profile_revision"] >= 1
        chapter = client.get(prefix + "/chapters/chapter_0001")
        assert chapter.status_code == 200
        chapter_detail = chapter.json()["chapter"]
        assert chapter_detail["committed"] is True
        assert len(chapter_detail["content"]) == 1_000
        assert chapter_detail["transaction_ids"] == [committed_transaction]
        assert chapter_detail["sections"][0]["content"] == chapter_detail["content"]

        committed_record = runtime.service.list_chapters(committed_only=True)[0]
        repaired_section = committed_record.sections[0].model_copy(
            update={"repair_performed": True}
        )
        repaired_record = committed_record.model_copy(
            update={"sections": [repaired_section], "repair_total": 1}
        )
        repaired_payload = production_control_routes._public_chapter(
            repaired_record,
            include_content=False,
        )
        assert repaired_payload["repair_total"] == 1
        assert repaired_payload["repair_performed"] is True


def test_cancel_at_runner_boundary_is_revisioned(isolated_api) -> None:
    novel, data_dir, prefix = _create_novel()
    runner = BlockingRunner(data_dir)
    runtime = get_production_runtime(
        "alice",
        novel["id"],
        data_dir=str(data_dir),
        section_runner=runner,
    )
    with _client("alice") as client:
        started = client.post(
            prefix + "/production/start",
            json=_start_payload(runtime),
        ).json()["job"]
        assert runner.entered.wait(3)
        current = runtime.service.get_job(started["id"])
        stale = client.post(
            prefix + "/production/cancel",
            json={"job_id": current.id, "expected_revision": current.revision - 1},
        )
        assert stale.status_code == 409
        requested = client.post(
            prefix + "/production/cancel",
            json={"job_id": current.id, "expected_revision": current.revision},
        )
        assert requested.status_code == 200
        assert requested.json()["job"]["status"] == "cancelling"
        runner.release.set()
        assert _wait_for_status(runtime.service, {"cancelled"}) == "cancelled"
        committed = runtime.service.list_chapters(committed_only=True)
        assert len(committed) == 1
        assert committed[0].sections[0].transaction_id == runner.inner.transactions[0]


def test_retry_failed_uses_revision_and_a_new_transaction(isolated_api) -> None:
    novel, data_dir, prefix = _create_novel()
    runner = FailOnceRunner(data_dir)
    runtime = get_production_runtime(
        "alice",
        novel["id"],
        data_dir=str(data_dir),
        section_runner=runner,
    )
    with _client("alice") as client:
        started = client.post(
            prefix + "/production/start",
            json=_start_payload(runtime),
        ).json()["job"]
        assert _wait_for_status(runtime.service, {"failed"}) == "failed"
        failed = runtime.service.get_job(started["id"])

        stale = client.post(
            prefix + "/production/retry-failed",
            json={"job_id": failed.id, "expected_revision": failed.revision - 1},
        )
        assert stale.status_code == 409
        retried = client.post(
            prefix + "/production/retry-failed",
            json={"job_id": failed.id, "expected_revision": failed.revision},
        )
        assert retried.status_code == 200, retried.text
        assert _wait_for_status(runtime.service, {"completed"}) == "completed"
        assert runner.inner.transactions
        assert runner.inner.transactions[0] != runner.failed_transaction
