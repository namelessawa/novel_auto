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
    StatePatch,
    WorldState,
)
from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
你是虚构世界的"命运" — 注入新事件让故事保持流动。

# 三类事件

* **endogenous** — 当前行动的自然因果延伸 (A 暗杀 B → C 发现尸体 → 调查)
* **exogenous** — 与主角色无直接因果的世界扰动 (陌生人、远方流言、灾害)
* **dramatic** — Showrunner 标记平静时, 用**已有**元素的新组合

# 原则

1. 节奏: 每 tick 0-2 事件, 不每次都大事件
2. 因果: 内生事件有迹可循, 读者事后能看出"种子在这里"
3. 设定一致: 外生事件符合 world_rules
4. 戏剧克制: 用 dormant_characters / 已有 locations, 不凭空创造
5. open_loops < 3 时必须注入能造张力的事件 (即便要新种)
6. **伏笔容量平衡 (Phase 2 Stage 3 长程数据反推)**: 当 stale_loops ≥ 3
   (即有 ≥3 条 open_loop 超过 20 tick 未推进), 本 tick **优先生成激活
   stale loop 的事件**, 不再新种伏笔. 注入事件描述里可以隐式引用 stale
   loop 的关键词 (人物 / 地点 / 物件), 让 Narrator 后续把它写明.
7. **cold_thread urgency boost (Phase 2 Stage 3 候选 #3)**: 若 Showrunner
   建议含 `type=trigger_dramatic_event` 或 `propose_meeting`, 并指向具体
   cold_thread (stale_ticks > 20), 注入的事件 narrative_value_hint **必须
   ≥ 7** — 让 Narrator critic gate 真正触发, 用关键节拍的全质量复活 cold
   thread. 普通注入 ≤ 5 即可. (Stage 3 数据: avg_urgency 7.0 → 6.11 持续
   下降, 新伏笔越来越弱; 此规则反着把激活类事件的 hint 拉高.)
   **若 recommendations 为空 (calm tick / Showrunner 未跑) 则本规则不
   适用** — 不要自己脑补 cold_thread 然后给所有事件 hint=7.

# 禁区

不复活死人 / 不为"有趣"违反因果 / 不一次注入过多 / 不发明新地名势力。

# state_patches (v2.18 Phase 8) — 强因果立即生效

爆炸波及 / 瘟疫降临 / 当场死亡 这类**外部权威**事件: 角色不会自己填"我
受伤了" (那是角色意志, 跟"被 NPC 炸伤"是两件事). 用 state_patches 让
Orchestrator 阶段 5d 直接 patch CharacterState / WorldState.

格式 — target_type ∈ {character, world}, target_id (character 时为
char_id, world 时空串), ops 是 list of {field, op ∈ {set/add/append/
remove}, value}. 仅强因果必须立即生效时填; 一般事件不需要.

# 输出格式 (严格 JSON, 不要 markdown 代码块)

{
  "events": [
    {
      "id": "evt_xxx",
      "type": "endogenous",
      "tick": <int>,
      "location": "<location_id>",
      "participants": ["<char_id>"],
      "description": "...",
      "visible_to": ["all_in_location"],
      "narrative_value": 0,
      "consequences": [],
      "rationale": "为什么此刻注入",
      "predicted_consequences": ["可能引发的后续"],
      "narrative_value_hint": 7
    }
  ],
  "state_patches": [
    // 仅强因果事件填; 一般事件留 [] 不填
    {
      "source_agent": "event_injector",
      "source_event_id": "evt_xxx",
      "target_type": "character",
      "target_id": "<char_id>",
      "ops": [{"field": "status_effects", "op": "append", "value": "受伤"}],
      "confidence": 0.9,
      "reason": "事件直接结果"
    }
  ],
  "no_events_reason": null
}

记住: 你是命运, 不是编剧。
"""


@dataclass
class EventInjectorOutput:
    events: list[Event]
    no_events_reason: str | None = None
    conflict_pool_count: int = 0
    # v2.18 Phase 8 — 强因果事件 (爆炸 / 瘟疫 / 死亡) 可携带 StatePatch 立即生效,
    # 避免借道 character_action (那是角色意志, 不该承担"被 NPC 炸伤"这种外部权威)。
    state_patches: list[StatePatch] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.state_patches is None:
            self.state_patches = []


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
                # v2.38 (iter#9) — Event injection 输出是 1-3 events + 可选
                # state_patches, ~2000-3000 tokens. 40960 是反推理浪费值.
                max_tokens=4096,
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
            {
                "id": l.id,
                "urgency": l.urgency,
                "type": l.type,
                "desc": l.description[:80],
                # Phase 2 Stage 4 (iter#90) — surface stale 状态供 LLM 决策.
                "stale_ticks": tick - max(
                    getattr(l, "last_referenced_tick", 0) or 0,
                    getattr(l, "opened_tick", 0) or 0,
                ),
            }
            for l in open_loops
        ]
        stale_count = sum(1 for l in loops_lite if l["stale_ticks"] > 20)
        dormant_lite = [
            {"id": p.id, "name": p.name, "tier": p.importance_tier}
            for p in dormant_characters[:10]
        ]

        # v2.38 (iter#22) — 紧凑视图: json indent 去掉, ```json 围栏去掉
        # (system prompt 已说严格 JSON 输出, fence 是冗余). 节省 ~40% prompt
        # 体积.
        # v2.38 (iter#90) — header 加 stale_loops 显式提示, 触发 system
        # prompt 原则 #6 (优先关旧 不新种).
        return f"""\
# 当前 tick={tick}, open_loops={len(open_loops)}, stale_loops={stale_count} (> 20 tick 未推进)

## WorldState 摘要
{json.dumps(ws_lite, ensure_ascii=False)}

## 最近 20 tick 事件摘要
{json.dumps(recent_evt_lite, ensure_ascii=False)}

## 主跟踪角色状态
{json.dumps(chars_lite, ensure_ascii=False)}

## 当前开放伏笔
{json.dumps(loops_lite, ensure_ascii=False)}

## Showrunner 建议
{json.dumps(showrunner_recs, ensure_ascii=False)}

## 非活跃角色池 (可作为外生事件素材)
{json.dumps(dormant_lite, ensure_ascii=False)}

按 system 提示输出严格 JSON, events 含完整字段. 不需注入时 events=[]
并填 no_events_reason.
"""

    def _parse_output(
        self,
        raw: str,
        *,
        tick: int,
        open_loop_count: int,
    ) -> EventInjectorOutput:
        try:
            payload = parse_llm_json(raw)
        except json.JSONDecodeError as e:
            logger.error(
                "EventInjector JSON parse failed: %s — raw[:300]=%r",
                e,
                raw[:300],
            )
            return EventInjectorOutput(events=[], no_events_reason="JSON parse error")

        events: list[Event] = []
        for idx, raw_ev in enumerate(payload.get("events", []) or []):
            # v2.38 (iter#40) — LLM 偶发把 event 写成 str (description-only)
            # 而非 dict, 与 newly_opened_loops / OpenLoop 同症. 加 isinstance.
            if isinstance(raw_ev, str):
                raw_ev = {"description": raw_ev[:200]}
            elif not isinstance(raw_ev, dict):
                logger.warning(
                    "Skip invalid injected event #%d (not dict/str): %r", idx, raw_ev
                )
                continue
            try:
                # 补 default id / tick 防 LLM 遗漏
                raw_ev.setdefault("id", f"evt_inj_{tick}_{uuid.uuid4().hex[:6]}")
                raw_ev.setdefault("tick", tick)
                raw_ev.setdefault("narrative_value", 0)
                events.append(Event.model_validate(raw_ev))
            except Exception as e:
                logger.warning("Skip invalid injected event #%d (%s): %s", idx, e, raw_ev)

        # v2.18 Phase 8 — 解析 state_patches; 单条失败跳过, 不影响其他
        state_patches: list[StatePatch] = []
        for idx, raw_patch in enumerate(payload.get("state_patches", []) or []):
            try:
                state_patches.append(StatePatch.model_validate(raw_patch))
            except Exception as e:
                logger.warning(
                    "Skip invalid state_patch #%d (%s): %s", idx, e, raw_patch
                )

        return EventInjectorOutput(
            events=events,
            no_events_reason=payload.get("no_events_reason"),
            conflict_pool_count=open_loop_count,
            state_patches=state_patches,
        )
