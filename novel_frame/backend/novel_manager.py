"""Novel Manager — manages multiple novel projects with isolated data directories."""

from __future__ import annotations

import json
import os
import shutil
import time
import re
from datetime import datetime, timezone

_NOVELS_DIR = os.path.join(os.path.dirname(__file__), "data", "novels")
_MANIFEST_PATH = os.path.join(_NOVELS_DIR, "manifest.json")


def _ensure_dir() -> None:
    os.makedirs(_NOVELS_DIR, exist_ok=True)


def _load_manifest() -> list[dict]:
    if not os.path.isfile(_MANIFEST_PATH):
        return []
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_manifest(entries: list[dict]) -> None:
    _ensure_dir()
    with open(_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _slugify(title: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]", "_", title).strip("_")[:30]
    suffix = hex(int(time.time() * 1000) % 0xFFFFFF)[2:]
    return f"{slug}_{suffix}" if slug else suffix


def list_novels() -> list[dict]:
    _ensure_dir()
    return _load_manifest()


def create_novel(title: str = "未命名小说") -> dict:
    _ensure_dir()
    entries = _load_manifest()
    novel_id = _slugify(title)
    novel_dir = os.path.join(_NOVELS_DIR, novel_id)
    os.makedirs(os.path.join(novel_dir, "chroma"), exist_ok=True)
    os.makedirs(os.path.join(novel_dir, "snapshots"), exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": novel_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }
    entries.append(entry)
    _save_manifest(entries)
    return entry


def update_title(novel_id: str, title: str) -> dict | None:
    entries = _load_manifest()
    for entry in entries:
        if entry["id"] == novel_id:
            entry["title"] = title
            entry["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_manifest(entries)
            return entry
    return None


def delete_novel(novel_id: str) -> bool:
    entries = _load_manifest()
    new_entries = [e for e in entries if e["id"] != novel_id]
    if len(new_entries) == len(entries):
        return False
    _save_manifest(new_entries)
    novel_dir = os.path.join(_NOVELS_DIR, novel_id)
    if os.path.isdir(novel_dir):
        shutil.rmtree(novel_dir, ignore_errors=True)
    return True


def get_novel_data_dir(novel_id: str) -> str:
    return os.path.join(_NOVELS_DIR, novel_id)


def get_novel(novel_id: str) -> dict | None:
    entries = _load_manifest()
    for entry in entries:
        if entry["id"] == novel_id:
            return entry
    return None


def migrate_legacy_data() -> str | None:
    """If legacy data dirs exist but no novels dir, migrate into a default novel."""
    _ensure_dir()
    entries = _load_manifest()
    if entries:
        return None  # already have novels, skip migration

    legacy_chroma = os.path.join(os.path.dirname(__file__), "data", "chroma")
    legacy_snapshots = os.path.join(os.path.dirname(__file__), "data", "snapshots")

    has_legacy = os.path.isdir(legacy_chroma) or os.path.isdir(legacy_snapshots)
    if not has_legacy:
        return None

    novel = create_novel("默认小说")
    novel_dir = get_novel_data_dir(novel["id"])

    if os.path.isdir(legacy_chroma):
        target = os.path.join(novel_dir, "chroma")
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(legacy_chroma, target)

    if os.path.isdir(legacy_snapshots):
        target = os.path.join(novel_dir, "snapshots")
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(legacy_snapshots, target)

    return novel["id"]
