"""MemoryCompressor — 分层记忆压缩 L0→L1→L2→L3 (prompts.md 第 9 节)。

| 层级 | 距今         | 保留                                            |
|------|--------------|------------------------------------------------|
| L0   | <50 tick     | 完整: 对话、细节、所有事件                     |
| L1   | 50-500 tick  | 摘要: 发生了什么、谁参与、情感色彩、影响       |
| L2   | 500-5000     | 抽象: 关系状态、关键事件指纹                   |
| L3   | >5000        | 传说化: 转为世界设定/民间传说,允许失真         |

重要原则:
1. 当前开放伏笔的源头不可删除,无论多久远
2. 被 Narrator 多次引用的事件优先保留
3. 创伤性事件长期保留(在角色记忆中以"伤疤"形式存在)
4. 日常事件激进遗忘

每 50 tick 由 Orchestrator 调用一次。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from memory.summary_tree import SummaryTree
from memory_system.models import MemoryEntry
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_L0_L1 = """\
你负责把 L0(详细)事件压缩为 L1(摘要)。

保留:事件本质、参与者、情感色彩、长期影响
删除:对话细节、感官描写、不重要的旁观者
**绝不可删除**:current_open_loop_origin_ids 列表中标注的事件

# 输出格式 (严格 JSON, 不要 markdown 代码块)

{
  "l1_entries": [
    {
      "original_event_ids": ["evt_xxx"],
      "summary": "...",
      "emotional_tags": ["..."],
      "involved": ["char_id_1"],
      "importance": 6,
      "tick_range": [start, end]
    }
  ]
}
"""

SYSTEM_PROMPT_L1_L2 = """\
你负责把 L1(摘要)条目压缩为 L2(抽象)。

保留:关系状态的改变、技能/财产的获得、仍持续影响
删除:已无后续影响的事件
不删除:current_open_loop_origin_ids 标注的事件

# 输出格式 (严格 JSON, 不要 markdown 代码块)

{
  "l2_entries": [
    {
      "original_l1_ids": ["l1_xxx"],
      "summary": "...",
      "emotional_tags": ["..."],
      "involved": ["..."],
      "importance": 5,
      "tick_range": [start, end]
    }
  ]
}
"""


@dataclass
class MemoryCompressorOutput:
    l0_to_l1: list[MemoryEntry] = field(default_factory=list)
    l1_to_l2: list[MemoryEntry] = field(default_factory=list)
    l2_to_l3_legend_ids: list[str] = field(default_factory=list)
    preserved_specially: list[str] = field(default_factory=list)


L0_TO_L1_BOUNDARY = 50
L1_TO_L2_BOUNDARY = 500
L2_TO_L3_BOUNDARY = 5000


class MemoryCompressor:
    """LLM 驱动的分层压缩。共用 SummaryTree.legendize() 完成 L3 传说化。"""

    def __init__(
        self,
        summary_tree: SummaryTree,
        model_tier: str = "small",
    ) -> None:
        self._summary_tree = summary_tree
        self._model_tier = model_tier

    async def compress(
        self,
        *,
        current_tick: int,
        memory_entries: list[MemoryEntry],
        open_loop_origin_ids: list[str],
    ) -> MemoryCompressorOutput:
        """三层边界并行处理。

        ``memory_entries`` - Orchestrator 维护的当前所有 MemoryEntry,按 tier 分组处理。
        ``open_loop_origin_ids`` - 当前 OpenLoop 关联的源事件 id 集合,被压缩时保护。
        """
        protected = set(open_loop_origin_ids)
        out = MemoryCompressorOutput()

        # 按 tier 分组
        by_tier: dict[str, list[MemoryEntry]] = {"L0": [], "L1": [], "L2": []}
        for m in memory_entries:
            if m.tier in by_tier:
                by_tier[m.tier].append(m)

        # L0 → L1: 距今 >50 tick 且非保护的 L0
        l0_candidates = [
            m
            for m in by_tier["L0"]
            if current_tick - m.original_tick_range[1] > L0_TO_L1_BOUNDARY
            and m.protected_reason is None
        ]
        if l0_candidates:
            new_l1 = await self._compress_l0_to_l1(l0_candidates, protected)
            out.l0_to_l1 = new_l1
            out.preserved_specially.extend(
                m.id for m in l0_candidates if m.id in protected
            )

        # L1 → L2: 距今 >500 tick
        l1_candidates = [
            m
            for m in by_tier["L1"]
            if current_tick - m.original_tick_range[1] > L1_TO_L2_BOUNDARY
            and m.protected_reason is None
        ]
        if l1_candidates:
            new_l2 = await self._compress_l1_to_l2(l1_candidates, protected)
            out.l1_to_l2 = new_l2

        # L2 → L3 (legendize): 距今 >5000 tick
        l2_candidates = [
            m
            for m in by_tier["L2"]
            if current_tick - m.original_tick_range[1] > L2_TO_L3_BOUNDARY
            and m.protected_reason is None
        ]
        if l2_candidates:
            # legendize 用 SummaryTree.node_id 关联;此处用 m.id 作为节点 id 代理
            for m in l2_candidates:
                try:
                    legend = await self._summary_tree.legendize(
                        node_ids=[m.id],
                        classification="folk_tale",
                        importance=m.importance,
                    )
                    out.l2_to_l3_legend_ids.append(legend.legend_id)
                except Exception as e:
                    logger.warning("L2→L3 legendize failed for %s: %s", m.id, e)

        return out

    # ------------------------------------------------------------------

    async def _compress_l0_to_l1(
        self,
        entries: list[MemoryEntry],
        protected: set[str],
    ) -> list[MemoryEntry]:
        # 按 importance 分桶: 高重要性单独 compress,低重要性批量
        # 简化:每 10 条一批
        batches = [entries[i : i + 10] for i in range(0, len(entries), 10)]
        results: list[MemoryEntry] = []
        for batch in batches:
            user_prompt = self._build_compress_prompt(batch, protected, target_tier="L1")
            try:
                resp = await llm_client.chat(
                    system_prompt=SYSTEM_PROMPT_L0_L1,
                    user_prompt=user_prompt,
                    temperature=0.3,
                    max_tokens=40960,
                )
                results.extend(
                    self._parse_compressed(resp.content, target_tier="L1", fallback_entries=batch)
                )
            except Exception as e:
                logger.error("L0→L1 compress LLM failed for batch: %s", e)
                # 兜底:不压缩,保留原 L0 防数据丢失(后续 tick 重试)
        return results

    async def _compress_l1_to_l2(
        self,
        entries: list[MemoryEntry],
        protected: set[str],
    ) -> list[MemoryEntry]:
        batches = [entries[i : i + 10] for i in range(0, len(entries), 10)]
        results: list[MemoryEntry] = []
        for batch in batches:
            user_prompt = self._build_compress_prompt(batch, protected, target_tier="L2")
            try:
                resp = await llm_client.chat(
                    system_prompt=SYSTEM_PROMPT_L1_L2,
                    user_prompt=user_prompt,
                    temperature=0.3,
                    max_tokens=20480,
                )
                results.extend(
                    self._parse_compressed(resp.content, target_tier="L2", fallback_entries=batch)
                )
            except Exception as e:
                logger.error("L1→L2 compress LLM failed: %s", e)
        return results

    def _build_compress_prompt(
        self,
        batch: list[MemoryEntry],
        protected: set[str],
        target_tier: str,
    ) -> str:
        items = [
            {
                "id": m.id,
                "summary": m.summary,
                "involved": m.involved,
                "importance": m.importance,
                "tick_range": list(m.original_tick_range),
                "emotional_tags": m.emotional_tags,
                "protected": m.id in protected,
            }
            for m in batch
        ]
        return f"""\
# 待压缩条目 ({len(batch)} 条)

```json
{json.dumps(items, ensure_ascii=False, indent=2)}
```

# 受保护(open_loop 源头)的 id

{sorted(m.id for m in batch if m.id in protected) or '(无)'}

请输出严格 JSON,字段名遵守 system 提示。
目标层级: {target_tier}
"""

    def _parse_compressed(
        self,
        raw: str,
        target_tier: str,
        fallback_entries: list[MemoryEntry],
    ) -> list[MemoryEntry]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("MemoryCompressor parse failed (%s): %s", e, text[:200])
            return []

        key = "l1_entries" if target_tier == "L1" else "l2_entries"
        src_field = "original_event_ids" if target_tier == "L1" else "original_l1_ids"
        # v2.15 — fallback_entries 是本批输入的真实 id 集合, 用于:
        # 1. 过滤 LLM 幻觉的 source id (只接受真实存在的)
        # 2. 当 LLM 完全没返回 source id 时, 默认把本批全部认为是源
        # 否则 MemoryCompressor 输出的 source_ids 永远是空 → store 不退役旧记录。
        batch_ids = {m.id for m in fallback_entries}
        out: list[MemoryEntry] = []
        for idx, item in enumerate(payload.get(key, []) or []):
            try:
                tick_range = item.get("tick_range", [0, 0])
                raw_src = item.get(src_field, []) or []
                src_ids = [s for s in raw_src if isinstance(s, str) and s in batch_ids]
                if not src_ids:
                    # LLM 没标 / 标了全是幻觉 → 用整批兜底
                    src_ids = list(batch_ids)
                out.append(
                    MemoryEntry(
                        id=f"{target_tier.lower()}_{tick_range[0]}_{tick_range[1]}_{idx}",
                        tier=target_tier,  # type: ignore[arg-type]
                        original_tick_range=(int(tick_range[0]), int(tick_range[1])),
                        summary=str(item.get("summary", "")),
                        emotional_tags=list(item.get("emotional_tags", []) or []),
                        involved=list(item.get("involved", []) or []),
                        importance=int(item.get("importance", 5)),
                        source_ids=src_ids,
                    )
                )
            except Exception as e:
                logger.warning("Skip invalid compressed entry: %s — %s", e, item)
        return out
