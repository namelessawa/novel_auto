from __future__ import annotations

from pathlib import Path

import pytest

from story.models import StateDeltaOperation, WriterCandidate
from story.repair_patch import RepairPatchSet
from story.service import AuthorGenerationService, GenerationRejected
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
async def test_retry_produces_valid_chapter(tmp_path: Path) -> None:
    writer = RetryWriter(_short(), _valid_candidate())
    service = _service(tmp_path, writer)

    transaction = await service.run(_goal(), request_id="retry_valid")

    assert transaction.committed is True
    assert transaction.writer_retry_performed is True
    assert transaction.writer_retry_count == 1
    assert transaction.writer_calls == 2
    assert transaction.repair_performed is False
    assert transaction.writer_first_pass_pass is False
    assert transaction.final_preflight_report.accepted is True
    assert transaction.usage["retry_tokens"] == 20
    assert writer.retry_calls == 1


def test_retry_prompt_forbids_new_facts() -> None:
    prompt = AuthorWriter.RETRY_SYSTEM_PROMPT

    for forbidden in ("新人物", "新背景", "新历史", "新关系", "新伤亡"):
        assert forbidden in prompt
    assert "Style controls expression" not in prompt
    assert "风格只控制表达" in prompt


@pytest.mark.asyncio
async def test_retry_does_not_modify_state_before_commit(tmp_path: Path) -> None:
    retried = _valid_candidate().model_copy(
        update={
            "state_delta": [
                StateDeltaOperation(
                    op="set",
                    path="/world/weather",
                    value="暴雨",
                    evidence="正文没有这句证据",
                )
            ]
        }
    )
    writer = RetryWriter(_short(), retried)
    service = _service(tmp_path, writer)
    prepared = service.prepare(_goal(), request_id="retry_no_state")
    generated = await service.generate(prepared)
    report = service.preflight(prepared, generated.candidate)

    await service.retry(prepared, generated.candidate, report)

    assert service.states.load() == prepared.state
    assert service.sections.count() == 0


@pytest.mark.asyncio
async def test_retry_limited_once(tmp_path: Path) -> None:
    writer = RetryWriter(_short(), _short())
    service = _service(tmp_path, writer)

    with pytest.raises(GenerationRejected):
        await service.run(_goal(), request_id="retry_once")

    transaction = service.transactions.load("retry_once")
    assert writer.generate_calls == 1
    assert writer.retry_calls == 1
    assert writer.repair_calls == 1
    assert transaction.writer_retry_count == 1
    assert transaction.writer_calls == 3
    assert transaction.repair_performed is True
