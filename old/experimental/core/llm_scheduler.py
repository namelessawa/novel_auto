#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Scheduler
Multi-LLM scheduling and coordination system

This module provides intelligent scheduling for multiple LLM providers:
- Load balancing across providers
- Fallback handling
- Cost optimization
- Latency optimization
- Rate limit management

Features:
- Multiple provider support
- Priority-based task routing
- Automatic retry with fallback
- Token usage tracking
- Cost-aware scheduling
"""

import os
import json
import time
import asyncio
from typing import List, Dict, Callable, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from collections import defaultdict


class ProviderType(Enum):
    """Supported LLM providers"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    CUSTOM = "custom"


class TaskPriority(Enum):
    """Task priority levels"""
    CRITICAL = 0    # Must succeed (use most reliable)
    HIGH = 1        # Important but can retry
    NORMAL = 2      # Standard priority
    LOW = 3         # Can be delayed or dropped
    BACKGROUND = 4  # Background tasks


class TaskType(Enum):
    """Types of LLM tasks"""
    GENERATION = "generation"        # Content generation
    ANALYSIS = "analysis"            # Content analysis
    EVALUATION = "evaluation"        # Quality evaluation
    SUMMARIZATION = "summarization"  # Summarization
    REFINEMENT = "refinement"        # Content refinement
    EMBEDDING = "embedding"          # Vector embedding


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider"""
    name: str
    provider_type: ProviderType
    api_key: str = ""
    base_url: str = ""
    model_name: str = ""
    max_tokens: int = 8192
    temperature: float = 0.7

    # Rate limits
    requests_per_minute: int = 60
    tokens_per_minute: int = 100000

    # Costs (per 1k tokens)
    input_cost: float = 0.001
    output_cost: float = 0.002

    # Reliability
    reliability_score: float = 0.95  # Historical success rate
    avg_latency_ms: float = 1000

    # Capabilities
    supports_json: bool = True
    supports_streaming: bool = True
    supports_system_prompt: bool = True


@dataclass
class LLMMetrics:
    """Metrics for an LLM provider"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost: float = 0.0
    avg_latency_ms: float = 0.0
    last_request_time: float = 0.0
    current_minute_requests: int = 0
    current_minute_tokens: int = 0
    minute_start_time: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests


@dataclass
class ScheduledTask:
    """A task to be executed by an LLM"""
    task_id: str
    task_type: TaskType
    priority: TaskPriority
    prompt: str
    max_tokens: int = 2048
    temperature: float = 0.7
    json_mode: bool = False
    system_prompt: str = ""
    context: Dict = field(default_factory=dict)
    callback: Optional[Callable] = None
    created_at: float = field(default_factory=time.time)
    attempts: int = 0
    max_attempts: int = 3


@dataclass
class TaskResult:
    """Result of an LLM task"""
    task_id: str
    success: bool
    content: str = ""
    error: str = ""
    provider: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    cost: float = 0.0
    attempts: int = 1


class LLMScheduler:
    """
    Intelligent LLM scheduler for multi-provider coordination

    Handles task routing, load balancing, and fallback management
    across multiple LLM providers.
    """

    def __init__(self, event_bus=None):
        """
        Initialize LLM scheduler

        Args:
            event_bus: Event bus for notifications
        """
        self.event_bus = event_bus
        self._providers: Dict[str, ProviderConfig] = {}
        self._clients: Dict[str, Any] = {}
        self._metrics: Dict[str, LLMMetrics] = defaultdict(LLMMetrics)
        self._task_counter = 0
        self._pending_tasks: List[ScheduledTask] = []

        # Routing configuration
        self._routing_rules: Dict[TaskType, List[str]] = {}
        self._fallback_chains: Dict[str, List[str]] = {}

        # Statistics
        self._stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_cost": 0.0
        }

    def register_provider(
        self,
        config: ProviderConfig,
        client: Optional[Any] = None
    ) -> None:
        """
        Register an LLM provider

        Args:
            config: Provider configuration
            client: Optional pre-configured client
        """
        self._providers[config.name] = config
        if client:
            self._clients[config.name] = client

        # Initialize fallback chain for this provider
        if config.name not in self._fallback_chains:
            self._fallback_chains[config.name] = []

    def get_client(self, provider_name: str) -> Optional[Any]:
        """Get or create client for a provider"""
        if provider_name in self._clients:
            return self._clients[provider_name]

        config = self._providers.get(provider_name)
        if not config:
            return None

        # Create client based on provider type
        try:
            if config.provider_type == ProviderType.DEEPSEEK:
                # Use OpenAI-compatible client
                from core.llm_client import LLMClient
                client = LLMClient(
                    api_key=config.api_key,
                    base_url=config.base_url,
                    model_name=config.model_name,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature
                )
                self._clients[provider_name] = client
                return client

            elif config.provider_type == ProviderType.OPENAI:
                from core.llm_client import LLMClient
                client = LLMClient(
                    api_key=config.api_key,
                    base_url=config.base_url or "https://api.openai.com/v1",
                    model_name=config.model_name,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature
                )
                self._clients[provider_name] = client
                return client

            else:
                # Generic client
                from core.llm_client import LLMClient
                client = LLMClient(
                    api_key=config.api_key,
                    base_url=config.base_url,
                    model_name=config.model_name,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature
                )
                self._clients[provider_name] = client
                return client

        except Exception as e:
            print(f"Error creating client for {provider_name}: {e}")
            return None

    def set_routing_rule(self, task_type: TaskType, providers: List[str]) -> None:
        """
        Set routing rule for a task type

        Args:
            task_type: Type of task
            providers: List of provider names in priority order
        """
        self._routing_rules[task_type] = providers

    def set_fallback_chain(self, provider: str, fallbacks: List[str]) -> None:
        """
        Set fallback chain for a provider

        Args:
            provider: Primary provider name
            fallbacks: List of fallback provider names
        """
        self._fallback_chains[provider] = fallbacks

    def select_provider(
        self,
        task: ScheduledTask
    ) -> Optional[str]:
        """
        Select the best provider for a task

        Args:
            task: Task to be executed

        Returns:
            Provider name or None if no suitable provider
        """
        # Check routing rules first
        if task.task_type in self._routing_rules:
            providers = self._routing_rules[task.task_type]
            for provider in providers:
                if self._is_provider_available(provider):
                    return provider

        # Select based on criteria
        candidates = []
        for name, config in self._providers.items():
            if not self._is_provider_available(name):
                continue

            # Score the provider
            metrics = self._metrics[name]

            # Reliability score
            reliability = config.reliability_score * metrics.success_rate

            # Latency score (lower is better)
            latency_score = 1.0 / (1.0 + metrics.avg_latency_ms / 1000)

            # Cost score (lower is better)
            cost_score = 1.0 / (1.0 + config.input_cost + config.output_cost)

            # Combined score
            score = (
                reliability * 0.5 +
                latency_score * 0.3 +
                cost_score * 0.2
            )

            # Priority adjustment
            if task.priority == TaskPriority.CRITICAL:
                # Use most reliable
                score = reliability
            elif task.priority == TaskPriority.LOW:
                # Use cheapest
                score = cost_score

            candidates.append((name, score))

        if not candidates:
            return None

        # Return best provider
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def _is_provider_available(self, provider: str) -> bool:
        """Check if a provider is available"""
        config = self._providers.get(provider)
        if not config:
            return False

        metrics = self._metrics[provider]

        # Check rate limits
        current_time = time.time()
        if current_time - metrics.minute_start_time >= 60:
            # Reset minute counters
            metrics.current_minute_requests = 0
            metrics.current_minute_tokens = 0
            metrics.minute_start_time = current_time

        if metrics.current_minute_requests >= config.requests_per_minute:
            return False

        if metrics.current_minute_tokens >= config.tokens_per_minute:
            return False

        return True

    def submit_task(
        self,
        task_type: TaskType,
        prompt: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        **kwargs
    ) -> str:
        """
        Submit a task for execution

        Args:
            task_type: Type of task
            prompt: Task prompt
            priority: Task priority
            **kwargs: Additional task parameters

        Returns:
            Task ID
        """
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"

        task = ScheduledTask(
            task_id=task_id,
            task_type=task_type,
            priority=priority,
            prompt=prompt,
            **kwargs
        )

        self._pending_tasks.append(task)
        self._stats["total_tasks"] += 1

        # Sort pending tasks by priority
        self._pending_tasks.sort(key=lambda t: t.priority.value)

        return task_id

    def execute_task(self, task: ScheduledTask) -> TaskResult:
        """
        Execute a task using the best available provider

        Args:
            task: Task to execute

        Returns:
            TaskResult with execution results
        """
        provider_name = self.select_provider(task)

        if not provider_name:
            return TaskResult(
                task_id=task.task_id,
                success=False,
                error="No available providers"
            )

        # Get fallback chain
        fallbacks = self._fallback_chains.get(provider_name, [])
        all_providers = [provider_name] + fallbacks

        # Try providers in order
        last_error = ""
        attempted = 0
        for provider in all_providers:
            # 跳过当前不可用（如已达速率限制 / 未注册）的 provider，
            # 让后续 fallback 有机会真正执行，而不是反复尝试已经不可用的主 provider。
            if not self._is_provider_available(provider):
                last_error = f"Provider {provider} unavailable (rate-limited or unknown)"
                continue
            attempted += 1
            result = self._execute_with_provider(task, provider)
            if result.success:
                return result
            last_error = result.error

        return TaskResult(
            task_id=task.task_id,
            success=False,
            error=(f"All providers failed: {last_error}" if attempted
                   else f"No available providers: {last_error}"),
            attempts=attempted
        )

    def _execute_with_provider(
        self,
        task: ScheduledTask,
        provider: str
    ) -> TaskResult:
        """Execute task with a specific provider"""
        config = self._providers.get(provider)
        client = self.get_client(provider)

        if not config or not client:
            return TaskResult(
                task_id=task.task_id,
                success=False,
                error=f"Provider {provider} not available",
                provider=provider
            )

        metrics = self._metrics[provider]
        start_time = time.time()

        try:
            # Execute based on mode
            if task.json_mode:
                content = client.generate_json(task.prompt)
                content_str = json.dumps(content, ensure_ascii=False) if content else ""
            else:
                content_str = client.generate(task.prompt) or ""

            # Calculate metrics
            latency = (time.time() - start_time) * 1000

            # Estimate tokens
            tokens_in = len(task.prompt) // 4
            tokens_out = len(content_str) // 4
            cost = (tokens_in * config.input_cost + tokens_out * config.output_cost) / 1000

            # Update metrics
            metrics.total_requests += 1
            metrics.successful_requests += 1
            metrics.total_tokens_in += tokens_in
            metrics.total_tokens_out += tokens_out
            metrics.total_cost += cost
            metrics.avg_latency_ms = (
                (metrics.avg_latency_ms * (metrics.successful_requests - 1) + latency) /
                metrics.successful_requests
            )
            metrics.current_minute_requests += 1
            metrics.current_minute_tokens += tokens_in + tokens_out

            self._stats["completed_tasks"] += 1
            self._stats["total_cost"] += cost

            return TaskResult(
                task_id=task.task_id,
                success=True,
                content=content_str,
                provider=provider,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency,
                cost=cost
            )

        except Exception as e:
            metrics.total_requests += 1
            metrics.failed_requests += 1
            # 失败也计入当前分钟请求数，否则持续失败的 provider 永远不会触发
            # 自身的速率限制，会在每次调用时被反复尝试。
            metrics.current_minute_requests += 1

            return TaskResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
                provider=provider
            )

    def execute_next(self) -> Optional[TaskResult]:
        """Execute the next pending task"""
        if not self._pending_tasks:
            return None

        task = self._pending_tasks.pop(0)
        return self.execute_task(task)

    def execute_all(self) -> List[TaskResult]:
        """Execute all pending tasks"""
        results = []
        while self._pending_tasks:
            result = self.execute_next()
            if result:
                results.append(result)
        return results

    def generate(
        self,
        prompt: str,
        task_type: TaskType = TaskType.GENERATION,
        priority: TaskPriority = TaskPriority.NORMAL,
        **kwargs
    ) -> str:
        """
        Convenience method for simple generation

        Args:
            prompt: Generation prompt
            task_type: Type of task
            priority: Task priority
            **kwargs: Additional parameters

        Returns:
            Generated content or empty string on failure
        """
        task = ScheduledTask(
            task_id=f"direct_{time.time()}",
            task_type=task_type,
            priority=priority,
            prompt=prompt,
            **kwargs
        )

        result = self.execute_task(task)
        return result.content if result.success else ""

    def generate_json(
        self,
        prompt: str,
        task_type: TaskType = TaskType.GENERATION,
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> Optional[Dict]:
        """
        Convenience method for JSON generation

        Returns:
            Parsed JSON or None on failure
        """
        task = ScheduledTask(
            task_id=f"direct_json_{time.time()}",
            task_type=task_type,
            priority=priority,
            prompt=prompt,
            json_mode=True
        )

        result = self.execute_task(task)
        if result.success:
            try:
                return json.loads(result.content)
            except json.JSONDecodeError:
                return None
        return None

    def get_stats(self) -> Dict:
        """Get scheduler statistics"""
        return {
            **self._stats,
            "pending_tasks": len(self._pending_tasks),
            "providers": {
                name: {
                    "success_rate": self._metrics[name].success_rate,
                    "total_requests": self._metrics[name].total_requests,
                    "total_cost": self._metrics[name].total_cost,
                    "avg_latency_ms": self._metrics[name].avg_latency_ms
                }
                for name in self._providers
            }
        }

    def get_provider_stats(self, provider: str) -> Optional[Dict]:
        """Get statistics for a specific provider"""
        if provider not in self._providers:
            return None

        metrics = self._metrics[provider]
        config = self._providers[provider]

        return {
            "name": provider,
            "type": config.provider_type.value,
            "model": config.model_name,
            "reliability_score": config.reliability_score,
            "success_rate": metrics.success_rate,
            "total_requests": metrics.total_requests,
            "successful_requests": metrics.successful_requests,
            "failed_requests": metrics.failed_requests,
            "total_tokens_in": metrics.total_tokens_in,
            "total_tokens_out": metrics.total_tokens_out,
            "total_cost": metrics.total_cost,
            "avg_latency_ms": metrics.avg_latency_ms
        }


# Global scheduler instance
_global_scheduler: Optional[LLMScheduler] = None


def get_scheduler() -> LLMScheduler:
    """Get the global LLM scheduler instance"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = LLMScheduler()
    return _global_scheduler


def init_scheduler(
    api_key: str,
    base_url: str,
    model_name: str = "deepseek-chat",
    **kwargs
) -> LLMScheduler:
    """
    Initialize the global scheduler with default provider

    Args:
        api_key: API key
        base_url: API base URL
        model_name: Model name
        **kwargs: Additional configuration

    Returns:
        Configured scheduler
    """
    global _global_scheduler
    scheduler = LLMScheduler()

    config = ProviderConfig(
        name="default",
        provider_type=ProviderType.DEEPSEEK,
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
        **kwargs
    )
    scheduler.register_provider(config)

    _global_scheduler = scheduler
    return scheduler
