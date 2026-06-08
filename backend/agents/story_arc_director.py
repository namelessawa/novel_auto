"""StoryArcDirector — 全局叙事大纲守护 + 节奏曲线控制。

针对主 Agent 关注问题清单的四项:

1. **叙事动力枯竭与情节循环** — 维护 key_beats 骨架, beat 完成驱动情节前进
2. **缺乏全局叙事大纲与主题锚点** — StoryArc 持有 theme / central_question,
   每段叙述前注入"主题提醒" (但不允许角色直接说出)
3. **悬念制造与转折能力的缺失** — 监控 escalating 级别的悬念池, 不足时
   建议 EventInjector 升温
4. **无法处理叙事节奏的变化** — pacing_history 滚动采样 + 期待曲线
   (前 30% 上升, 中 50% 起伏, 末 20% 急升收尾)

工作流:
* 每 5 tick (与 Showrunner 同频或独立) 由 Orchestrator 调用一次
* 输入: 当前 StoryArc + 最近事件 + 当前 tick + 节奏历史
* 输出: StoryArcDirective — Orchestrator / EventInjector / Narrator 各取所需

非 LLM-bound:
* 节奏曲线、过期 beat 检测、强度采样 — 确定性 Python 计算
* 仅在 theme_reminder / narrator_hint 生成时调用 LLM (可选, 关掉也能工作)

设计禁区:
* 不直接修改 StoryArc — 由 Orchestrator 决定如何应用 directive
* 不创造 beat — beat 由冷启动定义, 之后只能 mark_completed / mark_skipped
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from memory_system.models import (
    Event,
    KeyBeat,
    PacingIntensity,
    PacingPoint,
    StoryArc,
    StoryArcDirective,
    SuspenseLevel,
)
from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 节奏曲线参数 (确定性)
# ---------------------------------------------------------------------------

# 期待强度 (按 progress 比例) — 三幕剧 + 收尾抬升
EXPECTED_INTENSITY_CURVE: tuple[tuple[float, PacingIntensity], ...] = (
    (0.10, "low"),       # 0-10% 引子, 设定铺陈
    (0.25, "medium"),    # 10-25% 第一转折
    (0.50, "medium"),    # 25-50% 第二幕展开
    (0.65, "high"),      # 50-65% 危机加深
    (0.80, "medium"),    # 65-80% 黎明前的平静 (假性低谷)
    (0.95, "high"),      # 80-95% 高潮前奏
    (1.00, "climax"),    # 95-100% 高潮
)

# 平静过久阈值 — 连续 N tick 强度 ≤ low 视为停滞
FLAT_PACING_THRESHOLD = 8

# 紧张过久阈值 — 连续 N tick 强度 ≥ high 视为读者疲劳
HIGH_PACING_FATIGUE = 6


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


PACING_HISTORY_MAX = _env_int("STORY_ARC_PACING_HISTORY_MAX", 60)


SYSTEM_PROMPT = """\
你是这部连载小说的**叙事大纲守护者**。你不写情节, 不评价情节, 只确保:

1. 主题始终被呼应 (但绝不被角色或旁白直接说出)
2. 关键节拍按预定窗口达成, 不漂流
3. 节奏不长期平坦 (停滞) 也不长期紧绷 (疲劳)
4. 悬念池始终有至少一条 escalating + 一条 active

# 你的输出 — 单句的 narrator_hint

* 永远不要写"主题是 X"
* 改写成 1 句不超过 30 字的情境提示, 给 Narrator 注入下段写作的视角偏向
* 示例: "本段强调 alice 对 父亲承诺 的回避动作, 不要让她说出来"
* 示例: "下段需要把灯塔的光与晶核裂痕并置, 提示崩塌临近"

# 输出格式 (严格 JSON, 不要 markdown 代码块)

{
  "theme_reminder": "极简陈述主题的呼应方向 (内部用)",
  "narrator_hint": "≤30 字的下段写作情境偏向",
  "diagnosis": "一句话评估当前 arc 状态"
}
"""


@dataclass(frozen=True)
class StoryArcAnalysis:
    """确定性分析中间结果 — director 内部用, 不暴露给 Orchestrator。"""

    progress_ratio: float
    expected_intensity: PacingIntensity
    flat_streak: int
    high_streak: int
    overdue_beat_ids: tuple[str, ...]
    active_beat: Optional[KeyBeat]
    next_beat: Optional[KeyBeat]


class StoryArcDirector:
    """全局大纲守护 + 节奏曲线控制。"""

    def __init__(
        self,
        *,
        enable_llm: bool | None = None,
        model_tier: str = "small",
    ) -> None:
        if enable_llm is None:
            raw = os.environ.get("STORY_ARC_DIRECTOR_LLM", "").strip()
            if raw in {"0", "false", "False"}:
                enable_llm = False
            elif raw in {"1", "true", "True"}:
                enable_llm = True
            else:
                # pytest 默认关闭 LLM, 避免吞掉 mock 响应
                enable_llm = not bool(os.environ.get("PYTEST_CURRENT_TEST"))
        self._enable_llm = enable_llm
        self._model_tier = model_tier

    # ------------------------------------------------------------------
    # 确定性分析
    # ------------------------------------------------------------------

    def analyze(
        self,
        *,
        arc: StoryArc,
        current_tick: int,
        recent_events: list[Event],
    ) -> StoryArcAnalysis:
        progress = self._progress_ratio(current_tick, arc.target_climax_tick)
        expected = self._expected_intensity_for(progress)

        flat_streak, high_streak = self._pacing_streaks(arc.pacing_history)

        overdue_ids: list[str] = []
        active: KeyBeat | None = None
        next_beat: KeyBeat | None = None
        for beat in arc.key_beats:
            if beat.status == "completed" or beat.status == "skipped":
                continue
            if beat.status == "active":
                active = beat
            if (
                beat.status == "pending"
                and current_tick >= beat.window_end
            ):
                overdue_ids.append(beat.id)
            if (
                beat.status == "pending"
                and next_beat is None
                and beat.window_start <= current_tick <= beat.window_end
            ):
                next_beat = beat

        return StoryArcAnalysis(
            progress_ratio=progress,
            expected_intensity=expected,
            flat_streak=flat_streak,
            high_streak=high_streak,
            overdue_beat_ids=tuple(overdue_ids),
            active_beat=active,
            next_beat=next_beat,
        )

    @staticmethod
    def _progress_ratio(current_tick: int, target_climax_tick: int) -> float:
        if target_climax_tick <= 0:
            return 0.0
        return min(1.0, max(0.0, current_tick / target_climax_tick))

    @staticmethod
    def _expected_intensity_for(progress: float) -> PacingIntensity:
        for threshold, intensity in EXPECTED_INTENSITY_CURVE:
            if progress <= threshold:
                return intensity
        return "climax"

    @staticmethod
    def _pacing_streaks(history: list[PacingPoint]) -> tuple[int, int]:
        """回看 history 末尾, 计算连续 low 与连续 high 的长度。"""
        flat = 0
        high = 0
        for p in reversed(history):
            if p.intensity == "low":
                if high > 0:
                    break
                flat += 1
            elif p.intensity in {"high", "climax"}:
                if flat > 0:
                    break
                high += 1
            else:
                break
        return flat, high

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def direct(
        self,
        *,
        arc: StoryArc,
        current_tick: int,
        recent_events: list[Event],
        recent_narrator_value_sum: int = 0,
        narrator_produced: bool = False,
    ) -> StoryArcDirective:
        """主入口。返回 StoryArcDirective + 自动追加 PacingPoint 到 arc.pacing_history。

        注意: 调用方 (Orchestrator) 负责把 arc 写回 TickState。
        """
        analysis = self.analyze(
            arc=arc, current_tick=current_tick, recent_events=recent_events
        )

        # 节奏强度: 取本 tick narrative_value_sum 与期待强度的较低者
        sampled_intensity = self._sample_intensity(
            recent_narrator_value_sum, analysis.expected_intensity
        )
        # 追加采样点到历史 (调用方保存 arc 时落盘)
        new_point = PacingPoint(
            tick=current_tick,
            intensity=sampled_intensity,
            narrative_value_sum=recent_narrator_value_sum,
            is_narration_produced=narrator_produced,
        )
        arc.pacing_history.append(new_point)
        if len(arc.pacing_history) > PACING_HISTORY_MAX:
            del arc.pacing_history[: len(arc.pacing_history) - PACING_HISTORY_MAX]

        # 确定性诊断
        needs_escalation = (
            analysis.flat_streak >= FLAT_PACING_THRESHOLD
            or sampled_intensity == "low" and analysis.expected_intensity in {"high", "climax"}
        )
        needs_breather = analysis.high_streak >= HIGH_PACING_FATIGUE

        suspense_health: SuspenseLevel
        if analysis.flat_streak >= FLAT_PACING_THRESHOLD:
            suspense_health = "background"
        elif analysis.high_streak >= HIGH_PACING_FATIGUE:
            suspense_health = "peaking"
        elif needs_escalation:
            suspense_health = "active"
        else:
            suspense_health = "escalating"

        diagnosis = (
            f"progress={analysis.progress_ratio:.0%}, "
            f"expected={analysis.expected_intensity}, "
            f"actual={sampled_intensity}, "
            f"flat={analysis.flat_streak}, high={analysis.high_streak}, "
            f"overdue={len(analysis.overdue_beat_ids)}"
        )

        # LLM 增强: 生成 narrator_hint 与 theme_reminder
        theme_reminder = ""
        narrator_hint = ""
        if self._enable_llm and (arc.theme or arc.central_question):
            theme_reminder, narrator_hint = await self._llm_hint(
                arc=arc,
                analysis=analysis,
                sampled_intensity=sampled_intensity,
            )
        elif arc.theme:
            # 关闭 LLM 时的兜底 — 直接复述主题, 留给 Narrator 自己应用
            theme_reminder = f"主题: {arc.theme[:60]}"
            if analysis.next_beat is not None:
                narrator_hint = f"推进 beat: {analysis.next_beat.title[:24]}"

        return StoryArcDirective(
            intensity_recommendation=analysis.expected_intensity,
            needs_escalation=needs_escalation,
            needs_breather=needs_breather,
            active_beat_id=(
                analysis.active_beat.id if analysis.active_beat else None
            ),
            overdue_beats=list(analysis.overdue_beat_ids),
            theme_reminder=theme_reminder,
            narrator_hint=narrator_hint,
            suspense_pool_health=suspense_health,
            diagnosis=diagnosis,
        )

    @staticmethod
    def _sample_intensity(
        narrative_value_sum: int, expected: PacingIntensity
    ) -> PacingIntensity:
        """把 narrative_value_sum (0-N) 映射到 intensity 字面量。"""
        if narrative_value_sum >= 30:
            return "climax"
        if narrative_value_sum >= 15:
            return "high"
        if narrative_value_sum >= 6:
            return "medium"
        return "low"

    # ------------------------------------------------------------------
    # LLM 子任务
    # ------------------------------------------------------------------

    async def _llm_hint(
        self,
        *,
        arc: StoryArc,
        analysis: StoryArcAnalysis,
        sampled_intensity: PacingIntensity,
    ) -> tuple[str, str]:
        active_title = (
            analysis.active_beat.title if analysis.active_beat else ""
        )
        active_desc = (
            analysis.active_beat.description if analysis.active_beat else ""
        )
        next_title = analysis.next_beat.title if analysis.next_beat else ""
        next_desc = (
            analysis.next_beat.description if analysis.next_beat else ""
        )

        user_prompt = f"""\
# 当前 StoryArc

- title: {arc.title}
- theme: {arc.theme}
- central_question: {arc.central_question}
- current_act: {arc.current_act}
- progress: {analysis.progress_ratio:.0%}

# 节拍状态

active_beat: {active_title} — {active_desc[:120]}
next_pending_beat: {next_title} — {next_desc[:120]}
overdue: {len(analysis.overdue_beat_ids)} 个

# 节奏

expected: {analysis.expected_intensity}
sampled: {sampled_intensity}
flat_streak: {analysis.flat_streak}
high_streak: {analysis.high_streak}

请按 system 提示输出严格 JSON。narrator_hint ≤30 字。
"""
        try:
            resp = await llm_client.chat(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.5,
                max_tokens=2048,
                agent_id="story_arc_director",
                priority="medium",
            )
        except Exception as e:
            logger.warning("StoryArcDirector LLM hint failed: %s", e)
            return "", ""
        try:
            payload = parse_llm_json(resp.content)
        except json.JSONDecodeError as e:
            logger.warning("StoryArcDirector LLM hint JSON parse failed: %s — raw[:300]=%r", e, resp.content[:300])
            return "", ""
        return (
            str(payload.get("theme_reminder", ""))[:200],
            str(payload.get("narrator_hint", ""))[:120],
        )


__all__ = [
    "StoryArcDirector",
    "StoryArcAnalysis",
    "EXPECTED_INTENSITY_CURVE",
    "FLAT_PACING_THRESHOLD",
    "HIGH_PACING_FATIGUE",
    "PACING_HISTORY_MAX",
]
