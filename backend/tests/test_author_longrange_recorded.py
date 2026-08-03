from __future__ import annotations

import json
import hashlib

import pytest

from nf_core.provider_runtime import ProviderError, ProviderRuntimeConfig
from scripts.analyze_author_longrange import analyze
from scripts.run_author_longrange import RunLimits, _constraints, _safe_error, run_sequence
from story.models import CanonicalState, SectionGoal, StoryBible
from story.narrative_contract import NarrativeContractBuilder
from story.narrative_validator import NarrativeContractValidator
from story.writer import AuthorWriter


def _limits(max_sections: int) -> RunLimits:
    return RunLimits(
        max_sections=max_sections,
        max_total_tokens=0,
        max_cost=0.0,
        prompt_cost_per_million=0.0,
        completion_cost_per_million=0.0,
    )


def test_safe_error_keeps_only_allowlisted_provider_failure_metadata() -> None:
    secret = "test-only-super-secret-provider-key"
    endpoint = "https://provider-secret.invalid/v1"
    config = ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key=secret,
        base_url=endpoint,
        model="glm-5.2",
        thinking_mode="disabled",
        max_retries=0,
    )
    error = ProviderError(
        code="PROVIDER_UNAVAILABLE",
        message=f"raw upstream body {secret} from {endpoint}",
        http_status=502,
        http_category="unavailable",
        config=config,
        upstream_status=503,
    )
    AuthorWriter._annotate_provider_failure(
        error,
        stage="writer_json_repair",
        primary_calls=1,
        structured_calls=1,
    )

    safe = _safe_error(error)
    rendered = json.dumps(safe, ensure_ascii=False)

    assert safe == {
        "provider_failure": True,
        "provider_code": "PROVIDER_UNAVAILABLE",
        "provider_http_category": "unavailable",
        "provider_stage": "writer_json_repair",
        "planner_calls": 0,
        "writer_calls": 1,
        "structured_output_repair_count": 1,
        "provider_call_count": 2,
        "provider_call_count_known": True,
        "runtime_provider": "custom",
        "runtime_provider_model": "glm-5.2",
        "runtime_provider_source": "explicit",
        "runtime_provider_config_fingerprint": config.config_fingerprint,
    }
    assert secret not in rendered
    assert endpoint not in rendered

    non_provider = _safe_error(RuntimeError(f"internal {secret} at {endpoint}"))
    assert non_provider == {
        "provider_failure": False,
        "planner_calls": 0,
        "writer_calls": 0,
        "structured_output_repair_count": 0,
        "provider_call_count": 0,
        "provider_call_count_known": False,
    }
    assert secret not in json.dumps(non_provider)


def test_longrange_holder_evidence_accepts_natural_put_away_wording() -> None:
    contract = NarrativeContractBuilder().build(
        story_bible=StoryBible(premise="旧信交接", theme="责任", setting_summary="灯塔"),
        canonical_state=CanonicalState(
            characters={
                "shen_yan": {"name": "沈砚"},
                "lin_qiu": {"name": "林秋"},
            },
            items={"letter": {"name": "旧信", "holder": "lin_qiu"}},
        ),
        section_goal=SectionGoal(
            section_id="natural_holder",
            objective="林秋核对第三处记录并继续保管旧信",
            involved_characters=["shen_yan", "lin_qiu"],
            desired_length=300,
            narrative_constraints=_constraints(3, min_chars=10, max_chars=1000),
        ),
        story_threads=[],
    )
    prose = (
        "林秋从侧袋里抽出旧信，核对旧信第三处记录。"
        "她把信纸重新折好，将信滑进侧袋，确认拉链合拢。"
    )
    report = NarrativeContractValidator().validate(contract, prose)
    assert report.accepted is True
    assert report.required_end_state_coverage == 1.0


def test_real_provider_wrapper_alias_regression_is_not_false_rejected() -> None:
    prose = (
        "灯塔的玻璃罩里还蓄着昨夜的海雾，水珠沿着铜框往下走，一滴一滴落在林秋的袖口上。"
        "她没擦，只把手指按在透镜基座的铸铁接缝处，感受那层薄薄的锈。沈砚从梯口上来，"
        "靴底在铁格栅上踩出闷响，每一声都像在数什么。他怀里掏出一只油纸封，边角已经磨得发毛，"
        "纸面上洇着深浅不一的潮痕。“第七节，最后一段。”他说，把封套搁在透镜的检修台上，"
        "纸与铁板碰出干涩的摩擦声。林秋转过身，看见封套上那行褪成灰褐色的字迹，像被盐水泡过"
        "又晒干的贝壳。她伸手去接，指尖先触到纸的毛边，然后是沈砚留在上面的体温。封套滑进她"
        "侧袋时，油纸在布料上蹭出细碎的窸窣，像远处礁石间退潮的余响。她按住袋口，隔着布料"
        "感觉到那封旧信硬挺的边角正抵着掌心。"
    )
    assert hashlib.sha256(prose.encode("utf-8")).hexdigest() == (
        "ecb082e82c57224da9dab934ddd57d136e85da1d26c0f3fcf9ced62de7e65945"
    )
    contract = NarrativeContractBuilder().build(
        story_bible=StoryBible(premise="旧信交接", theme="责任", setting_summary="灯塔"),
        canonical_state=CanonicalState(
            characters={
                "shen_yan": {"name": "沈砚"},
                "lin_qiu": {"name": "林秋"},
            },
            items={"letter": {"name": "旧信", "holder": "shen_yan"}},
        ),
        section_goal=SectionGoal(
            section_id="real_alias",
            objective="沈砚把旧信交给林秋",
            involved_characters=["shen_yan", "lin_qiu"],
            desired_length=400,
            narrative_constraints=_constraints(1, min_chars=200, max_chars=800),
        ),
        story_threads=[],
    )
    assert NarrativeContractValidator().validate(contract, prose).accepted is True


@pytest.mark.asyncio
async def test_recorded_longrange_repair_checkpoint_recovery_and_sample_replay(
    tmp_path,
) -> None:
    output_dir = tmp_path / "stage0"
    report = await run_sequence(
        output_dir=output_dir,
        mode="recorded",
        style="literary",
        theme="reality_mystery",
        seed=20260722,
        desired_length=300,
        checkpoint_every=2,
        limits=_limits(6),
        resume=False,
    )

    assert report["summary"]["committed"] == 6
    assert report["summary"]["contract_pass_rate"] == 1.0
    assert report["summary"]["repairs"] == 1
    assert report["summary"]["total_tokens"] == 0
    assert report["summary"]["runtime_rebuilds"] == 2
    assert report["config"]["provider"] == "recorded"
    assert report["config"]["model"] == "recorded"
    assert report["config"]["desired_length"] == 300
    assert report["recovery_evidence"]["clean_staged_recovery"]["passed"] is True
    assert report["recovery_evidence"]["stale_staged_rejected"]["passed"] is True
    assert len(report["real_sample_replay"]) == 5
    assert all(
        not item["accepted"] for item in report["real_sample_replay"].values()
    )
    assert (output_dir / "checkpoint.json").is_file()
    assert (output_dir / "checkpoints" / "section_0006.json").is_file()
    primary_samples = [
        path
        for path in (output_dir / "samples").glob("section_*.txt")
        if "_repair_" not in path.name
    ]
    assert len(primary_samples) == 6
    assert (output_dir / "samples" / "section_0004_repair_before.txt").is_file()
    assert (output_dir / "samples" / "section_0004_repair_after.txt").is_file()
    first = report["sections"][0]
    assert first["story_bible_revision"] >= 1
    assert {
        item["story_bible_revision"] for item in report["sections"]
    } == {first["story_bible_revision"]}
    assert first["canonical_revision_before"] == 1
    assert first["canonical_revision_after"] == 2
    assert first["provider"] == first["model"] == "recorded"
    assert first["contract_hash"]
    assert first["context_contract_hash"] == first["contract_hash"]
    assert first["execution_spec_hash"]
    assert first["context_active_thread_ids"] == ["main_letter"]
    assert first["context_total_tokens"] <= first["context_max_tokens"]
    assert all(item["selection_reason"] for item in first["memory_selections"])
    discarded = {
        item["memory_id"]: item["reason"] for item in first["memory_discards"]
    }
    assert discarded["memory_stale_holder"] == "canon_status_superseded"
    assert discarded["memory_item_holder"] == "canonical_conflict"
    assert first["required_events"]
    assert first["completed_events"] == first["required_events"]
    assert first["missing_events"] == []
    assert first["contract_result"] is True
    assert first["committed_delta_count"] == len(first["committed_delta"])
    assert isinstance(first["rejected_delta"], list)
    assert set(first["thread_changes"]) == {"opened", "advanced", "resolved"}
    assert first["committed_thread_changes"] == []
    assert first["memory_records_added"] >= 1
    assert f"section_summary_{first['section_id']}" in first[
        "memory_record_ids_added"
    ]
    assert first["initial_narrative_length"] == first["initial_length_report"]["chars"]
    assert first["illegal_thread_change_commits"] == 0
    assert first["evidenceless_state_delta_commits"] == 0
    repaired = report["sections"][3]
    assert repaired["repair_patch_nonspace_lengths"]
    assert sum(repaired["repair_patch_nonspace_lengths"]) == repaired[
        "repair_patch_total_nonspace_chars"
    ]
    assert repaired["repair_patch_max_nonspace_chars"] == max(
        repaired["repair_patch_nonspace_lengths"]
    )
    assert analyze(report)["gate"] == "STAGE0_PASS"
    bible = json.loads(
        (output_dir / "runtime" / "story_bible.json").read_text(encoding="utf-8")
    )
    assert bible["theme_key"] == "reality_mystery"


@pytest.mark.asyncio
async def test_recorded_longrange_resume_has_no_duplicate_sections(tmp_path) -> None:
    output_dir = tmp_path / "resume"
    await run_sequence(
        output_dir=output_dir,
        mode="recorded",
        style="literary",
        theme="reality_mystery",
        seed=7,
        desired_length=300,
        checkpoint_every=2,
        limits=_limits(4),
        resume=False,
    )
    resumed = await run_sequence(
        output_dir=output_dir,
        mode="recorded",
        style="literary",
        theme="reality_mystery",
        seed=7,
        desired_length=300,
        checkpoint_every=2,
        limits=_limits(6),
        resume=True,
    )

    ids = [item["section_id"] for item in resumed["sections"]]
    transaction_ids = [item["transaction_id"] for item in resumed["sections"]]
    assert len(ids) == len(set(ids)) == 6
    assert len(transaction_ids) == len(set(transaction_ids)) == 6
    assert resumed["summary"]["committed"] == 6
    assert resumed["recovery_evidence"]["canonical_revision_contiguous"] is True
    on_disk = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert on_disk["config"]["max_sections"] == 6


@pytest.mark.asyncio
async def test_id_namespace_is_bound_to_run_transaction_and_section_ids(tmp_path) -> None:
    reports = []
    for namespace in ("g1_action_conflict_literary", "g2_action_conflict_literary"):
        reports.append(
            await run_sequence(
                output_dir=tmp_path / namespace,
                mode="recorded",
                style="literary",
                theme="action_conflict",
                seed=7,
                desired_length=300,
                checkpoint_every=1,
                limits=_limits(2),
                resume=False,
                id_namespace=namespace,
            )
        )

    left, right = reports
    assert left["config"]["id_namespace"] == "g1_action_conflict_literary"
    assert right["config"]["id_namespace"] == "g2_action_conflict_literary"
    assert left["run_id"] == (
        "author-g1_action_conflict_literary-recorded-action_conflict-literary-7"
    )
    assert right["run_id"] == (
        "author-g2_action_conflict_literary-recorded-action_conflict-literary-7"
    )
    assert [item["transaction_id"] for item in left["sections"]] == [
        "g1_action_conflict_literary_section_0001",
        "g1_action_conflict_literary_section_0002",
    ]
    assert [item["section_id"] for item in left["sections"]] == [
        "g1_action_conflict_literary_section_0001",
        "g1_action_conflict_literary_section_0002",
    ]
    assert {
        item["transaction_id"] for item in left["sections"]
    }.isdisjoint(item["transaction_id"] for item in right["sections"])
    assert {
        item["section_id"] for item in left["sections"]
    }.isdisjoint(item["section_id"] for item in right["sections"])


@pytest.mark.asyncio
async def test_id_namespace_rejects_unsafe_file_identifier_text(tmp_path) -> None:
    with pytest.raises(ValueError, match="id_namespace"):
        await run_sequence(
            output_dir=tmp_path / "unsafe",
            mode="recorded",
            style="literary",
            theme="action_conflict",
            seed=7,
            desired_length=300,
            checkpoint_every=1,
            limits=_limits(1),
            resume=False,
            id_namespace="../escape",
        )


@pytest.mark.asyncio
async def test_recorded_resume_rejects_identity_change(tmp_path) -> None:
    output_dir = tmp_path / "identity"
    await run_sequence(
        output_dir=output_dir,
        mode="recorded",
        style="literary",
        theme="reality_mystery",
        seed=7,
        desired_length=300,
        checkpoint_every=2,
        limits=_limits(2),
        resume=False,
    )

    with pytest.raises(ValueError, match="resume configuration mismatch"):
        await run_sequence(
            output_dir=output_dir,
            mode="recorded",
            style="literary",
            theme="action_conflict",
            seed=7,
            desired_length=300,
            checkpoint_every=2,
            limits=_limits(4),
            resume=True,
        )


@pytest.mark.asyncio
async def test_recorded_resume_rejects_id_namespace_change(tmp_path) -> None:
    output_dir = tmp_path / "namespace-identity"
    await run_sequence(
        output_dir=output_dir,
        mode="recorded",
        style="literary",
        theme="action_conflict",
        seed=7,
        desired_length=300,
        checkpoint_every=2,
        limits=_limits(2),
        resume=False,
        id_namespace="g1_action_conflict_literary",
    )

    with pytest.raises(ValueError, match="resume configuration mismatch"):
        await run_sequence(
            output_dir=output_dir,
            mode="recorded",
            style="literary",
            theme="action_conflict",
            seed=7,
            desired_length=300,
            checkpoint_every=2,
            limits=_limits(4),
            resume=True,
            id_namespace="g2_action_conflict_literary",
        )


@pytest.mark.asyncio
async def test_recorded_runtime_rebuild_failure_injection_is_checkpointed(
    tmp_path,
) -> None:
    report = await run_sequence(
        output_dir=tmp_path / "runtime-rebuild",
        mode="recorded",
        style="literary",
        theme="reality_mystery",
        seed=11,
        desired_length=300,
        checkpoint_every=1,
        runtime_rebuild_every=0,
        inject_failure="runtime_rebuild:1",
        stop_on_gate_failure=False,
        limits=_limits(3),
        resume=False,
    )

    assert report["summary"]["committed"] == 3
    assert report["summary"]["runtime_rebuilds"] == 1
    assert report["config"]["runtime_rebuild_every"] == 0
    assert report["config"]["inject_failure"] == "runtime_rebuild:1"
    assert report["recovery_evidence"]["canonical_revision_contiguous"] is True


@pytest.mark.asyncio
async def test_recorded_100_section_p2_gate_with_resume_and_semantic_recall(
    tmp_path,
) -> None:
    output_dir = tmp_path / "p2-recorded-100"
    await run_sequence(
        output_dir=output_dir,
        mode="recorded",
        style="literary",
        theme="reality_mystery",
        seed=20260728,
        desired_length=300,
        checkpoint_every=10,
        runtime_rebuild_every=5,
        limits=_limits(50),
        resume=False,
        stop_on_gate_failure=True,
    )
    report = await run_sequence(
        output_dir=output_dir,
        mode="recorded",
        style="literary",
        theme="reality_mystery",
        seed=20260728,
        desired_length=300,
        checkpoint_every=10,
        runtime_rebuild_every=5,
        limits=_limits(100),
        resume=True,
        stop_on_gate_failure=True,
    )

    assert report["summary"]["committed"] == 100
    assert report["summary"]["semantic_recall_pass"] == 7
    assert report["summary"]["semantic_recall_total"] == 7
    assert report["summary"]["wrong_version_memory_uses"] == 0
    assert report["summary"]["thread_liveness_violations"] == 0
    assert report["summary"]["planner_calls"] == 0
    assert report["summary"]["writer_retries"] == 0
    assert report["summary"]["context_token_p95"] <= 12000
    assert report["recovery_evidence"]["resume_used"] is True
    assert report["p2_gate"]["passed"] is True
    assert all(report["p2_gate"]["checks"].values())
