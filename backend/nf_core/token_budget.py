"""TokenBudgetTracker — LLM 调用成本追踪 + 预算硬上限 + 退化策略。

针对主 Agent 关注问题清单的两项:

1. **计算成本与延迟的指数级增长** — 全局记账, 每 tick / 每 agent /
   累计三层视图; 触达预算时高优先级路径优先, 低优先级 (critic, novelty critic)
   自动退化
2. **MIMO API 配额管理** — 用户场景下 "持续迭代开发直到 mimo api 返回用量不足",
   提前在客户端层切断, 避免重复触发 quota_exceeded

设计:
* 全局单例 `TOKEN_TRACKER`, 但允许构造独立实例以便测试
* 调用前检查 `can_afford(agent_tier, estimated_tokens)`
* 调用后 `record(agent_id, prompt_tokens, completion_tokens, model)`
* 退化优先级 — critical (Narrator/CritiqueGuardian) > medium > optional
* JSON 原子写到 `data_dir/token_budget.json`, 跨进程恢复累计
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


AgentPriority = Literal["critical", "medium", "optional"]


class BudgetExceeded(Exception):
    """LLMClient.chat 在 token_budget 拒绝该次调用时抛出。

    调用方既有 ``except Exception`` 兜底会自动 swallow,但保留独立子类让调用方
    可以选择按 priority 重试或显式降级,不与真实 API 失败混在一起统计。
    """

    def __init__(self, *, agent_id: str, priority: str, reason: str) -> None:
        self.agent_id = agent_id
        self.priority = priority
        self.reason = reason
        super().__init__(f"budget rejected {agent_id}/{priority}: {reason}")


@dataclass
class TokenUsageRecord:
    timestamp: float
    agent_id: str
    priority: AgentPriority
    prompt_tokens: int
    completion_tokens: int
    model: str = ""
    tick: int = -1
    note: str = ""

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class BudgetSnapshot:
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    by_agent: dict[str, int] = field(default_factory=dict)
    by_priority: dict[str, int] = field(default_factory=dict)
    call_count: int = 0
    last_tick: int = -1

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v >= 0 else default
    except ValueError:
        return default


class TokenBudgetTracker:
    """全局预算追踪 + 退化决策。"""

    FILENAME = "token_budget.json"

    def __init__(
        self,
        data_dir: str | None = None,
        *,
        max_total_tokens: int | None = None,
        max_per_tick_tokens: int | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._path = (
            os.path.join(data_dir, self.FILENAME) if data_dir else None
        )
        self._records: list[TokenUsageRecord] = []
        # 默认上限来源: 显式参数 > 环境变量 > 无限
        self._max_total = (
            max_total_tokens
            if max_total_tokens is not None
            else _env_int("LLM_BUDGET_MAX_TOTAL", 0) or None
        )
        self._max_per_tick = (
            max_per_tick_tokens
            if max_per_tick_tokens is not None
            else _env_int("LLM_BUDGET_MAX_PER_TICK", 0) or None
        )
        self._current_tick: int = -1
        self._tick_tokens: int = 0
        self._snapshot = BudgetSnapshot()

    # ------------------------------------------------------------------
    # 记账
    # ------------------------------------------------------------------

    def record(
        self,
        *,
        agent_id: str,
        priority: AgentPriority,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "",
        tick: int = -1,
        note: str = "",
    ) -> TokenUsageRecord:
        rec = TokenUsageRecord(
            timestamp=time.time() if not os.environ.get("PYTEST_CURRENT_TEST") else 0.0,
            agent_id=agent_id,
            priority=priority,
            prompt_tokens=int(max(0, prompt_tokens)),
            completion_tokens=int(max(0, completion_tokens)),
            model=model,
            tick=tick,
            note=note,
        )
        self._records.append(rec)
        self._snapshot.total_prompt_tokens += rec.prompt_tokens
        self._snapshot.total_completion_tokens += rec.completion_tokens
        self._snapshot.by_agent[agent_id] = (
            self._snapshot.by_agent.get(agent_id, 0) + rec.total
        )
        self._snapshot.by_priority[priority] = (
            self._snapshot.by_priority.get(priority, 0) + rec.total
        )
        self._snapshot.call_count += 1
        if tick >= 0:
            if tick != self._current_tick:
                self._current_tick = tick
                self._tick_tokens = 0
            self._tick_tokens += rec.total
            self._snapshot.last_tick = tick
        return rec

    def begin_tick(self, tick: int) -> None:
        self._current_tick = tick
        self._tick_tokens = 0

    # ------------------------------------------------------------------
    # 决策 — 调用前查询
    # ------------------------------------------------------------------

    def can_afford(
        self,
        *,
        priority: AgentPriority,
        estimated_tokens: int = 0,
    ) -> bool:
        """返回是否允许该次调用。

        策略:
        * 无上限设定时始终允许
        * critical 优先级即使超过上限也允许 (Narrator 不能被掐断)
        * medium 在总预算 90% 内允许
        * optional 在总预算 70% 内允许
        * 单 tick 上限独立约束 (optional 在 tick 上限 80% 内允许)
        """
        if priority == "critical":
            return True

        if self._max_total is not None:
            ratio = self._snapshot.total_tokens / max(1, self._max_total)
            est_ratio = (self._snapshot.total_tokens + estimated_tokens) / max(
                1, self._max_total
            )
            if priority == "medium" and est_ratio > 0.9:
                return False
            if priority == "optional" and est_ratio > 0.7:
                return False
            if ratio >= 1.0:
                return False  # 超出全局上限, 一律拒绝非 critical

        if self._max_per_tick is not None and self._current_tick >= 0:
            tick_after = self._tick_tokens + estimated_tokens
            tick_ratio = tick_after / max(1, self._max_per_tick)
            if priority == "optional" and tick_ratio > 0.8:
                return False
            if priority == "medium" and tick_ratio > 1.0:
                return False

        return True

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    @property
    def snapshot(self) -> BudgetSnapshot:
        return self._snapshot

    @property
    def records(self) -> list[TokenUsageRecord]:
        return list(self._records)

    @property
    def max_total(self) -> int | None:
        return self._max_total

    @property
    def max_per_tick(self) -> int | None:
        return self._max_per_tick

    def remaining_total(self) -> int | None:
        if self._max_total is None:
            return None
        return max(0, self._max_total - self._snapshot.total_tokens)

    def remaining_tick(self) -> int | None:
        if self._max_per_tick is None:
            return None
        return max(0, self._max_per_tick - self._tick_tokens)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def save(self) -> None:
        if self._data_dir is None or self._path is None:
            return
        os.makedirs(self._data_dir, exist_ok=True)
        payload = {
            "version": 1,
            "snapshot": {
                "total_prompt_tokens": self._snapshot.total_prompt_tokens,
                "total_completion_tokens": self._snapshot.total_completion_tokens,
                "by_agent": dict(self._snapshot.by_agent),
                "by_priority": dict(self._snapshot.by_priority),
                "call_count": self._snapshot.call_count,
                "last_tick": self._snapshot.last_tick,
            },
            "records_tail": [asdict(r) for r in self._records[-200:]],  # 仅尾部 200 条
        }
        fd, tmp = tempfile.mkstemp(
            prefix=".token_budget_", suffix=".tmp", dir=self._data_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def load(self) -> bool:
        if self._path is None or not os.path.exists(self._path):
            return False
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            logger.warning("TokenBudgetTracker load failed: %s", e)
            return False
        snap = payload.get("snapshot", {}) or {}
        self._snapshot = BudgetSnapshot(
            total_prompt_tokens=int(snap.get("total_prompt_tokens", 0)),
            total_completion_tokens=int(snap.get("total_completion_tokens", 0)),
            by_agent=dict(snap.get("by_agent", {}) or {}),
            by_priority=dict(snap.get("by_priority", {}) or {}),
            call_count=int(snap.get("call_count", 0)),
            last_tick=int(snap.get("last_tick", -1)),
        )
        self._records = []
        for raw in payload.get("records_tail", []) or []:
            try:
                self._records.append(TokenUsageRecord(**raw))
            except Exception:
                continue
        return True


# 全局默认实例 — agent 可通过 get_global_tracker() 取
_GLOBAL_TRACKER: TokenBudgetTracker | None = None


def get_global_tracker() -> TokenBudgetTracker:
    global _GLOBAL_TRACKER
    if _GLOBAL_TRACKER is None:
        _GLOBAL_TRACKER = TokenBudgetTracker()
    return _GLOBAL_TRACKER


def set_global_tracker(tracker: TokenBudgetTracker) -> None:
    global _GLOBAL_TRACKER
    _GLOBAL_TRACKER = tracker


__all__ = [
    "BudgetExceeded",
    "TokenBudgetTracker",
    "TokenUsageRecord",
    "BudgetSnapshot",
    "AgentPriority",
    "get_global_tracker",
    "set_global_tracker",
]
