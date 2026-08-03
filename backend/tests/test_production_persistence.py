from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from story.persistence import DataCorruptionError, StoryBibleStore
from story.production_models import (
    BookOutlineUpdate,
    GenerationJob,
    NovelProductionSpecUpdate,
    StyleProfileCreate,
    StyleProfileUpdate,
    VolumeOutline,
)
from story.production_persistence import (
    ActiveStyleStore,
    BookOutlineStore,
    GenerationJobStore,
    ProductionEventStore,
    ProductionSpecStore,
    RevisionConflict,
    StyleProfileStore,
    ensure_production_domain,
)


def _domain(tmp_path: Path):
    report = ensure_production_domain(str(tmp_path), title="潮汐之城")
    bible = StoryBibleStore(str(tmp_path)).load()
    spec_store = ProductionSpecStore(
        str(tmp_path),
        lambda: (_ for _ in ()).throw(AssertionError("spec must exist")),
    )
    return report, bible, spec_store


def _job(job_id: str, prompt_hash: str) -> GenerationJob:
    return GenerationJob(
        id=job_id,
        novel_id="novel_tide",
        status="draft",
        requested_spec_revision=1,
        requested_outline_revision=1,
        requested_style_profile_id="preset_literary",
        requested_style_revision=1,
        requested_style_prompt_hash=prompt_hash,
    )


def test_spec_store_is_revision_aware_and_recovers_last_good(
    tmp_path: Path,
) -> None:
    _, _, store = _domain(tmp_path)
    first = store.load()
    second = store.update(
        NovelProductionSpecUpdate(
            expected_revision=first.revision,
            theme="记忆与责任",
        )
    )
    assert second.revision == first.revision + 1
    assert (tmp_path / "production_spec.json.bak").is_file()

    with pytest.raises(RevisionConflict) as conflict:
        store.update(
            NovelProductionSpecUpdate(
                expected_revision=first.revision,
                theme="陈旧写入",
            )
        )
    assert conflict.value.expected == first.revision
    assert conflict.value.actual == second.revision

    (tmp_path / "production_spec.json").write_text("{broken", encoding="utf-8")
    recovered = store.load()
    assert recovered.revision == first.revision
    quarantined = list((tmp_path / "quarantine").glob("production_spec.json.*.corrupt"))
    assert len(quarantined) == 1


def test_invalid_document_without_last_good_fails_closed(tmp_path: Path) -> None:
    ensure_production_domain(str(tmp_path), title="失真之城")
    outline_path = tmp_path / "book_outline.json"
    backup_path = tmp_path / "book_outline.json.bak"
    backup_path.unlink(missing_ok=True)
    outline_path.write_text('{"schema_version": 1, "revision": "bad"}', encoding="utf-8")

    with pytest.raises(DataCorruptionError):
        BookOutlineStore(str(tmp_path)).load()
    assert list((tmp_path / "quarantine").glob("book_outline.json.*.corrupt"))


def test_permission_error_never_falls_back_to_stale_backup_or_quarantines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, _, store = _domain(tmp_path)
    first = store.load()
    current = store.update(
        NovelProductionSpecUpdate(
            expected_revision=first.revision,
            theme="当前版本",
        )
    )
    calls: list[str] = []
    original_read = store._read_validated

    def inaccessible(path: str):
        calls.append(path)
        if os.path.realpath(path) == store.path:
            raise PermissionError("recorded sharing violation")
        return original_read(path)

    monkeypatch.setattr(store, "_read_validated", inaccessible)
    with pytest.raises(PermissionError, match="recorded sharing violation"):
        store.load()

    assert calls == [store.path]
    assert not (tmp_path / "quarantine").exists()
    payload = json.loads((tmp_path / "production_spec.json").read_text(encoding="utf-8"))
    assert payload["revision"] == current.revision


def test_transient_permission_error_is_retried_for_read_and_replace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, _, store = _domain(tmp_path)
    current = store.load()

    import builtins
    import story.persistence as persistence_module

    real_open = builtins.open
    open_attempts = 0

    def flaky_open(path, *args, **kwargs):
        nonlocal open_attempts
        if os.path.realpath(os.fspath(path)) == store.path and open_attempts < 2:
            open_attempts += 1
            raise PermissionError("recorded read sharing violation")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)
    assert store.load().revision == current.revision
    assert open_attempts == 2

    real_replace = persistence_module.os.replace
    replace_attempts = 0

    def flaky_replace(source: str, target: str) -> None:
        nonlocal replace_attempts
        if replace_attempts < 2:
            replace_attempts += 1
            raise PermissionError("recorded replace sharing violation")
        real_replace(source, target)

    monkeypatch.setattr(persistence_module.os, "replace", flaky_replace)
    updated = store.update(
        NovelProductionSpecUpdate(
            expected_revision=current.revision,
            theme="共享冲突后仍保存当前版本",
        )
    )
    assert updated.revision == current.revision + 1
    assert replace_attempts == 2


def test_outline_update_uses_revision_and_validates_closed_budget(
    tmp_path: Path,
) -> None:
    _domain(tmp_path)
    store = BookOutlineStore(str(tmp_path))
    current = store.load()
    updated = store.update(
        BookOutlineUpdate(
            expected_revision=current.revision,
            logline="潮汐带走城市记忆。",
        )
    )
    assert updated.revision == 2

    with pytest.raises(RevisionConflict):
        store.update(
            BookOutlineUpdate(
                expected_revision=1,
                global_arc="陈旧版本",
            )
        )

    with pytest.raises(ValueError, match="both be populated"):
        store.update(
            BookOutlineUpdate(
                expected_revision=updated.revision,
                volumes=[
                    VolumeOutline(
                        id="volume_001",
                        ordinal=1,
                        title="孤卷",
                        objective="发现异常",
                        target_chapters=1,
                        target_chars=3_000,
                    )
                ],
            )
        )


def test_presets_are_read_only_and_custom_style_hash_is_versioned(
    tmp_path: Path,
) -> None:
    _domain(tmp_path)
    styles = StyleProfileStore(str(tmp_path))
    presets = [profile for profile in styles.list() if profile.read_only]
    assert presets
    assert all(profile.id.startswith(("preset_", "legacy_")) for profile in presets)

    created = styles.create(
        StyleProfileCreate(
            name="冷潮自定义",
            base_preset_key="noir_cold",
            narrative_voice="有限第三人称",
            pacing="缓慢收紧",
            optional_user_sample="样文不得进入 prompt。",
            derived_style_anchors=["物件先于判断"],
        ),
        profile_id="style_custom",
    )
    assert "样文不得进入" not in created.prompt_text()
    old_hash = created.prompt_hash
    updated = styles.update(
        created.id,
        StyleProfileUpdate(
            expected_revision=created.revision,
            pacing="快速收紧",
        ),
    )
    assert updated.revision == 2
    assert updated.prompt_hash != old_hash

    with pytest.raises(RevisionConflict):
        styles.update(
            created.id,
            StyleProfileUpdate(
                expected_revision=1,
                pacing="陈旧覆盖",
            ),
        )
    with pytest.raises(PermissionError):
        styles.delete(presets[0].id, expected_revision=presets[0].revision)

    active_store = ActiveStyleStore(
        str(tmp_path),
        lambda: (_ for _ in ()).throw(AssertionError("active style must exist")),
    )
    active = active_store.load()
    switched = active_store.activate(
        updated,
        applies_from_chapter_ordinal=3,
        expected_revision=active.revision,
    )
    assert switched.style_profile_id == updated.id
    assert switched.profile_revision == 2
    assert switched.applies_from_chapter_ordinal == 3


def test_job_transitions_are_atomic_and_events_are_idempotent(
    tmp_path: Path,
) -> None:
    _domain(tmp_path)
    style = StyleProfileStore(str(tmp_path)).list()[0]
    jobs = GenerationJobStore(str(tmp_path))
    created = jobs.create(_job("job_001", style.prompt_hash))
    queued = jobs.transition(
        created.id,
        expected_revision=created.revision,
        status="queued",
    )
    running = jobs.transition(
        queued.id,
        expected_revision=queued.revision,
        status="running",
    )
    pausing = jobs.transition(
        running.id,
        expected_revision=running.revision,
        status="pausing",
    )
    paused = jobs.transition(
        pausing.id,
        expected_revision=pausing.revision,
        status="paused",
    )
    assert paused.revision == 5
    assert paused.paused_at
    assert jobs.find_active().id == paused.id

    with pytest.raises(RevisionConflict):
        jobs.transition(
            paused.id,
            expected_revision=1,
            status="running",
        )
    with pytest.raises(ValueError, match="invalid generation job transition"):
        jobs.transition(
            paused.id,
            expected_revision=paused.revision,
            status="completed",
        )

    events = ProductionEventStore(str(tmp_path))
    first = events.append(
        paused.id,
        "job_status",
        dedupe_key="job-created",
        payload={"status": "queued"},
    )
    duplicate = events.append(
        paused.id,
        "job_status",
        dedupe_key="job-created",
        payload={"status": "must-not-overwrite"},
    )
    second = events.append(
        paused.id,
        "paused",
        dedupe_key="paused-r5",
        payload={"status": "paused"},
    )
    assert duplicate == first
    assert second.sequence == 2
    assert [event.sequence for event in events.after(paused.id)] == [1, 2]
    assert [event.sequence for event in events.after(paused.id, 1)] == [2]
    assert events.load(paused.id).revision == 3


def test_production_migration_is_idempotent_and_preserves_authorities_and_prose(
    tmp_path: Path,
) -> None:
    prose = '{"section_id":"legacy","content":"不可改写的正式正文"}\n'
    (tmp_path / "tick_sections.jsonl").write_text(prose, encoding="utf-8")

    first = ensure_production_domain(str(tmp_path), title="旧作")
    authority_names = (
        "story_bible.json",
        "canonical_state.json",
        "story_threads.json",
        "memory_records.json",
    )
    authority_bytes = {
        name: (tmp_path / name).read_bytes() for name in authority_names
    }
    production_bytes = {
        name: (tmp_path / name).read_bytes()
        for name in (
            "production_spec.json",
            "book_outline.json",
            "style_profiles.json",
            "active_style.json",
            "production_migration.json",
        )
    }

    second = ensure_production_domain(str(tmp_path), title="不得覆盖的新标题")

    assert second == first
    assert (tmp_path / "tick_sections.jsonl").read_text(encoding="utf-8") == prose
    assert {
        name: (tmp_path / name).read_bytes() for name in authority_names
    } == authority_bytes
    assert {
        name: (tmp_path / name).read_bytes() for name in production_bytes
    } == production_bytes
    assert first.active_style_profile_id
    assert json.loads((tmp_path / "production_spec.json").read_text("utf-8"))[
        "char_count_policy"
    ] == "non_whitespace"
