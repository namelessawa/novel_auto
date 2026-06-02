"""CharacterArcTracker — 人物弧光监控 + 性格漂移检测 + 配角独立性守护。

针对主 Agent 关注问题清单的四项:

1. **人物塑造的扁平化与失真** — 检测 B5 (主角全程正确), B4 (内心过载)
2. **性格一致性的长期崩坏** — 滑动窗口对比 CharacterAction 与 profile.core_values,
   检测 B1 (违背动机) 与 B2 (说话像别人)
3. **无法实现真实的人物成长与转变** — 维护 ArcStage 推进; arc_progress ≥0.85
   仍处 起点 → 强制升阶或标 stalled
4. **配角与群像塑造的彻底失败** — 监控 B 级角色 independent_agenda 推进, B3
   (配角只为主角而存在) 触发干预

设计:
* 每 30 tick (CONSISTENCY_GUARDIAN_CADENCE 同频或独立) 调用
* 输入: A/B 级 CharacterState 列表 + 最近 N 个 CharacterAction
* 输出: per-character `CharacterArcReport` + 总 `CharacterArcTrackerOutput`
* 确定性检测 (无 LLM): 阶段停滞过久 / agenda 缺失 / arc_progress vs arc_stage 不匹配
* LLM 增强 (可选): 漂移评分 + arc_stage 推荐 + 单句 fingerprint 校验
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from memory_system.models import (
    ArcStage,
    CharacterAction,
    CharacterProfile,
    CharacterState,
)
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


# ArcStage 推进顺序 — 编剧界 7 阶段
ARC_STAGE_ORDER: tuple[ArcStage, ...] = (
    "起点",
    "觉醒",
    "抗拒",
    "挫折",
    "转变",
    "抉择",
    "结局",
)
ARC_STAGE_INDEX: dict[ArcStage, int] = {s: i for i, s in enumerate(ARC_STAGE_ORDER)}


# arc_progress 与 arc_stage 的期待映射 — 偏离 > tolerance 触发警报
EXPECTED_PROGRESS_PER_STAGE: dict[ArcStage, tuple[float, float]] = {
    "起点": (0.0, 0.15),
    "觉醒": (0.10, 0.30),
    "抗拒": (0.25, 0.50),
    "挫折": (0.40, 0.65),
    "转变": (0.55, 0.80),
    "抉择": (0.70, 0.95),
    "结局": (0.85, 1.0),
}

STALLED_TICKS = 80  # 同 arc_stage 停留 > 80 tick 视为停滞


@dataclass
class CharacterArcReport:
    character_id: str
    current_stage: ArcStage
    suggested_stage: ArcStage | None = None
    is_stalled: bool = False
    progress_mismatch: bool = False
    drift_codes: list[str] = field(default_factory=list)  # B1/B2/B4/B5 等
    drift_evidence: list[str] = field(default_factory=list)
    independent_agenda_health: str = "ok"  # ok|low|empty
    speech_compliance: str = "unknown"  # ok|loose|mismatch
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "character_id": self.character_id,
            "current_stage": self.current_stage,
            "suggested_stage": self.suggested_stage,
            "is_stalled": self.is_stalled,
            "progress_mismatch": self.progress_mismatch,
            "drift_codes": list(self.drift_codes),
            "drift_evidence": list(self.drift_evidence),
            "independent_agenda_health": self.independent_agenda_health,
            "speech_compliance": self.speech_compliance,
            "rationale": self.rationale,
        }


@dataclass
class CharacterArcTrackerOutput:
    reports: list[CharacterArcReport] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "reports": [r.to_dict() for r in self.reports],
            "summary": self.summary,
        }

    def stalled_ids(self) -> list[str]:
        return [r.character_id for r in self.reports if r.is_stalled]

    def drift_ids(self) -> list[str]:
        return [r.character_id for r in self.reports if r.drift_codes]


SYSTEM_PROMPT = """\
你是这部连载小说的**人物弧光与性格一致性监督者**。你不写情节, 不替代 Narrator,
只检测以下失败模式:

# 你的检测维度

## 1. 性格漂移 (B 系列触发)
- B1: 角色行为违背已确立的核心动机/性格, 且原文未交代变化
- B2: 去掉名字后无法分辨是谁在说话 (对照 speech_fingerprint_features)
- B4: 内心独白字数 > (行动+对话) × 1.5
- B5: 角色全程"正确", 未犯错、未困惑、未失态
- B6: 不同角色面对同一事件反应趋同, 缺乏个体性

## 2. 弧光推进
- arc_progress 与 arc_stage 错配 (如 progress 0.7 仍处 觉醒)
- 阶段停留过久 (按 stalled_ticks 阈值)
- 建议下一阶段 (从 起点→觉醒→抗拒→挫折→转变→抉择→结局)

## 3. 配角独立议程
- B 级角色无 independent_agenda → 触发 B3 (配角只为主角而存在)
- 议程从未被推进或回应

# 输出格式 (严格 JSON, 不要 markdown 代码块)

{
  "reports": [
    {
      "character_id": "alice",
      "drift_codes": ["B5"],
      "drift_evidence": ["最近 5 个行动均成功, 无错误判断"],
      "suggested_stage": "觉醒",
      "speech_compliance": "ok",
      "rationale": "需要安排一次明显的判断失误"
    }
  ],
  "summary": "总体: 主角弧光停滞, 配角缺乏独立议程"
}
"""


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except ValueError:
        return default


class CharacterArcTracker:
    """每 N tick 评估 A/B 级角色的弧光与性格一致性。"""

    def __init__(
        self,
        *,
        enable_llm: bool | None = None,
        model_tier: str = "medium",
    ) -> None:
        if enable_llm is None:
            raw = os.environ.get("CHARACTER_ARC_TRACKER_LLM", "").strip()
            if raw in {"0", "false", "False"}:
                enable_llm = False
            elif raw in {"1", "true", "True"}:
                enable_llm = True
            else:
                enable_llm = not bool(os.environ.get("PYTEST_CURRENT_TEST"))
        self._enable_llm = enable_llm
        self._model_tier = model_tier

    # ------------------------------------------------------------------
    # 确定性检测
    # ------------------------------------------------------------------

    @staticmethod
    def detect_progress_mismatch(state: CharacterState) -> bool:
        lo, hi = EXPECTED_PROGRESS_PER_STAGE.get(state.arc_stage, (0.0, 1.0))
        return not (lo <= state.arc_progress <= hi)

    @staticmethod
    def detect_stalled(state: CharacterState, current_tick: int) -> bool:
        if state.arc_stage == "结局":
            return False  # 终结态不算停滞
        ticks = current_tick - state.arc_stage_entered_tick
        return ticks >= STALLED_TICKS

    @staticmethod
    def detect_agenda_health(
        profile: CharacterProfile, state: CharacterState
    ) -> str:
        if profile.importance_tier == "A":
            return "ok"  # A 级角色议程通过 arc_goal 表达, 不强制
        if not state.independent_agenda:
            return "empty"
        if len(state.independent_agenda) < 2:
            return "low"
        return "ok"

    @staticmethod
    def suggest_next_stage(state: CharacterState) -> ArcStage | None:
        idx = ARC_STAGE_INDEX.get(state.arc_stage, 0)
        # 检测是否 progress 超出当前阶段上限 — 提议升阶
        lo, hi = EXPECTED_PROGRESS_PER_STAGE.get(state.arc_stage, (0.0, 1.0))
        if state.arc_progress > hi and idx + 1 < len(ARC_STAGE_ORDER):
            return ARC_STAGE_ORDER[idx + 1]
        return None

    def deterministic_report(
        self,
        *,
        profile: CharacterProfile,
        state: CharacterState,
        current_tick: int,
    ) -> CharacterArcReport:
        is_stalled = self.detect_stalled(state, current_tick)
        progress_mismatch = self.detect_progress_mismatch(state)
        agenda_health = self.detect_agenda_health(profile, state)
        suggested = self.suggest_next_stage(state)

        drift_codes: list[str] = []
        drift_evidence: list[str] = []
        if agenda_health == "empty" and profile.importance_tier == "B":
            drift_codes.append("B3")
            drift_evidence.append(
                f"B 级角色 {profile.id} 无 independent_agenda"
            )
        if is_stalled:
            drift_evidence.append(
                f"已在 {state.arc_stage} 停留 ≥ {STALLED_TICKS} tick"
            )

        rationale = ""
        if is_stalled and suggested:
            rationale = f"建议推进 {state.arc_stage} → {suggested}"
        elif is_stalled:
            rationale = f"{state.arc_stage} 停滞, 但 progress 尚未超阈值, 需要事件干预"
        elif progress_mismatch:
            rationale = (
                f"arc_progress {state.arc_progress:.2f} 不在 "
                f"{state.arc_stage} 的预期区间"
            )

        return CharacterArcReport(
            character_id=profile.id,
            current_stage=state.arc_stage,
            suggested_stage=suggested,
            is_stalled=is_stalled,
            progress_mismatch=progress_mismatch,
            drift_codes=drift_codes,
            drift_evidence=drift_evidence,
            independent_agenda_health=agenda_health,
            speech_compliance="unknown",
            rationale=rationale,
        )

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        *,
        profiles: dict[str, CharacterProfile],
        states: dict[str, CharacterState],
        recent_actions_by_char: dict[str, list[CharacterAction]],
        current_tick: int,
    ) -> CharacterArcTrackerOutput:
        """主入口。A/B 级角色逐一评估。"""
        reports: list[CharacterArcReport] = []
        ab_profiles = [
            p for p in profiles.values() if p.importance_tier in ("A", "B")
        ]

        for prof in ab_profiles:
            state = states.get(prof.id)
            if state is None:
                continue
            base = self.deterministic_report(
                profile=prof, state=state, current_tick=current_tick
            )
            reports.append(base)

        # LLM 增强 — 一次性评估所有 A 级角色的漂移
        if self._enable_llm and reports:
            try:
                llm_codes = await self._llm_drift_evaluation(
                    profiles=profiles,
                    states=states,
                    recent_actions=recent_actions_by_char,
                    reports=reports,
                )
                self._merge_llm_results(reports, llm_codes)
            except Exception as e:
                logger.warning("CharacterArcTracker LLM eval failed: %s", e)

        summary = self._compose_summary(reports)
        return CharacterArcTrackerOutput(reports=reports, summary=summary)

    @staticmethod
    def _compose_summary(reports: list[CharacterArcReport]) -> str:
        stalled = [r.character_id for r in reports if r.is_stalled]
        drift = [r.character_id for r in reports if r.drift_codes]
        agenda = [
            r.character_id
            for r in reports
            if r.independent_agenda_health == "empty"
        ]
        parts: list[str] = []
        if stalled:
            parts.append(f"停滞: {','.join(stalled)}")
        if drift:
            parts.append(f"漂移: {','.join(drift)}")
        if agenda:
            parts.append(f"无议程: {','.join(agenda)}")
        return " | ".join(parts) or "全员稳定"

    # ------------------------------------------------------------------
    # LLM 子任务
    # ------------------------------------------------------------------

    async def _llm_drift_evaluation(
        self,
        *,
        profiles: dict[str, CharacterProfile],
        states: dict[str, CharacterState],
        recent_actions: dict[str, list[CharacterAction]],
        reports: list[CharacterArcReport],
    ) -> dict[str, dict]:
        # 构造紧凑输入: 每角色 profile.id/personality/speech_style +
        # arc_stage + recent_actions 摘要
        char_blobs = []
        for r in reports:
            cid = r.character_id
            prof = profiles.get(cid)
            state = states.get(cid)
            if prof is None or state is None:
                continue
            actions = recent_actions.get(cid, [])[-5:]
            char_blobs.append(
                {
                    "id": cid,
                    "tier": prof.importance_tier,
                    "personality": prof.personality[:80],
                    "speech_style": prof.speech_style[:60],
                    "speech_fingerprint_features": list(
                        state.speech_fingerprint_features
                    ),
                    "arc_goal": state.arc_goal[:80],
                    "arc_stage": state.arc_stage,
                    "arc_progress": state.arc_progress,
                    "recent_actions": [
                        {
                            "type": a.action_type,
                            "desc": (a.description or "")[:80],
                            "dialogue": (a.dialogue_spoken or "")[:60],
                            "emotional_shift": a.emotional_shift[:30],
                        }
                        for a in actions
                    ],
                }
            )

        user_prompt = f"""\
# 待评估角色清单

```json
{json.dumps(char_blobs, ensure_ascii=False, indent=2)}
```

# 检测要求

对每个角色:
1. 判断 B1/B2/B4/B5/B6 是否触发, 给出 evidence (引用 recent_actions 的具体内容)
2. 判断 speech_compliance: ok (符合) / loose (略偏) / mismatch (不像本人)
3. 若 arc 状态需调整, 给出 suggested_stage

请按 system 提示输出严格 JSON。
"""
        resp = await llm_client.chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=8192,
        )
        text = resp.content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("CharacterArcTracker LLM JSON parse failed")
            return {}
        out: dict[str, dict] = {}
        for item in payload.get("reports", []) or []:
            cid = item.get("character_id")
            if cid:
                out[str(cid)] = item
        return out

    @staticmethod
    def _merge_llm_results(
        reports: list[CharacterArcReport], llm_codes: dict[str, dict]
    ) -> None:
        for r in reports:
            patch = llm_codes.get(r.character_id)
            if not patch:
                continue
            new_codes = list(patch.get("drift_codes", []) or [])
            for c in new_codes:
                if c and c not in r.drift_codes:
                    r.drift_codes.append(c)
            new_ev = list(patch.get("drift_evidence", []) or [])
            for ev in new_ev:
                if ev and ev not in r.drift_evidence:
                    r.drift_evidence.append(str(ev)[:200])
            suggested = patch.get("suggested_stage")
            if suggested and r.suggested_stage is None:
                r.suggested_stage = suggested
            speech = patch.get("speech_compliance")
            if speech in {"ok", "loose", "mismatch"}:
                r.speech_compliance = speech
            if patch.get("rationale") and not r.rationale:
                r.rationale = str(patch["rationale"])[:200]


__all__ = [
    "CharacterArcTracker",
    "CharacterArcReport",
    "CharacterArcTrackerOutput",
    "ARC_STAGE_ORDER",
    "ARC_STAGE_INDEX",
    "EXPECTED_PROGRESS_PER_STAGE",
    "STALLED_TICKS",
]
