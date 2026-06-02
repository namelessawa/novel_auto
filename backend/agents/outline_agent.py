"""Outline Agent — generates the 100-word action plan for the next section."""

from __future__ import annotations

from nf_core.llm_client import llm_client
from memory_system.models import ActionPlan

SYSTEM_PROMPT = """\
你是一位资深网文大纲策划师。根据提供的全书梗概、前文内容和当前场景信息，
为下一节撰写一份《100字行动指南》。

要求：
1. 明确本节的核心冲突或转折。
2. 列出需要出场的关键角色（用"【角色名】"标注）。
3. 列出涉及的关键道具/地点/技能（用"《道具名》"标注）。
4. 控制在 100 字左右。
5. 用简洁的叙事指令，而非完整的正文。

输出格式：
行动指南: <指南文本>
关键实体: <逗号分隔的实体ID列表>
关键词: <逗号分隔的关键词列表>
"""


class OutlineAgent:
    async def plan(
        self,
        chapter: int,
        section: int,
        global_outline: str,
        recent_text: str,
        scene_info: str,
    ) -> ActionPlan:
        user_prompt = (
            f"当前进度: 第{chapter}章 第{section}节\n\n"
            f"【全书梗概】\n{global_outline}\n\n"
            f"【前文与场景】\n{scene_info}\n\n"
            f"【最近正文】\n{recent_text[-2000:]}\n\n"
            "请生成下一节的《100字行动指南》。"
        )

        resp = await llm_client.chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.6,
            max_tokens=512,
        )

        plan_text, entities, keywords = self._parse(resp.content)
        return ActionPlan(
            chapter=chapter,
            section=section,
            plan_text=plan_text,
            key_entities=entities,
            keywords=keywords,
        )

    @staticmethod
    def _parse(raw: str) -> tuple[str, list[str], list[str]]:
        plan_text = raw
        entities: list[str] = []
        keywords: list[str] = []

        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("行动指南:") or line.startswith("行动指南："):
                plan_text = line.split(":", 1)[-1].split("：", 1)[-1].strip()
            elif line.startswith("关键实体:") or line.startswith("关键实体："):
                raw_entities = line.split(":", 1)[-1].split("：", 1)[-1]
                entities = [
                    e.strip() for e in raw_entities.split(",") if e.strip()
                ]
            elif line.startswith("关键词:") or line.startswith("关键词："):
                raw_kw = line.split(":", 1)[-1].split("：", 1)[-1]
                keywords = [
                    k.strip() for k in raw_kw.split(",") if k.strip()
                ]

        return plan_text, entities, keywords
