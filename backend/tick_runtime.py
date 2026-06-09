"""tick_runtime — (user_id, novel_id) → Orchestrator 实例注册表。

v2.26 多租户改造
----------------
* 注册表 key 从 ``novel_id`` 改为 ``(user_id, novel_id)`` — A 用户的 mountain
  和 B 用户的 mountain 是两个独立 runtime。
* 活跃指针 ``_active_by_user: dict[user_id, novel_id]`` — 每用户独立活跃小说。
  ``set_active_novel(user_id, novel_id)`` 切换。
* 数据目录走 ``novel_manager.get_novel_data_dir(user_id, novel_id)``,
  realpath 必须落在 ``data/users/{user_id}/novels/`` 之下。
* tick_routes 是无状态的; 它通过 ``set_orchestrator_dependencies(orch, state, db)``
  接收当前请求活跃 runtime 的引用 — 由 ``set_active_novel`` 或显式 ``activate``
  调用注入。多请求并发时, 注入的总是"最后一次 activate 的", 这是已知限制
  (单租户时代留下)。

向后兼容
--------
保留 ``close_runtime()`` / ``close_all_runtimes()`` 旧 API。
``_clear_for_tests()`` 测试钩子保留。
"""
from __future__ import annotations

import logging
import os

import novel_manager
from agents.character_agent import CharacterAgent
from agents.character_arc_tracker import CharacterArcTracker
from agents.consistency_guardian import ConsistencyGuardian
from agents.event_injector import EventInjector
from agents.memory_compressor import MemoryCompressor
from agents.narrator_agent import NarratorAgent
from agents.novelty_critic import NoveltyCritic
from agents.orchestrator import Orchestrator
from agents.showrunner import Showrunner
from agents.story_arc_director import StoryArcDirector
from agents.world_simulator import WorldSimulator
from graph.knowledge_graph import KnowledgeGraph
from graph.tick_kg_sync import sync_tick_state_to_kg
from memory.memory_store import PriorityMemoryStore
from memory.summary_tree import SummaryTree
from memory.tick_state import TickState
from narrative.branch_manager import BranchManager
from narrative.creativity_scorer import CreativityScorer
from narrative.fact_ledger import FactLedger
from narrative.safety_filter import SafetyFilter
from nf_core.action_resolver import ActionResolver
from nf_core.token_budget import TokenBudgetTracker
from persistence.tick_db import TickDB

logger = logging.getLogger(__name__)


class TickRuntime:
    """单 (user_id, novel_id) → 一组 9 agent + state + db 的装配容器。"""

    def __init__(self, user_id: str, novel_id: str) -> None:
        self.user_id = user_id
        self.novel_id = novel_id
        # get_novel_data_dir 内部已做 realpath 沙箱校验
        self.data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
        os.makedirs(self.data_dir, exist_ok=True)

        # 基础设施
        self.tick_state = TickState(data_dir=self.data_dir)
        self.tick_state.load()
        # v2.34 — 把 novel_manager 里的最新标题强同步到 TickState, 修正:
        # (a) 老 tick_state.json 没 novel_title 字段; (b) 用户 PUT 改名时
        # 该 runtime 已 close 过, 下一次构造时拿到的是磁盘上旧版。
        try:
            novel = novel_manager.get_novel(user_id, novel_id)
            current_title = (novel.get("title") if novel else "") or ""
            if current_title and current_title != self.tick_state.novel_title:
                self.tick_state.set_novel_title(current_title)
        except Exception as e:
            logger.warning("seed novel_title from novel_manager failed: %s", e)

        self.tick_db = TickDB(db_path=os.path.join(self.data_dir, "ticks.db"))
        self.summary_tree = SummaryTree(merge_threshold=10)
        self.summary_tree.load_from_disk(
            os.path.join(self.data_dir, "summary_tree.json")
        )

        # v2.34 — 知识图谱: tick 架构在 _run_tick_unlocked 末尾自动同步。
        # snapshot_dir 用 per-novel 路径, 与 config.json 的全局 graph_snapshot_dir
        # 解耦, 避免多 novel 写到同一目录互相覆盖。
        self.kg_path = os.path.join(self.data_dir, "knowledge_graph.json")
        self.knowledge_graph = KnowledgeGraph(
            snapshot_dir=os.path.join(self.data_dir, "snapshots")
        )
        self.knowledge_graph.load_from_disk(self.kg_path)
        # 首次启动 (或上轮 KG 空) 时, 立即从当前 tick_state 灌一次种子图,
        # 让用户即便还没跑 tick 就能在前端看到 bootstrap 出来的角色/地点/势力。
        try:
            sync_tick_state_to_kg(
                self.knowledge_graph, self.tick_state, tick_events=None
            )
        except Exception as e:
            logger.warning("initial KG seed failed (non-fatal): %s", e)

        # 9 agents
        self.world_simulator = WorldSimulator()
        self.narrator = NarratorAgent()
        self.event_injector = EventInjector()
        self.showrunner = Showrunner()
        self.memory_compressor = MemoryCompressor(summary_tree=self.summary_tree)
        self.consistency_guardian = ConsistencyGuardian()
        self.novelty_critic = NoveltyCritic()
        self.action_resolver = ActionResolver()

        # 增强层
        self.memory_store = PriorityMemoryStore(data_dir=self.data_dir)
        self.memory_store.load()
        self.story_arc_director = StoryArcDirector()
        self.character_arc_tracker = CharacterArcTracker()
        self.fact_ledger = FactLedger(data_dir=self.data_dir)
        self.fact_ledger.load()
        self.safety_filter = SafetyFilter()
        self.token_budget = TokenBudgetTracker(data_dir=self.data_dir)
        self.token_budget.load()
        self.creativity_scorer = CreativityScorer()
        self.branch_manager = BranchManager(root_data_dir=self.data_dir)
        self.branch_manager.load()

        # CharacterAgent 实例
        self.character_agents: dict[str, CharacterAgent] = {}
        self._rebuild_character_agents()

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
            memory_store=self.memory_store,
            story_arc_director=self.story_arc_director,
            character_arc_tracker=self.character_arc_tracker,
            fact_ledger=self.fact_ledger,
            safety_filter=self.safety_filter,
            token_budget=self.token_budget,
            creativity_scorer=self.creativity_scorer,
            knowledge_graph=self.knowledge_graph,
            knowledge_graph_path=self.kg_path,
        )

    def _rebuild_character_agents(self) -> None:
        self.character_agents.clear()
        for profile in self.tick_state.list_character_profiles():
            if profile.importance_tier == "C":
                continue
            tier = "strong" if profile.importance_tier == "A" else "medium"
            self.character_agents[profile.id] = CharacterAgent(profile, model_tier=tier)
        logger.info(
            "Built %d CharacterAgent instances for (user=%s, novel=%s)",
            len(self.character_agents), self.user_id, self.novel_id,
        )

    def register_to_routes(self) -> None:
        """v2.26 no-op shim — tick_routes 改走 Depends 直接解析当前用户 runtime,
        不再用全局容器。保留方法签名兼容老调用方。"""
        return None

    def close(self) -> None:
        for name, fn in [
            ("TickState", self.tick_state.save),
            (
                "SummaryTree",
                lambda: self.summary_tree.persist_to_disk(
                    os.path.join(self.data_dir, "summary_tree.json")
                ),
            ),
            ("MemoryStore", self.memory_store.save),
            ("FactLedger", self.fact_ledger.save),
            ("TokenBudgetTracker", self.token_budget.save),
            ("BranchManager", self.branch_manager.save),
            (
                "KnowledgeGraph",
                lambda: self.knowledge_graph.save_to_disk(self.kg_path),
            ),
            ("TickDB", self.tick_db.close),
        ]:
            try:
                fn()
            except Exception as e:
                logger.error("Final %s persist failed: %s", name, e)


# ----- 全局注册表 ----------------------------------------------------------
_runtimes: dict[tuple[str, str], TickRuntime] = {}
_active_by_user: dict[str, str] = {}
# tick_routes 容器最后一次注入的 (user_id, novel_id) — 仅供诊断
_last_injected: tuple[str, str] | None = None


def get_runtime(user_id: str, novel_id: str | None = None) -> TickRuntime:
    """按需取/建 (user_id, novel_id) → TickRuntime。

    * ``novel_id=None``: 用该用户活跃 novel; 若没有则 resolve_default_novel_id
      (会必要时新建 "未命名小说")。
    * 第一次为某用户构造时, 自动设为活跃并注入到 tick_routes 容器。
    """
    nid = novel_id or _active_by_user.get(user_id)
    if nid is None:
        nid = novel_manager.resolve_default_novel_id(user_id)
    key = (user_id, nid)
    if key not in _runtimes:
        _runtimes[key] = TickRuntime(user_id=user_id, novel_id=nid)
    if user_id not in _active_by_user:
        set_active_novel(user_id, nid)
    return _runtimes[key]


def set_active_novel(user_id: str, novel_id: str) -> TickRuntime:
    """切换活跃 runtime; 必要时按需构造, 并立即注入 tick_routes 容器。"""
    global _last_injected
    if not isinstance(novel_id, str) or not novel_id:
        raise ValueError(f"invalid novel_id for set_active_novel: {novel_id!r}")
    key = (user_id, novel_id)
    if key not in _runtimes:
        _runtimes[key] = TickRuntime(user_id=user_id, novel_id=novel_id)
    _active_by_user[user_id] = novel_id
    _runtimes[key].register_to_routes()
    _last_injected = key
    logger.info(
        "Active novel switched: user=%s novel=%s (%d runtimes loaded)",
        user_id, novel_id, len(_runtimes),
    )
    return _runtimes[key]


def get_active_runtime(user_id: str) -> TickRuntime | None:
    nid = _active_by_user.get(user_id)
    if nid is None:
        return None
    return _runtimes.get((user_id, nid))


def get_active_novel_id(user_id: str) -> str | None:
    return _active_by_user.get(user_id)


def drop_runtime(user_id: str, novel_id: str) -> None:
    """从注册表中丢弃指定 runtime, 让下次 get_runtime 重新从盘载入。

    # 不会 save in-memory 状态

    两个调用方都需要"纯丢弃缓存"语义:

    1. ``bootstrap_routes._reload_runtime`` — bootstrap_world 把整套 TickState /
       SummaryTree / KnowledgeGraph 直写盘后调用, 目的是让 cached runtime 重读;
       若此处 save, 会用 bootstrap 之前缓存的空 (or stale) in-memory 状态原子
       覆盖盘上的 bootstrap 数据 — 世界设定 / 角色 / 伏笔 / 风格锚点全部丢失,
       Narrator 上场只能瞎写。

    2. ``cleanup_task`` — 24h ephemeral 过期清理, 紧接 ``delete_novel`` 删整个
       目录, save 是浪费 IO。

    只调 ``tick_db.close()`` 释放 SQLite 文件锁 — Windows 上不关连接会卡住
    后续目录删除 / 文件 rename。
    """
    key = (user_id, novel_id)
    rt = _runtimes.pop(key, None)
    if rt is not None:
        try:
            rt.tick_db.close()
        except Exception as e:
            logger.warning("drop_runtime tick_db.close failed for %s: %s", key, e)
    # 若它是该用户的 active, 重新构造以保证后续请求拿到新 state
    if _active_by_user.get(user_id) == novel_id:
        try:
            set_active_novel(user_id, novel_id)
        except Exception as e:
            logger.warning("re-set_active_novel %s failed: %s", key, e)


def close_all_runtimes() -> None:
    """FastAPI shutdown 钩子用 — 关闭所有, 清空注册表。"""
    for key, rt in list(_runtimes.items()):
        try:
            rt.close()
        except Exception as e:
            logger.error("close runtime %s failed: %s", key, e)
    _runtimes.clear()
    _active_by_user.clear()


# ----- 向后兼容外壳 -------------------------------------------------------
def close_runtime() -> None:
    """旧别名 — 仍调 close_all_runtimes。"""
    close_all_runtimes()


def _clear_for_tests() -> None:
    global _last_injected
    _runtimes.clear()
    _active_by_user.clear()
    _last_injected = None
