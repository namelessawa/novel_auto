"""Writer Agent — generates the final section prose."""

from __future__ import annotations

from typing import AsyncIterator

from core.llm_client import llm_client
from core.models import ActionPlan, Section

SYSTEM_PROMPT = """\
你是一位才华横溢的网络小说作家。请根据提供的行动指南、角色状态、历史细节和前文内容，
撰写下一节正文。

写作要求：
1. 叙事流畅，情节紧凑，符合网文节奏（节奏感、爽点、钩子）。
2. 人物对话要贴合角色性格，避免出戏（OOC）。
3. 场景描写要有代入感，善用五感描写。
4. 严格遵循行动指南的情节走向，不偏离主线。
5. 结尾留有悬念或钩子，引导读者继续阅读。
6. 字数控制在 1500-3000 字之间。
7. 不要输出任何元信息（如"第X章"标题），直接输出正文。
"""


class WriterAgent:
    async def write(
        self,
        plan: ActionPlan,
        entity_states: list[str],
        historical_fragments: list[str],
        recent_text: str,
        scene_info: str,
    ) -> Section:
        user_prompt = self._build_prompt(
            plan, entity_states, historical_fragments, recent_text, scene_info
        )
        resp = await llm_client.chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.85,
            max_tokens=8192,
        )
        content = resp.content.strip()
        return Section(
            chapter=plan.chapter,
            section=plan.section,
            title=plan.plan_text[:20],
            content=content,
            word_count=len(content),
        )

    async def write_stream(
        self,
        plan: ActionPlan,
        entity_states: list[str],
        historical_fragments: list[str],
        recent_text: str,
        scene_info: str,
    ) -> AsyncIterator[str]:
        user_prompt = self._build_prompt(
            plan, entity_states, historical_fragments, recent_text, scene_info
        )
        async for chunk in llm_client.chat_stream(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.85,
            max_tokens=8192,
        ):
            yield chunk

    @staticmethod
    def _build_prompt(
        plan: ActionPlan,
        entity_states: list[str],
        historical_fragments: list[str],
        recent_text: str,
        scene_info: str,
    ) -> str:
        states = "\n".join(entity_states) if entity_states else "（无）"
        history = "\n".join(historical_fragments) if historical_fragments else "（无）"
        return (
            f"【行动指南】\n{plan.plan_text}\n\n"
            f"【角色/实体当前状态】\n{states}\n\n"
            f"【相关历史细节】\n{history}\n\n"
            f"【当前场景】\n{scene_info}\n\n"
            f"【前文（最近）】\n{recent_text[-3000:]}\n\n"
            "请开始撰写本节正文。"
        )
