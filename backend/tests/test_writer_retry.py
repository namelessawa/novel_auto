from __future__ import annotations

from pathlib import Path

import pytest

from story.models import WriterCandidate
from story.repair_patch import RepairPatchSet
from story.service import GenerationRejected
from story.writer import AuthorWriter, WriterResult
from tests.test_author_generation_service import _goal, _service, _valid_candidate


class RetryWriter:
    def __init__(
        self,
        initial: WriterCandidate,
        retried: WriterCandidate,
    ) -> None:
        self.initial = initial
        self.retried = retried
        self.generate_calls = 0
        self.retry_calls = 0
        self.repair_calls = 0

    async def generate(self, context, goal):
        del context, goal
        self.generate_calls += 1
        return WriterResult(
            self.initial,
            {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    async def retry(self, context, goal, candidate, preflight_report):
        del context, goal, candidate
        self.retry_calls += 1
        assert preflight_report.retry_required is True
        return WriterResult(
            self.retried,
            {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        )

    async def repair(self, candidate, plan):
        del plan
        self.repair_calls += 1
        return WriterResult(
            candidate,
            {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            repair_patches=RepairPatchSet(),
        )


def _short() -> WriterCandidate:
    return _valid_candidate(
        "主角确认自己的身份，并选择承担代价。"
    )


@pytest.mark.asyncio
async def test_default_flow_never_calls_exposed_full_retry(tmp_path: Path) -> None:
    writer = RetryWriter(_short(), _valid_candidate())
    service = _service(tmp_path, writer)

    with pytest.raises(GenerationRejected):
        await service.run(_goal(), request_id="retry_disabled")

    transaction = service.transactions.load("retry_disabled")
    assert transaction.committed is False
    assert transaction.writer_retry_performed is False
    assert transaction.writer_retry_count == 0
    assert transaction.writer_calls == 2
    assert transaction.repair_performed is True
    assert transaction.writer_first_pass_pass is False
    assert transaction.usage.get("retry_tokens", 0) == 0
    assert writer.generate_calls == 1
    assert writer.retry_calls == 0
    assert writer.repair_calls == 1


def test_author_writer_has_no_full_retry_provider_path() -> None:
    assert not hasattr(AuthorWriter, "RETRY_SYSTEM_PROMPT")
    assert not hasattr(AuthorWriter, "retry")


@pytest.mark.asyncio
async def test_disabled_retry_cannot_modify_state_before_rejection(
    tmp_path: Path,
) -> None:
    writer = RetryWriter(_short(), _valid_candidate())
    service = _service(tmp_path, writer)
    before = service.states.load()

    with pytest.raises(GenerationRejected):
        await service.run(_goal(), request_id="retry_no_state")

    assert writer.retry_calls == 0
    assert service.states.load() == before
    assert service.sections.count() == 0


@pytest.mark.asyncio
async def test_default_call_cap_is_one_initial_plus_one_repair(
    tmp_path: Path,
) -> None:
    writer = RetryWriter(_short(), _short())
    service = _service(tmp_path, writer)

    with pytest.raises(GenerationRejected):
        await service.run(_goal(), request_id="retry_once")

    transaction = service.transactions.load("retry_once")
    assert writer.generate_calls == 1
    assert writer.retry_calls == 0
    assert writer.repair_calls == 1
    assert transaction.writer_retry_count == 0
    assert transaction.writer_retry_performed is False
    assert transaction.writer_calls == 2
    assert transaction.repair_performed is True


@pytest.mark.asyncio
async def test_valid_first_pass_uses_only_one_provider_call(
    tmp_path: Path,
) -> None:
    writer = RetryWriter(_valid_candidate(), _short())
    service = _service(tmp_path, writer)

    transaction = await service.run(_goal(), request_id="retry_not_needed")

    assert transaction.committed is True
    assert transaction.writer_calls == 1
    assert transaction.planner_calls == 0
    assert transaction.writer_retry_count == 0
    assert transaction.repair_performed is False
    assert writer.generate_calls == 1
    assert writer.retry_calls == 0
    assert writer.repair_calls == 0


def test_legacy_retry_metrics_remain_readable(tmp_path: Path) -> None:
    writer = RetryWriter(_valid_candidate(), _valid_candidate())
    service = _service(tmp_path, writer)
    prepared = service.prepare(_goal(), request_id="legacy_retry_metrics")
    legacy = prepared.transaction.model_copy(
        update={
            "writer_calls": 3,
            "writer_retry_count": 1,
            "writer_retry_performed": True,
            "usage": {"retry_tokens": 20, "total_tokens": 170},
        }
    )

    service.transactions.save(legacy)
    loaded = service.transactions.load(legacy.id)

    assert loaded.writer_calls == 3
    assert loaded.writer_retry_count == 1
    assert loaded.writer_retry_performed is True
    assert loaded.usage["retry_tokens"] == 20
