"""tick → KnowledgeGraph 同步 (v2.34).

UpdateAgent 是 v1.x 章节链路遗留, tick 架构整条流程从不写 KG, 导致前端
"知识图谱" tab 始终 0 实体 0 关系。本模块用纯 Python (无 LLM) 从 TickState
+ 本 tick events 派生实体和关系, 每 tick 末由 Orchestrator 调用一次。

设计原则:
* **幂等**: 同一 tick 调多次结果一致。networkx 节点/边按 id upsert, 不会
  重复创建。
* **不删除**: 角色/地点一旦进图就不撤回; 角色"死亡"不删节点 (剧情仍可
  回忆此人), 在 attributes 里打 status=dead。关系 type 变更 (朋友→敌人)
  覆盖旧 edge.
* **零 LLM 依赖**: 同步成本可忽略, 不进 token budget。
* **无副作用**: 只读 tick_state / events, 只写 kg。Orchestrator 失败仍能 tick。

数据源 → 图元素映射:

| tick 来源                                  | KG 元素                                |
|--------------------------------------------|----------------------------------------|
| ``CharacterProfile``                       | Entity(CHARACTER), attrs=tier/role     |
| ``CharacterState.status_effects``          | 节点 attr.status                       |
| ``CharacterState.current_location``        | Relation LOCATED_AT                    |
| ``CharacterState.relationships[other]``    | Relation KNOWS/HOSTILE/ALLIED/LOVES    |
| ``WorldState.locations``                   | Entity(LOCATION), attrs=type/state     |
| ``WorldState.factions``                    | Entity(FACTION)                        |
| ``Faction.leader_character_id``            | Relation MASTER_OF                     |
| ``Faction.allied_factions``                | Relation ALLIED                        |
| ``Faction.hostile_factions``               | Relation HOSTILE                       |
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from memory_system.models import (
    Entity,
    EntityType,
    Relation,
    RelationType,
)

if TYPE_CHECKING:
    from graph.knowledge_graph import KnowledgeGraph
    from memory.tick_state import TickState
    from memory_system.models import Event

logger = logging.getLogger(__name__)


# 角色状态 (中文 type) → RelationType + 是否保留中文 label.
# 兜底用 KNOWS + label=原 type, 让前端仍能看到"朋友/陌生人"的细分。
_RELATIONSHIP_TYPE_MAP: dict[str, RelationType] = {
    "盟友": RelationType.ALLIED,
    "战友": RelationType.ALLIED,
    "同盟": RelationType.ALLIED,
    "敌人": RelationType.HOSTILE,
    "仇敌": RelationType.HOSTILE,
    "宿敌": RelationType.HOSTILE,
    "对手": RelationType.HOSTILE,
    "恋人": RelationType.LOVES,
    "情人": RelationType.LOVES,
    "爱人": RelationType.LOVES,
    "父子": RelationType.PARENT_OF,
    "父女": RelationType.PARENT_OF,
    "母子": RelationType.PARENT_OF,
    "母女": RelationType.PARENT_OF,
    "师徒": RelationType.MASTER_OF,
    "师父": RelationType.MASTER_OF,
    "师傅": RelationType.MASTER_OF,
}


@dataclass(frozen=True)
class SyncStats:
    """同步结果统计, 供 TickSummary 诊断或日志。"""

    entities_added: int = 0
    relations_added: int = 0
    entities_updated: int = 0


def _resolve_relation_type(chinese_type: str) -> tuple[RelationType, str]:
    """中文关系名 → (RelationType, label)。未知映射时 KNOWS + 原文 label。"""
    if not chinese_type:
        return RelationType.KNOWS, ""
    if chinese_type in _RELATIONSHIP_TYPE_MAP:
        return _RELATIONSHIP_TYPE_MAP[chinese_type], chinese_type
    # 朋友 / 陌生人 / 同学 / ... 都归 KNOWS, 用 label 保留细分
    return RelationType.KNOWS, chinese_type


def sync_tick_state_to_kg(
    kg: "KnowledgeGraph",
    tick_state: "TickState",
    tick_events: "list[Event] | None" = None,
) -> SyncStats:
    """把 TickState 当前快照 + 本 tick 事件同步到 KG。

    幂等:重复调用结果相同。调用方应在 Orchestrator._run_tick_unlocked 末尾
    (持久化之后) 调一次, 让 KG 反映"本 tick 后"的世界状态。

    Args:
        kg: 目标 KnowledgeGraph 实例
        tick_state: 当前 TickState (角色档案 / 状态 / 世界)
        tick_events: 本 tick 全部事件 (用于将来扩展, 当前未消费)

    Returns:
        SyncStats(entities_added, relations_added, entities_updated)
    """
    stats_entities_added = 0
    stats_entities_updated = 0
    stats_relations_added = 0

    # ------------------------------------------------------------------
    # 1. 实体: CharacterProfile → Entity(CHARACTER)
    # ------------------------------------------------------------------
    existing_entity_ids = {e.id for e in kg.list_entities()}
    char_states = {
        s.character_id: s for s in tick_state.list_character_states()
    }
    for profile in tick_state.list_character_profiles():
        state = char_states.get(profile.id)
        attrs = {
            "tier": profile.importance_tier,
            "role": profile.role,
            "age": profile.age,
        }
        if state is not None:
            if state.status_effects:
                attrs["status_effects"] = list(state.status_effects)
            if state.emotional_state:
                attrs["emotional_state"] = state.emotional_state
            # "dead" / "死亡" 状态时打死亡标记, 让前端可着色
            if any(
                "dead" in (s or "").lower() or "死" in (s or "")
                for s in (state.status_effects or [])
            ):
                attrs["dead"] = True
        if profile.id in existing_entity_ids:
            try:
                kg.update_entity_attributes(profile.id, attrs)
                stats_entities_updated += 1
            except KeyError:
                pass
        else:
            kg.add_entity(
                Entity(
                    id=profile.id,
                    name=profile.name or profile.id,
                    entity_type=EntityType.CHARACTER,
                    attributes=attrs,
                )
            )
            stats_entities_added += 1
            existing_entity_ids.add(profile.id)

    # ------------------------------------------------------------------
    # 2. 实体: WorldState.locations → Entity(LOCATION)
    # ------------------------------------------------------------------
    ws = tick_state.world_state
    for loc in ws.locations:
        attrs = {
            "type": loc.type,
            "current_state": (loc.current_state or "")[:200],
        }
        if loc.notable_features:
            attrs["notable_features"] = list(loc.notable_features)
        if loc.id in existing_entity_ids:
            try:
                kg.update_entity_attributes(loc.id, attrs)
                stats_entities_updated += 1
            except KeyError:
                pass
        else:
            kg.add_entity(
                Entity(
                    id=loc.id,
                    name=loc.name or loc.id,
                    entity_type=EntityType.LOCATION,
                    attributes=attrs,
                )
            )
            stats_entities_added += 1
            existing_entity_ids.add(loc.id)

    # ------------------------------------------------------------------
    # 3. 实体: WorldState.factions → Entity(FACTION)
    # ------------------------------------------------------------------
    for fac in ws.factions:
        attrs = {
            "description": (fac.description or "")[:200],
            "territory": list(fac.territory),
        }
        if fac.id in existing_entity_ids:
            try:
                kg.update_entity_attributes(fac.id, attrs)
                stats_entities_updated += 1
            except KeyError:
                pass
        else:
            kg.add_entity(
                Entity(
                    id=fac.id,
                    name=fac.name or fac.id,
                    entity_type=EntityType.FACTION,
                    attributes=attrs,
                )
            )
            stats_entities_added += 1
            existing_entity_ids.add(fac.id)

    # ------------------------------------------------------------------
    # 4. 关系: CharacterState.current_location → LOCATED_AT
    # ------------------------------------------------------------------
    for state in char_states.values():
        if not state.current_location:
            continue
        if state.current_location not in existing_entity_ids:
            continue
        if state.character_id not in existing_entity_ids:
            continue
        try:
            kg.add_relation(
                Relation(
                    source_id=state.character_id,
                    target_id=state.current_location,
                    relation_type=RelationType.LOCATED_AT,
                    label="位于",
                )
            )
            stats_relations_added += 1
        except KeyError as e:
            logger.debug("LOCATED_AT skipped (%s)", e)

    # ------------------------------------------------------------------
    # 5. 关系: CharacterState.relationships → KNOWS / HOSTILE / ...
    # ------------------------------------------------------------------
    for state in char_states.values():
        for other_id, rel in state.relationships.items():
            if not other_id or other_id == state.character_id:
                continue
            if other_id not in existing_entity_ids:
                # 关系指向尚未建模的角色 (可能是 C 级 NPC), 跳过避免脏节点
                continue
            rtype, label = _resolve_relation_type(rel.type or "")
            try:
                kg.add_relation(
                    Relation(
                        source_id=state.character_id,
                        target_id=other_id,
                        relation_type=rtype,
                        label=label,
                        weight=max(0.1, (rel.trust + 10) / 20.0),  # 0..1
                    )
                )
                stats_relations_added += 1
            except KeyError as e:
                logger.debug("relation skipped (%s)", e)

    # ------------------------------------------------------------------
    # 6. 关系: Faction.leader_character_id → MASTER_OF
    #         Faction.allied_factions → ALLIED
    #         Faction.hostile_factions → HOSTILE
    # ------------------------------------------------------------------
    for fac in ws.factions:
        if fac.leader_character_id and fac.leader_character_id in existing_entity_ids:
            try:
                kg.add_relation(
                    Relation(
                        source_id=fac.leader_character_id,
                        target_id=fac.id,
                        relation_type=RelationType.MASTER_OF,
                        label="首领",
                    )
                )
                stats_relations_added += 1
            except KeyError as e:
                logger.debug("MASTER_OF skipped (%s)", e)
        for ally_id in fac.allied_factions or []:
            if ally_id not in existing_entity_ids or ally_id == fac.id:
                continue
            try:
                kg.add_relation(
                    Relation(
                        source_id=fac.id,
                        target_id=ally_id,
                        relation_type=RelationType.ALLIED,
                        label="结盟",
                    )
                )
                stats_relations_added += 1
            except KeyError as e:
                logger.debug("ALLIED faction skipped (%s)", e)
        for foe_id in fac.hostile_factions or []:
            if foe_id not in existing_entity_ids or foe_id == fac.id:
                continue
            try:
                kg.add_relation(
                    Relation(
                        source_id=fac.id,
                        target_id=foe_id,
                        relation_type=RelationType.HOSTILE,
                        label="敌对",
                    )
                )
                stats_relations_added += 1
            except KeyError as e:
                logger.debug("HOSTILE faction skipped (%s)", e)

    return SyncStats(
        entities_added=stats_entities_added,
        relations_added=stats_relations_added,
        entities_updated=stats_entities_updated,
    )


__all__ = ["sync_tick_state_to_kg", "SyncStats"]
