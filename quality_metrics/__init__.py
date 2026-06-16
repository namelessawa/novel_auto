"""Quality metrics for the cost-quality-loop's Phase 2.

Two layers:

* **det layer** (`repetition`, `consistency`, `compliance`) — zero LLM cost,
  runs on every bench. Used as the always-on quality gate.
* **judge layer** (`pairwise`, `rubric`) — LLM-judged samples for the
  semantic dimensions det cannot reach. Budget-capped per §7 of the Phase 2
  directive.

Design contract:

* All metric functions return plain dicts or dataclasses with stable schema.
  Bench tools serialise them straight to JSON without bespoke encoding.
* Det metrics are pure functions of (narrative_text, optional context) —
  reproducible, no I/O, no random state.
* Judge metrics get raw response strings AND structured side-channels for
  audit; the report writer is the place that masks API keys.

iter#76 lands the det `repetition` module + tests. Subsequent iters extend
to `consistency` (iter#77), `compliance` (iter#78), `judge` (iter#79),
bench integration (iter#80).
"""

from __future__ import annotations

from quality_metrics.compliance import (
    ComplianceReport,
    NarrationRecord,
    compliance_report,
)
from quality_metrics.longrange import (
    ForeshadowingCurve,
    MemoryFidelityReport,
    MemoryProbe,
    NoveltyDecayCurve,
    NoveltySample,
    OpenLoopSnapshot,
    foreshadowing_curve,
    memory_fidelity_report,
    novelty_decay_curve,
)
from quality_metrics.judge import (
    JudgeFn,
    JudgeMeta,
    PairwiseResult,
    RubricResult,
    make_active_judge_fn,
    make_ark_glm_judge_fn,
    make_mimo_judge_fn,
    pairwise_judge,
    rubric_judge,
)
from quality_metrics.consistency import (
    CharacterFact,
    ConsistencyReport,
    ConsistencyViolation,
    LocationFact,
    WorldSnapshot,
    check_narration_against_snapshot,
    consistency_report,
)
from quality_metrics.diversity import (
    DiversityReport,
    diversity_report,
    mattr,
    sentence_length_stats,
    type_token_ratio_char,
    type_token_ratio_word,
)
from quality_metrics.repetition import (
    RepetitionReport,
    char_ngram_distinct,
    char_ngram_overlap,
    repetition_report,
    word_ngram_distinct,
    word_ngram_overlap,
)

__all__ = [
    # diversity (Phase 3-C, iter#116)
    "DiversityReport",
    "diversity_report",
    "mattr",
    "sentence_length_stats",
    "type_token_ratio_char",
    "type_token_ratio_word",
    # repetition
    "RepetitionReport",
    "char_ngram_distinct",
    "char_ngram_overlap",
    "repetition_report",
    "word_ngram_distinct",
    "word_ngram_overlap",
    # consistency
    "CharacterFact",
    "ConsistencyReport",
    "ConsistencyViolation",
    "LocationFact",
    "WorldSnapshot",
    "check_narration_against_snapshot",
    "consistency_report",
    # compliance
    "ComplianceReport",
    "NarrationRecord",
    "compliance_report",
    # judge
    "JudgeFn",
    "JudgeMeta",
    "PairwiseResult",
    "RubricResult",
    "make_active_judge_fn",
    "make_ark_glm_judge_fn",
    "make_mimo_judge_fn",
    "pairwise_judge",
    "rubric_judge",
    # longrange
    "OpenLoopSnapshot",
    "ForeshadowingCurve",
    "foreshadowing_curve",
    "NoveltySample",
    "NoveltyDecayCurve",
    "novelty_decay_curve",
    "MemoryProbe",
    "MemoryFidelityReport",
    "memory_fidelity_report",
]
