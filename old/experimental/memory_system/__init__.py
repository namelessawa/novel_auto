#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Experimental cognitive-science multi-layered memory architecture.

NOT wired into the runtime pipeline. See experimental/__init__.py.

Layers:
1. Working Memory   - short-term active context with TTL + entity attention
2. Episodic Memory  - story events with temporal embeddings + importance weighting
3. Semantic Memory  - knowledge graph for entities/relations + inference
4. Procedural Memory- style patterns and narrative techniques
5. Unified Memory   - integrates the four layers + backward-compat adapter
"""

from .working_memory import (
    WorkingMemory,
    ContextItem,
    EntityAttention,
    WorkingMemoryAdapter,
)
from .episodic_memory import (
    EpisodicMemory,
    Episode,
)
from .semantic_memory import (
    SemanticMemory,
    Entity,
    Relation,
    OntologyNode,
)
from .procedural_memory import (
    ProceduralMemory,
    StylePattern,
    NarrativeTechnique,
    StyleProfile,
)
from .unified_memory import (
    UnifiedMemorySystem,
    MemorySystemAdapter,
)

__all__ = [
    'WorkingMemory',
    'ContextItem',
    'EntityAttention',
    'WorkingMemoryAdapter',
    'EpisodicMemory',
    'Episode',
    'SemanticMemory',
    'Entity',
    'Relation',
    'OntologyNode',
    'ProceduralMemory',
    'StylePattern',
    'NarrativeTechnique',
    'StyleProfile',
    'UnifiedMemorySystem',
    'MemorySystemAdapter',
]
