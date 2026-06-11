"""NarrativeCritic — 段级 CRITIQUE -> REVISE/REWRITE 循环。

对应 ``novel_quality_critique_and_iteration.md`` §2.2 三级迭代策略。

工作流:
1. 接收 Narrator 产出的段落 (草稿)
2. 跑确定性检查 (quality_checks.run_deterministic_checks)
3. 若高/中触发达阈值, 调用 LLM 做语义判定 (B/C/F/G 等 LLM-required 维度)
4. 合并触发列表, 按决策矩阵选 REWRITE / REVISE / POLISH / RED_TEAM
5. 调度 LLM 执行修订, 至多 ``MAX_REVISE_ROUNDS`` 轮
6. 全通过时启动红队复查 (§2.4)

输出契约:
* ``final_text`` — 最终采纳的段落
* ``rounds`` — 修订迭代历史 (供 trace / 调试)
* ``surviving_triggers`` — 最终仍存在的触发码 (供 TickState 黑名单更新)
* ``decision_trail`` — 每轮决策与理由
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Literal

from agents.quality_checks import (
    DeterministicTrigger,
    extract_opening_signature,
    run_deterministic_checks,
    summarize_triggers,
)
from agents.quality_spec import (
    RULES_BY_CODE,
    decide_action,
    render_critique_block_semantic,
    render_show_dont_tell_block,
)
from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


Action = Literal["REWRITE", "REVISE", "POLISH", "RED_TEAM", "ACCEPT"]


@dataclass
class CritiqueRound:
    round_index: int
    action: Action
    triggers_before: list[dict] = field(default_factory=list)
    triggers_after: list[dict] = field(default_factory=list)
    text_before: str = ""
    text_after: str = ""
    rationale: str = ""


@dataclass
class CritiqueOutput:
    final_text: str
    rounds: list[CritiqueRound]
    surviving_triggers: list[DeterministicTrigger]
    decision_trail: list[str]
    final_action: Action
    new_opening_signature: str
    blacklist_to_add: list[str]

    def to_dict(self) -> dict:
        return {
            "final_text": self.final_text,
            "rounds": [
                {
                    "round": r.round_index,
                    "action": r.action,
                    "rationale": r.rationale,
                    "triggers_before": r.triggers_before,
                    "triggers_after": r.triggers_after,
                }
                for r in self.rounds
            ],
            "surviving_triggers": [t.to_dict() for t in self.surviving_triggers],
            "decision_trail": self.decision_trail,
            "final_action": self.final_action,
            "new_opening_signature": self.new_opening_signature,
            "blacklist_to_add": self.blacklist_to_add,
        }


# ---------------------------------------------------------------------------
# LLM 判定 system prompt
# ---------------------------------------------------------------------------

CRITIC_SYSTEM_PROMPT = (
    """\
你是这部连载小说的最挑剔的责任编辑。你的工作不是夸赞,而是发现问题。

你不能跳过任何一条规则, 不能用"基本通过"、"瑕不掩瑜"等模糊措辞。
任何触发必须给出原文证据 (引用片段)。

# 分工

A 类 (重复) / G4 段末升华句 由 det 检查器先扫一遍, 你不需要再列 A1/A4/
A5/A6/A7/G4. 你聚焦在 LLM 才能察觉的语义/结构问题: B (角色失真) /
C (情节) / D (描写) / E (语言) / F (结构) / G 其余.

---

"""
    + render_critique_block_semantic()
    + "\n\n"
    + render_show_dont_tell_block()
    + """

---

# 输出格式 (严格 JSON, 不要 markdown 代码块)

{
  "triggers": [
    {"code": "A4", "severity": "high", "evidence": "...原文片段..."}
  ],
  "rationale": "一句话说明你最关心的问题",
  "red_team_critiques": [
    "若全部通过, 给出 3 条最可能的差评; 否则给空数组"
  ]
}

# 注意
- 仅输出 JSON, 不要任何前后说明文字
- evidence 必须是原文直接引用 (≤30 字片段), 不可改写
- 高/中严重度的判定参考给定的规则表
- 不要在 triggers 中包含"无触发", 没有就给空数组
"""
)


REVISE_SYSTEM_PROMPT = (
    """\
你是这部小说的修订者。你不重写, 你做外科手术式的局部修订。

# 规则

1. 保留段落主要事件与结构
2. 仅针对给定触发码做对症修改
3. 必须输出 修订对照 — 每个修改点列 原文 → 改后
4. 不允许仅做同义词替换 (这会触发新的 D3/G8)

# 修订原则映射

| 触发码 | 正确修订方向 |
|--------|--------------|
| A1 | 删除或替换为该上下文真正需要的具体词 |
| A2 | 至少一句改为不同长度或不同结构 |
| A4 | 删除整句, 或改为只在此场景成立的具体细节 |
| A5/A7 | 改变开头类型 (动作↔环境, 心理↔对话) |
| A6/G4 | 删除段末"升华句", 让段落停在动作或物件上 |
| B4 | 部分内心描写换成身体动作或物件特写 |
| D1 | 拆分至后续场景, 或改为对话泄露 |
| D2 | 改为动词驱动 + 一个具体名词 |
| D4 | 改为身体动作 + 周遭物件的反应 |
| D5 | 替换 (而非追加) 部分视觉为其他感官 |
| D6 | 强制引入至少一个可视化的具体物 |

# 黑名单
原稿命中的 A4 黑名单触发已在 user prompt 的 "待修订的触发项" 列出
(每项含 evidence 引用); 修订后请把这些词替换掉, 不再在 system prompt
里重复完整黑名单 (节省 token).

"""
    + render_show_dont_tell_block()
    + """

---

# 输出格式 (严格 JSON, 不要 markdown 代码块)
#
# revised_text 必须是真正修订过的段落正文中文小说本身,
# **绝不能 copy 这段 schema 描述里的字面字符串** —
# 不要写 "完整修订后的段落正文" / "原文片段" / 省略号占位符.

{
  "revised_text": "(此处放真正修订后的中文小说正文, 不少于 80 字)",
  "diffs": [
    {"trigger_code": "A4", "before": "雪粉仿佛笑了一下", "after": "雪粉嘴角弯了半寸"}
  ],
  "removed_words": ["仿佛", "缓缓地"]
}
"""
)


REWRITE_SYSTEM_PROMPT = (
    """\
你是这部小说的重写者。原稿命中高严重度触发, 必须丢弃, 重新起笔。

# 强约束

1. 完全丢弃原稿语言, 不允许"基于原文修改"
2. 维度切换 — 在以下至少一个维度上显著不同于原稿:
   * 叙事节奏 (快 ↔ 慢)
   * 主导感官 (视觉 → 听觉 / 触觉 / 体感)
   * 内外比例 (外部动作 ↔ 内心)
   * 句子节奏 (长句为主 ↔ 短句切分)
   * 信息密度 (明说 ↔ 暗示)
3. 必须严格避开 避免清单 中的触发项
4. 必须严格遵守原稿想表达的事件骨架 — 事件 / 角色 / 地点不变

# 黑名单
原稿命中的触发码已在 user prompt 的 "避免清单" 段列出 (每条 code +
描述). 重写时严禁触发其中任一; 不再在 system prompt 里重复完整黑名单.

"""
    + render_show_dont_tell_block()
    + """

---

# 输出格式 (严格 JSON, 不要 markdown 代码块)
#
# rewritten_text 必须是真正重写过的段落正文中文小说本身,
# **绝不能 copy 这段 schema 描述里的字面字符串** —
# 不要写 "完整重写后的段落正文" / "节奏由X变为Y" 这类占位符.

{
  "rewritten_text": "(此处放真正重写后的中文小说正文, 不少于 80 字)",
  "dimension_shift": "节奏由慢变快; 主导感官由视觉转触觉",
  "avoided_codes": ["A4", "A6"]
}
"""
)


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


MAX_REVISE_ROUNDS = _env_int("CRITIC_MAX_REVISE_ROUNDS", 1)
MAX_REWRITE_ROUNDS = _env_int("CRITIC_MAX_REWRITE_ROUNDS", 1)
# rewrite + revise 累计修订轮次硬上限。
# v2.38 (iter#3) — 默认从 4 降到 2.
# v2.38 (iter#33) — 进一步降到 1: 1 次 critique + 1 次 modify (revise OR
# rewrite) 后直接接受, 不再做 2nd critique. 实测 2nd critique 几乎总是
# POLISH (modify 已清掉高触发), 等于纯浪费. 通过 env 可恢复为 2/3/4.
MAX_TOTAL_ROUNDS = _env_int("CRITIC_MAX_TOTAL_ROUNDS", 1)
ENABLE_LLM_CRITIC = os.environ.get("CRITIC_ENABLE_LLM", "1").strip() != "0"

# v2.38 (iter#3) — critique 输出上限。triggers JSON 极其紧凑, 1500 tokens 足够
# 列 10+ 条触发; 之前的 8192 给推理模型留了把 budget 全填满的空间, 浪费且超时。
_CRITIQUE_MAX_OUTPUT = _env_int("CRITIC_CRITIQUE_MAX_TOKENS", 1500)
# revise / rewrite 输出上限。narrative_text 上限 ~2200 字 (≈3300 tokens),
# 给到 4096 留余量, 比之前的 32768 直接砍到 1/8。
_REVISE_MAX_OUTPUT = _env_int("CRITIC_REVISE_MAX_TOKENS", 4096)

# v2.38 (iter#3) — 推理模型泄漏前缀: critique 调用偶发被 MaaS Qwen / DeepSeek-R1
# 类模型当作开放问答, 输出 "Let me analyze..." / "好的, 让我..." 等 reasoning
# 前缀, 整次调用 JSON 解析失败,~6k tokens 白烧。检测到则直接 return []
# (退回 det-only), 不重试。
_REASONING_LEAK_PREFIXES = (
    "let me", "let's ", "first,", "i'll ", "i will ",
    "好的", "我先", "我来", "让我", "首先", "下面我",
)


class NarrativeCritic:
    """对 Narrator 输出执行 CRITIQUE → REVISE/REWRITE 循环。"""

    def __init__(
        self,
        *,
        model_tier_critic: str = "medium",
        model_tier_reviser: str = "medium",
        model_tier_rewriter: str = "strong",
    ) -> None:
        self._tier_critic = model_tier_critic
        self._tier_reviser = model_tier_reviser
        self._tier_rewriter = model_tier_rewriter

    async def critique_and_iterate(
        self,
        *,
        draft_text: str,
        recent_openings: list[str] | None = None,
        scene_focus: str = "",
        viewpoint_character_id: str = "",
        enable_llm: bool | None = None,
        exempt_words: list[str] | tuple[str, ...] | None = None,
    ) -> CritiqueOutput:
        """主入口。返回最终采纳文本 + 完整迭代历史。"""
        if not draft_text or not draft_text.strip():
            return CritiqueOutput(
                final_text=draft_text,
                rounds=[],
                surviving_triggers=[],
                decision_trail=["empty draft, skipped"],
                final_action="ACCEPT",
                new_opening_signature="",
                blacklist_to_add=[],
            )

        use_llm = ENABLE_LLM_CRITIC if enable_llm is None else enable_llm
        recent_openings = recent_openings or []

        rounds: list[CritiqueRound] = []
        trail: list[str] = []

        current_text = draft_text
        revise_used = 0
        rewrite_used = 0
        # v2.38 (iter#3) — LLM critique 只在第一轮调用. 后续轮只跑 det 检查
        # 验证修订是否把结构性触发清掉. 之前每轮都跑 LLM critique, 第二/三轮
        # 几乎都是冗余的二次确认 (语义触发在第一轮已识别, revise 阶段已带入
        # avoid_codes), 占基线 critic 开支 60-70%.
        #
        # v2.38 (iter#5 review fix) — 关于"第一次 LLM critique 失败"的显式
        # 约定: 即便首次 _llm_critique 因 reasoning leak / 解析失败 / 异常
        # 返回 [], llm_critique_done 仍置 True. 整个 draft 的语义检查降级为
        # det-only. 这是有意权衡 — 反复 retry 撞同一个错误浪费 token, 比保
        # 留语义盲点更糟. det 层已覆盖大部分结构性问题 (重复 / 开头 / 段末
        # / AI 套话), 语义失败的边际损失可接受.
        llm_critique_done = False

        while True:
            # === Step 1: 确定性 + LLM 触发合并 =========================
            det_triggers = run_deterministic_checks(
                current_text,
                recent_openings=recent_openings,
                exempt_words=exempt_words,
            )
            # v2.38 (iter#6) — LLM critique 条件触发: det 已找到 ≥1 个 high
            # 触发时跳过 LLM critique, 直接进入 REWRITE. 决策矩阵中 high>=1
            # 一律 REWRITE, 再问 LLM 不会改变行动结果.
            #
            # v2.38 (iter#8 review fix) — 此前 "det medium >= 2 就跳 LLM" 是
            # 错的: det 检的是结构性问题 (重复/开头/段末/AI 套话), LLM 检的是
            # 语义问题 (B/C/F/G — show-don't-tell / 情感平淡 / 视角漂移 /
            # 对话潜台词). 两者正交; 结构性 medium 不蕴含语义 high. 改成"只
            # 在 det 已 high>=1 时才跳 LLM" — 决策已确定为 REWRITE, 多问 LLM
            # 浪费; det 仅 medium 时仍需要 LLM 找语义触发.
            #
            # 用 CRITIC_FORCE_LLM=1 可强制总跑 (用于调试 / 严格场景).
            llm_triggers: list[DeterministicTrigger] = []
            det_high_count = sum(1 for t in det_triggers if t.severity == "high")
            force_llm = os.environ.get("CRITIC_FORCE_LLM", "0") == "1"
            should_call_llm = (
                use_llm
                and not llm_critique_done
                and (det_high_count == 0 or force_llm)
            )
            if should_call_llm:
                llm_triggers = await self._llm_critique(
                    current_text, scene_focus, viewpoint_character_id
                )
                llm_critique_done = True
            elif use_llm and not llm_critique_done and det_high_count >= 1:
                # 跳过本次 LLM critique, 标记已用 (避免后续 round 再跑)
                llm_critique_done = True
                trail.append(
                    f"  ~ det 已发现 {det_high_count} 个 high 触发, "
                    f"跳过 LLM critique 直接 REWRITE"
                )
            all_triggers = _merge_triggers(det_triggers, llm_triggers)
            summary = summarize_triggers(all_triggers)

            # === Step 2: 决策 ============================================
            action = decide_action(
                summary["high_count"], summary["medium_count"]
            )

            trail.append(
                f"round {len(rounds) + 1}: "
                f"det={len(det_triggers)} llm={len(llm_triggers)} "
                f"high={summary['high_count']} medium={summary['medium_count']} "
                f"→ {action}"
            )

            # === Step 3: 终止条件 ========================================
            if action in ("POLISH", "RED_TEAM"):
                # POLISH 直接接受; RED_TEAM 是全通过, 我们暂时也直接接受
                # (红队第二轮判定在 Showrunner / NoveltyCritic 层处理)
                final_action: Action = (
                    "ACCEPT" if action == "POLISH" else "RED_TEAM"
                )
                return CritiqueOutput(
                    final_text=current_text,
                    rounds=rounds,
                    surviving_triggers=all_triggers,
                    decision_trail=trail,
                    final_action=final_action,
                    new_opening_signature=extract_opening_signature(current_text),
                    blacklist_to_add=_extract_blacklist_words(all_triggers),
                )

            if (
                action in ("REWRITE", "REVISE")
                and revise_used + rewrite_used >= MAX_TOTAL_ROUNDS
            ):
                trail.append(
                    f"  ! 修订总轮次上限 ({MAX_TOTAL_ROUNDS}) 达到, 接受当前文本"
                )
                return CritiqueOutput(
                    final_text=current_text,
                    rounds=rounds,
                    surviving_triggers=all_triggers,
                    decision_trail=trail,
                    final_action="ACCEPT",
                    new_opening_signature=extract_opening_signature(current_text),
                    blacklist_to_add=_extract_blacklist_words(all_triggers),
                )

            if action == "REWRITE" and rewrite_used >= MAX_REWRITE_ROUNDS:
                # 达到 REWRITE 上限, 降级为 REVISE 一次或直接接受
                if revise_used < MAX_REVISE_ROUNDS:
                    action = "REVISE"
                    trail.append("  ! REWRITE 上限达到, 降级为 REVISE")
                else:
                    trail.append("  ! REWRITE / REVISE 上限均达到, 接受当前文本")
                    return CritiqueOutput(
                        final_text=current_text,
                        rounds=rounds,
                        surviving_triggers=all_triggers,
                        decision_trail=trail,
                        final_action="ACCEPT",
                        new_opening_signature=extract_opening_signature(
                            current_text
                        ),
                        blacklist_to_add=_extract_blacklist_words(all_triggers),
                    )

            if action == "REVISE" and revise_used >= MAX_REVISE_ROUNDS:
                trail.append("  ! REVISE 上限达到, 接受当前文本")
                return CritiqueOutput(
                    final_text=current_text,
                    rounds=rounds,
                    surviving_triggers=all_triggers,
                    decision_trail=trail,
                    final_action="ACCEPT",
                    new_opening_signature=extract_opening_signature(current_text),
                    blacklist_to_add=_extract_blacklist_words(all_triggers),
                )

            # === Step 4: 执行修订 ========================================
            # use_llm=False 时 REVISE/REWRITE 同样不允许调 LLM (此前只挡了
            # critique) — new_text 保持原文, 走下方 "修订未产生新文本" 分支
            # 返回当前文本 + 已记录的触发。
            new_text = current_text
            if action == "REWRITE":
                if use_llm:
                    new_text = await self._llm_rewrite(
                        original=current_text,
                        avoid_codes=summary["high_codes"] + summary["medium_codes"],
                        scene_focus=scene_focus,
                    )
                else:
                    trail.append("  ! use_llm=False, 跳过 REWRITE LLM 调用")
                rewrite_used += 1
            elif action == "REVISE":
                if use_llm:
                    new_text = await self._llm_revise(
                        original=current_text,
                        triggers=all_triggers,
                        scene_focus=scene_focus,
                    )
                else:
                    trail.append("  ! use_llm=False, 跳过 REVISE LLM 调用")
                revise_used += 1

            rounds.append(
                CritiqueRound(
                    round_index=len(rounds) + 1,
                    action=action,
                    triggers_before=[t.to_dict() for t in all_triggers],
                    text_before=current_text,
                    text_after=new_text,
                    rationale=trail[-1],
                )
            )

            # 修订未改变文本 (LLM 不可用 / parse 失败) → 接受当前文本
            if new_text == current_text or not new_text.strip():
                trail.append("  ! 修订未产生新文本, 接受当前")
                return CritiqueOutput(
                    final_text=current_text,
                    rounds=rounds,
                    surviving_triggers=all_triggers,
                    decision_trail=trail,
                    final_action="ACCEPT",
                    new_opening_signature=extract_opening_signature(current_text),
                    blacklist_to_add=_extract_blacklist_words(all_triggers),
                )

            current_text = new_text

    # ------------------------------------------------------------------
    # LLM 子任务
    # ------------------------------------------------------------------

    async def _llm_critique(
        self,
        text: str,
        scene_focus: str,
        viewpoint_character_id: str,
    ) -> list[DeterministicTrigger]:
        user_prompt = f"""\
# 待评估段落

{text}

# 场景信息

scene_focus: {scene_focus or '(未指定)'}
viewpoint_character_id: {viewpoint_character_id or '(未指定)'}

请按 system 提示输出严格 JSON, 仅给出真实触发的项, 其余忽略。
"""
        try:
            resp = await llm_client.chat(
                system_prompt=CRITIC_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=_CRITIQUE_MAX_OUTPUT,
                agent_id="narrative_critic:critique",
                priority="critical",
            )
        except Exception as e:
            logger.warning("NarrativeCritic LLM critique failed: %s", e)
            return []
        # v2.38 (iter#3) — 推理前缀检测: 提供商 reasoning 模型把 JSON 系统提示
        # 当开放问答,输出 "Let me analyze..." 类 prefix。这种响应解析必失败,
        # 浪费整次 budget。提前拦截退回 det-only,避免重试浪费。
        head = (resp.content or "").lstrip().lower()[:32]
        if any(head.startswith(p) for p in _REASONING_LEAK_PREFIXES):
            logger.info(
                "NarrativeCritic critique skipped due to reasoning leak prefix: %r",
                head[:40],
            )
            return []
        return _parse_critic_triggers(resp.content)

    async def _llm_revise(
        self,
        *,
        original: str,
        triggers: list[DeterministicTrigger],
        scene_focus: str,
    ) -> str:
        trigger_lines = "\n".join(
            f"  - [{t.code} | {t.severity}] {t.evidence}" for t in triggers
        )
        user_prompt = f"""\
# 原稿

{original}

# 待修订的触发项

{trigger_lines or '(无)'}

# 场景

scene_focus: {scene_focus or '(未指定)'}

请按 system 提示输出严格 JSON 包含 revised_text 字段, 字数与原稿相近。
"""
        try:
            resp = await llm_client.chat(
                system_prompt=REVISE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=_REVISE_MAX_OUTPUT,
                agent_id="narrative_critic:revise",
                priority="critical",
            )
        except Exception as e:
            logger.warning("NarrativeCritic LLM revise failed: %s", e)
            return original
        return _parse_text_field(resp.content, "revised_text") or original

    async def _llm_rewrite(
        self,
        *,
        original: str,
        avoid_codes: list[str],
        scene_focus: str,
    ) -> str:
        avoid_lines = "\n".join(
            f"  - {code}: {RULES_BY_CODE[code].description}"
            for code in avoid_codes
            if code in RULES_BY_CODE
        )
        user_prompt = f"""\
# 原稿事件骨架 (仅用作内容参考, 不要复用语言)

{original}

# 避免清单 (重写版本严禁触发以下任一)

{avoid_lines or '(无)'}

# 场景

scene_focus: {scene_focus or '(未指定)'}

请按 system 提示输出严格 JSON 包含 rewritten_text 字段。重写必须在
节奏 / 感官 / 内外比例 / 句长 / 信息密度 中至少一个维度上显著不同于原稿。
"""
        try:
            resp = await llm_client.chat(
                system_prompt=REWRITE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.85,
                max_tokens=_REVISE_MAX_OUTPUT,
                agent_id="narrative_critic:rewrite",
                priority="critical",
            )
        except Exception as e:
            logger.warning("NarrativeCritic LLM rewrite failed: %s", e)
            return original
        return _parse_text_field(resp.content, "rewritten_text") or original


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _merge_triggers(
    det: list[DeterministicTrigger], llm: list[DeterministicTrigger]
) -> list[DeterministicTrigger]:
    """合并去重 — 同 code 保留最严重的一条。"""
    seen: dict[str, DeterministicTrigger] = {}
    rank = {"high": 3, "medium": 2, "low": 1}
    for t in det + llm:
        if t.code not in seen or rank.get(t.severity, 0) > rank.get(
            seen[t.code].severity, 0
        ):
            seen[t.code] = t
    return list(seen.values())


def _parse_critic_triggers(raw: str) -> list[DeterministicTrigger]:
    """LLM critic 返回的 JSON → DeterministicTrigger 列表。"""
    try:
        payload = parse_llm_json(raw)
    except json.JSONDecodeError as e:
        logger.warning("NarrativeCritic critique JSON parse failed: %s — raw[:300]=%r", e, raw[:300])
        return []
    out: list[DeterministicTrigger] = []
    for item in payload.get("triggers", []) or []:
        code = str(item.get("code", "")).strip().upper()
        if not code:
            continue
        # severity 兜底
        sev = str(item.get("severity", "")).strip().lower()
        if sev not in {"high", "medium", "low"}:
            sev = RULES_BY_CODE.get(code).severity if code in RULES_BY_CODE else "medium"
        out.append(
            DeterministicTrigger(
                code=code,
                severity=sev,
                evidence=str(item.get("evidence", ""))[:200],
            )
        )
    return out


_REVISE_REWRITE_PLACEHOLDERS = (
    "完整修订后的段落正文",
    "完整重写后的段落正文",
    "此处放真正修订",
    "此处放真正重写",
)


def _parse_text_field(raw: str, field_name: str) -> str:
    try:
        payload = parse_llm_json(raw)
    except json.JSONDecodeError as e:
        logger.warning(
            "NarrativeCritic revise/rewrite JSON parse failed: %s — raw[:300]=%r", e, raw[:300],
        )
        return ""
    val = str(payload.get(field_name, "")).strip()
    # v2.38 (iter#15 review fix) — 占位符检测: 模型偶发直接 copy system prompt 里
    # 的 JSON schema 示例字符串作为 revised_text / rewritten_text, 用户得到的
    # narrative 是 "完整修订后的段落正文" 这种 schema 残骸. 命中即视作未产生新文本.
    for p in _REVISE_REWRITE_PLACEHOLDERS:
        if p in val:
            logger.warning(
                "NarrativeCritic revise/rewrite output is a schema placeholder, "
                "discarding: %r",
                val[:50],
            )
            return ""
    # v2.38 (iter#18 review fix) — 最小长度护栏: schema 说"不少于 80 字" 但
    # 模型偶发只回一两个字截断响应. 短于 40 字几乎肯定是损坏输出, 退化让
    # 调用方 fallback 到 original.
    if len(val) < 40:
        logger.warning(
            "NarrativeCritic revise/rewrite output too short (<40 chars), "
            "discarding: %r",
            val[:50],
        )
        return ""
    return val


def _extract_blacklist_words(triggers: list[DeterministicTrigger]) -> list[str]:
    """从触发证据中抽取需要进入"段内/章内黑名单"的词。"""
    words: set[str] = set()
    for t in triggers:
        if t.code != "A4":
            continue
        # 证据格式: '"仿佛" × 3: ...'
        ev = t.evidence
        if ev.startswith('"'):
            end = ev.find('"', 1)
            if end > 1:
                words.add(ev[1:end])
    return sorted(words)


__all__ = [
    "NarrativeCritic",
    "CritiqueOutput",
    "CritiqueRound",
    "MAX_REVISE_ROUNDS",
    "MAX_REWRITE_ROUNDS",
    "MAX_TOTAL_ROUNDS",
    "ENABLE_LLM_CRITIC",
]
