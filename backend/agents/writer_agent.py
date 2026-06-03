"""Writer Agent — generates the final section prose."""

from __future__ import annotations

from typing import AsyncIterator

from agents.quality_spec import render_narrator_quality_block
from nf_core.llm_client import llm_client
from memory_system.models import ActionPlan, Section

SYSTEM_PROMPT = (
    """\
你是一位严苛于自身的小说写作者。请根据提供的行动指南、角色状态、历史细节和前文内容,
撰写下一节正文。

# 写作要求

1. 叙事流畅, 情节紧凑, 节奏服务于角色困境而非套路化的"爽点"
2. 人物对话必须贴合该角色档案中的说话风格 (省略名字仍能分辨是谁)
3. 场景描写多感官, 但每段聚焦一种主导感官, 不要"摄像机扫视"
4. 严格遵循行动指南, 但允许角色在行动中表现犹豫、错误判断、失态
5. 章节结尾不写"反思 / 升华 / 总结" — 停在动作 / 物件 / 对话上
6. 字数控制在 1500-3000 字之间, 句长长短交错, 避免句式过分对仗
7. 不要输出任何元信息 (如"第X章"标题), 直接输出正文

---

"""
    + render_narrator_quality_block()
    + """

---

# 元规则

* 不奖励自己 — 默认你的第一稿有 AI 痕迹, 主动剔除黑名单词
* 代价原则 — 主角的胜利必须有代价 (关系 / 健康 / 信念 / 选择的另一面)
* 直接说情绪 = D4 触发 (高严重度) — 改为身体动作 + 周遭物件的反应
* 留白原则 — 同样能写明白或留白时, 留白更佳
"""
)


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
            max_tokens=163840,
            agent_id="writer_agent",
            priority="critical",
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
            max_tokens=163840,
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
