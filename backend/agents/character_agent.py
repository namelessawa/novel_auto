"""CharacterAgent — 单角色自主决策。

对应 ``infinite-novel-multiagent-prompts.md`` 第 6 节。每个活跃角色一个实例,
绑定一份不变的 ``CharacterProfile``,在每 tick 接受 ``CharacterState`` 和该
角色**可见的事件子集**,产出 ``CharacterAction``。

核心戏剧根基(prompts 第 0 节第 4 条):
> 角色只能用自己知道的信息。最容易塌陷的失败模式是角色"什么都知道"。

所以本类有两层 know-限制:
1. ``_filter_visible_events()`` 三档:本角色 id、``all``、``all_in_location`` 且
   当前位置匹配。v2.21 修复:此前 ``all_in_location`` 不校验位置,等价于全局广播
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
from nf_core.json_utils import parse_llm_json
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
    """CharacterAgent.batch_decide 默认并发数。

    v2.18 Phase 7 — 默认从 3 提到 6, 6 个 A/B 级角色一次并发跑完, 不再分两批
    串行。mimo / deepseek provider 默认 rate limit 都 >> 6 并发, 安全。
    若实际遇到 limit, 通过 ``CHARACTER_AGENT_CONCURRENCY`` 环境变量按需下调。
    """
    raw = os.environ.get("CHARACTER_AGENT_CONCURRENCY", "6").strip()
    try:
        n = int(raw)
        return n if n > 0 else 6
    except ValueError:
        return 6


SYSTEM_PROMPT_TEMPLATE = """\
你扮演角色: {name}

# 档案(恒定)
身份: {role}, {age}岁  ({importance_tier}级 — {tier_explain})
性格: {personality}
外貌: {appearance}
说话风格: {speech_style}
核心价值: {core_values}
深层恐惧: {fears}
深层欲望: {desires}

# 决策原则

1. 行动符合性格、基于已知信息 (不知道的事不能据此决策, 不"什么都知道")
2. 推进当前目标, 但允许突发事件改变优先级; 日常 tick 可维持日常
3. 保留秘密, 不脱口而出; 被迫做"绝对不会做"的事在 flags 标出

# 台词 (dialogue_spoken — 最终进小说的对白原文)

严格用"说话风格"说话, 读者要能分辨出是你. 像真人口语 (允许半句、打断、
犹豫、答非所问), 不书面腔. 说话有目的 (隐瞒 / 试探 / 索取 / 安抚),
跟 intent 一致但不直说. 没必要说话就填 null, 不为填字段尬聊.

# 语言

所有 description / dialogue_spoken / intent / internal_monologue /
emotional_shift / newly_learned / new_goals.description /
relationship_deltas.history_entry 必须中文. 动作用中文动词, 不允许英文
动作短语 ("Diana uses sword to attack" ❌ → "戴安娜挥剑刺向北门守卫" ✓).
JSON 字段名保留英文; 中文专有名词保持中文.

# 硬状态转移

身体上真发生的转移必须显式填字段, 不能只在 description 里写:

* ``new_location`` — 目标 location_id; 不移动留空
* ``inventory_added`` / ``inventory_removed`` — 物品名数组
* ``status_added`` / ``status_removed`` — 状态效果 (受伤 / 疲惫 / 治愈)
* ``relationship_deltas`` — {{"对方id": {{"trust_delta": -2, "new_type":
  "敌人", "history_entry": "..."}}}}
* ``money_delta`` — 经济动作 (buy/sell/pay/earn/steal/loot/give) 填非零

留白比胡乱填好.

# 输出格式 (严格 JSON, 不要 markdown 代码块)

{{
  "action_type": "move|speak|fight|investigate|wait|...",
  "target": "目标 (人物/地点/物品)",
  "description": "具体动作的中文描述",
  "dialogue_spoken": "原话" 或 null,
  "dialogue_to_whom": [],
  "intent": "真实意图 (他人不知道)",
  "internal_monologue": "此刻最重要的一个想法",
  "emotional_shift": "情绪变化, 没变化留空",
  "completed_goal_ids": [],
  "new_goals": [],
  "abandoned_goal_ids": [],
  "newly_learned": [],
  "newly_speculated": [],
  "flags": [],
  "new_location": "",
  "inventory_added": [],
  "inventory_removed": [],
  "status_added": [],
  "status_removed": [],
  "relationship_deltas": {{}},
  "money_delta": 0
}}

你不"写小说"。你**是**这个角色, 做这个角色会做的事。
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

        基础 tier 在此固定; v2.18 Phase 6 起, Guardian 监测幻觉率会按 tick
        通过 ``decide(... model_override=...)`` 临时替换为更低成本模型,
        激活路径需 ``HALLUCINATION_AUTO_DEGRADE=1``。
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
        *,
        model_override: str | None = None,
        recent_actions: list[CharacterAction] | None = None,
    ) -> CharacterAction:
        """对本 tick 做出行动决策。``all_tick_events`` 会被自动过滤为可见子集。

        ``model_override`` (v2.18 Phase 6): Guardian 监控建议降级时, Orchestrator
        阶段 3 注入。None / 空时不影响, 非空时透传给 llm_client.chat。

        ``recent_actions`` (v2.37): 本角色最近几 tick 的行动, 注入 prompt 防止
        无记忆的机械重复 (同一动作连刷十几个 tick 是实测高发退化)。
        """
        visible = self._filter_visible_events(all_tick_events, state.current_location)
        user_prompt = self._build_user_prompt(state, visible, recent_actions or [])
        try:
            # v2.38 (iter#8) — CharacterAction JSON 典型 ~500-800 tokens.
            # v2.38 (iter#8 review fix) — 此前直接砍到 2048 对 reasoning 模型
            # (DeepSeek-Reasoner / MiMo) 太紧: 它们的 chain-of-thought 与
            # message.content 共享 budget. 2048 让 reasoning 占满后 content 为
            # 空, extract_message_text 退到 reasoning_content 不是 JSON, 解析
            # 必败, 角色静默 fallback wait. A 级用更宽 budget 容下推理.
            cap = 8192 if self._profile.importance_tier == "A" else 4096
            resp = await llm_client.chat(
                system_prompt=self._system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=cap,
                agent_id=f"character_agent:{self._profile.id}",
                priority=self._priority,
                model_override=model_override,
            )
        except Exception as e:
            logger.error("CharacterAgent[%s] LLM call failed: %s", self._profile.id, e)
            return self._fallback_action()

        return self._parse_action(resp.content)

    def _filter_visible_events(
        self, events: list[Event], cur_location: str = ""
    ) -> list[Event]:
        """戏剧性根基:角色只看到 ``visible_to`` 含自身 id 的事件。

        三档可见性语义:
        - ``cid in e.visible_to``        — 显式点名
        - ``"all" in e.visible_to``      — 真·全局广播 (prompts 第 0 节)
        - ``"all_in_location"`` in e.visible_to AND ``e.location == cur_location``
          — 同地点广播:此前实现漏判位置,任何带此标记的事件都泄露给所有角色,
          直接违反戏剧根基。v2.21 修复。

        ``cur_location`` 留空 ("") 时 ``all_in_location`` 一律不可见 — 避免
        把"位置未知"角色误并入任意地点广播。
        """
        cid = self._profile.id
        return [
            e
            for e in events
            if cid in e.visible_to
            or "all" in e.visible_to
            or (
                "all_in_location" in e.visible_to
                and bool(cur_location)
                and e.location == cur_location
            )
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
        self,
        state: CharacterState,
        visible_events: list[Event],
        recent_actions: list[CharacterAction] | None = None,
    ) -> str:
        # v2.38 (iter#20) — user_prompt 紧凑: 多个独立 header 合并,
        # 关系/事件 description 截 60 字, recent_actions 取后 3 条 (从 4),
        # 删冗余说明文.
        rels_text = "(无)"
        if state.relationships:
            rels_text = "\n".join(
                f"  - {rel.with_character_id}: {rel.type}/信任{rel.trust:+d}/"
                f"{rel.history_summary[:50]}"
                for rel in state.relationships.values()
            )

        goals_text = "(无)"
        if state.current_goals:
            goals_text = "\n".join(
                f"  - [{g.priority}] {g.description[:80]} ({g.progress:.0%})"
                for g in state.current_goals
            )

        events_text = "(无可感知事件)"
        if visible_events:
            events_text = "\n".join(
                f"  - [{e.id}@{e.location}] {e.description[:100]}"
                for e in visible_events
            )

        recent_text = ""
        if recent_actions:
            recent_lines = "\n".join(
                f"  - {a.action_type}→{a.target or '-'}: {a.description[:50]}"
                for a in recent_actions[-3:]
            )
            recent_text = (
                f"\n\n# 最近几步 (旧→新)\n{recent_lines}\n"
                f"**不要原样重复上一步** — 要么推进, 要么换方法, 要么应对新事件."
            )

        status = ", ".join(state.status_effects) or "正常"
        inv = ", ".join(state.inventory) or "无"
        return f"""\
# 当前状态
位置: {state.current_location or '(未指定)'} | 情绪: {state.emotional_state} | 身体: {status} | 物品: {inv} | 钱: {state.money}

# 短期目标
{goals_text}

# 长期弧线
{state.arc_goal or '(尚未明确)'} (进度 {state.arc_progress:.0%})

# 知识范围 (极重要 — 不知道的事不能据此决策)
亲历/已知: {('; '.join(state.known_facts)[:200]) or '(无)'}
保守秘密: {('; '.join(state.secrets_kept)[:200]) or '(无)'}

# 关系网
{rels_text}

# 本 tick 可感知事件
{events_text}{recent_text}

基于你的目标、性格、所知信息, 决定本 tick 行动.
"""

    def _parse_action(self, raw: str) -> CharacterAction:
        try:
            payload: dict[str, Any] = parse_llm_json(raw)
        except json.JSONDecodeError as e:
            logger.error(
                "CharacterAgent[%s] JSON parse failed: %s — raw[:300]=%r",
                self._profile.id,
                e,
                raw[:300],
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
        *,
        model_overrides: dict[str, str] | None = None,
        recent_actions_by_char: dict[str, list[CharacterAction]] | None = None,
    ) -> list[CharacterAction]:
        """并行调用多个 CharacterAgent.decide()。

        按 Semaphore 控制并发,A 级角色优先(profile.importance_tier == 'A' 排前)。
        缺失 state 的 agent 跳过,返回的列表与 agents 顺序对齐;跳过项为 fallback 行动。

        ``model_overrides`` (v2.18 Phase 6): 按 character_id 分发的模型降级标记。
        None 或缺失某 cid 时该 agent 不降级 (model_override=None)。

        ``recent_actions_by_char`` (v2.37): 各角色最近行动环形缓冲 (Orchestrator
        持有), 注入各自 prompt 防机械重复。
        """
        if not agents:
            return []
        if concurrency is None:
            concurrency = _default_concurrency()
        overrides = model_overrides or {}
        recent_map = recent_actions_by_char or {}

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
            override = overrides.get(agent.character_id) or None
            recent = recent_map.get(agent.character_id) or []
            async with sem:
                action = await agent.decide(
                    state,
                    all_tick_events,
                    model_override=override,
                    recent_actions=recent,
                )
            results[index_map[agent]] = action

        await asyncio.gather(*(run_one(a) for a in prioritized))
        # 兜底:确保返回的列表无 None
        return [r if r is not None else a._fallback_action() for r, a in zip(results, agents)]
