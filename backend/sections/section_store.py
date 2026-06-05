"""v2.24 — tick 驱动节存储。

落盘格式: ``{data_dir}/tick_sections.jsonl`` (append-only, 每行一个 TickSection)。

JSONL 优点:
* 续写完一节就 append, 不会破坏已有节 (与原子 replace 全文不同, 单行追加是原子的)
* 进程崩溃最多丢最近一节, 已落盘的节安全
* 前端按行流式读, 方便分页

设计要点
--------
* per-novel 单例: ``get_section_store(novel_id)`` 缓存 — 同一进程对同一 novel
  的多次请求共用一个 store; 跨 novel 独立, 与 TickRuntime 注册表语义对齐。
* 章节计数: load 时扫一遍 JSONL 取 max(chapter,section), 之后由 store 持有
  内存计数。**只追加, 不允许编辑历史节** — 避免与正在跑的 SectionTask
  竞态。

不存到 ticks.db (SQLite) 的理由
-------------------------------
ticks.db 是 tick_log + events 两表, 它的事务边界是"一个 tick" — 节是 N tick
的聚合, 与其语义错位。JSONL 是更朴素的 audit log, 也更友好给前端直接读取。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class TickSection(BaseModel):
    """tick 驱动节落盘契约。"""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    chapter: int = Field(ge=1)
    section: int = Field(ge=1)
    title: str = ""
    content: str = ""
    word_count: int = 0
    tick_start: int = Field(ge=0)
    tick_end: int = Field(ge=0)
    tick_count: int = 0
    silent_tick_count: int = 0
    closure_supplement: str = ""
    created_at: str = ""

    @staticmethod
    def now_iso() -> str:
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class SectionStore:
    """per-novel JSONL 后端。

    线程安全: append 用 threading.Lock 保护 (即使多个 asyncio.Task 同时写,
    底层 file write 也需要互斥)。
    """

    JSONL_NAME = "tick_sections.jsonl"

    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir
        self._path = os.path.join(data_dir, self.JSONL_NAME)
        self._lock = threading.Lock()
        self._chapter, self._section = self._scan_last_position()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    @property
    def jsonl_path(self) -> str:
        return self._path

    def next_position(self) -> tuple[int, int]:
        """给下一节分配 (chapter, section)。

        规则: 每 5 节切一章 (与 legacy showrunner 每 5 tick 切章的节奏对齐)。
        外部可在调用 append 之前手动 override (P3 可能需要)。
        """
        with self._lock:
            chapter, section = self._chapter, self._section
            if chapter == 0:
                # 第一节
                return 1, 1
            if section >= 5:
                return chapter + 1, 1
            return chapter, section + 1

    def append(self, section: TickSection) -> None:
        """追加一节到 JSONL。

        必须由调用方先用 next_position() 拿到合法位置 — append 会校验
        新位置严格大于已存在最大位置, 否则抛 ValueError。
        """
        with self._lock:
            self._ensure_dir()
            # 严格单调 — 防止 section_executor 误传旧位置覆盖
            if not self._is_strictly_after(section.chapter, section.section):
                raise ValueError(
                    f"section ({section.chapter}, {section.section}) 必须严格大于 "
                    f"已存在最大位置 ({self._chapter}, {self._section})"
                )
            line = section.model_dump_json() + "\n"
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
            self._chapter, self._section = section.chapter, section.section

    def list_all(self) -> list[TickSection]:
        """读全部节 — 按写入顺序, 等价于按 (chapter, section) 升序。"""
        if not os.path.isfile(self._path):
            return []
        out: list[TickSection] = []
        with self._lock:
            with open(self._path, encoding="utf-8") as f:
                for ln, raw in enumerate(f, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                        out.append(TickSection.model_validate(payload))
                    except Exception as e:
                        logger.warning(
                            "tick_sections.jsonl 第 %d 行解析失败 (跳过): %s", ln, e
                        )
        return out

    def get_last(self) -> TickSection | None:
        items = self.list_all()
        return items[-1] if items else None

    def count(self) -> int:
        if not os.path.isfile(self._path):
            return 0
        with self._lock:
            with open(self._path, encoding="utf-8") as f:
                return sum(1 for ln in f if ln.strip())

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _ensure_dir(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)

    def _scan_last_position(self) -> tuple[int, int]:
        """启动时扫一遍 JSONL, 取最大 (chapter, section)。

        损坏的行跳过 — 不让一个坏行阻塞整个续写流程。
        """
        if not os.path.isfile(self._path):
            return 0, 0
        max_chapter, max_section = 0, 0
        try:
            with open(self._path, encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                        c = int(payload.get("chapter", 0))
                        s = int(payload.get("section", 0))
                        if (c, s) > (max_chapter, max_section):
                            max_chapter, max_section = c, s
                    except Exception:
                        continue
        except OSError as e:
            logger.warning("无法读 tick_sections.jsonl (%s): %s — 视为空", self._path, e)
            return 0, 0
        return max_chapter, max_section

    def _is_strictly_after(self, chapter: int, section: int) -> bool:
        if self._chapter == 0:
            return chapter >= 1 and section >= 1
        return (chapter, section) > (self._chapter, self._section)


# ---- per-novel 单例 ---------------------------------------------------------


_stores: dict[str, SectionStore] = {}
_stores_lock = threading.Lock()


def get_section_store(novel_id: str, data_dir: str | None = None) -> SectionStore:
    """返回 (并按需创建) 一个 novel 的 SectionStore。

    ``data_dir`` 不传时, 由调用方保证 store 已被注册 — 这是避免 sections 模块
    硬依赖 tick_runtime 的折中。实际续写路径会传入 TickRuntime.data_dir。
    """
    with _stores_lock:
        if novel_id not in _stores:
            if data_dir is None:
                raise ValueError(
                    f"section store for {novel_id!r} 未注册, 首次调用必须传 data_dir"
                )
            _stores[novel_id] = SectionStore(data_dir=data_dir)
        return _stores[novel_id]


def _clear_for_tests() -> None:
    with _stores_lock:
        _stores.clear()
