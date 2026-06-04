"""FastAPI routes for the novel generation system."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from config.settings import get_llm_config, update_llm_config
from memory_system.models import Entity, EntityType, Relation, RelationType
from pipeline.engine import GenerationPipeline, PipelineEvent, PipelineStage
import novel_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# Global pipeline instance + active novel tracking
_pipeline: GenerationPipeline | None = None
_active_novel_id: str | None = None


def _init_default_novel() -> str:
    """Ensure at least one novel exists; delegated to ``novel_manager``."""
    return novel_manager.resolve_default_novel_id()


def set_active_novel_id(novel_id: str) -> None:
    """启动钩子用 — 把 legacy pipeline 的 active 指针对齐到 tick runtime。

    旧实现: tick runtime 在 FastAPI startup 装配, ``_active_novel_id`` 直到
    第一次 ``get_pipeline()`` 才赋值; manifest 第一项与 tick runtime 启动用的
    ``ACTIVE_NOVEL_ID`` 不同步时, /api/stats 与 /api/tick/* 指向不同小说。
    """
    global _active_novel_id, _pipeline
    if _active_novel_id == novel_id:
        return
    if _pipeline is not None:
        try:
            _pipeline.save_state()
        except Exception:
            logger.exception("save_state before active novel realign failed")
        _pipeline = None
    _active_novel_id = novel_id


def get_pipeline() -> GenerationPipeline:
    global _pipeline, _active_novel_id
    if _pipeline is None:
        if _active_novel_id is None:
            _active_novel_id = _init_default_novel()
        data_dir = novel_manager.get_novel_data_dir(_active_novel_id)
        _pipeline = GenerationPipeline(data_dir=data_dir)
        _pipeline.load_state()
    return _pipeline


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


class ChapterAdvanceRequest(BaseModel):
    pass


class RollbackRequest(BaseModel):
    chapter: int


class OutlineUpdateRequest(BaseModel):
    outline: str


class LLMConfigUpdateRequest(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    # v2.20 — 切换 active provider (deepseek / mimo / custom)。后端写
    # os.environ['LLM_PROVIDER']; core/config.py 在 importlib 重 exec 时读到
    # 新值, 让 llm_client.reload() 真正跑到新 provider。仅作用于当前进程,
    # 重启后回退到 .env 静态值, 避免在线编辑 .env 带来的风险。
    provider: str | None = None


class NovelCreateRequest(BaseModel):
    title: str = "未命名小说"


class NovelUpdateRequest(BaseModel):
    title: str


# -- Novel Management Routes -------------------------------------------------


@router.get("/api/novels")
async def list_novels():
    novels = novel_manager.list_novels()
    return {"novels": novels, "active_id": _active_novel_id}


@router.post("/api/novels")
async def create_novel(req: NovelCreateRequest):
    entry = novel_manager.create_novel(req.title)
    return entry


@router.put("/api/novels/{novel_id}")
async def update_novel(novel_id: str, req: NovelUpdateRequest):
    try:
        entry = novel_manager.update_title(novel_id, req.title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if entry is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    return entry


@router.delete("/api/novels/{novel_id}")
async def delete_novel(novel_id: str):
    global _pipeline, _active_novel_id
    if novel_id == _active_novel_id:
        raise HTTPException(status_code=400, detail="不能删除当前活跃的小说")
    try:
        ok = novel_manager.delete_novel(novel_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Novel not found")
    return {"status": "ok"}


@router.post("/api/novels/{novel_id}/switch")
async def switch_novel(novel_id: str):
    global _pipeline, _active_novel_id

    try:
        target = novel_manager.get_novel(novel_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if target is None:
        raise HTTPException(status_code=404, detail="Novel not found")

    # Save current pipeline state
    if _pipeline is not None:
        _pipeline.save_state()

    # Load target novel
    _active_novel_id = novel_id
    data_dir = novel_manager.get_novel_data_dir(novel_id)
    _pipeline = GenerationPipeline(data_dir=data_dir)
    _pipeline.load_state()

    # v2.15 — 同步把 tick runtime 切到目标小说; 否则 /api/tick/* 仍指向旧 novel。
    # lazy import 防启动期循环依赖。tick runtime 装配 9 agent + 多个增强层,
    # 失败不应阻塞 legacy pipeline 切换 — 仅记日志。
    try:
        from tick_runtime import set_active_novel
        set_active_novel(novel_id)
    except Exception as e:
        logger.warning("set_active_novel(%s) failed (non-fatal): %s", novel_id, e)

    return {"status": "ok", "active_id": novel_id, "title": target["title"]}


# -- LLM Config Routes ------------------------------------------------------


@router.get("/api/config/llm")
async def get_llm_config_route():
    return get_llm_config()


@router.put("/api/config/llm")
async def update_llm_config_route(req: LLMConfigUpdateRequest):
    try:
        result = update_llm_config(
            api_key=req.api_key,
            base_url=req.base_url,
            model=req.model,
            provider=req.provider,
        )
    except ValueError as e:
        # v2.20 — 非法 provider 等显式约束失败 → 422, 不掉 500/暴露 traceback
        raise HTTPException(status_code=422, detail=str(e))

    # v2.17 — 真正热重建全局 llm_client; 之前只重置了 legacy pipeline, 但 tick
    # runtime 与 SummaryTree.legendize 等所有路径共享同一个 llm_client singleton,
    # 全部还指向旧 AsyncOpenAI 实例 → 配置改了等于没改。
    try:
        from nf_core.llm_client import llm_client
        applied = llm_client.reload()
        result["applied"] = applied
    except Exception as e:
        logger.error("llm_client.reload after config update failed: %s", e)
        result["applied"] = None

    # Reset pipeline so it picks up new config on next use
    global _pipeline
    if _pipeline is not None:
        _pipeline.save_state()
    _pipeline = None
    return result


# -- Pipeline Routes ---------------------------------------------------------


@router.post("/api/generate")
async def generate_section(req: GenerateRequest):
    pipeline = get_pipeline()
    section = await pipeline.generate_next_section(global_outline=req.outline)
    pipeline.save_state()
    _auto_generate_title(pipeline, section.content)
    return {
        "chapter": section.chapter,
        "section": section.section,
        "title": section.title,
        "content": section.content,
        "word_count": section.word_count,
        "summary": section.summary,
    }


@router.post("/api/generate/stream")
async def generate_section_stream(req: GenerateRequest):
    pipeline = get_pipeline()

    async def event_generator():
        # Use an asyncio.Queue so we can send heartbeats while the
        # pipeline blocks on long LLM calls (e.g. state sync).
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def produce():
            try:
                async for item in pipeline.generate_next_section_stream(
                    global_outline=req.outline
                ):
                    await queue.put(item)
            except Exception as e:
                await queue.put(
                    PipelineEvent(PipelineStage.FAILED, str(e))
                )
            finally:
                await queue.put(sentinel)

        task = asyncio.create_task(produce())

        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                # Send SSE comment as heartbeat to keep connection alive
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
                yield {
                    "event": "text",
                    "data": item,
                }

        yield {"event": "done", "data": ""}
        await task

        # Save state after generation completes
        pipeline.save_state()

    return EventSourceResponse(event_generator())


@router.post("/api/chapter/advance")
async def advance_chapter():
    pipeline = get_pipeline()
    pipeline.advance_chapter()
    pipeline.save_state()
    return {
        "chapter": pipeline.current_chapter,
        "section": pipeline.current_section,
    }


@router.post("/api/rollback")
async def rollback(req: RollbackRequest):
    pipeline = get_pipeline()
    try:
        pipeline.rollback_to_chapter(req.chapter)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    pipeline.save_state()
    return {
        "chapter": pipeline.current_chapter,
        "section": pipeline.current_section,
        "message": f"已回滚到第{req.chapter}章",
    }


@router.get("/api/stats")
async def get_stats():
    pipeline = get_pipeline()
    stats = pipeline.get_stats()
    stats["active_novel_id"] = _active_novel_id
    novel = novel_manager.get_novel(_active_novel_id) if _active_novel_id else None
    stats["active_novel_title"] = novel["title"] if novel else ""
    return stats


@router.get("/api/text")
async def get_full_text():
    pipeline = get_pipeline()
    return {"text": pipeline.get_full_text()}


@router.get("/api/sections")
async def get_sections():
    pipeline = get_pipeline()
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


@router.get("/api/graph")
async def get_graph():
    pipeline = get_pipeline()
    return pipeline.knowledge_graph.to_dict()


@router.get("/api/graph/entities")
async def list_entities(entity_type: str | None = None):
    pipeline = get_pipeline()
    et = EntityType(entity_type) if entity_type else None
    entities = pipeline.knowledge_graph.list_entities(et)
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
async def create_entity(req: EntityCreateRequest):
    pipeline = get_pipeline()
    entity = Entity(
        id=req.id,
        name=req.name,
        entity_type=EntityType(req.entity_type),
        attributes=req.attributes,
    )
    pipeline.knowledge_graph.add_entity(entity)
    return {"status": "ok", "entity_id": req.id}


@router.delete("/api/graph/entities/{entity_id}")
async def delete_entity(entity_id: str):
    pipeline = get_pipeline()
    pipeline.knowledge_graph.remove_entity(entity_id)
    return {"status": "ok"}


@router.get("/api/graph/entities/{entity_id}")
async def get_entity(entity_id: str):
    pipeline = get_pipeline()
    entity = pipeline.knowledge_graph.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    relations = pipeline.knowledge_graph.get_relations(entity_id)
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
async def create_relation(req: RelationCreateRequest):
    pipeline = get_pipeline()
    relation = Relation(
        source_id=req.source_id,
        target_id=req.target_id,
        relation_type=RelationType(req.relation_type),
        label=req.label,
    )
    pipeline.knowledge_graph.add_relation(relation)
    return {"status": "ok"}


@router.delete("/api/graph/relations")
async def delete_relation(source_id: str, target_id: str):
    pipeline = get_pipeline()
    pipeline.knowledge_graph.remove_relation(source_id, target_id)
    return {"status": "ok"}


# -- Snapshots ---------------------------------------------------------------


@router.get("/api/snapshots")
async def list_snapshots():
    pipeline = get_pipeline()
    return {"snapshots": pipeline.knowledge_graph.list_snapshots()}


@router.post("/api/snapshots")
async def take_snapshot():
    pipeline = get_pipeline()
    sid = pipeline.knowledge_graph.take_snapshot(pipeline.current_chapter)
    return {"snapshot_id": sid}


# -- Summary Tree ------------------------------------------------------------


@router.get("/api/outline")
async def get_outline():
    pipeline = get_pipeline()
    return {
        "outline": pipeline.summary_tree.get_outline(),
        "root_summary": pipeline.summary_tree.root_summary,
    }


# -- Memory ------------------------------------------------------------------


@router.get("/api/memory")
async def get_working_memory():
    pipeline = get_pipeline()
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
async def reset_pipeline():
    global _pipeline
    _pipeline = None
    pipeline = get_pipeline()
    return {"status": "ok", "message": "Pipeline reset"}


# -- Helpers -----------------------------------------------------------------


def _auto_generate_title(pipeline: GenerationPipeline, content: str) -> None:
    """Auto-generate novel title after first section if still unnamed."""
    if _active_novel_id is None:
        return
    novel = novel_manager.get_novel(_active_novel_id)
    if novel is None:
        return
    if novel["title"] != "未命名小说":
        return
    if pipeline.total_sections != 1:
        return

    # Generate title from content using LLM (fire-and-forget in background)
    asyncio.ensure_future(_generate_title_async(_active_novel_id, content))


async def _generate_title_async(novel_id: str, content: str) -> None:
    """Use LLM to generate a short novel title from the first section."""
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
            novel_manager.update_title(novel_id, title)
            logger.info("Auto-generated novel title: %s", title)
    except Exception as e:
        logger.error("Failed to auto-generate title: %s", e)
