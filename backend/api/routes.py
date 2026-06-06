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
async def create_novel(req: NovelCreateRequest, auto_bootstrap: bool = False):
    """创建小说。

    v2.25 — 默认改为 ``auto_bootstrap=False``: POST 仅创建空壳, 由前端随后
    显式调 POST /api/novels/{id}/bootstrap-world 跑 4 阶段冷启动 (世界 /
    角色 / 伏笔 / 风格锚点)。bootstrap_world 完成后会链式触发首节生成。

    根本原因: v2.24 默认自动入 bootstrap_section, 但 fresh novel 的 TickState
    没有任何角色 / 事件种子 → Narrator 沉默到 max_ticks → 首节几乎空。
    把"种子化"从"创建空壳"中拆出来, 让前端用户能填入世界种子 / 作品定位 /
    参考作家这三类用户意图, 才有信息给 LLM 生成有意义的初始世界。

    保留 ``auto_bootstrap=True`` 路径供测试 / 节级管线对照实验。
    """
    entry = novel_manager.create_novel(req.title)
    bootstrap_task_id = ""
    if auto_bootstrap:
        try:
            bootstrap_task_id = await _spawn_bootstrap_section_task(
                novel_id=entry["id"], novel_title=entry.get("title", "")
            )
        except Exception as e:
            # 不阻塞 novel 创建 — 任务失败前端能从 task list 看到错因, 不必让
            # POST /api/novels 整体 500。
            logger.warning(
                "auto bootstrap section task for novel '%s' failed: %s",
                entry["id"],
                e,
            )
    return {**entry, "bootstrap_task_id": bootstrap_task_id}


async def _spawn_bootstrap_section_task(*, novel_id: str, novel_title: str) -> str:
    """v2.24 — 创建小说时自动入队首节生成任务。

    与 /api/section/generate 走同一份 executor + SectionStore + SectionCloser,
    仅 kind 字段不同 (bootstrap_section), 方便前端区分"首节 / 续写"两种任务样式。
    """
    from agents.section_closer import SectionCloser
    from api.section_routes import _make_section_executor
    from sections.section_store import get_section_store
    from tasks.task_manager import TaskConflict, get_task_manager
    from tick_runtime import get_runtime

    # runtime 预拉起 — 失败 (LLM provider 未配等) 直接抛, 由调用方吞掉
    get_runtime(novel_id)
    data_dir = novel_manager.get_novel_data_dir(novel_id)
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
        # 同一 novel 刚被创建, 不应该 conflict — 真发生说明前端连点 2 次
        return ""
    return snap.id


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
    """两阶段小说切换 (v2.21 调整顺序):

    1. tick runtime 先切 (失败 → 503, 不污染 legacy);
    2. legacy pipeline 后切 (此时 tick 已成功, legacy save_state 是幂等的,
       即便它失败 tick 也已落地, 下次启动会读 tick 状态恢复一致性)。

    此前实现先 _pipeline 切到目标小说、再 set_active_novel; tick 失败时只
    warning + return 200, 用户看到"切换成功"但 /api/tick/* 仍指向旧 novel,
    UI 行为难以诊断 — 现修为显式 503。
    """
    global _pipeline, _active_novel_id

    try:
        target = novel_manager.get_novel(novel_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if target is None:
        raise HTTPException(status_code=404, detail="Novel not found")

    # Save current pipeline state (旧 novel 的状态先落盘, 与 tick 切换是否成功无关)
    if _pipeline is not None:
        _pipeline.save_state()

    # 阶段 1 — tick runtime 优先切换。失败立刻报错, legacy 还停在旧 novel。
    # lazy import 防启动期循环依赖。
    try:
        from tick_runtime import set_active_novel
        set_active_novel(novel_id)
    except Exception as e:
        logger.error("set_active_novel(%s) failed - aborting switch: %s", novel_id, e)
        raise HTTPException(
            status_code=503,
            detail=f"tick runtime 切换失败: {e}; legacy pipeline 未切换",
        )

    # 阶段 2 — legacy pipeline 跟进。到这里 tick 已切, 任何 legacy 失败都可在
    # 下次启动恢复 (默认会读 tick 状态)。
    _active_novel_id = novel_id
    data_dir = novel_manager.get_novel_data_dir(novel_id)
    _pipeline = GenerationPipeline(data_dir=data_dir)
    _pipeline.load_state()

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
@router.post("/api/legacy/generate")
async def generate_section(req: GenerateRequest):
    """v2.24 — 节级管线 (legacy 一次性章节生成器)。

    保留为前端"测试 → 节级管线"栏目的写入端点。新主路径是
    POST /api/section/generate (tick 驱动 + 任务队列)。

    /api/generate 旧路径保留为 alias, 后续清理可删。
    """
    pipeline = get_pipeline()
    novel_title = _current_novel_title()
    section = await pipeline.generate_next_section(
        global_outline=req.outline, novel_title=novel_title
    )
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
@router.post("/api/legacy/generate/stream")
async def generate_section_stream(req: GenerateRequest):
    pipeline = get_pipeline()
    # v2.23 — 拿到当前活跃小说的真实标题, 传到 OutlineAgent / WriterAgent prompt;
    # 此前完全没传, 标题"《白毛猫娘》"也被无视, 直接走"上班族公交车"开篇。
    novel_title = _current_novel_title()

    async def event_generator():
        # Use an asyncio.Queue so we can send heartbeats while the
        # pipeline blocks on long LLM calls (e.g. state sync).
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def produce():
            try:
                async for item in pipeline.generate_next_section_stream(
                    global_outline=req.outline, novel_title=novel_title
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

        # v2.23 — SSE 流路径也触发自动标题 (仅当用户保留默认"未命名小说"时);
        # 此前只有 /api/generate 非流式才补标题, 前端 HomeView 走的是 stream,
        # 第一节生成后小说名永远停在"未命名小说"。
        if pipeline._generated_sections:
            _auto_generate_title(
                pipeline, pipeline._generated_sections[-1].content
            )

    return EventSourceResponse(event_generator())


@router.post("/api/chapter/advance")
@router.post("/api/legacy/chapter/advance")
async def advance_chapter():
    pipeline = get_pipeline()
    pipeline.advance_chapter()
    pipeline.save_state()
    return {
        "chapter": pipeline.current_chapter,
        "section": pipeline.current_section,
    }


@router.post("/api/rollback")
@router.post("/api/legacy/rollback")
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
    # v2.22 — 把枚举越界翻成 422 而非未捕获 ValueError → 500。
    try:
        et = EntityType(entity_type) if entity_type else None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
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
    # v2.22 — 非法 entity_type 走 422 而非 500
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
    # v2.22 — 非法 relation_type → 422; 端点不存在 → 404 (而非把空节点写进图)
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
        pipeline.knowledge_graph.add_relation(relation)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
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
@router.post("/api/legacy/snapshots")
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
@router.post("/api/legacy/reset")
async def reset_pipeline():
    global _pipeline
    _pipeline = None
    pipeline = get_pipeline()
    return {"status": "ok", "message": "Pipeline reset"}


# -- Helpers -----------------------------------------------------------------


def _current_novel_title() -> str:
    """当前活跃小说标题; 没有活跃小说或仍是默认名时返回 空串。

    v2.23 — 给 OutlineAgent / WriterAgent 的 prompt 注入用; 空串 / 未命名
    时让 prompt 走兜底分支, 而不是反过来约束 LLM 写"未命名小说"题材。
    """
    if _active_novel_id is None:
        return ""
    novel = novel_manager.get_novel(_active_novel_id)
    if novel is None:
        return ""
    title = (novel.get("title") or "").strip()
    if title == "未命名小说":
        return ""
    return title


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
