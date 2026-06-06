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
from api.tick_routes import set_orchestrator_dependencies
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


# v2.17 — backend/data/novels/ 是所有 runtime 数据目录的合法根。
# 解析后的目录必须 realpath 落在此根下, 否则视为越界并拒绝。这里用 realpath + commonpath
# 是 CodeQL 认可的 path-injection sanitizer 模式。
_NOVELS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "novels"))


def _sanitize_within_novels_root(candidate: str) -> str:
    """强校验 candidate 必须落在 _NOVELS_ROOT 之下, 否则抛 ValueError。

    用 realpath 解掉 symlink/相对路径混淆, 用 commonpath 严格比较 — 这是 CodeQL
    py/path-injection 检查器识别的标准 sanitizer。
    """
    real_target = os.path.realpath(candidate)
    real_root = os.path.realpath(_NOVELS_ROOT)
    try:
        common = os.path.commonpath([real_target, real_root])
    except ValueError:
        raise ValueError(f"path outside novels root: {candidate!r}") from None
    if common != real_root:
        raise ValueError(f"path outside novels root: {candidate!r}")
    return real_target


def _resolve_novel_data_dir(novel_id: str | None = None) -> str:
    """解析数据目录, 强制落在 backend/data/novels/ 之下。

    * ``novel_id=None`` 走向后兼容的"启动默认"路径:
      优先 ``ACTIVE_NOVEL_DATA_DIR``, 否则 ``ACTIVE_NOVEL_ID`` → ``data/novels/<id>``。
    * 显式传 ``novel_id`` (v2.15 多 runtime 模式) 则总是 ``data/novels/<novel_id>``,
      不接受 ``ACTIVE_NOVEL_DATA_DIR`` 覆盖 — 否则注册表多个 runtime 会指向同一目录,
      产生并发写盘冲突。
    * v2.17 — 所有来源(env var、调用方 novel_id)都经 _sanitize_within_novels_root
      二次校验, 切断 path-injection 污点流到 os.makedirs / sqlite3.connect。
    """
    if novel_id is None:
        explicit = os.environ.get("ACTIVE_NOVEL_DATA_DIR", "").strip()
        if explicit:
            return _sanitize_within_novels_root(explicit)
        novel_id = os.environ.get("ACTIVE_NOVEL_ID", "default")
    # 复用 novel_manager._validate_novel_id 的正则白名单 (字母/数字/下划线/中文/-)
    novel_manager._validate_novel_id(novel_id)
    base = os.path.join(_NOVELS_ROOT, novel_id)
    return _sanitize_within_novels_root(base)


class TickRuntime:
    """单例容器 - 装配 Orchestrator + 所有依赖,管理生命周期。"""

    def __init__(self, novel_id: str | None = None) -> None:
        # 显式 novel_id 走标准路径; None 走环境变量回退路径 (向后兼容旧 main.py / tools/)
        self.novel_id = novel_id or os.environ.get("ACTIVE_NOVEL_ID", "default")
        self.data_dir = _resolve_novel_data_dir(novel_id)
        os.makedirs(self.data_dir, exist_ok=True)

        # 基础设施
        self.tick_state = TickState(data_dir=self.data_dir)
        self.tick_state.load()  # 静默 fall-through 到 fresh

        self.tick_db = TickDB(db_path=os.path.join(self.data_dir, "ticks.db"))
        self.summary_tree = SummaryTree(merge_threshold=10)
        self.summary_tree.load_from_disk(
            os.path.join(self.data_dir, "summary_tree.json")
        )

        # 9 agents (v2.0-v2.1)
        self.world_simulator = WorldSimulator()
        self.narrator = NarratorAgent()
        self.event_injector = EventInjector()
        self.showrunner = Showrunner()
        self.memory_compressor = MemoryCompressor(summary_tree=self.summary_tree)
        self.consistency_guardian = ConsistencyGuardian()
        self.novelty_critic = NoveltyCritic()
        self.action_resolver = ActionResolver()

        # v2.3-v2.9 增强层 — 全部显式装配, Orchestrator 即时享受全部能力
        self.memory_store = PriorityMemoryStore(data_dir=self.data_dir)
        self.memory_store.load()  # 静默 fallthrough
        self.story_arc_director = StoryArcDirector()
        self.character_arc_tracker = CharacterArcTracker()
        self.fact_ledger = FactLedger(data_dir=self.data_dir)
        self.fact_ledger.load()
        self.safety_filter = SafetyFilter()
        self.token_budget = TokenBudgetTracker(data_dir=self.data_dir)
        self.token_budget.load()
        self.creativity_scorer = CreativityScorer()
        # v2.9 BranchManager — 以小说根目录 (而非 data_dir) 为 root
        # data_dir 已是 <novels>/<id>/, 这里就以它为分支树根
        self.branch_manager = BranchManager(root_data_dir=self.data_dir)
        self.branch_manager.load()

        # CharacterAgent 实例随 TickState 中已注册的 profile 自动构造
        self.character_agents: dict[str, CharacterAgent] = {}
        self._rebuild_character_agents()

        # Orchestrator 主调度器 — v2.10 显式注入 v2.3-v2.9 全部增强层
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
        # 保存最终状态 (含 v2.3-v2.9 各层)
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
            self.memory_store.save()
        except Exception as e:
            logger.error("Final MemoryStore save failed: %s", e)
        try:
            self.fact_ledger.save()
        except Exception as e:
            logger.error("Final FactLedger save failed: %s", e)
        try:
            self.token_budget.save()
        except Exception as e:
            logger.error("Final TokenBudgetTracker save failed: %s", e)
        try:
            self.branch_manager.save()
        except Exception as e:
            logger.error("Final BranchManager save failed: %s", e)
        try:
            self.tick_db.close()
        except Exception as e:
            logger.error("TickDB close failed: %s", e)


# v2.15 — 多 novel_id → TickRuntime 注册表 (替代旧的单 _runtime 单例)
#
# 旧实现的根本问题: switch_novel 只换 legacy GenerationPipeline, tick_routes
# 永远绑在启动时那本小说。前端切小说后用户在 UI 操作的是 A, 但 /api/tick/*
# 仍在推进 B 的世界状态。
#
# 新实现:
# - get_runtime(novel_id) 按需构造并缓存 (惰性)
# - set_active_novel(novel_id) 切换路由层指向哪个 runtime
# - close_all_runtimes 关闭所有 (FastAPI shutdown 用)
#
# 旧 API ``get_runtime() / close_runtime()`` 保留作为向后兼容外壳。
_runtimes: dict[str, "TickRuntime"] = {}
_active_novel_id: str | None = None


def _resolve_default_novel_id() -> str:
    """启动时的默认 novel_id — 沿用 ACTIVE_NOVEL_ID 语义。"""
    return os.environ.get("ACTIVE_NOVEL_ID", "default").strip() or "default"


def get_runtime(novel_id: str | None = None) -> TickRuntime:
    """按 novel_id 取/建 TickRuntime。

    * 不传 novel_id: 走"启动默认"路径 (沿用旧 main.py 启动行为)。
    * 首次 get 时若尚无 active runtime, 把它注册为 active 并注入路由层。
    """
    global _active_novel_id
    nid = novel_id or _active_novel_id or _resolve_default_novel_id()
    if nid not in _runtimes:
        # 显式 nid 走标准路径 _resolve_novel_data_dir(nid);
        # 但若调用方完全没指定且也没 active, 我们想保留 ACTIVE_NOVEL_DATA_DIR 语义,
        # 所以这里区分: 真正"无参 get_runtime()" 时传 None 走环境回退。
        explicit = novel_id is not None or _active_novel_id is not None
        _runtimes[nid] = TickRuntime(novel_id=nid if explicit else None)
    if _active_novel_id is None:
        set_active_novel(nid)
    return _runtimes[nid]


def set_active_novel(novel_id: str) -> TickRuntime:
    """切换活跃 runtime; 必要时按需构造, 同时把它注入 tick_routes 容器。

    这是把 switch_novel HTTP 路由真正接入 tick 架构的钩子 — 没有它,
    /api/tick/* 永远是启动时那本小说。
    """
    global _active_novel_id
    if not isinstance(novel_id, str) or not novel_id:
        raise ValueError(f"invalid novel_id for set_active_novel: {novel_id!r}")
    if novel_id not in _runtimes:
        _runtimes[novel_id] = TickRuntime(novel_id=novel_id)
    _active_novel_id = novel_id
    _runtimes[novel_id].register_to_routes()
    logger.info("Active novel switched to '%s' (%d runtimes loaded)",
                novel_id, len(_runtimes))
    return _runtimes[novel_id]


def get_active_runtime() -> TickRuntime | None:
    if _active_novel_id is None:
        return None
    return _runtimes.get(_active_novel_id)


def close_all_runtimes() -> None:
    """关闭并清空所有已加载的 runtime — FastAPI shutdown 钩子用。"""
    global _active_novel_id
    for nid, rt in list(_runtimes.items()):
        try:
            rt.close()
        except Exception as e:
            logger.error("close runtime '%s' failed: %s", nid, e)
    _runtimes.clear()
    _active_novel_id = None


# ----- 向后兼容外壳 ---------------------------------------------------------
# tools/run_ticks.py / 早期 main.py 调用 close_runtime() (drive_ticks.py 自 v2.22
# 起已归档到 old/tools/ — 它直接写 _runtime 单例, 与 v2.15+ 注册表实现不兼容)。
# 旧 API "关闭那一个 runtime" 现在等价于"关闭注册表里所有 runtime"。

def close_runtime() -> None:
    """旧别名 → close_all_runtimes()。"""
    close_all_runtimes()


def _clear_for_tests() -> None:
    """测试钩子 — 清空注册表与 active 指针, 不调用 close (保留外部资源)。"""
    global _active_novel_id
    _runtimes.clear()
    _active_novel_id = None
