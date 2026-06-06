"""v2.25 — bootstrap_world 端点 + 链式首节触发。"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

import pytest


@pytest.fixture
def isolated_env(monkeypatch):
    """全局状态隔离: novels_dir / TaskManager / SectionStore / TickRuntime。"""
    tmp = tempfile.mkdtemp(prefix="v225_test_")

    import novel_manager
    monkeypatch.setattr(novel_manager, "_NOVELS_DIR", tmp)

    from tasks.task_manager import get_task_manager
    get_task_manager()._clear_for_tests()

    from sections import section_store as _ss
    _ss._stores.clear()

    # tick_runtime 注册表清空 — 让 _reload_runtime 在测试里也走 dict.pop 安全分支
    import tick_runtime
    tick_runtime._runtimes.clear()
    tick_runtime._active_novel_id = None

    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def patch_bootstrap_world(monkeypatch):
    """跳过真实 LLM 的 bootstrap_world — 直接构造一个有 1 角色 1 锚点的 TickState。"""

    async def _fake(*, novel_id, data_dir, seed, positioning, references):
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
        # 把 seed/positioning/references 偷渡到属性, 测试方便断言
        ts._test_seed = seed
        ts._test_positioning = positioning
        ts._test_references = references
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
        def __init__(self, novel_id):
            self.orchestrator = _FakeOrch()

    rt_cache = {}

    def _fake_get_runtime(novel_id=None):
        nid = novel_id or "default"
        if nid not in rt_cache:
            rt_cache[nid] = _FakeRuntime(nid)
        return rt_cache[nid]

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
            "ghost", BootstrapWorldRequest(seed="任意")
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

    novel = novel_manager.create_novel("测试")
    nid = novel["id"]

    snap = await bootstrap_world_endpoint(
        nid,
        BootstrapWorldRequest(
            seed="冰封大陆边境",
            positioning="冷冽克制",
            references="Le Guin",
            also_generate_first_section=False,
        ),
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
    assert len(mgr.list_for_novel(nid)) == 1


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

    # section executor 跑 max_ticks 兜底, 标题 LLM 一次
    mock_llm.set_responses(["首节"] * 5)

    novel = novel_manager.create_novel("测试链式")
    nid = novel["id"]

    snap = await bootstrap_world_endpoint(
        nid,
        BootstrapWorldRequest(
            seed="任意",
            also_generate_first_section=True,
        ),
    )
    await asyncio.sleep(0.3)

    mgr = get_task_manager()
    # 应当有 2 个任务: bootstrap_world + bootstrap_section
    tasks = mgr.list_for_novel(nid)
    kinds = sorted(t.kind for t in tasks)
    assert kinds == ["bootstrap_section", "bootstrap_world"], (
        f"应当链式触发 bootstrap_section, 实际 kinds={kinds}"
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
    from tasks.task_manager import get_task_manager

    novel = novel_manager.create_novel("透传测试")
    nid = novel["id"]

    snap = await bootstrap_world_endpoint(
        nid,
        BootstrapWorldRequest(
            seed="自定义种子文本",
            positioning="自定义文风",
            references="自定义参考",
            also_generate_first_section=False,
        ),
    )
    await asyncio.sleep(0.2)

    # 验证 bootstrap_world 内部确实拿到这些值 — 通过读 tick_state.json
    # (fake 把 seed 写到了 OpenLoop.description)
    from memory.tick_state import TickState
    data_dir = novel_manager.get_novel_data_dir(nid)
    ts2 = TickState(data_dir=data_dir)
    ts2.load()
    loops = ts2.get_open_loops()
    assert any("自定义种子文本" in l.description for l in loops)


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
    async def _slow(*, novel_id, data_dir, seed, positioning, references):
        os.makedirs(data_dir, exist_ok=True)
        from memory.tick_state import TickState
        from memory_system.models import WorldState
        await asyncio.sleep(0.5)
        ts = TickState(data_dir=data_dir)
        ts.set_world_state(WorldState(era="", current_season="", weather=""))
        ts.save()
        return ts

    monkeypatch.setattr("api.bootstrap_routes.bootstrap_world", _slow)

    novel = novel_manager.create_novel("冲突测试")
    nid = novel["id"]

    await bootstrap_world_endpoint(nid, BootstrapWorldRequest(seed="种子"))
    # 立即再发一次
    with pytest.raises(HTTPException) as exc:
        await bootstrap_world_endpoint(nid, BootstrapWorldRequest(seed="种子"))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_bootstrap_world_failure_marks_task_failed(
    isolated_env, patch_section_runtime, monkeypatch
):
    """bootstrap_world 抛异常时, task 状态应当 failed, 不应该链式触发首节。"""
    import novel_manager
    from api.bootstrap_routes import (
        BootstrapWorldRequest,
        bootstrap_world_endpoint,
    )
    from tasks.task_manager import get_task_manager

    async def _boom(*, novel_id, data_dir, seed, positioning, references):
        raise RuntimeError("LLM 配额耗尽")

    monkeypatch.setattr("api.bootstrap_routes.bootstrap_world", _boom)

    novel = novel_manager.create_novel("失败测试")
    nid = novel["id"]

    snap = await bootstrap_world_endpoint(
        nid,
        BootstrapWorldRequest(seed="种子", also_generate_first_section=True),
    )
    await asyncio.sleep(0.1)

    mgr = get_task_manager()
    final = mgr.get(snap["id"])
    assert final.status == "failed"
    assert "LLM 配额耗尽" in final.error
    # 只应当有这 1 个任务 — 失败不链式
    assert len(mgr.list_for_novel(nid)) == 1


@pytest.mark.asyncio
async def test_bootstrap_router_registered():
    """main.app 已挂载 /api/novels/{id}/bootstrap-world 路由。"""
    import main
    paths = {getattr(r, "path", "") for r in main.app.routes}
    assert any(
        p.endswith("/bootstrap-world") for p in paths
    ), f"bootstrap-world 端点未注册. paths={sorted(paths)[:30]}"
