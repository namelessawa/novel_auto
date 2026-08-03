"""FastAPI routes for the novel generation system (v2.26 — user-scoped)。

所有触及 novel 数据的端点都经 ``Depends(get_current_user)`` 拿到 user_id,
所有 novel_manager 调用都按 user_id 命名空间。

legacy GenerationPipeline 也按 (user_id, novel_id) 缓存。
LLM 配置 (/api/config/llm) 保持全局 — 系统级 fallback 配置, 与用户 API key
(浏览器 localStorage) 不冲突。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

import novel_manager
from auth import User, get_current_user
from config.settings import get_llm_config, update_llm_config
from memory_system.models import Entity, EntityType, Relation, RelationType
from nf_core.provider_runtime import (
    ProviderConfigurationError,
    ProviderError,
    ephemeral_provider_client,
    provider_output_invalid,
    resolve_provider_runtime,
)
from pipeline.engine import GenerationPipeline, PipelineEvent, PipelineStage

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-user legacy pipeline + active novel state
_pipelines: dict[tuple[str, str], GenerationPipeline] = {}
_active_by_user: dict[str, str] = {}

# v2.37 — 后台标题生成任务的强引用集合: event loop 只持任务的弱引用,
# ensure_future 后无人持有的 task 可能被 GC 中途回收, 异常也无人消费。
# done_callback 里 discard + 记录异常。
_title_tasks: set[asyncio.Task] = set()


def _get_active_novel_id(user_id: str) -> str | None:
    return _active_by_user.get(user_id)


def _init_default_novel(user_id: str) -> str:
    return novel_manager.resolve_default_novel_id(user_id)


def _get_pipeline(user_id: str) -> GenerationPipeline:
    """惰性构造该用户当前 active novel 的 GenerationPipeline。"""
    nid = _active_by_user.get(user_id)
    if nid is None:
        nid = _init_default_novel(user_id)
        _active_by_user[user_id] = nid
    key = (user_id, nid)
    if key not in _pipelines:
        data_dir = novel_manager.get_novel_data_dir(user_id, nid)
        pipeline = GenerationPipeline(data_dir=data_dir)
        pipeline.load_state()
        _pipelines[key] = pipeline
    return _pipelines[key]


# -- Request / Response Models -----------------------------------------------


class GenerateRequest(BaseModel):
    outline: str = Field(default="", description="全局大纲（可选）")


class EntityCreateRequest(BaseModel):
    id: str
    name: str
    entity_type: str = "character"
    attributes: dict = Field(default_factory=dict)


class RelationCreateRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str = "custom"
    label: str = ""


class RollbackRequest(BaseModel):
    chapter: int


class LLMConfigUpdateRequest(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    provider: str | None = None


class LLMProbeRequest(BaseModel):
    max_tokens: int = Field(default=16, ge=1, le=64)


class NovelCreateRequest(BaseModel):
    title: str = "未命名小说"
    generation_mode: Literal["author", "simulation"] = "author"


class NovelUpdateRequest(BaseModel):
    title: str


# -- Novel Management Routes -------------------------------------------------


@router.get("/api/novels")
async def list_novels(current_user: User = Depends(get_current_user)):
    novels = novel_manager.list_novels(current_user.id)
    return {"novels": novels, "active_id": _active_by_user.get(current_user.id)}


@router.post("/api/novels")
async def create_novel(
    req: NovelCreateRequest,
    auto_bootstrap: bool = False,
    current_user: User = Depends(get_current_user),
):
    entry = novel_manager.create_novel(current_user.id, req.title)
    # Establish the author-domain authorities immediately.  A later bootstrap
    # may enrich only these untouched placeholders from its TickState output.
    from story.migrations import ensure_story_domain
    from story.models import GenerationModeConfig
    from story.persistence import GenerationModeStore

    data_dir = novel_manager.get_novel_data_dir(current_user.id, entry["id"])
    ensure_story_domain(data_dir, title=req.title)
    mode_store = GenerationModeStore(data_dir)
    if req.generation_mode != mode_store.load().mode:
        mode_store.save(GenerationModeConfig(mode=req.generation_mode))
    bootstrap_task_id = ""
    if auto_bootstrap:
        try:
            bootstrap_task_id = await _spawn_bootstrap_section_task(
                user_id=current_user.id,
                novel_id=entry["id"],
                novel_title=entry.get("title", ""),
            )
        except Exception as e:
            logger.warning(
                "auto bootstrap section task for novel '%s' failed: %s",
                entry["id"],
                e,
            )
    return {
        **entry,
        "bootstrap_task_id": bootstrap_task_id,
        "generation_mode": req.generation_mode,
    }


async def _spawn_bootstrap_section_task(
    *, user_id: str, novel_id: str, novel_title: str
) -> str:
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
    from story.persistence import GenerationModeStore

    if GenerationModeStore(data_dir).load().mode == "author":
        from api.story_routes import _make_author_executor
        from sections.section_store import get_section_store
        from story.models import SectionGoal
        from tasks.task_manager import TaskConflict, get_task_manager

        goal = SectionGoal(
            objective="建立主角、核心冲突与世界规则，并以一个可追踪的选择结束本节。"
        )
        store = get_section_store(novel_id, data_dir=data_dir)
        chapter, section = store.next_position()
        try:
            task = await get_task_manager().create_task(
                user_id=user_id,
                novel_id=novel_id,
                novel_title=novel_title,
                kind="author_section_generation",
                executor=_make_author_executor(goal),
                target_words=goal.desired_length,
                min_words=200,
                max_ticks=2,
                chapter=chapter,
                section_no=section,
            )
        except TaskConflict:
            return ""
        return task.id

    from agents.section_closer import SectionCloser
    from api.section_routes import _make_section_executor
    from sections.section_store import get_section_store
    from tasks.task_manager import TaskConflict, get_task_manager
    from tick_runtime import get_runtime

    get_runtime(user_id, novel_id)
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
    except TaskConflict:
        return ""
    return snap.id


@router.put("/api/novels/{novel_id}")
async def update_novel(
    novel_id: str,
    req: NovelUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        entry = novel_manager.update_title(current_user.id, novel_id, req.title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if entry is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    # v2.34 — 同步活跃 runtime 的 TickState.novel_title, 让 Narrator 立刻看到新标题.
    # runtime 不存在时 (从未启动过) 静默跳过, 下次 get_runtime 会从 novel_manager
    # 元数据初始化时把标题写入。
    try:
        from tick_runtime import _runtimes  # noqa: WPS437 — 跨模块协作
        rt = _runtimes.get((current_user.id, novel_id))
        if rt is not None:
            rt.tick_state.set_novel_title(req.title)
            # save() 是同步 JSON + os.replace, 放线程池避免阻塞 event loop
            await run_in_threadpool(rt.tick_state.save)
    except Exception as e:
        logger.warning(
            "sync novel_title to active runtime failed (non-fatal): %s", e
        )
    return entry


@router.delete("/api/novels/{novel_id}")
async def delete_novel(
    novel_id: str, current_user: User = Depends(get_current_user)
):
    from tick_runtime import drop_cache, get_active_novel_id

    if novel_id in {
        _active_by_user.get(current_user.id),
        get_active_novel_id(current_user.id),
    }:
        raise HTTPException(status_code=400, detail="不能删除当前活跃的小说")
    try:
        existing = novel_manager.get_novel(current_user.id, novel_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if existing is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    # Release runtime/SQLite handles before removing the directory (Windows).
    from story.runtime import drop_author_runtime

    drop_author_runtime(current_user.id, novel_id)
    await run_in_threadpool(drop_cache, current_user.id, novel_id)
    try:
        ok = novel_manager.delete_novel(current_user.id, novel_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Novel not found")
    # 顺便清掉该用户该 novel 的 pipeline 缓存
    _pipelines.pop((current_user.id, novel_id), None)
    return {"status": "ok"}


@router.post("/api/novels/{novel_id}/switch")
async def switch_novel(
    novel_id: str, current_user: User = Depends(get_current_user)
):
    try:
        target = novel_manager.get_novel(current_user.id, novel_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if target is None:
        raise HTTPException(status_code=404, detail="Novel not found")

    # 旧 active 落盘
    old_id = _active_by_user.get(current_user.id)
    if old_id and old_id != novel_id:
        old_key = (current_user.id, old_id)
        old_pipe = _pipelines.get(old_key)
        if old_pipe is not None:
            try:
                await run_in_threadpool(old_pipe.save_state)
            except Exception:
                logger.exception("save_state before active novel realign failed")
            _pipelines.pop(old_key, None)

    data_dir = novel_manager.get_novel_data_dir(current_user.id, novel_id)
    from story.migrations import ensure_story_domain
    from story.persistence import GenerationModeStore

    ensure_story_domain(data_dir, title=str(target.get("title") or ""))
    mode = GenerationModeStore(data_dir).load().mode
    if mode == "simulation":
        # Only an explicitly selected experimental novel constructs TickRuntime.
        try:
            from tick_runtime import switch_active_novel

            def _sync_legacy_active() -> None:
                _active_by_user[current_user.id] = novel_id

            switch_active_novel(current_user.id, novel_id, _sync_legacy_active)
        except Exception as e:
            logger.error(
                "switch_active_novel(%s, %s) failed: %s",
                current_user.id,
                novel_id,
                e,
            )
            raise HTTPException(
                status_code=503,
                detail=f"tick runtime 切换失败: {e}; active novel 未切换",
            )
        pipeline = GenerationPipeline(data_dir=data_dir)
        await run_in_threadpool(pipeline.load_state)
        _pipelines[(current_user.id, novel_id)] = pipeline
    else:
        # Author mode updates only the lightweight active pointer and explicitly
        # deactivates any prior simulation runtime without constructing a new one.
        from tick_runtime import drop_cache, get_active_novel_id as get_tick_active

        tick_active = get_tick_active(current_user.id)
        if tick_active:
            await run_in_threadpool(drop_cache, current_user.id, tick_active)
        _active_by_user[current_user.id] = novel_id
        _pipelines.pop((current_user.id, novel_id), None)

    novel_manager.touch_last_accessed(current_user.id, novel_id)
    return {
        "status": "ok",
        "active_id": novel_id,
        "title": target["title"],
        "generation_mode": mode,
    }


# -- LLM Config Routes ------------------------------------------------------


@router.get("/api/config/llm")
async def get_llm_config_route(current_user: User = Depends(get_current_user)):
    return get_llm_config()


@router.get("/api/config/llm/providers")
async def get_llm_providers_route(
    current_user: User = Depends(get_current_user),
):
    from core.config import get_provider_catalog

    return {"providers": get_provider_catalog()}


@router.get("/api/config/llm/runtime")
async def get_llm_runtime_route(
    current_user: User = Depends(get_current_user),
):
    try:
        return resolve_provider_runtime().diagnostics()
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PROVIDER_CONFIG_INVALID",
                "message": str(exc),
                "details": {},
            },
        ) from exc


@router.post("/api/config/llm/probe")
async def probe_llm_runtime_route(
    req: LLMProbeRequest | None = None,
    current_user: User = Depends(get_current_user),
):
    del current_user
    try:
        config = resolve_provider_runtime()
    except ProviderConfigurationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PROVIDER_CONFIG_INVALID",
                "message": str(exc),
                "details": {},
            },
        ) from exc
    from nf_core.llm_client import llm_client

    started = time.perf_counter()
    try:
        async with ephemeral_provider_client(config) as client:
            response = await llm_client.chat(
                system_prompt="Return exactly: OK",
                user_prompt="OK",
                temperature=0.0,
                max_tokens=(req.max_tokens if req is not None else 16),
                agent_id="provider_probe",
                priority="critical",
                provider_config=config,
                client_override=client,
            )
        if not response.content.strip():
            raise provider_output_invalid(config)
    except ProviderError as exc:
        detail = exc.to_probe_detail(
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        raise HTTPException(
            status_code=exc.http_status,
            detail=detail,
        ) from exc
    return {
        "success": True,
        "http_category": "ok",
        "code": "OK",
        "provider": config.provider,
        "model": config.model,
        "thinking_mode": config.thinking_mode,
        "sdk_retries": config.max_retries,
        "prompt_tokens": response.usage_prompt_tokens,
        "completion_tokens": response.usage_completion_tokens,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "source": config.source,
        "config_fingerprint": config.config_fingerprint,
    }


@router.put("/api/config/llm")
async def update_llm_config_route(
    req: LLMConfigUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        result = update_llm_config(
            api_key=req.api_key,
            base_url=req.base_url,
            model=req.model,
            provider=req.provider,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        from nf_core.llm_client import llm_client
        applied = llm_client.reload(
            config=resolve_provider_runtime(
                include_request=False,
                include_stage=False,
            )
        )
        result["applied"] = applied
    except Exception as e:
        logger.error("llm_client.reload after config update failed: %s", e)
        result["applied"] = None

    # 让该用户的 legacy pipeline 在下次访问时重建
    user_pipelines = [k for k in _pipelines if k[0] == current_user.id]
    for key in user_pipelines:
        try:
            await run_in_threadpool(_pipelines[key].save_state)
        except Exception:
            # 重建路径不能因落盘失败而阻塞 LLM 配置更新, 但必须有 log 留痕
            logger.exception(
                "pipeline.save_state failed during LLM config reload (user=%s, novel=%s)",
                key[0],
                key[1],
            )
        _pipelines.pop(key, None)
    return result


# -- Legacy Pipeline Routes (测试栏目用) -------------------------------------


@router.post("/api/generate")
@router.post("/api/legacy/generate")
async def generate_section(
    req: GenerateRequest, current_user: User = Depends(get_current_user)
):
    pipeline = _get_pipeline(current_user.id)
    novel_title = _current_novel_title(current_user.id)
    section = await pipeline.generate_next_section(
        global_outline=req.outline, novel_title=novel_title
    )
    await run_in_threadpool(pipeline.save_state)
    _auto_generate_title(current_user.id, pipeline, section.content)
    return {
        "chapter": section.chapter,
        "section": section.section,
        "title": section.title,
        "content": section.content,
        "word_count": section.word_count,
        "summary": section.summary,
    }


@router.post("/api/generate/stream")
@router.post("/api/legacy/generate/stream")
async def generate_section_stream(
    req: GenerateRequest, current_user: User = Depends(get_current_user)
):
    pipeline = _get_pipeline(current_user.id)
    novel_title = _current_novel_title(current_user.id)

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def produce():
            try:
                async for item in pipeline.generate_next_section_stream(
                    global_outline=req.outline, novel_title=novel_title
                ):
                    await queue.put(item)
            except asyncio.CancelledError:
                # 客户端断开 → 上游 cancel 我们; 不当 PipelineEvent 入队 (没人收), 直接退出
                raise
            except Exception as e:
                await queue.put(PipelineEvent(PipelineStage.FAILED, str(e)))
            finally:
                await queue.put(sentinel)

        task = asyncio.create_task(produce())

        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"comment": "heartbeat"}
                    continue

                if item is sentinel:
                    break

                if isinstance(item, PipelineEvent):
                    yield {
                        "event": "pipeline",
                        "data": json.dumps(
                            {
                                "stage": item.stage.value,
                                "message": item.message,
                                "data": item.data,
                            },
                            ensure_ascii=False,
                        ),
                    }
                elif isinstance(item, str):
                    yield {"event": "text", "data": item}

            yield {"event": "done", "data": ""}
        finally:
            # 客户端断开 / 异常退出时, produce 协程必须被取消, 否则 LLM 会继续烧 token.
            # 落盘也放在 finally — 中断时也保证写出已生成内容, 避免下次访问看到空状态。
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            try:
                await run_in_threadpool(pipeline.save_state)
            except Exception:
                logger.exception("save_state in stream finalizer failed")
            if pipeline._generated_sections:
                _auto_generate_title(
                    current_user.id,
                    pipeline,
                    pipeline._generated_sections[-1].content,
                )

    return EventSourceResponse(event_generator())


@router.post("/api/chapter/advance")
@router.post("/api/legacy/chapter/advance")
async def advance_chapter(current_user: User = Depends(get_current_user)):
    pipeline = _get_pipeline(current_user.id)
    pipeline.advance_chapter()
    await run_in_threadpool(pipeline.save_state)
    return {
        "chapter": pipeline.current_chapter,
        "section": pipeline.current_section,
    }


@router.post("/api/rollback")
@router.post("/api/legacy/rollback")
async def rollback(
    req: RollbackRequest, current_user: User = Depends(get_current_user)
):
    pipeline = _get_pipeline(current_user.id)
    try:
        pipeline.rollback_to_chapter(req.chapter)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await run_in_threadpool(pipeline.save_state)
    return {
        "chapter": pipeline.current_chapter,
        "section": pipeline.current_section,
        "message": f"已回滚到第{req.chapter}章",
    }


@router.get("/api/stats")
async def get_stats(current_user: User = Depends(get_current_user)):
    pipeline = _get_pipeline(current_user.id)
    stats = pipeline.get_stats()
    active_id = _active_by_user.get(current_user.id)
    stats["active_novel_id"] = active_id
    novel = (
        novel_manager.get_novel(current_user.id, active_id) if active_id else None
    )
    stats["active_novel_title"] = novel["title"] if novel else ""
    return stats


@router.get("/api/sections")
async def get_sections(current_user: User = Depends(get_current_user)):
    pipeline = _get_pipeline(current_user.id)
    return {
        "sections": [
            {
                "chapter": s.chapter,
                "section": s.section,
                "title": s.title,
                "content": s.content,
                "word_count": s.word_count,
                "summary": s.summary,
            }
            for s in pipeline._generated_sections
        ]
    }


# -- Knowledge Graph Routes --------------------------------------------------
#
# v2.34 — 优先用 tick 架构的 KnowledgeGraph (从 char_states / world_state 自动
# 喂图); 老 v1.x GenerationPipeline 仅作 fallback (用户从未启动过 tick runtime
# 时, 例如纯 legacy 节生成回退场景). 用户手动添加的实体/关系会同时落到 tick KG,
# 下次重启从 tick KG 恢复。


def _get_active_kg(user_id: str):
    """返回当前用户活跃 (user, novel) 的 KnowledgeGraph + 用于 save_to_disk 的 path.

    优先级:
    1. 当前已 active 的 TickRuntime.knowledge_graph (tick 架构, 自动喂图)
    2. 否则 fallback 到 legacy GenerationPipeline.knowledge_graph

    返回 ``(kg, kg_path_or_None)`` — path 仅在 tick KG 时有效, legacy pipeline
    不暴露独立路径 (GenerationPipeline 自管理 save_state).
    """
    try:
        from tick_runtime import get_active_runtime
        rt = get_active_runtime(user_id)
        if rt is not None:
            return rt.knowledge_graph, rt.kg_path
    except Exception as e:
        logger.debug("tick KG lookup failed, falling back to legacy: %s", e)
    pipeline = _get_pipeline(user_id)
    return pipeline.knowledge_graph, None


async def _persist_active_kg(user_id: str, kg, kg_path) -> None:
    """tick KG 改动后落盘. legacy fallback (kg_path is None) 静默跳过。

    save_to_disk 是同步 JSON 写, 大图时阻塞 event loop, 必须挪到线程池。
    """
    if not kg_path:
        return
    try:
        await run_in_threadpool(kg.save_to_disk, kg_path)
    except Exception as e:
        logger.warning("KG save_to_disk failed (non-fatal): %s", e)


@router.get("/api/graph")
async def get_graph(current_user: User = Depends(get_current_user)):
    kg, _ = _get_active_kg(current_user.id)
    return kg.to_dict()


@router.get("/api/graph/entities")
async def list_entities(
    entity_type: str | None = None,
    current_user: User = Depends(get_current_user),
):
    kg, _ = _get_active_kg(current_user.id)
    try:
        et = EntityType(entity_type) if entity_type else None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    entities = kg.list_entities(et)
    return {
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.entity_type.value,
                "attributes": e.attributes,
            }
            for e in entities
        ]
    }


@router.post("/api/graph/entities")
async def create_entity(
    req: EntityCreateRequest, current_user: User = Depends(get_current_user)
):
    kg, kg_path = _get_active_kg(current_user.id)
    try:
        entity_type = EntityType(req.entity_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    entity = Entity(
        id=req.id,
        name=req.name,
        entity_type=entity_type,
        attributes=req.attributes,
    )
    kg.add_entity(entity)
    await _persist_active_kg(current_user.id, kg, kg_path)
    return {"status": "ok", "entity_id": req.id}


@router.delete("/api/graph/entities/{entity_id}")
async def delete_entity(
    entity_id: str, current_user: User = Depends(get_current_user)
):
    kg, kg_path = _get_active_kg(current_user.id)
    kg.remove_entity(entity_id)
    await _persist_active_kg(current_user.id, kg, kg_path)
    return {"status": "ok"}


@router.get("/api/graph/entities/{entity_id}")
async def get_entity(
    entity_id: str, current_user: User = Depends(get_current_user)
):
    kg, _ = _get_active_kg(current_user.id)
    entity = kg.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    relations = kg.get_relations(entity_id)
    return {
        "entity": {
            "id": entity.id,
            "name": entity.name,
            "type": entity.entity_type.value,
            "attributes": entity.attributes,
        },
        "relations": [
            {
                "source": r.source_id,
                "target": r.target_id,
                "type": r.relation_type.value,
                "label": r.label,
            }
            for r in relations
        ],
    }


@router.post("/api/graph/relations")
async def create_relation(
    req: RelationCreateRequest, current_user: User = Depends(get_current_user)
):
    kg, kg_path = _get_active_kg(current_user.id)
    try:
        relation_type = RelationType(req.relation_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    relation = Relation(
        source_id=req.source_id,
        target_id=req.target_id,
        relation_type=relation_type,
        label=req.label,
    )
    try:
        kg.add_relation(relation)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await _persist_active_kg(current_user.id, kg, kg_path)
    return {"status": "ok"}


@router.delete("/api/graph/relations")
async def delete_relation(
    source_id: str,
    target_id: str,
    current_user: User = Depends(get_current_user),
):
    kg, kg_path = _get_active_kg(current_user.id)
    kg.remove_relation(source_id, target_id)
    await _persist_active_kg(current_user.id, kg, kg_path)
    return {"status": "ok"}


# -- Snapshots ---------------------------------------------------------------


@router.get("/api/snapshots")
async def list_snapshots(current_user: User = Depends(get_current_user)):
    pipeline = _get_pipeline(current_user.id)
    return {"snapshots": pipeline.knowledge_graph.list_snapshots()}


@router.post("/api/snapshots")
@router.post("/api/legacy/snapshots")
async def take_snapshot(current_user: User = Depends(get_current_user)):
    pipeline = _get_pipeline(current_user.id)
    # take_snapshot 写 JSON 文件 (knowledge_graph 全量 dump), 放线程池
    sid = await run_in_threadpool(
        pipeline.knowledge_graph.take_snapshot, pipeline.current_chapter
    )
    return {"snapshot_id": sid}


# -- Summary Tree ------------------------------------------------------------


@router.get("/api/outline")
async def get_outline(current_user: User = Depends(get_current_user)):
    pipeline = _get_pipeline(current_user.id)
    return {
        "outline": pipeline.summary_tree.get_outline(),
        "root_summary": pipeline.summary_tree.root_summary,
    }


# -- Memory ------------------------------------------------------------------


@router.get("/api/memory")
async def get_working_memory(current_user: User = Depends(get_current_user)):
    pipeline = _get_pipeline(current_user.id)
    wm = pipeline.working_memory
    return {
        "sections": [
            {
                "chapter": s.chapter,
                "section": s.section,
                "title": s.title,
                "word_count": s.word_count,
            }
            for s in wm.sections
        ],
        "scene": {
            "environment": wm.scene.environment_description,
            "active_characters": [
                {
                    "entity_id": c.entity_id,
                    "name": c.name,
                    "emotion": c.emotion,
                }
                for c in wm.scene.active_characters
            ],
        },
    }


# -- System ------------------------------------------------------------------


@router.post("/api/reset")
@router.post("/api/legacy/reset")
async def reset_pipeline(current_user: User = Depends(get_current_user)):
    nid = _active_by_user.get(current_user.id)
    if nid is not None:
        _pipelines.pop((current_user.id, nid), None)
    _get_pipeline(current_user.id)
    return {"status": "ok", "message": "Pipeline reset"}


# -- Helpers -----------------------------------------------------------------


def _current_novel_title(user_id: str) -> str:
    active = _active_by_user.get(user_id)
    if active is None:
        return ""
    novel = novel_manager.get_novel(user_id, active)
    if novel is None:
        return ""
    title = (novel.get("title") or "").strip()
    if title == "未命名小说":
        return ""
    return title


def _auto_generate_title(
    user_id: str, pipeline: GenerationPipeline, content: str
) -> None:
    active = _active_by_user.get(user_id)
    if active is None:
        return
    novel = novel_manager.get_novel(user_id, active)
    if novel is None or novel["title"] != "未命名小说":
        return
    if pipeline.total_sections != 1:
        return
    task = asyncio.create_task(
        _generate_title_async(user_id, active, content),
        name=f"auto-title-{user_id}-{active}",
    )
    _title_tasks.add(task)
    task.add_done_callback(_on_title_task_done)


def _on_title_task_done(task: asyncio.Task) -> None:
    """v2.37 — 释放强引用 + 消费异常 (防止 'exception was never retrieved')。"""
    _title_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("auto title generation task crashed: %s", exc, exc_info=exc)


async def _generate_title_async(user_id: str, novel_id: str, content: str) -> None:
    try:
        from nf_core.llm_client import llm_client

        resp = await llm_client.chat(
            system_prompt=(
                "你是一位小说编辑。根据以下小说开篇内容，为这部小说取一个简短的标题（2-6个字）。"
                "只输出标题，不要任何解释或标点符号。"
            ),
            user_prompt=content[:2000],
            temperature=0.7,
            max_tokens=32,
            agent_id="title_generator",
            priority="optional",
        )
        title = resp.content.strip().strip("《》\"''""")[:20]
        if title:
            novel_manager.update_title(user_id, novel_id, title)
            logger.info("Auto-generated novel title: %s", title)
    except Exception as e:
        logger.error("Failed to auto-generate title: %s", e)


# v2.26 — legacy set_active_novel_id 兼容 shim: 旧测试代码可能 still 调用。
# 不再做任何事 — 旧单租户语义已无法对齐多用户。
def set_active_novel_id(novel_id: str) -> None:  # noqa: D401
    """Deprecated — v2.26 multi-tenant 后 active 是 per-user 的。"""
    logger.debug("set_active_novel_id is deprecated as of v2.26 (no-op)")
