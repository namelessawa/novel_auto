from __future__ import annotations

from pathlib import Path

import pytest

from sections.section_store import _clear_for_tests
from story.models import CanonicalState
from story.service import (
    AuthorGenerationService,
    RevisionChainBrokenError,
)
from tests.test_author_generation_service import (
    FakeWriter,
    _goal,
    _service,
    _valid_candidate,
)


@pytest.fixture(autouse=True)
def clear_sections():
    _clear_for_tests()
    yield
    _clear_for_tests()


async def _staged(service: AuthorGenerationService, request_id: str):
    prepared = service.prepare(_goal(), request_id=request_id)
    generated = await service.generate(prepared)
    transaction = service._record_generated(prepared.transaction, generated)
    report = service.validate(prepared, generated.candidate)
    return service._stage(
        prepared,
        transaction,
        generated.candidate,
        report,
    )


@pytest.mark.asyncio
async def test_revision_mismatch_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path, FakeWriter(_valid_candidate()))
    staged = await _staged(service, "revision_mismatch")
    service.states.save(
        CanonicalState(
            revision=2,
            world={"external": True},
        )
    )

    with pytest.raises(RevisionChainBrokenError):
        service.commit(staged)

    rejected = service.transactions.load(staged.id)
    assert rejected.phase == "rejected"
    assert rejected.error_code == "REVISION_CHAIN_BROKEN"
    assert service.sections.count() == 0


@pytest.mark.asyncio
async def test_recover_mismatch_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path, FakeWriter(_valid_candidate()))
    staged = await _staged(service, "recover_revision_mismatch")
    service.transactions.save(
        staged.model_copy(
            update={
                "phase": "committing",
                "journal_canonical_revision": staged.target_canonical_revision,
            }
        )
    )
    del service
    _clear_for_tests()

    recovered = AuthorGenerationService(
        user_id="alice",
        novel_id="novel",
        data_dir=str(tmp_path),
        title="测试小说",
        writer=FakeWriter(_valid_candidate()),
    )

    rejected = recovered.transactions.load(staged.id)
    assert rejected.phase == "rejected"
    assert rejected.error_code == "REVISION_CHAIN_BROKEN"
    assert recovered.states.load().revision == staged.canonical_state_revision
    assert recovered.sections.count() == 0


@pytest.mark.asyncio
async def test_no_revision_jump(tmp_path: Path) -> None:
    service = _service(tmp_path, FakeWriter(_valid_candidate()))

    first = await service.run(_goal(), request_id="revision_one")
    second = await service.run(_goal(), request_id="revision_two")

    assert (
        first.canonical_state_revision,
        first.journal_canonical_revision,
        first.target_canonical_revision,
    ) == (1, 2, 2)
    assert (
        second.canonical_state_revision,
        second.journal_canonical_revision,
        second.target_canonical_revision,
    ) == (2, 3, 3)
    assert service.states.load().revision == 3
    assert service.sections.count() == 2
