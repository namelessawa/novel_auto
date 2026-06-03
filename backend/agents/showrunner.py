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
from nf_core.json_utils import strip_code_fence
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
你是这部无限连载的 showrunner。你不写一个字,但你决定故事的呼吸。

# 判断维度

## 1. 系统是否过于平静
标志: 连续 5 tick 无 narrative_value ≥ 7 的事件 / 开放伏笔数 <3
应对: 建议 EventInjector 触发戏剧事件

## 2. 是否有冷却的线索
标志: 某开放伏笔 >20 tick 未推进
应对: 建议安排相关角色相遇/事件激活该线索

## 3. 节奏是否平衡
标志: 连续 3 章都是高强度冲突 → 建议低强度章节缓冲
反之: 连续 5 章低强度后必须有事

## 4. 角色弧线是否需要转折
标志: 某 A 级角色 arc_progress >0.85 → 建议安排完成或反转的事件

## 5. 是否到了时间跳跃窗口
标志: 一代主角弧线已完成,阶段性饱和 → 建议跳跃 1-5 年

## 6. 是否需要宏观重置
标志: 累计 >1000 tick,世界状态极其复杂 → 建议战争/王朝崩塌

# 你的调度权力(不能直接改写情节)

* 标记"过于平静" → EventInjector
* 建议特定角色相遇(通过环境事件)
* 提议时间跳跃
* 提议代际更替
* 触发宏观重置

# 输出格式(严格 JSON, 不要 markdown 代码块)

{
  "pacing_assessment": {
    "current_intensity": "low|medium|high",
    "recent_trend": "rising|flat|falling",
    "diagnosis": "..."
  },
  "conflict_pool_status": {
    "count": 4,
    "health": "ok|low|critical"
  },
  "cold_threads": [
    {"loop_id": "...", "stale_ticks": 25, "urgency": "high"}
  ],
  "arc_status": [
    {"character_id": "...", "progress": 0.87, "recommendation": "ripe for climax"}
  ],
  "recommendations": [
    {
      "type": "trigger_dramatic_event|propose_meeting|time_jump|generation_shift|macro_reset",
      "target": "...",
      "rationale": "...",
      "urgency": "low|medium|high"
    }
  ]
}
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
                max_tokens=30720,
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
        # 计算 cold_threads 候选
        cold_candidates = []
        for l in open_loops:
            stale = (current_tick - max(l.last_referenced_tick, l.opened_tick))
            if stale > 20:
                cold_candidates.append(
                    {
                        "loop_id": l.id,
                        "stale_ticks": stale,
                        "urgency": l.urgency,
                        "desc": l.description[:80],
                    }
                )

        return f"""\
# 当前 tick={current_tick}, 累计 ticks={total_ticks}

## 角色弧线进度 (A/B 级)
```json
{json.dumps(character_arcs, ensure_ascii=False, indent=2)}
```

## 开放伏笔
```json
{json.dumps([{"id": l.id, "urgency": l.urgency, "type": l.type, "desc": l.description[:80], "stale_ticks": current_tick - max(l.last_referenced_tick, l.opened_tick)} for l in open_loops], ensure_ascii=False, indent=2)}
```

## 候选冷线索 (>20 tick 未推进)
```json
{json.dumps(cold_candidates, ensure_ascii=False, indent=2)}
```

## 最近章节摘要 (last 20)
{chr(10).join(f'  - {s}' for s in recent_chapters[-20:]) or '  (尚无)'}

## 事件统计 (最近 50 tick)
```json
{json.dumps(event_stats, ensure_ascii=False, indent=2)}
```

请按 system 提示输出严格 JSON,recommendations 数组按 urgency 降序。
"""

    def _parse_output(self, raw: str) -> ShowrunnerOutput:
        text = strip_code_fence(raw)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("Showrunner JSON parse failed: %s — first 200: %s", e, text[:200])
            return ShowrunnerOutput()

        return ShowrunnerOutput(
            pacing_assessment=dict(payload.get("pacing_assessment", {}) or {}),
            conflict_pool_status=dict(payload.get("conflict_pool_status", {}) or {}),
            cold_threads=list(payload.get("cold_threads", []) or []),
            arc_status=list(payload.get("arc_status", []) or []),
            recommendations=list(payload.get("recommendations", []) or []),
        )
