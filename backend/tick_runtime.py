"""tick_runtime - 把 9 agent + TickState + TickDB 装配为单例 Orchestrator。

由 main.py 在 FastAPI startup 时调用,把生成的容器注入到 tick_routes.py 的全局
依赖容器。

设计要点:
* 单 novel_id 单 Orchestrator 实例(当前 backend 单小说运行模型)
* CharacterAgent 实例数随 TickState.character_profiles 增长
* tick_routes API 通过 set_orchestrator_dependencies() 拿到引用
* main.py FastAPI 启动事件触发 build_orchestrator(); 关闭事件触发 close()
"""

from __future__ import annotations

import logging
import os
from typing import Any

from agents.character_agent import CharacterAgent
from agents.consistency_guardian import ConsistencyGuardian
from agents.event_injector import EventInjector
from agents.memory_compressor import MemoryCompressor
from agents.narrator_agent import NarratorAgent
from agents.novelty_critic import NoveltyCritic
from agents.orchestrator import Orchestrator
from agents.showrunner import Showrunner
from agents.world_simulator import WorldSimulator
from api.tick_routes import set_orchestrator_dependencies
from memory.summary_tree import SummaryTree
from memory.tick_state import TickState
from nf_core.action_resolver import ActionResolver
from persistence.tick_db import TickDB

logger = logging.getLogger(__name__)


def _resolve_novel_data_dir(novel_id: str | None = None) -> str:
    """优先环境变量 ``ACTIVE_NOVEL_DATA_DIR``,否则 ``data/novels/<id>``。"""
    explicit = os.environ.get("ACTIVE_NOVEL_DATA_DIR", "").strip()
    if explicit:
        return os.path.abspath(explicit)
    nid = novel_id or os.environ.get("ACTIVE_NOVEL_ID", "default")
    base = os.path.join(os.path.dirname(__file__), "data", "novels", nid)
    return os.path.abspath(base)


class TickRuntime:
    """单例容器 - 装配 Orchestrator + 所有依赖,管理生命周期。"""

    def __init__(self, novel_id: str | None = None) -> None:
        self.novel_id = novel_id or os.environ.get("ACTIVE_NOVEL_ID", "default")
        self.data_dir = _resolve_novel_data_dir(self.novel_id)
        os.makedirs(self.data_dir, exist_ok=True)

        # 基础设施
        self.tick_state = TickState(data_dir=self.data_dir)
        self.tick_state.load()  # 静默 fall-through 到 fresh

        self.tick_db = TickDB(db_path=os.path.join(self.data_dir, "ticks.db"))
        self.summary_tree = SummaryTree(merge_threshold=10)
        self.summary_tree.load_from_disk(
            os.path.join(self.data_dir, "summary_tree.json")
        )

        # 9 agents
        self.world_simulator = WorldSimulator()
        self.narrator = NarratorAgent()
        self.event_injector = EventInjector()
        self.showrunner = Showrunner()
        self.memory_compressor = MemoryCompressor(summary_tree=self.summary_tree)
        self.consistency_guardian = ConsistencyGuardian()
        self.novelty_critic = NoveltyCritic()
        self.action_resolver = ActionResolver()

        # CharacterAgent 实例随 TickState 中已注册的 profile 自动构造
        self.character_agents: dict[str, CharacterAgent] = {}
        self._rebuild_character_agents()

        # Orchestrator 主调度器
        self.orchestrator = Orchestrator(
            tick_state=self.tick_state,
            world_simulator=self.world_simulator,
            character_agents=self.character_agents,
            narrator=self.narrator,
            action_resolver=self.action_resolver,
            showrunner=self.showrunner,
            event_injector=self.event_injector,
            memory_compressor=self.memory_compressor,
            consistency_guardian=self.consistency_guardian,
            novelty_critic=self.novelty_critic,
            tick_db=self.tick_db,
            main_tracking_character_id=os.environ.get("MAIN_TRACKING_CHARACTER_ID"),
        )

    def _rebuild_character_agents(self) -> None:
        """根据 TickState 中已注册的 profile 重建 CharacterAgent dict。"""
        self.character_agents.clear()
        for profile in self.tick_state.list_character_profiles():
            if profile.importance_tier == "C":
                # C 级仅标签,不实例化
                continue
            tier = "strong" if profile.importance_tier == "A" else "medium"
            self.character_agents[profile.id] = CharacterAgent(profile, model_tier=tier)
        logger.info(
            "Built %d CharacterAgent instances for novel '%s'",
            len(self.character_agents),
            self.novel_id,
        )

    def register_to_routes(self) -> None:
        """把本容器注入到 tick_routes.py 的全局依赖。"""
        set_orchestrator_dependencies(
            orchestrator=self.orchestrator,
            tick_state=self.tick_state,
            tick_db=self.tick_db,
        )

    def close(self) -> None:
        # 保存最终状态
        try:
            self.tick_state.save()
        except Exception as e:
            logger.error("Final TickState save failed: %s", e)
        try:
            self.summary_tree.persist_to_disk(
                os.path.join(self.data_dir, "summary_tree.json")
            )
        except Exception as e:
            logger.error("Final SummaryTree persist failed: %s", e)
        try:
            self.tick_db.close()
        except Exception as e:
            logger.error("TickDB close failed: %s", e)


# 模块级单例(惰性)
_runtime: TickRuntime | None = None


def get_runtime() -> TickRuntime:
    global _runtime
    if _runtime is None:
        _runtime = TickRuntime()
        _runtime.register_to_routes()
    return _runtime


def close_runtime() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.close()
        _runtime = None
