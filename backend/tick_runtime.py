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
import threading
from collections.abc import Callable

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
            # v2.36 — orchestrator 每 tick 持久化 summary_tree / branch_manager,
            # 让 drop / cleanup / 进程崩失场景不再丢 MemoryCompressor 累积的 leaves
            # 和 branch 元数据。
            summary_tree=self.summary_tree,
            branch_manager=self.branch_manager,
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
# 注册表互斥锁 — 串行化 _runtimes / _active_by_user 的 check-then-set 模式,
# 防止两个并发 get_runtime 同时通过 `if key not in _runtimes` 后各自构造一份
# TickRuntime, 第二份覆盖第一份留下被孤立的 SQLite 连接 (Windows: WAL 互锁).
# 锁内允许做 TickRuntime() 构造 (秒级), 因为这是低频操作; 高频路径 (tick run)
# 拿到 rt 引用后就不再持锁。
_registry_lock = threading.RLock()
# tick_routes 容器最后一次注入的 (user_id, novel_id) — 仅供诊断
_last_injected: tuple[str, str] | None = None


def get_runtime(user_id: str, novel_id: str | None = None) -> TickRuntime:
    """按需取/建 (user_id, novel_id) → TickRuntime。

    * ``novel_id=None``: 用该用户活跃 novel; 若没有则 resolve_default_novel_id
      (会必要时新建 "未命名小说")。
    * 第一次为某用户构造时, 自动设为活跃并注入到 tick_routes 容器。

    v2.37 — active 指针读取 + default 解析全部移进 _registry_lock: 此前在锁外
    读 ``_active_by_user`` (TOCTOU), 两个并发请求可能 resolve 出不同 nid 各自
    构造 runtime, 先建的一份被活跃指针抛弃但 SQLite 句柄仍开着。已存在的
    runtime 不重复构造 (单次 dict 查找)。锁内做 resolve/构造与既有约定一致
    (低频操作, 见 _registry_lock 注释)。
    """
    with _registry_lock:
        nid = novel_id or _active_by_user.get(user_id)
        if nid is None:
            nid = novel_manager.resolve_default_novel_id(user_id)
        key = (user_id, nid)
        rt = _runtimes.get(key)
        if rt is None:
            rt = TickRuntime(user_id=user_id, novel_id=nid)
            _runtimes[key] = rt
        if user_id not in _active_by_user:
            set_active_novel(user_id, nid)  # RLock — 嵌套获取安全
        return rt


def set_active_novel(user_id: str, novel_id: str) -> TickRuntime:
    """切换活跃 runtime; 必要时按需构造, 并立即注入 tick_routes 容器。"""
    global _last_injected
    if not isinstance(novel_id, str) or not novel_id:
        raise ValueError(f"invalid novel_id for set_active_novel: {novel_id!r}")
    key = (user_id, novel_id)
    with _registry_lock:
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


def switch_active_novel(
    user_id: str,
    novel_id: str,
    on_switched: Callable[[], None] | None = None,
) -> TickRuntime:
    """v2.37 — 在 ``_registry_lock`` 内完成 set_active_novel + 调用方回调。

    routes.switch_novel 需要在 tick 侧切换后同步它自己的 per-user active map;
    两步在锁外做, 并发 switch 请求会交错出 tick=B / legacy=A 的状态分歧。
    回调在锁内执行 — 必须保持轻量 (dict 赋值级别), 不要做 I/O。
    """
    with _registry_lock:
        rt = set_active_novel(user_id, novel_id)
        if on_switched is not None:
            on_switched()
        return rt


def get_active_runtime(user_id: str) -> TickRuntime | None:
    with _registry_lock:
        nid = _active_by_user.get(user_id)
        if nid is None:
            return None
        return _runtimes.get((user_id, nid))


def get_active_novel_id(user_id: str) -> str | None:
    with _registry_lock:
        return _active_by_user.get(user_id)


def reload_cache(user_id: str, novel_id: str) -> None:
    """丢弃缓存 → 释放 SQLite 文件锁 → (若 active) 重新构造以从盘载入新状态。

    用于 ``bootstrap_routes._reload_runtime`` 等"外部刚直写盘, 让缓存重读"场景。

    # 不会 save in-memory 状态

    保证: cached runtime 持有的 in-memory state 在外部直写盘场景下通常是空 / 过时
    的; 直接 save 会原子覆盖盘上新数据 (bootstrap 链路曾因此丢失整套世界设定 +
    5 角色 + 5 伏笔 + 4 风格锚点)。

    每 tick 已经 save 了 TickState / MemoryStore / FactLedger / TokenBudget /
    KnowledgeGraph; SummaryTree / BranchManager 也在 orchestrator 末尾 save (v2.36).
    因此丢弃缓存不会丢失数据。

    重建失败时 (盘上 JSON 损坏等), 清掉 ``_active_by_user[user_id]`` 让调用方 fail
    cleanly, 而非保留孤儿指针让 ``get_active_runtime`` 静默返回 None。
    """
    key = (user_id, novel_id)
    with _registry_lock:
        rt = _runtimes.pop(key, None)
        if rt is not None:
            try:
                rt.tick_db.close()
            except Exception as e:
                logger.warning("reload_cache tick_db.close failed for %s: %s", key, e)
        # 若它是该用户的 active, 重新构造以保证后续请求拿到新 state
        if _active_by_user.get(user_id) == novel_id:
            try:
                set_active_novel(user_id, novel_id)
            except Exception as e:
                logger.error(
                    "reload_cache rebuild failed for %s: %s — clearing _active_by_user "
                    "to avoid orphan pointer; next get_runtime will retry.",
                    key, e,
                )
                _active_by_user.pop(user_id, None)


def drop_cache(user_id: str, novel_id: str) -> None:
    """纯丢弃缓存, 不重建 — 用于 ``cleanup_task`` 等"紧接 delete_novel 删整个目录"场景。

    与 ``reload_cache`` 的区别: 不调 ``set_active_novel`` 重建。重建会重新打开
    ticks.db (Windows: 文件锁), 紧跟其后的 ``shutil.rmtree`` 会因被占用而失败,
    ``ignore_errors=True`` 又会静默吞掉报错, 留下孤儿目录 + 已开 SQLite 句柄。

    顺手清掉 ``_active_by_user[user_id]`` (若指向本 novel), 防止之后 get_runtime
    用同一 novel_id 访问已删除目录。
    """
    key = (user_id, novel_id)
    with _registry_lock:
        rt = _runtimes.pop(key, None)
        if rt is not None:
            try:
                rt.tick_db.close()
            except Exception as e:
                logger.warning("drop_cache tick_db.close failed for %s: %s", key, e)
        if _active_by_user.get(user_id) == novel_id:
            _active_by_user.pop(user_id, None)


# 兼容旧名 — 等同 reload_cache (原 drop_runtime 的语义)
def drop_runtime(user_id: str, novel_id: str) -> None:
    """Deprecated 别名 — 转发到 ``reload_cache``。新代码请用 ``reload_cache`` /
    ``drop_cache`` 显式表达意图 (见 v2.36)。"""
    reload_cache(user_id, novel_id)


def close_all_runtimes(persist: bool = False) -> None:
    """FastAPI shutdown 钩子用 — 关闭所有 runtime, 清空注册表。

    ``persist=False`` (默认): 仅 ``tick_db.close()`` 释放 SQLite 句柄, 不 save
    其他 in-memory state — 因为 orchestrator 每 tick 已经持久化全部 7 个子系统
    (tick_state / memory_store / fact_ledger / token_budget / knowledge_graph /
    summary_tree / branch_manager, 见 v2.36), shutdown 时再 save 是多余且危险
    (若有外部进程在 bootstrap 阶段直写盘, save 会用 stale in-memory 覆盖).

    ``persist=True``: 与旧行为兼容, 显式调用 ``rt.close()`` 全 8 项 save —
    仅用于明确知道无外部写入的离线工具.
    """
    with _registry_lock:
        for key, rt in list(_runtimes.items()):
            try:
                if persist:
                    rt.close()
                else:
                    rt.tick_db.close()
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
