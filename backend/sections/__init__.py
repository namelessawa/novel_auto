"""v2.24 — tick 驱动节存储 (与 legacy 节级管线的 GenerationPipeline 解耦)。

公共出口
--------
* ``TickSection`` / ``SectionStore`` — JSONL 后端 + Pydantic 契约
* ``get_section_store(novel_id)`` — per-novel 单例
"""

from sections.section_store import (
    SectionStore,
    TickSection,
    get_section_store,
)

__all__ = [
    "TickSection",
    "SectionStore",
    "get_section_store",
]
