#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Experimental (next-generation) subsystems — NOT wired into the runtime pipeline.

These modules are a designed-but-unintegrated rewrite of the novel-generation
engine. They are imported by **nothing** in the live pipeline (`core/generator.py`
and friends). They are kept here, clearly quarantined, so the working system's
import surface stays small and so the project's true integration status is honest.

Contents:
- experimental/memory_system/  Cognitive-science four-layer memory
                               (working / episodic / semantic / procedural / unified)
- experimental/plot_engine/    Foreshadowing lifecycle + multi-thread story arcs
- experimental/evaluation/     Iterative refinement + context-integrity assembly
- experimental/core/           Event bus / plugin manager / multi-LLM scheduler

To actually use any of these, import from the `experimental.*` namespace and wire
it into `NovelGenerator`. See docs/ and PROGRESS_SUMMARY.md for the migration plan.

Importing this package does NOT import the submodules (they may pull heavy optional
deps); import the specific subpackage you need explicitly.
"""

__all__ = []
