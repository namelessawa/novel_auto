"""v2.26 — 24h ephemeral novel 清理后台任务。

策略
----
* 每 ``cleanup_interval_seconds`` 秒醒一次 (默认 3600 = 1h)。
* 扫所有用户 manifest;
* 对每个 entry 检查:
  - 该用户 ``save_my_works=True`` → 跳过
  - 该用户 ``save_my_works=False`` AND ``now - last_accessed_at > ephemeral_ttl_hours * 3600`` → 删
* LEGACY_USER (_legacy) 不清理 — 它是迁移容器, 假装永远 save_my_works=True。

不删 auth.db 里的 OTP 记录 — 那有独立 expires_at, OTP 校验失败路径会自动清。
但提供 ``purge_expired_otps`` 顺便调用一次, 避免 OTP 表无限膨胀。
"""

from __future__ import annotations

import asyncio
import logging
import time

import novel_manager
from auth import LEGACY_USER_ID
from auth.config import get_auth_config
from auth.store import get_user_store
from tick_runtime import drop_runtime

logger = logging.getLogger(__name__)


async def cleanup_loop() -> None:
    """后台 task — 永久循环, 由 FastAPI shutdown 时 cancel。"""
    while True:
        cfg = get_auth_config()
        try:
            n_deleted = run_once()
            n_otp = get_user_store().purge_expired_otps()
            if n_deleted or n_otp:
                logger.info(
                    "cleanup pass: %d novels purged, %d expired OTPs purged",
                    n_deleted, n_otp,
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("cleanup pass failed: %s", e)

        try:
            await asyncio.sleep(max(60, cfg.cleanup_interval_seconds))
        except asyncio.CancelledError:
            raise


def run_once() -> int:
    """同步一次扫描 — 返回删除的 novel 数。"""
    cfg = get_auth_config()
    ttl_seconds = cfg.ephemeral_ttl_hours * 3600
    cutoff = time.time() - ttl_seconds

    store = get_user_store()
    save_map: dict[str, bool] = {LEGACY_USER_ID: True}  # legacy 不清
    for row in store.list_all():
        save_map[row["id"]] = bool(row.get("save_my_works"))

    total_deleted = 0
    for user_id in novel_manager.list_all_users_with_novels():
        if save_map.get(user_id, False):
            continue  # 用户已选保存 / legacy
        entries = novel_manager.list_novels(user_id)
        for entry in entries:
            last = entry.get("last_accessed_at") or 0
            if last >= cutoff:
                continue
            try:
                drop_runtime(user_id, entry["id"])
            except Exception as e:
                logger.debug("drop_runtime during cleanup failed: %s", e)
            try:
                if novel_manager.delete_novel(user_id, entry["id"]):
                    total_deleted += 1
                    logger.info(
                        "cleanup deleted novel (user=%s novel=%s last_accessed=%s)",
                        user_id, entry["id"], last,
                    )
            except Exception as e:
                logger.warning(
                    "cleanup delete failed for (%s, %s): %s",
                    user_id, entry["id"], e,
                )
    return total_deleted
