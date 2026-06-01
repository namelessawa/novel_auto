#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluation Module (active runtime evaluator)

``continuity_v2`` is the multi-dimensional continuity scorer wired into
``NovelGenerator`` (see ``core_generator.py``).

The unintegrated iterative-refinement and context-integrity modules now live
under ``experimental/evaluation/``; import them explicitly from there if needed.
"""

from .continuity_v2 import (
    ContinuityDimension,
    ContinuityIssue,
    ContinuityScore,
    EnhancedContinuityEvaluator,
    ContinuityEvaluatorAdapter,
)

__all__ = [
    'ContinuityDimension',
    'ContinuityIssue',
    'ContinuityScore',
    'EnhancedContinuityEvaluator',
    'ContinuityEvaluatorAdapter',
]
