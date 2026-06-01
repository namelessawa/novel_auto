"""Hierarchical Summary Tree — multi-level compression of novel history."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from core.llm_client import llm_client

logger = logging.getLogger(__name__)


@dataclass
class SummaryNode:
    node_id: str
    level: int  # 0 = section leaf, 1 = chapter, 2 = volume, …
    summary: str
    children: list[SummaryNode] = field(default_factory=list)
    chapter_range: tuple[int, int] = (0, 0)  # inclusive


class SummaryTree:
    """N-ary tree that compresses section summaries into chapter / volume synopses."""

    def __init__(self, merge_threshold: int = 10) -> None:
        self._root = SummaryNode(
            node_id="root", level=99, summary="故事尚未开始。"
        )
        self._leaves: list[SummaryNode] = []
        self._merge_threshold = merge_threshold
        self._pending_chapter_leaves: list[SummaryNode] = []

    # -- public api -----------------------------------------------------------

    @property
    def root_summary(self) -> str:
        # If no merges have happened yet, derive summary from pending leaves
        if self._root.summary == "故事尚未开始。" and self._pending_chapter_leaves:
            parts = [leaf.summary for leaf in self._pending_chapter_leaves]
            return " ".join(parts)[:300]
        return self._root.summary

    @property
    def leaf_count(self) -> int:
        return len(self._leaves)

    async def add_section_summary(
        self, chapter: int, section: int, summary: str
    ) -> None:
        leaf = SummaryNode(
            node_id=f"ch{chapter}_s{section}",
            level=0,
            summary=summary,
            chapter_range=(chapter, chapter),
        )
        self._leaves.append(leaf)
        self._pending_chapter_leaves.append(leaf)

        if len(self._pending_chapter_leaves) >= self._merge_threshold:
            await self._merge_up()

    def get_outline(self, max_depth: int = 2) -> str:
        """Return a top-level outline string suitable for prompt injection."""
        lines: list[str] = []
        self._walk(self._root, 0, max_depth, lines)
        # Include pending leaves that haven't been merged yet
        if self._pending_chapter_leaves:
            for leaf in self._pending_chapter_leaves:
                indent = "  " * 1
                lines.append(f"{indent}[{leaf.node_id}] {leaf.summary[:80]}…")
        return "\n".join(lines)

    def get_chapter_summaries(self, chapter: int) -> list[str]:
        return [
            n.summary
            for n in self._leaves
            if n.chapter_range[0] == chapter
        ]

    # -- internals ------------------------------------------------------------

    async def _merge_up(self) -> None:
        children = list(self._pending_chapter_leaves)
        self._pending_chapter_leaves.clear()

        combined = "\n".join(f"- {c.summary}" for c in children)
        ch_start = children[0].chapter_range[0]
        ch_end = children[-1].chapter_range[1]

        try:
            merged_summary = await self._compress(combined, ch_start, ch_end)
        except Exception as e:
            logger.error("Summary merge LLM failed: %s", e)
            merged_summary = combined[:200]

        parent = SummaryNode(
            node_id=f"vol_{ch_start}_{ch_end}",
            level=1,
            summary=merged_summary,
            children=children,
            chapter_range=(ch_start, ch_end),
        )
        self._root.children.append(parent)

        try:
            self._root.summary = await self._compress_root()
        except Exception as e:
            logger.error("Root compress LLM failed: %s", e)
            self._root.summary = merged_summary[:300]

    async def _compress(
        self, text: str, ch_start: int, ch_end: int
    ) -> str:
        resp = await llm_client.chat(
            system_prompt=(
                "你是一位小说编辑。请将以下多段内容摘要压缩为一段简洁的"
                f"分卷梗概（第{ch_start}-{ch_end}章），保留关键情节转折和角色发展。"
                "字数控制在 200 字以内。"
            ),
            user_prompt=text,
            temperature=0.3,
            max_tokens=512,
        )
        return resp.content.strip()

    async def _compress_root(self) -> str:
        if not self._root.children:
            return self._root.summary
        parts = "\n".join(
            f"[{c.chapter_range}] {c.summary}" for c in self._root.children
        )
        resp = await llm_client.chat(
            system_prompt=(
                "你是一位小说编辑。请将以下各卷梗概合并为一段全书总纲摘要，"
                "字数控制在 300 字以内，保留主线和关键转折。"
            ),
            user_prompt=parts,
            temperature=0.3,
            max_tokens=512,
        )
        return resp.content.strip()

    def _walk(
        self,
        node: SummaryNode,
        depth: int,
        max_depth: int,
        lines: list[str],
    ) -> None:
        indent = "  " * depth
        label = node.node_id
        lines.append(f"{indent}[{label}] {node.summary[:80]}…")
        if depth < max_depth:
            for child in node.children:
                self._walk(child, depth + 1, max_depth, lines)
