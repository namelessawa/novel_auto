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

from pydantic import BaseModel, ConfigDict, Field

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


ImportanceTier = Literal["A", "B", "C"]
EventKind = Literal["endogenous", "exogenous", "dramatic", "character_action"]
MemoryTier = Literal["L0", "L1", "L2", "L3"]
ConflictPriority = Literal["A", "B", "C", "D"]
ConflictType = Literal["character", "time", "setting", "relationship", "item"]
OpenLoopType = Literal["mystery", "conflict", "promise", "threat", "other"]


class TickLocation(BaseModel):
    """世界中的一个地点。与遗留 ``Entity(entity_type=LOCATION)`` 不冲突。"""

    model_config = _TickModelConfig

    id: str
    name: str
    type: str = Field(default="region", description="city|village|wilderness|...")
    current_state: str = Field(default="", description="自然语言描述")
    present_characters: list[str] = Field(default_factory=list, description="character_ids")
    notable_features: list[str] = Field(default_factory=list)


class Faction(BaseModel):
    """势力。WorldState 引用,可选,初代世界至少应有 3 个。"""

    model_config = _TickModelConfig

    id: str
    name: str
    description: str = ""
    territory: list[str] = Field(default_factory=list, description="location_ids")
    leader_character_id: str | None = None
    allied_factions: list[str] = Field(default_factory=list)
    hostile_factions: list[str] = Field(default_factory=list)


class WorldState(BaseModel):
    """世界级状态 - WorldSimulator 输入与输出的核心契约。"""

    model_config = _TickModelConfig

    world_time: int = Field(default=0, description="世界时间 tick")
    era: str = ""
    current_season: str = ""
    weather: str = ""
    locations: list[TickLocation] = Field(default_factory=list)
    factions: list[Faction] = Field(default_factory=list)
    active_global_events: list[str] = Field(default_factory=list, description="战争/瘟疫等大背景")
    world_rules: list[str] = Field(default_factory=list, description="物理/魔法/社会规则,不超过10条")


class CharacterProfile(BaseModel):
    """角色档案 - 不变部分。CharacterAgent 实例化时一次性持有。"""

    model_config = _TickModelConfig

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


class Goal(BaseModel):
    """角色短期/长期目标。CharacterState.current_goals 持有。"""

    model_config = _TickModelConfig

    id: str
    description: str
    priority: int = Field(default=5, ge=0, le=10)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    obstacles: list[str] = Field(default_factory=list)


class Relationship(BaseModel):
    """角色对角色的关系条目。CharacterState.relationships[other_id] 持有。"""

    model_config = _TickModelConfig

    with_character_id: str
    type: str = Field(default="stranger", description="朋友|敌人|恋人|陌生人|...")
    trust: int = Field(default=0, ge=-10, le=10)
    history_summary: str = ""
    last_interaction_tick: int = 0


class CharacterState(BaseModel):
    """角色可变状态 - 每 tick 由 CharacterAgent 更新。"""

    model_config = _TickModelConfig

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


class Event(BaseModel):
    """世界事件 - 在 WorldSimulator / EventInjector / CharacterAgent 之间流转。

    可见性受 ``visible_to`` 严格约束 - CharacterAgent 只能看到自己 id 在
    ``visible_to`` 中的事件。这是戏剧性的根基(prompts.md 第 0 节第 4 条)。
    """

    model_config = _TickModelConfig

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


class OpenLoop(BaseModel):
    """未解决的张力/伏笔 - Showrunner 维护冲突保留池 >=3 的核心抓手。"""

    model_config = _TickModelConfig

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


class MemoryEntry(BaseModel):
    """分层记忆条目 - MemoryCompressor 在 L0/L1/L2/L3 间搬运。"""

    model_config = _TickModelConfig

    id: str
    tier: MemoryTier
    original_tick_range: tuple[int, int]
    summary: str
    emotional_tags: list[str] = Field(default_factory=list)
    involved: list[str] = Field(default_factory=list, description="character_ids")
    importance: int = Field(default=5, ge=0, le=10)
    # 保护标记 - 开放伏笔源头 / 创伤性事件,MemoryCompressor 跳过压缩
    protected_reason: str | None = None


class StyleAnchor(BaseModel):
    """风格锚点 - Narrator 每次写作时取 top-k 注入 system_prompt 保持文风。"""

    model_config = _TickModelConfig

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


class CharacterAction(BaseModel):
    """CharacterAgent 决策输出 - Orchestrator 阶段4(冲突解析)的输入。

    与遗留 ``ActionPlan`` 不同:``ActionPlan`` 是 OutlineAgent 给 WriterAgent
    的节级写作指南;``CharacterAction`` 是单角色 tick 内的具体行动。
    """

    model_config = _TickModelConfig

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


class TickSummary(BaseModel):
    """Orchestrator 每 tick 结束时的诊断输出 - 写入 TickDB,推送给前端 SSE。"""

    model_config = _TickModelConfig

    tick: int
    world_time: int
    world_time_advanced: str = ""
    agents_called: list[str] = Field(default_factory=list)
    events_generated: list[str] = Field(default_factory=list, description="event_ids")
    narrator_produced_text: bool = False
    narrator_output_chars: int = 0
    state_changes_summary: str = ""
    next_tick_recommendations: list[str] = Field(default_factory=list)


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
    "CharacterAction",
    "TickSummary",
]
