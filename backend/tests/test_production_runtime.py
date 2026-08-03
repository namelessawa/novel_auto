from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import novel_manager
from nf_core.provider_runtime import (
    ProviderConfigurationError,
    ProviderError,
    ProviderRuntimeConfig,
    get_request_provider_config,
    reset_request_provider_config,
    set_request_provider_config,
)
from story.models import StoryBibleUpdate
from story.persistence import CanonicalStateStore, StoryBibleStore
from story.production_models import (
    BookOutlineUpdate,
    ChapterOutline,
    NovelProductionSpecUpdate,
    VolumeOutline,
)
from story.production_persistence import (
    BookOutlineStore,
    ProductionSectionAttemptStore,
    ProductionSpecStore,
    ensure_production_domain,
)
from story.production_runtime import (
    ProductionRuntime,
    _provider_retry_delay,
    close_all_production_runtimes,
    get_production_runtime,
    recover_persisted_productions,
    reset_production_runner_factory_for_tests,
    set_production_runner_factory_for_tests,
)
from story.production_service import (
    SectionCommitPending,
    SectionRunRequest,
    SectionRunResult,
    WholeBookProductionService,
)


def _configure_book(data_dir: Path) -> None:
    ensure_production_domain(str(data_dir), title="潮汐之城")
    bible_store = StoryBibleStore(str(data_dir))
    bible = bible_store.load()
    bible_store.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            title="潮汐之城",
            premise="城市用记忆交换平静。",
            theme="记忆与责任",
            setting_summary="一座受潮汐契约约束的海港城。",
        )
    )
    spec_store = ProductionSpecStore(
        str(data_dir),
        lambda: (_ for _ in ()).throw(AssertionError("spec must exist")),
    )
    spec = spec_store.load()
    spec_store.update(
        NovelProductionSpecUpdate(
            expected_revision=spec.revision,
            target_total_chars=1_000,
            volume_count=1,
            chapter_count=1,
            target_chapter_chars=1_000,
            accepted_chapter_min_chars=1_000,
            accepted_chapter_max_chars=1_000,
            section_target_chars=1_000,
        )
    )
    outline_store = BookOutlineStore(str(data_dir))
    outline = outline_store.load()
    outline_store.update(
        BookOutlineUpdate(
            expected_revision=outline.revision,
            logline="守潮人发现平静的代价。",
            global_arc="发现、追查、承担。",
            volumes=[
                VolumeOutline(
                    id="volume_001",
                    ordinal=1,
                    title="失潮",
                    objective="确认契约",
                    opening_state="潮汐平静",
                    closing_state="真相公开",
                    target_chapters=1,
                    target_chars=1_000,
                )
            ],
            chapters=[
                ChapterOutline(
                    id="chapter_0001",
                    ordinal=1,
                    volume_id="volume_001",
                    title="退去的名字",
                    objective="确认记忆代价",
                    target_chars=1_000,
                )
            ],
            ending_target="公开真相并承担后果。",
            status="ready",
        )
    )


def _start(service: WholeBookProductionService):
    spec = service.specs.load()
    outline = service.outlines.load()
    return service.start(
        expected_spec_revision=spec.revision,
        expected_outline_revision=outline.revision,
    ).job


class SuccessfulRunner:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = str(data_dir)
        self.transactions: list[str] = []
        self.results: dict[str, SectionRunResult] = {}

    async def run_section(self, request: SectionRunRequest) -> SectionRunResult:
        self.transactions.append(request.transaction_id)
        if request.transaction_id in self.results:
            return self.results[request.transaction_id]
        states = CanonicalStateStore(self.data_dir)
        current = states.load()
        updated = current.model_copy(
            update={"revision": current.revision + 1, "world_time": current.world_time + 1}
        )
        states.save_next(updated, expected_revision=current.revision)
        content = "潮" * request.snapshot.section_target_chars
        result = SectionRunResult(
            transaction_id=request.transaction_id,
            section_id=request.section_id,
            committed=True,
            content=content,
            summary="守潮人确认了交换的代价。",
            char_count=len(content),
            canonical_revision_after=updated.revision,
            story_bible_revision=request.snapshot.story_bible_revision,
            validation_passed=True,
        )
        self.results[request.transaction_id] = result
        return result


class ProviderFailureRunner:
    def __init__(
        self,
        error: ProviderError | ProviderConfigurationError,
    ) -> None:
        self.error = error
        self.transactions: list[str] = []

    async def run_section(self, request: SectionRunRequest) -> SectionRunResult:
        self.transactions.append(request.transaction_id)
        raise self.error


class CommitPendingRunner:
    def __init__(self) -> None:
        self.transactions: list[str] = []

    async def run_section(self, request: SectionRunRequest) -> SectionRunResult:
        self.transactions.append(request.transaction_id)
        raise SectionCommitPending("recorded commit pending")


class AsyncBlockingRunner:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.cancelled = False

    async def run_section(self, request: SectionRunRequest) -> SectionRunResult:
        del request
        self.entered.set()
        try:
            await asyncio.Future()
        finally:
            self.cancelled = True


class ContextRaceService:
    novel_id = "context-race"

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.models: list[str] = []

    async def run(self, job_id: str):
        del job_id
        config = get_request_provider_config()
        self.models.append(config.model if config is not None else "")
        if len(self.models) == 1:
            self.entered.set()
            await self.release.wait()
            return SimpleNamespace(status="paused")
        return SimpleNamespace(status="completed")

    def get_job(self, job_id: str):
        del job_id
        return SimpleNamespace(status="queued")


class PersistenceRaceService:
    novel_id = "persistence-race"

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, job_id: str):
        del job_id
        self.calls += 1
        if self.calls == 1:
            raise PermissionError("recorded transient sharing violation")
        return SimpleNamespace(status="completed")

    def get_job(self, job_id: str):
        del job_id
        return SimpleNamespace(status="running")


def _provider_config(model: str = "recorded-model") -> ProviderRuntimeConfig:
    return ProviderRuntimeConfig(
        provider="custom",
        api_key="recorded-only",
        base_url="https://provider.invalid/v1",
        model=model,
        thinking_mode="disabled",
        timeout=1,
        max_retries=0,
        temperature=0,
        max_tokens_cap=1_000,
        source="test",
    )


def _provider_error(category: str) -> ProviderError:
    config = _provider_config()
    rows = {
        "auth": ("PROVIDER_AUTH_FAILED", 424, 401),
        "rate_limit": ("PROVIDER_RATE_LIMITED", 429, 429),
        "unavailable": ("PROVIDER_UNAVAILABLE", 502, 503),
        "output_invalid": ("PROVIDER_OUTPUT_INVALID", 502, None),
    }
    code, status, upstream = rows[category]
    return ProviderError(
        code=code,
        message="recorded provider failure",
        http_status=status,
        http_category=category,
        config=config,
        upstream_status=upstream,
    )


@pytest.mark.asyncio
async def test_runtime_has_one_driver_and_close_cancels_it(tmp_path: Path) -> None:
    _configure_book(tmp_path)
    runner = CommitPendingRunner()
    service = WholeBookProductionService(
        user_id="user_1",
        novel_id="novel_1",
        data_dir=str(tmp_path),
        section_runner=runner,
        lease_seconds=0,
    )
    job = _start(service)
    runtime = ProductionRuntime(service)

    first = runtime.schedule(job.id)
    second = runtime.schedule(job.id)
    assert first is second
    await first

    paused = service.get_job(job.id)
    assert paused.status == "paused"
    assert paused.failure_code == "SECTION_COMMIT_PENDING"
    assert len(runner.transactions) == 3
    assert len(set(runner.transactions)) == 1
    assert runtime.task is None


@pytest.mark.asyncio
async def test_registry_is_singleton_and_close_cancels_active_driver(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path)
    runner = AsyncBlockingRunner()
    runtime = get_production_runtime(
        "user_1",
        "novel_1",
        data_dir=str(tmp_path),
        section_runner=runner,
    )
    assert (
        get_production_runtime("user_1", "novel_1", data_dir=str(tmp_path))
        is runtime
    )
    job = _start(runtime.service)
    task = runtime.schedule(job.id)
    await asyncio.wait_for(runner.entered.wait(), timeout=3)

    await close_all_production_runtimes()

    assert task.cancelled()
    assert runner.cancelled is True
    assert runtime.task is None
    assert runtime.service.get_job(job.id).status == "running"


@pytest.mark.asyncio
async def test_pending_resume_inherits_the_new_request_provider_context() -> None:
    service = ContextRaceService()
    runtime = ProductionRuntime(service)  # type: ignore[arg-type]

    first_token = set_request_provider_config(_provider_config("model-before-pause"))
    try:
        first_task = runtime.schedule("job_context")
    finally:
        reset_request_provider_config(first_token)
    await asyncio.wait_for(service.entered.wait(), timeout=3)

    resume_token = set_request_provider_config(_provider_config("model-on-resume"))
    try:
        assert runtime.schedule("job_context") is first_task
    finally:
        reset_request_provider_config(resume_token)

    service.release.set()
    await first_task
    for _ in range(100):
        if len(service.models) == 2:
            break
        await asyncio.sleep(0)

    assert service.models == ["model-before-pause", "model-on-resume"]
    assert runtime.task is None or runtime.task.done()


@pytest.mark.asyncio
async def test_transient_persistence_sharing_violation_replays_driver() -> None:
    service = PersistenceRaceService()
    runtime = ProductionRuntime(service)  # type: ignore[arg-type]

    await runtime.schedule("job_persistence")

    assert service.calls == 2
    assert runtime.task is None


def test_provider_retry_delay_is_durable_exponential_and_bounded() -> None:
    def job(attempt: int, code: str = "PROVIDER_RATE_LIMITED"):
        return SimpleNamespace(
            failure_code=code,
            current_chapter_id="chapter_0001",
            chapter_attempts={"chapter_0001": attempt},
        )

    assert _provider_retry_delay(job(2)) == 0.25
    assert _provider_retry_delay(job(3)) == 0.5
    assert _provider_retry_delay(job(4)) == 1.0
    assert _provider_retry_delay(job(5)) == 2.0
    assert _provider_retry_delay(job(20)) == 2.0
    assert _provider_retry_delay(job(2, "PROVIDER_OUTPUT_INVALID")) == 0.0
    assert _provider_retry_delay(job(2, "PROVIDER_AUTH_FAILED")) == 0.0


@pytest.mark.asyncio
async def test_provider_auth_pauses_immediately_and_resume_uses_new_attempt(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path)
    runner = ProviderFailureRunner(_provider_error("auth"))
    service = WholeBookProductionService(
        user_id="user_1",
        novel_id="novel_1",
        data_dir=str(tmp_path),
        section_runner=runner,
        lease_seconds=0,
    )
    job = _start(service)
    paused = await service.run(job.id)

    assert paused.status == "paused"
    assert paused.failure_code == "PROVIDER_AUTH_FAILED"
    assert len(runner.transactions) == 1
    first_transaction = runner.transactions[0]
    assert service.list_chapters(committed_only=True) == []

    success = SuccessfulRunner(tmp_path)
    service.section_runner = success
    resumed = service.resume(job.id, expected_revision=paused.revision)
    completed = await service.run(resumed.id)
    assert completed.status == "completed"
    assert success.transactions[0] != first_transaction
    attempts = ProductionSectionAttemptStore(str(tmp_path)).list_all(job_id=job.id)
    assert [item.attempt_number for item in attempts] == [1, 2]
    assert [item.status for item in attempts] == ["failed", "committed"]


@pytest.mark.asyncio
async def test_provider_configuration_failure_pauses_without_retry(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path)
    runner = ProviderFailureRunner(
        ProviderConfigurationError("recorded configuration unavailable")
    )
    service = WholeBookProductionService(
        user_id="user_1",
        novel_id="novel_1",
        data_dir=str(tmp_path),
        section_runner=runner,
        lease_seconds=0,
    )
    job = _start(service)

    paused = await service.run(job.id)

    assert paused.status == "paused"
    assert paused.failure_code == "PROVIDER_CONFIG_INVALID"
    assert len(runner.transactions) == 1
    attempts = ProductionSectionAttemptStore(str(tmp_path)).list_all(job_id=job.id)
    assert len(attempts) == 1
    assert attempts[0].attempt_number == 1
    assert attempts[0].status == "failed"


@pytest.mark.asyncio
async def test_provider_output_invalid_pauses_without_fresh_writer_attempt(
    tmp_path: Path,
) -> None:
    _configure_book(tmp_path)
    runner = ProviderFailureRunner(_provider_error("output_invalid"))
    service = WholeBookProductionService(
        user_id="user_1",
        novel_id="novel_1",
        data_dir=str(tmp_path),
        section_runner=runner,
        lease_seconds=0,
        provider_retry_limit=2,
    )
    job = _start(service)

    paused = await service.run(job.id)

    assert paused.status == "paused"
    assert paused.failure_code == "PROVIDER_OUTPUT_INVALID"
    assert len(runner.transactions) == 1
    attempts = ProductionSectionAttemptStore(str(tmp_path)).list_all(job_id=job.id)
    assert len(attempts) == 1
    assert attempts[0].attempt_number == 1
    assert attempts[0].status == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("category", ["rate_limit", "unavailable"])
async def test_transient_provider_failure_is_bounded_then_paused(
    tmp_path: Path,
    category: str,
) -> None:
    _configure_book(tmp_path)
    runner = ProviderFailureRunner(_provider_error(category))
    service = WholeBookProductionService(
        user_id="user_1",
        novel_id="novel_1",
        data_dir=str(tmp_path),
        section_runner=runner,
        lease_seconds=0,
        provider_retry_limit=2,
    )
    job = _start(service)
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    runtime = ProductionRuntime(service, sleeper=record_delay)
    await runtime.schedule(job.id)

    paused = service.get_job(job.id)
    assert paused.status == "paused"
    assert len(runner.transactions) == 3
    assert len(set(runner.transactions)) == 3
    attempts = ProductionSectionAttemptStore(str(tmp_path)).list_all(job_id=job.id)
    assert [item.attempt_number for item in attempts] == [1, 2, 3]
    assert all(item.status == "failed" for item in attempts)
    assert service.list_chapters(committed_only=True) == []
    assert delays == [0.25, 0.5]


@pytest.mark.asyncio
async def test_startup_recovery_schedules_one_recorded_driver(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = str(tmp_path / "data")
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", root)
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", os.path.join(root, "users"))
    monkeypatch.setattr(
        novel_manager,
        "_LEGACY_NOVELS_DIR",
        os.path.join(root, "novels"),
    )
    novel = novel_manager.create_novel("alice", "潮汐之城")
    data_dir = Path(novel_manager.get_novel_data_dir("alice", novel["id"]))
    _configure_book(data_dir)
    seed_runner = SuccessfulRunner(data_dir)
    seed_service = WholeBookProductionService(
        user_id="alice",
        novel_id=novel["id"],
        data_dir=str(data_dir),
        section_runner=seed_runner,
        lease_seconds=0,
    )
    job = _start(seed_service)

    created: list[SuccessfulRunner] = []

    def factory(**kwargs):
        runner = SuccessfulRunner(Path(kwargs["data_dir"]))
        created.append(runner)
        return runner

    await close_all_production_runtimes()
    set_production_runner_factory_for_tests(factory)
    try:
        assert await recover_persisted_productions() == 1
        runtime = get_production_runtime("alice", novel["id"], data_dir=str(data_dir))
        assert runtime.task is not None
        await runtime.task
        assert runtime.service.get_job(job.id).status == "completed"
        assert len(created) == 1
    finally:
        await close_all_production_runtimes()
        reset_production_runner_factory_for_tests()
