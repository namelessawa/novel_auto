"""Pairwise judge prompt — v2 (iter#82 fix).

v1 ran into mimo (reasoning-style 模型) 完全用散文分析回答而不输出 JSON.
v2 用三招阻断推理冲动:
1. 把"JSON-only"放在指令最显眼位置 (开头 + 重复 + 结尾)
2. 明确告诉模型"禁止分析" 而非"输出 JSON"
3. 给出极短示例 + 输出长度上限 (≤80 字符)
"""

from __future__ import annotations

PAIRWISE_VERSION = "pairwise_v2"


PAIRWISE_PROMPT_V2 = """\
**重要**: 你**只输出 1 行 JSON**, 不做任何分析, 不写思考过程,
不用 markdown 围栏. 整个回复 ≤80 字符. 违反则视为废答.

格式严格如下 (winner 必须是 A / B / tie 之一):

{{"winner": "A", "reason": "≤30字"}}

# 评判标准 (心里想, 不写出来)
连贯性 + 角色声音 + 情节推进 综合判断. 长度差异不算分.

# 段 A
{text_a}

# 段 B
{text_b}

再次提醒: 只输出 1 行 JSON. 别的一律不要写.
"""


__all__ = ["PAIRWISE_PROMPT_V2", "PAIRWISE_VERSION"]
