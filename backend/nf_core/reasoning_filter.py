"""Reasoning trace 反泄漏 — 共享给 NarratorAgent 与 SectionCloser。

> Reasoning 模型 (MiMo / DeepSeek-Reasoner) 偶尔把 chain-of-thought 写进
> ``content`` 字段, 接在正文末尾或前面。这些短语只会出现在 meta-思考里,
> 不会进入真正的小说正文。命中即从该位置砍掉后续, 调用方加 consistency
> flag 报警。

历史: 原实现在 ``agents/narrator_agent.py``, v2.34 commit 365dac7 引入。
SectionCloser 的补叙路径漏掉了同样的清洗 — 用户看到 supplement 末尾
出现 "首先, 用户提供了..." 一整段 reasoning 复述。此模块提取共享逻辑
并补充 marker, 确保所有 narrative 写入路径都过反泄漏闸。
"""

from __future__ import annotations

import re

REASONING_LEAK_MARKERS: tuple[str, ...] = (
    "首先,理解任务",
    "首先,理解一下",
    "首先,我需要",
    "首先,分析",
    "首先,让我",
    "首先,要分析",
    "首先,我来分析",
    "首先,我要",
    "首先,确认",
    "首先,这是",
    "首先,用户",
    "首先,作品",
    "首先,这段",
    "首先,我们",
    "首先,这个",
    "从tick摘要",
    "从tick 摘要",
    "关键点包括",
    "tick摘要",
    "好的,以下是",
    "好的,我来",
    "好的,让我",
    "好的,首先",
    "让我先",
    "让我来",
    "我应该",
    "我需要为",
    "我需要写",
    "我需要先",
    "我的任务是",
    "我的任务",
    "用户提供了",
    "用户提供的",
    "用户要求",
    "用户给出",
    "需要快速带过",
    "需要写一段",
    "要求包括",
    "要求如下",
    "因此,我",
    "考虑到这些",
    "考虑到上述",
    "现在,我开始",
    "现在开始写",
    "**思考过程**",
    "**分析过程**",
    "**任务理解**",
)


def _normalise_punct(s: str) -> str:
    """全 → 半角逗号, 仅做匹配用; 不改原文。"""
    return s.replace("，", ",")


_PATTERN = re.compile(
    "(" + "|".join(re.escape(_normalise_punct(m)) for m in REASONING_LEAK_MARKERS) + ")"
)


def strip_reasoning_leak(text: str) -> tuple[str, bool]:
    """从 narrative 文本砍掉 reasoning prologue/epilogue 泄漏。

    策略: 标准化全角逗号为半角后, 在文本里找第一个 reasoning marker 命中点。
    命中位置位于一个段落开头 (前面是 ``\\n\\n`` 或位于文本开头) 才算泄漏,
    避免把"首先"这种合法散文起始词误伤。

    返回 ``(clean_text, leaked)`` — leaked=True 时调用方应加 consistency
    flag 或视情况退化输出。
    """
    if not text:
        return text, False
    norm = _normalise_punct(text)
    m = _PATTERN.search(norm)
    if not m:
        return text, False
    pos = m.start()
    # 段落起点 = 文本开头 / 前两个字符是 \n\n
    at_para_start = pos == 0 or norm[max(0, pos - 2) : pos] == "\n\n"
    if not at_para_start:
        return text, False
    clean = text[:pos].rstrip()
    return clean, True
