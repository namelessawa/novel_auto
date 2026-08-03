from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import novel_manager
from api import production_routes
from auth import get_current_user
from auth.models import User
from story.production_models import NovelProductionSpecUpdate, StyleProfile
from story.production_persistence import (
    BookOutlineStore,
    ProductionSpecStore,
)


_OPEN_CLIENTS: list[TestClient] = []


def _user(user_id: str) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@local",
        has_password=False,
        save_my_works=True,
        created_at=datetime.fromtimestamp(0, tz=timezone.utc),
    )


@pytest.fixture
def isolated_api(monkeypatch, tmp_path):
    root = str(tmp_path)
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", root)
    monkeypatch.setattr(
        novel_manager,
        "_USERS_ROOT",
        os.path.join(root, "users"),
    )
    monkeypatch.setattr(
        novel_manager,
        "_LEGACY_NOVELS_DIR",
        os.path.join(root, "novels"),
    )
    try:
        yield
    finally:
        while _OPEN_CLIENTS:
            _OPEN_CLIENTS.pop().__exit__(None, None, None)


def _client(user_id: str) -> TestClient:
    app = FastAPI()
    app.include_router(production_routes.router)
    app.dependency_overrides[get_current_user] = lambda: _user(user_id)
    client = TestClient(app)
    client.__enter__()
    _OPEN_CLIENTS.append(client)
    return client


def _create_novel(user_id: str = "alice") -> tuple[dict, TestClient, str]:
    novel = novel_manager.create_novel(user_id, "潮汐之城")
    client = _client(user_id)
    prefix = f"/api/novels/{novel['id']}"
    return novel, client, prefix


def _small_spec(client: TestClient, prefix: str) -> dict:
    current = client.get(prefix + "/production-spec").json()["production_spec"]
    response = client.put(
        prefix + "/production-spec",
        json={
            "expected_revision": current["revision"],
            "title": "潮汐之城",
            "premise": "城市以记忆换取潮汐平静。",
            "genre": "幻想悬疑",
            "theme": "记忆与责任",
            "central_question": "真相是否值得代价？",
            "target_total_chars": 1_000,
            "volume_count": 1,
            "chapter_count": 2,
            "target_chapter_chars": 500,
            "accepted_chapter_min_chars": 400,
            "accepted_chapter_max_chars": 600,
            "section_target_chars": 250,
            "generation_language": "zh-CN",
            "ending_direction": "公开真相并承担后果。",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["production_spec"]


def _valid_outline_payload() -> dict:
    return {
        "logline": "守潮人发现城市的平静以居民记忆为代价。",
        "global_arc": "发现代价，追查来源，公开真相。",
        "volumes": [
            {
                "id": "volume_001",
                "ordinal": 1,
                "title": "失潮",
                "objective": "确认遗忘机制",
                "opening_state": "潮汐平静",
                "closing_state": "真相公开",
                "target_chapters": 2,
                "target_chars": 1_000,
            }
        ],
        "chapters": [
            {
                "id": "chapter_0001",
                "ordinal": 1,
                "volume_id": "volume_001",
                "title": "退去的名字",
                "objective": "发现第一处记忆缺口",
                "target_chars": 500,
            },
            {
                "id": "chapter_0002",
                "ordinal": 2,
                "volume_id": "volume_001",
                "title": "归还潮声",
                "objective": "公开代价并承担后果",
                "target_chars": 500,
            },
        ],
        "ending_target": "城市保留真相并承担潮灾。",
        "major_turning_points": ["发现记忆账本", "公开交换机制"],
        "central_conflict_progression": ["怀疑", "求证", "承担"],
        "thread_schedule": {},
        "character_arc_schedule": {},
    }


def test_style_activation_targets_next_not_started_chapter() -> None:
    outline = production_routes.BookOutline(
        **_valid_outline_payload(),
        status="ready",
    )
    started = SimpleNamespace(chapter_id="chapter_0001")
    store = SimpleNamespace(list_all=lambda **_kwargs: [started])

    assert (
        production_routes._next_ungenerated_chapter(outline, store)
        == 2
    )


def _response(content: str, prompt_tokens: int = 3, completion_tokens: int = 5):
    return SimpleNamespace(
        content=content,
        usage_prompt_tokens=prompt_tokens,
        usage_completion_tokens=completion_tokens,
    )


def _json_bytes(data_dir: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in data_dir.glob("*.json")
        if path.is_file()
    }


def test_migration_is_idempotent_spec_is_revisioned_and_tenant_is_hidden(
    isolated_api,
) -> None:
    novel, alice, prefix = _create_novel()
    data_dir = Path(novel_manager.get_novel_data_dir("alice", novel["id"]))

    first = alice.get(prefix + "/production-spec")
    assert first.status_code == 200, first.text
    first_bytes = _json_bytes(data_dir)
    second = alice.get(prefix + "/production-spec")
    assert second.status_code == 200
    assert _json_bytes(data_dir) == first_bytes

    saved = _small_spec(alice, prefix)
    stale = alice.put(
        prefix + "/production-spec",
        json={
            "expected_revision": saved["revision"] - 1,
            "theme": "陈旧覆盖",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "REVISION_CONFLICT",
        "message": "数据已被其他会话更新，请重新载入",
        "details": {
            "expected": saved["revision"] - 1,
            "actual": saved["revision"],
        },
    }

    hidden = _client("bob").get(prefix + "/production-spec")
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "NOVEL_NOT_FOUND"


def test_outline_generate_uses_one_call_and_put_is_revision_aware(
    isolated_api,
    monkeypatch,
) -> None:
    _, client, prefix = _create_novel()
    spec = _small_spec(client, prefix)
    outline = client.get(prefix + "/outline").json()["book_outline"]
    calls: list[dict] = []

    async def fake_chat(**kwargs):
        calls.append(kwargs)
        proposed = _valid_outline_payload()
        proposed["chapters"][0]["status"] = "committed"
        proposed["chapters"][0]["committed_section_ids"] = ["provider_fake"]
        return _response(
            json.dumps(proposed, ensure_ascii=False),
            11,
            19,
        )

    monkeypatch.setattr("story.outline_generator.llm_client.chat", fake_chat)
    generated = client.post(
        prefix + "/outline/generate",
        json={
            "expected_spec_revision": spec["revision"],
            "expected_outline_revision": outline["revision"],
        },
    )
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["provider_calls"] == 1
    assert body["repair_performed"] is False
    assert body["usage"]["total_tokens"] == 30
    assert body["book_outline"]["revision"] == outline["revision"] + 1
    assert body["book_outline"]["chapters"][0]["status"] == "draft"
    assert body["book_outline"]["chapters"][0]["committed_section_ids"] == []
    assert len(calls) == 1
    assert calls[0]["agent_id"] == "whole_book_outline"

    current = body["book_outline"]
    saved = client.put(
        prefix + "/outline",
        json={
            "expected_revision": current["revision"],
            "logline": "守潮人必须决定是否归还所有人的记忆。",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["book_outline"]["revision"] == current["revision"] + 1

    stale = client.put(
        prefix + "/outline",
        json={
            "expected_revision": current["revision"],
            "global_arc": "陈旧编辑",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "REVISION_CONFLICT"

    invalid = client.put(
        prefix + "/outline",
        json={
            "expected_revision": saved.json()["book_outline"]["revision"],
            "volumes": [
                {
                    **_valid_outline_payload()["volumes"][0],
                    "target_chars": 1_200,
                }
            ],
            "chapters": [
                {
                    **_valid_outline_payload()["chapters"][0],
                    "target_chars": 600,
                },
                {
                    **_valid_outline_payload()["chapters"][1],
                    "target_chars": 600,
                },
            ],
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "BOOK_OUTLINE_INVALID"


def test_outline_generation_repairs_once_then_returns_sanitized_failure(
    isolated_api,
    monkeypatch,
) -> None:
    _, client, prefix = _create_novel()
    spec = _small_spec(client, prefix)
    calls: list[dict] = []

    async def fake_chat(**kwargs):
        calls.append(kwargs)
        return _response("not-json-with-api_key=SHOULD_NOT_LEAK")

    monkeypatch.setattr("story.outline_generator.llm_client.chat", fake_chat)
    response = client.post(
        prefix + "/outline/generate",
        json={"expected_spec_revision": spec["revision"]},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "PROVIDER_OUTPUT_INVALID"
    assert len(calls) == 2
    serialized = json.dumps(response.json(), ensure_ascii=False)
    assert "SHOULD_NOT_LEAK" not in serialized
    assert "candidate" not in serialized.lower()


def test_outline_generation_refuses_post_call_revision_drift(
    isolated_api,
    monkeypatch,
) -> None:
    novel, client, prefix = _create_novel()
    spec = _small_spec(client, prefix)
    data_dir = novel_manager.get_novel_data_dir("alice", novel["id"])
    store = ProductionSpecStore(
        data_dir,
        lambda: (_ for _ in ()).throw(AssertionError("spec must exist")),
    )

    async def fake_chat(**_kwargs):
        current = store.load()
        store.update(
            NovelProductionSpecUpdate(
                expected_revision=current.revision,
                theme="Provider 调用期间发生的并发编辑",
            )
        )
        return _response(json.dumps(_valid_outline_payload(), ensure_ascii=False))

    monkeypatch.setattr("story.outline_generator.llm_client.chat", fake_chat)
    response = client.post(
        prefix + "/outline/generate",
        json={"expected_spec_revision": spec["revision"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REVISION_CONFLICT"
    assert client.get(prefix + "/outline").json()["book_outline"]["revision"] == 1


def test_style_create_copy_update_delete_and_read_only_contract(
    isolated_api,
) -> None:
    _, client, prefix = _create_novel()
    created_response = client.post(
        prefix + "/style-profiles",
        json={
            "name": "冷潮自定义",
            "base_preset_key": "noir_cold",
            "narrative_voice": "有限第三人称",
            "pacing": "缓慢收紧",
            "optional_user_sample": "样文只用于抽取特征。",
            "derived_style_anchors": ["物件先于判断"],
        },
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()["style_profile"]
    assert len(created["prompt_hash"]) == 64
    assert created["derived_style_anchors"]
    assert "样文只用于抽取特征" not in json.dumps(
        created["derived_style_anchors"],
        ensure_ascii=False,
    )
    assert "样文只用于抽取特征" not in StyleProfile.model_validate(
        created
    ).prompt_text()

    copied_response = client.post(
        prefix + "/style-profiles",
        json={
            "name": "冷潮副本",
            "copy_from_profile_id": created["id"],
        },
    )
    assert copied_response.status_code == 201, copied_response.text
    copied = copied_response.json()["style_profile"]
    assert copied["id"] != created["id"]
    assert copied["prompt_hash"] == created["prompt_hash"]
    assert copied["read_only"] is False

    updated_response = client.put(
        prefix + f"/style-profiles/{copied['id']}",
        json={
            "expected_revision": copied["revision"],
            "pacing": "快速收紧",
            "optional_user_sample": "UPDATE_UNIQUE_SENTINEL。另一句用于统计！",
            "derived_style_anchors": [],
        },
    )
    assert updated_response.status_code == 200, updated_response.text
    updated = updated_response.json()["style_profile"]
    assert updated["revision"] == copied["revision"] + 1
    assert updated["prompt_hash"] != copied["prompt_hash"]
    assert updated["derived_style_anchors"]
    assert "UPDATE_UNIQUE_SENTINEL" not in json.dumps(
        updated["derived_style_anchors"],
        ensure_ascii=False,
    )
    assert "UPDATE_UNIQUE_SENTINEL" not in StyleProfile.model_validate(
        updated
    ).prompt_text()

    stale = client.put(
        prefix + f"/style-profiles/{copied['id']}",
        json={
            "expected_revision": copied["revision"],
            "pacing": "陈旧覆盖",
        },
    )
    assert stale.status_code == 409

    deleted = client.delete(
        prefix + f"/style-profiles/{copied['id']}",
        params={"expected_revision": updated["revision"]},
    )
    assert deleted.status_code == 200
    profiles = client.get(prefix + "/style-profiles").json()
    assert set(profiles) == {"profiles", "active_style"}
    assert copied["id"] not in {profile["id"] for profile in profiles["profiles"]}

    preset = next(
        profile for profile in profiles["profiles"] if profile["read_only"]
    )
    forbidden = client.put(
        prefix + f"/style-profiles/{preset['id']}",
        json={
            "expected_revision": preset["revision"],
            "pacing": "不得改写",
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "STYLE_PROFILE_READ_ONLY"


def test_style_activation_defaults_to_next_uncommitted_and_reconciles_spec(
    isolated_api,
    monkeypatch,
) -> None:
    novel, client, prefix = _create_novel()
    spec = _small_spec(client, prefix)

    async def fake_chat(**_kwargs):
        return _response(json.dumps(_valid_outline_payload(), ensure_ascii=False))

    monkeypatch.setattr("story.outline_generator.llm_client.chat", fake_chat)
    generated = client.post(
        prefix + "/outline/generate",
        json={"expected_spec_revision": spec["revision"]},
    ).json()["book_outline"]

    data_dir = novel_manager.get_novel_data_dir("alice", novel["id"])
    outline_store = BookOutlineStore(data_dir)
    outline = outline_store.load()
    committed_first = outline.chapters[0].model_copy(
        update={
            "status": "committed",
            "committed_section_ids": ["section_0001_01"],
        }
    )
    outline_store.save(
        outline.model_copy(
            update={
                "chapters": [committed_first, *outline.chapters[1:]],
                "progress_revision": outline.progress_revision + 1,
            }
        )
    )

    created = client.post(
        prefix + "/style-profiles",
        json={"name": "下一章风格", "pacing": "短促"},
    ).json()["style_profile"]
    styles = client.get(prefix + "/style-profiles").json()
    active = styles["active_style"]
    current_spec = client.get(prefix + "/production-spec").json()[
        "production_spec"
    ]
    switched = client.post(
        prefix + f"/style-profiles/{created['id']}/activate",
        json={
            "expected_revision": active["revision"],
            "expected_spec_revision": current_spec["revision"],
        },
    )
    assert switched.status_code == 200, switched.text
    body = switched.json()
    assert body["active_style"]["style_profile_id"] == created["id"]
    assert body["active_style"]["applies_from_chapter_ordinal"] == 2
    assert body["production_spec"]["active_style_profile_id"] == created["id"]
    assert body["production_spec"]["revision"] == current_spec["revision"] + 1

    stale = client.post(
        prefix + f"/style-profiles/{created['id']}/activate",
        json={
            "expected_revision": active["revision"],
            "expected_spec_revision": current_spec["revision"],
        },
    )
    assert stale.status_code == 409

    # Simulate a process exit after active_style.json committed but before its
    # derived production-spec field did.  The next API request heals it.
    spec_store = ProductionSpecStore(
        data_dir,
        lambda: (_ for _ in ()).throw(AssertionError("spec must exist")),
    )
    mismatched = spec_store.load()
    spec_store.update(
        NovelProductionSpecUpdate(
            expected_revision=mismatched.revision,
            active_style_profile_id="preset_literary",
        )
    )
    client.get(prefix + "/style-profiles")
    healed = spec_store.load()
    assert healed.active_style_profile_id == created["id"]
    assert healed.revision == mismatched.revision + 2
    assert generated["chapters"][0]["id"] == "chapter_0001"


def test_style_preview_uses_no_user_sample_and_commits_no_authority(
    isolated_api,
    monkeypatch,
) -> None:
    novel, client, prefix = _create_novel()
    created = client.post(
        prefix + "/style-profiles",
        json={
            "name": "预览风格",
            "narrative_voice": "近距离第三人称",
            "optional_user_sample": "NEVER_SEND_THIS_SAMPLE_SENTENCE",
        },
    ).json()["style_profile"]
    assert created["derived_style_anchors"]
    assert "NEVER_SEND_THIS_SAMPLE_SENTENCE" not in json.dumps(
        created["derived_style_anchors"],
        ensure_ascii=False,
    )
    assert "NEVER_SEND_THIS_SAMPLE_SENTENCE" not in StyleProfile.model_validate(
        created
    ).prompt_text()
    data_dir = Path(novel_manager.get_novel_data_dir("alice", novel["id"]))
    before = _json_bytes(data_dir)
    calls: list[dict] = []

    async def fake_chat(**kwargs):
        calls.append(kwargs)
        return _response("潮水退后，门环仍在微微发冷。", 7, 9)

    monkeypatch.setattr("api.production_routes.llm_client.chat", fake_chat)
    response = client.post(
        prefix + f"/style-profiles/{created['id']}/preview",
        json={
            "expected_revision": created["revision"],
            "sample_goal": "展示一个不进入 Canon 的短场景。",
        },
    )
    assert response.status_code == 200, response.text
    assert len(calls) == 1
    provider_context = calls[0]["system_prompt"] + calls[0]["user_prompt"]
    assert "NEVER_SEND_THIS_SAMPLE_SENTENCE" not in provider_context
    assert "optional_user_sample" not in provider_context
    assert calls[0]["agent_id"] == "style_preview"
    assert _json_bytes(data_dir) == before
    serialized = json.dumps(response.json(), ensure_ascii=False)
    assert "candidate" not in serialized.lower()
    assert "api_key" not in serialized.lower()
    assert "NEVER_SEND_THIS_SAMPLE_SENTENCE" not in serialized

    async def unsafe_chat(**_kwargs):
        return _response("api_key=TOPSECRET_SHOULD_NOT_LEAK")

    monkeypatch.setattr("api.production_routes.llm_client.chat", unsafe_chat)
    unsafe = client.post(
        prefix + f"/style-profiles/{created['id']}/preview",
        json={"expected_revision": created["revision"]},
    )
    assert unsafe.status_code == 502
    assert "TOPSECRET_SHOULD_NOT_LEAK" not in json.dumps(unsafe.json())

    calls_before_stale = len(calls)
    stale = client.post(
        prefix + f"/style-profiles/{created['id']}/preview",
        json={"expected_revision": created["revision"] + 1},
    )
    assert stale.status_code == 409
    assert len(calls) == calls_before_stale
