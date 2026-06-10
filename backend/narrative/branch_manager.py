"""BranchManager — 读者互动分支管理 (fork / switch / list / archive)。

针对主 Agent 关注问题清单的一项:
* **读者互动与分支处理的困境** — 读者在"选择点"做出不同选择时,
  系统能保留多条平行叙事线; 每条线持有独立的 tick_state + memory_store
  + fact_ledger + narratives, 互不污染

设计:
* **拷贝即分支** — fork(branch_id) 复制整个 data_dir 到子目录, 然后用
  独立 Orchestrator 实例继续推进; 不在内存中维护"多状态合一"的复杂图
* **明示选择点** — 每次 fork 必须给一个"分歧文本" (description) 与
  triggered_tick, 写入 branches.json 索引
* **可追溯** — fork 时记录 parent_branch_id, 形成树形结构供前端展示
* **可归档** — archive(branch_id) 把分支移出 active 集合但保留磁盘文件,
  供"对照阅读"使用
* **不强制 merge** — 不同分支语义上是平行宇宙, 不期待合并回主线;
  若用户决定"采用某分支为主", 通过 set_canonical(branch_id) 切换

非目标:
* 不实时同步 — 分支之间状态完全独立, 不做事件广播
* 不做合并冲突解决 — 平行宇宙概念下不需要
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BranchMeta:
    """单个分支的元数据。"""

    branch_id: str
    parent_branch_id: str = ""
    forked_at_tick: int = 0
    choice_description: str = ""
    choice_options: list[str] = field(default_factory=list)
    selected_option: str = ""
    archived: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BranchMeta":
        return cls(
            branch_id=str(data.get("branch_id", "")),
            parent_branch_id=str(data.get("parent_branch_id", "")),
            forked_at_tick=int(data.get("forked_at_tick", 0)),
            choice_description=str(data.get("choice_description", "")),
            choice_options=list(data.get("choice_options", []) or []),
            selected_option=str(data.get("selected_option", "")),
            archived=bool(data.get("archived", False)),
            notes=str(data.get("notes", "")),
        )


@dataclass
class BranchTreeNode:
    """供前端展示的树节点。"""

    meta: BranchMeta
    children: list["BranchTreeNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "meta": self.meta.to_dict(),
            "children": [c.to_dict() for c in self.children],
        }


# 不能拷贝的目录 / 文件 — 避免无谓膨胀
_SKIP_NAMES: frozenset[str] = frozenset({"branches", ".git", "__pycache__"})


class BranchManager:
    """读者分支管理。每个分支 = data_dir/branches/<branch_id>/。

    用法:
        bm = BranchManager(root_data_dir="/path/to/novels/my_novel")
        bm.load()  # 读取 branches.json
        # 在 tick 50 时, Narrator 输出后给读者两个选择
        new_branch = bm.fork(
            from_branch_id="main",
            new_branch_id="branch_a",
            forked_at_tick=50,
            choice_description="alice 在十字路口的选择",
            choice_options=["选择回家", "选择继续追查"],
            selected_option="选择回家",
        )
        # 之后 Orchestrator 用 new_branch.data_dir 实例化新的 TickState
    """

    INDEX_FILENAME = "branches.json"
    BRANCH_SUBDIR = "branches"

    def __init__(self, root_data_dir: str, *, canonical_branch_id: str = "main") -> None:
        self._root = os.path.abspath(root_data_dir)
        self._index_path = os.path.join(self._root, self.INDEX_FILENAME)
        self._branches_dir = os.path.join(self._root, self.BRANCH_SUBDIR)
        self._canonical = canonical_branch_id
        self._branches: dict[str, BranchMeta] = {}
        # main 分支视为根 (data_dir 即 root, 不在 branches/ 下)
        if self._canonical not in self._branches:
            self._branches[self._canonical] = BranchMeta(
                branch_id=self._canonical,
                forked_at_tick=0,
                choice_description="主线",
            )

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------

    @property
    def root_data_dir(self) -> str:
        return self._root

    @property
    def canonical_branch_id(self) -> str:
        return self._canonical

    def list_branches(self, *, include_archived: bool = False) -> list[BranchMeta]:
        out = []
        for m in self._branches.values():
            if not include_archived and m.archived:
                continue
            out.append(m)
        return sorted(out, key=lambda m: (m.forked_at_tick, m.branch_id))

    def get(self, branch_id: str) -> BranchMeta | None:
        return self._branches.get(branch_id)

    def data_dir_for(self, branch_id: str) -> str:
        if branch_id == self._canonical:
            return self._root
        return os.path.join(self._branches_dir, branch_id)

    # ------------------------------------------------------------------
    # 分支操作
    # ------------------------------------------------------------------

    def fork(
        self,
        *,
        from_branch_id: str,
        new_branch_id: str,
        forked_at_tick: int,
        choice_description: str,
        choice_options: list[str] | None = None,
        selected_option: str = "",
    ) -> BranchMeta:
        """从 from_branch_id 拷贝 data_dir 到 new_branch_id, 记录元数据。"""
        if new_branch_id in self._branches:
            raise ValueError(f"branch_id 已存在: {new_branch_id}")
        if from_branch_id not in self._branches:
            raise ValueError(f"父分支不存在: {from_branch_id}")
        src = self.data_dir_for(from_branch_id)
        if not os.path.isdir(src):
            raise FileNotFoundError(f"父分支 data_dir 不存在: {src}")

        dst = self.data_dir_for(new_branch_id)
        os.makedirs(self._branches_dir, exist_ok=True)
        if os.path.exists(dst):
            raise FileExistsError(f"目标 data_dir 已存在: {dst}")

        # 拷贝, 跳过 branches/ 与 .git/
        def _ignore(_root, names):
            return [n for n in names if n in _SKIP_NAMES]

        shutil.copytree(src, dst, ignore=_ignore)

        meta = BranchMeta(
            branch_id=new_branch_id,
            parent_branch_id=from_branch_id,
            forked_at_tick=forked_at_tick,
            choice_description=choice_description,
            choice_options=list(choice_options or []),
            selected_option=selected_option,
        )
        self._branches[new_branch_id] = meta
        self.save()
        return meta

    def archive(self, branch_id: str) -> bool:
        """归档分支 — 不从磁盘删除, 只在索引里标记 archived=True。

        save() 失败时回滚内存值再抛出, 保证内存与磁盘索引一致。
        """
        if branch_id == self._canonical:
            raise ValueError("不能归档 canonical 分支")
        meta = self._branches.get(branch_id)
        if meta is None:
            return False
        previous = meta.archived
        meta.archived = True
        try:
            self.save()
        except Exception:
            meta.archived = previous
            raise
        return True

    def unarchive(self, branch_id: str) -> bool:
        meta = self._branches.get(branch_id)
        if meta is None or not meta.archived:
            return False
        previous = meta.archived
        meta.archived = False
        try:
            self.save()
        except Exception:
            meta.archived = previous
            raise
        return True

    def set_canonical(self, branch_id: str) -> None:
        """切换 canonical 分支 — Orchestrator 启动时读取 canonical_branch_id。"""
        if branch_id not in self._branches:
            raise ValueError(f"branch_id 不存在: {branch_id}")
        self._canonical = branch_id
        self.save()

    def annotate(self, branch_id: str, notes: str) -> bool:
        meta = self._branches.get(branch_id)
        if meta is None:
            return False
        previous = meta.notes
        meta.notes = notes
        try:
            self.save()
        except Exception:
            meta.notes = previous
            raise
        return True

    # ------------------------------------------------------------------
    # 树形展示
    # ------------------------------------------------------------------

    def build_tree(self) -> BranchTreeNode | None:
        """以 canonical 为根, 拼成树形结构。归档分支也包含。"""
        if self._canonical not in self._branches:
            return None
        node_map: dict[str, BranchTreeNode] = {
            bid: BranchTreeNode(meta=m)
            for bid, m in self._branches.items()
        }
        root = node_map[self._canonical]
        for bid, meta in self._branches.items():
            if bid == self._canonical:
                continue
            parent_id = meta.parent_branch_id or self._canonical
            parent = node_map.get(parent_id)
            if parent is None:
                # 父节点丢失, 挂到 root
                root.children.append(node_map[bid])
            else:
                parent.children.append(node_map[bid])
        return root

    # ------------------------------------------------------------------
    # 索引持久化
    # ------------------------------------------------------------------

    def save(self) -> None:
        os.makedirs(self._root, exist_ok=True)
        payload = {
            "version": 1,
            "canonical_branch_id": self._canonical,
            "branches": [m.to_dict() for m in self._branches.values()],
        }
        fd, tmp = tempfile.mkstemp(
            prefix=".branches_", suffix=".tmp", dir=self._root
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._index_path)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def load(self) -> bool:
        if not os.path.exists(self._index_path):
            return False
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            logger.warning("BranchManager load failed: %s", e)
            return False
        self._canonical = str(payload.get("canonical_branch_id", "main")) or "main"
        self._branches.clear()
        for raw in payload.get("branches", []) or []:
            try:
                m = BranchMeta.from_dict(raw)
                self._branches[m.branch_id] = m
            except Exception as e:
                logger.warning("Skip invalid branch entry: %s", e)
        # 兜底 — 确保 canonical 存在
        if self._canonical not in self._branches:
            self._branches[self._canonical] = BranchMeta(
                branch_id=self._canonical, choice_description="主线"
            )
        return True


__all__ = [
    "BranchManager",
    "BranchMeta",
    "BranchTreeNode",
]
