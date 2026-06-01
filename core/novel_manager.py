"""
多小说项目管理器。

把主项目的 ``results/{topic}/`` 目录纳入统一管理：
- ``results/manifest.json`` 维护每本小说的元数据 (id / title / created_at / updated_at)。
- ``id`` 同时是目录名 (kebab/拼音 slug)，与现有 CLI 路径兼容。
- 已存在但不在 manifest 中的 ``results/*`` 目录会在首次访问时自动注册 (backfill)。

设计目标：让现有 ``create_novel.py`` / ``continue_novel.py`` 入口保持可用，同时
为前端提供 ``list / rename / delete / switch`` 这些能力。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import RESULTS_DIR

_MANIFEST_FILENAME = "manifest.json"
_LEGACY_SKIP = {"__pycache__"}  # 忽略的非小说目录


def _manifest_path() -> Path:
    return Path(RESULTS_DIR) / _MANIFEST_FILENAME


def _ensure_results_dir() -> None:
    Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(title: str) -> str:
    """生成安全的目录名 slug。

    - 保留中文 / 字母 / 数字 / 下划线 / 短横；其他替换为下划线。
    - 截断到 30 字符并追加 6 位时间戳后缀，避免冲突。
    """
    cleaned = re.sub(r"[^\w一-鿿-]", "_", title).strip("_")[:30]
    suffix = hex(int(time.time() * 1000) % 0xFFFFFF)[2:]
    return f"{cleaned}_{suffix}" if cleaned else suffix


@dataclass(frozen=True)
class NovelEntry:
    id: str
    title: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def _load_manifest() -> list[dict]:
    path = _manifest_path()
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_manifest(entries: list[dict]) -> None:
    _ensure_results_dir()
    path = _manifest_path()
    with path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _scan_legacy_topics() -> list[str]:
    """扫描 ``results/`` 下已存在但未注册的小说目录。"""
    _ensure_results_dir()
    result: list[str] = []
    for entry in Path(RESULTS_DIR).iterdir():
        if not entry.is_dir():
            continue
        if entry.name in _LEGACY_SKIP or entry.name.startswith("."):
            continue
        result.append(entry.name)
    return result


def _backfill_legacy(entries: list[dict]) -> list[dict]:
    """把磁盘上有但 manifest 没有的目录注册进来。"""
    known_ids = {e["id"] for e in entries}
    legacy_topics = _scan_legacy_topics()
    changed = False
    for topic in legacy_topics:
        if topic in known_ids:
            continue
        topic_path = Path(RESULTS_DIR) / topic
        ts_str = _now_iso()
        try:
            mtime = topic_path.stat().st_mtime
            ts_str = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        except OSError:
            pass
        entries.append(
            {
                "id": topic,
                "title": topic,  # 老目录默认以目录名作为标题
                "created_at": ts_str,
                "updated_at": ts_str,
            }
        )
        changed = True
    if changed:
        _save_manifest(entries)
    return entries


def list_novels() -> list[dict]:
    """返回所有小说元数据（自动 backfill 旧目录）。"""
    entries = _load_manifest()
    entries = _backfill_legacy(entries)
    # 默认按 updated_at 倒序
    return sorted(entries, key=lambda e: e.get("updated_at", ""), reverse=True)


def get_novel(novel_id: str) -> Optional[dict]:
    for entry in list_novels():
        if entry["id"] == novel_id:
            return entry
    return None


def get_novel_data_dir(novel_id: str) -> str:
    """返回某本小说的数据目录路径（不强制存在）。"""
    return str(Path(RESULTS_DIR) / novel_id)


def create_novel(title: str = "未命名小说") -> dict:
    """创建新小说目录与 manifest 项。"""
    _ensure_results_dir()
    entries = _load_manifest()
    novel_id = _slugify(title)
    # slug 撞库时叠加随机后缀
    while any(e["id"] == novel_id for e in entries):
        novel_id = f"{novel_id}_{hex(int(time.time() * 1000) % 0xFFFFFF)[2:]}"

    novel_dir = Path(RESULTS_DIR) / novel_id
    novel_dir.mkdir(parents=True, exist_ok=True)

    now = _now_iso()
    entry = {
        "id": novel_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }
    entries.append(entry)
    _save_manifest(entries)
    return entry


def update_title(novel_id: str, title: str) -> Optional[dict]:
    entries = _load_manifest()
    for entry in entries:
        if entry["id"] == novel_id:
            entry["title"] = title
            entry["updated_at"] = _now_iso()
            _save_manifest(entries)
            return entry
    return None


def touch(novel_id: str) -> None:
    """更新 updated_at 时间戳（在生成新章节后调用）。"""
    entries = _load_manifest()
    for entry in entries:
        if entry["id"] == novel_id:
            entry["updated_at"] = _now_iso()
            _save_manifest(entries)
            return


def delete_novel(novel_id: str, *, remove_files: bool = True) -> bool:
    """从 manifest 中删除条目，并可选地物理删除目录。"""
    entries = _load_manifest()
    new_entries = [e for e in entries if e["id"] != novel_id]
    if len(new_entries) == len(entries):
        return False
    _save_manifest(new_entries)

    if remove_files:
        novel_dir = Path(RESULTS_DIR) / novel_id
        if novel_dir.is_dir():
            shutil.rmtree(novel_dir, ignore_errors=True)
    return True


__all__ = [
    "NovelEntry",
    "list_novels",
    "get_novel",
    "get_novel_data_dir",
    "create_novel",
    "update_title",
    "touch",
    "delete_novel",
]
