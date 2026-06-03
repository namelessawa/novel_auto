"""
跨模块共享的领域模型。

本文件同时承载两套契约,刻意保留分层:

1. **遗留 dataclass 契约**(``Entity`` / ``Relation`` / ``Section`` / ``ActionPlan``
   / ``ValidationResult`` / ``GraphSnapshot`` 等) - 供 ``backend/graph/knowledge_graph.py``
   与节级管线(outline → retrieval → validation → writer → update)使用。
   frozen dataclass、零依赖,接口稳定不动。

2. **tick 架构 Pydantic v2 契约**(``WorldState`` / ``CharacterProfile`` /
   ``CharacterState`` / ``Event`` / ``OpenLoop`` / ``MemoryEntry`` /
   ``StyleAnchor`` 等) - 对应 ``infinite-novel-multiagent-prompts.md`` 第 2 节
   定义的 TypeScript interface,供新的 9 agent(Orchestrator / WorldSimulator /
   CharacterAgent / Narrator / EventInjector / Showrunner / MemoryCompressor /
   ConsistencyGuardian / NoveltyCritic) 跨边界传值。Pydantic 提供
   ``model_dump_json()`` / ``model_validate_json()`` 与 FastAPI 原生集成,
   SQLite 序列化与 SSE 推送都靠它。

两套契约通过 ``__all__`` 同时导出,迁移期不强制谁淘汰谁。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# 遗留 dataclass 契约 (knowledge_graph / 节级管线)
# ---------------------------------------------------------------------------


class EntityType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"
    SKILL = "skill"
    FACTION = "faction"


class RelationType(str, Enum):
    LOCATED_AT = "located_at"
    HOLDS = "holds"
    KNOWS = "knows"
    HOSTILE = "hostile"
    ALLIED = "allied"
    LOVES = "loves"
    PARENT_OF = "parent_of"
    MEMBER_OF = "member_of"
    MASTER_OF = "master_of"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Entity:
    id: str
    name: str
    entity_type: EntityType
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Relation:
    source_id: str
    target_id: str
    relation_type: RelationType
    label: str = ""
    weight: float = 1.0
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphSnapshot:
    snapshot_id: str
    chapter: int
    timestamp: str
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)


@dataclass(frozen=True)
class Section:
    chapter: int
    section: int
    title: str
    content: str
    summary: str = ""
    word_count: int = 0


@dataclass(frozen=True)
class ActionPlan:
    chapter: int
    section: int
    plan_text: str
    key_entities: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    conflicts: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# tick 架构 Pydantic v2 契约 (新 9 agent)
# ---------------------------------------------------------------------------

# 所有新模型用同一份配置:允许从 dict 反向构造、未知字段忽略、
# 字段额外校验在 model_validator 中处理而非默认抛错。
_TickModelConfig = ConfigDict(
    populate_by_name=True,
    extra="ignore",
    str_strip_whitespace=True,
)


def _coerce_llm_payload(cls, values):
    """Tolerate quirks of LLM-generated JSON before strict pydantic validation.

    LLMs commonly emit ``None`` for optional string fields (instead of ``""``)
    stringly-typed numbers for ``age``/``priority``, and a single scalar where a
    list is required (e.g. ``"all_in_location"`` instead of
    ``["all_in_location"]``). Without this, the whole model is rejected and the
    character/state/event is silently dropped during bootstrap or injection.
    We coerce just enough to keep valid payloads usable, while leaving genuinely
    malformed values to fail downstream validation.
    """
    if not isinstance(values, dict):
        return values
    for fname, finfo in cls.model_fields.items():
        if fname not in values:
            continue
        val = values[fname]
        ann = finfo.annotation
        ann_str = str(ann)
        is_list = ann is list or getattr(ann, "__origin__", None) is list
        is_dict = ann is dict or getattr(ann, "__origin__", None) is dict

        if val is None:
            # Skip fields where None is explicitly allowed (Optional / X | None)
            if "None" in ann_str or "Optional" in ann_str:
                continue
            if ann is str:
                values[fname] = ""
            elif ann is int:
                values[fname] = 0
            elif ann is float:
                values[fname] = 0.0
            elif is_list:
                values[fname] = []
            elif is_dict:
                values[fname] = {}
            continue

        # Wrap a scalar in a list when a list is expected
        # (LLMs sometimes return a single string instead of an array)
        if is_list and not isinstance(val, (list, tuple)):
            if isinstance(val, str) and val.strip():
                values[fname] = [val]
            elif val == "":
                values[fname] = []
    return values


class _TickBase(BaseModel):
    """Common base for tick-architecture Pydantic models.

    Provides shared config and the LLM payload normalisation hook so that None
    values for required-string fields don't drop entire records during bootstrap
    or agent output parsing.
    """

    model_config = _TickModelConfig

    @model_validator(mode="before")
    @classmethod
    def _normalise_llm_payload(cls, values):
        return _coerce_llm_payload(cls, values)


ImportanceTier = Literal["A", "B", "C"]
EventKind = Literal["endogenous", "exogenous", "dramatic", "character_action"]
MemoryTier = Literal["L0", "L1", "L2", "L3"]
ConflictPriority = Literal["A", "B", "C", "D"]
ConflictType = Literal["character", "time", "setting", "relationship", "item"]
OpenLoopType = Literal["mystery", "conflict", "promise", "threat", "other"]
# v2.5 人物弧光阶段 — 编剧界 7 阶段经典模型
ArcStage = Literal["起点", "觉醒", "抗拒", "挫折", "转变", "抉择", "结局"]


class TickLocation(_TickBase):
    """世界中的一个地点。与遗留 ``Entity(entity_type=LOCATION)`` 不冲突。"""


    id: str
    name: str
    type: str = Field(default="region", description="city|village|wilderness|...")
    current_state: str = Field(default="", description="自然语言描述")
    present_characters: list[str] = Field(default_factory=list, description="character_ids")
    notable_features: list[str] = Field(default_factory=list)


class Faction(_TickBase):
    """势力。WorldState 引用,可选,初代世界至少应有 3 个。"""


    id: str
    name: str
    description: str = ""
    territory: list[str] = Field(default_factory=list, description="location_ids")
    leader_character_id: str | None = None
    allied_factions: list[str] = Field(default_factory=list)
    hostile_factions: list[str] = Field(default_factory=list)


class WorldState(_TickBase):
    """世界级状态 - WorldSimulator 输入与输出的核心契约。"""


    world_time: int = Field(default=0, description="世界时间 tick")
    era: str = ""
    current_season: str = ""
    weather: str = ""
    locations: list[TickLocation] = Field(default_factory=list)
    factions: list[Faction] = Field(default_factory=list)
    active_global_events: list[str] = Field(default_factory=list, description="战争/瘟疫等大背景")
    world_rules: list[str] = Field(default_factory=list, description="物理/魔法/社会规则,不超过10条")


class CharacterProfile(_TickBase):
    """角色档案 - 不变部分。CharacterAgent 实例化时一次性持有。"""


    id: str
    name: str
    age: int = 0
    role: str = Field(default="npc", description="主角|配角|NPC")
    importance_tier: ImportanceTier = "C"
    personality: str = ""
    appearance: str = ""
    speech_style: str = Field(default="", description="说话风格指纹")
    core_values: list[str] = Field(default_factory=list)
    fears: list[str] = Field(default_factory=list)
    desires: list[str] = Field(default_factory=list)

    @field_validator("age", mode="before")
    @classmethod
    def _coerce_age(cls, v):
        """LLM may return strings like "未知" or "未知（古老）" for mysterious entities.

        Try to parse leading integer; otherwise fall back to 0 instead of failing
        the whole CharacterProfile validation.
        """
        if isinstance(v, int):
            return v
        if v is None or v == "":
            return 0
        if isinstance(v, str):
            import re
            m = re.search(r"-?\d+", v)
            return int(m.group(0)) if m else 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0



class Goal(_TickBase):
    """角色短期/长期目标。CharacterState.current_goals 持有。"""


    id: str
    description: str
    priority: int = Field(default=5, ge=0, le=10)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    obstacles: list[str] = Field(default_factory=list)


class Relationship(_TickBase):
    """角色对角色的关系条目。CharacterState.relationships[other_id] 持有。"""


    with_character_id: str
    type: str = Field(default="stranger", description="朋友|敌人|恋人|陌生人|...")
    trust: int = Field(default=0, ge=-10, le=10)
    history_summary: str = ""
    last_interaction_tick: int = 0


class CharacterState(_TickBase):
    """角色可变状态 - 每 tick 由 CharacterAgent 更新。"""


    character_id: str
    current_location: str = Field(default="", description="location_id")
    current_goals: list[Goal] = Field(default_factory=list)
    arc_goal: str = Field(default="", description="长期弧线目标")
    arc_progress: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="arc 完成度,Showrunner 监控用",
    )
    arc_stage: ArcStage = Field(
        default="起点",
        description="v2.5 弧光阶段 — 由 CharacterArcTracker 监控并推荐推进",
    )
    arc_stage_entered_tick: int = Field(
        default=0,
        ge=0,
        description="本阶段开始的 tick, 用于检测 阶段停滞过久",
    )
    independent_agenda: list[str] = Field(
        default_factory=list,
        description="独立议程 — 该角色自己关心、但不为主角而存在的事项 (B 级配角必须)",
    )
    speech_fingerprint_features: list[str] = Field(
        default_factory=list,
        description="说话风格指纹特征 (如 短句 / 反问多 / 沉默多 / 偏书面)",
    )
    known_facts: list[str] = Field(
        default_factory=list,
        description="此角色知道的事 - CharacterAgent 决策的唯一信息源",
    )
    secrets_kept: list[str] = Field(default_factory=list)
    relationships: dict[str, Relationship] = Field(
        default_factory=dict, description="key=other_character_id"
    )
    emotional_state: str = "neutral"
    inventory: list[str] = Field(default_factory=list)
    status_effects: list[str] = Field(default_factory=list, description="受伤|生病|堕落中|...")
    # v2.18 — 经济维度。int (不接受自然语言); 不允许 < 0, Orchestrator 在 apply
    # 时 clamp 到 0 并打 money_overdraft flag。币种由 WorldState 隐含, 不区分多币种。
    money: int = Field(
        default=0,
        ge=0,
        description="角色当前持有的钱币数量, 不允许为负",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalise_llm_payload(cls, values):
        return _coerce_llm_payload(cls, values)


class Event(_TickBase):
    """世界事件 - 在 WorldSimulator / EventInjector / CharacterAgent 之间流转。

    可见性受 ``visible_to`` 严格约束 - CharacterAgent 只能看到自己 id 在
    ``visible_to`` 中的事件。这是戏剧性的根基(prompts.md 第 0 节第 4 条)。
    """


    id: str
    tick: int
    type: EventKind
    location: str = Field(default="", description="location_id")
    participants: list[str] = Field(default_factory=list, description="character_ids")
    description: str
    visible_to: list[str] = Field(
        default_factory=list, description="character_ids,能感知此事件的角色子集"
    )
    narrative_value: int = Field(default=0, ge=0, le=10, description="Narrator 评分")
    consequences: list[str] = Field(default_factory=list)
    # EventInjector 额外填写的诊断字段(其他来源的 Event 为 None)
    rationale: str | None = None
    predicted_consequences: list[str] | None = None
    narrative_value_hint: int | None = Field(default=None, ge=0, le=10)


class OpenLoop(_TickBase):
    """未解决的张力/伏笔 - Showrunner 维护冲突保留池 >=3 的核心抓手。"""


    id: str
    opened_tick: int
    description: str
    involved_characters: list[str] = Field(default_factory=list)
    urgency: int = Field(default=5, ge=0, le=10)
    type: OpenLoopType = "other"
    # 风险缓解:防 OpenLoop 数量失控 - 超过 max_age_ticks 强制关闭
    max_age_ticks: int = Field(
        default=200,
        ge=10,
        description="超过此 tick 数未消费则 Orchestrator 强制关闭",
    )
    last_referenced_tick: int = Field(
        default=0,
        description="Narrator 最近一次引用此 loop 的 tick,用于冷线索检测",
    )


class MemoryEntry(_TickBase):
    """分层记忆条目 - MemoryCompressor 在 L0/L1/L2/L3 间搬运。"""


    id: str
    tier: MemoryTier
    original_tick_range: tuple[int, int]
    summary: str
    emotional_tags: list[str] = Field(default_factory=list)
    involved: list[str] = Field(default_factory=list, description="character_ids")
    importance: int = Field(default=5, ge=0, le=10)
    # 保护标记 - 开放伏笔源头 / 创伤性事件,MemoryCompressor 跳过压缩
    protected_reason: str | None = None
    # v2.15 — 升级后保留所替换的下级 entry id 列表, 供 MemoryStore 真正退役旧记录。
    # 空列表 = 未经压缩生成的原始条目 (例如 L0 事件直接入库)。
    source_ids: list[str] = Field(default_factory=list)


class StyleAnchor(_TickBase):
    """风格锚点 - Narrator 每次写作时取 top-k 注入 system_prompt 保持文风。"""


    excerpt: str = Field(description="高质量段落,通常约 300 字")
    selection_reason: str = ""
    weight: float = Field(default=1.0, ge=0.0, description="权重,越高对 Narrator 影响越大")
    scene_type: str = Field(
        default="general",
        description="dialogue|action|inner_monologue|nature|general",
    )


# ---------------------------------------------------------------------------
# Orchestrator / Showrunner 输出诊断契约
# ---------------------------------------------------------------------------


class RelationshipDelta(_TickBase):
    """v2.16 — 角色关系的单 tick 增量更新。

    CharacterAction.relationship_deltas 用 ``{other_id: RelationshipDelta}`` 表达
    本 tick 内角色对其他角色关系的变化。Orchestrator._apply_actions 把它合并到
    CharacterState.relationships 中, 并 clamp trust 到 [-10, 10]。
    """

    trust_delta: int = Field(
        default=0,
        ge=-20,
        le=20,
        description="信任度增量, 应用前 clamp 到 ±20 防 LLM 出格; 合并后再 clamp 到 [-10, 10]",
    )
    new_type: str = Field(
        default="",
        description="若非空, 覆盖关系类型 (朋友|敌人|恋人|盟友|陌生人|...)",
    )
    history_entry: str = Field(
        default="",
        description="本 tick 互动的一句话摘要; 合并进 history_summary 尾部",
    )


class CharacterAction(_TickBase):
    """CharacterAgent 决策输出 - Orchestrator 阶段4(冲突解析)的输入。

    与遗留 ``ActionPlan`` 不同:``ActionPlan`` 是 OutlineAgent 给 WriterAgent
    的节级写作指南;``CharacterAction`` 是单角色 tick 内的具体行动。

    v2.16 — 硬状态转移字段 (new_location / inventory_*/ status_*/ relationship_deltas)
    让 CharacterAgent 输出能直接落到 CharacterState 上, 不再仅靠 Narrator 圆场。
    所有新字段都有零值默认, 旧 LLM 输出无需迁移。
    """


    character_id: str
    action_type: str = Field(default="wait", description="move|speak|fight|investigate|wait|...")
    target: str = ""
    description: str = ""
    dialogue_spoken: str | None = None
    dialogue_to_whom: list[str] = Field(default_factory=list)
    intent: str = Field(default="", description="角色的真实意图,其他角色不知道")
    internal_monologue: str = ""
    emotional_shift: str = ""
    completed_goal_ids: list[str] = Field(default_factory=list)
    new_goals: list[Goal] = Field(default_factory=list)
    abandoned_goal_ids: list[str] = Field(default_factory=list)
    newly_learned: list[str] = Field(default_factory=list, description="此 tick 新了解的事")
    newly_speculated: list[str] = Field(default_factory=list, description="新猜测")
    flags: list[str] = Field(default_factory=list, description="例如'此行动违背我的性格'")

    # v2.16 硬状态转移 —————————————————————————————————————————————————
    new_location: str = Field(
        default="",
        description="如本 tick 角色移动, 填入目标 location_id; 不变留空",
    )
    inventory_added: list[str] = Field(
        default_factory=list,
        description="本 tick 新获得的物品名称, 自动去重并入 CharacterState.inventory",
    )
    inventory_removed: list[str] = Field(
        default_factory=list,
        description="本 tick 失去/给出/丢弃的物品名称, 自动从 inventory 移除",
    )
    status_added: list[str] = Field(
        default_factory=list,
        description="本 tick 新增的身体/精神状态效果 (受伤|疲惫|中毒|...)",
    )
    status_removed: list[str] = Field(
        default_factory=list,
        description="本 tick 解除的状态效果 (治愈|休息恢复|...)",
    )
    relationship_deltas: dict[str, RelationshipDelta] = Field(
        default_factory=dict,
        description="key=对方 character_id, value=该关系本 tick 的增量更新",
    )
    # v2.18 — 经济动作的金额增量, +赚/抢/收 / -花/支/失。clamp 见 _apply_actions。
    money_delta: int = Field(
        default=0,
        ge=-1_000_000,
        le=1_000_000,
        description="本 tick 钱币变化, 上下限防 LLM 输出天文数字",
    )


class AgentRuntimeState(_TickBase):
    """Agent 运行态 — 与角色 CharacterState 分离的"调度信息"。

    设计意图: CharacterAgent 实例本身不该持有失败计数/冷却等可变运行态,
    否则进程重启/重建实例就丢; 同样 Orchestrator 也不该把这种 per-agent 元数据
    跟 CharacterState 混在一起 (角色"知道自己被 LLM 拒绝过几次"是荒谬的)。

    TickState 持有 dict[agent_id, AgentRuntimeState], save/load 时与
    character_states 平级持久化。``agent_id`` 通常形如
    ``"character_agent:<character_id>"`` / ``"narrator"`` / ``"world_simulator"``。
    """

    agent_id: str
    last_invoked_tick: int = Field(
        default=0, ge=0, description="最近一次被调用的 tick"
    )
    failure_count: int = Field(
        default=0,
        ge=0,
        description="连续失败次数; 成功调用清零",
    )
    cooldown_until_tick: int = Field(
        default=0,
        ge=0,
        description="若 > current_tick 则跳过本 agent; 0 表示无冷却",
    )
    model_tier_override: str = Field(
        default="",
        description="临时降级标记 (haiku 替 sonnet 等), 由 Guardian 监控写入",
    )
    summary_cache: str = Field(
        default="",
        description="跨 tick 复用的摘要缓存 (例如 CharacterAgent 自我描述), 减少 prompt 重算",
    )


class TickSummary(_TickBase):
    """Orchestrator 每 tick 结束时的诊断输出 - 写入 TickDB,推送给前端 SSE。"""


    tick: int
    world_time: int
    world_time_advanced: str = ""
    agents_called: list[str] = Field(default_factory=list)
    events_generated: list[str] = Field(default_factory=list, description="event_ids")
    narrator_produced_text: bool = False
    narrator_output_chars: int = 0
    state_changes_summary: str = ""
    next_tick_recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# v2.4 叙事大纲层 — StoryArc / KeyBeat / PacingPoint / SuspenseLevel
# ---------------------------------------------------------------------------


BeatStatus = Literal["pending", "active", "completed", "skipped"]
PacingIntensity = Literal["low", "medium", "high", "climax"]
SuspenseLevel = Literal["background", "active", "escalating", "peaking"]


class KeyBeat(_TickBase):
    """剧情大纲中的关键节拍。

    设计原则:
    * 不指定具体场景, 只指定戏剧目标 — 让 Narrator / EventInjector 自由实现
    * 有目标 tick 区间但不强制 (window_start ≤ 触达 tick ≤ window_end)
    * status 由 StoryArcDirector 推断, 完成态后保留作为伏笔回响参考
    """

    id: str
    title: str
    description: str = Field(description="该节拍要达到的戏剧目标, 而非具体场景")
    act: int = Field(default=1, ge=1, le=5, description="所属幕, 默认 3 幕剧")
    window_start: int = Field(default=0, ge=0, description="可触发的最早 tick")
    window_end: int = Field(default=100, ge=0, description="必须完成的最晚 tick")
    status: BeatStatus = "pending"
    triggered_at_tick: int = 0
    completion_evidence: list[str] = Field(
        default_factory=list,
        description="完成证据 — 关联的事件 id / Narrator 段落标记",
    )
    importance: int = Field(default=7, ge=1, le=10)


class PacingPoint(_TickBase):
    """单 tick 的强度采样 — StoryArcDirector 用于绘制节奏曲线。"""

    tick: int
    intensity: PacingIntensity = "medium"
    narrative_value_sum: int = 0
    is_narration_produced: bool = False


class StoryArc(_TickBase):
    """全局叙事大纲 — 在冷启动时生成, 由 StoryArcDirector 维护。

    防止"叙事动力枯竭"与"情节循环":
    * theme — 主题锚点, 所有章节必须呼应 (但不直接说出)
    * key_beats — 剧本骨架, 按 act 分组, 不达成则强制 EventInjector 兜底
    * current_act / target_climax_tick — 当前位置与终点目标, 防止漂流
    * pacing_history — 最近 N 个 tick 的强度采样, 用于节奏校正
    * suspense_pool — 按 level 分级的悬念池, 强制 ≥1 escalating + ≥1 active
    """

    title: str = ""
    theme: str = Field(
        default="",
        description="一句话主题 — 不是答案, 是问题",
    )
    central_question: str = Field(
        default="",
        description="读者要带走的'问题', 不是结论",
    )
    current_act: int = Field(default=1, ge=1, le=5)
    target_climax_tick: int = Field(
        default=500,
        ge=10,
        description="预期高潮 tick, 节奏曲线向此收敛",
    )
    key_beats: list[KeyBeat] = Field(default_factory=list)
    pacing_history: list[PacingPoint] = Field(
        default_factory=list,
        description="最近 N 个 tick 的强度采样, 上限由 director 维护",
    )
    last_updated_tick: int = 0


class StoryArcDirective(_TickBase):
    """StoryArcDirector 输出 — 给 Orchestrator / EventInjector / Narrator 的调度指令。"""

    intensity_recommendation: PacingIntensity = "medium"
    needs_escalation: bool = False
    needs_breather: bool = False
    active_beat_id: str | None = None
    overdue_beats: list[str] = Field(default_factory=list)
    theme_reminder: str = ""
    narrator_hint: str = Field(
        default="",
        description="单句, 注入 Narrator 用户提示, 不显式说出主题",
    )
    suspense_pool_health: SuspenseLevel = "active"
    diagnosis: str = ""


__all__ = [
    # 遗留 dataclass
    "EntityType",
    "RelationType",
    "Entity",
    "Relation",
    "GraphSnapshot",
    "Section",
    "ActionPlan",
    "ValidationResult",
    # tick 字面量类型
    "ImportanceTier",
    "EventKind",
    "MemoryTier",
    "ConflictPriority",
    "ConflictType",
    "OpenLoopType",
    "ArcStage",
    # tick Pydantic 契约
    "TickLocation",
    "Faction",
    "WorldState",
    "CharacterProfile",
    "Goal",
    "Relationship",
    "CharacterState",
    "Event",
    "OpenLoop",
    "MemoryEntry",
    "StyleAnchor",
    "RelationshipDelta",
    "CharacterAction",
    "AgentRuntimeState",
    "TickSummary",
    # v2.4 叙事大纲层
    "BeatStatus",
    "PacingIntensity",
    "SuspenseLevel",
    "KeyBeat",
    "PacingPoint",
    "StoryArc",
    "StoryArcDirective",
]
