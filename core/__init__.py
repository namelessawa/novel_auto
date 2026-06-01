#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core runtime engine for the novel-generation pipeline.

This package houses the live orchestrator and the services it depends on
(everything that used to live at the project root as standalone .py files):

- generator.py          NovelGenerator — the main orchestrator
- llm_client.py         LLMClient — OpenAI SDK wrapper for DeepSeek
- chapter_analyzer.py   ChapterAnalyzer — LLM-driven entity/event extraction
- background_task.py    ChapterPostProcessor — async post-processing
- embedding_service.py  EmbeddingService — sentence-transformers embeddings
- config.py             centralized configuration (env-var driven)

Note: ``experimental/core/`` (event_bus / plugin_manager / llm_scheduler) is
a *different* package — it is the quarantined plugin-architecture rewrite
and is not imported by the runtime.
"""

from .generator import NovelGenerator
from .llm_client import LLMClient
from .chapter_analyzer import ChapterAnalyzer, apply_analysis_to_memory
from .background_task import ChapterPostProcessor
from .embedding_service import EmbeddingService
from . import novel_manager

__all__ = [
    "NovelGenerator",
    "LLMClient",
    "ChapterAnalyzer",
    "apply_analysis_to_memory",
    "ChapterPostProcessor",
    "EmbeddingService",
    "novel_manager",
]
