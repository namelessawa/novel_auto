"""quality_checks — 确定性 (无 LLM) 质量检测。

针对 novel_quality_critique_and_iteration.md 中可机器判定的触发条件:

* A4 — AI 高频套话黑名单命中
* D3 — 陈词滥调命中
* D2 — 形容词连续堆砌 (启发式)
* A1 — 实词同段重复 ≥3 次
* A5 / A7 — 开头句式重复 (需要外部状态)
* A6 — 段末"总结性独白"启发式
* E1 — 句长标准差过低

LLM-based 的语义判定 (B/C/F/G 中的多数项) 留给 NarrativeCritic agent。

设计上区分两类工具:
* check_* 函数 — 输入字符串, 输出 (触发码, 证据片段) 列表
* compute_* 函数 — 输入字符串, 输出统计量 (供 LLM critic 引用)
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from agents.quality_spec import (
    AI_CLICHE_BLACKLIST,
    CLICHE_BLACKLIST,
)


@dataclass(frozen=True)
class DeterministicTrigger:
    code: str
    severity: str
    evidence: str
    location_hint: str = ""  # 如 "段 2 行 3"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "evidence": self.evidence,
            "location_hint": self.location_hint,
        }


# ---------------------------------------------------------------------------
# 黑名单检测
# ---------------------------------------------------------------------------


def check_ai_cliche_blacklist(text: str) -> list[DeterministicTrigger]:
    """A4: 任何一个 AI 套话出现即触发 (高严重度)。

    对于 "缓缓地 / 轻轻地 / 静静地", 需单段内出现 ≥2 次才计 A4
    (规范 §1 附录 1 备注)。
    """
    triggers: list[DeterministicTrigger] = []
    soft_words = {"缓缓地", "轻轻地", "静静地"}
    for word in AI_CLICHE_BLACKLIST:
        cnt = text.count(word)
        if cnt == 0:
            continue
        if word in soft_words:
            # 单段 ≥2 次才触发
            if cnt < 2:
                continue
        # 取首次出现的上下文片段作为证据
        idx = text.find(word)
        evidence = _extract_context(text, idx, len(word), context=24)
        triggers.append(
            DeterministicTrigger(
                code="A4",
                severity="high",
                evidence=f'"{word}" × {cnt}: ...{evidence}...',
            )
        )
    return triggers


def check_cliche_blacklist(text: str) -> list[DeterministicTrigger]:
    """D3: 陈词滥调命中 (中严重度)。"""
    triggers: list[DeterministicTrigger] = []
    for word in CLICHE_BLACKLIST:
        cnt = text.count(word)
        if cnt == 0:
            continue
        idx = text.find(word)
        evidence = _extract_context(text, idx, len(word), context=20)
        triggers.append(
            DeterministicTrigger(
                code="D3",
                severity="medium",
                evidence=f'"{word}" × {cnt}: ...{evidence}...',
            )
        )
    return triggers


# ---------------------------------------------------------------------------
# 形容词堆砌 (D2)
# ---------------------------------------------------------------------------

_ADJECTIVE_RUN_PAT = re.compile(
    r"([一-龥]{1,3}(?:的)?(?:、|,|，)){3,}",
)


def check_adjective_runs(text: str) -> list[DeterministicTrigger]:
    """D2 启发式: 连续 ≥3 个用顿号/逗号分隔的小词修饰同一事物。

    精确判定需要中文 POS 标注; 这里用 顿号/逗号 分隔的短词序列作为近似。
    """
    triggers: list[DeterministicTrigger] = []
    for match in _ADJECTIVE_RUN_PAT.finditer(text):
        evidence = match.group(0)
        # 排除明显是名词列举的情况 (启发式: 后面紧跟动词)
        triggers.append(
            DeterministicTrigger(
                code="D2",
                severity="medium",
                evidence=f"形容词堆砌嫌疑: {evidence}",
            )
        )
    return triggers


# ---------------------------------------------------------------------------
# A1: 同段实词重复 ≥3 次
# ---------------------------------------------------------------------------

# 中文字符片段切分: 按标点和空白拆段, 段内做滑动 2-char 提取
_CJK_SEGMENT_PAT = re.compile(r"[一-龥]+")

# 太常见以致重复无意义的高频词 — 排除
_STOP_NOMINALS: frozenset[str] = frozenset(
    {
        "自己",
        "什么",
        "一个",
        "这个",
        "那个",
        "可以",
        "因为",
        "所以",
        "但是",
        "如果",
        "已经",
        "没有",
        "他们",
        "我们",
        "她们",
        "它们",
        "这样",
        "那样",
        "时候",
        "知道",
        "看到",
        "听到",
        "感到",
        "觉得",
        "可能",
        "应该",
        "需要",
        "之间",
        "之后",
        "之前",
        "现在",
        "今天",
        "一切",
        "所有",
        "一些",
        "这些",
        "那些",
        "起来",
        "下去",
        "出来",
    }
)


def check_word_repetition(text: str, threshold: int = 3) -> list[DeterministicTrigger]:
    """A1: 同段实词重复 ≥threshold 次。

    实词识别策略 (轻量, 无分词器依赖):
    * 按标点/空白把文本切成中文连续片段
    * 每段内取所有 2-char 滑动窗口
    * 排除 _STOP_NOMINALS 中的常用功能词
    * 计数后取出现 ≥threshold 次的词作为触发
    """
    counter: Counter[str] = Counter()
    for segment in _CJK_SEGMENT_PAT.findall(text):
        if len(segment) < 2:
            continue
        for i in range(len(segment) - 1):
            w = segment[i : i + 2]
            if w in _STOP_NOMINALS:
                continue
            counter[w] += 1
    triggers: list[DeterministicTrigger] = []
    for word, cnt in counter.most_common(20):
        if cnt < threshold:
            break
        triggers.append(
            DeterministicTrigger(
                code="A1",
                severity="medium",
                evidence=f'实词 "{word}" 出现 {cnt} 次',
            )
        )
    return triggers


# ---------------------------------------------------------------------------
# A6: 段末"总结性独白"启发式
# ---------------------------------------------------------------------------

_SUMMARY_ENDING_PAT = re.compile(
    r"(只剩下|只有|不过是|只是|终归|终究|或许就是|大约就是|"
    r"这就是|这便是|这才是|"
    r"无论如何|纵然|纵使|"
    r"也许从此|从此|此后|此刻|这一刻)"
    r"[一-龥,，、 ]{3,}"
    r"[。…！]?\s*$"
)


def check_summary_ending(text: str) -> list[DeterministicTrigger]:
    """A6/G4: 段末"总结性独白"启发式。

    检测段落最后 ~50 字中是否包含"只剩下 X"/"这就是 Y"/"终究 Z"等
    升华套路。
    """
    tail = text.rstrip()[-80:]
    if _SUMMARY_ENDING_PAT.search(tail):
        return [
            DeterministicTrigger(
                code="A6",
                severity="high",
                evidence=f"段末疑似升华/总结: {tail[-40:].strip()}",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# E1: 句长标准差过低
# ---------------------------------------------------------------------------

_SENT_SPLIT_PAT = re.compile(r"[。!?！？；;]")


def compute_sentence_length_stats(text: str) -> tuple[float, float]:
    """返回 (mean, stddev) 句长 (按中文字符计)。"""
    sents = [s.strip() for s in _SENT_SPLIT_PAT.split(text) if s.strip()]
    if not sents:
        return 0.0, 0.0
    lengths = [len(s) for s in sents]
    mean = sum(lengths) / len(lengths)
    var = sum((x - mean) ** 2 for x in lengths) / len(lengths)
    return mean, var**0.5


def check_sentence_rhythm(text: str) -> list[DeterministicTrigger]:
    """E1: 句长标准差过低 (节奏均匀单调)。

    阈值: 句子数 ≥6 且 stddev / mean < 0.25 → 触发。
    """
    sents = [s for s in _SENT_SPLIT_PAT.split(text) if s.strip()]
    if len(sents) < 6:
        return []
    mean, std = compute_sentence_length_stats(text)
    if mean > 0 and (std / mean) < 0.25:
        return [
            DeterministicTrigger(
                code="E1",
                severity="medium",
                evidence=f"句长均值 {mean:.1f}, 标准差 {std:.1f} (相对 {std/mean:.0%})",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# 开头句式相似性 (A5/A7) — 需要外部状态
# ---------------------------------------------------------------------------


def extract_opening_signature(text: str, n: int = 6) -> str:
    """提取段落开头前 n 字, 用于跟踪最近三段开头句式重复。"""
    stripped = text.lstrip()
    return stripped[:n]


def check_opening_repetition(
    text: str, recent_openings: list[str]
) -> list[DeterministicTrigger]:
    """A5/A7: 当前段开头与最近三段命中任一即触发 (中严重度)。"""
    sig = extract_opening_signature(text)
    if not sig:
        return []
    triggers: list[DeterministicTrigger] = []
    for prev in recent_openings[-3:]:
        if not prev:
            continue
        if sig == prev or (len(prev) >= 4 and prev[:4] == sig[:4]):
            triggers.append(
                DeterministicTrigger(
                    code="A7",
                    severity="medium",
                    evidence=f'本段开头 "{sig}" 命中最近段开头 "{prev}"',
                )
            )
            break
    return triggers


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def run_deterministic_checks(
    text: str,
    *,
    recent_openings: list[str] | None = None,
) -> list[DeterministicTrigger]:
    """跑全部确定性检查, 返回去重后的触发列表。"""
    if not text or not text.strip():
        return []
    out: list[DeterministicTrigger] = []
    out.extend(check_ai_cliche_blacklist(text))
    out.extend(check_cliche_blacklist(text))
    out.extend(check_adjective_runs(text))
    out.extend(check_word_repetition(text))
    out.extend(check_summary_ending(text))
    out.extend(check_sentence_rhythm(text))
    if recent_openings is not None:
        out.extend(check_opening_repetition(text, recent_openings))
    return out


def summarize_triggers(triggers: list[DeterministicTrigger]) -> dict:
    """供 NarrativeCritic / Orchestrator 决策矩阵使用。"""
    high = [t for t in triggers if t.severity == "high"]
    medium = [t for t in triggers if t.severity == "medium"]
    return {
        "high_count": len(high),
        "medium_count": len(medium),
        "high_codes": sorted({t.code for t in high}),
        "medium_codes": sorted({t.code for t in medium}),
        "evidence": [t.to_dict() for t in triggers],
    }


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _extract_context(text: str, start: int, length: int, context: int = 20) -> str:
    """从命中点向两边截取上下文片段, 转义换行。"""
    lo = max(0, start - context)
    hi = min(len(text), start + length + context)
    return text[lo:hi].replace("\n", " ")


__all__ = [
    "DeterministicTrigger",
    "check_ai_cliche_blacklist",
    "check_cliche_blacklist",
    "check_adjective_runs",
    "check_word_repetition",
    "check_summary_ending",
    "check_sentence_rhythm",
    "check_opening_repetition",
    "extract_opening_signature",
    "compute_sentence_length_stats",
    "run_deterministic_checks",
    "summarize_triggers",
]
