"""TickState - tick 架构持久化容器。

承载 Orchestrator 在 tick 之间需要跨进程恢复的全部最小状态:

* tick 计数 + 世界时间
* WorldState (角色/势力/天气/规则)
* CharacterProfile + CharacterState (按 id 索引)
* OpenLoop 列表(Showrunner 监控、自动过期)
* StyleAnchor 仓库(Narrator 取 top-k 注入 system_prompt)
* 各事件类型最后发生的 tick(EventInjector 触发判断)
* NoveltyCritic 输出的重复模式警告

存储方式: 单 JSON 文件 ``{data_dir}/tick_state.json``,Pydantic 直接 dump/validate,
原子写(``tempfile.mkstemp`` + ``os.replace``)。

不存储:
* 章节文本 - 由 GenerationPipeline 写入 ``state.json``
* 知识图谱 - 由 KnowledgeGraph 写入 ``snapshots/``
* tick 日志 - 由 TickDB(SQLite) 持有
* 长期向量记忆 - ChromaDB 独立持久化
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Iterable

from memory_system.models import (
    CharacterProfile,
    CharacterState,
    OpenLoop,
    StyleAnchor,
    WorldState,
)

logger = logging.getLogger(__name__)

STATE_FILENAME = "tick_state.json"


class TickState:
    """Mutable tick state with atomic JSON persistence.

    实例化时 ``data_dir`` 必须为绝对路径,通常为
    ``backend/data/novels/{novel_id}/``。
    """

    def __init__(self, data_dir: str) -> None:
        self._data_dir = os.path.abspath(data_dir)
        os.makedirs(self._data_dir, exist_ok=True)
        self._path = os.path.join(self._data_dir, STATE_FILENAME)

        # 核心 tick 计数
        self._current_tick: int = 0
        self._world_state: WorldState = WorldState()

        # 角色档案与状态(by id)
        self._character_profiles: dict[str, CharacterProfile] = {}
        self._character_states: dict[str, CharacterState] = {}

        # 张力池
        self._open_loops: dict[str, OpenLoop] = {}

        # 风格锚点(按 weight 降序排列)
        self._style_anchors: list[StyleAnchor] = []

        # EventInjector / Narrator 调度参考
        self._last_event_tick_by_type: dict[str, int] = {}
        self._last_narration_tick: int = 0

        # NoveltyCritic 输出的反馈,供 Narrator/EventInjector 下次调用参考
        self._novelty_warnings: list[str] = []

    # ------------------------------------------------------------------
    # 只读属性
    # ------------------------------------------------------------------

    @property
    def current_tick(self) -> int:
        return self._current_tick

    @property
    def world_time(self) -> int:
        return self._world_state.world_time

    @property
    def world_state(self) -> WorldState:
        return self._world_state

    @property
    def last_narration_tick(self) -> int:
        return self._last_narration_tick

    @property
    def data_dir(self) -> str:
        return self._data_dir

    # ------------------------------------------------------------------
    # tick 推进
    # ------------------------------------------------------------------

    def advance_tick(self) -> int:
        """推进 tick 计数,返回新 tick 编号。Orchestrator 每 tick 调用一次。"""
        self._current_tick += 1
        return self._current_tick

    def set_world_state(self, ws: WorldState) -> None:
        self._world_state = ws

    def mark_narration(self, tick: int) -> None:
        self._last_narration_tick = tick

    # ------------------------------------------------------------------
    # 角色档案 / 状态
    # ------------------------------------------------------------------

    def upsert_character_profile(self, profile: CharacterProfile) -> None:
        self._character_profiles[profile.id] = profile

    def upsert_character_state(self, state: CharacterState) -> None:
        self._character_states[state.character_id] = state

    def get_character_profile(self, character_id: str) -> CharacterProfile | None:
        return self._character_profiles.get(character_id)

    def get_character_state(self, character_id: str) -> CharacterState | None:
        return self._character_states.get(character_id)

    def list_character_profiles(
        self, tiers: Iterable[str] | None = None
    ) -> list[CharacterProfile]:
        if tiers is None:
            return list(self._character_profiles.values())
        tier_set = set(tiers)
        return [p for p in self._character_profiles.values() if p.importance_tier in tier_set]

    def list_character_states(self) -> list[CharacterState]:
        return list(self._character_states.values())

    def get_arc_status(self) -> dict[str, float]:
        """供 Showrunner 监控 - 仅 A/B 级角色的 arc_progress。"""
        out: dict[str, float] = {}
        for cid, state in self._character_states.items():
            profile = self._character_profiles.get(cid)
            if profile is None or profile.importance_tier == "C":
                continue
            out[cid] = state.arc_progress
        return out

    def update_arc_progress(self, character_id: str, progress: float) -> None:
        st = self._character_states.get(character_id)
        if st is None:
            return
        clamped = max(0.0, min(1.0, progress))
        # Pydantic v2: model_copy with update
        self._character_states[character_id] = st.model_copy(
            update={"arc_progress": clamped}
        )

    # ------------------------------------------------------------------
    # OpenLoop 张力池(自动过期保护)
    # ------------------------------------------------------------------

    def add_open_loop(self, loop: OpenLoop) -> None:
        self._open_loops[loop.id] = loop

    def close_open_loop(self, loop_id: str) -> OpenLoop | None:
        return self._open_loops.pop(loop_id, None)

    def get_open_loops(
        self,
        min_urgency: int = 0,
        top_k: int | None = None,
    ) -> list[OpenLoop]:
        """按 urgency 降序返回。``top_k`` 用于限制 Narrator prompt 大小。"""
        loops = [l for l in self._open_loops.values() if l.urgency >= min_urgency]
        loops.sort(key=lambda l: (-l.urgency, l.opened_tick))
        if top_k is not None:
            loops = loops[:top_k]
        return loops

    def get_open_loop_count(self) -> int:
        return len(self._open_loops)

    def reap_stale_open_loops(self, current_tick: int) -> list[str]:
        """强制关闭超过 ``max_age_ticks`` 未消费的 loops,防数量失控。"""
        stale_ids = [
            l.id
            for l in self._open_loops.values()
            if current_tick - l.opened_tick > l.max_age_ticks
        ]
        for loop_id in stale_ids:
            self._open_loops.pop(loop_id, None)
        if stale_ids:
            logger.info("Reaped %d stale OpenLoops at tick %d", len(stale_ids), current_tick)
        return stale_ids

    def touch_open_loop(self, loop_id: str, tick: int) -> None:
        """Narrator 引用某 loop 时调用,更新 last_referenced_tick(冷线索检测)。"""
        loop = self._open_loops.get(loop_id)
        if loop is None:
            return
        self._open_loops[loop_id] = loop.model_copy(
            update={"last_referenced_tick": tick}
        )

    # ------------------------------------------------------------------
    # StyleAnchor(Narrator 取 top-k)
    # ------------------------------------------------------------------

    def add_style_anchor(self, anchor: StyleAnchor) -> None:
        self._style_anchors.append(anchor)
        # 按 weight 降序排序,保证 get_style_anchors(top_k) 直接 slice
        self._style_anchors.sort(key=lambda a: -a.weight)

    def get_style_anchors(self, top_k: int = 5) -> list[StyleAnchor]:
        return self._style_anchors[:top_k]

    def list_style_anchors(self) -> list[StyleAnchor]:
        return list(self._style_anchors)

    # ------------------------------------------------------------------
    # EventInjector / Narrator 调度参考
    # ------------------------------------------------------------------

    def record_last_event_tick(self, event_type: str, tick: int) -> None:
        self._last_event_tick_by_type[event_type] = tick

    def ticks_since_last_event(self, event_type: str, current_tick: int) -> int:
        last = self._last_event_tick_by_type.get(event_type)
        if last is None:
            return current_tick + 1  # 视为从未发生过
        return current_tick - last

    def set_novelty_warnings(self, warnings: list[str]) -> None:
        self._novelty_warnings = list(warnings)

    def get_novelty_warnings(self) -> list[str]:
        return list(self._novelty_warnings)

    # ------------------------------------------------------------------
    # 持久化(原子写)
    # ------------------------------------------------------------------

    def save(self) -> None:
        payload = {
            "version": 1,
            "current_tick": self._current_tick,
            "last_narration_tick": self._last_narration_tick,
            "world_state": self._world_state.model_dump(mode="json"),
            "character_profiles": {
                cid: p.model_dump(mode="json")
                for cid, p in self._character_profiles.items()
            },
            "character_states": {
                cid: s.model_dump(mode="json")
                for cid, s in self._character_states.items()
            },
            "open_loops": {
                lid: l.model_dump(mode="json") for lid, l in self._open_loops.items()
            },
            "style_anchors": [a.model_dump(mode="json") for a in self._style_anchors],
            "last_event_tick_by_type": dict(self._last_event_tick_by_type),
            "novelty_warnings": list(self._novelty_warnings),
        }

        fd, tmp_path = tempfile.mkstemp(
            prefix=".tick_state_", suffix=".tmp.json", dir=self._data_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
            logger.debug(
                "TickState saved: tick=%d open_loops=%d chars=%d",
                self._current_tick,
                len(self._open_loops),
                len(self._character_states),
            )
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    def load(self) -> bool:
        if not os.path.isfile(self._path):
            logger.info("TickState file not found, starting fresh: %s", self._path)
            return False

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error("TickState load failed (%s) - starting fresh", e)
            return False

        try:
            self._current_tick = int(payload.get("current_tick", 0))
            self._last_narration_tick = int(payload.get("last_narration_tick", 0))
            self._world_state = WorldState.model_validate(
                payload.get("world_state", {})
            )
            self._character_profiles = {
                cid: CharacterProfile.model_validate(data)
                for cid, data in payload.get("character_profiles", {}).items()
            }
            self._character_states = {
                cid: CharacterState.model_validate(data)
                for cid, data in payload.get("character_states", {}).items()
            }
            self._open_loops = {
                lid: OpenLoop.model_validate(data)
                for lid, data in payload.get("open_loops", {}).items()
            }
            self._style_anchors = [
                StyleAnchor.model_validate(a)
                for a in payload.get("style_anchors", [])
            ]
            self._style_anchors.sort(key=lambda a: -a.weight)
            self._last_event_tick_by_type = {
                k: int(v) for k, v in payload.get("last_event_tick_by_type", {}).items()
            }
            self._novelty_warnings = list(payload.get("novelty_warnings", []))
        except Exception as e:
            logger.error(
                "TickState payload validation failed (%s) - starting fresh", e
            )
            # 重置为干净状态,避免半截数据污染下游
            self.__init__(self._data_dir)
            return False

        logger.info(
            "TickState restored: tick=%d open_loops=%d chars=%d anchors=%d",
            self._current_tick,
            len(self._open_loops),
            len(self._character_states),
            len(self._style_anchors),
        )
        return True
