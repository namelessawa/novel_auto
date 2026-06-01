#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plot Engine Module
Active foreshadowing and story arc control for intelligent narrative generation

Modules:
- foreshadowing: Lifecycle management of narrative hints
- story_arc: Multi-threaded story arc controller
"""

from .foreshadowing import (
    ForeshadowingEngine,
    Foreshadowing,
    ForeshadowingType,
    ForeshadowingStatus
)

from .story_arc import (
    StoryArcController,
    StoryThread,
    Conflict,
    ThreadStatus,
    ThreadPriority,
    ArcPhase
)

__all__ = [
    'ForeshadowingEngine',
    'Foreshadowing',
    'ForeshadowingType',
    'ForeshadowingStatus',
    'StoryArcController',
    'StoryThread',
    'Conflict',
    'ThreadStatus',
    'ThreadPriority',
    'ArcPhase'
]
