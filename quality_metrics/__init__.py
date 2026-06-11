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

from quality_metrics.consistency import (
    CharacterFact,
    ConsistencyReport,
    ConsistencyViolation,
    LocationFact,
    WorldSnapshot,
    check_narration_against_snapshot,
    consistency_report,
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
]
