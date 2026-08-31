from __future__ import annotations

import pytest
from pydantic import ValidationError

from story.production_models import (
    BookOutline,
    BookOutlineUpdate,
    ChapterOutline,
    GenerationJob,
    GenerationJobControlRequest,
    JobStatus,
    NovelProductionSpec,
    NovelProductionSpecUpdate,
    StyleProfile,
    StyleProfileUpdate,
    VolumeOutline,
    non_whitespace_char_count,
)


def _spec(**updates: object) -> NovelProductionSpec:
    payload: dict[str, object] = {
        "title": "潮汐之城",
        "premise": "一名抄表员发现城市每天遗忘一条街。",
        "genre": "悬疑",
        "theme": "记忆与责任",
        "target_total_chars": 12_000,
        "volume_count": 2,
        "chapter_count": 4,
        "target_chapter_chars": 3_000,
        "accepted_chapter_min_chars": 2_700,
        "accepted_chapter_max_chars": 3_300,
        "section_target_chars": 1_500,
    }
    payload.update(updates)
    return NovelProductionSpec.model_validate(payload)


def _chapter(
    ordinal: int,
    volume_id: str,
    *,
    target_chars: int = 3_000,
) -> ChapterOutline:
    return ChapterOutline(
        id=f"chapter_{ordinal:04d}",
        ordinal=ordinal,
        volume_id=volume_id,
        title=f"第{ordinal}章",
        objective=f"推进第{ordinal}个目标",
        target_chars=target_chars,
    )


def _outline(**updates: object) -> BookOutline:
    payload: dict[str, object] = {
        "logline": "一座城市用遗忘换取潮汐平静。",
        "global_arc": "发现代价、追查契约、决定是否打破循环。",
        "volumes": [
            VolumeOutline(
                id="volume_001",
                ordinal=1,
                title="退潮",
                objective="发现异常",
                opening_state="城市看似平静",
                closing_state="主角确认遗忘存在",
                target_chapters=2,
                target_chars=6_000,
            ),
            VolumeOutline(
                id="volume_002",
                ordinal=2,
                title="涨潮",
                objective="承担选择",
                opening_state="契约暴露",
                closing_state="循环被改变",
                target_chapters=2,
                target_chars=6_000,
            ),
        ],
        "chapters": [
            _chapter(1, "volume_001"),
            _chapter(2, "volume_001"),
            _chapter(3, "volume_002"),
            _chapter(4, "volume_002"),
        ],
        "ending_target": "主角保留记忆并承担公开真相的代价。",
        "status": "ready",
    }
    payload.update(updates)
    return BookOutline.model_validate(payload)


def _style(**updates: object) -> StyleProfile:
    payload: dict[str, object] = {
        "id": "style_cold_tide",
        "revision": 1,
        "name": "冷潮",
        "base_preset_key": "noir_cold",
        "description": "克制、具体、低温。",
        "narrative_voice": "有限第三人称",
        "viewpoint": "贴近视点人物",
        "tense": "过去时",
        "sentence_length_tendency": "短句为主",
        "paragraph_density": "疏",
        "dialogue_ratio": 0.25,
        "description_ratio": 0.40,
        "pacing": "稳步收紧",
        "must_do_rules": ["用动作承载情绪", "用动作承载情绪"],
        "forbidden_rules": ["不得改变事实"],
        "avoided_phrases": ["命运的齿轮"],
        "optional_user_sample": "这句话只用于分析，不应进入 Writer prompt。",
        "derived_style_anchors": ["物件先于判断"],
        "deterministic_rules": ["no_meta_leak"],
    }
    payload.update(updates)
    return StyleProfile.model_validate(payload)


def _job(status: JobStatus = "draft") -> GenerationJob:
    style = _style()
    return GenerationJob(
        id=f"job_{status}",
        novel_id="novel_tide",
        status=status,
        requested_spec_revision=1,
        requested_outline_revision=1,
        requested_style_profile_id=style.id,
        requested_style_revision=style.revision,
        requested_style_prompt_hash=style.prompt_hash,
    )


def test_non_whitespace_char_count_is_the_single_length_metric() -> None:
    assert non_whitespace_char_count("潮 汐\n之\t城\u3000。") == 5
    assert non_whitespace_char_count("") == 0


def test_production_spec_revision_patch_and_scale_validation() -> None:
    spec = _spec()
    assert spec.revision == 1
    assert spec.target_total_chars == spec.chapter_count * spec.target_chapter_chars
    assert spec.char_count_policy == "non_whitespace"

    patch = NovelProductionSpecUpdate(
        expected_revision=spec.revision,
        target_total_chars=12_400,
        theme="记忆、责任与选择",
    )
    merged = spec.model_dump()
    merged.update(patch.model_dump(exclude={"expected_revision"}, exclude_none=True))
    merged["revision"] = spec.revision + 1
    revised = NovelProductionSpec.model_validate(merged)
    assert revised.revision == 2
    assert revised.theme == "记忆、责任与选择"

    with pytest.raises(ValidationError, match="target_total_chars"):
        _spec(target_total_chars=50_000)
    with pytest.raises(ValidationError, match="volume_count"):
        _spec(volume_count=5)
    with pytest.raises(ValidationError, match="accepted_chapter_min_chars"):
        NovelProductionSpecUpdate(
            expected_revision=1,
            accepted_chapter_min_chars=4_000,
            accepted_chapter_max_chars=3_000,
        )


def test_book_outline_closes_ordinals_volume_membership_and_char_budget() -> None:
    spec = _spec()
    outline = _outline()

    assert outline.target_chars == 12_000
    assert outline.validation_errors_for(spec) == []
    assert [chapter.ordinal for chapter in outline.chapters] == [1, 2, 3, 4]

    with pytest.raises(ValidationError, match="chapter ordinals"):
        _outline(
            chapters=[
                _chapter(1, "volume_001"),
                _chapter(3, "volume_001"),
                _chapter(4, "volume_002"),
                _chapter(5, "volume_002"),
            ]
        )
    with pytest.raises(ValidationError, match="target_chapters"):
        _outline(
            volumes=[
                VolumeOutline(
                    id="volume_001",
                    ordinal=1,
                    title="退潮",
                    objective="发现异常",
                    target_chapters=1,
                    target_chars=6_000,
                ),
                VolumeOutline(
                    id="volume_002",
                    ordinal=2,
                    title="涨潮",
                    objective="承担选择",
                    target_chapters=2,
                    target_chars=6_000,
                ),
            ]
        )

    mismatched = _outline(
        volumes=[
            VolumeOutline(
                id="volume_001",
                ordinal=1,
                title="退潮",
                objective="发现异常",
                target_chapters=2,
                target_chars=6_200,
            ),
            VolumeOutline(
                id="volume_002",
                ordinal=2,
                title="涨潮",
                objective="承担选择",
                target_chapters=2,
                target_chars=6_000,
            ),
        ],
        chapters=[
            _chapter(1, "volume_001", target_chars=3_100),
            _chapter(2, "volume_001", target_chars=3_100),
            _chapter(3, "volume_002"),
            _chapter(4, "volume_002"),
        ],
    )
    assert "character budget" in " ".join(mismatched.validation_errors_for(spec))

    update = BookOutlineUpdate(expected_revision=outline.revision, logline="新梗概")
    assert update.expected_revision == 1


def test_style_prompt_hash_is_stable_expression_only_and_tamper_evident() -> None:
    first = _style()
    same_prompt_different_sample = _style(
        optional_user_sample="另一段只用于特征抽取的样文。"
    )
    assert len(first.prompt_hash) == 64
    assert first.prompt_hash == same_prompt_different_sample.prompt_hash
    assert "只用于分析" not in first.prompt_text()
    assert first.must_do_rules == ["用动作承载情绪"]

    changed = _style(pacing="快速推进")
    assert changed.prompt_hash != first.prompt_hash

    payload = first.model_dump()
    payload["prompt_hash"] = "0" * 64
    # Self-healing migration: a stale/mismatched stored hash is recomputed from
    # the current contract on load instead of raising, so legacy profiles saved
    # before a prompt_contract() change still load.
    healed = StyleProfile.model_validate(payload)
    assert healed.prompt_hash == healed.computed_prompt_hash()
    assert healed.prompt_hash != "0" * 64

    update = StyleProfileUpdate(expected_revision=first.revision, pacing="快速推进")
    assert update.expected_revision == 1
    with pytest.raises(ValidationError):
        StyleProfileUpdate(expected_revision=0)


def test_generation_job_supports_required_states_and_revision_requests() -> None:
    statuses: tuple[JobStatus, ...] = (
        "draft",
        "queued",
        "running",
        "pausing",
        "paused",
        "failed",
        "cancelling",
        "cancelled",
        "completed",
    )
    assert [GenerationJob.model_validate(_job(status).model_dump()).status for status in statuses] == list(
        statuses
    )

    job = _job("running")
    assert job.revision == 1
    assert job.last_committed_canonical_revision == 0
    control = GenerationJobControlRequest(
        job_id=job.id,
        expected_revision=job.revision,
    )
    assert control.expected_revision == 1

    payload = job.model_dump()
    payload["status"] = "pause_requested"
    with pytest.raises(ValidationError):
        GenerationJob.model_validate(payload)

    with pytest.raises(ValidationError, match="chapter_attempts"):
        GenerationJob(
            **{
                **job.model_dump(exclude={"chapter_attempts"}),
                "chapter_attempts": {"chapter_0001": 0},
            }
        )
