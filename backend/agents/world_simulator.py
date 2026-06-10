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
import uuid
from dataclasses import dataclass
from typing import Any

from memory_system.models import Event, WorldState
from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
你是虚构世界的物理与社会规则引擎。你不创造剧情, 只推进规则。

# 任务

1. 推进时间 (world_time / current_season / weather)
2. 模拟自然变化与上 tick 事件的物理后果 (天气演变、火势蔓延、伤病演变、
   势力间资源流动、远方传闻); 自然事件 narrative_value ≤ 4 (背景级别)
3. **每 tick 至少产出 1-3 条 natural_events** — 即便世界状态变化轻微, 也
   要把环境里能被角色感知到的细节列成 event (脚下泥泞 / 远处汽笛 / 雾里
   人影一闪 / 街角告示牌新换 / 邻巷传来争吵). 这些事件是 CharacterAgent
   做决策的输入, 没有事件链路下游全部冻结.

# 禁区

不引入新设定 / 不创造新角色 / 不模拟具体角色决策 / 一切变化必须可量化。

# 输出格式 (严格 JSON, 不要 markdown 代码块, 不要省略号)
#
# v2.38 (iter#5) — 改成 DELTA 输出: world_state_delta 只列实际变更的字段,
# 未变的字段不要写出来. natural_events 必须非空 (见上 #3).

{
  "world_state_delta": {
    "world_time": 12,
    "current_season": "深秋",
    "weather": "酸雨加剧"
  },
  "natural_events": [
    {
      "type": "exogenous",
      "location": "<location_id>",
      "participants": [],
      "description": "雨势加大, 山道泥泞",
      "visible_to": ["all_in_location"],
      "narrative_value": 2,
      "consequences": []
    }
  ],
  "delta_summary": "本 tick 世界变化的一句话"
}

记住: 你是宇宙规则, 不是编剧。delta 只填变了的字段, 但 natural_events 必须有。
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
                # v2.38 (iter#5) — delta-output 让 4096 远够 (实测 ~800-1500
                # tokens). 此前 81920 给推理模型留了把 budget 全填满的空间.
                max_tokens=4096,
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
        # v2.38 (iter#5) — 紧凑视图: 只送 LLM 需要看的字段, 不再回灌整个
        # WorldState (locations/factions/world_rules 占体积大且每 tick 几乎
        # 不变). 模型按 delta 模式只输出变了的字段, 稳态字段沿用 prior.
        # v2.38 (iter#34) — events 20→10 (世界推进只需最近上下文; 20 含太多
        # 历史事件实际影响极小), description 80→60 字 (够说明事件性质).
        ws = world_state
        loc_names = ", ".join(loc.name for loc in ws.locations[:8]) or "(无)"
        events_compact = []
        for e in last_tick_events[:10]:
            events_compact.append(
                f"- [{e.type}] {e.description[:60]} "
                f"(loc={e.location or '-'}, value={e.narrative_value or 0})"
            )
        events_block = "\n".join(events_compact) or "(无)"
        return (
            f"# 世界当前快照 (volatile 字段)\n"
            f"world_time: {ws.world_time}  (本 tick 推到 {ws.world_time + time_step})\n"
            f"era: {ws.era}\n"
            f"current_season: {ws.current_season}\n"
            f"weather: {ws.weather}\n"
            f"地点: {loc_names}\n"
            f"\n# 上 tick 事件 ({len(last_tick_events)} 条)\n{events_block}\n\n"
            f"按系统提示输出 world_state_delta + natural_events + delta_summary。"
            f"world_state_delta 只列实际变了的字段, era/locations/factions/"
            f"world_rules 一般留空让系统沿用上 tick。"
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
        # v2.38 (iter#5) — 优先读 world_state_delta (delta-output, 只列变了
        # 的字段, 与 prior 合并). 老 new_world_state (全量回传) 仍支持作
        # backward-compatible 兜底.
        delta_raw = payload.get("world_state_delta")
        full_raw = payload.get("new_world_state")
        try:
            if delta_raw and isinstance(delta_raw, dict):
                # delta 模式: prior + LLM 给的字段
                base = prior_world_state.model_dump(mode="json")
                # 只接受 delta 里非空的字段, 防 LLM 把 era="" 这种值覆盖掉.
                # v2.38 (iter#5 review fix) — 用 None / "" / [] / {} 精确判, 不
                # 用 truthy 测试: world_time=0 / False 之类合法零值不应被当空.
                for k, v in delta_raw.items():
                    if v is None:
                        continue
                    if isinstance(v, (str, list, dict)) and len(v) == 0:
                        continue
                    base[k] = v
                # world_time 兜底 — delta 显式没给 (键缺失或 None) 才补 prior +
                # time_step. v2.38 (iter#5 review fix) — 此前用 `not delta_raw.
                # get("world_time")` 把 0 误判为缺失, 会双倍推进时间.
                if delta_raw.get("world_time") is None:
                    base["world_time"] = prior_world_state.world_time + time_step
                new_ws = WorldState.model_validate(base)
            elif full_raw:
                new_ws = WorldState.model_validate(full_raw)
            else:
                # 两个字段都没有, 仅推时间
                new_ws = prior_world_state.model_copy(
                    update={"world_time": prior_world_state.world_time + time_step}
                )
        except Exception as e:
            logger.warning("WorldSimulator state parse invalid (%s),保留旧值仅推进时间", e)
            new_ws = prior_world_state.model_copy(
                update={"world_time": prior_world_state.world_time + time_step}
            )

        # v2.35 — 稳态字段反清空保护 (delta 模式下其实已经天然成立, 但保留作
        # 全量回传路径的兜底).
        merged_updates: dict = {}
        if not new_ws.locations and prior_world_state.locations:
            merged_updates["locations"] = prior_world_state.locations
        if not new_ws.factions and prior_world_state.factions:
            merged_updates["factions"] = prior_world_state.factions
        if not new_ws.world_rules and prior_world_state.world_rules:
            merged_updates["world_rules"] = prior_world_state.world_rules
        if merged_updates:
            logger.warning(
                "WorldSimulator dropped stable fields (locations/factions/rules), "
                "restoring from prior: %s",
                list(merged_updates.keys()),
            )
            new_ws = new_ws.model_copy(update=merged_updates)

        # natural_events 解析(逐条尝试,跳过坏数据)
        # v2.34 — 兜底 LLM 常见漏写:
        #   * 缺 ``type`` 字段 → 自然事件按定义都是 ``exogenous``, 注入而非靠
        #     Event.model_validate 抛 missing-field error 整条丢弃
        #   * id 撞车 (``evt_001`` / ``evt_002`` 跨 tick 重复, 上 tick log 会被
        #     UNIQUE 约束顶掉) → 强制重写为 ``evt_nat_{tick}_{idx}_{6位 hex}``,
        #     保留 LLM 原 id 写入 description 末尾仅供诊断不丢失
        events: list[Event] = []
        prior_world_time = prior_world_state.world_time + time_step
        for idx, raw_ev in enumerate(payload.get("natural_events", []) or []):
            try:
                if isinstance(raw_ev, dict):
                    raw_ev.setdefault("type", "exogenous")
                    raw_ev.setdefault("tick", prior_world_time)
                    # 强制 unique id, 避免 LLM 反复输出 evt_001/evt_002
                    raw_ev["id"] = (
                        f"evt_nat_{prior_world_time}_{idx}_{uuid.uuid4().hex[:6]}"
                    )
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
