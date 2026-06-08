"""WorldSimulator — 虚构世界的物理与社会规则引擎。

对应 ``infinite-novel-multiagent-prompts.md`` 第 4 节。每 tick 调用一次,
任务严格限定为推进规则,不创造剧情:

* 时间 / 季节 / 天气演变(按概率分布)
* 自然事件(潮汐、月相、罕见现象)
* 社会规模的演变(资源流动、领土微调、技术演进、远方传闻)
* 上 tick 事件的物理后果(火势蔓延、伤病演变、经济连锁)

严格禁区:
* 不引入新的世界设定(魔法规则/地理/种族)
* 不创造角色(那是 EventInjector 的工作)
* 不模拟具体角色决策(那是 CharacterAgent)

模型层级: ``small`` (Haiku 4.5)。WorldSimulator 任务模板化、约束多,小模型够用。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from memory_system.models import Event, WorldState
from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
你是一个虚构世界的物理与社会规则引擎。你不创造剧情,只推进规则。

# 你的任务

1. 推进时间(更新 world_time / current_season / weather)
2. 模拟自然变化:天气演变(依据季节/地理/概率)、自然事件(潮汐、月相、罕见现象)
3. 模拟社会规模的演变:势力间的资源流动、领土微调、技术与文化的缓慢演进、远方传闻
4. 应用上 tick 事件的物理后果:火灾蔓延、建筑倒塌、伤病演变、经济连锁

# 严格约束

* 不引入新的世界设定(魔法规则、地理、新种族)
* 不创造新角色(那是 Event Injector 的工作)
* 不模拟具体角色的决策(那是 Character Agent 的工作)
* 一切变化必须可量化或可描述为状态字段的修改
* 自然事件 narrative_value 通常 ≤ 4(背景级别)

# 输出格式(严格 JSON, 不要 markdown 代码块)

{
  "new_world_state": { 完整的 WorldState 对象,字段名同输入 },
  "natural_events": [
    {
      "id": "evt_xxx",
      "type": "exogenous",
      "tick": <int>,
      "location": "location_id",
      "participants": [],
      "description": "雨势加大,山道泥泞",
      "visible_to": ["all_in_location"],
      "narrative_value": 2,
      "consequences": []
    }
  ],
  "delta_summary": "本 tick 世界变化的一句话总结"
}

记住:你是宇宙规则,不是编剧。
"""


@dataclass(frozen=True)
class WorldSimulatorOutput:
    new_world_state: WorldState
    natural_events: list[Event]
    delta_summary: str


class WorldSimulator:
    """每 tick 推进 WorldState 并产出自然事件。"""

    def __init__(self, model_tier: str = "small") -> None:
        """``model_tier`` 仅作标签记录, 不影响实际模型选择。

        模型选择由 ``LLMClient`` 的 provider 配置决定 (config.json llm.* 或
        .env LLM_PROVIDER); v2.18 Phase 6 起, 个别调用点 (CharacterAgent) 会
        通过 ``llm_client.chat(model_override=...)`` 按 tick 临时降级。
        WorldSimulator 当前不参与降级路径, 始终用默认 provider model。
        """
        self._model_tier = model_tier

    async def simulate(
        self,
        world_state: WorldState,
        last_tick_events: list[Event],
        time_step: int = 1,
    ) -> WorldSimulatorOutput:
        """主入口 - Orchestrator 阶段 1 调用。"""
        user_prompt = self._build_user_prompt(world_state, last_tick_events, time_step)
        try:
            resp = await llm_client.chat(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=81920,
                agent_id="world_simulator",
                priority="medium",
            )
        except Exception as e:
            logger.error("WorldSimulator LLM call failed: %s", e)
            # 兜底:推进 world_time + time_step,其他状态不变,无 natural events
            return self._fallback_output(world_state, time_step)

        return self._parse_output(resp.content, world_state, time_step)

    # ------------------------------------------------------------------

    def _build_user_prompt(
        self, world_state: WorldState, last_tick_events: list[Event], time_step: int
    ) -> str:
        ws_dump = world_state.model_dump(mode="json")
        events_dump = [e.model_dump(mode="json") for e in last_tick_events]
        return (
            f"# 当前 WorldState\n```json\n{json.dumps(ws_dump, ensure_ascii=False, indent=2)}\n```\n\n"
            f"# 上 tick 所有事件 ({len(events_dump)} 条)\n```json\n"
            f"{json.dumps(events_dump, ensure_ascii=False, indent=2)}\n```\n\n"
            f"# 时间步长\n{time_step} tick(请将 world_time + {time_step})\n\n"
            "请按系统提示要求,输出严格 JSON 格式的 new_world_state、natural_events、delta_summary。"
        )

    def _parse_output(
        self,
        raw: str,
        prior_world_state: WorldState,
        time_step: int,
    ) -> WorldSimulatorOutput:
        try:
            payload: dict[str, Any] = parse_llm_json(raw)
        except json.JSONDecodeError as e:
            logger.error("WorldSimulator JSON parse failed: %s — raw[:300]=%r", e, raw[:300])
            return self._fallback_output(prior_world_state, time_step)

        # WorldState 解析
        ws_raw = payload.get("new_world_state") or {}
        try:
            new_ws = WorldState.model_validate(ws_raw)
        except Exception as e:
            logger.warning("WorldSimulator new_world_state invalid (%s),保留旧值仅推进时间", e)
            new_ws = prior_world_state.model_copy(
                update={"world_time": prior_world_state.world_time + time_step}
            )

        # natural_events 解析(逐条尝试,跳过坏数据)
        events: list[Event] = []
        for raw_ev in payload.get("natural_events", []) or []:
            try:
                events.append(Event.model_validate(raw_ev))
            except Exception as e:
                logger.warning("Skip invalid natural event (%s): %s", e, raw_ev)

        delta_summary = str(payload.get("delta_summary", "")).strip() or "(无显著变化)"
        return WorldSimulatorOutput(
            new_world_state=new_ws,
            natural_events=events,
            delta_summary=delta_summary,
        )

    @staticmethod
    def _fallback_output(
        prior: WorldState, time_step: int
    ) -> WorldSimulatorOutput:
        """LLM 失败时的安全兜底:仅推进 world_time,世界其他状态不变。"""
        new_ws = prior.model_copy(update={"world_time": prior.world_time + time_step})
        return WorldSimulatorOutput(
            new_world_state=new_ws,
            natural_events=[],
            delta_summary="WorldSimulator LLM 不可用,仅推进时间。",
        )
