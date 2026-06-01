#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory System Module (active runtime memory)

These are the five memory modules actually wired into ``NovelGenerator``
(see ``core_generator.py``):

- Sliding Window      (sliding_window.py)        token-based short-term context
- Entity State        (entity_state.py)          global state machine + snapshots
- Hierarchical Summary(hierarchical_summary.py)  three-level summaries
- Long-Term Memory    (long_term_memory.py)      ChromaDB RAG event store
- Character Relationship (character_relationship.py) relationship graph

The cognitive-science four-layer rewrite (working / episodic / semantic /
procedural / unified memory) is unintegrated and now lives under
``experimental/memory_system/``. Import it explicitly from there if needed.
"""

from .sliding_window import SlidingWindowMemory
from .entity_state import EntityStateTracker
from .hierarchical_summary import HierarchicalSummarizer
from .long_term_memory import LongTermEventMemory
from .character_relationship import CharacterRelationshipGraph

__all__ = [
    'SlidingWindowMemory',
    'EntityStateTracker',
    'HierarchicalSummarizer',
    'LongTermEventMemory',
    'CharacterRelationshipGraph',
]
