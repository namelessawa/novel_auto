"""Phase 6-C first slice — prose dynamics det checks (E1 + D6 lite).

> Aligns with `docs/design/novel_quality_critique_and_iteration.md`:
>
> | code | trigger |
> | --- | --- |
> | E1 | 句子长度分布过于均匀 (标准差小), 缺乏节奏 |
> | D6 | 描述全是抽象 (美丽 / 宏伟 / 古老), 无可视化具体物 |
>
> These two are mechanical (countable) — perfect for det layer. The harder ones
> (B 角色失真 / C 情节 / G AI-pattern) need semantic LLM critic and stay there.
>
> Why E1 + D6 first:
> - E1 has objective ground truth (std-dev math). Lowest false-positive risk.
> - D6 has a cheap heuristic: ratio of abstract adjectives (定义明确的字符级
>   词表) vs concrete nouns. Imperfect but actionable.
>
> Output: structured ProseDynamicsReport, ready to fold into
> narrative_critic det layer in a separate change.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

# Chinese sentence-ending punctuation (incl. ellipsis as one boundary).
_SENT_END = "。!?!?…"
_SENT_END_RE = re.compile(f"[{_SENT_END}]+")

# Abstract adjectives commonly flagged by D6 in Chinese long-form fiction.
# Not exhaustive — the heuristic is "are these EVERYWHERE without a concrete
# noun nearby?". Adding rare words yields more false positives without
# catching the common offenders.
_ABSTRACT_ADJECTIVES = frozenset(
    [
        "美丽", "宏伟", "古老", "神秘", "深邃", "璀璨", "辉煌", "灿烂",
        "壮丽", "庄严", "宁静", "祥和", "凄美", "凄凉", "孤寂", "悲壮",
        "巍峨", "雄伟", "苍茫", "苍凉", "浩瀚", "无垠", "永恒", "亘古",
        "瑰丽", "斑斓", "迷离", "缥缈", "悠远", "悠长", "幽深", "隽永",
    ]
)

# Concrete noun seed list — things a camera can actually photograph. Used
# as a *signal* not a whitelist: presence indicates D6 risk is lower.
_CONCRETE_NOUNS = frozenset(
    [
        # 身体 / 动作
        "手", "脸", "眼", "嘴", "肩", "膝", "腰", "脚", "指", "腕",
        "头", "眉", "唇", "齿", "舌", "颈", "胸", "背", "肘", "拳",
        # 物件 / 器物
        "刀", "剑", "杯", "碗", "灯", "门", "窗", "桌", "椅", "床",
        "袖", "袍", "鞋", "笔", "纸", "墨", "钱", "钥匙", "镜", "瓶",
        # 自然 / 物质
        "雪", "雨", "风", "云", "石", "树", "草", "木", "水", "火",
        "血", "汗", "泥", "沙", "灰", "土", "铁", "铜", "玉", "丝",
    ]
)


def split_sentences(text: str) -> list[str]:
    """Split Chinese prose into sentences, stripping leading/trailing whitespace.

    Empty sentences (caused by consecutive punctuation) are dropped — they
    inflate the count without contributing to rhythm signal.
    """
    if not text:
        return []
    pieces = _SENT_END_RE.split(text)
    return [p.strip() for p in pieces if p.strip()]


def sentence_length_stats(text: str) -> dict[str, float]:
    """Mean / stddev / min / max / count for sentence character length.

    Returns ``{}`` when fewer than 2 sentences (stddev undefined).
    """
    sents = split_sentences(text)
    if len(sents) < 2:
        return {}
    lengths = [len(s) for s in sents]
    return {
        "count": float(len(sents)),
        "mean": round(statistics.mean(lengths), 2),
        "stddev": round(statistics.stdev(lengths), 2),
        "min": float(min(lengths)),
        "max": float(max(lengths)),
    }


def e1_rhythm_check(text: str, min_stddev: float = 6.0) -> tuple[bool, str]:
    """E1: 句长分布过于均匀.

    Triggers when stddev of sentence length < ``min_stddev`` AND at least 5
    sentences are present (avoids false positives on short paragraphs).

    Returns ``(triggered, evidence_summary)``.
    The 6.0 default came from inspecting Phase 5-J 200tick narratives: healthy
    prose had stddev 8-15, AI-flat samples landed at 3-5. 6.0 is the gap.
    """
    s = sentence_length_stats(text)
    if not s or s["count"] < 5:
        return False, ""
    stddev = s["stddev"]
    if stddev < min_stddev:
        return True, (
            f"stddev={stddev:.1f} < {min_stddev:.1f} threshold "
            f"(n={int(s['count'])} sentences, mean={s['mean']:.1f}, "
            f"min={int(s['min'])}, max={int(s['max'])})"
        )
    return False, ""


def d6_abstraction_check(
    text: str, min_abstract_ratio: float = 0.5
) -> tuple[bool, str]:
    """D6 (lite): abstract adjectives over-represented vs concrete nouns.

    Heuristic: count occurrences of each set. If abstract count > 0 AND
    ``abstract / (abstract + concrete) >= min_abstract_ratio``, trigger.

    NOT a full D6 detector (a real one would parse syntactic role + check
    proximity to nouns). This catches the obvious "everything is 宏伟/古老
    none of it is a hand or a knife" case. Suitable for det layer
    cheap-pass; harder cases stay with LLM critic.
    """
    if not text:
        return False, ""
    abstract_count = sum(text.count(w) for w in _ABSTRACT_ADJECTIVES)
    concrete_count = sum(text.count(w) for w in _CONCRETE_NOUNS)
    total = abstract_count + concrete_count
    if total == 0:
        return False, ""
    ratio = abstract_count / total
    if abstract_count > 0 and ratio >= min_abstract_ratio:
        # List top 3 offending abstract words to make the trigger actionable.
        hits = sorted(
            ((w, text.count(w)) for w in _ABSTRACT_ADJECTIVES if text.count(w) > 0),
            key=lambda kv: -kv[1],
        )[:3]
        evidence = ", ".join(f"{w}×{c}" for w, c in hits)
        return True, (
            f"abstract:concrete = {abstract_count}:{concrete_count} "
            f"(ratio={ratio:.2f} ≥ {min_abstract_ratio:.2f}). "
            f"Top hits: {evidence}"
        )
    return False, ""


@dataclass(frozen=True)
class ProseDynamicsReport:
    """All prose dynamics dim findings for a single narrative chunk."""

    text_length: int
    sentence_stats: dict[str, float]
    e1_triggered: bool
    e1_evidence: str
    d6_triggered: bool
    d6_evidence: str
    surviving_triggers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text_length": self.text_length,
            "sentence_stats": self.sentence_stats,
            "e1": {"triggered": self.e1_triggered, "evidence": self.e1_evidence},
            "d6": {"triggered": self.d6_triggered, "evidence": self.d6_evidence},
            "surviving_triggers": self.surviving_triggers,
        }


def prose_dynamics_report(
    text: str,
    *,
    e1_min_stddev: float = 6.0,
    d6_min_abstract_ratio: float = 0.5,
) -> ProseDynamicsReport:
    """Run E1 + D6 on a narrative chunk, return combined report.

    Empty / very short chunks return a no-trigger report — det layer should
    short-circuit on len(text) < ~100 before this runs (covered by existing
    `_CRITIC_MIN_NARRATIVE_LEN` env knob in critic).
    """
    stats = sentence_length_stats(text)
    e1_trig, e1_ev = e1_rhythm_check(text, min_stddev=e1_min_stddev)
    d6_trig, d6_ev = d6_abstraction_check(text, min_abstract_ratio=d6_min_abstract_ratio)
    surviving = []
    if e1_trig:
        surviving.append("E1")
    if d6_trig:
        surviving.append("D6")
    return ProseDynamicsReport(
        text_length=len(text),
        sentence_stats=stats,
        e1_triggered=e1_trig,
        e1_evidence=e1_ev,
        d6_triggered=d6_trig,
        d6_evidence=d6_ev,
        surviving_triggers=surviving,
    )
