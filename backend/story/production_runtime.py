"""Process-local drivers for durable whole-book production jobs.

The durable truth remains in ``generation_jobs`` and the attempt journals.
This registry owns only asyncio tasks.  Losing it on process death is safe:
``recover_persisted_productions`` rebuilds drivers from disk on startup.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import novel_manager
from story.production_service import (
    ProductionLeaseConflict,
    SectionCommitPending,
    SectionRunner,
    WholeBookProductionService,
)


logger = logging.getLogger(__name__)

RunnerFactory = Callable[..., SectionRunner]
Sleeper = Callable[[float], Awaitable[None]]
_TERMINAL_OR_IDLE = frozenset(
    {"paused", "failed", "cancelled", "completed"}
)
_RECOVERABLE = frozenset({"queued", "running", "pausing", "cancelling"})
_TRANSIENT_PROVIDER_FAILURES = frozenset(
    {"PROVIDER_RATE_LIMITED", "PROVIDER_TIMEOUT", "PROVIDER_UNAVAILABLE"}
)


def _provider_retry_delay(job) -> float:
    """Return a bounded exponential delay for the current durable retry."""

    if job.failure_code not in _TRANSIENT_PROVIDER_FAILURES:
        return 0.0
    attempt_number = int(job.chapter_attempts.get(job.current_chapter_id, 1))
    failure_ordinal = max(1, attempt_number - 1)
    return min(2.0, 0.25 * (2 ** (failure_ordinal - 1)))


def _default_runner_factory(**kwargs: Any) -> SectionRunner:
    # Import lazily so CRUD/migrations and read-only endpoints do not construct
    # a Writer or resolve Provider configuration.
    from story.production_adapter import AuthorProductionSectionRunner
    from story.service import AuthorGenerationService

    service = AuthorGenerationService(
        user_id=str(kwargs["user_id"]),
        novel_id=str(kwargs["novel_id"]),
        data_dir=str(kwargs["data_dir"]),
        title=str(kwargs.get("title") or ""),
        enable_llm_planner=False,
    )
    return AuthorProductionSectionRunner(service)


@dataclass
class ProductionRuntime:
    service: WholeBookProductionService
    task: asyncio.Task[None] | None = None
    pending_job_id: str = ""
    pending_context: contextvars.Context | None = None
    sleeper: Sleeper = asyncio.sleep

    def schedule(self, job_id: str) -> asyncio.Task[None]:
        """Start one driver and inherit the caller's Provider ContextVar."""

        context = contextvars.copy_context()
        if self.task is not None and not self.task.done():
            # A resume can race the previous driver's final ``paused`` read.
            # Only an explicit resume/retry has moved durable state back to
            # queued.  A duplicate start while the same job is still running
            # must reuse the current driver without scheduling a second one.
            try:
                durable = self.service.get_job(job_id)
            except (KeyError, ValueError):
                durable = None
            if durable is not None and durable.status == "queued":
                self.pending_job_id = job_id
                self.pending_context = context
            return self.task
        return self._start_task(job_id, context)

    def _start_task(
        self,
        job_id: str,
        context: contextvars.Context,
    ) -> asyncio.Task[None]:
        self.task = asyncio.create_task(
            self._drive(job_id),
            name=f"whole-book-production:{self.service.novel_id}:{job_id}",
            context=context,
        )
        return self.task

    async def _drive(self, job_id: str) -> None:
        commit_pending_count = 0
        persistence_retry_count = 0
        try:
            while True:
                try:
                    job = await self.service.run(job_id)
                    commit_pending_count = 0
                    persistence_retry_count = 0
                except SectionCommitPending:
                    commit_pending_count += 1
                    if commit_pending_count >= 3:
                        self.service.pause_recoverable(
                            job_id,
                            failure_code="SECTION_COMMIT_PENDING",
                            failure_message=(
                                "Section commit could not be reconciled after "
                                "three same-transaction replays"
                            ),
                        )
                        return
                    await self.sleeper(0)
                    continue
                except ProductionLeaseConflict:
                    # Another process owns a live lease.  Its durable heartbeat
                    # is authoritative; this process must not compete.
                    return
                except PermissionError:
                    # Windows may briefly deny ``os.replace`` while a scanner
                    # has the destination open.  The journaled coordinator is
                    # restart-safe, so replay the same durable boundary with a
                    # small bounded backoff instead of orphaning a running job.
                    persistence_retry_count += 1
                    if persistence_retry_count > 5:
                        logger.error(
                            "production persistence remained busy for %s",
                            self.service.novel_id,
                        )
                        return
                    await self.sleeper(0.05 * persistence_retry_count)
                    continue
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # The coordinator normally journals failures itself.  Keep
                    # logs secret-safe even if an unexpected implementation
                    # error escapes.
                    logger.error(
                        "production driver stopped for %s (%s)",
                        self.service.novel_id,
                        type(exc).__name__,
                    )
                    return

                if job.status in _TERMINAL_OR_IDLE:
                    return
                if job.status not in _RECOVERABLE:
                    return
                # A transient Provider error returns ``running`` after it has
                # journaled a fresh-attempt retry. The attempt ordinal is
                # durable, so restarts preserve the bounded exponential delay.
                await self.sleeper(_provider_retry_delay(job))
        finally:
            current = asyncio.current_task()
            if self.task is current:
                self.task = None
            pending = self.pending_job_id
            pending_context = self.pending_context
            self.pending_job_id = ""
            self.pending_context = None
            if pending:
                try:
                    job = self.service.get_job(pending)
                except (KeyError, ValueError):
                    job = None
                if job is not None and job.status in _RECOVERABLE:
                    self._start_task(
                        pending,
                        pending_context or contextvars.copy_context(),
                    )

    def cancel_driver(self) -> asyncio.Task[None] | None:
        self.pending_job_id = ""
        self.pending_context = None
        task = self.task
        if task is not None and not task.done():
            task.cancel()
        return task


_RUNTIMES: dict[tuple[str, str], ProductionRuntime] = {}
_RUNTIMES_LOCK = threading.RLock()
_RUNNER_FACTORY: RunnerFactory = _default_runner_factory


def get_production_runtime(
    user_id: str,
    novel_id: str,
    *,
    data_dir: str | None = None,
    title: str = "",
    section_runner: SectionRunner | None = None,
) -> ProductionRuntime:
    key = (user_id, novel_id)
    resolved_dir = os.path.realpath(
        os.path.abspath(
            data_dir or novel_manager.get_novel_data_dir(user_id, novel_id)
        )
    )
    with _RUNTIMES_LOCK:
        existing = _RUNTIMES.get(key)
        if existing is not None:
            if existing.service.data_dir != resolved_dir:
                raise ValueError("production runtime data directory changed")
            return existing
        runner = section_runner or _RUNNER_FACTORY(
            user_id=user_id,
            novel_id=novel_id,
            data_dir=resolved_dir,
            title=title,
        )
        runtime = ProductionRuntime(
            service=WholeBookProductionService(
                user_id=user_id,
                novel_id=novel_id,
                data_dir=resolved_dir,
                title=title,
                section_runner=runner,
            )
        )
        _RUNTIMES[key] = runtime
        return runtime


def drop_production_runtime(
    user_id: str,
    novel_id: str,
) -> asyncio.Task[None] | None:
    with _RUNTIMES_LOCK:
        runtime = _RUNTIMES.pop((user_id, novel_id), None)
    return runtime.cancel_driver() if runtime is not None else None


async def recover_persisted_productions() -> int:
    """Schedule every durable non-paused active job found at startup."""

    scheduled = 0
    for user_id in novel_manager.list_all_users_with_novels():
        for novel in novel_manager.list_novels(user_id):
            novel_id = str(novel.get("id") or "")
            if not novel_id:
                continue
            try:
                data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
                jobs_dir = os.path.join(data_dir, "generation_jobs")
                if not os.path.isdir(jobs_dir):
                    continue
                runtime = get_production_runtime(
                    user_id,
                    novel_id,
                    data_dir=data_dir,
                    title=str(novel.get("title") or ""),
                )
                job = runtime.service.jobs.find_active()
                if job is not None and job.status in _RECOVERABLE:
                    runtime.schedule(job.id)
                    scheduled += 1
            except Exception as exc:
                logger.error(
                    "production startup recovery skipped %s/%s (%s)",
                    user_id,
                    novel_id,
                    type(exc).__name__,
                )
    return scheduled


async def close_all_production_runtimes() -> None:
    with _RUNTIMES_LOCK:
        runtimes = list(_RUNTIMES.values())
        _RUNTIMES.clear()
    tasks = [
        task
        for runtime in runtimes
        if (task := runtime.cancel_driver()) is not None
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def set_production_runner_factory_for_tests(factory: RunnerFactory) -> None:
    global _RUNNER_FACTORY
    with _RUNTIMES_LOCK:
        if _RUNTIMES:
            raise RuntimeError("drop production runtimes before changing factory")
        _RUNNER_FACTORY = factory


def reset_production_runner_factory_for_tests() -> None:
    global _RUNNER_FACTORY
    with _RUNTIMES_LOCK:
        if _RUNTIMES:
            raise RuntimeError("drop production runtimes before resetting factory")
        _RUNNER_FACTORY = _default_runner_factory


__all__ = [
    "ProductionRuntime",
    "close_all_production_runtimes",
    "drop_production_runtime",
    "get_production_runtime",
    "recover_persisted_productions",
    "reset_production_runner_factory_for_tests",
    "set_production_runner_factory_for_tests",
]
