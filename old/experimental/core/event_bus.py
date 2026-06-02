#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event Bus System
Decoupled event-driven communication for plugin architecture

This module provides a publish-subscribe event bus that enables:
- Loose coupling between system components
- Plugin intercommunication
- Lifecycle event propagation
- Asynchronous event processing

Features:
- Topic-based subscriptions
- Priority-based event handling
- Event filtering
- Async event dispatch
- Event history for debugging
"""

import os
import json
import asyncio
import threading
from typing import List, Dict, Callable, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor


class EventType(Enum):
    """System event types"""
    # Generation lifecycle
    BEFORE_GENERATE = "before_generate"
    AFTER_GENERATE = "after_generate"
    ON_GENERATE_ERROR = "on_generate_error"

    # Chapter lifecycle
    BEFORE_CHAPTER = "before_chapter"
    AFTER_CHAPTER = "after_chapter"
    CHAPTER_ANALYZED = "chapter_analyzed"

    # Memory events
    MEMORY_UPDATED = "memory_updated"
    ENTITY_CREATED = "entity_created"
    ENTITY_UPDATED = "entity_updated"
    RELATIONSHIP_CREATED = "relationship_created"
    EVENT_STORED = "event_stored"

    # Plot events
    FORESHADOWING_PLANTED = "foreshadowing_planted"
    FORESHADOWING_RESOLVED = "foreshadowing_resolved"
    THREAD_CREATED = "thread_created"
    THREAD_ADVANCED = "thread_advanced"
    CONFLICT_ESCALATED = "conflict_escalated"

    # Evaluation events
    BEFORE_EVALUATION = "before_evaluation"
    AFTER_EVALUATION = "after_evaluation"
    CONTINUITY_ISSUE = "continuity_issue"
    REFINEMENT_STARTED = "refinement_started"
    REFINEMENT_COMPLETED = "refinement_completed"

    # System events
    PLUGIN_LOADED = "plugin_loaded"
    PLUGIN_UNLOADED = "plugin_unloaded"
    CONFIG_CHANGED = "config_changed"
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"


@dataclass
class Event:
    """Represents a system event"""
    event_type: EventType
    data: Dict[str, Any]
    source: str = "system"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    priority: int = 0  # Higher = more important
    propagate: bool = True  # Whether to continue propagation

    def to_dict(self) -> Dict:
        return {
            "event_type": self.event_type.value,
            "data": self.data,
            "source": self.source,
            "timestamp": self.timestamp,
            "priority": self.priority,
            "propagate": self.propagate
        }


@dataclass
class Subscription:
    """Represents an event subscription"""
    handler: Callable[[Event], None]
    topic: EventType
    priority: int = 0  # Handler execution priority (lower = earlier)
    filter_func: Optional[Callable[[Event], bool]] = None
    subscriber_id: str = ""
    once: bool = False  # Auto-unsubscribe after first match


class EventBus:
    """
    Central event bus for system-wide communication

    Provides a decoupled way for components to communicate
    through publish-subscribe pattern.
    """

    def __init__(self, max_history: int = 100, async_enabled: bool = True):
        """
        Initialize event bus

        Args:
            max_history: Maximum events to keep in history
            async_enabled: Enable async event dispatch
        """
        self._subscriptions: Dict[EventType, List[Subscription]] = defaultdict(list)
        self._event_history: List[Event] = []
        self._max_history = max_history
        self._async_enabled = async_enabled
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4) if async_enabled else None
        self._subscriber_counter = 0

        # Statistics
        self._stats = {
            "events_published": 0,
            "events_handled": 0,
            "handlers_invoked": 0
        }

    def subscribe(
        self,
        topic: EventType,
        handler: Callable[[Event], None],
        priority: int = 0,
        filter_func: Optional[Callable[[Event], bool]] = None,
        once: bool = False
    ) -> str:
        """
        Subscribe to an event topic

        Args:
            topic: Event type to subscribe to
            handler: Function to call when event is published
            priority: Handler execution priority (lower = earlier)
            filter_func: Optional filter function
            once: Auto-unsubscribe after first match

        Returns:
            Subscription ID for unsubscribing
        """
        with self._lock:
            self._subscriber_counter += 1
            subscriber_id = f"sub_{self._subscriber_counter}"

            subscription = Subscription(
                handler=handler,
                topic=topic,
                priority=priority,
                filter_func=filter_func,
                subscriber_id=subscriber_id,
                once=once
            )

            self._subscriptions[topic].append(subscription)

            # Sort by priority
            self._subscriptions[topic].sort(key=lambda s: s.priority)

            return subscriber_id

    def unsubscribe(self, subscriber_id: str) -> bool:
        """
        Unsubscribe from events

        Args:
            subscriber_id: ID returned from subscribe()

        Returns:
            True if subscription was found and removed
        """
        with self._lock:
            for topic in self._subscriptions:
                for i, sub in enumerate(self._subscriptions[topic]):
                    if sub.subscriber_id == subscriber_id:
                        self._subscriptions[topic].pop(i)
                        return True
            return False

    def publish(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source: str = "system",
        priority: int = 0
    ) -> Event:
        """
        Publish an event to all subscribers

        Args:
            event_type: Type of event
            data: Event data
            source: Source identifier
            priority: Event priority

        Returns:
            The published event
        """
        event = Event(
            event_type=event_type,
            data=data,
            source=source,
            priority=priority
        )

        with self._lock:
            self._stats["events_published"] += 1

            # Add to history
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)

            # Get subscriptions for this event type
            subscriptions = self._subscriptions.get(event_type, []).copy()

        # Process subscriptions
        to_remove = []
        for sub in subscriptions:
            # Apply filter if present
            if sub.filter_func and not sub.filter_func(event):
                continue

            # Check if propagation stopped
            if not event.propagate:
                break

            # Execute handler
            try:
                if self._async_enabled and self._executor:
                    self._executor.submit(self._execute_handler, sub.handler, event)
                else:
                    sub.handler(event)

                self._stats["handlers_invoked"] += 1

            except Exception as e:
                print(f"Event handler error: {e}")

            # Mark for removal if once
            if sub.once:
                to_remove.append(sub.subscriber_id)

        # Remove once subscriptions
        for sid in to_remove:
            self.unsubscribe(sid)

        self._stats["events_handled"] += 1
        return event

    def _execute_handler(self, handler: Callable, event: Event):
        """Execute handler in thread pool"""
        try:
            handler(event)
        except Exception as e:
            print(f"Async handler error: {e}")

    def publish_sync(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source: str = "system"
    ) -> Event:
        """
        Publish event synchronously (wait for all handlers)

        This ensures all handlers complete before returning.
        """
        event = Event(
            event_type=event_type,
            data=data,
            source=source
        )

        with self._lock:
            subscriptions = self._subscriptions.get(event_type, []).copy()

        for sub in subscriptions:
            if sub.filter_func and not sub.filter_func(event):
                continue
            if not event.propagate:
                break

            try:
                sub.handler(event)
            except Exception as e:
                print(f"Handler error: {e}")

        return event

    def get_history(self, limit: int = 10) -> List[Dict]:
        """Get recent event history"""
        with self._lock:
            events = self._event_history[-limit:]
            return [e.to_dict() for e in events]

    def get_stats(self) -> Dict:
        """Get event bus statistics"""
        with self._lock:
            return {
                **self._stats,
                "subscription_count": sum(
                    len(subs) for subs in self._subscriptions.values()
                ),
                "topic_count": len(self._subscriptions)
            }

    def clear_history(self) -> None:
        """Clear event history"""
        with self._lock:
            self._event_history = []

    def shutdown(self) -> None:
        """Shutdown event bus"""
        if self._executor:
            self._executor.shutdown(wait=True)


# Global event bus instance
_global_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance"""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


def reset_event_bus() -> None:
    """Reset the global event bus (mainly for testing)"""
    global _global_bus
    if _global_bus:
        _global_bus.shutdown()
    _global_bus = None
