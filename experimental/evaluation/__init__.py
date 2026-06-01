#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Experimental evaluation subsystems — NOT wired into the runtime pipeline.

The active continuity scorer lives at `evaluation/continuity_v2.py`. These two
modules are standalone and unintegrated:

- refinement: iterative refinement loop / multi-stage pipeline
- context_integrity: priority-based, token-aware context assembly
"""

from .refinement import (
    RefinementStrategy,
    RefinementStatus,
    RefinementStep,
    RefinementResult,
    IterativeRefinement,
    RefinementPipeline,
)
from .context_integrity import (
    ContextPriority,
    ContentType,
    ContextBlock,
    IntegrityResult,
    ContextIntegrityManager,
    ContextBuilder,
)

__all__ = [
    'RefinementStrategy',
    'RefinementStatus',
    'RefinementStep',
    'RefinementResult',
    'IterativeRefinement',
    'RefinementPipeline',
    'ContextPriority',
    'ContentType',
    'ContextBlock',
    'IntegrityResult',
    'ContextIntegrityManager',
    'ContextBuilder',
]
