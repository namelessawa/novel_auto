"""ActionResolver — Orchestrator 阶段 4 的行动冲突解析,无 LLM。

prompts.md 第 12 节 step 4:
> resolve_action_conflicts(char_actions, world_state) - 处理同一目标位置/
> 同一目标对象的冲突

策略(从简到复杂):
1. 按 (action_type, target) 分桶,识别独占性冲突类(fight/take/control/claim/attack)
2. 同桶内按 (importance_tier: A>B>C, 该角色目标优先级 desc, 角色 id 字典序) 排序
3. 第一名保留原行动;其他角色获得 ``flags=['conflict_lost:<winner_id>']``
   且 ``action_type='wait'`` (描述追加 "因冲突未能完成原行动")

非独占类(speak/move/wait/investigate)不视为冲突。

注意: 本类**不修改 WorldState**,只重排 / 标注 CharacterAction。世界状态更新由
Orchestrator 阶段 5(``_phase5_apply_changes``)负责。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from memory_system.models import CharacterAction, CharacterProfile, WorldState

logger = logging.getLogger(__name__)

# 独占类行动 - 同 target 仅一个角色可成功
EXCLUSIVE_ACTION_TYPES = frozenset(
    {"fight", "attack", "kill", "take", "steal", "claim", "control", "occupy"}
)

# A > B > C
_TIER_RANK = {"A": 0, "B": 1, "C": 2}


@dataclass(frozen=True)
class ResolutionDiagnostic:
    """单次 resolve() 的结果诊断,供 TickSummary 与日志记录。"""

    conflict_groups: int
    losers: int
    winner_by_group: dict[str, str]  # group_key -> winner_character_id


class ActionResolver:
    """Pure-Python 行动冲突解析器。"""

    def __init__(
        self,
        exclusive_types: frozenset[str] = EXCLUSIVE_ACTION_TYPES,
    ) -> None:
        self._exclusive_types = exclusive_types

    def resolve(
        self,
        actions: list[CharacterAction],
        profiles: dict[str, CharacterProfile],
        world_state: WorldState | None = None,
    ) -> tuple[list[CharacterAction], ResolutionDiagnostic]:
        """返回 (resolved_actions, diagnostic)。

        ``actions`` 顺序保持不变 — 仅 ``CharacterAction`` 内容会被 model_copy 替换。
        ``world_state`` 当前不使用,留作未来扩展(例如 location-based 容量限制)。
        """
        if not actions:
            return [], ResolutionDiagnostic(0, 0, {})

        # 1. 按 (action_type, target) 分桶
        buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
        for idx, act in enumerate(actions):
            if act.action_type not in self._exclusive_types:
                continue
            if not act.target:
                # 无明确 target 的独占类视为各自独立
                continue
            buckets[(act.action_type, act.target)].append(idx)

        winner_by_group: dict[str, str] = {}
        losers_total = 0
        resolved: list[CharacterAction] = list(actions)  # 浅拷贝引用

        # 2. 对每个有 >=2 个 contender 的桶解析冲突
        for (atype, target), indices in buckets.items():
            if len(indices) < 2:
                continue

            ranked = sorted(
                indices,
                key=lambda i: self._priority_key(resolved[i], profiles),
            )
            winner_idx = ranked[0]
            winner_id = resolved[winner_idx].character_id
            group_key = f"{atype}:{target}"
            winner_by_group[group_key] = winner_id

            # 标注 losers
            for loser_idx in ranked[1:]:
                losers_total += 1
                loser = resolved[loser_idx]
                lost_flag = f"conflict_lost:{winner_id}"
                # v2.18 — 清零败者的"成果"字段, 否则阶段 5 _apply_actions
                # 仍会把这些硬转移写回 CharacterState (例如两人同 take 同物品,
                # 败者 action_type 改 wait 但 inventory_added=["剑"] 仍在,
                # 导致两人都获得剑)。
                # 主动卸下/解除 (inventory_removed / status_removed / 负 money_delta)
                # 保留 — 失败也允许"丢掉手里的剑"/"挣脱中毒"/"自愿支付意图"。
                cleared_money = (
                    loser.money_delta if loser.money_delta < 0 else 0
                )
                resolved[loser_idx] = loser.model_copy(
                    update={
                        "action_type": "wait",
                        "description": (
                            (loser.description or "")
                            + f" (原计划'{atype} → {target}'因 {winner_id} 优先而搁置)"
                        ).strip(),
                        "flags": list(loser.flags) + [lost_flag],
                        "new_location": "",
                        "inventory_added": [],
                        "status_added": [],
                        "relationship_deltas": {},
                        "money_delta": cleared_money,
                    }
                )
            logger.info(
                "Conflict on (%s, %s): winner=%s, losers=%d",
                atype,
                target,
                winner_id,
                len(ranked) - 1,
            )

        diag = ResolutionDiagnostic(
            conflict_groups=sum(1 for v in buckets.values() if len(v) >= 2),
            losers=losers_total,
            winner_by_group=winner_by_group,
        )
        return resolved, diag

    # ------------------------------------------------------------------

    @staticmethod
    def _priority_key(
        action: CharacterAction, profiles: dict[str, CharacterProfile]
    ) -> tuple[int, int, str]:
        """排序键: (tier_rank, -goal_priority, character_id)。越小越优先。"""
        profile = profiles.get(action.character_id)
        tier_rank = _TIER_RANK.get(profile.importance_tier, 9) if profile else 9
        # goal priority 取已完成 goal_id 对应的 priority? - CharacterAction 没带 goal 信息
        # 退化:用 new_goals 的最高 priority,作为该角色本 tick "投入度" 指标
        top_priority = 0
        if action.new_goals:
            top_priority = max(g.priority for g in action.new_goals)
        return (tier_rank, -top_priority, action.character_id)
