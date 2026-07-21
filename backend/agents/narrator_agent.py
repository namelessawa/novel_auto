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
from dataclasses import dataclass, field, replace

from agents.narrative_critic import CritiqueOutput, NarrativeCritic
from agents.quality_spec import render_narrator_discipline_block
from memory_system.models import (
    CharacterAction,
    CharacterProfile,
    CharacterState,
    Event,
    OpenLoop,
    StyleAnchor,
    WorldState,
)
from nf_core.env_helpers import env_bool, env_bool_tri
from nf_core.json_utils import parse_llm_json, strip_code_fence
from nf_core.llm_client import llm_client
from nf_core.reasoning_filter import strip_reasoning_leak as _strip_reasoning_leak
from narrative.typed_continuity import (
    continuity_legacy_view,
    normalise_continuity_state as normalise_typed_continuity_state,
)
from quality_metrics.style_contract import style_contract_report

# Phase 5+: style preset 由 env 控制 — bootstrap / matrix bench 在 spawn 子进程
# 时设 NOVEL_STYLE_PRESET=<key>, narrator 在 user_prompt 头部追加预设的写作契约.
# 未设 / 空 / unknown key 时 silent fallback 到默认行为 (= literary preset 但不
# 显式注入, 老 bench 完全等价).
try:
    from novel_presets import StylePreset, get_style_preset, list_style_keys
    _STYLE_PRESETS_AVAILABLE = True
except ImportError:  # pragma: no cover — defensive 在裸 import 环境
    _STYLE_PRESETS_AVAILABLE = False

    def list_style_keys() -> list[str]:
        return []

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
    resolved_open_loops: list[dict] = field(default_factory=list)
    newly_opened_loops: list[OpenLoop] = field(default_factory=list)
    # 正文结束时的叙事层状态（非 WorldState），用于约束下一段中的
    # 伤势、物品归属/数量/损坏与角色知识。
    continuity_state: dict = field(default_factory=dict)
    # Phase 8: normalization provenance + retained raw payload. Existing consumers
    # continue to use continuity_state (or its conservative legacy view).
    continuity_state_audit: dict = field(default_factory=dict)
    continuity_guard_trace: dict = field(default_factory=dict)
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
    # iter#R — 当 critic 被 gate (length / importance / disabled) 跳过时记录
    # 原因, _append_critic_log 据此写 SKIP 行. 空字符串 = critic 真跑了或
    # narrator silent (上下文区分).
    critique_skip_reason: str = ""
    # v2.46: 风格专属 det 验收 + 最多一次定向重写审计记录。
    style_contract_trace: dict = field(default_factory=dict)


NARRATOR_SYSTEM_PROMPT = (
    """\
你是这部连载小说的执笔人。简报是这段世界时间的素材, 你把值得讲的部分写成
连载正文的下一段。读者读到的是连续小说 — 每段都接着前文, 同一位作者笔下。

# 写作方法

1. **场景三要素**: 视点角色此刻要什么(目标), 谁/什么在挡他(阻力),
   段末有什么变了(进展/代价/新问题)。三者缺一即沉默。
2. **对白承载冲突**: 简报里的台词原文是首要素材, 优先入正文 (措辞可调,
   立场不可改)。穿插动作节拍(端杯、移开视线、半句被打断), 不堆引号。
   两人说话要听得出是两个人。
3. **具体物优先, 内心要薄**: 每段至少一个摄像机拍得到的具体物。情绪由
   身体动作+物件反应承载, 不直报。内心一两句白描即可, 贴着目标走;
   △ 标记的私密动机只供你理解, 不可整句抄成旁白。
4. **节奏与衔接**: 长短句交错, 关键时刻用短句。第一句必须能直接接在
   "前文结尾"后面读下去 — 不重新介绍场景, 不复述前文。角色第二次起
   直接用名字。

# 信息纪律

* 人物 / 地点 / 势力 / 既定事实以简报为准, 不发明新设定。
* 高价值源事件是模拟世界中已经发生的事实，不是可选灵感。若你在
  events_consumed 声明消费，正文必须写到它的明确结果，不得停在准备行动时。
* 允许无害补白(器物、天气、动作、过场对话), 不许引入新事实或改变角色
  立场 / 知识范围。
* 角色只知道他该知道的事; 矛盾不要自行修正, 写进 consistency_flags。

# 取舍

优先级: 拐点 > 揭示 > 对峙 > 有信息量的日常。素材整段不值得写时
narrative_text 留空, 系统会自动记账。伏笔: 优先呼应开放 loops, 至多新
种 1 个 (在 origin_event_ids 列触发事件 id)。只有正文已经给出明确回答、人物
选择及可见后果时才能填 resolved_open_loops；必须同时引用真实 loop_id 和本 tick
已消费的 evidence_event_ids。仅仅再次提到、变冷或想减少池子都不算兑现。
新种 loop 时必须填写 promised_question（读者最终等待回答的具体问题）以及
payoff_requirements（至少包含“证据”“人物选择”“可见后果”中的一项）。

# 跨段状态账本

* continuity_state 输出完整 typed v1 状态；地点与移动分开，支撑/搬运不得写进地点。
* ID 只能从本次允许列表选择；不确定时用 null、unknown 或空列表，禁止猜测。
* 上一段账本是当前状态。保留仍然有效的旧条目；只有正文明写交付、
  使用、损坏、移动、受伤或得知事件时才能更新。已交付/用完/损坏的
  物品不得恢复；变化必须在 narrative_text 中看得见。

"""
    + render_narrator_discipline_block()
    + """

# 输出禁区 (违反立即返工 — 极重要)

* narrative_text 只放小说正文中文本身, 不写任何 meta 思考。绝不出现:
  "首先, 理解任务" / "首先, 我看素材" / "从素材看" / "关键点包括" /
  "好的, 以下是" / "让我先 / 让我来" / "Let me" / "I'll write" /
  "First, I"。这些是分析自言自语, 读者看的是小说。
* 不在 narrative_text 里出现系统术语 (tick / 素材 / 简报 / 事件摘要 /
  task / viewpoint / narrative_text / 字段名)。
* 不列编号清单解释打算怎么写; 不写 "(约 800 字)" 之类的字数标注;
  不输出省略号 (...)。
* 直接给真正的小说正文, 像作家从前文接着写。

# 输出格式 (严格 JSON, 不要 markdown 代码块, 不要省略号占位符)

{
  "narrative_text": "(此处放真正的中文小说正文, 至少 80 字)",
  "estimated_length": "short",
  "viewpoint_characters": ["char_su_mo"],
  "scene_focus": "苏默冒雨向安全屋移动",
  "events_consumed": ["evt_001"],
  "open_loops_referenced": [],
  "resolved_open_loops": [],
  "newly_opened_loops": [],
  "continuity_state": {"schema_version": "1", "time_marker": "", "characters": {}, "items": {}, "newly_known_fact_ids": {}, "active_open_loop_ids": []},
  "style_diagnostics": {"avg_sentence_length": 18, "rhetoric_density": "low"},
  "consistency_flags": []
}

你是这部小说的灵魂。写的是人和他们要的东西, 不是气氛。
"""
)


# 触发产出的最低事件总分阈值
_NARRATE_SKIP_THRESHOLD = 5
_NARRATE_SHORT_THRESHOLD = 15
_NARRATE_FULL_THRESHOLD = 30

# 压缩段落 escape valve:距上次叙述超过此 tick 数即使分数不够也要给个时间流逝段
_TIME_LAPSE_TICKS = 10

# 前文结尾注入上限 (字符)。再长对衔接没有边际收益, 反而稀释素材权重。
# v2.38 (iter#7) — 1200 → 800. 实测最后 800 字足以维持文风/视角延续,
# 多出来的 400 字主要是上一段已经讲完的素材, 占 input prompt 体积。
_PROSE_TAIL_MAX_CHARS = 800
# 场景简报里渲染的最大角色数 / 事件素材数
# v2.38 (iter#7) — char 8→5, events 24→16. 多于此数对单段 tick 是噪声,
# 反而稀释 Narrator 注意力, 同时占 input prompt 体积。
_MAX_BRIEF_CHARS_COUNT = 5
_MAX_BRIEF_EVENTS = 16
_NARRATOR_TEMPERATURE_DEFAULT = 0.65


def _compact_continuity_value(value, *, depth: int = 0):
    """限制模型返回的状态账本体积，避免未受控 JSON 污染后续 prompt。"""
    # TypedContinuityState nests injury records at depth 4; retain their typed
    # fields while keeping the existing per-container and per-string caps.
    if depth >= 6:
        return str(value)[:240]
    if isinstance(value, dict):
        compact: dict[str, object] = {}
        for raw_key, raw_value in list(value.items())[:40]:
            key = str(raw_key).strip()[:80]
            if key:
                compact[key] = _compact_continuity_value(
                    raw_value, depth=depth + 1
                )
        return compact
    if isinstance(value, list):
        return [
            _compact_continuity_value(item, depth=depth + 1)
            for item in value[:30]
        ]
    if isinstance(value, str):
        return value.strip()[:300]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:240]


def _normalise_continuity_state(value) -> dict:
    if not isinstance(value, dict):
        return {}
    compact = _compact_continuity_value(value)
    return compact if isinstance(compact, dict) else {}


def _continuity_reference_catalogs(
    *,
    tick_events: list[Event],
    char_states: list[CharacterState],
    char_profiles: dict[str, CharacterProfile],
    world_state: WorldState | None,
    open_loops: list[OpenLoop],
    previous_state: dict,
) -> dict[str, set[str]]:
    """Build ID catalogs only from context already available to Narrator."""
    character_ids = set(char_profiles)
    character_ids.update(state.character_id for state in char_states)
    location_ids = {
        location.id for location in (world_state.locations if world_state else [])
    }
    item_ids = {
        str(item).strip()
        for state in char_states
        for item in state.inventory
        if str(item).strip()
    }
    fact_ids: set[str] = set()
    event_ids = {event.id for event in tick_events}
    open_loop_ids = {loop.id for loop in open_loops}

    if isinstance(previous_state, dict):
        raw_items = previous_state.get("items") or {}
        if isinstance(raw_items, dict):
            item_ids.update(str(item_id).strip() for item_id in raw_items if str(item_id).strip())
        raw_characters = previous_state.get("characters") or {}
        if isinstance(raw_characters, dict):
            for raw_character in raw_characters.values():
                if not isinstance(raw_character, dict):
                    continue
                fact_ids.update(
                    str(fact_id).strip()
                    for fact_id in (raw_character.get("knowledge_fact_ids") or [])
                    if str(fact_id).strip()
                )
                for injury in raw_character.get("injuries") or []:
                    if isinstance(injury, dict) and injury.get("source_event_id"):
                        event_ids.add(str(injury["source_event_id"]).strip())
        raw_known = previous_state.get("newly_known_fact_ids") or {}
        if isinstance(raw_known, dict):
            for raw_fact_ids in raw_known.values():
                if isinstance(raw_fact_ids, list):
                    fact_ids.update(
                        str(fact_id).strip()
                        for fact_id in raw_fact_ids
                        if str(fact_id).strip()
                    )
        open_loop_ids.update(
            str(loop_id).strip()
            for loop_id in (previous_state.get("active_open_loop_ids") or [])
            if str(loop_id).strip()
        )
    return {
        "valid_character_ids": character_ids,
        "valid_location_ids": location_ids,
        "valid_item_ids": item_ids,
        "valid_fact_ids": fact_ids,
        "valid_open_loop_ids": open_loop_ids,
        "valid_event_ids": event_ids,
    }


def _normalise_generated_continuity(
    value,
    *,
    catalogs: dict[str, set[str]] | None,
) -> tuple[dict, dict]:
    compact = _normalise_continuity_state(value)
    result = normalise_typed_continuity_state(compact, **(catalogs or {}))
    if result.source_schema == "typed_v1":
        state = result.typed_state.model_dump(mode="json")
    elif result.source_schema == "legacy":
        state = compact
    else:
        state = {}
    return state, result.model_dump(mode="json")


def _continuity_guard_enabled() -> bool:
    raw = os.environ.get("NARRATOR_STATE_VERIFY_ENABLE", "").strip().lower()
    if raw:
        return raw not in {"0", "false", "no", "off"}
    # 单元测默认不额外消耗 mock 响应；生产与实写默认开。
    return "PYTEST_CURRENT_TEST" not in os.environ


def _narrator_temperature() -> float:
    raw = os.environ.get("NARRATOR_TEMPERATURE", "").strip()
    if not raw:
        return _NARRATOR_TEMPERATURE_DEFAULT
    try:
        return min(1.2, max(0.0, float(raw)))
    except ValueError:
        return _NARRATOR_TEMPERATURE_DEFAULT


# v2.38 (iter#10) — 短段落跳过 critic 的字数下限. 一次 critique+rewrite
# ~4500 tokens 比 < 400 字段落本身还多, 收益不成比例.
# v2.38 (iter#12 review fix) — 此前定义在 narrate() 方法体里, 不利于
# 测试 monkeypatch / 配置发现. 提升到模块级.
# v2.38 (iter#25) — 默认 400 → 600. 实测 400-600 字 narrative critic 触发
# REVISE+REWRITE 时 ~14k tokens (与产出本身同级), 但短中段落即使有结构
# 性触发, 改写后净收益不显著. 600 字以上才是值得反复打磨的"段".
# v2.38 (iter#27 review fix) — 用 lazy 函数读 env, 测试可以
# monkeypatch.setenv 后正确改阈值; 此前 module load 时冻结到常量,
# monkeypatch 无效.
_CRITIC_MIN_NARRATIVE_LEN_DEFAULT = 600


def _critic_min_narrative_len() -> int:
    raw = os.environ.get("CRITIC_MIN_NARRATIVE_LEN", "").strip()
    if not raw:
        return _CRITIC_MIN_NARRATIVE_LEN_DEFAULT
    try:
        v = int(raw)
        # v2.38 (iter#54) — 负值或 0 退回 default (0 等于 critic 总开,
        # 负值无意义), 防误配把 critic 全打开蹦 token 预算.
        return v if v > 0 else _CRITIC_MIN_NARRATIVE_LEN_DEFAULT
    except ValueError:
        return _CRITIC_MIN_NARRATIVE_LEN_DEFAULT


# Phase 2 Stage 2 (iter#84) — importance gating.
# Stage 1 裁决 (verdict-v15-vs-v16.md) 揭示: 平均场景 v16 (critic 关)
# win 70%, 但 v15 (critic 开) win 的 3 场都关 "推进+角色" → critic 帮
# 的是关键节拍而非平均质量. 用 tick 重要性门控: 高 importance → critic
# 全链路 (v15 路径); 低 importance → 跳 critic (v16 路径).
#
# importance 来源: tick_events 的 max(narrative_value, narrative_value_hint).
# 阈值默认 7 (≈ 显著事件级, EventInjector 给戏剧事件多打 ≥7).
# CRITIC_IMPORTANCE_MIN=0 → critic 总跑 (老 v15 行为); 999 → critic 总跳 (v16).
_CRITIC_IMPORTANCE_MIN_DEFAULT = 7


# iter#O — critic length-gate 加严. 段落超此长度强制 critic, 不再被
# importance gate 跳过. 防 spike 段超长 narrative 漏审 (Phase 6-A run 2
# 实测 max 4123 chars 段落). 0 = 禁用 (回 iter#O 之前行为).
_CRITIC_FORCE_ABOVE_LEN_DEFAULT = 2500


def _critic_force_above_len() -> int:
    """Read CRITIC_FORCE_ABOVE_LEN env (lazy, for tests).

    0 → disabled (永不强制).
    invalid / 负值 → 回 default 2500.
    """
    raw = os.environ.get("CRITIC_FORCE_ABOVE_LEN", "").strip()
    if not raw:
        return _CRITIC_FORCE_ABOVE_LEN_DEFAULT
    try:
        v = int(raw)
        if v < 0:
            return _CRITIC_FORCE_ABOVE_LEN_DEFAULT
        return v
    except ValueError:
        return _CRITIC_FORCE_ABOVE_LEN_DEFAULT


def _should_force_critic_by_length(narrative_chars: int) -> bool:
    """是否因 narrative 超长而强制 critic.

    >: 严格大于 (boundary == threshold 不触发).
    阈值 = 0 时永不触发 (env disable).
    """
    threshold = _critic_force_above_len()
    if threshold <= 0:
        return False
    return narrative_chars > threshold


def _critic_importance_min() -> int:
    raw = os.environ.get("CRITIC_IMPORTANCE_MIN", "").strip()
    if not raw:
        return _CRITIC_IMPORTANCE_MIN_DEFAULT
    try:
        v = int(raw)
        # 接受 0 (critic 总跑); 负值/非法退回 default.
        return v if v >= 0 else _CRITIC_IMPORTANCE_MIN_DEFAULT
    except ValueError:
        return _CRITIC_IMPORTANCE_MIN_DEFAULT


def _tick_importance_score(tick_events) -> int:
    """tick 重要性 = events 中最高 narrative_value (含 hint).

    无事件 → 0 (critic skip, 因为没素材).
    所有事件的两个字段都缺/0 → 0 (critic skip). 这是 by design — narrator
    的 _NARRATE_SKIP_THRESHOLD 已在更上层用 total_score 截短无价值 tick;
    走到这里却都是 0-value 的事件意味着 EventInjector 没在 hint 字段上打分,
    应当当作"低重要性"由 critic 跳过, 不去无中生有调一次贵 LLM.

    用现成 Event 字段, 不引入新 LLM 调用."""
    if not tick_events:
        return 0
    return max(
        max(e.narrative_value or 0, e.narrative_value_hint or 0)
        for e in tick_events
    )


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
            # v2.38 (iter#69) — env_bool_tri 抽出复用 (替代手抄拼写集合).
            # v2.38 (iter#74 review fix) — import 提到模块顶部.
            tri = env_bool_tri("NARRATOR_ENABLE_CRITIC")
            if tri is not None:
                enable_critic = tri
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
        # iter#M — intensity guard 滚动窗口. 跟踪最近 10 tick 的 narrative
        # chars. 当 ≥5 tick > 1500 chars → 下 tick prompt 加 "请短促收尾" directive.
        # 防 Phase 6-A run 1 stuck-state. cap=10 由 deque(maxlen=10) 自动维护.
        import collections as _coll
        self._recent_narrative_chars: _coll.deque[int] = _coll.deque(maxlen=10)

    def set_exempt_words(self, words) -> None:
        """Orchestrator 在装配阶段 / 角色加入时调用, 注入专有名词豁免。"""
        self._exempt_words = set(w for w in words if w)

    # ------------------------------------------------------------------
    # iter#M — Intensity guard (反 sustained-climax)
    # ------------------------------------------------------------------

    def _record_narrative_chars(self, chars: int) -> None:
        """Orchestrator/narrate() 在每次成功产出 narrative 后调用.

        cap=10 由 deque maxlen 维护, 旧记录自动挤出.
        """
        try:
            self._recent_narrative_chars.append(int(chars))
        except (TypeError, ValueError):
            return

    def _intensity_guard_active(self) -> bool:
        """≥ COUNT tick > CHARS chars in last 10 → True.

        Env knobs (lazy read 以支持测试 monkeypatch):
        * NARRATOR_INTENSITY_GUARD_ENABLE (default True)
        * NARRATOR_INTENSITY_GUARD_CHARS (default 1500)
        * NARRATOR_INTENSITY_GUARD_COUNT (default 5)
        """
        if not env_bool("NARRATOR_INTENSITY_GUARD_ENABLE", default=True):
            return False
        try:
            chars_threshold = int(os.environ.get(
                "NARRATOR_INTENSITY_GUARD_CHARS", "1500"
            ))
        except ValueError:
            chars_threshold = 1500
        try:
            count_threshold = int(os.environ.get(
                "NARRATOR_INTENSITY_GUARD_COUNT", "5"
            ))
        except ValueError:
            count_threshold = 5
        over = sum(1 for c in self._recent_narrative_chars if c > chars_threshold)
        return over >= count_threshold

    def _render_intensity_guard_block(self) -> str:
        """Active 时返回插入 user_prompt 的 directive block."""
        if not self._intensity_guard_active():
            return ""
        chars_in_window = list(self._recent_narrative_chars)
        return (
            "# ⚠ 节奏护栏 (intensity guard)\n\n"
            "已连续高密度叙事 (最近 "
            f"{len(chars_in_window)} tick 中 "
            f"{sum(1 for c in chars_in_window if c > 1500)} 段超 1500 字). "
            "此 tick 请: 短促收尾 / 留白 / 跳过细节展开. "
            "目标 ≤ 800 字, 让读者喘口气. "
            "若剧情节点无法回落, narrative_text 可留空 + "
            "consistency_flags 说明.\n"
        )

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
        novel_title: str = "",
        *,
        tick_actions: list[CharacterAction] | None = None,
        char_profiles: dict[str, CharacterProfile] | None = None,
        world_state: WorldState | None = None,
        prose_tail: str = "",
        # Phase 5+: TickState 持久化的 style preset key (空 → fallback 到 env / 默认)
        style_preset_key: str = "",
        style_preset_snapshot: dict | None = None,
        reader_knowledge: dict | None = None,
        continuity_state: dict | None = None,
        continuity_state_audit: dict | None = None,
    ) -> NarratorOutput:
        """主入口。无事件或事件价值过低时返回 should_narrate=False。

        ``novel_title`` (v2.34) — 作品标题, 渲染到 user_prompt 顶部. 默认空字符串
        保持与旧调用方的二进制兼容; Orchestrator 应总是传入非空值。

        v2.37 场景简报参数 (全部可选, 缺省时退化为仅事件描述):
        * ``tick_actions`` — 本 tick 角色行动原始输出。这是台词
          (dialogue_spoken) / 意图 / 内心独白的唯一来源 — Event 转换会把它们
          丢掉, 此前 Narrator 根本看不到角色说了什么, 被迫写无对话的意境段。
        * ``char_profiles`` — id→CharacterProfile, 提供角色名 / 性格 / 说话风格。
          此前 Narrator 只拿到 ``char_xxx`` 这样的 id, 连角色叫什么都不知道。
        * ``world_state`` — 渲染场景地点的名字与现状, 让场景落地。
        * ``prose_tail`` — 上一段实际正文的结尾, 衔接连续性的根基。
        """
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

        # 2. 决定篇幅 — 单 tick 是世界里的一小段时间, 指标过高只会逼出注水。
        # 宁短勿水: 一节的体量由 SectionCloser 跨 tick 累积保证。
        # v2.38 (iter#4) — max_tokens 按目标字数 + JSON overhead 估算 (中文
        # ~0.6 char/token, 加 800 tokens 给 JSON wrapper / 短字段). 此前固定
        # 16384 给了模型超出 target_chars 50%+ 的空间, baseline 实测 1854 vs
        # 目标 1200, 注水 54%. 收紧后模型被迫贴 target.
        if total_score >= _NARRATE_FULL_THRESHOLD:
            estimated_length = "long"
            target_chars = "1200-2200 字"
            max_output_tokens = 5500
        elif total_score >= _NARRATE_SHORT_THRESHOLD:
            estimated_length = "medium"
            target_chars = "600-1200 字"
            max_output_tokens = 3500
        else:
            estimated_length = "short"
            target_chars = "300-700 字"
            max_output_tokens = 2200

        # 3. 调用 LLM 写作
        # Phase 5-A: system_prompt 不再追加 style_anchors, 改由 user_prompt 头部
        # 承载。这样 SYSTEM 跨 tick bit-identical, 命中 DeepSeek/ARK auto prefix
        # cache (~5x 折扣 on input tokens). 语感锚移到 user 头部, 模型读到的
        # 字面信息完全等价。
        system_prompt = self._build_system_prompt()
        continuity_catalogs = _continuity_reference_catalogs(
            tick_events=tick_events,
            char_states=char_states,
            char_profiles=char_profiles or {},
            world_state=world_state,
            open_loops=open_loops,
            previous_state=continuity_state or {},
        )
        user_prompt = self._build_user_prompt(
            tick=tick,
            world_time=world_time,
            tracking_character_id=tracking_character_id,
            tick_events=tick_events,
            char_states=char_states,
            recent_chapter_summaries=recent_chapter_summaries,
            open_loops=open_loops,
            target_chars=target_chars,
            novel_title=novel_title,
            tick_actions=tick_actions or [],
            char_profiles=char_profiles or {},
            world_state=world_state,
            prose_tail=prose_tail,
            style_anchors=style_anchors,
            style_preset_key=style_preset_key,
            style_preset_snapshot=style_preset_snapshot,
            reader_knowledge=reader_knowledge or {},
            continuity_state=continuity_state or {},
            continuity_catalogs=continuity_catalogs,
        )

        try:
            resp = await llm_client.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=_narrator_temperature(),
                max_tokens=max_output_tokens,
                agent_id="narrator",
                priority="critical",
                tick=tick,
            )
        except Exception as e:
            logger.error("NarratorAgent LLM call failed: %s", e)
            return NarratorOutput(
                should_narrate=False,
                skip_reason=f"LLM 不可用: {e}",
                tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
            )

        parsed = self._parse_output(
            resp.content,
            estimated_length,
            tick,
            tick_events,
            continuity_catalogs=continuity_catalogs,
        )
        preset = self._resolve_style_preset(
            style_preset_key, style_preset_snapshot
        )
        if parsed.should_narrate and parsed.narrative_text and preset is not None:
            parsed = await self._enforce_style_contract(
                parsed,
                preset=preset,
                strict=self._is_strict_style_tick(preset, tick, tick_events),
                tick=tick,
            )
        # 4. CRITIQUE → REVISE/REWRITE 循环
        # v2.38 (iter#10) — 短段落跳过 critic, 阈值通过 _critic_min_narrative_len()
        # 每次 lazy 读 env (允许 monkeypatch.setenv 后立即生效).
        # Phase 2 Stage 2 (iter#84) — 加 importance 门控:
        # tick importance < CRITIC_IMPORTANCE_MIN 时跳 critic, 保留关键节拍
        # 的全链路质量 + 平均节拍的 v16 成本. Stage 1 verdict 数据支持.
        # v2.38 (iter#88 review fix) — 拆 critic gating 与日志, 删除重复 elif.
        critic_eligible = (
            parsed.should_narrate
            and self._critic is not None
            and parsed.narrative_text
            and len(parsed.narrative_text) >= _critic_min_narrative_len()
        )
        # iter#R — 当 critic 没跑时记录 skip_reason 让 critic_log 写 SKIP 行.
        if parsed.should_narrate and parsed.narrative_text:
            if self._critic is None:
                parsed.critique_skip_reason = "critic_disabled"
            elif len(parsed.narrative_text) < _critic_min_narrative_len():
                parsed.critique_skip_reason = "length_gate"
        if critic_eligible:
            importance = _tick_importance_score(tick_events)
            gate_importance = _critic_importance_min()
            # iter#O — 长 narrative (>2500 by default) 强制 critic 即使
            # importance 不到 gate. 防 spike 段超长漏审.
            force_by_length = _should_force_critic_by_length(
                len(parsed.narrative_text)
            )
            if importance >= gate_importance or force_by_length:
                if force_by_length and importance < gate_importance:
                    logger.info(
                        "narrator[tick=%d] critic FORCED by length: chars=%d > %d",
                        tick, len(parsed.narrative_text), _critic_force_above_len(),
                    )
                parsed = await self._run_critique(parsed)
            else:
                # 显式日志: 低重要性 tick 跳 critic. 不污染 consistency_flags.
                logger.info(
                    "narrator[tick=%d] critic skipped: importance=%d < gate=%d",
                    tick, importance, gate_importance,
                )
                # iter#R — 标记 critic_log 写 SKIP 行原因.
                parsed.critique_skip_reason = "importance_gate"
        # 正文、风格修订和 critic 都完成后，再做一次叙事状态闭环。
        # 放在最后是为了避免后续 rewrite 让 continuity_state 再次过时。
        if (
            parsed.should_narrate
            and parsed.narrative_text
            and _continuity_guard_enabled()
        ):
            from agents.narrative_state_guard import NarrativeStateGuard

            consumed_ids = set(parsed.events_consumed)
            required_events = [
                {
                    "id": event.id,
                    "description": event.description,
                    "required_end_states": list(event.consequences),
                }
                for event in tick_events
                if event.id in consumed_ids
            ]
            if not required_events:
                required_events = [
                    {
                        "id": event.id,
                        "description": event.description,
                        "required_end_states": list(event.consequences),
                    }
                    for event in tick_events
                    if self._effective_value(event) >= _NARRATE_SKIP_THRESHOLD
                ][:3]
            guard_out = await NarrativeStateGuard().guard(
                narrative_text=parsed.narrative_text,
                previous_state=continuity_legacy_view(
                    continuity_state or {},
                    audit=continuity_state_audit,
                ),
                declared_state=continuity_legacy_view(
                    parsed.continuity_state,
                    audit=parsed.continuity_state_audit,
                ),
                required_events=required_events,
                style_contract=(preset.narrator_addendum if preset else ""),
                protected_terms=[
                    profile.name
                    for profile in (char_profiles or {}).values()
                    if profile.name
                ],
                entity_names={
                    character_id: profile.name
                    for character_id, profile in (char_profiles or {}).items()
                    if profile.name
                },
                tracking_character_id=tracking_character_id,
                tick=tick,
            )
            if guard_out.safe:
                guarded_state = parsed.continuity_state
                guarded_audit = parsed.continuity_state_audit
                guarded_flags = list(parsed.consistency_flags)
                if guard_out.adopted:
                    guarded_state, guarded_audit = (
                        _normalise_generated_continuity(
                            guard_out.continuity_state,
                            catalogs=continuity_catalogs,
                        )
                    )
                    guarded_audit["pre_repair"] = (
                        parsed.continuity_state_audit
                    )
                    guarded_audit["guard_repair_adopted"] = True
                    guarded_flags.append(
                        "continuity_state_guard_repair_legacy"
                    )
                parsed = replace(
                    parsed,
                    narrative_text=guard_out.narrative_text,
                    continuity_state=guarded_state,
                    continuity_state_audit=guarded_audit,
                    consistency_flags=guarded_flags,
                    continuity_guard_trace=guard_out.trace,
                )
            else:
                parsed = replace(
                    parsed,
                    should_narrate=False,
                    narrative_text="",
                    skip_reason="Narrator 正文状态矛盾未通过修复复验",
                    consistency_flags=(
                        list(parsed.consistency_flags)
                        + ["narrative_state_guard_failed"]
                    ),
                    continuity_guard_trace=guard_out.trace,
                )
        # iter#M — 记录本 tick narrative chars 入滚动窗口 (供下 tick 判断
        # 是否激活 intensity guard). should_narrate=False 时不记录, 让 silent
        # 段不污染窗口.
        if parsed.should_narrate and parsed.narrative_text:
            self._record_narrative_chars(len(parsed.narrative_text))
        return parsed

    # ------------------------------------------------------------------

    async def _enforce_style_contract(
        self,
        draft: NarratorOutput,
        *,
        preset,
        strict: bool,
        tick: int,
    ) -> NarratorOutput:
        """跑风格 det gate；high 违约时最多调用一次定向重写。"""
        before = style_contract_report(
            preset.key,
            draft.narrative_text,
            preset.det_rules,
            strict=strict,
        )
        trace = {
            "preset_key": preset.key,
            "preset_version": preset.version,
            "prompt_hash": preset.prompt_hash,
            "strict": strict,
            "before": before.to_dict(),
            "rewrite_attempted": False,
            "rewrite_adopted": False,
        }
        flags = list(draft.consistency_flags)
        if not before.requires_rewrite:
            return replace(draft, style_contract_trace=trace)

        trace["rewrite_attempted"] = True
        finding_text = "\n".join(
            f"- [{f.code}] {f.message}"
            for f in before.findings
            if f.severity == "high"
        )
        prompt = f"""\
请只修复下面小说正文中已经被确定性检查证实的风格违约。保留全部事件、因果、
人物立场、知识边界、伏笔与大致篇幅，不新增事实；不要解释修改过程。

# 风格契约
{preset.narrator_addendum.strip()}

# 本次必须修复
{finding_text}

# 原正文
{draft.narrative_text}

严格输出 JSON：{{"narrative_text":"修订后的完整正文"}}
"""
        try:
            resp = await llm_client.chat(
                system_prompt=(
                    "你是小说风格修订器。只做最小必要修改，严格输出 JSON，"
                    "绝不输出分析或说明。"
                ),
                user_prompt=prompt,
                temperature=0.35,
                max_tokens=min(5500, max(1200, len(draft.narrative_text) * 2)),
                agent_id="narrator_style_rewrite",
                priority="critical",
                tick=tick,
            )
            payload = parse_llm_json(resp.content)
            candidate = str(payload.get("narrative_text", "") or "").strip()
            if not candidate:
                raise ValueError("style rewrite returned empty narrative_text")
            # 防止修订器把正文压成摘要或成倍注水。
            ratio = len(candidate) / max(1, len(draft.narrative_text))
            if not 0.55 <= ratio <= 1.8:
                raise ValueError(f"style rewrite length ratio out of range: {ratio:.2f}")
            after = style_contract_report(
                preset.key, candidate, preset.det_rules, strict=strict
            )
            trace["after"] = after.to_dict()
            # 只有 high 数严格减少才采纳；一次后仍失败也不递归重试。
            before_high = sum(f.severity == "high" for f in before.findings)
            after_high = sum(f.severity == "high" for f in after.findings)
            if after_high < before_high:
                trace["rewrite_adopted"] = True
                if after_high:
                    flags.append("style_contract_surviving_high")
                return replace(
                    draft,
                    narrative_text=candidate,
                    draft_text=draft.draft_text or draft.narrative_text,
                    consistency_flags=flags,
                    style_contract_trace=trace,
                )
            trace["rewrite_error"] = "rewrite did not reduce high findings"
        except Exception as exc:
            logger.warning(
                "NarratorAgent style rewrite failed (non-fatal, tick=%d): %s",
                tick, exc,
            )
            trace["rewrite_error"] = str(exc)[:240]

        flags.append("style_contract_rewrite_failed")
        return replace(
            draft,
            consistency_flags=flags,
            style_contract_trace=trace,
        )

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
            resolved_open_loops=draft.resolved_open_loops,
            newly_opened_loops=draft.newly_opened_loops,
            continuity_state=draft.continuity_state,
            continuity_state_audit=draft.continuity_state_audit,
            continuity_guard_trace=draft.continuity_guard_trace,
            style_diagnostics=draft.style_diagnostics,
            consistency_flags=new_flags,
            tick_summary_for_record=draft.tick_summary_for_record,
            skip_reason=draft.skip_reason,
            critique_trace=out.to_dict(),
            critique_action=out.final_action,
            draft_text=original,
            new_opening_signature=out.new_opening_signature,
            blacklist_to_add=out.blacklist_to_add,
            style_contract_trace=draft.style_contract_trace,
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

    def _build_system_prompt(self) -> str:
        """Phase 5-A: 纯静态 SYSTEM, 跨 tick bit-identical, 命中 prefix cache.

        style_anchors 已迁到 user_prompt 头部 (见 ``_render_style_anchor_block``)。
        """
        return NARRATOR_SYSTEM_PROMPT

    @staticmethod
    def _render_style_anchor_block(style_anchors: list[StyleAnchor]) -> str:
        """Phase 5-A: 把 style_anchors 渲染成 user_prompt 头部块。

        与原 SYSTEM 末尾追加的字面信息完全等价 — 只改位置, 不改语义。空 list
        时返回空字符串, caller 自行决定要不要拼。
        """
        if not style_anchors:
            return ""
        anchor_text = "\n\n".join(
            f"【语感示例 - {a.scene_type}】\n{a.excerpt}"
            for a in style_anchors[:3]
        )
        return (
            "# 语感参考(只看句长 / 词汇密度 / 修辞密度。示例的题材、"
            "场景、人物与本作无关, 不要模仿其内容; 本段写什么由素材简报"
            "决定 — 动作场就写动作, 对峙场就写对峙, 不要一律写成静景)\n\n"
            f"{anchor_text}\n\n"
        )

    @staticmethod
    def _resolve_style_preset(
        key: str | None = None, snapshot: dict | None = None
    ):
        """优先恢复 novel 冻结快照；没有快照的旧存档才查当前注册表。"""
        if not _STYLE_PRESETS_AVAILABLE:
            return None
        resolved = (key or "").strip() or (
            os.environ.get("NOVEL_STYLE_PRESET") or ""
        ).strip()
        if not resolved:
            return None
        try:
            if snapshot:
                preset = StylePreset.from_snapshot(snapshot)
                if preset.key != resolved:
                    logger.warning(
                        "style snapshot key=%r mismatches selected key=%r; using registry",
                        preset.key, resolved,
                    )
                else:
                    return preset
            return get_style_preset(resolved)
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "style preset key=%r invalid — ignoring (valid: %s)",
                resolved, ",".join(list_style_keys()),
            )
            return None

    @classmethod
    def _render_style_preset_block(
        cls, key: str | None = None, snapshot: dict | None = None
    ) -> str:
        """Phase 5+: 渲染风格 preset block.

        解析顺序:
        1. ``key`` 显式参数 (从 TickState.style_preset_key 传入) — Phase 5+ 持久化路径
        2. ``NOVEL_STYLE_PRESET`` env — Phase 5-A 早期 matrix bench 用过的临时旋钮

        未设 / 空 / 未知 key 都安静返回空串 — 老 bench / 未升级用户完全等价.
        位置在 user_prompt 头部, 在 style_anchors 块之前.
        """
        preset = cls._resolve_style_preset(key, snapshot)
        return preset.narrator_addendum if preset is not None else ""

    @staticmethod
    def _is_strict_style_tick(preset, tick: int, tick_events: list[Event]) -> bool:
        """确定性 cadence：首段、每 N tick、或高重要性场景执行强格式。"""
        every = max(1, int(getattr(preset, "strict_every_ticks", 1) or 1))
        importance = _tick_importance_score(tick_events)
        return (
            every == 1
            or tick <= 1
            or tick % every == 0
            or importance >= int(getattr(preset, "strict_importance", 7) or 7)
        )

    @staticmethod
    def _infer_scene_mode(
        tick_events: list[Event], tick_actions: list[CharacterAction]
    ) -> str:
        """Cheap semantic scene mode used to vary prose rhythm by situation."""
        material = " ".join(e.description for e in tick_events)
        if any(a.dialogue_spoken for a in tick_actions):
            dialogue_weight = sum(bool(a.dialogue_spoken) for a in tick_actions)
        else:
            dialogue_weight = 0
        keyword_modes: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("revelation", ("揭露", "真相", "秘密", "认出", "证据显出", "证明了")),
            ("investigation", ("调查", "搜查", "追踪", "检查", "线索", "推断", "暗号")),
            ("recovery", ("疗伤", "休息", "包扎", "发烧", "疲惫", "安顿", "照料")),
            ("travel", ("赶往", "抵达", "离开", "穿过", "上路", "撤离", "绕行")),
            ("relationship", ("道歉", "告别", "和解", "误会", "信任", "承诺", "拒绝")),
            ("action", ("追", "逃", "冲", "夺", "攻击", "爆炸", "封死", "战斗", "开火")),
        )
        for mode, keywords in keyword_modes:
            if any(keyword in material for keyword in keywords):
                return mode
        if dialogue_weight >= 2:
            return "dialogue"
        if dialogue_weight == 1:
            return "dialogue_action"
        return "transition"

    @staticmethod
    def _render_scene_mode_block(mode: str) -> str:
        directives = {
            "action": "只写新的动作与后果；缩短判断，避免再次布置已经成立的危机。",
            "dialogue": "让立场差异推动场面；对白之间必须有动作反应，避免轮流说明信息。",
            "dialogue_action": "对白必须改变下一步行动，不把人物已经知道的事再讲一遍。",
            "investigation": "每个观察都导向一个可验证推断；不要提前宣布尚无证据的真相。",
            "revelation": "先落证据与人物反应，再给结论；本段只揭示素材支持的那一层。",
            "recovery": "降低强度，写伤势、照料或关系变化；不要凭空追加新袭击。",
            "travel": "用位置变化和途中选择推进，不重复出发原因，不写流水账。",
            "relationship": "用选择、沉默和具体动作改变关系，不用总结句替人物下结论。",
            "transition": "短写状态变化与新落点，为下一场留出空间，不强造高潮。",
        }
        return (
            "# 场景模式\n\n"
            f"{mode} — {directives.get(mode, directives['transition'])}\n\n"
        )

    # -- 场景简报渲染 ---------------------------------------------------

    @staticmethod
    def _display_name(
        cid: str, char_profiles: dict[str, CharacterProfile]
    ) -> str:
        p = char_profiles.get(cid)
        return p.name if p is not None and p.name else cid

    def _render_scene_block(
        self,
        *,
        tick_events: list[Event],
        char_states: list[CharacterState],
        char_profiles: dict[str, CharacterProfile],
        world_state: WorldState | None,
        tracking_character_id: str,
    ) -> str:
        """渲染 [场景] 块: 涉事地点 + 在场角色名片。

        角色名片是 Narrator 能写出"有声纹的对话"的根基 — 名字 / 性格 / 说话
        风格全部来自 CharacterProfile (此前从未传给 Narrator)。
        """
        # 本 tick 涉及的角色: 事件参与者 ∪ 行动者, 主跟踪角色置顶
        involved: list[str] = []

        def _add(cid: str) -> None:
            if cid and cid in {s.character_id for s in char_states} and cid not in involved:
                involved.append(cid)

        _add(tracking_character_id)
        for e in tick_events:
            for cid in e.participants:
                _add(cid)
        involved = involved[:_MAX_BRIEF_CHARS_COUNT]
        involved_set = set(involved)

        # 涉事地点
        states_by_id = {s.character_id: s for s in char_states}
        loc_ids: list[str] = []
        for cid in involved:
            st = states_by_id.get(cid)
            if st and st.current_location and st.current_location not in loc_ids:
                loc_ids.append(st.current_location)
        for e in tick_events:
            if e.location and e.location not in loc_ids:
                loc_ids.append(e.location)

        lines: list[str] = []
        if world_state is not None:
            env_bits = [b for b in (world_state.era, world_state.current_season, world_state.weather) if b]
            if env_bits:
                lines.append("环境: " + " / ".join(env_bits))
            locs_by_id = {loc.id: loc for loc in world_state.locations}
            for lid in loc_ids[:4]:
                loc = locs_by_id.get(lid)
                if loc is not None:
                    desc = loc.current_state or "(无描述)"
                    lines.append(f"地点【{loc.name}】: {desc[:80]}")

        if involved:
            lines.append("在场人物:")
            for cid in involved:
                p = char_profiles.get(cid)
                st = states_by_id.get(cid)
                name = self._display_name(cid, char_profiles)
                tag = " (视点)" if cid == tracking_character_id else ""
                bits: list[str] = []
                if p is not None:
                    if p.personality:
                        bits.append(p.personality[:40])
                    if p.speech_style:
                        bits.append(f"说话: {p.speech_style[:40]}")
                if st is not None:
                    if st.speech_fingerprint_features:
                        bits.append(
                            "声纹: " + "、".join(st.speech_fingerprint_features[:4])
                        )
                    if st.emotional_state and st.emotional_state != "neutral":
                        bits.append(f"情绪: {st.emotional_state[:24]}")
                    rel_bits = []
                    for other_id, rel in list(st.relationships.items())[:4]:
                        if other_id in involved_set and other_id != cid:
                            rel_bits.append(
                                f"{self._display_name(other_id, char_profiles)}({rel.type},信任{rel.trust:+d})"
                            )
                    if rel_bits:
                        bits.append("关系: " + ", ".join(rel_bits))
                detail = " — " + "; ".join(bits) if bits else ""
                lines.append(f"- {name} [{cid}]{tag}{detail}")

        return "\n".join(lines) if lines else "(场景信息缺失 — 以素材为准)"

    def _render_material_block(
        self,
        *,
        tick_events: list[Event],
        tick_actions: list[CharacterAction],
        char_profiles: dict[str, CharacterProfile],
    ) -> str:
        """渲染 [本段素材] 块: 按序号列出事件, 角色行动附台词原文 / △私密线。

        这是修复"Narrator 写不出对话"的关键: dialogue_spoken / intent /
        internal_monologue 在 action→Event 转换时被丢弃, 必须从原始
        CharacterAction 取回并随事件一起渲染。
        """
        # v2.38 (iter#19) — material block 紧凑:
        # * event description 截 120 字 (此前不截, 单事件可达 300+ chars)
        # * internal/intent 从 80 截到 60 字 (足够传达动机, 不冗长)
        # * 保留 [e.id] — Narrator 输出 events_consumed 字段必须引用真实 id
        actions_by_char = {a.character_id: a for a in tick_actions}
        consumed_action_chars: set[str] = set()
        lines: list[str] = []
        idx = 0
        kind_map = {"exogenous": "环境", "endogenous": "因果", "dramatic": "变故"}
        for e in tick_events[:_MAX_BRIEF_EVENTS]:
            idx += 1
            desc = e.description[:120] if len(e.description) > 120 else e.description
            if e.type == "character_action" and e.participants:
                actor_id = e.participants[0]
                actor = self._display_name(actor_id, char_profiles)
                lines.append(f"{idx}. [{e.id}] {actor}: {desc}")
                act = actions_by_char.get(actor_id)
                if act is not None and actor_id not in consumed_action_chars:
                    consumed_action_chars.add(actor_id)
                    if act.dialogue_spoken:
                        to_whom = "、".join(
                            self._display_name(t, char_profiles)
                            for t in act.dialogue_to_whom[:3]
                        )
                        suffix = f"(对{to_whom})" if to_whom else ""
                        lines.append(f"   台词{suffix}: 「{act.dialogue_spoken}」")
                    if act.internal_monologue:
                        lines.append(f"   △内心: {act.internal_monologue[:60]}")
                    if act.intent:
                        lines.append(f"   △意图: {act.intent[:60]}")
            else:
                kind = kind_map.get(e.type, e.type)
                lines.append(f"{idx}. [{e.id}] ({kind}) {desc}")
        if not lines:
            return "(本段无素材)"
        return "\n".join(lines)

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
        novel_title: str = "",
        tick_actions: list[CharacterAction] | None = None,
        char_profiles: dict[str, CharacterProfile] | None = None,
        world_state: WorldState | None = None,
        prose_tail: str = "",
        style_anchors: list[StyleAnchor] | None = None,
        # Phase 5+: 显式 style preset key (TickState 透传过来),
        # _render_style_preset_block 会优先用它, fallback 到 env.
        style_preset_key: str = "",
        style_preset_snapshot: dict | None = None,
        reader_knowledge: dict | None = None,
        continuity_state: dict | None = None,
        continuity_catalogs: dict[str, set[str]] | None = None,
    ) -> str:
        tick_actions = tick_actions or []
        char_profiles = char_profiles or {}
        style_anchors = style_anchors or []
        reader_knowledge = reader_knowledge or {}
        continuity_state = continuity_state or {}
        continuity_catalogs = continuity_catalogs or {}
        # Phase 5+: 顺序 = preset addendum (本作怎么写) → style_anchors (语感示例)
        # 两个都拼在 # 连载进度 之前. preset 另在最终写作指令前复核一次, 防止
        # 长素材 prompt 稀释头部风格契约; 未绑定 preset 时仍 bit-identical.
        preset = self._resolve_style_preset(
            style_preset_key, style_preset_snapshot
        )
        preset_block = preset.narrator_addendum if preset is not None else ""
        anchor_block = self._render_style_anchor_block(style_anchors)
        style_block = preset_block + anchor_block
        style_recheck_block = ""
        if preset is not None:
            strict_style = self._is_strict_style_tick(preset, tick, tick_events)
            cadence_note = (
                "本 tick 是严格风格节拍，短清单全部为硬验收项。"
                if strict_style
                else "本 tick 是过渡节拍：保留辨识度，但不要机械凑齐强格式。"
            )
            style_recheck_block = (
                "# 最终风格验收 (高优先级, 输出 JSON 前逐条执行)\n\n"
                "素材决定发生什么, 本作风格契约决定怎么讲; 不得改动既定事实, "
                "也不得让素材的默认语调吞掉风格。"
                f"{cadence_note}\n- {preset.final_checklist}\n"
                f"- 冲突策略: {preset.conflict_policy}\n\n"
            )

        scene_block = self._render_scene_block(
            tick_events=tick_events,
            char_states=char_states,
            char_profiles=char_profiles,
            world_state=world_state,
            tracking_character_id=tracking_character_id,
        )
        material_block = self._render_material_block(
            tick_events=tick_events,
            tick_actions=tick_actions,
            char_profiles=char_profiles,
        )
        scene_mode = self._infer_scene_mode(tick_events, tick_actions)
        scene_mode_block = self._render_scene_mode_block(scene_mode)

        # v2.38 (iter#7) — loops 8→5, summaries 8→5. 焦点放在最紧迫/最近的;
        # 旧 8 条对应单段 tick 是噪声, 模型会试图全部呼应导致内容散乱.
        loops_text = "(无开放伏笔)"
        if open_loops:
            # 按 urgency 降序排, 取前 5 紧迫. OpenLoop.urgency 是非 nullable
            # int (默认 5), 不需要 getattr 防御性默认.
            top_loops = sorted(open_loops, key=lambda loop: -loop.urgency)[:5]
            loops_text = "\n".join(
                f"- [{loop.id}] ({loop.type}, 紧迫{loop.urgency}) "
                f"{loop.description[:80]}"
                + (
                    f" | 承诺问题: {loop.promised_question[:60]}"
                    if loop.promised_question else ""
                )
                + (
                    f" | 已引用{loop.reference_count}次"
                    if loop.reference_count else ""
                )
                for loop in top_loops
            )

        # iter#114 试 [-5:] → [-3:], iter#115 bench 反向: tokens +4.9%,
        # avg_urg -12.7%, overlap consec char-3 +88% / char-4 +226% — LLM
        # 失去关键 long-range 上下文导致 narrator 自我重复 + 张力下降. 退回
        # [-5:]. 此处保留教训: prose_tail (~1600 chars) 与 summaries 并非
        # 简单 redundant, summaries 提供 "前情" 抽象层 (主线张力 anchor),
        # prose_tail 提供 immediate 续写锚 (语气 anchor). 两者作用不同.
        summaries_text = "(连载刚开始, 尚无前情)"
        if recent_chapter_summaries:
            summaries_text = "\n".join(
                f"- {s}" for s in recent_chapter_summaries[-5:]
            )

        title_line = ""
        if novel_title and novel_title not in ("未命名小说", "(未命名)"):
            title_line = f"《{novel_title}》 — "

        tail_block = (
            f"# 前文结尾 (你写的上一段就停在这里, 新内容必须能直接接着读)\n\n"
            f"……{prose_tail[-_PROSE_TAIL_MAX_CHARS:]}\n"
            if prose_tail.strip()
            else "# 前文结尾\n\n(这是本书的第一段正文 — 用一个具体的场景开场, 不要写楔子式的世界观介绍)\n"
        )
        continuity_block = (
            "# 跨段连续性硬约束\n\n"
            "前文结尾是当前状态，优先级高于素材中重复出现的危机背景。只写从该状态"
            "到本 tick 新结果的增量：已经完成的夺取、交易、开门、倒计时、受伤、"
            "抵达和发现不得换一种说法重演。若素材仍复述旧起点，把它理解为尚存压力，"
            "不要让人物和物品回到先前位置。第一句从前文最后一个动作之后开始。\n\n"
            if prose_tail.strip()
            else ""
        )
        reader_known = list(reader_knowledge.get("known_facts", []) or [])[-12:]
        reader_questions = list(reader_knowledge.get("open_questions", []) or [])[:8]
        reader_answers = list(reader_knowledge.get("recent_answers", []) or [])[-5:]
        reader_block = (
            "# 读者信息边界\n\n"
            f"已明确展示的事实（可自然引用，不得再次当作新揭示）："
            f"{json.dumps(reader_known, ensure_ascii=False)}\n"
            f"仍等待回答的问题（本段可推进，不可无证据宣布解决）："
            f"{json.dumps(reader_questions, ensure_ascii=False)}\n"
            f"最近已经兑现的问题（不得重新悬置）："
            f"{json.dumps(reader_answers, ensure_ascii=False)}\n\n"
            if reader_known or reader_questions or reader_answers
            else ""
        )
        narrative_state_block = (
            "# 上一段结束时的叙事状态账本（当前事实）\n\n"
            f"{json.dumps(continuity_state, ensure_ascii=False)}\n\n"
            "账本中仍有效的伤势、地点、物品持有者/数量/状况必须延续。"
            "只有本段正文明写改变动作才能更新；输出时再给出完整的"
            " continuity_state。\n\n"
            if continuity_state
            else ""
        )
        typed_ledger_block = (
            "# Typed continuity_state v1（结构约束，不是文学要求）\n\n"
            f"允许的 character_id：{sorted(continuity_catalogs.get('valid_character_ids', set()))}\n"
            f"允许的 location_id：{sorted(continuity_catalogs.get('valid_location_ids', set()))}\n"
            f"允许的 item_id：{sorted(continuity_catalogs.get('valid_item_ids', set()))}\n"
            f"允许的 fact_id：{sorted(continuity_catalogs.get('valid_fact_ids', set()))}\n"
            f"允许的 open_loop_id：{sorted(continuity_catalogs.get('valid_open_loop_ids', set()))}\n"
            f"允许的 source_event_id：{sorted(continuity_catalogs.get('valid_event_ids', set()))}\n"
            "movement_status 只能是 stationary/departing/in_transit/arrived/unknown；"
            "location_id 只放 ID，扶持/背负另填 supporting_character_ids / "
            "carried_by_character_id。无法可靠表达的旧自然语言值"
            "不要猜测，改用 null/unknown/空列表。\n\n"
        )
        committed_events = [
            event for event in tick_events
            if self._effective_value(event) >= _NARRATE_SKIP_THRESHOLD
        ][:5]
        event_commitment_block = (
            "# 本段必须兑现的高价值源事件（不是可选灵感）\n\n"
            + "\n".join(
                f"- [{event.id}] {event.description}"
                + (
                    "\n  必须达到的结束状态：" + "；".join(event.consequences)
                    if event.consequences
                    else ""
                )
                for event in committed_events
            )
            + "\n正文必须到达上述结果；若源事件声明‘已经’，用最小过渡承认该"
            "前态，不得退回重演。只有真正写入的事件才能列入 "
            "events_consumed。源事件只写‘守门人、掠夺者、路人’等称谓时，"
            "必须沿用称谓，不得擅自取名、加绰号或写成主角早就认识的人。\n\n"
            if committed_events
            else ""
        )

        viewpoint_name = self._display_name(tracking_character_id, char_profiles)

        # iter#M — intensity guard block (active 时插在 # 写作指令 之前,
        # 让 LLM 看到节奏护栏后再读最终指令). inactive 时为空字符串.
        intensity_block = self._render_intensity_guard_block()

        return f"""\
{style_block}# 连载进度

{title_line}世界时间 {world_time} (第 {tick} 段素材)

{tail_block}
{continuity_block}{narrative_state_block}{typed_ledger_block}{reader_block}{scene_mode_block}
# 场景

{scene_block}

# 本段素材 (按时间序。△ 标记 = 角色私密信息, 只用于理解动机, 不可写成旁白明示)

{material_block}

# 可呼应的伏笔 (优先呼应, 谨慎新增)

{loops_text}

# 此前剧情备忘 (高度压缩, 仅供保持连贯, 勿照抄)

{summaries_text}

{intensity_block}{style_recheck_block}{event_commitment_block}# 写作指令
视点角色 {viewpoint_name} | 目标篇幅 {target_chars} (宁短勿水) | 从前文结尾自然接续 | 严格 JSON 输出 | 不值得讲时 narrative_text 留空 + consistency_flags 说明.
"""

    def _parse_output(
        self,
        raw: str,
        estimated_length: str,
        tick: int,
        tick_events: list[Event],
        *,
        continuity_catalogs: dict[str, set[str]] | None = None,
    ) -> NarratorOutput:
        try:
            payload = parse_llm_json(raw)
        except json.JSONDecodeError as e:
            logger.error("NarratorAgent JSON parse failed: %s — raw[:300]=%r", e, raw[:300])
            # v2.38 (iter#4) — 兜底前先扫 reasoning 泄漏. 此前 JSON 解析失败时
            # 整段 raw 被当 narrative_text 写盘, 导致 "Let me analyze..." 之类
            # chain-of-thought 直接出现在小说正文里. 现在扫到 marker 退化为不
            # 叙述, 保留 tick_summary 让 MemoryCompressor 仍能记账。
            cleaned = strip_code_fence(raw)
            cleaned, leaked = _strip_reasoning_leak(cleaned)
            if leaked and (not cleaned or len(cleaned.strip()) < 80):
                logger.warning(
                    "NarratorAgent[tick=%d] JSON parse failed AND raw was reasoning "
                    "leak, skipping narration",
                    tick,
                )
                return NarratorOutput(
                    should_narrate=False,
                    skip_reason="Narrator 输出非 JSON 且全为 reasoning 泄漏",
                    tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
                    consistency_flags=["narrator_output_not_json", "reasoning_leak"],
                )
            return NarratorOutput(
                should_narrate=True,
                narrative_text=cleaned,
                estimated_length=estimated_length,
                tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
                consistency_flags=["narrator_output_not_json"]
                + (["reasoning_leak"] if leaked else []),
            )

        narrative_text = str(payload.get("narrative_text", "")).strip()
        if not narrative_text:
            return NarratorOutput(
                should_narrate=False,
                skip_reason="Narrator 主动留空叙述(品味决定跳过)",
                tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
                consistency_flags=list(payload.get("consistency_flags", []) or []),
            )

        # v2.34 — 反 reasoning 泄漏: 砍掉 narrative_text 里的 chain-of-thought
        # (MiMo / DeepSeek-Reasoner 偶发把"首先,理解任务..." 接在正文末尾)。
        # v2.38 (iter#4) — 占位符检测: 模型偶发直接 copy system prompt 里
        # 的 JSON schema 示例值 ("...实际的中文小说正文..." 等). 已知占位符片段
        # 出现即泄漏; 大量 ASCII 三连点 / 中文双省略号也视作 schema 痕迹.
        # v2.38 (iter#5 review fix) — 中文文学常用 "……" (双省略号), 把 "…" 单
        # glyph 当连续点会把悬念句 "她停下……他也停下……灯灭了……" 误杀.
        # 改为按"……" / "..." 整组算 1 次, 阈值放到 6 (一段里 ≥6 组省略号才
        # 真有可能是 schema dump). 同时分别检查 ASCII "..." 三连点 >= 4 组
        # (中文正文几乎不用 ASCII 三连点, 4 组及以上是强信号).
        ascii_groups = narrative_text.count("...")
        cjk_groups = narrative_text.count("……")
        is_placeholder = (
            ascii_groups >= 4
            or narrative_text.strip().startswith("...")
            or "实际的中文小说正文" in narrative_text
            or "char_id_1" in narrative_text
            or "loop_id_1" in narrative_text
        )
        if is_placeholder:
            logger.warning(
                "NarratorAgent[tick=%d] schema placeholder leak detected, "
                "skipping narration",
                tick,
            )
            return NarratorOutput(
                should_narrate=False,
                skip_reason="Narrator 输出 copy 了 JSON schema 占位符",
                tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
                consistency_flags=list(payload.get("consistency_flags", []) or [])
                + ["schema_placeholder_leak"],
            )

        narrative_text, leaked = _strip_reasoning_leak(narrative_text)
        extra_flags = ["reasoning_leak"] if leaked else []
        # 中文对话里的停顿可能自然超过 6 组，不能因此丢弃整段。保留诊断给
        # critic/bench；真正 schema leak 仍由字段名和 ASCII 占位符拦截。
        if cjk_groups >= 6:
            extra_flags.append("excessive_cjk_ellipsis")
        if leaked:
            logger.warning(
                "NarratorAgent[tick=%d] reasoning leak detected, stripped %d chars",
                tick,
                len(payload.get("narrative_text", "")) - len(narrative_text),
            )
        # leak 后正文几乎为空 — 退化为不叙述. 阈值只在 leaked=True 时强制, 平时
        # 不应破坏正常短输出 (mock 测试也常用 < 80 字短文本)。
        if leaked and (not narrative_text or len(narrative_text) < 40):
            return NarratorOutput(
                should_narrate=False,
                skip_reason="Narrator 输出仅含 reasoning 泄漏, 砍后正文为空",
                tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
                consistency_flags=list(payload.get("consistency_flags", []) or [])
                + extra_flags,
            )
        if not narrative_text:
            return NarratorOutput(
                should_narrate=False,
                skip_reason="Narrator 主动留空叙述(品味决定跳过)",
                tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
                consistency_flags=list(payload.get("consistency_flags", []) or []),
            )

        # newly_opened_loops 解析(逐条 validate)
        # v2.38 (iter#38) — LLM 偶发把 loop 写成纯字符串 (description-only) 而非
        # dict, 此前直接抛 "'str' object has no attribute 'setdefault'" 到 except
        # 噪声日志. 加 isinstance 兼容: 收到 str 时包成 dict, 缺字段走兜底.
        new_loops: list[OpenLoop] = []
        for idx, loop_raw in enumerate(payload.get("newly_opened_loops", []) or []):
            if isinstance(loop_raw, str):
                # 简单 fallback: 当作 description, 其他字段缺省
                loop_raw = {"description": loop_raw[:200]}
            elif not isinstance(loop_raw, dict):
                logger.warning(
                    "Skip invalid newly_opened_loop (not dict/str): %r", loop_raw
                )
                continue
            try:
                # 用户产出可能省略 id/opened_tick - 补齐
                if not loop_raw.get("id") and loop_raw.get("loop_id"):
                    loop_raw["id"] = loop_raw.get("loop_id")
                if not loop_raw.get("type") and loop_raw.get("loop_type"):
                    loop_raw["type"] = loop_raw.get("loop_type")
                if not loop_raw.get("description"):
                    loop_raw["description"] = (
                        loop_raw.get("promised_question")
                        or "；".join(loop_raw.get("payoff_requirements", []) or [])
                        or "待兑现的开放问题"
                    )
                loop_raw.setdefault("id", f"loop_t{tick}_{idx}")
                loop_raw.setdefault("opened_tick", tick)
                new_loops.append(OpenLoop.model_validate(loop_raw))
            except Exception as e:
                logger.warning("Skip invalid newly_opened_loop (%s): %s", e, loop_raw)

        resolved_loops: list[dict] = []
        for raw_item in payload.get("resolved_open_loops", []) or []:
            if not isinstance(raw_item, dict):
                continue
            loop_id = str(raw_item.get("loop_id", "") or "").strip()
            payoff = str(raw_item.get("payoff_summary", "") or "").strip()
            evidence = [
                str(item).strip()
                for item in (raw_item.get("evidence_event_ids", []) or [])
                if str(item).strip()
            ]
            if loop_id and payoff and evidence:
                resolved_loops.append(
                    {
                        "loop_id": loop_id,
                        "payoff_summary": payoff[:300],
                        "evidence_event_ids": evidence[:10],
                    }
                )

        raw_continuity_state = payload.get("continuity_state", {})
        continuity_state, continuity_audit = _normalise_generated_continuity(
            raw_continuity_state,
            catalogs=continuity_catalogs,
        )
        if not continuity_state:
            extra_flags.append("continuity_state_missing")
        source_schema = continuity_audit.get("source_schema")
        if raw_continuity_state and source_schema == "legacy":
            extra_flags.append("continuity_state_legacy_fallback")
        elif source_schema == "invalid":
            extra_flags.append("continuity_state_typed_invalid")
        elif continuity_audit.get("issues"):
            extra_flags.append("continuity_state_reference_invalid")

        return NarratorOutput(
            should_narrate=True,
            narrative_text=narrative_text,
            estimated_length=str(payload.get("estimated_length", estimated_length)),
            viewpoint_characters=list(payload.get("viewpoint_characters", []) or []),
            scene_focus=str(payload.get("scene_focus", "")),
            events_consumed=list(payload.get("events_consumed", []) or []),
            open_loops_referenced=list(payload.get("open_loops_referenced", []) or []),
            resolved_open_loops=resolved_loops,
            newly_opened_loops=new_loops,
            continuity_state=continuity_state,
            continuity_state_audit=continuity_audit,
            style_diagnostics=dict(payload.get("style_diagnostics", {}) or {}),
            consistency_flags=list(payload.get("consistency_flags", []) or [])
            + extra_flags,
            tick_summary_for_record=self._compose_tick_summary(tick, tick_events),
        )
