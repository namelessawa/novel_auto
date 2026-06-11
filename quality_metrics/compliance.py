"""Compliance metrics — does the narrative respect the contract?

Phase 2 §3.1 (iter#78). 把已有的过滤器与解析兜底"触发"事件转成可度量的
比率, 而非散落在日志里. Surface 4 类:

1. **length tier 命中率** — Narrator 按 score → estimated_length 分档
   (short=300-700 / medium=600-1200 / long=1200-2200). 度量实际产出落在
   指定范围内的比率.
2. **schema violation 率** — narrative_text 字段缺失 / JSON 解析失败 /
   非 JSON 输出兜底命中的比率. 已存 consistency_flags 里有
   `narrator_output_not_json` 等信号, 我们把它聚合.
3. **reasoning leak filter 触发次数** — strip_reasoning_leak 命中
   (consistency_flags 含 `reasoning_leak`).
4. **占位符泄漏检测命中数** — schema placeholder
   (consistency_flags 含 `schema_placeholder_leak`).

This is a **post-hoc** metric: it reads NarratorOutput-shaped dicts (the
caller materialises them from disk or from a bench run). We don't import
NarratorOutput here, just consume the JSON shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


# Length tier ranges. Must match `backend/agents/narrator_agent.py` —
# duplicated here on purpose (this is a metric, not the source of truth).
# A short ratio of "off-spec" means the narrator misses its own contract,
# which is the signal we care about.
_TIER_RANGES: dict[str, tuple[int, int]] = {
    "short": (300, 700),
    "medium": (600, 1200),
    "long": (1200, 2200),
}


@dataclass
class NarrationRecord:
    """A single Narrator output as observed by the bench.

    The contract:
    * ``text`` — what was actually written to disk (post strip / post critic).
    * ``estimated_length`` — Narrator's declared tier ("short" / "medium" /
      "long" / "none"). "none" means Narrator declined to write (sub-threshold);
      we count it separately rather than treat it as a tier miss.
    * ``consistency_flags`` — list of strings the Narrator parser attached.
      Known signals we care about:
      - "narrator_output_not_json" → schema violation (JSON parse fallback)
      - "reasoning_leak" → reasoning_filter stripped a prefix
      - "schema_placeholder_leak" → placeholder copy detection fired
    * ``should_narrate`` — when False, the Narrator deliberately skipped
      (low event score / time-lapse skip). We exclude these from tier hit
      rate (denominator) but count them separately for transparency.
    """

    text: str
    estimated_length: str
    consistency_flags: list[str] = field(default_factory=list)
    should_narrate: bool = True


@dataclass
class ComplianceReport:
    total_records: int = 0
    skipped_records: int = 0  # should_narrate=False
    on_tier_count: int = 0
    off_tier_count: int = 0
    schema_violation_count: int = 0
    reasoning_leak_count: int = 0
    placeholder_leak_count: int = 0
    # Per-tier breakdown for diagnostics
    per_tier: dict[str, dict[str, int]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def evaluated_count(self) -> int:
        """should_narrate=True 的记录数 (length tier 命中率分母)."""
        return self.on_tier_count + self.off_tier_count

    @property
    def tier_hit_rate(self) -> float:
        denom = self.evaluated_count
        return self.on_tier_count / denom if denom else 0.0

    @property
    def schema_violation_rate(self) -> float:
        denom = self.evaluated_count
        return self.schema_violation_count / denom if denom else 0.0

    @property
    def reasoning_leak_rate(self) -> float:
        denom = self.evaluated_count
        return self.reasoning_leak_count / denom if denom else 0.0

    @property
    def placeholder_leak_rate(self) -> float:
        denom = self.evaluated_count
        return self.placeholder_leak_count / denom if denom else 0.0

    def to_dict(self) -> dict:
        return {
            "total_records": self.total_records,
            "skipped_records": self.skipped_records,
            "evaluated_count": self.evaluated_count,
            "tier_hit_count": self.on_tier_count,
            "tier_off_count": self.off_tier_count,
            "tier_hit_rate": round(self.tier_hit_rate, 4),
            "schema_violation_count": self.schema_violation_count,
            "schema_violation_rate": round(self.schema_violation_rate, 4),
            "reasoning_leak_count": self.reasoning_leak_count,
            "reasoning_leak_rate": round(self.reasoning_leak_rate, 4),
            "placeholder_leak_count": self.placeholder_leak_count,
            "placeholder_leak_rate": round(self.placeholder_leak_rate, 4),
            "per_tier": {
                tier: {
                    "hit": stats.get("hit", 0),
                    "off": stats.get("off", 0),
                }
                for tier, stats in sorted(self.per_tier.items())
            },
            "notes": list(self.notes),
        }


def _classify_length(text_len: int, tier: str) -> str:
    """Return 'hit' / 'off' / 'unknown' per spec range."""
    if tier not in _TIER_RANGES:
        return "unknown"
    lo, hi = _TIER_RANGES[tier]
    return "hit" if lo <= text_len <= hi else "off"


def compliance_report(records: Sequence[NarrationRecord]) -> ComplianceReport:
    """Aggregate compliance over a sequence of Narrator records."""
    rep = ComplianceReport(total_records=len(records))
    if not records:
        rep.notes.append("empty_input")
        return rep

    unknown_tier_count = 0
    for rec in records:
        if not rec.should_narrate:
            rep.skipped_records += 1
            continue
        flags = set(rec.consistency_flags or [])
        if "narrator_output_not_json" in flags:
            rep.schema_violation_count += 1
        if "reasoning_leak" in flags:
            rep.reasoning_leak_count += 1
        if "schema_placeholder_leak" in flags:
            rep.placeholder_leak_count += 1

        kind = _classify_length(len(rec.text), rec.estimated_length)
        if kind == "unknown":
            unknown_tier_count += 1
            continue
        tier_stats = rep.per_tier.setdefault(
            rec.estimated_length, {"hit": 0, "off": 0}
        )
        if kind == "hit":
            rep.on_tier_count += 1
            tier_stats["hit"] += 1
        else:
            rep.off_tier_count += 1
            tier_stats["off"] += 1

    if unknown_tier_count:
        rep.notes.append(f"unknown_tier_count={unknown_tier_count}")

    return rep


__all__ = [
    "NarrationRecord",
    "ComplianceReport",
    "compliance_report",
]
