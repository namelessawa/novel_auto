#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core Module
Plugin-based architecture for extensibility and multi-LLM coordination

This module implements Phase 4 of the next-generation AI novel system:
- Event bus for decoupled communication
- Plugin manager for extensibility
- LLM scheduler for multi-provider coordination

Components:
- event_bus: Publish-subscribe event system
- plugin_manager: Plugin lifecycle management
- llm_scheduler: Multi-LLM scheduling and coordination
"""

from .event_bus import (
    EventType,
    Event,
    Subscription,
    EventBus,
    get_event_bus,
    reset_event_bus
)

from .plugin_manager import (
    PluginState,
    PluginPriority,
    PluginInfo,
    PluginBase,
    MemoryPluginBase,
    GeneratorPluginBase,
    EvaluatorPluginBase,
    PluginManager
)

from .llm_scheduler import (
    ProviderType,
    TaskPriority,
    TaskType,
    ProviderConfig,
    LLMMetrics,
    ScheduledTask,
    TaskResult,
    LLMScheduler,
    get_scheduler,
    init_scheduler
)

__all__ = [
    # Event bus
    'EventType',
    'Event',
    'Subscription',
    'EventBus',
    'get_event_bus',
    'reset_event_bus',

    # Plugin manager
    'PluginState',
    'PluginPriority',
    'PluginInfo',
    'PluginBase',
    'MemoryPluginBase',
    'GeneratorPluginBase',
    'EvaluatorPluginBase',
    'PluginManager',

    # LLM scheduler
    'ProviderType',
    'TaskPriority',
    'TaskType',
    'ProviderConfig',
    'LLMMetrics',
    'ScheduledTask',
    'TaskResult',
    'LLMScheduler',
    'get_scheduler',
    'init_scheduler'
]
