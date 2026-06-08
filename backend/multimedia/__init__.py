"""v2.33 — 多模态资产: 每节一个目录, 存分段 + 图 + 音频 + 视频."""
from multimedia.asset_store import (
    MultimediaError,
    MultimediaManifest,
    MultimediaStore,
    SegmentAsset,
    get_multimedia_store,
)

__all__ = [
    "MultimediaError",
    "MultimediaManifest",
    "MultimediaStore",
    "SegmentAsset",
    "get_multimedia_store",
]
