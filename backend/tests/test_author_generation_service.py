from __future__ import annotations

from pathlib import Path

import pytest

from nf_core.provider_runtime import ProviderError, ProviderRuntimeConfig
from sections.section_store import _clear_for_tests
from story.models import (
    SectionGoal,
    StateDeltaOperation,
    StoryBibleUpdate,
    WriterCandidate,
)
from story.persistence import StoryBibleStore
from story.repair_patch import (
    ProviderRepairPatch,
    ProviderRepairPatchSet,
    RepairPatchSet,
)
from story.repair_plan import repair_patch_prompt_payload
from story.service import (
    AuthorGenerationService,
    CommitPendingError,
    GenerationRejected,
    StaleStoryBibleError,
)
from story.writer import AuthorWriter, WriterResult


class FakeWriter:
    def __init__(
        self,
        generated: WriterCandidate,
        repaired: WriterCandidate | None = None,
        *,
        repair_patches: RepairPatchSet | None = None,
    ):
        self.generated = generated
        self.repaired = repaired or generated
        self.repair_patches = repair_patches
        self.generate_calls = 0
        self.repair_calls = 0

    async def generate(self, context, goal):
        self.generate_calls += 1
        assert "story_bible" in context.slots
        assert context.writing_plan is not None
        assert context.section_budget_plan is not None
        assert "section_writing_plan" not in context.slots["narrative_contract"]
        assert "section_budget_plan" not in context.slots["narrative_contract"]
        return WriterResult(
            self.generated,
            {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )

    async def repair(self, candidate, report):
        self.repair_calls += 1
        prompt_payload = repair_patch_prompt_payload(
            report,
            candidate.narrative_text,
        )
        provider_patches: list[ProviderRepairPatch] = []
        for request in prompt_payload["provider_patch_requests"]:
            source = (
                "风沿着旧城墙缓缓移动，主角没有离开，只把眼前已经发生的选择重新看清。"
            )
            target = request["target_chars"]
            patch_text = (source * ((target + len(source) - 1) // len(source)))[:target]
            provider_patches.append(
                ProviderRepairPatch(
                    patch_id=request["patch_id"],
                    patch_text=patch_text,
                )
            )
        return WriterResult(
            candidate,
            {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
            repair_patches=(
                self.repair_patches
                if self.repair_patches is not None
                else None
            ),
            provider_repair_patches=(
                None
                if self.repair_patches is not None
                else ProviderRepairPatchSet(patches=provider_patches)
            ),
        )


class ProviderReceiptWriter(FakeWriter):
    async def generate(self, context, goal):
        result = await super().generate(context, goal)
        return WriterResult(
            candidate=result.candidate,
            usage=result.usage,
            provider="custom",
            provider_model="glm-5.2",
            provider_source="provider_file",
            provider_config_fingerprint="0123456789abcdef",
            writer_block_nonspace_lengths=[40] * 10,
            writer_cell_nonspace_lengths=[7] * 51 + [43],
            writer_cell_sentence_boundary_counts=[1] * 52,
        )


class FormatRecoveredWriter(FakeWriter):
    async def generate(self, context, goal):
        result = await super().generate(context, goal)
        return WriterResult(
            candidate=result.candidate,
            usage=result.usage,
            structured_output_repair_count=1,
            primary_output_contract_pass=False,
            audit_codes=["WRITER_FORMAT_RECOVERY_USED"],
        )


class RepairFormatRecoveredWriter(FakeWriter):
    async def repair(self, candidate, report):
        result = await super().repair(candidate, report)
        return WriterResult(
            candidate=result.candidate,
            usage=result.usage,
            structured_output_repair_count=1,
            provider_repair_patches=result.provider_repair_patches,
        )


class ProviderFailureWriter(FakeWriter):
    def __init__(
        self,
        generated: WriterCandidate,
        error: ProviderError,
        *,
        fail_stage: str,
    ) -> None:
        super().__init__(generated)
        self.provider_error = error
        self.fail_stage = fail_stage

    async def generate(self, context, goal):
        if self.fail_stage == "writer":
            raise AuthorWriter._annotate_provider_failure(
                self.provider_error,
                stage="writer",
                primary_calls=1,
                structured_calls=0,
            )
        result = await super().generate(context, goal)
        config = self.provider_error.config
        return WriterResult(
            candidate=result.candidate,
            usage=result.usage,
            provider=config.provider,
            provider_model=config.model,
            provider_source=config.source,
            provider_config_fingerprint=config.config_fingerprint,
        )

    async def repair(self, candidate, report):
        del candidate, report
        raise AuthorWriter._annotate_provider_failure(
            self.provider_error,
            stage=self.fail_stage,
            primary_calls=1,
            structured_calls=int(self.fail_stage == "repair_json_repair"),
        )


@pytest.fixture(autouse=True)
def clear_sections():
    _clear_for_tests()
    yield
    _clear_for_tests()


def _goal() -> SectionGoal:
    return SectionGoal(
        objective="让主角以一次选择回应身份与牺牲。",
        desired_length=400,
    )


def _valid_candidate(text: str = "") -> WriterCandidate:
    narrative = text or ("主角确认自己的身份，并选择为同伴承担牺牲的代价。" * 20)
    return WriterCandidate(
        narrative_text=narrative,
        title="代价",
        section_summary="主角以牺牲回应身份冲突。",
    )


def _service(tmp_path: Path, writer: FakeWriter) -> AuthorGenerationService:
    service = AuthorGenerationService(
        user_id="alice",
        novel_id="novel",
        data_dir=str(tmp_path),
        title="测试小说",
        writer=writer,
    )
    bible = service.bibles.load()
    service.bibles.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            premise="一名失忆者守护旧城。",
            theme="身份与牺牲",
            setting_summary="封闭的旧城。",
            immutable_world_rules=["死亡不可逆"],
        )
    )
    return service


@pytest.mark.asyncio
async def test_author_service_commits_one_writer_call_and_persists_long_memory(
    tmp_path: Path,
) -> None:
    writer = FakeWriter(_valid_candidate())
    service = _service(tmp_path, writer)

    tx = await service.run(_goal(), request_id="req_one")

    assert tx.committed is True
    assert tx.writer_calls == 1
    assert tx.repair_performed is False
    assert tx.story_bible_revision == 2
    assert service.states.load().revision == 2
    assert service.sections.count() == 1
    assert "section_summary_" + tx.section_id in service.memories.load().records
    assert service.manifests.load().slots[0].name == "story_bible"
    assert writer.generate_calls == 1

    retried = await service.run(_goal(), request_id="req_one")
    assert retried.id == tx.id
    assert service.sections.count() == 1
    assert writer.generate_calls == 1


@pytest.mark.asyncio
async def test_format_recovered_content_is_not_counted_as_writer_first_pass(
    tmp_path: Path,
) -> None:
    writer = FormatRecoveredWriter(_valid_candidate())
    service = _service(tmp_path, writer)

    transaction = await service.run(_goal(), request_id="format_first_pass")

    assert transaction.committed is True
    assert transaction.writer_first_pass_pass is False
    assert transaction.structured_output_repair_count == 1
    assert "WRITER_FORMAT_RECOVERY_USED" in transaction.repair_audit_codes


@pytest.mark.asyncio
async def test_author_transaction_records_only_safe_provider_receipt(
    tmp_path: Path,
) -> None:
    writer = ProviderReceiptWriter(_valid_candidate())
    service = _service(tmp_path, writer)

    transaction = await service.run(_goal(), request_id="provider_receipt")

    assert transaction.provider == "custom"
    assert transaction.provider_model == "glm-5.2"
    assert transaction.provider_source == "provider_file"
    assert transaction.provider_config_fingerprint == "0123456789abcdef"
    assert transaction.provider_config_fingerprints == ["0123456789abcdef"]
    assert transaction.writer_block_nonspace_lengths == [40] * 10
    assert transaction.writer_cell_nonspace_lengths == [7] * 51 + [43]
    assert transaction.writer_cell_sentence_boundary_counts == [1] * 52
    serialized = transaction.model_dump_json()
    assert "api_key" not in serialized
    assert "base_url" not in serialized


@pytest.mark.asyncio
async def test_provider_failure_journal_is_secret_free_and_counts_direct_call(
    tmp_path: Path,
) -> None:
    secret = "test-only-journal-secret"
    endpoint = "https://journal-provider.invalid/v1"
    config = ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key=secret,
        base_url=endpoint,
        model="glm-5.2",
        thinking_mode="disabled",
        max_retries=0,
        source="provider_file",
    )
    error = ProviderError(
        code="PROVIDER_UNAVAILABLE",
        message=f"raw body with {secret} and {endpoint}",
        http_status=502,
        http_category="unavailable",
        config=config,
    )
    service = _service(
        tmp_path,
        ProviderFailureWriter(_valid_candidate(), error, fail_stage="writer"),
    )

    with pytest.raises(ProviderError):
        await service.run(_goal(), request_id="provider_direct_failure")

    transaction = service.transactions.load("provider_direct_failure")
    serialized = transaction.model_dump_json()
    assert transaction.phase == "failed"
    assert transaction.error_code == "PROVIDER_UNAVAILABLE"
    assert transaction.error == "generation failed; provider response omitted"
    assert transaction.provider_error_category == "unavailable"
    assert transaction.provider_error_stage == "writer"
    assert transaction.planner_calls == 0
    assert transaction.writer_calls == 1
    assert transaction.structured_output_repair_count == 0
    assert transaction.provider_config_fingerprint == config.config_fingerprint
    assert secret not in serialized
    assert endpoint not in serialized
    assert "raw body" not in serialized


@pytest.mark.asyncio
async def test_repair_json_provider_failure_counts_each_call_once(
    tmp_path: Path,
) -> None:
    config = ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key="test-only",
        base_url="https://provider.invalid/v1",
        model="glm-5.2",
        thinking_mode="disabled",
        max_retries=0,
        source="provider_file",
    )
    error = ProviderError(
        code="PROVIDER_OUTPUT_INVALID",
        message="raw malformed payload",
        http_status=502,
        http_category="output_invalid",
        config=config,
    )
    too_short = _valid_candidate(
        "主角确认自己的身份，并选择为同伴承担牺牲的代价。" * 7
    )
    service = _service(
        tmp_path,
        ProviderFailureWriter(
            too_short,
            error,
            fail_stage="repair_json_repair",
        ),
    )

    with pytest.raises(ProviderError):
        await service.run(_goal(), request_id="provider_repair_failure")

    transaction = service.transactions.load("provider_repair_failure")
    assert transaction.phase == "failed"
    assert transaction.provider_error_stage == "repair_json_repair"
    assert transaction.planner_calls == 0
    assert transaction.writer_calls == 2
    assert transaction.structured_output_repair_count == 1

@pytest.mark.asyncio
async def test_author_service_repairs_once_then_commits(tmp_path: Path) -> None:
    bad = _valid_candidate(
        "主角确认自己的身份，并选择为同伴承担牺牲的代价。" * 7
    ).model_copy(
        update={
            "state_delta": [
                StateDeltaOperation(
                    op="set",
                    path="/story_bible/theme",
                    value="升级",
                    evidence="失去意义",
                )
            ]
        }
    )
    writer = FakeWriter(bad, _valid_candidate())
    service = _service(tmp_path, writer)

    tx = await service.run(_goal(), request_id="req_repair")

    assert tx.committed is True
    assert tx.writer_calls == 2
    assert tx.repair_performed is True
    assert writer.generate_calls == 1
    assert writer.repair_calls == 1
    assert tx.usage["total_tokens"] == 200
    assert tx.usage["repair_tokens"] == 50


@pytest.mark.asyncio
async def test_format_recovery_exhausts_the_second_call_before_prose_repair(
    tmp_path: Path,
) -> None:
    too_short = _valid_candidate(
        "主角确认自己的身份，并选择为同伴承担牺牲的代价。" * 7
    )
    writer = FormatRecoveredWriter(too_short)
    service = _service(tmp_path, writer)

    with pytest.raises(GenerationRejected) as error:
        await service.run(_goal(), request_id="format_then_length")

    transaction = error.value.transaction
    assert writer.generate_calls == 1
    assert writer.repair_calls == 0
    assert transaction.writer_calls == 1
    assert transaction.structured_output_repair_count == 1
    assert "REPAIR_CALL_BUDGET_EXHAUSTED" in transaction.repair_audit_codes
    assert "PATCH_ID_MISSING" in {
        item.code for item in transaction.repair_patch_report.violations
    }


@pytest.mark.asyncio
async def test_repair_format_recovery_cannot_commit_after_three_provider_calls(
    tmp_path: Path,
) -> None:
    too_short = _valid_candidate(
        "主角确认自己的身份，并选择为同伴承担牺牲的代价。" * 7
    )
    writer = RepairFormatRecoveredWriter(too_short)
    service = _service(tmp_path, writer)

    with pytest.raises(GenerationRejected) as error:
        await service.run(_goal(), request_id="repair_format_budget")

    transaction = error.value.transaction
    assert writer.generate_calls == 1
    assert writer.repair_calls == 1
    assert transaction.writer_calls == 2
    assert transaction.structured_output_repair_count == 1
    assert "PROVIDER_CALL_BUDGET_EXCEEDED" in transaction.repair_audit_codes
    assert transaction.committed is False
    assert service.states.load().revision == 1
    assert service.sections.count() == 0


@pytest.mark.asyncio
async def test_author_service_rejects_after_single_failed_repair_without_half_commit(
    tmp_path: Path,
) -> None:
    bad = _valid_candidate(
        "主角确认自己的身份，并选择为同伴承担牺牲的代价。" * 7
    ).model_copy(
        update={
            "state_delta": [
                StateDeltaOperation(
                    op="set",
                    path="/story_bible/theme",
                    value="升级",
                    evidence="失去意义",
                )
            ]
        }
    )
    writer = FakeWriter(bad, bad, repair_patches=RepairPatchSet())
    service = _service(tmp_path, writer)

    with pytest.raises(GenerationRejected) as error:
        await service.run(_goal(), request_id="req_reject")

    assert error.value.transaction.phase == "rejected"
    assert error.value.transaction.writer_calls == 2
    assert service.states.load().revision == 1
    assert service.sections.count() == 0
    assert writer.repair_calls == 1


@pytest.mark.asyncio
async def test_commit_failure_recovers_without_duplicate_section(
    tmp_path: Path, monkeypatch
) -> None:
    writer = FakeWriter(_valid_candidate())
    service = _service(tmp_path, writer)
    original_save = service.memories.save
    calls = {"count": 0}

    def fail_once(value):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("simulated disk interruption")
        return original_save(value)

    monkeypatch.setattr(service.memories, "save", fail_once)
    with pytest.raises(CommitPendingError):
        await service.run(_goal(), request_id="req_recover")

    assert service.states.load().revision == 2
    assert service.sections.count() == 0

    # A fresh process/runtime scans the journal and rolls the staged transaction forward.
    recovered = AuthorGenerationService(
        user_id="alice",
        novel_id="novel",
        data_dir=str(tmp_path),
        title="测试小说",
        writer=FakeWriter(_valid_candidate()),
    )
    transaction = recovered.transactions.load("req_recover")
    assert transaction.committed is True
    assert recovered.sections.count() == 1
    assert recovered.states.load().revision == 2
    assert recovered.memories.load().revision == 2


@pytest.mark.asyncio
async def test_story_bible_is_unchanged_after_generation_commit(tmp_path: Path) -> None:
    writer = FakeWriter(_valid_candidate())
    service = _service(tmp_path, writer)
    before = StoryBibleStore(str(tmp_path)).load()
    await service.run(_goal(), request_id="req_bible_unchanged")
    after = StoryBibleStore(str(tmp_path)).load()
    assert before.revision == 2
    assert before.theme == "身份与牺牲"
    assert after == before


@pytest.mark.asyncio
async def test_missing_evidence_delta_is_never_committed(tmp_path: Path) -> None:
    candidate = _valid_candidate().model_copy(
        update={
            "state_delta": [
                StateDeltaOperation(
                    op="set", path="/world/weather", value="暴雨", evidence=""
                )
            ]
        }
    )
    service = _service(tmp_path, FakeWriter(candidate, candidate))
    tx = await service.run(_goal(), request_id="missing_evidence")
    assert tx.committed is True
    assert "weather" not in service.states.load().world
    assert tx.validation_report is not None
    assert tx.validation_report.validated_delta == []


@pytest.mark.asyncio
async def test_repair_must_revalidate_delta_against_repaired_prose(tmp_path: Path) -> None:
    operation = StateDeltaOperation(
        op="set",
        path="/world/weather",
        value="暴雨",
        evidence="旧城骤然落下暴雨",
    )
    original = _valid_candidate(
        "主角确认自己的身份，并选择为同伴承担牺牲的代价。" * 7
    ).model_copy(
        update={"state_delta": [operation]}
    )
    repaired = _valid_candidate()
    service = _service(tmp_path, FakeWriter(original, repaired))
    tx = await service.run(_goal(), request_id="revalidate_repair")
    assert tx.committed is True
    assert "weather" not in service.states.load().world
    assert tx.validation_report.validated_delta == []
    assert tx.validation_report.dropped_delta_count == 1


@pytest.mark.asyncio
async def test_unnarrated_state_change_is_dropped_without_prose_repair(
    tmp_path: Path,
) -> None:
    operation = StateDeltaOperation(
        op="set",
        path="/world/weather",
        value="暴雨",
        evidence="旧城骤然落下暴雨",
    )
    candidate = _valid_candidate().model_copy(update={"state_delta": [operation]})
    service = _service(tmp_path, FakeWriter(candidate, candidate))
    transaction = await service.run(_goal(), request_id="unnarrated_after_repair")
    assert transaction.committed is True
    assert transaction.repair_performed is False
    assert transaction.validation_report.dropped_delta_count == 1
    assert "weather" not in service.states.load().world
    assert service.sections.count() == 1


@pytest.mark.asyncio
async def test_multiple_deltas_only_commit_individually_valid_operations(
    tmp_path: Path,
) -> None:
    candidate = _valid_candidate(
        "旧城骤然落下暴雨，主角为身份与牺牲承担代价。" * 10
    ).model_copy(
        update={
            "state_delta": [
                StateDeltaOperation(
                    op="set",
                    path="/world/weather",
                    value="暴雨",
                    evidence="旧城骤然落下暴雨",
                ),
                StateDeltaOperation(
                    op="set", path="/world/current_season", value="冬", evidence=""
                ),
            ]
        }
    )
    service = _service(tmp_path, FakeWriter(candidate, candidate))
    await service.run(_goal(), request_id="mixed_deltas")
    state = service.states.load()
    assert state.world["weather"] == "暴雨"
    assert "current_season" not in state.world


class BibleChangingWriter(FakeWriter):
    def __init__(self, generated: WriterCandidate):
        super().__init__(generated)
        self.service = None

    async def generate(self, context, goal):
        result = await super().generate(context, goal)
        bible = self.service.bibles.load()
        self.service.bibles.update(
            StoryBibleUpdate(
                expected_revision=bible.revision,
                title=bible.title,
                source_seed=bible.source_seed,
                theme_key=bible.theme_key,
                positioning=bible.positioning,
                reference_preferences=bible.reference_preferences,
                premise=bible.premise,
                theme="变化后的主题",
                setting_summary=bible.setting_summary,
                immutable_world_rules=bible.immutable_world_rules,
                style_contract=bible.style_contract,
            )
        )
        return result


@pytest.mark.asyncio
async def test_story_bible_revision_change_blocks_commit(tmp_path: Path) -> None:
    writer = BibleChangingWriter(_valid_candidate())
    service = _service(tmp_path, writer)
    writer.service = service
    with pytest.raises(StaleStoryBibleError) as error:
        await service.run(_goal(), request_id="stale_bible")
    assert error.value.transaction.phase == "stale_context"
    assert error.value.transaction.error_code == "STORY_BIBLE_REVISION_STALE"
    assert service.states.load().revision == 1
    assert service.threads.load().revision == 1
    assert service.memories.load().revision == 1
    assert service.sections.count() == 0


@pytest.mark.asyncio
async def test_story_bible_change_does_not_partially_commit(tmp_path: Path) -> None:
    writer = BibleChangingWriter(_valid_candidate())
    service = _service(tmp_path, writer)
    writer.service = service
    before = (
        service.states.load(),
        service.threads.load(),
        service.memories.load(),
    )
    with pytest.raises(StaleStoryBibleError):
        await service.run(_goal(), request_id="stale_no_partial")
    assert service.states.load() == before[0]
    assert service.threads.load() == before[1]
    assert service.memories.load() == before[2]
    assert service.sections.count() == 0


class StyleChangingWriter(FakeWriter):
    def __init__(self, generated: WriterCandidate):
        super().__init__(generated)
        self.service = None

    async def generate(self, context, goal):
        result = await super().generate(context, goal)
        bible = self.service.bibles.load()
        self.service.bibles.update_style(
            expected_revision=bible.revision,
            style_contract={"key": "literary", "version": "test"},
            positioning="新风格",
            references="测试参考",
        )
        return result


@pytest.mark.asyncio
async def test_author_style_change_invalidates_inflight_transaction(
    tmp_path: Path,
) -> None:
    writer = StyleChangingWriter(_valid_candidate())
    service = _service(tmp_path, writer)
    writer.service = service
    with pytest.raises(StaleStoryBibleError) as error:
        await service.run(_goal(), request_id="style_stale")
    assert error.value.transaction.error_code == "STORY_BIBLE_REVISION_STALE"
    assert service.sections.count() == 0


@pytest.mark.asyncio
async def test_stale_bible_transaction_can_be_safely_retried_with_new_request(
    tmp_path: Path,
) -> None:
    writer = BibleChangingWriter(_valid_candidate())
    service = _service(tmp_path, writer)
    writer.service = service
    with pytest.raises(StaleStoryBibleError):
        await service.run(_goal(), request_id="stale_old")
    service.writer = FakeWriter(_valid_candidate())
    fresh = await service.run(_goal(), request_id="stale_fresh")
    assert fresh.committed is True
    assert service.sections.count() == 1


@pytest.mark.asyncio
async def test_recover_rejects_staged_transaction_after_bible_change(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, FakeWriter(_valid_candidate()))
    prepared = service.prepare(_goal(), request_id="recover_stale")
    generated = await service.generate(prepared)
    tx = service._record_generated(prepared.transaction, generated)
    report = service.validate(prepared, generated.candidate)
    staged = service._stage(prepared, tx, generated.candidate, report)
    bible = service.bibles.load()
    service.bibles.update(
        StoryBibleUpdate(
            expected_revision=bible.revision,
            title=bible.title,
            premise=bible.premise,
            theme="重启前改变",
            setting_summary=bible.setting_summary,
        )
    )
    recovered = AuthorGenerationService(
        user_id="alice",
        novel_id="novel",
        data_dir=str(tmp_path),
        title="测试小说",
        writer=FakeWriter(_valid_candidate()),
    )
    stale = recovered.transactions.load(staged.id)
    assert stale.phase == "stale_context"
    assert stale.error_code == "STORY_BIBLE_REVISION_STALE"
    assert recovered.states.load().revision == 1
    assert recovered.sections.count() == 0
