"""Phase 6 iter#UU — D5 single-sense paragraph det (lite).

> Aligns with `docs/design/novel_quality_critique_and_iteration.md`:
>
> | code | trigger |
> | --- | --- |
> | D5   | 整段只有视觉描写, 缺另一种感官 (medium) |

iter#C3 时代 quality_checks 注释列了 D5 但没实现. 本 iter 补.

## Strategy

5 个感官 category 关键词, 段落内统计每类出现次数. 触发条件:

* 视觉关键词 count ≥ 5 (足够多, 才算"主导")
* 同时其余 4 类全 0 (听 / 嗅 / 触 / 味 — 心理在 B4 处理, 不算感官)
* 文本 ≥ 200 字 (短段落统计不稳定, 与 character_signal 同源 baseline)

## Why conservative

D5 应是真正"sterile visual stream", 不能 FP 在普通景色描写. 5 视觉
+ 0 其他 = strong signal. 4 视觉 + 1 触 = 多元, 不触发.

## env knob

* `SENSE_DIVERSITY_ENABLE` (default True)
* `SENSE_DIVERSITY_VISUAL_MIN` (default 5)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# 5 sense categories. 每个 category = 关键词列表. 用 frozenset 加速 in.
_VISUAL_WORDS: frozenset[str] = frozenset({
    "看", "望", "见", "瞥", "盯", "凝视", "注视",
    "影", "光", "色", "亮", "暗", "明", "黑", "白", "红", "黄", "蓝",
    "绿", "灰", "金", "银", "紫", "深", "浅",
    "形", "状", "圆", "方", "长", "短", "高", "低", "大", "小",
    "闪", "辉", "耀", "晃", "映",
})

_AUDIO_WORDS: frozenset[str] = frozenset({
    "听", "闻声", "声", "响", "鸣", "嘶", "叫", "喊", "唱", "嗡", "啪",
    "嗒", "哗", "轰", "咚", "咔", "嚓", "簌", "嘎", "哧", "啧",
    # 静/寂/悄 不放 — 与 "平静" 等视觉静止词冲突, 会 FP.
})

_SMELL_WORDS: frozenset[str] = frozenset({
    "闻", "嗅", "味", "气味", "香", "臭", "腥", "酸", "霉", "焦",
    "烟味", "草味", "土味", "血腥",
})

_TOUCH_WORDS: frozenset[str] = frozenset({
    "摸", "碰", "触", "贴", "握", "捏", "按", "压",
    "凉", "暖", "冰", "烫", "热", "冷",
    "涩", "滑", "粗", "糙", "软", "硬",
    "刺", "刺骨", "痒", "麻",
})

_TASTE_WORDS: frozenset[str] = frozenset({
    "尝", "舔", "咬", "嚼", "咽",
    "甜", "苦", "辣", "酸", "咸", "鲜", "腻",
})

# 单字 keyword 用 char-in-text 即可; 双字 keyword 需子串扫.
_CATEGORY_WORDS = {
    "visual": _VISUAL_WORDS,
    "audio": _AUDIO_WORDS,
    "smell": _SMELL_WORDS,
    "touch": _TOUCH_WORDS,
    "taste": _TASTE_WORDS,
}


# Minimum text length to bother running. 100 比 character_signal 的 200
# 略低 — D5 视觉单一信号在中等段落已可判, 不需要超长 baseline.
# 短文本 (silent tick fragment 等) 仍跳过.
_MIN_TEXT_LEN = 100
_DEFAULT_VISUAL_MIN = 5


@dataclass(frozen=True)
class SenseDiversityReport:
    text_length: int
    counts: dict[str, int]
    d5_triggered: bool
    d5_evidence: str

    def to_dict(self) -> dict:
        return {
            "text_length": self.text_length,
            "counts": dict(self.counts),
            "d5": {"triggered": self.d5_triggered, "evidence": self.d5_evidence},
        }


def _count_in(words: frozenset[str], text: str) -> int:
    """Count total occurrences of any word in `words` within `text`."""
    n = 0
    for w in words:
        # 单字 char-count fast path
        if len(w) == 1:
            n += text.count(w)
        else:
            # 多字 — text.count(substring) 已是高效 algorithm
            n += text.count(w)
    return n


def sense_diversity_report(
    text: str,
    *,
    visual_min: int = _DEFAULT_VISUAL_MIN,
) -> SenseDiversityReport:
    """Run D5 single-sense check.

    Trigger: visual count ≥ visual_min AND 其余 4 类全 = 0.
    """
    if not text or len(text.strip()) < _MIN_TEXT_LEN:
        return SenseDiversityReport(
            text_length=len(text or ""),
            counts={},
            d5_triggered=False,
            d5_evidence="",
        )

    counts = {
        cat: _count_in(words, text) for cat, words in _CATEGORY_WORDS.items()
    }
    other_sum = sum(counts[c] for c in ("audio", "smell", "touch", "taste"))
    triggered = counts["visual"] >= visual_min and other_sum == 0
    evidence = ""
    if triggered:
        evidence = (
            f"段落 {len(text)} 字, 视觉关键词 {counts['visual']} 次, "
            f"其他感官 0 次 (听/嗅/触/味). 单一视觉流."
        )
    return SenseDiversityReport(
        text_length=len(text),
        counts=counts,
        d5_triggered=triggered,
        d5_evidence=evidence,
    )


__all__ = [
    "SenseDiversityReport",
    "sense_diversity_report",
]
