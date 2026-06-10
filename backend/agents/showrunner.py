"""Showrunner — 宏观节奏与长期张力管理者 (prompts.md 第 8 节)。

> 你是这部无限连载的 showrunner,关注宏观节奏和长期张力。你不写一个字,
> 但你决定故事的呼吸。

监控指标:
* 冲突保留池数量(open_loops)
* 线索温度(open_loop 的 last_referenced_tick)
* 节奏曲线(最近 20 章 narrative_value 强度分布)
* 角色弧线进度(每个 A 级角色 arc_progress)
* 关系图变化率
* 近期事件多样性(重复模式检测交给 NoveltyCritic)

调度权力 - 不能改写情节,但可以:
* 标记"系统过于平静" → 触发 EventInjector
* 建议特定角色相遇
* 提议时间跳跃
* 提议代际更替
* 触发宏观重置
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from memory_system.models import OpenLoop
from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
你是这部无限连载的 showrunner — 不写一个字, 但决定故事的呼吸。

# 6 个判断维度 → 建议

1. **平静** — 连续 5 tick 无 narrative_value ≥ 7 / open_loops < 3
   → trigger_dramatic_event
2. **冷却线索** — 某 open_loop > 20 tick 未推进 → propose_meeting (相关
   角色相遇或事件激活)
3. **节奏失衡** — 连续 3 章高强度 → 低强度缓冲; 连续 5 章低强度必须有事
4. **角色弧线** — A 角 arc_progress > 0.85 → 安排完成或反转
5. **时代跳跃** — 一代主角弧线完成 → time_jump 1-5 年
6. **宏观重置** — 累计 > 1000 tick → macro_reset (战争/王朝崩塌)

你不能直接改写情节, 只能下建议给 EventInjector / 后续 tick 调度。

# 输出格式 (严格 JSON, 不要 markdown 代码块)

{
  "pacing_assessment": {
    "current_intensity": "medium",
    "recent_trend": "flat",
    "diagnosis": "连续 4 tick 平稳, 接近 dramatic 临界"
  },
  "conflict_pool_status": {"count": 4, "health": "ok"},
  "cold_threads": [
    {"loop_id": "loop_3", "stale_ticks": 25, "urgency": "high"}
  ],
  "arc_status": [
    {"character_id": "char_a", "progress": 0.87, "recommendation": "ripe for climax"}
  ],
  "recommendations": [
    {
      "type": "trigger_dramatic_event",
      "target": "loop_3",
      "rationale": "loop 已沉寂 25 tick, 应激活",
      "urgency": "high"
    }
  ]
}

字段值用枚举: intensity ∈ {low, medium, high}, trend ∈ {rising, flat,
falling}, health ∈ {ok, low, critical}, type ∈ {trigger_dramatic_event,
propose_meeting, time_jump, generation_shift, macro_reset}, urgency ∈
{low, medium, high}.
"""


@dataclass
class ShowrunnerOutput:
    pacing_assessment: dict = field(default_factory=dict)
    conflict_pool_status: dict = field(default_factory=dict)
    cold_threads: list[dict] = field(default_factory=list)
    arc_status: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)


class Showrunner:
    def __init__(self, model_tier: str = "medium") -> None:
        self._model_tier = model_tier

    async def assess(
        self,
        *,
        character_arcs: dict[str, float],
        open_loops: list[OpenLoop],
        recent_chapters: list[str],
        event_stats: dict,
        total_ticks: int,
        current_tick: int,
    ) -> ShowrunnerOutput:
        user_prompt = self._build_prompt(
            character_arcs=character_arcs,
            open_loops=open_loops,
            recent_chapters=recent_chapters,
            event_stats=event_stats,
            total_ticks=total_ticks,
            current_tick=current_tick,
        )
        try:
            resp = await llm_client.chat(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.4,
                # v2.38 (iter#9) — Showrunner 输出是 5-10 条建议 JSON, ~1500
                # tokens. 此前 30720 给 reasoning model 留出全填满空间.
                max_tokens=3072,
                agent_id="showrunner",
                priority="medium",
            )
        except Exception as e:
            logger.error("Showrunner LLM call failed: %s", e)
            return ShowrunnerOutput(
                pacing_assessment={"diagnosis": f"LLM error: {e}"},
                conflict_pool_status={
                    "count": len(open_loops),
                    "health": "low" if len(open_loops) < 3 else "ok",
                },
            )

        return self._parse_output(resp.content)

    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        *,
        character_arcs: dict[str, float],
        open_loops: list[OpenLoop],
        recent_chapters: list[str],
        event_stats: dict,
        total_ticks: int,
        current_tick: int,
    ) -> str:
        # 计算 cold_threads 候选 (字段可能为 None — or 0 兜底防 TypeError)
        cold_candidates = []
        for l in open_loops:
            stale = (current_tick - max(l.last_referenced_tick or 0, l.opened_tick or 0))
            if stale > 20:
                cold_candidates.append(
                    {
                        "loop_id": l.id,
                        "stale_ticks": stale,
                        "urgency": l.urgency,
                        "desc": l.description[:80],
                    }
                )

        # v2.38 (iter#21) — 紧凑视图: indent=2 → 不缩进 (节省 ~30% JSON 体积),
        # 最近章节摘要从 20 截到 10 (10 段足够看节奏趋势, 20 段有 ~2-3k chars
        # 净浪费), 开放伏笔 description 截 60 (从 80).
        loops_view = [
            {
                "id": l.id,
                "urgency": l.urgency,
                "type": l.type,
                "desc": l.description[:60],
                "stale_ticks": current_tick - max(
                    l.last_referenced_tick or 0, l.opened_tick or 0
                ),
            }
            for l in open_loops
        ]
        return f"""\
# 当前 tick={current_tick}, 累计 ticks={total_ticks}

## 角色弧线进度 (A/B 级)
{json.dumps(character_arcs, ensure_ascii=False)}

## 开放伏笔
{json.dumps(loops_view, ensure_ascii=False)}

## 候选冷线索 (>20 tick 未推进)
{json.dumps(cold_candidates, ensure_ascii=False)}

## 最近章节摘要 (last 10)
{chr(10).join(f'  - {s}' for s in recent_chapters[-10:]) or '  (尚无)'}

## 事件统计 (最近 50 tick)
{json.dumps(event_stats, ensure_ascii=False)}

按 system 提示输出严格 JSON, recommendations 按 urgency 降序.
"""

    def _parse_output(self, raw: str) -> ShowrunnerOutput:
        try:
            payload = parse_llm_json(raw)
        except json.JSONDecodeError as e:
            logger.error("Showrunner JSON parse failed: %s — raw[:300]=%r", e, raw[:300])
            return ShowrunnerOutput()

        return ShowrunnerOutput(
            pacing_assessment=dict(payload.get("pacing_assessment", {}) or {}),
            conflict_pool_status=dict(payload.get("conflict_pool_status", {}) or {}),
            cold_threads=list(payload.get("cold_threads", []) or []),
            arc_status=list(payload.get("arc_status", []) or []),
            recommendations=list(payload.get("recommendations", []) or []),
        )
