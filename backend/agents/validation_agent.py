"""Validation Agent — checks action plan against knowledge graph for conflicts."""

from __future__ import annotations

from nf_core.llm_client import llm_client
from memory_system.models import ActionPlan, ValidationResult
from graph.knowledge_graph import KnowledgeGraph

SYSTEM_PROMPT = """\
你是一位严谨的小说逻辑审查员。你的任务是检查《行动指南》是否与当前的世界状态（知识图谱）存在冲突。

冲突类型包括：
1. 已死亡角色重新出现且无合理解释。
2. 角色使用不持有的道具或未掌握的技能。
3. 角色出现在不可达的地点。
4. 关系矛盾（如已知敌对的角色突然合作，缺乏铺垫）。
5. 时间线矛盾。

如果无冲突，输出：
结论: 通过

如果有冲突，输出：
结论: 冲突
冲突1: <描述>
冲突2: <描述>
建议: <修改建议>
"""


class ValidationAgent:
    def __init__(self, graph: KnowledgeGraph) -> None:
        self._graph = graph

    async def validate(
        self,
        plan: ActionPlan,
        entity_states: list[str],
    ) -> ValidationResult:
        states_text = "\n".join(entity_states) if entity_states else "（无相关实体状态）"

        user_prompt = (
            f"【行动指南】\n{plan.plan_text}\n\n"
            f"【涉及实体当前状态】\n{states_text}\n\n"
            "请判断上述行动指南是否与世界状态冲突。"
        )

        resp = await llm_client.chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=20480,
        )

        return self._parse(resp.content)

    @staticmethod
    def _parse(raw: str) -> ValidationResult:
        lines = raw.strip().split("\n")
        is_valid = True
        conflicts: list[str] = []
        suggestions: list[str] = []

        for line in lines:
            line = line.strip()
            if "冲突" in line and ("结论" in line or line.startswith("结论")):
                is_valid = False
            elif line.startswith("冲突"):
                conflict_text = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                if conflict_text:
                    conflicts.append(conflict_text)
            elif line.startswith("建议"):
                suggestion = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                if suggestion:
                    suggestions.append(suggestion)

        return ValidationResult(
            is_valid=is_valid,
            conflicts=conflicts,
            suggestions=suggestions,
        )
