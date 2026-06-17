"""v2.25 — bootstrap_world 端点 + 链式首节触发 (v2.26 加 user 隔离)。

| Method | Path                                                | 用途                              |
|--------|-----------------------------------------------------|-----------------------------------|
| POST   | /api/novels/{novel_id}/bootstrap-world              | 冷启动世界 (4 阶段 LLM)            |
| POST   | /api/novels/{novel_id}/regenerate-style-anchors     | 单独重生成风格锚点 (复用 PROMPT_STYLE) |

novel_id 路径参数下, 强制校验当前用户拥有该 novel — 否则 404 (不泄露存在性)。
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import novel_manager
from auth import User, get_current_user
from bootstrap_prompts import bootstrap_world, generate_style_anchors
from memory.tick_state import TickState
from tasks.task_manager import (
    ProgressUpdater,
    TaskConflict,
    get_task_manager,
)

# Phase 5+: theme + style preset 注册表 — UI 用 GET /api/presets 拉取,
# bootstrap 端点用 theme key 自动 resolve seed.
try:
    from novel_presets import (
        STYLE_PRESETS,
        THEME_SEEDS,
        get_style_preset,
        get_theme_seed,
    )
    _PRESETS_AVAILABLE = True
except ImportError:
    _PRESETS_AVAILABLE = False
    STYLE_PRESETS = {}
    THEME_SEEDS = {}

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bootstrap"])

DEFAULT_POSITIONING = "古典含蓄、心理白描、节奏舒缓、避免华丽辞藻"
DEFAULT_REFERENCES = "Le Guin / 古龙"


# ---- Phase 5+ presets registry — UI 拉下拉列表 -----------------------------


@router.get("/api/presets")
async def get_presets(current_user: User = Depends(get_current_user)):
    """Phase 5+: 列出 theme + style preset 注册表, 前端动态构建下拉.

    Auth-gated — seed 字符串属 prompt engineering IP, 不公开. 登录用户可读
    (前端 authedFetch 自动带 token).
    """
    if not _PRESETS_AVAILABLE:
        return {"themes": [], "styles": [], "available": False}
    return {
        "themes": [
            {
                "key": t.key,
                "label": t.label,
                "category": t.category,
                "seed": t.seed,
            }
            for t in THEME_SEEDS.values()
        ],
        "styles": [
            {
                "key": s.key,
                "label": s.label,
                "description": s.description,
            }
            for s in STYLE_PRESETS.values()
        ],
        "available": True,
    }


class BootstrapWorldRequest(BaseModel):
    # Phase 5+: seed 现在可空, 若给 theme key 自动从 THEME_SEEDS 取
    seed: str = Field(
        default="",
        description="世界种子描述 (主题 / 设定). 空时必须给 theme.",
    )
    theme: str = Field(
        default="",
        description=(
            "Phase 5+ 主题 key (novel_presets.THEME_SEEDS). 设置时若 seed 空, "
            "用注册表里的 seed."
        ),
    )
    style: str = Field(
        default="",
        description=(
            "Phase 5+ 风格 preset key (novel_presets.STYLE_PRESETS). "
            "持久化进 TickState, narrator 每 tick 拼到 user_prompt 头."
        ),
    )
    positioning: str = Field(
        default=DEFAULT_POSITIONING,
        description="作品定位 (文风 / 节奏)",
    )
    references: str = Field(
        default=DEFAULT_REFERENCES,
        description="参考作家 / 作品",
    )
    also_generate_first_section: bool = Field(
        default=True,
        description="bootstrap 完成后是否立即入队首节生成任务",
    )


@router.post("/api/novels/{novel_id}/bootstrap-world")
async def bootstrap_world_endpoint(
    novel_id: str,
    req: BootstrapWorldRequest,
    current_user: User = Depends(get_current_user),
):
    """冷启动一个空小说 — 4 阶段种子化, 完成后可选链式触发首节。"""
    novel = novel_manager.get_novel(current_user.id, novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    novel_title = (novel.get("title") or "").strip()

    # Phase 5+: theme / style 校验 + seed 自动 resolve
    resolved_seed = (req.seed or "").strip()
    resolved_style = (req.style or "").strip()
    if req.theme:
        if not _PRESETS_AVAILABLE or req.theme not in THEME_SEEDS:
            raise HTTPException(
                status_code=400,
                detail=f"theme {req.theme!r} not in registry (valid: {sorted(THEME_SEEDS) if _PRESETS_AVAILABLE else 'none'})",
            )
        if not resolved_seed:
            resolved_seed = THEME_SEEDS[req.theme].seed
    if resolved_style:
        if not _PRESETS_AVAILABLE or resolved_style not in STYLE_PRESETS:
            raise HTTPException(
                status_code=400,
                detail=f"style {resolved_style!r} not in registry (valid: {sorted(STYLE_PRESETS) if _PRESETS_AVAILABLE else 'none'})",
            )
    if not resolved_seed:
        raise HTTPException(
            status_code=400,
            detail="必须提供 seed 或 theme (从注册表自动取 seed)",
        )

    executor = _make_bootstrap_world_executor(
        seed=resolved_seed,
        positioning=req.positioning,
        references=req.references,
        title=novel_title,
        also_generate_first_section=req.also_generate_first_section,
        style_preset_key=resolved_style,
    )

    mgr = get_task_manager()
    try:
        snap = await mgr.create_task(
            user_id=current_user.id,
            novel_id=novel_id,
            novel_title=novel_title,
            kind="bootstrap_world",
            executor=executor,
            target_words=0,
            min_words=0,
            max_ticks=4,
        )
    except TaskConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    novel_manager.touch_last_accessed(current_user.id, novel_id)
    return snap.model_dump(mode="json")


# ---- 内部 — executor 工厂 --------------------------------------------------


def _make_bootstrap_world_executor(
    *,
    seed: str,
    positioning: str,
    references: str,
    title: str,
    also_generate_first_section: bool,
    style_preset_key: str = "",
):
    async def _executor(
        updater: ProgressUpdater, user_id: str, novel_id: str
    ) -> dict:
        data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
        os.makedirs(data_dir, exist_ok=True)

        updater.set(tick_count=0, last_message="启动冷启动流程")
        updater.set(
            tick_count=1,
            last_message="生成世界状态 / 角色 / 伏笔 / 风格锚点 …",
        )
        try:
            ts = await bootstrap_world(
                novel_id=novel_id,
                data_dir=data_dir,
                seed=seed,
                positioning=positioning,
                references=references,
                title=title,
                style_preset_key=style_preset_key,
            )
        except Exception:
            logger.exception("bootstrap_world failed for novel '%s'", novel_id)
            raise

        # bootstrap 直写盘 — 让 runtime 重读 (close + 重建)
        _reload_runtime(user_id, novel_id)

        updater.set(
            tick_count=4,
            last_message=(
                f"种子化完成: {len(ts.list_character_profiles())} 角色 / "
                f"{ts.get_open_loop_count()} 伏笔 / "
                f"{len(ts.list_style_anchors())} 风格锚点"
            ),
        )

        result: dict = {
            "result_title": "世界种子已就位",
            "result_word_count": 0,
        }

        if also_generate_first_section:
            chained_id = await _spawn_chained_first_section(user_id, novel_id)
            result["chained_section_task_id"] = chained_id
            updater.set(
                last_message=f"已链式触发首节生成任务 {chained_id or '(skip)'}",
            )

        novel_manager.touch_last_accessed(user_id, novel_id)
        return result

    return _executor


def _reload_runtime(user_id: str, novel_id: str) -> None:
    """v2.36 — 用 reload_cache: drop 缓存 + 若 active 则重建, 强制重读 bootstrap
    刚写的盘。reload_cache 不会用 stale in-memory state 覆盖新盘 (历史教训:
    bootstrap → drop+save → 整个世界设定丢失)。"""
    from tick_runtime import reload_cache

    reload_cache(user_id, novel_id)


# ---- 重生成 style_anchors --------------------------------------------------


class RegenerateStyleAnchorsRequest(BaseModel):
    positioning: str = Field(
        default=DEFAULT_POSITIONING,
        description="作品定位 (语感: 句长 / 修辞密度 / 节奏)",
    )
    references: str = Field(
        default=DEFAULT_REFERENCES,
        description="参考作家 / 作品 (语感偏好)",
    )


@router.post("/api/novels/{novel_id}/regenerate-style-anchors")
async def regenerate_style_anchors_endpoint(
    novel_id: str,
    req: RegenerateStyleAnchorsRequest,
    current_user: User = Depends(get_current_user),
):
    """重新生成当前 novel 的 style_anchors —
    复用 bootstrap PROMPT_STYLE, 用 novel 的当前 title + 请求里的 positioning /
    references 重跑文风那一阶段, 替换 TickState 里旧的锚点。

    用于当前 novel 的 style_anchors 与标题语感脱节时 (例如标题是奇幻动作向,
    锚点却被默认的"古典含蓄"模板生成成了茶室静景), 用户在 UI 触发后端
    immediately 用新 prompt 重写锚点, 下一 tick narrator 即拿到新锚点。"""
    novel = novel_manager.get_novel(current_user.id, novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    novel_title = (novel.get("title") or "").strip()

    data_dir = novel_manager.get_novel_data_dir(current_user.id, novel_id)
    ts = TickState(data_dir=data_dir)
    # HIGH bug fix (code review 2026-06-17): __init__ 只初始化空字段, 必须先 load()
    # 把磁盘 tick_state.json 读回内存. 不 load 直接 save 会把 current_tick / open_loops
    # / character_profiles / style_preset_key 等所有字段重置成默认值, 造成已跑过 tick
    # 的小说在 UI 点 "重生成风格锚点" 后整个 TickState 被清空.
    ts.load()

    try:
        new_anchors = await generate_style_anchors(
            title=novel_title,
            positioning=req.positioning,
            references=req.references,
        )
    except Exception as e:
        logger.exception(
            "regenerate_style_anchors failed for novel '%s'", novel_id
        )
        raise HTTPException(
            status_code=502, detail=f"LLM 生成风格锚点失败: {e}"
        )

    if not new_anchors:
        raise HTTPException(
            status_code=502,
            detail="LLM 返回的 style_anchors 全部无效, 未替换原有锚点",
        )

    ts.replace_style_anchors(new_anchors)
    ts.save()

    # 让 runtime 立即重读 (若该 novel 当前在内存中)
    _reload_runtime(current_user.id, novel_id)
    novel_manager.touch_last_accessed(current_user.id, novel_id)

    return {
        "novel_id": novel_id,
        "style_anchors_count": len(new_anchors),
        "message": f"已重新生成 {len(new_anchors)} 段风格锚点",
        "scene_types": [a.scene_type for a in new_anchors],
    }


async def _spawn_chained_first_section(user_id: str, novel_id: str) -> str:
    from agents.section_closer import SectionCloser
    from api.section_routes import _make_section_executor
    from sections.section_store import get_section_store

    novel = novel_manager.get_novel(user_id, novel_id)
    novel_title = (novel.get("title") if novel else "") or ""
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
    store = get_section_store(novel_id, data_dir=data_dir)
    next_chapter, next_section = store.next_position()

    closer = SectionCloser()
    executor = _make_section_executor(
        closer=closer,
        store=store,
        novel_title=novel_title,
        chapter=next_chapter,
        section_no=next_section,
    )
    mgr = get_task_manager()
    try:
        snap = await mgr.create_task(
            user_id=user_id,
            novel_id=novel_id,
            novel_title=novel_title,
            kind="bootstrap_section",
            executor=executor,
            target_words=closer.target_words,
            min_words=closer.min_words,
            max_ticks=closer.max_ticks,
            chapter=next_chapter,
            section_no=next_section,
        )
        return snap.id
    except TaskConflict as e:
        logger.warning("chained section task conflict for '%s': %s", novel_id, e)
        return ""
