"""Shared data contracts for the backend tick engine.

After the v2.x consolidation only ``memory_system/models.py`` remains here
— it holds the Pydantic v2 tick contracts (``TickState``, ``CharacterState``,
``Event``, ``OpenLoop``, ``WorldState`` …) that ``backend/`` imports
directly.

All v1.x memory modules (sliding window / entity state / hierarchical
summary / long-term memory / character relationship / knowledge graph
duplicate) live in ``old/memory_system/``. The active tick-era memory
implementations now live under ``backend/memory/`` and ``backend/graph/``.
"""

from . import models

__all__ = ["models"]
