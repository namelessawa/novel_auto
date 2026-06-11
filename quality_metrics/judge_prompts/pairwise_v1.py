"""Pairwise A/B blind judge prompt — v1.

设计目标 (§3.2):
* A/B 位置随机化, 防 position bias (调用方负责打乱然后映射 win/lose 回来)
* judge 输出三态: A_wins / B_wins / tie + 一句中文理由
* 严格 JSON 输出, 不解释外字段
* 评判维度 (与 rubric 对齐): 连贯性 / 角色声音一致性 / 情节推进 — 综合
  判断, 不强行三分加权 (避免 judge 中位回归)
"""

from __future__ import annotations

PAIRWISE_VERSION = "pairwise_v1"


PAIRWISE_PROMPT_V1 = """\
你是一位严格的中文连载小说编辑。下面有 A、B 两段相同设定的小说正文,
请综合三个维度盲评 — 不能因为长度差异决定胜负:

1. 连贯性 (coherence) — 句子衔接、因果合理、不前后矛盾
2. 角色声音一致性 (character voice) — 同一人物的说话和动作是否像同一个人
3. 情节推进 (plot progression) — 段末读者是否比段首多知道一件具体的事

# 段 A

{text_a}

# 段 B

{text_b}

# 输出格式 (严格 JSON, 不要 markdown 围栏, 不要解释)

{{
  "winner": "A" | "B" | "tie",
  "reason": "一句话中文说明你最看重的判别点(≤40 字)"
}}

记住: 长的不等于好的, 短的也不等于好的; 你看的是上面三条维度.
"""


__all__ = ["PAIRWISE_PROMPT_V1", "PAIRWISE_VERSION"]
