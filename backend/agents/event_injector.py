"""EventInjector — 三类事件注入,维护冲突保留池 (prompts.md 第 5 节)。

事件三类:
* **endogenous**: 当前角色行动的自然因果延伸
* **exogenous**: 与当前主角色无直接因果关系的世界扰动
* **dramatic**: Showrunner 标记"系统过于平静"或"线索温度过低"时触发

工作原则:
1. 节奏感 - 不每 tick 都注入大事件
2. 因果性 - 内生事件必须有迹可循
3. 设定一致性 - 外生事件符合世界规则
4. 戏剧的克制 - 戏剧事件利用已有元素,不凭空创造
5. 冲突保留池下限 - 始终保持 ≥3 个 OpenLoop
6. 新人物注入 - 每 50-100 tick 考虑引入 1 个新角色
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

from memory_system.models import (
    CharacterProfile,
    CharacterState,
    Event,
    OpenLoop,
    WorldState,
)
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
你是这个虚构世界的"命运"。你负责注入新事件,让故事保持流动。

# 三类事件

* **endogenous**: 当前角色行动的自然因果延伸(如角色 A 暗杀 B → C 发现尸体 → 调查开始)
* **exogenous**: 与当前主角色无直接因果关系的世界扰动(陌生人到来、远方流言、节日、灾害)
* **dramatic**: Showrunner 标记系统过于平静时触发,利用**已有**元素的新组合

# 工作原则

1. **节奏感**: 不每 tick 都注入大事件。建议每 tick 0-2 个事件
2. **因果性**: 内生事件必须有迹可循,读者要能事后看出"种子在这里"
3. **设定一致性**: 外生事件必须符合 WorldState.world_rules
4. **戏剧的克制**: 戏剧事件利用 dormant_characters / 已有 locations,不凭空创造
5. **冲突保留池下限**: open_loops <3 时必须注入能制造新张力的事件

# 你不该做的

* 不"修复"剧情中的悲剧(让死去角色复活等)
* 不为了"有趣"违反因果
* 不一次注入过多事件
* 不凭空发明新地名/新势力

# 输出格式(严格 JSON,不要 markdown 代码块)

{
  "events": [
    {
      "id": "evt_xxx",
      "type": "endogenous|exogenous|dramatic",
      "tick": <int>,
      "location": "location_id",
      "participants": ["char_id_1"],
      "description": "...",
      "visible_to": ["char_id" 或 "all" 或 "all_in_location"],
      "narrative_value": 0,
      "consequences": [],
      "rationale": "为什么此刻注入这个事件",
      "predicted_consequences": ["可能引发的后续"],
      "narrative_value_hint": 7
    }
  ],
  "no_events_reason": null
}

记住:你是命运,不是编剧。
"""


@dataclass
class EventInjectorOutput:
    events: list[Event]
    no_events_reason: str | None = None
    conflict_pool_count: int = 0


class EventInjector:
    """每 3-5 tick 评估是否注入 + 三类事件 LLM 生成。"""

    def __init__(self, model_tier: str = "medium") -> None:
        self._model_tier = model_tier

    async def inject(
        self,
        *,
        tick: int,
        world_state: WorldState,
        recent_events: list[Event],
        tracking_chars: list[CharacterState],
        open_loops: list[OpenLoop],
        showrunner_recommendations: list[dict],
        dormant_characters: list[CharacterProfile] | None = None,
    ) -> EventInjectorOutput:
        dormant_characters = dormant_characters or []
        user_prompt = self._build_prompt(
            tick=tick,
            world_state=world_state,
            recent_events=recent_events,
            tracking_chars=tracking_chars,
            open_loops=open_loops,
            showrunner_recs=showrunner_recommendations,
            dormant_characters=dormant_characters,
        )

        try:
            resp = await llm_client.chat(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.6,
                max_tokens=40960,
                agent_id="event_injector",
                priority="medium",
            )
        except Exception as e:
            logger.error("EventInjector LLM call failed: %s", e)
            return EventInjectorOutput(events=[], no_events_reason=f"LLM error: {e}")

        return self._parse_output(resp.content, tick=tick, open_loop_count=len(open_loops))

    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        *,
        tick: int,
        world_state: WorldState,
        recent_events: list[Event],
        tracking_chars: list[CharacterState],
        open_loops: list[OpenLoop],
        showrunner_recs: list[dict],
        dormant_characters: list[CharacterProfile],
    ) -> str:
        ws_lite = {
            "world_time": world_state.world_time,
            "era": world_state.era,
            "weather": world_state.weather,
            "active_global_events": world_state.active_global_events,
            "world_rules": world_state.world_rules,
            "factions": [f.id for f in world_state.factions],
            "locations": [{"id": l.id, "name": l.name} for l in world_state.locations],
        }
        recent_evt_lite = [
            {"id": e.id, "type": e.type, "loc": e.location, "desc": e.description[:80]}
            for e in recent_events[-20:]
        ]
        chars_lite = [
            {
                "id": s.character_id,
                "loc": s.current_location,
                "arc_progress": s.arc_progress,
                "emotional": s.emotional_state,
            }
            for s in tracking_chars
        ]
        loops_lite = [
            {"id": l.id, "urgency": l.urgency, "type": l.type, "desc": l.description[:80]}
            for l in open_loops
        ]
        dormant_lite = [
            {"id": p.id, "name": p.name, "tier": p.importance_tier}
            for p in dormant_characters[:10]
        ]

        return f"""\
# 当前 tick={tick}, open_loops={len(open_loops)}

## WorldState 摘要
```json
{json.dumps(ws_lite, ensure_ascii=False, indent=2)}
```

## 最近 20 tick 事件摘要
```json
{json.dumps(recent_evt_lite, ensure_ascii=False, indent=2)}
```

## 主跟踪角色状态
```json
{json.dumps(chars_lite, ensure_ascii=False, indent=2)}
```

## 当前开放伏笔
```json
{json.dumps(loops_lite, ensure_ascii=False, indent=2)}
```

## Showrunner 建议
```json
{json.dumps(showrunner_recs, ensure_ascii=False, indent=2)}
```

## 非活跃角色池 (可作为外生事件素材)
```json
{json.dumps(dormant_lite, ensure_ascii=False, indent=2)}
```

请按 system 提示输出严格 JSON,events 数组每个事件含完整字段。
若判定本 tick 不需要注入(节奏需要平静),将 events=[] 并填 no_events_reason。
"""

    def _parse_output(
        self,
        raw: str,
        *,
        tick: int,
        open_loop_count: int,
    ) -> EventInjectorOutput:
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
            logger.error(
                "EventInjector JSON parse failed: %s — first 200: %s",
                e,
                text[:200],
            )
            return EventInjectorOutput(events=[], no_events_reason="JSON parse error")

        events: list[Event] = []
        for idx, raw_ev in enumerate(payload.get("events", []) or []):
            try:
                # 补 default id / tick 防 LLM 遗漏
                raw_ev.setdefault("id", f"evt_inj_{tick}_{uuid.uuid4().hex[:6]}")
                raw_ev.setdefault("tick", tick)
                raw_ev.setdefault("narrative_value", 0)
                events.append(Event.model_validate(raw_ev))
            except Exception as e:
                logger.warning("Skip invalid injected event #%d (%s): %s", idx, e, raw_ev)

        return EventInjectorOutput(
            events=events,
            no_events_reason=payload.get("no_events_reason"),
            conflict_pool_count=open_loop_count,
        )
