"""Core Execution Pipeline — orchestrates the full section-generation workflow."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Callable

from agents.outline_agent import OutlineAgent
from agents.retrieval_agent import RetrievalAgent
from agents.update_agent import UpdateAgent
from agents.validation_agent import ValidationAgent
from agents.writer_agent import WriterAgent
from config.settings import settings
from memory_system.models import ActionPlan, Section, ValidationResult
from graph.knowledge_graph import KnowledgeGraph
from memory.summary_tree import SummaryTree
from memory.working_memory import ActiveCharacter, SceneContext, WorkingMemory
from vector.vector_store import VectorStore

logger = logging.getLogger(__name__)


class PipelineStage(str, Enum):
    CONTEXT_ASSEMBLY = "context_assembly"
    PLANNING = "planning"
    RETRIEVAL = "retrieval"
    VALIDATION = "validation"
    GENERATION = "generation"
    STATE_SYNC = "state_sync"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class PipelineEvent:
    stage: PipelineStage
    message: str
    data: dict = field(default_factory=dict)


class GenerationPipeline:
    """Orchestrates the six-stage section generation pipeline."""

    def __init__(self, data_dir: str | None = None) -> None:
        self._data_dir = data_dir

        # Resolve per-novel dirs or fall back to global settings
        chroma_dir = os.path.join(data_dir, "chroma") if data_dir else None
        snapshot_dir = os.path.join(data_dir, "snapshots") if data_dir else None

        # Core modules
        self.working_memory = WorkingMemory(capacity=settings.working_memory_size)
        self.summary_tree = SummaryTree(merge_threshold=settings.summary_merge_threshold)
        self.knowledge_graph = KnowledgeGraph(snapshot_dir=snapshot_dir)
        self.vector_store = VectorStore(persist_dir=chroma_dir)

        # Agents
        self._outline_agent = OutlineAgent()
        self._retrieval_agent = RetrievalAgent(
            self.knowledge_graph, self.vector_store
        )
        self._validation_agent = ValidationAgent(self.knowledge_graph)
        self._writer_agent = WriterAgent()
        self._update_agent = UpdateAgent(
            self.knowledge_graph, self.vector_store, self.summary_tree
        )

        # Register eviction callback
        self.working_memory.register_evict_callback(self._on_section_evict)

        # State
        self._current_chapter = 1
        self._current_section = 1
        self._generated_sections: list[Section] = []
        self._event_listeners: list[Callable[[PipelineEvent], None]] = []

    # -- public api -----------------------------------------------------------

    @property
    def current_chapter(self) -> int:
        return self._current_chapter

    @property
    def current_section(self) -> int:
        return self._current_section

    @property
    def total_sections(self) -> int:
        return len(self._generated_sections)

    @property
    def total_words(self) -> int:
        return sum(s.word_count for s in self._generated_sections)

    def on_event(self, listener: Callable[[PipelineEvent], None]) -> None:
        self._event_listeners.append(listener)

    async def generate_next_section(
        self, global_outline: str = ""
    ) -> Section:
        """Run the full pipeline to produce the next section."""

        # Stage 1: Context Assembly
        self._emit(PipelineStage.CONTEXT_ASSEMBLY, "组装上下文…")
        outline = global_outline or self.summary_tree.get_outline()
        recent_text = self.working_memory.recent_text
        scene_info = self.working_memory.to_prompt_block()

        # Stage 2: Planning
        self._emit(PipelineStage.PLANNING, "生成行动指南…")
        plan = await self._outline_agent.plan(
            chapter=self._current_chapter,
            section=self._current_section,
            global_outline=outline,
            recent_text=recent_text,
            scene_info=scene_info,
        )
        self._emit(
            PipelineStage.PLANNING,
            f"行动指南: {plan.plan_text[:60]}…",
            {"plan": plan.plan_text},
        )

        # Stage 3 & 4: Retrieval + Validation loop
        section = await self._retrieve_validate_generate(
            plan, outline, recent_text, scene_info
        )

        # Stage 6: State Sync
        self._emit(PipelineStage.STATE_SYNC, "同步世界状态…")
        changes = await self._update_agent.update(section)

        # Update scene context from changes
        scene_data = changes.get("scene", {})
        if scene_data:
            active_chars = [
                ActiveCharacter(
                    entity_id=c.get("entity_id", ""),
                    name=c.get("name", ""),
                    emotion=c.get("emotion", "neutral"),
                )
                for c in scene_data.get("active_characters", [])
            ]
            self.working_memory.update_scene(
                SceneContext(
                    environment_description=scene_data.get("environment", ""),
                    active_characters=active_chars,
                )
            )

        # Push to working memory
        await self.working_memory.push(section)
        self._generated_sections.append(section)

        # Take snapshot at chapter boundaries
        if self._should_snapshot():
            self.knowledge_graph.take_snapshot(self._current_chapter)

        # Advance counters
        self._current_section += 1

        self._emit(
            PipelineStage.COMPLETE,
            f"第{section.chapter}章 第{section.section}节 生成完成（{section.word_count}字）",
            {
                "chapter": section.chapter,
                "section": section.section,
                "word_count": section.word_count,
            },
        )
        return section

    async def generate_next_section_stream(
        self, global_outline: str = ""
    ) -> AsyncIterator[str | PipelineEvent]:
        """Streaming variant that yields text chunks and pipeline events."""

        # Stage 1: Context Assembly
        event = PipelineEvent(PipelineStage.CONTEXT_ASSEMBLY, "组装上下文…")
        yield event
        outline = global_outline or self.summary_tree.get_outline()
        recent_text = self.working_memory.recent_text
        scene_info = self.working_memory.to_prompt_block()

        # Stage 2: Planning
        event = PipelineEvent(PipelineStage.PLANNING, "生成行动指南…")
        yield event
        plan = await self._outline_agent.plan(
            chapter=self._current_chapter,
            section=self._current_section,
            global_outline=outline,
            recent_text=recent_text,
            scene_info=scene_info,
        )
        yield PipelineEvent(
            PipelineStage.PLANNING,
            f"行动指南就绪",
            {"plan": plan.plan_text},
        )

        # Stage 3: Retrieval
        yield PipelineEvent(PipelineStage.RETRIEVAL, "检索相关信息…")
        context = await self._retrieval_agent.retrieve(plan)

        # Stage 4: Validation
        yield PipelineEvent(PipelineStage.VALIDATION, "逻辑审查…")
        validation = await self._validation_agent.validate(
            plan, context.entity_states
        )
        if not validation.is_valid:
            yield PipelineEvent(
                PipelineStage.VALIDATION,
                f"检测到冲突: {', '.join(validation.conflicts)}",
                {"conflicts": validation.conflicts},
            )

        # Stage 5: Generation (streaming)
        yield PipelineEvent(PipelineStage.GENERATION, "开始生成正文…")
        collected_text: list[str] = []
        async for chunk in self._writer_agent.write_stream(
            plan=plan,
            entity_states=context.entity_states,
            historical_fragments=context.historical_fragments,
            recent_text=recent_text,
            scene_info=scene_info,
        ):
            collected_text.append(chunk)
            yield chunk

        content = "".join(collected_text)
        section = Section(
            chapter=self._current_chapter,
            section=self._current_section,
            title=plan.plan_text[:20],
            content=content,
            word_count=len(content),
        )

        # Stage 6: State Sync (must not block completion)
        yield PipelineEvent(PipelineStage.STATE_SYNC, "同步世界状态…")
        try:
            changes = await self._update_agent.update(section)
            scene_data = changes.get("scene", {})
            if scene_data:
                active_chars = [
                    ActiveCharacter(
                        entity_id=c.get("entity_id", ""),
                        name=c.get("name", ""),
                        emotion=c.get("emotion", "neutral"),
                    )
                    for c in scene_data.get("active_characters", [])
                ]
                self.working_memory.update_scene(
                    SceneContext(
                        environment_description=scene_data.get("environment", ""),
                        active_characters=active_chars,
                    )
                )
        except Exception as e:
            logger.error("State sync failed (non-fatal): %s", e)

        await self.working_memory.push(section)
        self._generated_sections.append(section)

        if self._should_snapshot():
            self.knowledge_graph.take_snapshot(self._current_chapter)

        self._current_section += 1

        yield PipelineEvent(
            PipelineStage.COMPLETE,
            f"生成完成（{section.word_count}字）",
            {
                "chapter": section.chapter,
                "section": section.section,
                "word_count": section.word_count,
            },
        )

    def advance_chapter(self) -> None:
        self.knowledge_graph.take_snapshot(self._current_chapter)
        self._current_chapter += 1
        self._current_section = 1

    def rollback_to_chapter(self, chapter: int) -> None:
        snapshots = self.knowledge_graph.list_snapshots()
        target = None
        for s in snapshots:
            if f"_ch{chapter}_" in s:
                target = s
                break
        if target is None:
            raise ValueError(f"No snapshot found for chapter {chapter}")

        self.knowledge_graph.rollback(target)
        self._generated_sections = [
            s for s in self._generated_sections if s.chapter < chapter
        ]
        self.working_memory.clear()
        self._current_chapter = chapter
        self._current_section = 1
        logger.info("Rolled back to chapter %d (snapshot %s)", chapter, target)

    def get_full_text(self) -> str:
        parts: list[str] = []
        current_ch = -1
        for s in self._generated_sections:
            if s.chapter != current_ch:
                current_ch = s.chapter
                parts.append(f"\n\n{'='*40}\n第{current_ch}章\n{'='*40}\n")
            parts.append(f"\n--- 第{s.section}节 ---\n{s.content}\n")
        return "".join(parts)

    def get_stats(self) -> dict:
        return {
            "current_chapter": self._current_chapter,
            "current_section": self._current_section,
            "total_sections": self.total_sections,
            "total_words": self.total_words,
            "entity_count": len(self.knowledge_graph.list_entities()),
            "vector_count": self.vector_store.count,
            "summary_leaf_count": self.summary_tree.leaf_count,
            "snapshots": self.knowledge_graph.list_snapshots()[:5],
        }

    # -- internals ------------------------------------------------------------

    async def _retrieve_validate_generate(
        self,
        plan: ActionPlan,
        outline: str,
        recent_text: str,
        scene_info: str,
    ) -> Section:
        for attempt in range(settings.max_validation_retries):
            # Stage 3: Retrieval
            self._emit(PipelineStage.RETRIEVAL, "检索相关信息…")
            context = await self._retrieval_agent.retrieve(plan)

            # Stage 4: Validation
            self._emit(PipelineStage.VALIDATION, f"逻辑审查（第{attempt+1}次）…")
            validation = await self._validation_agent.validate(
                plan, context.entity_states
            )

            if validation.is_valid:
                break

            self._emit(
                PipelineStage.VALIDATION,
                f"检测到冲突: {', '.join(validation.conflicts)}，重新规划…",
                {"conflicts": validation.conflicts, "attempt": attempt + 1},
            )

            # Re-plan with conflict feedback
            plan = await self._outline_agent.plan(
                chapter=plan.chapter,
                section=plan.section,
                global_outline=(
                    outline
                    + f"\n\n【上次冲突】{', '.join(validation.conflicts)}"
                    + f"\n【修改建议】{', '.join(validation.suggestions)}"
                ),
                recent_text=recent_text,
                scene_info=scene_info,
            )
        else:
            self._emit(
                PipelineStage.FAILED,
                "多次验证失败，使用最后一版计划继续生成。",
            )

        # Stage 5: Generation
        self._emit(PipelineStage.GENERATION, "生成正文…")
        section = await self._writer_agent.write(
            plan=plan,
            entity_states=context.entity_states,
            historical_fragments=context.historical_fragments,
            recent_text=recent_text,
            scene_info=scene_info,
        )
        return section

    async def _on_section_evict(self, section: Section) -> None:
        logger.debug(
            "Section evicted from working memory: ch%d s%d",
            section.chapter,
            section.section,
        )

    def _should_snapshot(self) -> bool:
        # Snapshot every 5 sections or on chapter change
        return self._current_section % 5 == 0

    def _emit(
        self, stage: PipelineStage, message: str, data: dict | None = None
    ) -> None:
        event = PipelineEvent(stage=stage, message=message, data=data or {})
        for listener in self._event_listeners:
            listener(event)
        logger.info("[%s] %s", stage.value, message)

    # -- persistence ----------------------------------------------------------

    # v2.17 — legacy pipeline 的 SummaryTree 与 tick runtime 共享 data_dir,
    # 但概念上是两条平行的生成链路。用独立文件名避免「tick 关闭时写盘」与
    # 「legacy 生成时写盘」互相覆盖。
    _SUMMARY_TREE_FILENAME = "summary_tree_legacy.json"

    def _summary_tree_path(self) -> str | None:
        if not self._data_dir:
            return None
        return os.path.join(self._data_dir, self._SUMMARY_TREE_FILENAME)

    def save_state(self) -> None:
        """Serialize pipeline state to data_dir/state.json + summary_tree + KG snapshot.

        v2.17: 旧实现只把 chapter/section/sections 写到 state.json, 重启后
        SummaryTree 与 KnowledgeGraph 全部空白 → /api/generate 上下文丢失。
        现在 SummaryTree 通过原子写入持久化, KG 通过现有 snapshot 机制持久化。
        """
        if not self._data_dir:
            return
        state = {
            "current_chapter": self._current_chapter,
            "current_section": self._current_section,
            "sections": [
                {
                    "chapter": s.chapter,
                    "section": s.section,
                    "title": s.title,
                    "content": s.content,
                    "summary": s.summary,
                    "word_count": s.word_count,
                }
                for s in self._generated_sections
            ],
        }
        path = os.path.join(self._data_dir, "state.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        # v2.17 — SummaryTree 增量摘要 (UpdateAgent 在每节后调用 add_section_summary)
        tree_path = self._summary_tree_path()
        if tree_path is not None:
            try:
                self.summary_tree.persist_to_disk(tree_path)
            except Exception as e:
                logger.error("SummaryTree persist failed (non-fatal): %s", e)

        # v2.17 — KG 触发一次 snapshot, 保证下次 load_state 能 rollback 回这一刻
        # _should_snapshot() 已经在每 5 节自动调用, 这里仅在 save_state 边界补一刀,
        # 防止用户手动 reset 或异常退出 → 两次 snapshot 之间的实体修改丢失。
        if self._generated_sections:
            try:
                self.knowledge_graph.take_snapshot(self._current_chapter)
            except Exception as e:
                logger.error("KG snapshot on save_state failed (non-fatal): %s", e)

    def load_state(self) -> None:
        """Restore pipeline state from data_dir/state.json + summary tree + latest KG snapshot."""
        if not self._data_dir:
            return
        path = os.path.join(self._data_dir, "state.json")
        if not os.path.isfile(path):
            # 即使 state.json 不存在, 也尝试恢复 SummaryTree / KG —— 兼容只用 tick
            # 流水线生成、后切回 legacy 看大纲的场景。
            self._restore_summary_tree()
            self._restore_kg_from_latest_snapshot()
            return
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        self._current_chapter = state.get("current_chapter", 1)
        self._current_section = state.get("current_section", 1)
        self._generated_sections = [
            Section(
                chapter=s["chapter"],
                section=s["section"],
                title=s["title"],
                content=s["content"],
                summary=s.get("summary", ""),
                word_count=s.get("word_count", 0),
            )
            for s in state.get("sections", [])
        ]
        self._restore_summary_tree()
        self._restore_kg_from_latest_snapshot()

    def _restore_summary_tree(self) -> None:
        tree_path = self._summary_tree_path()
        if tree_path is None:
            return
        try:
            self.summary_tree.load_from_disk(tree_path)
        except Exception as e:
            logger.error("SummaryTree load failed (non-fatal): %s", e)

    def _restore_kg_from_latest_snapshot(self) -> None:
        try:
            snapshots = self.knowledge_graph.list_snapshots()
        except Exception as e:
            logger.error("KG list_snapshots failed (non-fatal): %s", e)
            return
        if not snapshots:
            return
        # list_snapshots 按文件名倒序, 最新一个最先出现
        latest = snapshots[0]
        try:
            self.knowledge_graph.rollback(latest)
            logger.info("KG restored from snapshot: %s", latest)
        except Exception as e:
            logger.error("KG rollback to %s failed (non-fatal): %s", latest, e)
