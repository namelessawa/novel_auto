from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import novel_manager
import tick_runtime
from api import story_routes
from auth import get_current_user
from auth.models import User
from sections.section_store import TickSection, _clear_for_tests
from story.models import (
    ContextManifest,
    GenerationTransaction,
    MemoryRecord,
    ValidationReport,
    ValidationViolation,
    WriterCandidate,
)
from story.narrative_contract import NarrativeValidationReport
from story.persistence import (
    ContextManifestStore,
    GenerationTransactionStore,
    MemoryRepository,
)
from story.production_models import (
    ChapterOutline,
    NovelProductionSpec,
    ProductionContextSnapshot,
    StyleProfile,
)
from story.runtime import clear_author_runtimes
from story.service import GenerationRejected
from tasks.task_manager import get_task_manager


_OPEN_CLIENTS: list[TestClient] = []


def _user(uid: str) -> User:
    return User(
        id=uid,
        email=f"{uid}@local",
        has_password=False,
        save_my_works=True,
        created_at=datetime.fromtimestamp(0, tz=timezone.utc),
    )


@pytest.fixture
def isolated_api(monkeypatch, tmp_path):
    root = str(tmp_path)
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", root)
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", os.path.join(root, "users"))
    monkeypatch.setattr(
        novel_manager, "_LEGACY_NOVELS_DIR", os.path.join(root, "novels")
    )
    get_task_manager()._clear_for_tests()
    clear_author_runtimes()
    _clear_for_tests()
    try:
        yield
    finally:
        while _OPEN_CLIENTS:
            _OPEN_CLIENTS.pop().__exit__(None, None, None)
        get_task_manager()._clear_for_tests()
        clear_author_runtimes()
        _clear_for_tests()


def _client(uid: str) -> TestClient:
    app = FastAPI()
    app.include_router(story_routes.router)
    app.dependency_overrides[get_current_user] = lambda: _user(uid)
    client = TestClient(app)
    client.__enter__()
    _OPEN_CLIENTS.append(client)
    return client


def test_story_bible_get_put_and_revision_conflict(isolated_api) -> None:
    novel = novel_manager.create_novel("alice", "潮门")
    client = _client("alice")

    initial = client.get(f"/api/novels/{novel['id']}/story-bible")
    assert initial.status_code == 200
    revision = initial.json()["story_bible"]["revision"]
    saved = client.put(
        f"/api/novels/{novel['id']}/story-bible",
        json={
            "expected_revision": revision,
            "premise": "守门人必须选择。",
            "theme": "身份与牺牲",
            "setting_summary": "雾历旧港。",
            "immutable_world_rules": ["死亡不可逆"],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["story_bible"]["revision"] == revision + 1
    assert saved.json()["story_bible"]["migration"]["needs_confirmation"] is False

    conflict = client.put(
        f"/api/novels/{novel['id']}/story-bible",
        json={
            "expected_revision": revision,
            "premise": "旧版本",
            "theme": "旧主题",
            "setting_summary": "旧背景",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "REVISION_CONFLICT"
    assert conflict.json()["detail"]["details"]["actual"] == revision + 1


def test_canonical_threads_mode_manifest_and_tenant_isolation(isolated_api) -> None:
    alice_novel = novel_manager.create_novel("alice", "A")
    novel_manager.create_novel("bob", "B")
    alice = _client("alice")
    bob = _client("bob")
    prefix = f"/api/novels/{alice_novel['id']}"

    assert alice.get(prefix + "/canonical-state").json()["authority"] == "only_current_fact_source"
    assert alice.get(prefix + "/story-threads").json()["threads"] == {}
    mode = alice.get(prefix + "/generation-mode").json()
    assert mode["mode"] == "author"
    assert "实验" in mode["modes"]["simulation"]
    manifest = alice.get(prefix + "/context-manifest").json()
    assert manifest["novel_id"] == alice_novel["id"]
    assert manifest["slots"] == []

    hidden = bob.get(prefix + "/canonical-state")
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "NOVEL_NOT_FOUND"


def test_generation_mode_revision_and_author_default(isolated_api) -> None:
    novel = novel_manager.create_novel("alice", "模式")
    client = _client("alice")
    path = f"/api/novels/{novel['id']}/generation-mode"
    current = client.get(path).json()

    updated = client.put(
        path,
        json={"expected_revision": current["revision"], "mode": "author"},
    )
    assert updated.status_code == 200
    assert updated.json()["mode"] == "author"
    assert updated.json()["revision"] == current["revision"] + 1

    conflict = client.put(
        path,
        json={"expected_revision": current["revision"], "mode": "author"},
    )
    assert conflict.status_code == 409


def test_generation_mode_rolls_back_when_simulation_runtime_fails(
    isolated_api, monkeypatch
) -> None:
    novel = novel_manager.create_novel("alice", "回滚")
    client = _client("alice")
    path = f"/api/novels/{novel['id']}/generation-mode"
    current = client.get(path).json()

    def fail_runtime(user_id, novel_id):
        raise RuntimeError("simulated runtime assembly failure")

    monkeypatch.setattr(tick_runtime, "set_active_novel", fail_runtime)
    failed = client.put(
        path,
        json={"expected_revision": current["revision"], "mode": "simulation"},
    )

    assert failed.status_code == 503
    restored = client.get(path).json()
    assert restored["mode"] == "author"
    assert restored["revision"] == current["revision"] + 2


def test_section_generate_task_and_status_expose_validation_not_prompt(
    isolated_api, monkeypatch
) -> None:
    novel = novel_manager.create_novel("alice", "生成")

    section = TickSection(
        id="ch0001_s0001",
        chapter=1,
        section=1,
        title="选择",
        content="身份与牺牲。",
        word_count=6,
        tick_start=0,
        tick_end=0,
        generation_mode="author",
    )

    class _Service:
        def __init__(self):
            self.sections = SimpleNamespace(get_by_id=lambda _: section)

        async def run(self, goal, request_id):
            return GenerationTransaction(
                id=request_id,
                user_id="alice",
                novel_id=novel["id"],
                section_id=section.id,
                phase="committed",
                story_bible_revision=1,
                canonical_state_revision=1,
                target_canonical_revision=2,
                writer_calls=1,
                committed=True,
                validation_report=ValidationReport(accepted=True),
            )

    monkeypatch.setattr(
        story_routes,
        "get_author_runtime",
        lambda user_id, novel_id: SimpleNamespace(service=_Service()),
    )
    client = _client("alice")
    created = client.post(
        f"/api/novels/{novel['id']}/sections/generate",
        json={"objective": "让主角回应身份与牺牲", "desired_length": 800},
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]
    time.sleep(0.05)
    status = client.get(
        f"/api/novels/{novel['id']}/sections/{task_id}/status"
    )
    assert status.status_code == 200
    task = status.json()["task"]
    assert task["status"] == "completed"
    assert task["committed"] is True
    assert task["validation_report"]["accepted"] is True
    assert "prompt" not in status.text.lower()


def test_validation_failure_is_queryable_and_has_no_section(
    isolated_api, monkeypatch
) -> None:
    novel = novel_manager.create_novel("alice", "拒绝")
    data_dir = novel_manager.get_novel_data_dir("alice", novel["id"])

    class _Service:
        sections = SimpleNamespace(get_by_id=lambda _: None)

        async def run(self, goal, request_id):
            report = ValidationReport(
                accepted=False,
                severity="high",
                violations=[
                    ValidationViolation(
                        code="IMMUTABLE_RULE_REVIVAL",
                        message="死亡不可逆",
                        severity="high",
                    )
                ],
            )
            tx = GenerationTransaction(
                id=request_id,
                user_id="alice",
                novel_id=novel["id"],
                section_id="ch0001_s0001",
                phase="rejected",
                story_bible_revision=1,
                canonical_state_revision=1,
                target_canonical_revision=2,
                writer_calls=2,
                repair_performed=True,
                validation_report=report,
                error="高置信一致性冲突在一次修复后仍存在",
            )
            GenerationTransactionStore(data_dir).save(tx)
            raise GenerationRejected(tx)

    monkeypatch.setattr(
        story_routes,
        "get_author_runtime",
        lambda user_id, novel_id: SimpleNamespace(service=_Service()),
    )
    client = _client("alice")
    created = client.post(
        f"/api/novels/{novel['id']}/sections/generate",
        json={"objective": "尝试复活旧王"},
    )
    task_id = created.json()["id"]
    time.sleep(0.05)
    status = client.get(
        f"/api/novels/{novel['id']}/sections/{task_id}/status"
    ).json()
    assert status["task"]["status"] == "failed"
    assert status["transaction"]["phase"] == "rejected"
    assert status["transaction"]["validation_report"]["violations"][0]["code"] == "IMMUTABLE_RULE_REVIVAL"
    assert status["section"] is None


def test_contract_preview_is_semantic_and_does_not_expose_validator_patterns(
    isolated_api,
) -> None:
    novel = novel_manager.create_novel("alice", "契约预览")
    client = _client("alice")
    bible_path = f"/api/novels/{novel['id']}/story-bible"
    revision = client.get(bible_path).json()["story_bible"]["revision"]
    saved = client.put(
        bible_path,
        json={
            "expected_revision": revision,
            "premise": "两名维护者必须在灯塔完成旧信交接。",
            "theme": "责任与选择",
            "setting_summary": "没有超自然力量的旧港灯塔。",
        },
    )
    assert saved.status_code == 200, saved.text

    preview = client.post(
        f"/api/novels/{novel['id']}/sections/contract-preview",
        json={
            "objective": "沈砚把旧信交给林秋",
            "desired_length": 400,
            "narrative_constraints": {
                "required_events": [
                    {
                        "id": "handover",
                        "actor": "沈砚",
                        "action": "交信",
                        "target": "林秋",
                        "evidence_patterns": ["秘密服务端模式"],
                    }
                ]
            },
        },
    )
    assert preview.status_code == 200, preview.text
    contract = preview.json()["narrative_contract"]
    assert contract["required_events"][0]["id"] == "handover"
    assert contract["style_priority"] == "subordinate_to_facts"
    assert "evidence_patterns" not in preview.text
    assert "秘密服务端模式" not in preview.text
    assert "prompt" not in preview.text.lower()


def test_long_run_status_aggregates_transactions_without_prose(isolated_api) -> None:
    novel = novel_manager.create_novel("alice", "长程状态")
    data_dir = novel_manager.get_novel_data_dir("alice", novel["id"])
    GenerationTransactionStore(data_dir).save(
        GenerationTransaction(
            id="run_section_0001",
            user_id="alice",
            novel_id=novel["id"],
            section_id="ch0001_s0001",
            phase="committed",
            story_bible_revision=1,
            canonical_state_revision=1,
            target_canonical_revision=2,
            writer_calls=2,
            repair_performed=True,
            committed=True,
            narrative_validation_report=NarrativeValidationReport(
                accepted=True,
                contract_coverage=1.0,
            ),
            validation_report=ValidationReport(accepted=True),
            usage={"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12},
            recovery_count=1,
        )
    )

    response = _client("alice").get(
        f"/api/novels/{novel['id']}/long-run/status"
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run_id"] == "run_section_0001"
    assert payload["completed_sections"] == 1
    assert payload["contract_pass_rate"] == 1.0
    assert payload["repair_rate"] == 1.0
    assert payload["hard_reject_count"] == 0
    assert payload["total_tokens"] == 12
    assert payload["restart_recovery_count"] == 1
    assert "narrative_text" not in response.text


def test_memory_and_transaction_ledger_are_auditable_and_redacted(
    isolated_api,
) -> None:
    novel = novel_manager.create_novel("alice", "证据台")
    data_dir = novel_manager.get_novel_data_dir("alice", novel["id"])
    memory_store = MemoryRepository(data_dir)
    memory_store.save(
        memory_store.load().model_copy(
            update={
                "revision": 2,
                "records": {
                    "memory-1": MemoryRecord(
                        id="memory-1",
                        type="promise",
                        section_id="ch0001_s0001",
                        entities=["shen_yan"],
                        summary="沈砚承诺在天亮前交信。",
                        importance=8,
                        created_at_revision=2,
                    )
                },
            }
        )
    )
    ContextManifestStore(data_dir, novel_id=novel["id"]).save(
        ContextManifest(
            novel_id=novel["id"],
            section_id="ch0001_s0002",
            story_bible_revision=1,
            canonical_state_revision=2,
            selected_memory_ids=["memory-1"],
            active_thread_ids=["harbor"],
            total_chars=10,
            total_token_estimate=5,
            max_context_chars=100,
            max_context_token_estimate=50,
        )
    )
    GenerationTransactionStore(data_dir).save(
        GenerationTransaction(
            id="redacted_transaction",
            user_id="alice",
            novel_id=novel["id"],
            section_id="ch0001_s0002",
            phase="rejected",
            story_bible_revision=1,
            canonical_state_revision=2,
            target_canonical_revision=3,
            writer_calls=1,
            candidate=WriterCandidate(
                narrative_text="REJECTED_CANDIDATE_MUST_NEVER_LEAK",
                section_summary="拒绝候选",
            ),
            usage={"total_tokens": 12, "api_key": 999},
            error="Authorization: fixture-redaction-sentinel",
            production_context=ProductionContextSnapshot(
                job_id="job_public_evidence",
                job_revision=3,
                production_spec=NovelProductionSpec(
                    title="Public evidence",
                    premise="A recoverable production run.",
                    theme="continuity",
                    target_total_chars=1_000,
                    volume_count=1,
                    chapter_count=1,
                    target_chapter_chars=1_000,
                    accepted_chapter_min_chars=900,
                    accepted_chapter_max_chars=1_100,
                    section_target_chars=1_000,
                ),
                outline_revision=4,
                chapter_outline=ChapterOutline(
                    id="chapter_0001",
                    ordinal=1,
                    volume_id="volume_0001",
                    title="Public chapter",
                    objective="Advance the public evidence contract.",
                    target_chars=1_000,
                ),
                style_profile=StyleProfile(
                    id="style_public",
                    revision=2,
                    name="Public style",
                    optional_user_sample="PRIVATE_STYLE_SAMPLE_MUST_NEVER_LEAK",
                ),
                story_bible_revision=1,
                canonical_state_revision=2,
                story_thread_revision=1,
                memory_revision=1,
                chapter_attempt=1,
                section_ordinal=2,
                section_target_chars=1_000,
                section_min_chars=900,
                section_max_chars=1_100,
            ),
        )
    )

    client = _client("alice")
    memories = client.get(f"/api/novels/{novel['id']}/memories")
    assert memories.status_code == 200, memories.text
    assert memories.json()["records"][0]["selected"] is True
    assert memories.json()["records"][0]["summary"] == "沈砚承诺在天亮前交信。"

    transactions = client.get(f"/api/novels/{novel['id']}/transactions")
    assert transactions.status_code == 200, transactions.text
    payload = transactions.json()["transactions"][0]
    assert payload["error"] == "内部错误已记录"
    assert payload["usage"] == {"total_tokens": 12}
    assert "REJECTED_CANDIDATE_MUST_NEVER_LEAK" not in transactions.text
    assert "fixture-redaction-sentinel" not in transactions.text
    assert "api_key" not in transactions.text
    assert "base_canonical_state" not in transactions.text
    assert "PRIVATE_STYLE_SAMPLE_MUST_NEVER_LEAK" not in transactions.text
    production_context = payload["production_context"]
    assert production_context["job_id"] == "job_public_evidence"
    assert production_context["chapter_ordinal"] == 1
    assert production_context["section_ordinal"] == 2
    assert production_context["style_profile_id"] == "style_public"
    assert production_context["style_profile_revision"] == 2
    assert len(production_context["style_prompt_hash"]) == 64


def test_exports_include_only_committed_prose_and_public_evidence(
    isolated_api,
) -> None:
    novel = novel_manager.create_novel("alice", "导出边界")
    data_dir = novel_manager.get_novel_data_dir("alice", novel["id"])
    transactions = GenerationTransactionStore(data_dir)
    store = story_routes.get_section_store(novel["id"], data_dir=data_dir)
    rows = [
        ("committed_tx", "committed", True, "COMMITTED_PROSE", 1),
        ("rejected_tx", "rejected", False, "REJECTED_PROSE", 2),
        ("staged_tx", "validated", False, "STAGED_PROSE", 3),
    ]
    for transaction_id, phase, committed, prose, section_no in rows:
        transactions.save(
            GenerationTransaction(
                id=transaction_id,
                user_id="alice",
                novel_id=novel["id"],
                section_id=f"ch0001_s{section_no:04d}",
                phase=phase,
                story_bible_revision=1,
                canonical_state_revision=section_no,
                target_canonical_revision=section_no + 1,
                writer_calls=1,
                committed=committed,
                candidate=WriterCandidate(
                    narrative_text=f"{prose}_CANDIDATE",
                    section_summary=prose,
                ),
            )
        )
        store.append(
            TickSection(
                id=f"ch0001_s{section_no:04d}",
                chapter=1,
                section=section_no,
                title=prose,
                content=prose,
                word_count=len(prose),
                tick_start=0,
                tick_end=0,
                generation_mode="author",
                transaction_id=transaction_id,
            )
        )

    client = _client("alice")
    manuscript = client.get(f"/api/novels/{novel['id']}/exports/manuscript")
    assert manuscript.status_code == 200, manuscript.text
    assert "COMMITTED_PROSE" in manuscript.text
    assert "REJECTED_PROSE" not in manuscript.text
    assert "STAGED_PROSE" not in manuscript.text
    assert manuscript.headers["x-included-sections"] == "1"
    assert manuscript.headers["x-excluded-sections"] == "2"
    assert len(manuscript.headers["x-artifact-sha256"]) == 64

    evidence = client.get(f"/api/novels/{novel['id']}/exports/evidence")
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["committed_sections"][0]["id"] == "ch0001_s0001"
    assert set(evidence.json()["excluded_section_ids"]) == {
        "ch0001_s0002",
        "ch0001_s0003",
    }
    assert "COMMITTED_PROSE_CANDIDATE" not in evidence.text
    assert "REJECTED_PROSE_CANDIDATE" not in evidence.text
    assert "STAGED_PROSE_CANDIDATE" not in evidence.text
    assert len(evidence.headers["x-artifact-sha256"]) == 64


def test_recovery_resume_is_idempotent_and_reports_pending(
    isolated_api, monkeypatch
) -> None:
    novel = novel_manager.create_novel("alice", "恢复")
    data_dir = novel_manager.get_novel_data_dir("alice", novel["id"])
    transactions = GenerationTransactionStore(data_dir)
    pending = GenerationTransaction(
        id="pending_tx",
        user_id="alice",
        novel_id=novel["id"],
        section_id="ch0001_s0001",
        phase="validated",
        story_bible_revision=1,
        canonical_state_revision=1,
        target_canonical_revision=2,
        writer_calls=1,
    )
    transactions.save(pending)

    class _RecoveryService:
        def recover(self):
            current = transactions.load("pending_tx")
            transactions.save(
                current.model_copy(update={"phase": "committed", "committed": True})
            )
            return ["pending_tx"]

    monkeypatch.setattr(
        story_routes,
        "get_author_runtime",
        lambda user_id, novel_id: SimpleNamespace(service=_RecoveryService()),
    )
    client = _client("alice")
    first = client.post(f"/api/novels/{novel['id']}/recovery/resume")
    assert first.status_code == 200, first.text
    assert first.json() == {
        "status": "recovered",
        "pending_before": ["pending_tx"],
        "recovered_transaction_ids": ["pending_tx"],
        "pending_after": [],
    }

    second = client.post(f"/api/novels/{novel['id']}/recovery/resume")
    assert second.status_code == 200, second.text
    assert second.json()["pending_before"] == []
    assert second.json()["pending_after"] == []
