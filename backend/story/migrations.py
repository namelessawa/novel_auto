"""Idempotent legacy-to-author-domain migration.

Legacy files are read-only inputs.  The migration never renames, deletes, or
overwrites them; malformed sources are copied into the novel quarantine folder
for inspection and skipped conservatively.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any

from story.models import (
    CanonicalState,
    GenerationModeConfig,
    MemoryRecord,
    MemoryRepositoryState,
    MigrationMetadata,
    MigrationReport,
    StoryBible,
    StoryThread,
    StoryThreadRepository,
)
from story.persistence import (
    CanonicalStateStore,
    GenerationModeStore,
    MemoryRepository,
    MigrationReportStore,
    StoryBibleStore,
    StoryThreadStore,
)


MIGRATION_VERSION = 1


def _safe_legacy_json(
    data_dir: str,
    filename: str,
    *,
    warnings: list[str],
    source_files: list[str],
) -> dict[str, Any]:
    path = os.path.join(data_dir, filename)
    if not os.path.isfile(path):
        return {}
    source_files.append(filename)
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("top-level value is not an object")
        return payload
    except Exception as exc:
        quarantine = os.path.join(data_dir, "quarantine")
        os.makedirs(quarantine, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        copied = os.path.join(quarantine, f"legacy_{filename}.{stamp}.corrupt")
        try:
            shutil.copy2(path, copied)
        except OSError:
            copied = "(copy failed)"
        warnings.append(f"{filename} 无法读取，已跳过；隔离副本: {copied}; {exc}")
        return {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _location_summary(world: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, label in (("era", "时代"), ("current_season", "季节"), ("weather", "天气")):
        value = world.get(key)
        if value:
            parts.append(f"{label}：{value}")
    locations = [
        str(item.get("name") or item.get("id") or "").strip()
        for item in _as_list(world.get("locations"))
        if isinstance(item, dict)
    ]
    if locations:
        parts.append("地点：" + "、".join(item for item in locations if item))
    factions = [
        str(item.get("name") or item.get("id") or "").strip()
        for item in _as_list(world.get("factions"))
        if isinstance(item, dict)
    ]
    if factions:
        parts.append("势力：" + "、".join(item for item in factions if item))
    return "；".join(parts)


def _build_story_bible(
    title: str,
    tick: dict[str, Any],
    seed: str,
    source_files: list[str],
) -> tuple[StoryBible, list[str]]:
    arc = _as_dict(tick.get("story_arc"))
    world = _as_dict(tick.get("world_state"))
    profiles = _as_dict(tick.get("character_profiles"))
    loops = _as_dict(tick.get("open_loops"))
    style = _as_dict(tick.get("style_preset_snapshot"))

    inferred: list[str] = []
    premise = seed or f"围绕《{title or '未命名小说'}》展开的长篇故事。"
    inferred.append("premise")
    theme = str(arc.get("theme") or "待用户确认的核心主题")
    if not theme:
        inferred.append("theme")
    central_question = str(arc.get("central_question") or "主人公最终将如何回应核心冲突？")
    if not central_question:
        inferred.append("central_question")
    setting_summary = _location_summary(world) or "待用户确认的世界背景。"
    if not setting_summary:
        inferred.append("setting_summary")

    protagonist_contracts: list[str] = []
    for profile in profiles.values():
        if not isinstance(profile, dict) or profile.get("importance_tier", "C") != "A":
            continue
        name = str(profile.get("name") or profile.get("id") or "主角")
        values = profile.get("core_values") or []
        personality = str(profile.get("personality") or "").strip()
        contract = f"{name}"
        if personality:
            contract += f"：{personality}"
        if values:
            contract += "；核心价值：" + "、".join(map(str, values))
        protagonist_contracts.append(contract)
    if not protagonist_contracts:
        inferred.append("protagonist_contracts")

    main_conflicts = [
        str(beat.get("description") or beat.get("title") or "").strip()
        for beat in _as_list(arc.get("key_beats"))
        if isinstance(beat, dict)
        and (beat.get("description") or beat.get("title"))
    ]
    if not main_conflicts:
        main_conflicts = [
            str(loop.get("description") or "").strip()
            for loop in loops.values()
            if isinstance(loop, dict) and loop.get("description")
        ][:5]
        inferred.append("main_conflicts")

    rules = [str(item).strip() for item in _as_list(world.get("world_rules")) if str(item).strip()]
    if not rules:
        inferred.append("immutable_world_rules")

    style_contract: dict[str, Any] = dict(style)
    if tick.get("style_preset_key"):
        style_contract.setdefault("key", tick.get("style_preset_key"))
    if tick.get("style_preset_version"):
        style_contract.setdefault("version", tick.get("style_preset_version"))
    if not style_contract:
        inferred.append("style_contract")

    is_legacy = bool(tick or source_files)
    metadata = MigrationMetadata(
        source="legacy_inferred" if is_legacy else "new",
        migration_version=MIGRATION_VERSION,
        inferred_fields=list(dict.fromkeys(inferred)),
        source_files=list(dict.fromkeys(source_files)),
        needs_confirmation=True,
    )
    bible = StoryBible(
        title=title,
        source_seed=seed,
        premise=premise,
        theme=theme,
        central_question=central_question,
        setting_summary=setting_summary,
        immutable_world_rules=rules,
        protagonist_contracts=protagonist_contracts,
        main_conflicts=list(dict.fromkeys(item for item in main_conflicts if item)),
        style_contract=style_contract,
        field_provenance={
            field: "legacy_inferred"
            for field in (
                "source_seed",
                "premise",
                "theme",
                "central_question",
                "setting_summary",
                "immutable_world_rules",
                "protagonist_contracts",
                "main_conflicts",
                "style_contract",
            )
            if seed or field != "source_seed"
        }
        if is_legacy
        else {},
        migration=metadata,
    )
    return bible, metadata.inferred_fields


def _thread_type(raw: Any) -> str:
    value = str(raw or "").lower()
    if value in {"mystery", "conflict", "promise", "threat", "goal"}:
        return value
    if value in {"romance", "quest", "foreshadow"}:
        return "promise" if value == "foreshadow" else "goal"
    return "mystery"


def _build_threads(tick: dict[str, Any]) -> StoryThreadRepository:
    threads: dict[str, StoryThread] = {}
    for key, raw in _as_dict(tick.get("open_loops")).items():
        if not isinstance(raw, dict):
            continue
        thread_id = str(raw.get("id") or key).strip()
        description = str(raw.get("description") or "").strip()
        if not thread_id or not description:
            continue
        threads[thread_id] = StoryThread(
            id=thread_id,
            type=_thread_type(raw.get("type")),
            description=description,
            promised_question=str(raw.get("promised_question") or ""),
            involved_characters=list(map(str, _as_list(raw.get("involved_characters")))),
            origin_refs=list(map(str, _as_list(raw.get("origin_event_ids")))),
            urgency=max(0, min(10, int(raw.get("urgency", 5) or 5))),
            resolution_requirements=list(map(str, _as_list(raw.get("payoff_requirements")))),
            opened_at_revision=max(0, int(raw.get("opened_tick", 0) or 0)),
            updated_at_revision=max(0, int(raw.get("last_referenced_tick", 0) or 0)),
            source="legacy_inferred",
        )
    return StoryThreadRepository(threads=threads)


def _merge_character(profile: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    merged = dict(profile)
    merged.update(state)
    if "alive" not in merged:
        statuses = " ".join(map(str, _as_list(state.get("status_effects")))).lower()
        merged["alive"] = not any(word in statuses for word in ("死亡", "dead", "deceased"))
    merged.setdefault("location", state.get("current_location", ""))
    merged.setdefault("injuries", _as_list(state.get("status_effects")))
    return merged


def _build_canonical(
    tick: dict[str, Any],
    ledger: dict[str, Any],
    threads: StoryThreadRepository,
    source_files: list[str],
) -> CanonicalState:
    world_state = _as_dict(tick.get("world_state"))
    profiles = _as_dict(tick.get("character_profiles"))
    states = _as_dict(tick.get("character_states"))
    characters: dict[str, dict[str, Any]] = {}
    character_knowledge: dict[str, list[str]] = {}
    relationships: dict[str, Any] = {}
    items: dict[str, dict[str, Any]] = {}

    for character_id in sorted(set(profiles) | set(states)):
        profile = _as_dict(profiles.get(character_id))
        state = _as_dict(states.get(character_id))
        merged = _merge_character(profile, state)
        characters[str(character_id)] = merged
        known = _as_list(state.get("known_facts")) or _as_list(profile.get("known_facts"))
        character_knowledge[str(character_id)] = list(dict.fromkeys(map(str, known)))
        relationships[str(character_id)] = _as_dict(state.get("relationships"))
        for raw_item in _as_list(state.get("inventory")):
            item_id = str(raw_item).strip()
            if not item_id:
                continue
            item = items.setdefault(item_id, {"id": item_id, "quantity": 0, "owners": []})
            item["quantity"] += 1
            if character_id not in item["owners"]:
                item["owners"].append(character_id)

    facts: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_as_list(ledger.get("facts"))):
        if not isinstance(raw, dict) or raw.get("status", "active") != "active":
            continue
        fact_id = str(raw.get("id") or f"legacy_fact_{index}")
        facts[fact_id] = dict(raw)
        if raw.get("kind") == "death" and raw.get("subject") in characters:
            characters[str(raw["subject"])]["alive"] = False
        if raw.get("kind") == "possession" and raw.get("object"):
            item_id = str(raw["object"])
            items[item_id] = {
                "id": item_id,
                "quantity": 1,
                "owners": [str(raw.get("subject") or "")],
                "source_fact_id": fact_id,
            }

    world = dict(world_state)
    world.pop("world_time", None)
    arc = _as_dict(tick.get("story_arc"))
    active_threads = {
        tid: {
            "status": thread.status,
            "description": thread.description,
            "urgency": thread.urgency,
        }
        for tid, thread in threads.threads.items()
        if thread.status not in {"resolved", "abandoned"}
    }
    return CanonicalState(
        world_time=max(0, int(world_state.get("world_time", tick.get("current_tick", 0)) or 0)),
        world=world,
        characters=characters,
        items=items,
        relationships=relationships,
        character_knowledge=character_knowledge,
        reader_knowledge={
            "known_facts": _as_list(tick.get("reader_known_facts")),
            "source": "legacy_tick_state",
        },
        active_threads=active_threads,
        plot_position={
            "current_act": arc.get("current_act", 1),
            "target_climax_tick": arc.get("target_climax_tick", 0),
            "last_updated_tick": arc.get("last_updated_tick", 0),
        },
        last_scene_state=_as_dict(tick.get("narrative_continuity_state")),
        canonical_facts=facts,
        migration=MigrationMetadata(
            source="legacy_inferred" if tick else "new",
            source_files=list(dict.fromkeys(source_files)),
            inferred_fields=["items", "relationships", "plot_position"],
            needs_confirmation=bool(tick),
        ),
    )


def _memory_record(
    record_id: str,
    summary: str,
    *,
    entities: list[str] | None = None,
    importance: int = 5,
    status: str = "confirmed",
    refs: list[str] | None = None,
) -> MemoryRecord | None:
    summary = summary.strip()
    if not record_id or not summary:
        return None
    return MemoryRecord(
        id=record_id,
        summary=summary,
        entities=entities or [],
        importance=max(0, min(10, importance)),
        canon_status=status,
        source_refs=refs or [],
    )


def _build_memories(memory: dict[str, Any], summary_tree: dict[str, Any]) -> MemoryRepositoryState:
    records: dict[str, MemoryRecord] = {}
    for index, raw in enumerate(_as_list(memory.get("records"))):
        if not isinstance(raw, dict):
            continue
        entry = _as_dict(raw.get("entry")) or raw
        record_id = str(entry.get("id") or f"legacy_memory_{index}")
        item = _memory_record(
            record_id,
            str(entry.get("summary") or ""),
            entities=list(map(str, _as_list(entry.get("involved")))),
            importance=int(entry.get("importance", raw.get("base_importance", 5)) or 5),
            refs=["memory_store.json"],
        )
        if item:
            records[item.id] = item

    seen_nodes: set[str] = set()
    for source_key in ("leaves", "pending_chapter_leaves"):
        for index, raw in enumerate(_as_list(summary_tree.get(source_key))):
            if not isinstance(raw, dict):
                continue
            node_id = str(raw.get("node_id") or f"{source_key}_{index}")
            if node_id in seen_nodes:
                continue
            seen_nodes.add(node_id)
            item = _memory_record(
                f"summary_{node_id}",
                str(raw.get("summary") or ""),
                importance=6,
                refs=["summary_tree.json", node_id],
            )
            if item:
                records[item.id] = item

    # Legends remain searchable history but are explicitly uncertain and never
    # copied into CanonicalState.canonical_facts.
    for index, raw in enumerate(_as_list(summary_tree.get("legends"))):
        if not isinstance(raw, dict):
            continue
        legend_id = str(raw.get("legend_id") or f"legend_{index}")
        item = _memory_record(
            f"legend_{legend_id}",
            str(raw.get("legendary_form") or ""),
            importance=int(raw.get("importance", 5) or 5),
            status="uncertain",
            refs=["summary_tree.json", "L3_legend"],
        )
        if item:
            records[item.id] = item
    return MemoryRepositoryState(records=records)


def ensure_story_domain(data_dir: str, *, title: str = "") -> MigrationReport:
    """Create missing author-domain files without modifying any legacy source."""

    data_dir = os.path.realpath(os.path.abspath(data_dir))
    os.makedirs(data_dir, exist_ok=True)
    bible_store = StoryBibleStore(data_dir)
    canonical_store = CanonicalStateStore(data_dir)
    thread_store = StoryThreadStore(data_dir)
    memory_store = MemoryRepository(data_dir)
    mode_store = GenerationModeStore(data_dir)
    report_store = MigrationReportStore(data_dir)

    required = [
        bible_store.exists(),
        canonical_store.exists(),
        thread_store.exists(),
        memory_store.exists(),
        mode_store.exists(),
    ]
    if all(required):
        # Validate every authoritative file before declaring the migration current.
        bible_store.load()
        canonical_store.load()
        thread_store.load()
        memory_store.load()
        mode_store.load()
        if report_store.exists():
            return report_store.load()
        report = MigrationReport(status="already_current")
        report_store.save(report)
        return report

    warnings: list[str] = []
    source_files: list[str] = []
    tick = _safe_legacy_json(
        data_dir, "tick_state.json", warnings=warnings, source_files=source_files
    )
    ledger = _safe_legacy_json(
        data_dir, "fact_ledger.json", warnings=warnings, source_files=source_files
    )
    legacy_memory = _safe_legacy_json(
        data_dir, "memory_store.json", warnings=warnings, source_files=source_files
    )
    summary_tree = _safe_legacy_json(
        data_dir, "summary_tree.json", warnings=warnings, source_files=source_files
    )
    seed = str(tick.get("source_seed") or tick.get("seed") or "")
    inferred: list[str] = []

    threads = thread_store.load() if thread_store.exists() else _build_threads(tick)
    if not thread_store.exists():
        thread_store.save(threads)
    if not bible_store.exists():
        bible, inferred = _build_story_bible(title, tick, seed, source_files)
        bible_store.save(bible)
    if not canonical_store.exists():
        canonical_store.save(_build_canonical(tick, ledger, threads, source_files))
    if not memory_store.exists():
        memory_store.save(_build_memories(legacy_memory, summary_tree))
    if not mode_store.exists():
        mode_store.save(GenerationModeConfig(mode="author"))

    status = "migrated" if source_files else "created"
    if warnings:
        status = "partial"
    report = MigrationReport(
        status=status,
        source_files=list(dict.fromkeys(source_files)),
        inferred_fields=list(dict.fromkeys(inferred)),
        warnings=warnings,
    )
    report_store.save(report)
    return report


def enrich_unconfirmed_domain_from_legacy(
    data_dir: str, *, title: str = ""
) -> MigrationReport:
    """Replace only untouched placeholder documents after legacy bootstrap.

    This is deliberately narrower than a force migration: any user-confirmed
    StoryBible or any CanonicalState revision beyond the empty initial document
    wins and is never overwritten.
    """

    data_dir = os.path.realpath(os.path.abspath(data_dir))
    ensure_story_domain(data_dir, title=title)
    bible_store = StoryBibleStore(data_dir)
    state_store = CanonicalStateStore(data_dir)
    thread_store = StoryThreadStore(data_dir)
    memory_store = MemoryRepository(data_dir)
    report_store = MigrationReportStore(data_dir)
    bible = bible_store.load()
    state = state_store.load()
    if not (
        state.revision == 1
        and state.migration.source == "new"
        and not state.characters
        and not state.canonical_facts
    ):
        return report_store.load()

    warnings: list[str] = []
    source_files: list[str] = []
    tick = _safe_legacy_json(
        data_dir, "tick_state.json", warnings=warnings, source_files=source_files
    )
    if not tick:
        return report_store.load()
    ledger = _safe_legacy_json(
        data_dir, "fact_ledger.json", warnings=warnings, source_files=source_files
    )
    legacy_memory = _safe_legacy_json(
        data_dir, "memory_store.json", warnings=warnings, source_files=source_files
    )
    summary_tree = _safe_legacy_json(
        data_dir, "summary_tree.json", warnings=warnings, source_files=source_files
    )
    # New author works already persisted the exact seed before this executor.
    # Legacy TickState may carry an explicit seed field; bootstrap.env is never
    # parsed because it cannot prove provenance or preserve the original text.
    seed = str(tick.get("source_seed") or tick.get("seed") or "")
    threads = _build_threads(tick)
    migrated_bible, inferred = _build_story_bible(
        title, tick, seed, source_files
    )
    if bible.migration.source == "user_confirmed":
        mergeable = set(bible.migration.inferred_fields)
        updates: dict[str, Any] = {}
        provenance = dict(bible.field_provenance)
        for field in (
            "premise",
            "theme",
            "central_question",
            "genre",
            "setting_summary",
            "immutable_world_rules",
            "forbidden_deviations",
            "protagonist_contracts",
            "main_conflicts",
            "ending_direction",
        ):
            if field not in mergeable:
                continue
            value = getattr(migrated_bible, field)
            if value:
                updates[field] = value
                provenance[field] = "llm_inferred"
        bible_store.save(
            bible.model_copy(
                update={
                    **updates,
                    "revision": bible.revision + 1,
                    "field_provenance": provenance,
                    "migration": bible.migration.model_copy(
                        update={
                            "source_files": list(
                                dict.fromkeys(
                                    bible.migration.source_files + source_files
                                )
                            ),
                            "needs_confirmation": bool(mergeable),
                        }
                    ),
                }
            )
        )
    else:
        bible_store.save(migrated_bible)
    state_store.save(_build_canonical(tick, ledger, threads, source_files))
    if not thread_store.load().threads:
        thread_store.save(threads)
    if not memory_store.load().records:
        memory_store.save(_build_memories(legacy_memory, summary_tree))
    report = MigrationReport(
        status="partial" if warnings else "migrated",
        source_files=list(dict.fromkeys(source_files)),
        inferred_fields=list(dict.fromkeys(inferred)),
        warnings=warnings,
    )
    report_store.save(report)
    return report


__all__ = [
    "MIGRATION_VERSION",
    "enrich_unconfirmed_domain_from_legacy",
    "ensure_story_domain",
]
