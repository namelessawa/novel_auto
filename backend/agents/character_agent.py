"""CharacterAgent — 单角色自主决策。

对应 ``infinite-novel-multiagent-prompts.md`` 第 6 节。每个活跃角色一个实例,
绑定一份不变的 ``CharacterProfile``,在每 tick 接受 ``CharacterState`` 和该
角色**可见的事件子集**,产出 ``CharacterAction``。

核心戏剧根基(prompts 第 0 节第 4 条):
> 角色只能用自己知道的信息。最容易塌陷的失败模式是角色"什么都知道"。

所以本类有两层 know-限制:
1. ``_filter_visible_events()`` 只保留 ``visible_to`` 含本角色 id 的事件
2. prompt 模板只暴露 ``state.known_facts`` 和过滤后的事件,不暴露 WorldState 全貌

并发控制:
``batch_decide()`` 用 ``asyncio.Semaphore(CHARACTER_AGENT_CONCURRENCY)``,默认 3,
保护下游 LLM API 限速。可通过环境变量调整。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from memory_system.models import (
    CharacterAction,
    CharacterProfile,
    CharacterState,
    Event,
    Goal,
    RelationshipDelta,
)
from nf_core.llm_client import llm_client

# v2.16 — 连续 ≥3 个英文单词 (≥2 个字母, 空格分隔) 视为语言污染。
# 容忍单个英文专有名词 (角色名缩写、商标), 拦截大段英文动作描述。
_ENGLISH_RUN_PATTERN = re.compile(r"(?:\b[A-Za-z]{2,}\b\s+){2}\b[A-Za-z]{2,}\b")

logger = logging.getLogger(__name__)


def _coerce_int(v: Any, default: int = 0) -> int:
    """LLM 偶尔把 money_delta 写成 '50' / '+50' / '50元' / None, 容错转 int。
    超出 [-1_000_000, 1_000_000] 被 Pydantic 在外层 clamp / reject。
    """
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    if v is None or v == "":
        return default
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+", v)
        return int(m.group(0)) if m else default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _default_concurrency() -> int:
    raw = os.environ.get("CHARACTER_AGENT_CONCURRENCY", "3").strip()
    try:
        n = int(raw)
        return n if n > 0 else 3
    except ValueError:
        return 3


SYSTEM_PROMPT_TEMPLATE = """\
你扮演角色: {name}

# 你的档案(恒定)

身份: {role}, {age}岁
重要性: {importance_tier} 级 ({tier_explain})
性格: {personality}
外貌: {appearance}
说话风格: {speech_style}
核心价值: {core_values}
深层恐惧: {fears}
深层欲望: {desires}

# 决策原则

1. 行动必须符合性格(寡言的人不会突然滔滔不绝)
2. 行动必须基于已知信息(不知道的事不能据此决策)
3. 优先推进当前目标,但允许被突发事件改变优先级
4. 允许说"今天没什么可做的"(日常 tick 可维持日常活动)
5. 保留秘密 - 在不合适的场合不脱口而出
6. 如情节让你做"绝对不会做"的事,在 flags 中标出

# 语言约束(强制)

* 所有可读文本字段 (description / dialogue_spoken / intent / internal_monologue /
  emotional_shift / newly_learned / newly_speculated / new_goals.description /
  relationship_deltas.history_entry) 必须使用**中文**
* 动作描述用中文动词, 不允许英文动作短语
* 错误示例 ❌: "Diana uses sword to attack" / "alice moves to forest"
* 正确示例 ✅: "戴安娜挥剑刺向北门守卫" / "爱丽丝沿溪流向西踏入林间"
* JSON 字段名 (key) 保留英文; 仅字段值用中文
* 专有名词 (角色名 / 地点名) 若已是中文则保持; 否则按系统已建立的命名

# 硬状态转移(本 tick 你身体上发生了什么)

如果你的行动会改变下列状态, 必须**显式**填入相应字段, 不然世界不知道你动了:

* ``new_location`` — 移动到的目标 location_id; 不移动留空字符串
* ``inventory_added`` / ``inventory_removed`` — 本 tick 获得 / 失去的物品 (字符串数组)
* ``status_added`` / ``status_removed`` — 本 tick 新增 / 解除的状态效果 (受伤 / 疲惫 / 中毒 / 治愈)
* ``relationship_deltas`` — 与他人关系的增量, 格式 {{"对方id": {{"trust_delta": -2, "new_type": "敌人", "history_entry": "..."}}}}
* ``money_delta`` — 本 tick 钱币变化, +赚/抢/收 / -花/支/失; 仅 buy/sell/pay/earn/steal/loot/give 等经济动作下填非零, 否则保持 0

留白字段比胡乱填好。但**真发生了的转移必须落字段**, 不能只写在 description 里。

# 输出格式(严格 JSON, 不要 markdown 代码块)

{{
  "action_type": "move|speak|fight|investigate|wait|...",
  "target": "目标(人物/地点/物品)",
  "description": "具体动作的中文自然语言描述",
  "dialogue_spoken": "如有说话,原话(用你的说话风格)" 或 null,
  "dialogue_to_whom": ["..."],
  "intent": "你的真实意图(其他人不知道)",
  "internal_monologue": "你此刻最重要的一个想法(1-2 句)",
  "emotional_shift": "本 tick 你的情绪变化(如有)",
  "completed_goal_ids": ["..."],
  "new_goals": [{{"id": "g_xxx", "description": "...", "priority": 5, "progress": 0.0, "obstacles": []}}],
  "abandoned_goal_ids": ["..."],
  "newly_learned": ["你本 tick 新了解的事"],
  "newly_speculated": ["你的新猜测"],
  "flags": [],
  "new_location": "loc_xxx 或空字符串",
  "inventory_added": [],
  "inventory_removed": [],
  "status_added": [],
  "status_removed": [],
  "relationship_deltas": {{}},
  "money_delta": 0
}}

记住:你不是叙述者。你不"写小说"。你只**是**这个角色,做这个角色会做的事。
"""

_TIER_EXPLAIN = {
    "A": "深度建模,主角候选",
    "B": "重要配角",
    "C": "NPC,仅标签建模",
}


class CharacterAgent:
    """单角色决策代理。一个 profile 对应一个长期存在的实例。"""

    def __init__(self, profile: CharacterProfile, model_tier: str = "medium") -> None:
        """``model_tier`` A 级建议 'strong' (Sonnet),B 级 'medium',C 级不应实例化。

        当前 model_tier 仅记录,真实模型切换在 P1 集成。
        """
        self._profile = profile
        self._model_tier = model_tier
        # v2.16 — 观测优先级: A 级角色推动主线 → critical (Narrator 都要看), B 级 → medium。
        # 这让 TokenBudget 在紧预算时优先保 A 角的决策, 避免主角"哑火"。
        self._priority = "critical" if profile.importance_tier == "A" else "medium"
        self._system_prompt = self._build_system_prompt()

    @property
    def profile(self) -> CharacterProfile:
        return self._profile

    @property
    def character_id(self) -> str:
        return self._profile.id

    @property
    def model_tier(self) -> str:
        return self._model_tier

    # ------------------------------------------------------------------

    async def decide(
        self,
        state: CharacterState,
        all_tick_events: list[Event],
    ) -> CharacterAction:
        """对本 tick 做出行动决策。``all_tick_events`` 会被自动过滤为可见子集。"""
        visible = self._filter_visible_events(all_tick_events)
        user_prompt = self._build_user_prompt(state, visible)
        try:
            resp = await llm_client.chat(
                system_prompt=self._system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=30720,
                agent_id=f"character_agent:{self._profile.id}",
                priority=self._priority,
            )
        except Exception as e:
            logger.error("CharacterAgent[%s] LLM call failed: %s", self._profile.id, e)
            return self._fallback_action()

        return self._parse_action(resp.content)

    def _filter_visible_events(self, events: list[Event]) -> list[Event]:
        """戏剧性根基:角色只看到 ``visible_to`` 含自身 id 的事件。"""
        cid = self._profile.id
        return [
            e
            for e in events
            if cid in e.visible_to or "all" in e.visible_to or "all_in_location" in e.visible_to
        ]

    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        p = self._profile
        return SYSTEM_PROMPT_TEMPLATE.format(
            name=p.name,
            role=p.role,
            age=p.age,
            importance_tier=p.importance_tier,
            tier_explain=_TIER_EXPLAIN.get(p.importance_tier, ""),
            personality=p.personality or "(未指定)",
            appearance=p.appearance or "(未指定)",
            speech_style=p.speech_style or "(未指定)",
            core_values=", ".join(p.core_values) or "(未指定)",
            fears=", ".join(p.fears) or "(未指定)",
            desires=", ".join(p.desires) or "(未指定)",
        )

    def _build_user_prompt(
        self, state: CharacterState, visible_events: list[Event]
    ) -> str:
        # 关系网渲染:只显示对方 id + 关系类型 + 信任度 + 历史一句话
        rels_text = "(无关系记录)"
        if state.relationships:
            rels_text = "\n".join(
                f"  - {rel.with_character_id}: {rel.type}, "
                f"信任 {rel.trust:+d}, 历史: {rel.history_summary[:60]}"
                for rel in state.relationships.values()
            )

        goals_text = "(无明确目标)"
        if state.current_goals:
            goals_text = "\n".join(
                f"  - [{g.priority}] {g.description} (进度 {g.progress:.0%})"
                for g in state.current_goals
            )

        events_text = "(本 tick 你周围没有可感知的事件)"
        if visible_events:
            events_text = "\n".join(
                f"  - [{e.id} @ {e.location}] {e.description}"
                for e in visible_events
            )

        return f"""\
# 你的当前状态

【所在位置】{state.current_location or '(未指定)'}
【情绪】{state.emotional_state}
【身体状态】{', '.join(state.status_effects) or '正常'}
【手头物品】{', '.join(state.inventory) or '(无)'}
【钱币】{state.money}

# 你的当前短期目标

{goals_text}

# 你的长期弧线目标

{state.arc_goal or '(尚未明确)'} (当前进度 {state.arc_progress:.0%})

# 你的知识范围(极其重要)

【你亲历过的事 / 已知信息】
{chr(10).join(f'  - {f}' for f in state.known_facts) or '  (无)'}

【你保守的秘密】
{chr(10).join(f'  - {s}' for s in state.secrets_kept) or '  (无)'}

# 你的关系网

{rels_text}

# 本 tick 你能感知到的事件

{events_text}

请基于你的目标、性格、当前所知信息,决定本 tick 你**采取的行动**。
"""

    def _parse_action(self, raw: str) -> CharacterAction:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            payload: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(
                "CharacterAgent[%s] JSON parse failed: %s — first 200 chars: %s",
                self._profile.id,
                e,
                text[:200],
            )
            return self._fallback_action()

        # new_goals 需要单独 validate(Goal 字段)
        new_goals_raw = payload.get("new_goals", []) or []
        new_goals: list[Goal] = []
        for g in new_goals_raw:
            try:
                if isinstance(g, str):
                    # 兼容简化输出
                    new_goals.append(
                        Goal(
                            id=f"g_{self._profile.id}_{len(new_goals)}",
                            description=g,
                            priority=5,
                        )
                    )
                else:
                    new_goals.append(Goal.model_validate(g))
            except Exception as e:
                logger.warning("Skip invalid new_goal (%s): %s", e, g)

        # v2.16 — relationship_deltas: dict[str, RelationshipDelta]
        rel_deltas_raw = payload.get("relationship_deltas", {}) or {}
        rel_deltas: dict[str, RelationshipDelta] = {}
        if isinstance(rel_deltas_raw, dict):
            for other_id, delta_raw in rel_deltas_raw.items():
                if not other_id or not isinstance(delta_raw, dict):
                    continue
                try:
                    rel_deltas[str(other_id)] = RelationshipDelta.model_validate(delta_raw)
                except Exception as e:
                    logger.warning(
                        "CharacterAgent[%s] skip invalid relationship_delta for %s: %s",
                        self._profile.id,
                        other_id,
                        e,
                    )

        # v2.16 — 语言污染检测: description / dialogue_spoken 出现连续 ≥3 英文词
        # 触发 lang_contamination flag, Narrator / 测试可据此降权或忽略。
        extra_flags: list[str] = []
        description_val = str(payload.get("description", ""))
        dialogue_val = payload.get("dialogue_spoken") or ""
        if isinstance(dialogue_val, str) and (
            _ENGLISH_RUN_PATTERN.search(description_val)
            or _ENGLISH_RUN_PATTERN.search(dialogue_val)
        ):
            extra_flags.append("lang_contamination")

        try:
            return CharacterAction(
                character_id=self._profile.id,
                action_type=str(payload.get("action_type", "wait")),
                target=str(payload.get("target", "")),
                description=description_val,
                dialogue_spoken=payload.get("dialogue_spoken") or None,
                dialogue_to_whom=list(payload.get("dialogue_to_whom", []) or []),
                intent=str(payload.get("intent", "")),
                internal_monologue=str(payload.get("internal_monologue", "")),
                emotional_shift=str(payload.get("emotional_shift", "")),
                completed_goal_ids=list(payload.get("completed_goal_ids", []) or []),
                new_goals=new_goals,
                abandoned_goal_ids=list(payload.get("abandoned_goal_ids", []) or []),
                newly_learned=list(payload.get("newly_learned", []) or []),
                newly_speculated=list(payload.get("newly_speculated", []) or []),
                flags=list(payload.get("flags", []) or []) + extra_flags,
                new_location=str(payload.get("new_location", "") or ""),
                inventory_added=[
                    str(x) for x in (payload.get("inventory_added", []) or []) if x
                ],
                inventory_removed=[
                    str(x) for x in (payload.get("inventory_removed", []) or []) if x
                ],
                status_added=[
                    str(x) for x in (payload.get("status_added", []) or []) if x
                ],
                status_removed=[
                    str(x) for x in (payload.get("status_removed", []) or []) if x
                ],
                relationship_deltas=rel_deltas,
                money_delta=_coerce_int(payload.get("money_delta", 0)),
            )
        except Exception as e:
            logger.error(
                "CharacterAgent[%s] CharacterAction validation failed: %s",
                self._profile.id,
                e,
            )
            return self._fallback_action()

    def _fallback_action(self) -> CharacterAction:
        return CharacterAction(
            character_id=self._profile.id,
            action_type="wait",
            description="(LLM 不可用,维持现状)",
            internal_monologue="",
        )

    # ------------------------------------------------------------------
    # 并行调度
    # ------------------------------------------------------------------

    @classmethod
    async def batch_decide(
        cls,
        agents: list["CharacterAgent"],
        states: dict[str, CharacterState],
        all_tick_events: list[Event],
        concurrency: int | None = None,
    ) -> list[CharacterAction]:
        """并行调用多个 CharacterAgent.decide()。

        按 Semaphore 控制并发,A 级角色优先(profile.importance_tier == 'A' 排前)。
        缺失 state 的 agent 跳过,返回的列表与 agents 顺序对齐;跳过项为 fallback 行动。
        """
        if not agents:
            return []
        if concurrency is None:
            concurrency = _default_concurrency()

        # A 级优先排入 sem 队列
        prioritized = sorted(agents, key=lambda a: 0 if a.profile.importance_tier == "A" else 1)
        index_map = {agent: i for i, agent in enumerate(agents)}
        results: list[CharacterAction | None] = [None] * len(agents)
        sem = asyncio.Semaphore(concurrency)

        async def run_one(agent: "CharacterAgent") -> None:
            state = states.get(agent.character_id)
            if state is None:
                logger.warning(
                    "CharacterAgent[%s] has no state, skipping", agent.character_id
                )
                results[index_map[agent]] = agent._fallback_action()
                return
            async with sem:
                action = await agent.decide(state, all_tick_events)
            results[index_map[agent]] = action

        await asyncio.gather(*(run_one(a) for a in prioritized))
        # 兜底:确保返回的列表无 None
        return [r if r is not None else a._fallback_action() for r, a in zip(results, agents)]
