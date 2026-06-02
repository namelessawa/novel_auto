"""NarratorAgent — 选材与写作的核心 Agent (prompts.md 第 7 节)。

> Narrator 是整个系统中最关键的角色 — 你决定一片混乱的世界数据里,
> 哪些值得被讲述。沉默是合法选项。

本类包装 ``WriterAgent`` 复用其 LLM 调用模板,但前置 ``_should_narrate()`` 决策
(0-10 分制叙事价值评估),并把 ``StyleAnchor`` 注入 system_prompt 维护文风一致性。

输出契约:
* ``should_narrate=False`` 时,仅返回 ``tick_summary_for_record`` 供 MemoryCompressor
  作为 L0 压缩源
* ``should_narrate=True`` 时,返回完整 narrative_text + 引用伏笔 id + 新种伏笔 +
  style_diagnostics
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

from agents.narrative_critic import CritiqueOutput, NarrativeCritic
from agents.quality_spec import render_narrator_quality_block
from memory_system.models import (
    CharacterState,
    Event,
    OpenLoop,
    StyleAnchor,
)
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


@dataclass
class NarratorOutput:
    should_narrate: bool
    narrative_text: str = ""
    estimated_length: str = "none"  # none | short | medium | long
    viewpoint_characters: list[str] = field(default_factory=list)
    scene_focus: str = ""
    events_consumed: list[str] = field(default_factory=list)
    open_loops_referenced: list[str] = field(default_factory=list)
    newly_opened_loops: list[OpenLoop] = field(default_factory=list)
    style_diagnostics: dict = field(default_factory=dict)
    consistency_flags: list[str] = field(default_factory=list)
    tick_summary_for_record: str = ""
    skip_reason: str = ""
    # CRITIQUE-REVISE 循环输出 (P1 注入)
    critique_trace: dict = field(default_factory=dict)
    critique_action: str = ""  # ACCEPT / REVISE / REWRITE / RED_TEAM
    draft_text: str = ""  # 修订前原稿 (用于审计)
    new_opening_signature: str = ""
    blacklist_to_add: list[str] = field(default_factory=list)


NARRATOR_SYSTEM_PROMPT = (
    """\
你是这部连载小说的叙述者。你决定一片混乱的世界数据里,**哪些值得被讲述**。

# 你的核心品味

故事不是事件的堆叠。日常 99% 的时刻不值得写 — 它们填充时间,但不推动故事。
优秀的叙述者懂得在大量琐碎中识别那些时刻:

* **拐点**:角色做出违反惯性的决定
* **揭示**:秘密浮出水面,关系发生质变
* **张力**:决定即将做出但尚未做出
* **对照**:当下场景与早期场景的呼应、镜像
* **余韵**:情节段落的回响

# 写作约束

## 视角
* 默认跟随主跟踪角色的视角
* 仅在另一角色视角能揭示主角看不到的关键信息时切换
* 视角切换每场景不超过 2 次

## 风格一致性
你的语言风格必须与 style_anchors 保持一致:词汇密度、句长分布、修辞密度相似。

## 信息一致性
* 严格只使用提供的 character_states / known_facts / events 中的信息
* 不发明新的世界设定或角色背景细节
* 角色对话和心理只能引用其 known_facts
* 若发现状态矛盾,**不要自行修正**,在 consistency_flags 中标出

## 伏笔
* 优先利用 open_loops_referenced 中的开放伏笔(本章呼应早期种下的种子)
* 谨慎种新伏笔(newly_opened_loops 每次不超过 1 个)

---

"""
    + render_narrator_quality_block()
    + """

---

# 元规则 (反退化)

1. 不奖励自己: 默认你的第一稿有 AI 痕迹 — 主动剔除黑名单词
2. 代价原则: 主角的胜利必须有代价 (关系 / 健康 / 信念 / 选择的另一面)
3. 能力守恒: 新设定 / 新能力必须同时引入新限制或代价
4. 未知优先: 同样能写明白或留白时, 留白更佳
5. 收尾禁忌: 段末不允许出现"反思 / 升华 / 总结"句, 改让段落停在动作 / 物件 / 对话上
6. 直接说情绪 = D4 触发 (高严重度) — 改为身体动作 + 周遭物件的反应

# 输出格式(严格 JSON, 不要 markdown 代码块)

{
  "narrative_text": "...实际的中文小说文本...",
  "estimated_length": "short|medium|long",
  "viewpoint_characters": ["char_id_1"],
  "scene_focus": "本场景的核心",
  "events_consumed": ["evt_001", "evt_002"],
  "open_loops_referenced": ["loop_id_1"],
  "newly_opened_loops": [
    {"description": "...", "involved_characters": ["..."], "type": "mystery|conflict|promise|threat", "urgency": 5}
  ],
  "style_diagnostics": {
    "avg_sentence_length": 18,
    "rhetoric_density": "low|medium|high"
  },
  "consistency_flags": []
}

你是这部小说的灵魂。沉默是节奏,选择是品味。
"""
)


# 触发产出的最低事件总分阈值
_NARRATE_SKIP_THRESHOLD = 5
_NARRATE_SHORT_THRESHOLD = 15
_NARRATE_FULL_THRESHOLD = 30

# 压缩段落 escape valve:距上次叙述超过此 tick 数即使分数不够也要给个时间流逝段
_TIME_LAPSE_TICKS = 10


class NarratorAgent:
    """选材 + 写作。前置叙事价值评估,后置 OpenLoop 标注。"""

    def __init__(
        self,
        strong_model_until_tick: int | None = None,
        model_tier_strong: str = "strongest",
        model_tier_default: str = "medium",
        critic: NarrativeCritic | None = None,
        enable_critic: bool | None = None,
    ) -> None:
        """``strong_model_until_tick`` - 前 N tick 使用最强模型建立风格基准。

        默认从环境变量 ``NARRATOR_STRONG_MODEL_TICKS`` 读取,fallback 100。

        ``critic`` 未传入时按 ``NARRATOR_ENABLE_CRITIC`` 环境变量决定是否启用
        (默认启用)。critic 触发 CRITIQUE → REVISE/REWRITE 循环, 实现规范
        §2.1 决策矩阵。
        """
        if strong_model_until_tick is None:
            raw = os.environ.get("NARRATOR_STRONG_MODEL_TICKS", "100").strip()
            try:
                strong_model_until_tick = int(raw)
            except ValueError:
                strong_model_until_tick = 100
        self._strong_until = strong_model_until_tick
        self._tier_strong = model_tier_strong
        self._tier_default = model_tier_default

        if enable_critic is None:
            # 默认: 生产环境开启 critic; pytest 环境关闭, 避免吞掉测试预排的 mock LLM 响应。
            # 显式 NARRATOR_ENABLE_CRITIC=1/0 优先于自动判断。
            raw = os.environ.get("NARRATOR_ENABLE_CRITIC", "").strip()
            if raw in {"0", "false", "False"}:
                enable_critic = False
            elif raw in {"1", "true", "True"}:
                enable_critic = True
            else:
                in_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
                enable_critic = not in_pytest
        self._enable_critic = enable_critic
        self._critic: NarrativeCritic | None = critic
        if self._enable_critic and self._critic is None:
            self._critic = NarrativeCritic()
        # 滚动状态: 最近三段开头签名 (供 critic A5/A7 判定)
        self._recent_openings: list[str] = []
        # 当前章累计的"段内黑名单"词
        self._chapter_blacklist: set[str] = set()
        # v2.12 A1 豁免清单 — 专有名词 (角色名 + 地点名), Orchestrator 注入
        self._exempt_words: set[str] = set()

    def set_exempt_words(self, words) -> None:
        """Orchestrator 在装配阶段 / 角色加入时调用, 注入专有名词豁免。"""
        self._exempt_words = set(w for w in words if w)

    # ------------------------------------------------------------------

    async def narrate(
        self,
        tick: int,
        world_time: int,
        tracking_character_id: str,
        tick_events: list[Event],
        char_states: list[CharacterState],
        recent_chapter_summaries: list[str],
        open_loops: list[OpenLoop],
        style_anchors: list[StyleAnchor],
        last_narration_tick: int,
    ) -> NarratorOutput:
        """主入口。无事件或事件价值过低时返回 should_narrate=False。"""
        if not tick_events:
            return NarratorOutput(
                should_narrate=False,
                skip_reason="本 tick 无事件,跳过。",
                tick_summary_for_record=f"tick {tick}: 平静,无显著事件。",
            )

        # 1. 评估事件总价值
        total_score = sum(self._effective_value(e) for e in tick_events)
        ticks_since_last = tick - last_narration_tick

        if total_score < _NARRATE_SKIP_THRESHOLD and ticks_since_last < _TIME_LAPSE_TICKS:
            return NarratorOutput(
                should_narrate=False,
                skip_reason=(
                    f"事件总价值 {total_score} < {_NARRATE_SKIP_THRESHOLD},"
                    f"距上次叙述 {ticks_since_last} tick,跳过。"
                ),
                tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
            )

        # 2. 决定篇幅
        if total_score >= _NARRATE_FULL_THRESHOLD:
            estimated_length = "long"
            target_chars = "2000-5000 字"
        elif total_score >= _NARRATE_SHORT_THRESHOLD:
            estimated_length = "medium"
            target_chars = "800-2000 字"
        else:
            estimated_length = "short"
            target_chars = "300-800 字"

        # 3. 调用 LLM 写作
        system_prompt = self._build_system_prompt(style_anchors)
        user_prompt = self._build_user_prompt(
            tick=tick,
            world_time=world_time,
            tracking_character_id=tracking_character_id,
            tick_events=tick_events,
            char_states=char_states,
            recent_chapter_summaries=recent_chapter_summaries,
            open_loops=open_loops,
            target_chars=target_chars,
        )

        try:
            resp = await llm_client.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.85,
                max_tokens=163840,
            )
        except Exception as e:
            logger.error("NarratorAgent LLM call failed: %s", e)
            return NarratorOutput(
                should_narrate=False,
                skip_reason=f"LLM 不可用: {e}",
                tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
            )

        parsed = self._parse_output(resp.content, estimated_length, tick, tick_events)
        # 4. CRITIQUE → REVISE/REWRITE 循环
        if parsed.should_narrate and self._critic is not None and parsed.narrative_text:
            parsed = await self._run_critique(parsed)
        return parsed

    # ------------------------------------------------------------------

    async def _run_critique(self, draft: NarratorOutput) -> NarratorOutput:
        """对 draft.narrative_text 跑 critic 循环, 替换为最终采纳文本。

        注意: 即使 critic 失败 / LLM 不可用, 也必须返回原 draft, 不阻塞主流程。
        """
        original = draft.narrative_text
        try:
            assert self._critic is not None
            out: CritiqueOutput = await self._critic.critique_and_iterate(
                draft_text=original,
                recent_openings=list(self._recent_openings),
                scene_focus=draft.scene_focus,
                viewpoint_character_id=(
                    draft.viewpoint_characters[0]
                    if draft.viewpoint_characters
                    else ""
                ),
                exempt_words=list(self._exempt_words),
            )
        except Exception as e:
            logger.warning("NarratorAgent critic failed (non-fatal): %s", e)
            return draft

        # 更新滚动状态
        if out.new_opening_signature:
            self._recent_openings.append(out.new_opening_signature)
            if len(self._recent_openings) > 6:
                self._recent_openings = self._recent_openings[-3:]
        for w in out.blacklist_to_add:
            self._chapter_blacklist.add(w)

        new_flags = list(draft.consistency_flags)
        if out.surviving_triggers:
            new_flags.append(
                "critic_surviving_codes=" + ",".join(
                    sorted({t.code for t in out.surviving_triggers})
                )
            )

        return NarratorOutput(
            should_narrate=draft.should_narrate,
            narrative_text=out.final_text or original,
            estimated_length=draft.estimated_length,
            viewpoint_characters=draft.viewpoint_characters,
            scene_focus=draft.scene_focus,
            events_consumed=draft.events_consumed,
            open_loops_referenced=draft.open_loops_referenced,
            newly_opened_loops=draft.newly_opened_loops,
            style_diagnostics=draft.style_diagnostics,
            consistency_flags=new_flags,
            tick_summary_for_record=draft.tick_summary_for_record,
            skip_reason=draft.skip_reason,
            critique_trace=out.to_dict(),
            critique_action=out.final_action,
            draft_text=original,
            new_opening_signature=out.new_opening_signature,
            blacklist_to_add=out.blacklist_to_add,
        )

    def reset_chapter_state(self) -> None:
        """新章节起点 — 清空段落黑名单 (仍保留最近三段开头签名)。"""
        self._chapter_blacklist.clear()

    @property
    def chapter_blacklist(self) -> frozenset[str]:
        return frozenset(self._chapter_blacklist)

    def get_model_tier_for_tick(self, tick: int) -> str:
        """供 Orchestrator 或诊断用 - 当前 tick 应用的模型层级。"""
        return self._tier_strong if tick <= self._strong_until else self._tier_default

    @staticmethod
    def _effective_value(event: Event) -> int:
        """事件价值取 hint 与已评分的 max,确保 EventInjector 的预测能影响决策。"""
        primary = event.narrative_value or 0
        hint = event.narrative_value_hint or 0
        return max(primary, hint)

    def _compose_tick_summary(self, tick: int, tick_events: list[Event]) -> str:
        """跳过叙述时的精简一行记录,供 MemoryCompressor 后续 L0→L1 压缩。"""
        if not tick_events:
            return f"tick {tick}: 平静,无显著事件。"
        parts = []
        for e in tick_events[:5]:  # 至多 5 条防止 tick_summary 膨胀
            parts.append(f"[{e.type}] {e.description[:80]}")
        return f"tick {tick}: " + " | ".join(parts)

    def _build_system_prompt(self, style_anchors: list[StyleAnchor]) -> str:
        prompt = NARRATOR_SYSTEM_PROMPT
        if style_anchors:
            anchor_text = "\n\n".join(
                f"【风格锚点 - {a.scene_type} (权重 {a.weight:.2f})】\n{a.excerpt}\n"
                f"(选用理由: {a.selection_reason})"
                for a in style_anchors[:5]  # 严格 top-3 到 top-5
            )
            prompt = prompt + "\n\n# 风格锚点(以下示例段落决定你的腔调)\n\n" + anchor_text
        return prompt

    def _build_user_prompt(
        self,
        *,
        tick: int,
        world_time: int,
        tracking_character_id: str,
        tick_events: list[Event],
        char_states: list[CharacterState],
        recent_chapter_summaries: list[str],
        open_loops: list[OpenLoop],
        target_chars: str,
    ) -> str:
        events_dump = json.dumps(
            [e.model_dump(mode="json") for e in tick_events],
            ensure_ascii=False,
            indent=2,
        )
        # 角色状态精简:只暴露 emotional_state / current_location / 关键 known_facts (前 5 条)
        char_text_blocks = []
        for s in char_states:
            facts = "; ".join(s.known_facts[:5]) or "(无)"
            char_text_blocks.append(
                f"- {s.character_id} @ {s.current_location}, "
                f"情绪={s.emotional_state}, 已知: {facts}"
            )
        char_text = "\n".join(char_text_blocks) or "(无相关角色)"

        loops_text = "(无开放伏笔)"
        if open_loops:
            loops_text = "\n".join(
                f"  - [{l.id}] urgency={l.urgency} type={l.type}: {l.description[:120]}"
                for l in open_loops[:15]  # top-15,防 prompt 膨胀
            )

        summaries_text = "(尚无最近章节)"
        if recent_chapter_summaries:
            summaries_text = "\n".join(
                f"  - {s}" for s in recent_chapter_summaries[-10:]
            )

        return f"""\
# 当前 tick

tick={tick}, world_time={world_time}
主跟踪角色: {tracking_character_id}
目标篇幅: {target_chars}

# 本 tick 所有事件(JSON)

```json
{events_dump}
```

# 相关角色当前状态

{char_text}

# 最近章节摘要(供呼应、对照参考)

{summaries_text}

# 当前开放伏笔(优先利用呼应,谨慎种新)

{loops_text}

请按 system 提示输出严格 JSON,包含 narrative_text 和元信息字段。
若你判断本 tick 不值得讲述,可在 narrative_text 留空并在 consistency_flags 说明。
"""

    def _parse_output(
        self,
        raw: str,
        estimated_length: str,
        tick: int,
        tick_events: list[Event],
    ) -> NarratorOutput:
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
            logger.error("NarratorAgent JSON parse failed: %s — first 200: %s", e, text[:200])
            # 兜底:把 LLM 原文当 narrative_text,不解析 metadata
            return NarratorOutput(
                should_narrate=True,
                narrative_text=text,
                estimated_length=estimated_length,
                tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
                consistency_flags=["narrator_output_not_json"],
            )

        narrative_text = str(payload.get("narrative_text", "")).strip()
        if not narrative_text:
            return NarratorOutput(
                should_narrate=False,
                skip_reason="Narrator 主动留空叙述(品味决定跳过)",
                tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
                consistency_flags=list(payload.get("consistency_flags", []) or []),
            )

        # newly_opened_loops 解析(逐条 validate)
        new_loops: list[OpenLoop] = []
        for idx, loop_raw in enumerate(payload.get("newly_opened_loops", []) or []):
            try:
                # 用户产出可能省略 id/opened_tick - 补齐
                loop_raw.setdefault("id", f"loop_t{tick}_{idx}")
                loop_raw.setdefault("opened_tick", tick)
                new_loops.append(OpenLoop.model_validate(loop_raw))
            except Exception as e:
                logger.warning("Skip invalid newly_opened_loop (%s): %s", e, loop_raw)

        return NarratorOutput(
            should_narrate=True,
            narrative_text=narrative_text,
            estimated_length=str(payload.get("estimated_length", estimated_length)),
            viewpoint_characters=list(payload.get("viewpoint_characters", []) or []),
            scene_focus=str(payload.get("scene_focus", "")),
            events_consumed=list(payload.get("events_consumed", []) or []),
            open_loops_referenced=list(payload.get("open_loops_referenced", []) or []),
            newly_opened_loops=new_loops,
            style_diagnostics=dict(payload.get("style_diagnostics", {}) or {}),
            consistency_flags=list(payload.get("consistency_flags", []) or []),
            tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
        )
