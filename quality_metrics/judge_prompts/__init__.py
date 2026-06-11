"""Versioned judge prompts.

Each prompt is its own immutable string constant with a version suffix.
When a prompt is reworked the version bumps and the old one is kept; the
judge runner writes the resolved version into the bench artifact metadata
so historical results stay interpretable.

iter#79 ships v1 of both prompts (pairwise + rubric).
"""

from __future__ import annotations

from quality_metrics.judge_prompts.pairwise_v1 import (
    PAIRWISE_PROMPT_V1,
    PAIRWISE_VERSION,
)
from quality_metrics.judge_prompts.rubric_v1 import (
    RUBRIC_PROMPT_V1,
    RUBRIC_VERSION,
)

__all__ = [
    "PAIRWISE_PROMPT_V1",
    "PAIRWISE_VERSION",
    "RUBRIC_PROMPT_V1",
    "RUBRIC_VERSION",
]
