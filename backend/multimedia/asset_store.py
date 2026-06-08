"""v2.33 — 多模态资产 store, per-novel-per-section.

目录布局
--------
``{novel_data_dir}/multimedia/sec_{chapter}_{section}/``

```
manifest.json        # 整体状态: segments + voice + 视频路径
img_001.png          # 第 1 段对应的图
img_002.png
...
audio_001.mp3        # 第 1 段对应的 TTS
audio_002.mp3
...
subtitles.srt        # 字幕 (合成时写, 留作 debug)
output.mp4           # 最终视频
```

为啥不存 ticks.db / tick_sections.jsonl?
* 二进制文件 (png/mp3/mp4) 不适合塞 JSON
* 资产生成是幂等的, 可重做, 不需要事务边界
* 前端按文件名直接 fetch (走 /api/multimodal/.../asset) 比走 JSON 解码 base64 高效

并发
----
同一 (novel, chapter, section) 在同进程内同时被两个 task 写 manifest 是 race —
上层 (multimodal_routes) 用 TaskManager 的 conflict 拒掉; store 这层只在
write_manifest 加文件锁意义不大, 简单 threading.Lock 够用.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


AssetStatus = Literal["pending", "running", "done", "failed"]


class MultimediaError(Exception):
    """多模态资产 store 错误."""


class SegmentAsset(BaseModel):
    """单段资产 — 一段文字 + 它的图 + 音频."""

    model_config = ConfigDict(extra="ignore")

    index: int = Field(ge=0)
    text: str
    char_count: int = 0
    image_filename: str = ""        # 相对 sec_{ch}_{s}/ 的文件名
    image_status: AssetStatus = "pending"
    image_error: str = ""
    audio_filename: str = ""
    audio_status: AssetStatus = "pending"
    audio_error: str = ""
    duration_ms: int = 0


class MultimediaManifest(BaseModel):
    """整个节的多模态状态."""

    model_config = ConfigDict(extra="ignore")

    novel_id: str
    chapter: int = Field(ge=1)
    section: int = Field(ge=1)
    source_text: str = ""           # 节原文 (供回放校对)
    voice: str = ""                 # edge-tts voice id
    image_provider: str = ""        # xfyun / openai / ...
    image_width: int = 768
    image_height: int = 768
    segments: list[SegmentAsset] = Field(default_factory=list)
    video_filename: str = ""        # 默认 "output.mp4", 完成后填
    video_status: AssetStatus = "pending"
    video_error: str = ""
    created_at: str = ""
    updated_at: str = ""

    @staticmethod
    def now_iso() -> str:
        # 用 timezone-aware utcnow — datetime.utcnow() 在 3.12+ 弃用
        return (
            datetime.now(timezone.utc)
            .replace(tzinfo=None)
            .isoformat(timespec="seconds")
            + "Z"
        )


class MultimediaStore:
    """per-novel multimedia 资产管理."""

    DIR_NAME = "multimedia"
    MANIFEST_NAME = "manifest.json"

    def __init__(self, novel_id: str, data_dir: str) -> None:
        self._novel_id = novel_id
        self._root = Path(data_dir) / self.DIR_NAME
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------

    @property
    def root(self) -> Path:
        return self._root

    def section_dir(self, chapter: int, section: int) -> Path:
        return self._root / f"sec_{chapter}_{section}"

    def manifest_path(self, chapter: int, section: int) -> Path:
        return self.section_dir(chapter, section) / self.MANIFEST_NAME

    def image_filename(self, index: int) -> str:
        return f"img_{index + 1:03d}.png"

    def audio_filename(self, index: int) -> str:
        return f"audio_{index + 1:03d}.mp3"

    # ------------------------------------------------------------------
    # manifest 读写
    # ------------------------------------------------------------------

    def load_manifest(self, chapter: int, section: int) -> MultimediaManifest | None:
        path = self.manifest_path(chapter, section)
        if not path.is_file():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            return MultimediaManifest.model_validate_json(raw)
        except Exception as e:
            logger.warning("无法读 multimedia manifest (%s): %s", path, e)
            return None

    def save_manifest(self, manifest: MultimediaManifest) -> None:
        """原子写 — tempfile + os.replace, 防崩溃留半截文件.

        线程安全: threading.Lock 保护单进程内的并发写; 跨进程 (多 worker
        uvicorn) 不保护 — 本项目部署默认单 worker, 不在此修.
        """
        with self._lock:
            self._save_manifest_unlocked(manifest)

    def _save_manifest_unlocked(self, manifest: MultimediaManifest) -> None:
        """无锁版本 — 仅在已持有 self._lock 时调用 (update_segment_status 复用)."""
        section_dir = self.section_dir(manifest.chapter, manifest.section)
        section_dir.mkdir(parents=True, exist_ok=True)
        path = self.manifest_path(manifest.chapter, manifest.section)

        manifest_to_write = manifest.model_copy(
            update={"updated_at": MultimediaManifest.now_iso()}
        )
        if not manifest_to_write.created_at:
            manifest_to_write = manifest_to_write.model_copy(
                update={"created_at": MultimediaManifest.now_iso()}
            )

        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            manifest_to_write.model_dump_json(indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def update_segment_status(
        self,
        chapter: int,
        section: int,
        index: int,
        **fields: Any,
    ) -> MultimediaManifest | None:
        """原子更新单段的状态字段 — load + modify + save 整体加锁.

        让调用方不用自己处理 race: 之前每个并发协程做 load-modify-save 的
        三步在 asyncio 单线程 + 同步 I/O 下是侥幸原子的, 但一旦其中任一步
        被改成 await (例: 用 asyncio.to_thread 做磁盘 I/O), 就立刻 race.
        把整段 read-modify-write 拉进 store 的锁内, 是更牢的契约.

        ``fields`` 支持 SegmentAsset 上的任意字段 (image_status / image_error /
        audio_status / audio_error / duration_ms / ...).
        """
        with self._lock:
            manifest = self.load_manifest(chapter, section)
            if manifest is None:
                logger.warning(
                    "update_segment_status: manifest 不存在 (%d, %d), 跳过",
                    chapter, section,
                )
                return None
            segments = list(manifest.segments)
            if not (0 <= index < len(segments)):
                logger.warning(
                    "update_segment_status: index %d 越界 (共 %d 段)",
                    index, len(segments),
                )
                return manifest
            segments[index] = segments[index].model_copy(update=fields)
            new_manifest = manifest.model_copy(update={"segments": segments})
            self._save_manifest_unlocked(new_manifest)
            return new_manifest

    # ------------------------------------------------------------------
    # 写入资产
    # ------------------------------------------------------------------

    def write_image(self, chapter: int, section: int, index: int, png_bytes: bytes) -> str:
        """写 PNG 图片, 返回文件名."""
        fn = self.image_filename(index)
        section_dir = self.section_dir(chapter, section)
        section_dir.mkdir(parents=True, exist_ok=True)
        (section_dir / fn).write_bytes(png_bytes)
        return fn

    def audio_path(self, chapter: int, section: int, index: int) -> Path:
        """返回 audio 文件的绝对路径 — 给 edge_tts 直接写入用."""
        fn = self.audio_filename(index)
        section_dir = self.section_dir(chapter, section)
        section_dir.mkdir(parents=True, exist_ok=True)
        return section_dir / fn

    def video_path(self, chapter: int, section: int, video_filename: str = "output.mp4") -> Path:
        return self.section_dir(chapter, section) / video_filename

    # ------------------------------------------------------------------
    # 列表 + 状态
    # ------------------------------------------------------------------

    def list_sections(self) -> list[tuple[int, int]]:
        """扫所有 sec_{ch}_{s} 目录, 返回 [(chapter, section)] 升序."""
        if not self._root.is_dir():
            return []
        out: list[tuple[int, int]] = []
        for entry in self._root.iterdir():
            if not entry.is_dir():
                continue
            name = entry.name
            if not name.startswith("sec_"):
                continue
            parts = name[4:].split("_")
            if len(parts) != 2:
                continue
            try:
                ch = int(parts[0])
                s = int(parts[1])
            except ValueError:
                continue
            out.append((ch, s))
        out.sort()
        return out


# ---- per-novel 单例 ---------------------------------------------------------


_stores: dict[str, MultimediaStore] = {}
_stores_lock = threading.Lock()


def get_multimedia_store(novel_id: str, data_dir: str) -> MultimediaStore:
    """返回 (按需创建) 一个 novel 的 MultimediaStore."""
    if not novel_id:
        raise MultimediaError("novel_id 不能为空")
    if not data_dir:
        raise MultimediaError("data_dir 不能为空")
    with _stores_lock:
        if novel_id not in _stores:
            _stores[novel_id] = MultimediaStore(novel_id=novel_id, data_dir=data_dir)
        return _stores[novel_id]


def _clear_for_tests() -> None:
    with _stores_lock:
        _stores.clear()
