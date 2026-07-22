"""v2.26 — bootstrap_world 端点 + 链式首节触发 (multi-tenant 重写).

旧测试用 ``_NOVELS_DIR`` / ``tick_runtime._active_novel_id`` / 单参 get_runtime
/ 不带 user_id 的 novel_manager API — 全部不再存在。本文件适配 v2.26
multi-tenant API: ``_DATA_ROOT`` + ``_USERS_ROOT``, 每个 endpoint 调用都需要传
current_user。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from datetime import datetime, timezone

import pytest

from auth.models import User


def _fake_user(user_id: str = "test_user") -> User:
    return User(
        id=user_id,
        email=f"{user_id}@local",
        has_password=False,
        save_my_works=True,
        created_at=datetime.fromtimestamp(0, tz=timezone.utc),
    )


@pytest.fixture
def isolated_env(monkeypatch):
    """v2.26 — 隔离数据根 + 清 TaskManager + 清 tick_runtime registry."""
    tmp = tempfile.mkdtemp(prefix="v226_test_")

    import novel_manager
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", tmp)
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", os.path.join(tmp, "users"))
    monkeypatch.setattr(
        novel_manager, "_LEGACY_NOVELS_DIR", os.path.join(tmp, "novels")
    )

    from tasks.task_manager import get_task_manager
    get_task_manager()._clear_for_tests()

    from sections import section_store as _ss
    _ss._stores.clear()

    import tick_runtime
    tick_runtime._clear_for_tests()

    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def patch_bootstrap_world(monkeypatch):
    """跳过真实 LLM 的 bootstrap_world — 直接构造一个有 1 角色 1 锚点的 TickState。"""

    async def _fake(
        *,
        novel_id,
        data_dir,
        seed,
        positioning,
        references,
        title="",
        style_preset_key="",
    ):
        os.makedirs(data_dir, exist_ok=True)
        from memory.tick_state import TickState
        from memory_system.models import (
            CharacterProfile,
            CharacterState,
            OpenLoop,
            StyleAnchor,
            WorldState,
        )
        ts = TickState(data_dir=data_dir)
        ts.set_world_state(
            WorldState(
                era="测试纪元", current_season="春", weather="晴",
                locations=[], factions=[], active_global_events=[], world_rules=[],
            )
        )
        ts.upsert_character_profile(
            CharacterProfile(id="c1", name="主角", importance_tier="A")
        )
        ts.upsert_character_state(
            CharacterState(character_id="c1", current_location="loc_1")
        )
        ts.add_open_loop(
            OpenLoop(
                id="l1",
                description=seed,
                urgency=8,
                type="mystery",
                opened_tick=0,
            )
        )
        ts.add_style_anchor(
            StyleAnchor(excerpt="风格示例 " * 5, scene_type="general", weight=1.0)
        )
        ts.save()
        return ts

    monkeypatch.setattr("api.bootstrap_routes.bootstrap_world", _fake)
    return _fake


@pytest.fixture
def patch_section_runtime(monkeypatch):
    """链式 first section 任务用到 section executor / orchestrator — stub 之。"""
    class _FakeOrch:
        current_tick = 0
        last_narrator_output = None

        async def run_tick(self):
            class _S:
                tick = 0
            return _S()

    class _FakeRuntime:
        def __init__(self, user_id, novel_id):
            self.user_id = user_id
            self.novel_id = novel_id
            self.orchestrator = _FakeOrch()

    rt_cache = {}

    def _fake_get_runtime(user_id, novel_id=None):
        nid = novel_id or "default"
        key = (user_id, nid)
        if key not in rt_cache:
            rt_cache[key] = _FakeRuntime(user_id, nid)
        return rt_cache[key]

    monkeypatch.setattr("tick_runtime.get_runtime", _fake_get_runtime)
    monkeypatch.setattr("api.section_routes.get_runtime", _fake_get_runtime)
    return rt_cache


# ---- 端点 -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_world_endpoint_404_when_novel_missing(isolated_env):
    from api.bootstrap_routes import (
        BootstrapWorldRequest,
        bootstrap_world_endpoint,
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await bootstrap_world_endpoint(
            "ghost",
            BootstrapWorldRequest(seed="任意"),
            current_user=_fake_user(),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_bootstrap_world_creates_task_and_completes(
    isolated_env, patch_bootstrap_world, patch_section_runtime, mock_llm
):
    """端到端: POST → task 入队 → executor 跑 → completed; chained section 不触发时仅 1 个任务。"""
    import novel_manager
    from api.bootstrap_routes import (
        BootstrapWorldRequest,
        bootstrap_world_endpoint,
    )
    from tasks.task_manager import get_task_manager

    user = _fake_user("u_complete")
    novel = novel_manager.create_novel(user.id, "测试")
    nid = novel["id"]

    snap = await bootstrap_world_endpoint(
        nid,
        BootstrapWorldRequest(
            seed="冰封大陆边境",
            positioning="冷冽克制",
            references="Le Guin",
            also_generate_first_section=False,
        ),
        current_user=user,
    )
    assert snap["kind"] == "bootstrap_world"
    assert snap["novel_id"] == nid

    # 等 executor 跑完
    await asyncio.sleep(0.2)
    mgr = get_task_manager()
    final = mgr.get(snap["id"])
    assert final.status == "completed", f"err={final.error}"
    assert final.result_title == "世界种子已就位"
    # 仅 1 个任务 — also_generate_first_section=False
    assert len(mgr.list_for_user_and_novel(user.id, nid)) == 1


@pytest.mark.asyncio
async def test_bootstrap_world_chains_first_section_task(
    isolated_env, patch_bootstrap_world, patch_section_runtime, mock_llm
):
    """also_generate_first_section=True 时, bootstrap 完成应当链式入队一个 bootstrap_section。"""
    import novel_manager
    from api.bootstrap_routes import (
        BootstrapWorldRequest,
        bootstrap_world_endpoint,
    )
    from tasks.task_manager import get_task_manager

    mock_llm.set_responses(
        [
            {
                "narrative_text": "主角确认身份，并为同伴承担牺牲。" * 20,
                "section_summary": "主角以牺牲回应身份冲突。",
                "title": "选择",
            }
        ]
    )

    user = _fake_user("u_chain")
    novel = novel_manager.create_novel(user.id, "测试链式")
    nid = novel["id"]

    await bootstrap_world_endpoint(
        nid,
        BootstrapWorldRequest(
            seed="任意",
            also_generate_first_section=True,
        ),
        current_user=user,
    )
    await asyncio.sleep(0.3)

    mgr = get_task_manager()
    tasks = mgr.list_for_user_and_novel(user.id, nid)
    kinds = sorted(t.kind for t in tasks)
    assert kinds == ["author_section_generation", "bootstrap_world"], (
        f"应当链式触发默认 author section, 实际 kinds={kinds}"
    )

    bw = next(t for t in tasks if t.kind == "bootstrap_world")
    assert bw.status == "completed"


@pytest.mark.asyncio
async def test_bootstrap_world_passes_user_inputs_to_seed_function(
    isolated_env, patch_bootstrap_world, patch_section_runtime, mock_llm
):
    """seed / positioning / references 必须按用户输入透传到 bootstrap_world。"""
    import novel_manager
    from api.bootstrap_routes import (
        BootstrapWorldRequest,
        bootstrap_world_endpoint,
    )

    user = _fake_user("u_pass")
    novel = novel_manager.create_novel(user.id, "透传测试")
    nid = novel["id"]

    await bootstrap_world_endpoint(
        nid,
        BootstrapWorldRequest(
            seed="自定义种子文本",
            positioning="自定义文风",
            references="自定义参考",
            also_generate_first_section=False,
        ),
        current_user=user,
    )
    await asyncio.sleep(0.2)

    # 验证 bootstrap_world 内部确实拿到这些值 — 通过读 tick_state.json
    # (fake 把 seed 写到了 OpenLoop.description)
    from memory.tick_state import TickState
    data_dir = novel_manager.get_novel_data_dir(user.id, nid)
    ts2 = TickState(data_dir=data_dir)
    ts2.load()
    loops = ts2.get_open_loops()
    assert any("自定义种子文本" in loop.description for loop in loops)


@pytest.mark.asyncio
async def test_author_bootstrap_preserves_exact_source_seed(
    isolated_env, patch_bootstrap_world, patch_section_runtime
):
    import novel_manager
    from api.bootstrap_routes import (
        BootstrapWorldRequest,
        STYLE_PRESETS,
        THEME_SEEDS,
        bootstrap_world_endpoint,
    )
    from story.persistence import StoryBibleStore

    user = _fake_user("u_exact_seed")
    novel = novel_manager.create_novel(user.id, "逐字种子")
    seed = "潮声：‘别回头’——第一行。\n第二行（保留！）"
    theme_key = next(iter(THEME_SEEDS))
    style_key = next(iter(STYLE_PRESETS))
    await bootstrap_world_endpoint(
        novel["id"],
        BootstrapWorldRequest(
            seed=seed,
            theme=theme_key,
            style=style_key,
            positioning="冷峻；短句",
            references="作者甲 / 作品乙",
            also_generate_first_section=False,
        ),
        current_user=user,
    )
    bible = StoryBibleStore(
        novel_manager.get_novel_data_dir(user.id, novel["id"])
    ).load()
    assert bible.source_seed == seed
    assert bible.theme_key == theme_key
    assert bible.style_contract["key"] == style_key
    assert bible.positioning == "冷峻；短句"
    assert bible.reference_preferences == ["作者甲 / 作品乙"]
    assert bible.migration.source == "user_confirmed"
    assert bible.field_provenance["source_seed"] == "user_input"


@pytest.mark.asyncio
async def test_bootstrap_world_uses_defaults_when_optional_fields_omitted(
    isolated_env, patch_bootstrap_world, patch_section_runtime
):
    """positioning / references 可省 — 走 bootstrap_routes 模块级默认。"""
    from api.bootstrap_routes import (
        DEFAULT_POSITIONING,
        DEFAULT_REFERENCES,
        BootstrapWorldRequest,
    )
    req = BootstrapWorldRequest(seed="只有种子")
    assert req.positioning == DEFAULT_POSITIONING
    assert req.references == DEFAULT_REFERENCES


@pytest.mark.asyncio
async def test_bootstrap_world_conflict_409_for_same_novel(
    isolated_env, patch_bootstrap_world, patch_section_runtime, monkeypatch
):
    """同 novel 已有 bootstrap_world 在跑时, 二次请求应当 409。"""
    import novel_manager
    from api.bootstrap_routes import (
        BootstrapWorldRequest,
        bootstrap_world_endpoint,
    )
    from fastapi import HTTPException

    # 让 fake bootstrap_world 不要立即完成 — sleep 一会儿模拟真实 LLM
    async def _slow(
        *,
        novel_id,
        data_dir,
        seed,
        positioning,
        references,
        title="",
        style_preset_key="",
    ):
        os.makedirs(data_dir, exist_ok=True)
        from memory.tick_state import TickState
        from memory_system.models import WorldState
        await asyncio.sleep(0.5)
        ts = TickState(data_dir=data_dir)
        ts.set_world_state(WorldState(era="", current_season="", weather=""))
        ts.save()
        return ts

    monkeypatch.setattr("api.bootstrap_routes.bootstrap_world", _slow)

    user = _fake_user("u_conf")
    novel = novel_manager.create_novel(user.id, "冲突测试")
    nid = novel["id"]

    await bootstrap_world_endpoint(
        nid, BootstrapWorldRequest(seed="种子"), current_user=user
    )
    # 立即再发一次
    with pytest.raises(HTTPException) as exc:
        await bootstrap_world_endpoint(
            nid, BootstrapWorldRequest(seed="种子"), current_user=user
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_bootstrap_failure_does_not_lose_story_bible(
    isolated_env, patch_section_runtime, monkeypatch
):
    """bootstrap_world 抛异常时, task 状态应当 failed, 不应该链式触发首节。"""
    import novel_manager
    from api.bootstrap_routes import (
        BootstrapWorldRequest,
        bootstrap_world_endpoint,
    )
    from tasks.task_manager import get_task_manager

    async def _boom(
        *,
        novel_id,
        data_dir,
        seed,
        positioning,
        references,
        title="",
        style_preset_key="",
    ):
        raise RuntimeError("LLM 配额耗尽")

    monkeypatch.setattr("api.bootstrap_routes.bootstrap_world", _boom)

    user = _fake_user("u_fail")
    novel = novel_manager.create_novel(user.id, "失败测试")
    nid = novel["id"]

    snap = await bootstrap_world_endpoint(
        nid,
        BootstrapWorldRequest(seed="种子", also_generate_first_section=True),
        current_user=user,
    )
    await asyncio.sleep(0.1)

    mgr = get_task_manager()
    final = mgr.get(snap["id"])
    assert final.status == "failed"
    assert "LLM 配额耗尽" in final.error
    # 只应当有这 1 个任务 — 失败不链式
    assert len(mgr.list_for_user_and_novel(user.id, nid)) == 1
    from story.persistence import StoryBibleStore

    bible = StoryBibleStore(novel_manager.get_novel_data_dir(user.id, nid)).load()
    assert bible.source_seed == "种子"
    assert bible.migration.source == "user_confirmed"


@pytest.mark.asyncio
async def test_bootstrap_retry_does_not_overwrite_user_confirmed_bible(
    isolated_env, patch_bootstrap_world, patch_section_runtime
):
    import novel_manager
    from api.bootstrap_routes import BootstrapWorldRequest, bootstrap_world_endpoint
    from story.models import StoryBibleUpdate
    from story.persistence import StoryBibleStore

    user = _fake_user("u_retry_bible")
    novel = novel_manager.create_novel(user.id, "重试保护")
    request = BootstrapWorldRequest(
        seed="原始种子",
        positioning="原定位",
        references="原参考",
        also_generate_first_section=False,
    )
    await bootstrap_world_endpoint(novel["id"], request, current_user=user)
    await asyncio.sleep(0.2)
    store = StoryBibleStore(novel_manager.get_novel_data_dir(user.id, novel["id"]))
    bible = store.load()
    confirmed = store.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            title=bible.title,
            source_seed=bible.source_seed,
            theme_key=bible.theme_key,
            positioning=bible.positioning,
            reference_preferences=bible.reference_preferences,
            premise="用户确认的前提",
            theme="用户确认的主题",
            setting_summary="用户确认的背景",
            style_contract=bible.style_contract,
        )
    )
    await bootstrap_world_endpoint(novel["id"], request, current_user=user)
    await asyncio.sleep(0.2)
    restored = store.load()
    assert restored.revision == confirmed.revision
    assert restored.theme == "用户确认的主题"
    assert restored.source_seed == "原始种子"


@pytest.mark.asyncio
async def test_switch_style_preset_is_atomic_and_preserves_tick_state(
    isolated_env, monkeypatch
):
    import novel_manager
    from api.bootstrap_routes import (
        SwitchStylePresetRequest,
        switch_style_preset_endpoint,
    )
    from memory.tick_state import TickState
    from memory_system.models import StyleAnchor
    from novel_presets import get_style_preset
    from story.models import GenerationModeConfig
    from story.persistence import GenerationModeStore

    user = _fake_user("u_style_switch")
    novel = novel_manager.create_novel(user.id, "风格切换测试")
    data_dir = novel_manager.get_novel_data_dir(user.id, novel["id"])
    GenerationModeStore(data_dir).save(GenerationModeConfig(mode="simulation"))
    ts = TickState(data_dir=data_dir)
    ts.advance_tick()
    old = get_style_preset("literary")
    ts.set_style_preset_contract(old.key, old.to_snapshot())
    ts.add_style_anchor(
        StyleAnchor(excerpt="旧锚点", scene_type="general", weight=1.0)
    )
    ts.save()

    async def _fake_anchors(**kwargs):
        assert kwargs["style_preset_key"] == "hot_blooded"
        assert kwargs["style_preset_snapshot"]["key"] == "hot_blooded"
        return [StyleAnchor(excerpt="新热血锚点", scene_type="action", weight=2.0)]

    monkeypatch.setattr(
        "api.bootstrap_routes.generate_style_anchors", _fake_anchors
    )
    monkeypatch.setattr("api.bootstrap_routes._reload_runtime", lambda *_: None)

    result = await switch_style_preset_endpoint(
        novel["id"],
        SwitchStylePresetRequest(style="hot_blooded"),
        current_user=user,
    )
    assert result["style_preset_key"] == "hot_blooded"

    restored = TickState(data_dir=data_dir)
    assert restored.load() is True
    selected = get_style_preset("hot_blooded")
    assert restored.current_tick == 1
    assert restored.style_preset_prompt_hash == selected.prompt_hash
    assert [a.excerpt for a in restored.list_style_anchors()] == ["新热血锚点"]


@pytest.mark.asyncio
async def test_author_style_switch_updates_story_bible(
    isolated_env, monkeypatch
):
    import novel_manager
    from api.bootstrap_routes import SwitchStylePresetRequest, switch_style_preset_endpoint
    from story.migrations import ensure_story_domain
    from story.persistence import StoryBibleStore

    user = _fake_user("u_author_style")
    novel = novel_manager.create_novel(user.id, "作者风格")
    data_dir = novel_manager.get_novel_data_dir(user.id, novel["id"])
    ensure_story_domain(data_dir, title=novel["title"])
    before = StoryBibleStore(data_dir).load()
    called = {"anchors": 0}

    async def _must_not_generate(**kwargs):
        called["anchors"] += 1
        raise AssertionError("author style switch must not generate TickState anchors")

    monkeypatch.setattr("api.bootstrap_routes.generate_style_anchors", _must_not_generate)
    result = await switch_style_preset_endpoint(
        novel["id"],
        SwitchStylePresetRequest(
            style="hot_blooded",
            expected_revision=before.revision,
            positioning="短促有力",
            references="不模仿具体作者",
        ),
        current_user=user,
    )
    after = StoryBibleStore(data_dir).load()
    assert result["authority"] == "story_bible"
    assert after.revision == before.revision + 1
    assert after.style_contract["key"] == "hot_blooded"
    assert after.positioning == "短促有力"
    assert called["anchors"] == 0
    assert not os.path.exists(os.path.join(data_dir, "tick_state.json"))


@pytest.mark.asyncio
async def test_author_style_switch_does_not_depend_on_tick_state(
    isolated_env, monkeypatch
):
    import novel_manager
    from api.bootstrap_routes import SwitchStylePresetRequest, switch_style_preset_endpoint
    from story.migrations import ensure_story_domain

    user = _fake_user("u_author_style_no_tick")
    novel = novel_manager.create_novel(user.id, "无 Tick 风格")
    data_dir = novel_manager.get_novel_data_dir(user.id, novel["id"])
    ensure_story_domain(data_dir, title=novel["title"])
    monkeypatch.setattr(
        "api.bootstrap_routes.generate_style_anchors",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    result = await switch_style_preset_endpoint(
        novel["id"],
        SwitchStylePresetRequest(style="literary", regenerate_anchors=True),
        current_user=user,
    )
    assert result["authority"] == "story_bible"
    assert not os.path.exists(os.path.join(data_dir, "tick_state.json"))


def test_author_seed_api_roundtrip_survives_runtime_rebuild(
    isolated_env, patch_bootstrap_world, patch_section_runtime
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api import bootstrap_routes, routes, story_routes
    from auth import get_current_user
    from story.runtime import clear_author_runtimes

    user = _fake_user("u_seed_e2e")
    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(bootstrap_routes.router)
    app.include_router(story_routes.router)
    app.dependency_overrides[get_current_user] = lambda: user
    seed = "钟摆停在 00:00——‘谁在撒谎？’\n第二行：保留【括号】与；分号。"
    with TestClient(app) as client:
        created = client.post(
            "/api/novels?auto_bootstrap=false",
            json={"title": "精确种子 API", "generation_mode": "author"},
        )
        assert created.status_code == 200, created.text
        novel_id = created.json()["id"]
        boot = client.post(
            f"/api/novels/{novel_id}/bootstrap-world",
            json={
                "seed": seed,
                "positioning": "逐句克制",
                "references": "仅作语感参考",
                "also_generate_first_section": False,
            },
        )
        assert boot.status_code == 200, boot.text
        first = client.get(f"/api/novels/{novel_id}/story-bible")
        assert first.status_code == 200
        assert first.json()["story_bible"]["source_seed"] == seed
        clear_author_runtimes()
        second = client.get(f"/api/novels/{novel_id}/story-bible")
        assert second.json()["story_bible"]["source_seed"] == seed


@pytest.mark.asyncio
async def test_simulation_style_switch_remains_isolated(
    isolated_env, monkeypatch
):
    import novel_manager
    from api.bootstrap_routes import SwitchStylePresetRequest, switch_style_preset_endpoint
    from memory.tick_state import TickState
    from memory_system.models import StyleAnchor
    from story.migrations import ensure_story_domain
    from story.models import GenerationModeConfig
    from story.persistence import GenerationModeStore, StoryBibleStore

    user = _fake_user("u_sim_style")
    novel = novel_manager.create_novel(user.id, "模拟风格")
    data_dir = novel_manager.get_novel_data_dir(user.id, novel["id"])
    ensure_story_domain(data_dir, title=novel["title"])
    GenerationModeStore(data_dir).save(GenerationModeConfig(mode="simulation"))
    bible_before = StoryBibleStore(data_dir).load()
    ts = TickState(data_dir=data_dir)
    ts.save()

    async def _anchors(**kwargs):
        return [StyleAnchor(excerpt="模拟锚点", scene_type="action", weight=1.0)]

    monkeypatch.setattr("api.bootstrap_routes.generate_style_anchors", _anchors)
    monkeypatch.setattr("api.bootstrap_routes._reload_runtime", lambda *_: None)
    await switch_style_preset_endpoint(
        novel["id"],
        SwitchStylePresetRequest(style="hot_blooded"),
        current_user=user,
    )
    assert StoryBibleStore(data_dir).load() == bible_before
    restored = TickState(data_dir=data_dir)
    assert restored.load() is True
    assert restored.style_preset_key == "hot_blooded"


@pytest.mark.asyncio
async def test_bootstrap_router_registered():
    """main.app 已挂载 /api/novels/{id}/bootstrap-world 路由。"""
    import main
    paths = {getattr(r, "path", "") for r in main.app.routes}
    assert any(
        p.endswith("/bootstrap-world") for p in paths
    ), f"bootstrap-world 端点未注册. paths={sorted(paths)[:30]}"
