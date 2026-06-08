"""进程内令牌桶 — per-scope per-key 滑动窗口计数。

适配场景: 单进程 FastAPI / uvicorn worker_count=1。多 worker 或多机部署
请换 Redis backend (slowapi 自带支持)。

线程安全: 单 ``threading.Lock`` 保护 dict, 命中频次低 (登录路径) 不是瓶颈。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimit:
    """``max_count`` 次每 ``window_seconds`` 秒。"""

    max_count: int
    window_seconds: int


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key = (scope, identifier), value = sorted list of hit timestamps
        self._hits: dict[tuple[str, str], list[float]] = defaultdict(list)

    def check_and_record(self, scope: str, key: str, limit: RateLimit) -> bool:
        """允许 → True 并记一次; 超限 → False 不记。"""
        if limit.max_count <= 0:
            return False
        now = time.time()
        cutoff = now - limit.window_seconds
        composite = (scope, key)
        with self._lock:
            hits = self._hits[composite]
            # 清理过期 (sorted, 从前剪)
            i = 0
            while i < len(hits) and hits[i] < cutoff:
                i += 1
            if i > 0:
                del hits[:i]
            if len(hits) >= limit.max_count:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        """测试钩子 — 清空所有计数。"""
        with self._lock:
            self._hits.clear()

    def snapshot(self) -> dict[tuple[str, str], int]:
        """诊断 — 返回每 (scope, key) 当前窗口内命中数。"""
        with self._lock:
            return {k: len(v) for k, v in self._hits.items()}


_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter
