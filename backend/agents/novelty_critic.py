"""NoveltyCritic — 重复模式检测 (prompts.md 第 11 节)。

每 20 tick 调用,输出 detected_patterns 与 recommendations,Orchestrator 写入
TickState.novelty_warnings,供 Narrator / EventInjector 下次调用参考。

检测模式:
1. 情节结构重复(都是"接受任务→遭遇阻碍→克服→回归")
2. 冲突类型重复(都是欺骗 / 都是战斗 / 都是误会)
3. 角色行为重复(某角色反复用同样方式解决问题)
4. 修辞与意象重复(某些句式/比喻/意象密度过高)
5. 场景类型重复(反复在相同地点 / 时段 / 关系组合)

虽然 prompts.md 把它放 P2,我把它一并放 P1 — 实现简单,且为 Narrator 提供反馈通路。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from memory_system.models import Event
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
你监控故事的新颖性。运行越久,重复模式越容易出现。

# 检测模式

## 1. 情节结构重复
最近几章是否在结构上相似?(都是"接受任务→遭遇阻碍→克服→回归")

## 2. 冲突类型重复
最近冲突是否都是同一种?(都是欺骗 / 都是战斗 / 都是误会)

## 3. 角色行为重复
某角色是否反复做相似的事?(每次都用同样方式解决问题)

## 4. 修辞与意象重复
是否过度使用某些句式、比喻、意象? 某些词汇密度过高?

## 5. 场景类型重复
是否反复在相同地点、相同时段、相同关系组合中展开?

# 输出格式(严格 JSON,不要 markdown 代码块)

{
  "overall_novelty_score": 7,
  "detected_patterns": [
    {
      "pattern": "...",
      "occurrences": 4,
      "severity": "low|medium|high",
      "examples": ["..."]
    }
  ],
  "recommendations": [
    "建议下次冲突避开'误会'类型",
    "建议 Narrator 减少使用'...仿佛...'句式"
  ]
}
"""


@dataclass
class NoveltyCriticOutput:
    overall_novelty_score: int = 5
    detected_patterns: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class NoveltyCritic:
    def __init__(self, model_tier: str = "small") -> None:
        self._model_tier = model_tier

    async def critique(
        self,
        *,
        recent_chapters: list[str],
        recent_events: list[Event],
        action_patterns: dict,
    ) -> NoveltyCriticOutput:
        user_prompt = self._build_prompt(
            recent_chapters=recent_chapters,
            recent_events=recent_events,
            action_patterns=action_patterns,
        )
        try:
            resp = await llm_client.chat(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=1024,
            )
        except Exception as e:
            logger.error("NoveltyCritic LLM call failed: %s", e)
            return NoveltyCriticOutput()

        return self._parse_output(resp.content)

    def _build_prompt(
        self,
        *,
        recent_chapters: list[str],
        recent_events: list[Event],
        action_patterns: dict,
    ) -> str:
        recent_evt_lite = [
            {"type": e.type, "desc": e.description[:60], "participants": e.participants}
            for e in recent_events[-50:]
        ]
        return f"""\
# 最近 30 章摘要

{chr(10).join(f'  - {s}' for s in recent_chapters[-30:]) or '  (尚无)'}

# 最近 50 事件

```json
{json.dumps(recent_evt_lite, ensure_ascii=False, indent=2)}
```

# 角色行动模式统计 (TickDB 提供)

```json
{json.dumps(action_patterns, ensure_ascii=False, indent=2)}
```

请按 system 提示输出严格 JSON。recommendations 数组每条不超过 50 字。
"""

    def _parse_output(self, raw: str) -> NoveltyCriticOutput:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("NoveltyCritic JSON parse failed: %s — first 200: %s", e, text[:200])
            return NoveltyCriticOutput()

        return NoveltyCriticOutput(
            overall_novelty_score=int(payload.get("overall_novelty_score", 5)),
            detected_patterns=list(payload.get("detected_patterns", []) or []),
            recommendations=list(payload.get("recommendations", []) or []),
        )
