"""Phase 6 iter#VV — E2 parallelism (对仗工整) det check.

> Aligns with `docs/design/novel_quality_critique_and_iteration.md`:
>
> | code | trigger |
> | --- | --- |
> | E2   | 句式过分对仗工整 (典型 AI 腔) — high |

## Strategy

最朴素的对仗 = 两 adjacent comma-separated clause **同长度** + **同末字**.
例:
* "风停了, 雨停了" — 4 字两 clause, 末字都是 "了"
* "他笑了, 她笑了" — 同上
* "灯亮起, 夜显形" — 4 字, 不同末字, 不算 (差异即非对仗)

强 trigger 信号: 段内出现 ≥ 3 对相邻同长度同末字 clause, 总相邻 clause
对中 ≥ 30% 是对仗. 这是 AI 写作"诗化"的常见 fingerprint.

## False positives 防御

* 短文本 (< 100 字) skip
* clause 长度 < 3 不进对仗判定 (太短的 "我说, 你听" 也合法)
* 长度 > 12 不进对仗判定 (长 clause 同末字偶然性高, 不是有意对仗)

## env knob

* PARALLELISM_ENABLE (default True)
* PARALLELISM_MIN_PAIRS (default 3): 最少几对相邻对仗才 trigger
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# 切分段: 句末标点 句号 / 感叹号 / 问号 / 分号; 子句标点 顿号 / 逗号.
_SENT_SPLIT = re.compile(r"[。！？；!?;.]+")
_CLAUSE_SPLIT = re.compile(r"[，,、]+")

# 60 chars — E2 对仗工整 segment 可在短段中出现 (AI 腔). 比 D5 (100) 低.
_MIN_TEXT_LEN = 60
_MIN_CLAUSE_LEN = 3
_MAX_CLAUSE_LEN = 12
_DEFAULT_MIN_PAIRS = 3


@dataclass(frozen=True)
class ParallelismReport:
    text_length: int
    total_clause_pairs: int
    parallel_pairs: int
    parallel_ratio: float
    e2_triggered: bool
    e2_evidence: str

    def to_dict(self) -> dict:
        return {
            "text_length": self.text_length,
            "total_clause_pairs": self.total_clause_pairs,
            "parallel_pairs": self.parallel_pairs,
            "parallel_ratio": self.parallel_ratio,
            "e2": {"triggered": self.e2_triggered, "evidence": self.e2_evidence},
        }


def _is_parallel(c1: str, c2: str) -> bool:
    """Are two clauses parallel?

    定义:
    * 长度差 ≤ 1 (允许 4-5 字组合)
    * 长度都在 [_MIN_CLAUSE_LEN, _MAX_CLAUSE_LEN]
    * 同末字 (强 anchor — AI 喜欢 '了' / '在' / '中' / '里' 重复)
    """
    if len(c1) < _MIN_CLAUSE_LEN or len(c1) > _MAX_CLAUSE_LEN:
        return False
    if len(c2) < _MIN_CLAUSE_LEN or len(c2) > _MAX_CLAUSE_LEN:
        return False
    if abs(len(c1) - len(c2)) > 1:
        return False
    return c1[-1] == c2[-1]


def parallelism_report(
    text: str,
    *,
    min_pairs: int = _DEFAULT_MIN_PAIRS,
) -> ParallelismReport:
    """Run E2 parallelism det."""
    if not text or len(text.strip()) < _MIN_TEXT_LEN:
        return ParallelismReport(
            text_length=len(text or ""),
            total_clause_pairs=0,
            parallel_pairs=0,
            parallel_ratio=0.0,
            e2_triggered=False,
            e2_evidence="",
        )

    parallel_pairs = 0
    total_pairs = 0
    samples: list[str] = []
    # Split into sentences first, then per-sentence clauses.
    for sent in _SENT_SPLIT.split(text):
        sent = sent.strip()
        if not sent:
            continue
        clauses = [c.strip() for c in _CLAUSE_SPLIT.split(sent) if c.strip()]
        if len(clauses) < 2:
            continue
        for i in range(len(clauses) - 1):
            total_pairs += 1
            if _is_parallel(clauses[i], clauses[i + 1]):
                parallel_pairs += 1
                if len(samples) < 3:
                    samples.append(f"'{clauses[i]}, {clauses[i + 1]}'")

    ratio = parallel_pairs / total_pairs if total_pairs > 0 else 0.0
    triggered = parallel_pairs >= min_pairs and ratio >= 0.3
    evidence = ""
    if triggered:
        evidence = (
            f"{parallel_pairs}/{total_pairs} 相邻 clause 对仗 "
            f"({int(ratio * 100)}%). 样例: " + " | ".join(samples)
        )
    return ParallelismReport(
        text_length=len(text),
        total_clause_pairs=total_pairs,
        parallel_pairs=parallel_pairs,
        parallel_ratio=ratio,
        e2_triggered=triggered,
        e2_evidence=evidence,
    )


__all__ = [
    "ParallelismReport",
    "parallelism_report",
]
