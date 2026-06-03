"""Hierarchical Summary Tree — multi-level compression of novel history.

Layers (per ``infinite-novel-multiagent-prompts.md`` 第 9 节):

* Pending leaves (L0 candidates) - 刚到达,还没有触发 merge
* Leaves (L1 candidates) - 已被 merge 的节级摘要
* Volumes (L2) - 数章合并出的卷级梗概(_root.children)
* Root summary (L2/L3 mix) - 全书总纲
* Legends (L3) - 主动传说化的远古事件,允许多版本失真

P0 修复:之前这个文件没有 ``persist_to_disk()`` / ``load_from_disk()``,
重启 FastAPI 后所有 LLM 压缩出的历史摘要全部丢失,回退为 "故事尚未开始"。
现在补上原子化磁盘持久化 + ``legendize()`` 入口,供 MemoryCompressor 调用。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field

from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


@dataclass
class SummaryNode:
    node_id: str
    level: int  # 0 = section leaf, 1 = chapter, 2 = volume, …
    summary: str
    children: list["SummaryNode"] = field(default_factory=list)
    chapter_range: tuple[int, int] = (0, 0)  # inclusive

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "level": self.level,
            "summary": self.summary,
            "chapter_range": list(self.chapter_range),
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SummaryNode":
        cr = data.get("chapter_range", [0, 0])
        return cls(
            node_id=data["node_id"],
            level=int(data["level"]),
            summary=data.get("summary", ""),
            chapter_range=(int(cr[0]), int(cr[1])),
            children=[cls.from_dict(c) for c in data.get("children", [])],
        )


@dataclass
class Legend:
    """L3 传说化记忆条目 - 允许多版本失真。"""

    legend_id: str
    original_node_ids: list[str]
    chapter_range: tuple[int, int]
    legendary_form: str  # 自然语言,允许 "一种说法是...,另一种说法是..."
    classification: str = "folk_tale"  # world_lore | folk_tale | proverb
    importance: int = 5

    def to_dict(self) -> dict:
        return {
            "legend_id": self.legend_id,
            "original_node_ids": list(self.original_node_ids),
            "chapter_range": list(self.chapter_range),
            "legendary_form": self.legendary_form,
            "classification": self.classification,
            "importance": self.importance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Legend":
        cr = data.get("chapter_range", [0, 0])
        return cls(
            legend_id=data["legend_id"],
            original_node_ids=list(data.get("original_node_ids", [])),
            chapter_range=(int(cr[0]), int(cr[1])),
            legendary_form=data.get("legendary_form", ""),
            classification=data.get("classification", "folk_tale"),
            importance=int(data.get("importance", 5)),
        )


class SummaryTree:
    """N-ary tree that compresses section summaries into chapter / volume synopses."""

    def __init__(self, merge_threshold: int = 10) -> None:
        self._root = SummaryNode(node_id="root", level=99, summary="故事尚未开始。")
        self._leaves: list[SummaryNode] = []
        self._merge_threshold = merge_threshold
        self._pending_chapter_leaves: list[SummaryNode] = []
        self._legends: list[Legend] = []

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

    @property
    def legend_count(self) -> int:
        return len(self._legends)

    def get_legends(self) -> list[Legend]:
        return list(self._legends)

    async def add_section_summary(self, chapter: int, section: int, summary: str) -> None:
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
        # Include legends (L3) - 传说化已转为世界设定
        if self._legends:
            lines.append("\n【世界传说 / 民间故事】")
            for leg in self._legends:
                lines.append(f"  ({leg.classification}) {leg.legendary_form[:120]}…")
        return "\n".join(lines)

    def get_chapter_summaries(self, chapter: int) -> list[str]:
        return [n.summary for n in self._leaves if n.chapter_range[0] == chapter]

    # -- L3 传说化(MemoryCompressor 调用) ------------------------------------

    async def legendize(
        self,
        node_ids: list[str],
        classification: str = "folk_tale",
        importance: int = 5,
    ) -> Legend:
        """将旧的 L2 节点压缩为允许失真的 L3 传说。

        prompts.md 第 9 节: "转化为'世界传说'或'民间故事',允许引入合理失真
        (人名变体、夸张化、变成谚语),可能并存多个版本"。

        被传说化的源节点不会从树中移除 - MemoryCompressor 拿到 Legend 后,
        可选择是否调用 ``prune_nodes()`` 物理删除以释放 token 预算。
        """
        sources = self._find_nodes(node_ids)
        if not sources:
            raise ValueError(f"找不到任何指定 node_id: {node_ids}")

        combined = "\n".join(f"- [{n.node_id}] {n.summary}" for n in sources)
        ch_lo = min(n.chapter_range[0] for n in sources)
        ch_hi = max(n.chapter_range[1] for n in sources)

        try:
            resp = await llm_client.chat(
                system_prompt=(
                    "你是这个虚构世界的吟游诗人。请将以下历史事件转化为'世界传说'或"
                    "'民间故事'形式,允许引入合理失真:人名变体、夸张化、变成谚语。"
                    "可以使用'一种说法是...,另一种说法是...'的并存版本表述。"
                    "字数控制在 200 字以内,保留事件的核心情绪与道德启示。"
                ),
                user_prompt=combined,
                temperature=0.5,
                max_tokens=10240,
                agent_id="summary_tree:legendize",
                priority="optional",
            )
            legendary_form = resp.content.strip()
        except Exception as e:
            logger.error("Legendize LLM call failed: %s", e)
            # 兜底:简单截断 + 标签前缀,不阻塞 MemoryCompressor
            legendary_form = f"[传说] {combined[:180]}…"

        legend = Legend(
            legend_id=f"legend_{ch_lo}_{ch_hi}_{len(self._legends)}",
            original_node_ids=[n.node_id for n in sources],
            chapter_range=(ch_lo, ch_hi),
            legendary_form=legendary_form,
            classification=classification,
            importance=importance,
        )
        self._legends.append(legend)
        return legend

    def prune_nodes(self, node_ids: list[str]) -> int:
        """从 leaves/volumes 中物理删除指定节点(供 MemoryCompressor 释放预算)。

        ``legendize()`` 不会自动 prune - 调用方需在确认 Legend 安全持久化后
        显式调用,避免传说化失败时丢失原文。
        """
        targets = set(node_ids)
        removed = 0

        # 从 _leaves 移除
        new_leaves = [n for n in self._leaves if n.node_id not in targets]
        removed += len(self._leaves) - len(new_leaves)
        self._leaves = new_leaves

        # 从 _pending_chapter_leaves 移除
        new_pending = [n for n in self._pending_chapter_leaves if n.node_id not in targets]
        removed += len(self._pending_chapter_leaves) - len(new_pending)
        self._pending_chapter_leaves = new_pending

        # 从 _root.children (volumes) 移除
        new_children = [n for n in self._root.children if n.node_id not in targets]
        removed += len(self._root.children) - len(new_children)
        self._root.children = new_children

        return removed

    # -- 持久化(P0 bug 修复) -------------------------------------------------

    def persist_to_disk(self, path: str) -> None:
        """原子化写盘:先写 .tmp,再 os.replace,避免半截 JSON。"""
        payload = {
            "version": 1,
            "merge_threshold": self._merge_threshold,
            "root": self._root.to_dict(),
            "leaves": [n.to_dict() for n in self._leaves],
            "pending_chapter_leaves": [n.to_dict() for n in self._pending_chapter_leaves],
            "legends": [leg.to_dict() for leg in self._legends],
        }
        target_dir = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(target_dir, exist_ok=True)

        # tempfile.NamedTemporaryFile + os.replace 保证原子性
        fd, tmp_path = tempfile.mkstemp(
            prefix=".summary_tree_", suffix=".tmp.json", dir=target_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)
            logger.info(
                "SummaryTree persisted: %d leaves, %d volumes, %d legends → %s",
                len(self._leaves),
                len(self._root.children),
                len(self._legends),
                path,
            )
        except Exception:
            # 写盘失败 - 清理 tmp 文件再抛错
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    def load_from_disk(self, path: str) -> bool:
        """从磁盘恢复 - 返回是否成功加载。文件不存在不算错。"""
        if not os.path.isfile(path):
            logger.info("SummaryTree disk file not found, starting fresh: %s", path)
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error("SummaryTree load failed (%s) - starting fresh", e)
            return False

        try:
            self._merge_threshold = int(
                payload.get("merge_threshold", self._merge_threshold)
            )
            self._root = SummaryNode.from_dict(payload["root"])
            self._leaves = [SummaryNode.from_dict(n) for n in payload.get("leaves", [])]
            self._pending_chapter_leaves = [
                SummaryNode.from_dict(n)
                for n in payload.get("pending_chapter_leaves", [])
            ]
            self._legends = [Legend.from_dict(d) for d in payload.get("legends", [])]
        except (KeyError, TypeError, ValueError) as e:
            logger.error("SummaryTree payload corrupted (%s) - starting fresh", e)
            self.__init__(merge_threshold=self._merge_threshold)
            return False

        logger.info(
            "SummaryTree restored: %d leaves, %d volumes, %d legends from %s",
            len(self._leaves),
            len(self._root.children),
            len(self._legends),
            path,
        )
        return True

    # -- internals ------------------------------------------------------------

    def _find_nodes(self, node_ids: list[str]) -> list[SummaryNode]:
        """遍历整棵树查找节点 - 用于 legendize()。"""
        targets = set(node_ids)
        found: list[SummaryNode] = []

        def walk(node: SummaryNode) -> None:
            if node.node_id in targets:
                found.append(node)
            for child in node.children:
                walk(child)

        walk(self._root)
        for leaf in self._leaves:
            if leaf.node_id in targets and leaf not in found:
                found.append(leaf)
        for pending in self._pending_chapter_leaves:
            if pending.node_id in targets and pending not in found:
                found.append(pending)
        return found

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

    async def _compress(self, text: str, ch_start: int, ch_end: int) -> str:
        resp = await llm_client.chat(
            system_prompt=(
                "你是一位小说编辑。请将以下多段内容摘要压缩为一段简洁的"
                f"分卷梗概(第{ch_start}-{ch_end}章),保留关键情节转折和角色发展。"
                "字数控制在 200 字以内。"
            ),
            user_prompt=text,
            temperature=0.3,
            max_tokens=10240,
            agent_id="summary_tree:volume_compress",
            priority="optional",
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
                "你是一位小说编辑。请将以下各卷梗概合并为一段全书总纲摘要,"
                "字数控制在 300 字以内,保留主线和关键转折。"
            ),
            user_prompt=parts,
            temperature=0.3,
            max_tokens=10240,
            agent_id="summary_tree:root_compress",
            priority="optional",
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
