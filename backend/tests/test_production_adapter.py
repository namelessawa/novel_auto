from __future__ import annotations

import json
from pathlib import Path

import pytest

from sections.section_store import _clear_for_tests
from story.models import SectionGoal, StoryBibleUpdate, WriterCandidate
from story.production_adapter import (
    AuthorProductionSectionRunner,
    ProductionAdapterInvariantError,
)
from story.production_models import (
    BookOutlineUpdate,
    ChapterOutline,
    NovelProductionSpecUpdate,
    StyleProfile,
    StyleProfileCreate,
    VolumeOutline,
)
from story.production_persistence import (
    ActiveStyleStore,
    BookOutlineStore,
    ProductionSectionAttemptStore,
    ProductionSpecStore,
    StyleProfileStore,
    ensure_production_domain,
)
from story.production_service import (
    InjectedProductionCrash,
    SectionCommitPending,
    SectionRunRequest,
    WholeBookProductionService,
)
from story.repair_patch import RepairPatchSet
from story.service import (
    AuthorGenerationService,
    ProductionSnapshotMismatchError,
)
from story.writer import WriterResult


class RecordedAuthorWriter:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject
        self.generate_calls = 0
        self.repair_calls = 0
        self.planner_calls = 0
        self.goals: list[SectionGoal] = []
        self.style_slots: list[dict] = []

    async def plan(self, _context, _goal):
        self.planner_calls += 1
        raise AssertionError("production must not invoke the optional LLM planner")

    async def generate(self, context, goal):
        self.generate_calls += 1
        self.goals.append(goal)
        style_slot = json.loads(context.slots["style_contract"])
        self.style_slots.append(style_slot)
        assert "optional_user_sample" not in style_slot
        assert "样文绝不能进入提示词" not in context.slots["style_contract"]
        unit = "".join(goal.objective.split()) + "。"
        target = 24 if self.reject else goal.desired_length
        text = (unit * ((target + len(unit) - 1) // len(unit)))[:target]
        return WriterResult(
            candidate=WriterCandidate(
                narrative_text=text,
                title="选择",
                section_summary="主角确认选择并承担代价。",
            ),
            usage={
                "prompt_tokens": 11,
                "completion_tokens": 17,
                "total_tokens": 28,
            },
        )

    async def repair(self, candidate, _report):
        self.repair_calls += 1
        return WriterResult(
            candidate=candidate,
            usage={
                "prompt_tokens": 3,
                "completion_tokens": 5,
                "total_tokens": 8,
            },
            repair_patches=RepairPatchSet(),
        )


@pytest.fixture(autouse=True)
def clear_section_stores():
    _clear_for_tests()
    yield
    _clear_for_tests()


def _configure_domain(
    tmp_path: Path,
    writer: RecordedAuthorWriter,
    *,
    chapter_count: int = 2,
    section_target_chars: int = 500,
) -> tuple[
    AuthorGenerationService,
    AuthorProductionSectionRunner,
    WholeBookProductionService,
    StyleProfile,
]:
    author = AuthorGenerationService(
        user_id="production_user",
        novel_id="production_novel",
        data_dir=str(tmp_path),
        title="潮汐之城",
        writer=writer,
        enable_llm_planner=True,
    )
    bible = author.bibles.load()
    author.bibles.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            premise="一名守城人发现潮声会抹去记忆。",
            theme="选择、责任与记忆",
            setting_summary="被潮汐围困的旧城。",
            immutable_world_rules=["死亡不可逆"],
        )
    )
    ensure_production_domain(str(tmp_path), title="潮汐之城")

    styles = StyleProfileStore(str(tmp_path))
    custom = styles.create(
        StyleProfileCreate(
            name="冷潮自定义",
            base_preset_key="noir_cold",
            narrative_voice="克制的有限第三人称",
            pacing="短促而稳定",
            optional_user_sample="样文绝不能进入提示词",
            derived_style_anchors=["动作先于判断"],
            deterministic_rules=["不改变事实"],
        ),
        profile_id="style_recorded_cold",
    )
    active_styles = ActiveStyleStore(
        str(tmp_path),
        lambda: (_ for _ in ()).throw(AssertionError("active style must exist")),
    )
    active = active_styles.load()
    active_styles.activate(
        custom,
        applies_from_chapter_ordinal=1,
        expected_revision=active.revision,
    )

    spec_store = ProductionSpecStore(
        str(tmp_path),
        lambda: (_ for _ in ()).throw(AssertionError("spec must exist")),
    )
    spec = spec_store.load()
    spec_store.update(
        NovelProductionSpecUpdate(
            expected_revision=spec.revision,
            target_total_chars=chapter_count * 1_000,
            volume_count=1,
            chapter_count=chapter_count,
            target_chapter_chars=1_000,
            accepted_chapter_min_chars=1_000,
            accepted_chapter_max_chars=1_000,
            section_target_chars=section_target_chars,
            active_style_profile_id=custom.id,
        )
    )
    chapters = [
        ChapterOutline(
            id=f"chapter_{ordinal:04d}",
            ordinal=ordinal,
            volume_id="volume_001",
            title=f"第{ordinal}章",
            objective="主角确认选择并承担代价",
            target_chars=1_000,
        )
        for ordinal in range(1, chapter_count + 1)
    ]
    outlines = BookOutlineStore(str(tmp_path))
    outline = outlines.load()
    outlines.update(
        BookOutlineUpdate(
            expected_revision=outline.revision,
            logline="一座城市用遗忘换取潮汐平静。",
            global_arc="发现、追查、选择并承担。",
            volumes=[
                VolumeOutline(
                    id="volume_001",
                    ordinal=1,
                    title="潮城",
                    objective="确认代价并作出选择",
                    opening_state="真相尚未揭开",
                    closing_state="选择已经完成",
                    target_chapters=chapter_count,
                    target_chars=chapter_count * 1_000,
                )
            ],
            chapters=chapters,
            ending_target="主角公开真相并承担后果。",
            status="ready",
        )
    )

    adapter = AuthorProductionSectionRunner(author)
    production = WholeBookProductionService(
        user_id="production_user",
        novel_id="production_novel",
        data_dir=str(tmp_path),
        section_runner=adapter,
        owner_id="recorded_worker",
        lease_seconds=0,
    )
    return author, adapter, production, custom


def _start(production: WholeBookProductionService):
    return production.start(
        expected_spec_revision=production.specs.load().revision,
        expected_outline_revision=production.outlines.load().revision,
    ).job


def _first_request(
    production: WholeBookProductionService,
    job,
) -> SectionRunRequest:
    authorities = production._load_fresh_authorities(job)
    chapter = production._next_chapter(job, authorities.outline)
    assert chapter is not None
    job, record = production._ensure_chapter(job, chapter, authorities)
    attempt = production._create_attempt(job, record, 1, authorities)
    return production._request_for(attempt)


@pytest.mark.asyncio
async def test_recorded_author_chain_commits_two_chapters_with_frozen_style(
    tmp_path: Path,
) -> None:
    writer = RecordedAuthorWriter()
    author, adapter, production, custom = _configure_domain(tmp_path, writer)
    bible_before = author.bibles.load()
    job = _start(production)

    completed = await production.run(job.id)

    assert completed.status == "completed"
    assert writer.generate_calls == 4
    assert writer.planner_calls == 0
    assert writer.repair_calls == 0
    assert author.bibles.load() == bible_before
    assert [
        (section.chapter, section.section)
        for section in author.sections.list_all()
    ] == [(1, 1), (1, 2), (2, 1), (2, 2)]
    assert [
        (
            goal.production_chapter_ordinal,
            goal.production_section_ordinal,
        )
        for goal in writer.goals
    ] == [(1, 1), (1, 2), (2, 1), (2, 2)]
    assert all(slot["profile_id"] == custom.id for slot in writer.style_slots)
    assert all(slot["profile_revision"] == custom.revision for slot in writer.style_slots)
    assert all(slot["prompt_hash"] == custom.prompt_hash for slot in writer.style_slots)

    transactions = author.transactions.list_all()
    assert len(transactions) == 4
    assert all(transaction.committed for transaction in transactions)
    assert all(transaction.production_context is not None for transaction in transactions)
    assert all(transaction.planner_calls == 0 for transaction in transactions)
    assert all(transaction.writer_calls == 1 for transaction in transactions)
    assert all(transaction.writer_retry_count == 0 for transaction in transactions)
    assert [section.canonical_state_revision for section in author.sections.list_all()] == [
        2,
        3,
        4,
        5,
    ]

    attempts = ProductionSectionAttemptStore(str(tmp_path)).list_all(job_id=job.id)
    first_request = production._request_for(attempts[0])
    first_result = await adapter.run_section(first_request)
    assert first_result.committed is True
    assert writer.generate_calls == 4
    assert author.sections.count() == 4

    changed_style = StyleProfile.model_validate(
        {
            **custom.model_dump(mode="python"),
            "revision": custom.revision + 1,
            "pacing": "明显加速",
            "prompt_hash": "",
        }
    )
    changed_snapshot = first_request.snapshot.model_copy(
        update={"style_profile": changed_style}
    )
    with pytest.raises(
        ProductionSnapshotMismatchError,
        match="does not match replay",
    ):
        await adapter.run_section(
            first_request.model_copy(update={"snapshot": changed_snapshot})
        )


@pytest.mark.asyncio
async def test_stale_outline_snapshot_fails_before_writer_or_author_journal(
    tmp_path: Path,
) -> None:
    writer = RecordedAuthorWriter()
    author, adapter, production, _ = _configure_domain(
        tmp_path,
        writer,
        chapter_count=1,
    )
    request = _first_request(production, _start(production))
    invalid_style = request.snapshot.style_profile.model_copy(
        update={"prompt_hash": "0" * 64}
    )
    invalid_request = request.model_copy(
        update={
            "snapshot": request.snapshot.model_copy(
                update={"style_profile": invalid_style}
            )
        }
    )
    with pytest.raises(
        ProductionSnapshotMismatchError,
        match="prompt hash",
    ):
        await adapter.run_section(invalid_request)

    outline = production.outlines.load()
    production.outlines.update(
        BookOutlineUpdate(
            expected_revision=outline.revision,
            logline="并发编辑后的新梗概。",
        )
    )

    with pytest.raises(
        ProductionSnapshotMismatchError,
        match="BookOutline revision",
    ):
        await adapter.run_section(request)

    assert writer.generate_calls == 0
    assert author.transactions.exists(request.transaction_id) is False
    assert author.sections.count() == 0
    assert author.states.load().revision == 1


@pytest.mark.asyncio
async def test_crash_after_author_commit_replays_exact_transaction_once(
    tmp_path: Path,
) -> None:
    writer = RecordedAuthorWriter()
    author, adapter, production, _ = _configure_domain(
        tmp_path,
        writer,
        chapter_count=1,
    )
    crashed = False

    def crash_once(phase, _attempt, _result) -> None:
        nonlocal crashed
        if phase == "after_runner_commit" and not crashed:
            crashed = True
            raise InjectedProductionCrash()

    production.fault_injector = crash_once
    job = _start(production)
    with pytest.raises(InjectedProductionCrash):
        await production.run(job.id)
    assert writer.generate_calls == 1
    assert author.states.load().revision == 2
    assert author.sections.count() == 1

    recovered_author = AuthorGenerationService(
        user_id="production_user",
        novel_id="production_novel",
        data_dir=str(tmp_path),
        title="潮汐之城",
        writer=writer,
        enable_llm_planner=True,
    )
    recovered = WholeBookProductionService(
        user_id="production_user",
        novel_id="production_novel",
        data_dir=str(tmp_path),
        section_runner=AuthorProductionSectionRunner(recovered_author),
        owner_id="recovered_worker",
        lease_seconds=0,
    )
    completed = await recovered.run(job.id)

    assert completed.status == "completed"
    assert writer.generate_calls == 2
    assert recovered_author.states.load().revision == 3
    assert recovered_author.sections.count() == 2
    assert len({item.transaction_id for item in recovered_author.sections.list_all()}) == 2
    attempts = ProductionSectionAttemptStore(str(tmp_path)).list_all(job_id=job.id)
    assert len(attempts) == 2
    assert all(attempt.status == "committed" for attempt in attempts)


@pytest.mark.asyncio
async def test_rejected_author_candidate_never_exposes_or_commits_prose(
    tmp_path: Path,
) -> None:
    writer = RecordedAuthorWriter(reject=True)
    author, adapter, production, _ = _configure_domain(
        tmp_path,
        writer,
        chapter_count=1,
    )
    request = _first_request(production, _start(production))

    result = await adapter.run_section(request)

    assert result.committed is False
    assert result.content == ""
    assert result.char_count == 0
    assert result.error_code == "GENERATION_REJECTED"
    assert writer.generate_calls == 1
    assert writer.repair_calls == 1
    rejected = author.transactions.load(request.transaction_id)
    assert rejected.phase == "rejected"
    assert rejected.writer_calls == 2
    assert rejected.writer_retry_count == 0
    assert rejected.repair_performed is True
    adapter._assert_call_budget(rejected)
    with pytest.raises(
        ProductionAdapterInvariantError,
        match="frozen plan's targeted provider repair",
    ):
        adapter._assert_call_budget(rejected.model_copy(update={"writer_calls": 1}))
    assert author.sections.count() == 0
    assert author.states.load().revision == 1


@pytest.mark.asyncio
async def test_author_commit_pending_is_recoverable_with_the_same_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    writer = RecordedAuthorWriter()
    author, adapter, production, _ = _configure_domain(
        tmp_path,
        writer,
        chapter_count=1,
    )
    request = _first_request(production, _start(production))
    original_save = author.memories.save
    calls = 0

    def fail_once(value):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("recorded commit interruption")
        return original_save(value)

    monkeypatch.setattr(author.memories, "save", fail_once)
    with pytest.raises(SectionCommitPending):
        await adapter.run_section(request)
    assert writer.generate_calls == 1
    assert author.states.load().revision == 2
    assert author.sections.count() == 0

    monkeypatch.setattr(author.memories, "save", original_save)
    recovered_author = AuthorGenerationService(
        user_id="production_user",
        novel_id="production_novel",
        data_dir=str(tmp_path),
        title="潮汐之城",
        writer=writer,
        enable_llm_planner=True,
    )
    result = await AuthorProductionSectionRunner(recovered_author).run_section(
        request
    )

    assert result.committed is True
    assert writer.generate_calls == 1
    assert recovered_author.sections.count() == 1
    assert recovered_author.states.load().revision == 2


@pytest.mark.asyncio
async def test_legacy_author_request_keeps_unpositioned_single_section_behavior(
    tmp_path: Path,
) -> None:
    writer = RecordedAuthorWriter()
    author = AuthorGenerationService(
        user_id="legacy_user",
        novel_id="legacy_novel",
        data_dir=str(tmp_path),
        title="旧作品",
        writer=writer,
    )
    bible = author.bibles.load()
    author.bibles.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            premise="旧作品继续生成。",
            theme="选择",
            setting_summary="一座旧城。",
            immutable_world_rules=["死亡不可逆"],
        )
    )
    goal = SectionGoal(
        objective="主角确认选择并承担代价",
        desired_length=400,
    )

    transaction = await author.run(goal, request_id="legacy_single")

    assert transaction.committed is True
    assert transaction.production_context is None
    section = author.sections.get_by_id(transaction.id)
    assert section is not None
    assert (section.chapter, section.section) == (1, 1)
    assert section.section_goal["production_chapter_ordinal"] == 0
    assert section.section_goal["production_section_ordinal"] == 0
