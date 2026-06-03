"""LLM 输出预处理工具 (v2.19.6)。

8 个 agent 此前各自实现同一段 markdown fence stripping, 统一到这里:

* 未来 LLM 输出格式变化只需修一处
* 边界 case (语言标签 / 缺闭合 fence / 前后空白) 有集中测试覆盖
* narrative_critic 原有的 _strip_code_fence 也会改成调本 helper

设计原则: 不改变原 7 处实现的语义 — 这是个纯重构, 不引入新行为, 防止潜在的
跨 agent 回归。需要增强的"prose-before-fence"或"自动定位首个 { / [" 等
鲁棒性提升, 在独立轮次中带新测试做。
"""

from __future__ import annotations


def strip_code_fence(text: str) -> str:
    """剥离 LLM 常见的 markdown 围栏。

    行为 (保持与历史 7 处内联实现一致):
    * 先 strip 前后空白
    * 若整体以 ``` 开头 → 去掉第一行 (含可能的 ``json`` / ``yaml`` 语言标签)
    * 末行 strip 后仍以 ``` 开头 → 同时去掉
    * 否则原样返回

    空字符串 / 仅空白安全返回 ``""``。

    NOTE: 此 helper 仅处理整体被 fence 包围的常见 case; 当 LLM 输出 prose +
    fence 混合时仍可能返回未被剥净的内容, 由调用方 ``json.loads`` 失败兜底
    (这是原 7 处的既有行为)。
    """
    t = text.strip()
    if not t:
        return ""
    if t.startswith("```"):
        lines = t.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t


__all__ = ["strip_code_fence"]
