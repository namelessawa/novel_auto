"""Novel Manager — 多用户多小说命名空间。

v2.26 数据布局 (multi-tenant)
-----------------------------
``backend/data/users/{user_id}/manifest.json``  — 该用户的 novel 索引
``backend/data/users/{user_id}/novels/{novel_id}/``  — 该 novel 的全部数据

v2.25 及以前的 ``backend/data/novels/{novel_id}/`` 在启动时被一次性迁移到
``backend/data/users/_legacy/novels/{novel_id}/``  — auth 关闭时 LEGACY_USER
能看到这些; 一旦 auth 打开, legacy 数据需要管理员手动迁移到真实用户名下
(``backend/data/users/_legacy/`` 整个 mv 到目标 ``{real_uid}/``)。

API 形状
---------
全部入口都要 ``user_id``。任何 ``user_id`` 与 ``novel_id`` 走路径拼接的位置
都过 ``_validate_user_id`` / ``_validate_novel_id`` + realpath sanitizer 双校验,
继续维持 v2.17 起的路径注入防御。
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# v2.26 — 新根, 取代旧的 ``backend/data/novels``
_DATA_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "data"))
_USERS_ROOT = os.path.join(_DATA_ROOT, "users")
_LEGACY_NOVELS_DIR = os.path.join(_DATA_ROOT, "novels")  # 升级前的位置
_LEGACY_USER_ID = "_legacy"

# user_id: uuid4 hex (32 hex chars) 或 "_legacy"。比 novel_id 更窄, 不接受中文。
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# novel_id: 与 v2.15 _slugify 输出对齐
_NOVEL_ID_RE = re.compile(r"^[\w一-鿿\-]{1,64}$")


def _validate_user_id(user_id: str) -> str:
    if not isinstance(user_id, str) or not _USER_ID_RE.match(user_id):
        raise ValueError(f"invalid user_id: {user_id!r}")
    return user_id


def _validate_novel_id(novel_id: str) -> str:
    if not isinstance(novel_id, str) or not _NOVEL_ID_RE.match(novel_id):
        raise ValueError(f"invalid novel_id: {novel_id!r}")
    return novel_id


def _user_root(user_id: str) -> str:
    _validate_user_id(user_id)
    return os.path.join(_USERS_ROOT, user_id)


def _user_novels_root(user_id: str) -> str:
    return os.path.join(_user_root(user_id), "novels")


def _user_manifest_path(user_id: str) -> str:
    return os.path.join(_user_root(user_id), "manifest.json")


def _assert_path_within(path: str, root: str) -> None:
    """realpath sanitizer — CodeQL py/path-injection 认可的 commonpath 模式。"""
    real_target = os.path.realpath(path)
    real_root = os.path.realpath(root)
    try:
        common = os.path.commonpath([real_target, real_root])
    except ValueError:
        raise ValueError(f"path outside allowed root: {path!r}") from None
    if common != real_root:
        raise ValueError(f"path outside allowed root: {path!r}")


# v2.25 兼容别名 — 旧 test_novel_manager_security.py 用此名
def _assert_path_within_novels_root(path: str) -> None:
    """旧 API 兼容: 校验 path 落在 _LEGACY_NOVELS_DIR 之下。

    v2.26 之后实际数据已迁移到 data/users/{uid}/novels/, 此函数只为旧测试
    collection 兼容; 调用方应改用 ``_assert_path_within(path, root)``。
    """
    _assert_path_within(path, _LEGACY_NOVELS_DIR)


def _ensure_user_dirs(user_id: str) -> None:
    os.makedirs(_user_novels_root(user_id), exist_ok=True)


def _load_manifest(user_id: str) -> list[dict]:
    path = _user_manifest_path(user_id)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as e:
        logger.error("manifest read failed for user '%s': %s", user_id, e)
        return []


def _save_manifest(user_id: str, entries: list[dict]) -> None:
    _ensure_user_dirs(user_id)
    path = _user_manifest_path(user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _slugify(title: str) -> str:
    slug = re.sub(r"[^\w一-鿿-]", "_", title).strip("_")[:30]
    suffix = hex(int(time.time() * 1000) % 0xFFFFFF)[2:]
    return f"{slug}_{suffix}" if slug else suffix


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


# ---- 公共 API -----------------------------------------------------------
def list_novels(user_id: str) -> list[dict]:
    _ensure_user_dirs(user_id)
    return _load_manifest(user_id)


def create_novel(user_id: str, title: str = "未命名小说") -> dict:
    _ensure_user_dirs(user_id)
    entries = _load_manifest(user_id)
    novel_id = _slugify(title)
    novel_dir = get_novel_data_dir(user_id, novel_id)
    os.makedirs(os.path.join(novel_dir, "chroma"), exist_ok=True)
    os.makedirs(os.path.join(novel_dir, "snapshots"), exist_ok=True)

    now = _now_iso()
    entry = {
        "id": novel_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "last_accessed_at": _now_ts(),  # v2.26 — cleanup 任务用
    }
    entries.append(entry)
    _save_manifest(user_id, entries)
    return entry


def update_title(user_id: str, novel_id: str, title: str) -> dict | None:
    _validate_novel_id(novel_id)
    entries = _load_manifest(user_id)
    for entry in entries:
        if entry["id"] == novel_id:
            entry["title"] = title
            entry["updated_at"] = _now_iso()
            entry["last_accessed_at"] = _now_ts()
            _save_manifest(user_id, entries)
            return entry
    return None


def delete_novel(user_id: str, novel_id: str) -> bool:
    _validate_novel_id(novel_id)
    entries = _load_manifest(user_id)
    new_entries = [e for e in entries if e["id"] != novel_id]
    if len(new_entries) == len(entries):
        return False
    _save_manifest(user_id, new_entries)
    novel_dir = get_novel_data_dir(user_id, novel_id)
    _assert_path_within(novel_dir, _user_novels_root(user_id))
    if os.path.isdir(novel_dir):
        shutil.rmtree(novel_dir, ignore_errors=True)
    return True


def get_novel_data_dir(user_id: str, novel_id: str) -> str:
    _validate_user_id(user_id)
    _validate_novel_id(novel_id)
    path = os.path.join(_user_novels_root(user_id), novel_id)
    _assert_path_within(path, _user_novels_root(user_id))
    return path


def get_novel(user_id: str, novel_id: str) -> dict | None:
    _validate_novel_id(novel_id)
    entries = _load_manifest(user_id)
    for entry in entries:
        if entry["id"] == novel_id:
            return entry
    return None


def touch_last_accessed(user_id: str, novel_id: str) -> None:
    """更新 last_accessed_at — 任何对小说的写操作前调一次, 给 cleanup 兜底。"""
    _validate_novel_id(novel_id)
    entries = _load_manifest(user_id)
    changed = False
    for entry in entries:
        if entry["id"] == novel_id:
            entry["last_accessed_at"] = _now_ts()
            changed = True
            break
    if changed:
        _save_manifest(user_id, entries)


def resolve_default_novel_id(user_id: str) -> str:
    """该用户的"启动默认 novel_id"。manifest 第一项, 或新建一本。"""
    entries = list_novels(user_id)
    if entries:
        return entries[0]["id"]
    return create_novel(user_id, "未命名小说")["id"]


# ---- 一次性迁移 — v2.25 → v2.26 -----------------------------------------
def migrate_legacy_layout() -> bool:
    """如发现 v2.25 旧目录结构 (data/novels/), 一次性迁移到 data/users/_legacy/novels/。

    返回 True 表示发生了迁移; False 表示已经是新布局或无 legacy 数据。

    由 main.py 启动钩子调用一次。idempotent — 第二次启动不会再动。
    """
    if not os.path.isdir(_LEGACY_NOVELS_DIR):
        return False

    legacy_user_novels = _user_novels_root(_LEGACY_USER_ID)
    if os.path.isdir(legacy_user_novels):
        # 已经迁移过 — 跳过
        return False

    os.makedirs(_user_root(_LEGACY_USER_ID), exist_ok=True)

    # 移动 (而非复制) 整个 novels 目录到 _legacy 用户名下
    try:
        shutil.move(_LEGACY_NOVELS_DIR, legacy_user_novels)
        logger.info(
            "MIGRATED v2.25 → v2.26: %s → %s",
            _LEGACY_NOVELS_DIR, legacy_user_novels,
        )
    except OSError as e:
        logger.error("legacy migration failed: %s", e)
        return False

    # 旧 manifest 在 data/novels/manifest.json (现在已被 move 进 legacy_user_novels)
    legacy_manifest_old = os.path.join(legacy_user_novels, "manifest.json")
    legacy_manifest_new = _user_manifest_path(_LEGACY_USER_ID)
    if os.path.isfile(legacy_manifest_old):
        shutil.move(legacy_manifest_old, legacy_manifest_new)
        # 为旧 entries 补 last_accessed_at 字段
        try:
            entries = _load_manifest(_LEGACY_USER_ID)
            now = _now_ts()
            for e in entries:
                e.setdefault("last_accessed_at", now)
            _save_manifest(_LEGACY_USER_ID, entries)
        except Exception as e:
            logger.error("legacy manifest backfill failed: %s", e)
    return True


# ---- cleanup 用 ---------------------------------------------------------
def list_all_users_with_novels() -> list[str]:
    """枚举所有有 novel 数据的 user_id (从盘上扫, 不依赖 auth.db)。"""
    if not os.path.isdir(_USERS_ROOT):
        return []
    out: list[str] = []
    for name in os.listdir(_USERS_ROOT):
        try:
            _validate_user_id(name)
        except ValueError:
            continue
        if os.path.isdir(_user_novels_root(name)):
            out.append(name)
    return out
