"""Deterministic fixed-slot context assembly for the author writer."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from story.models import (
    CanonicalState,
    ContextManifest,
    ContextSlotManifest,
    MemoryRecord,
    SectionGoal,
    StoryBible,
    StoryThread,
)


SLOT_ORDER = (
    "story_bible",
    "canonical_state",
    "section_goal",
    "active_story_threads",
    "reader_knowledge",
    "character_knowledge",
    "previous_prose_tail",
    "recent_section_summaries",
    "relevant_long_term_memories",
    "style_contract",
)


DEFAULT_SLOT_BUDGETS = {
    "story_bible": 5200,
    "canonical_state": 5000,
    "section_goal": 1800,
    "active_story_threads": 2800,
    "reader_knowledge": 1800,
    "character_knowledge": 2400,
    "previous_prose_tail": 2600,
    "recent_section_summaries": 2600,
    "relevant_long_term_memories": 3200,
    "style_contract": 1800,
}


@dataclass(frozen=True)
class ContextPackage:
    prompt: str
    slots: dict[str, str]
    manifest: ContextManifest


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _head(text: str, budget: int) -> tuple[str, bool]:
    if len(text) <= budget:
        return text, False
    return text[: max(0, budget - 16)].rstrip() + "\n…[槽位已截断]", True


def _tail(text: str, budget: int) -> tuple[str, bool]:
    if len(text) <= budget:
        return text, False
    return "[仅保留正文结尾]…\n" + text[-max(0, budget - 16) :], True


def _token_estimate(text: str) -> int:
    # Conservative mixed Chinese/Latin estimate; deterministic and provider-free.
    return math.ceil(len(text) / 2)


def _ngrams(text: str, size: int = 4) -> set[str]:
    compact = "".join(text.split())
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[i : i + size] for i in range(len(compact) - size + 1)}


def _duplicate_ratio(text: str, previous: str) -> float:
    current = _ngrams(text)
    if not current:
        return 0.0
    prior = _ngrams(previous)
    return round(len(current & prior) / len(current), 4)


class ContextBuilder:
    def __init__(self, slot_budgets: dict[str, int] | None = None) -> None:
        self.slot_budgets = dict(DEFAULT_SLOT_BUDGETS)
        if slot_budgets:
            unknown = set(slot_budgets) - set(SLOT_ORDER)
            if unknown:
                raise ValueError(f"unknown context slots: {sorted(unknown)}")
            self.slot_budgets.update(
                {name: max(200, int(value)) for name, value in slot_budgets.items()}
            )

    def build(
        self,
        *,
        novel_id: str,
        section_id: str,
        story_bible: StoryBible,
        canonical_state: CanonicalState,
        section_goal: SectionGoal,
        story_threads: list[StoryThread],
        previous_prose_tail: str,
        recent_summaries: list[dict[str, Any] | str],
        long_term_memories: list[MemoryRecord],
    ) -> ContextPackage:
        relevant_ids = set(section_goal.involved_characters)
        if section_goal.viewpoint_character_id:
            relevant_ids.add(section_goal.viewpoint_character_id)
        relevant_threads = set(section_goal.target_threads)

        bible_text = self._story_bible_text(story_bible)
        canonical_snapshot = self._canonical_snapshot(
            canonical_state,
            relevant_ids=relevant_ids,
            location_id=section_goal.location_id,
        )
        active_threads = [
            thread.model_dump(mode="json")
            for thread in story_threads
            if thread.status not in {"resolved", "abandoned"}
            and (
                not relevant_threads
                or thread.id in relevant_threads
                or bool(relevant_ids.intersection(thread.involved_characters))
                or thread.urgency >= 7
            )
        ]
        if not active_threads:
            active_threads = [
                thread.model_dump(mode="json")
                for thread in story_threads
                if thread.status not in {"resolved", "abandoned"}
            ][:8]

        character_knowledge = {
            character_id: canonical_state.character_knowledge.get(character_id, [])
            for character_id in sorted(relevant_ids)
            if character_id in canonical_state.character_knowledge
        }
        memory_payload = [record.model_dump(mode="json") for record in long_term_memories]
        recent_payload = recent_summaries[-12:]

        raw_slots = {
            "story_bible": bible_text,
            "canonical_state": _json(canonical_snapshot),
            "section_goal": _json(section_goal.model_dump(mode="json")),
            "active_story_threads": _json(active_threads),
            "reader_knowledge": _json(canonical_state.reader_knowledge),
            "character_knowledge": _json(character_knowledge),
            "previous_prose_tail": previous_prose_tail.strip(),
            "recent_section_summaries": _json(recent_payload),
            "relevant_long_term_memories": _json(memory_payload),
            "style_contract": _json(story_bible.style_contract),
        }

        slots: dict[str, str] = {}
        truncated: dict[str, bool] = {}
        for name in SLOT_ORDER:
            raw = raw_slots[name]
            if name == "previous_prose_tail":
                rendered, was_truncated = _tail(raw, self.slot_budgets[name])
            elif name == "story_bible":
                # Bible rules are protected.  `_story_bible_text` renders every
                # immutable rule and forbidden deviation before optional fields;
                # its protected prefix may expand this one slot rather than vanish.
                protected_len = raw.find("\n【可选创作方向】")
                protected_len = len(raw) if protected_len < 0 else protected_len
                budget = max(self.slot_budgets[name], protected_len)
                rendered, was_truncated = _head(raw, budget)
            else:
                rendered, was_truncated = _head(raw, self.slot_budgets[name])
            slots[name] = rendered
            truncated[name] = was_truncated

        manifests: list[ContextSlotManifest] = []
        previous_rendered = ""
        for name in SLOT_ORDER:
            rendered = slots[name]
            references = self._references(
                name,
                section_goal=section_goal,
                story_threads=story_threads,
                memories=long_term_memories,
            )
            selected_count = 0
            if name == "active_story_threads":
                selected_count = len(active_threads)
            elif name == "recent_section_summaries":
                selected_count = len(recent_payload)
            elif name == "relevant_long_term_memories":
                selected_count = len(memory_payload)
            manifests.append(
                ContextSlotManifest(
                    name=name,
                    char_count=len(rendered),
                    token_estimate=_token_estimate(rendered),
                    budget_chars=self.slot_budgets[name],
                    truncated=truncated[name],
                    reference_ids=references,
                    selected_count=selected_count,
                    omitted_count=(
                        max(0, len(recent_summaries) - len(recent_payload))
                        if name == "recent_section_summaries"
                        else 0
                    ),
                    duplicate_ratio=_duplicate_ratio(rendered, previous_rendered),
                )
            )
            previous_rendered += "\n" + rendered

        prompt = "\n\n".join(
            f"## {index}. {name}\n{slots[name] or '（空）'}"
            for index, name in enumerate(SLOT_ORDER, start=1)
        )
        manifest = ContextManifest(
            novel_id=novel_id,
            section_id=section_id,
            story_bible_revision=story_bible.revision,
            canonical_state_revision=canonical_state.revision,
            total_chars=len(prompt),
            total_token_estimate=_token_estimate(prompt),
            slots=manifests,
        )
        return ContextPackage(prompt=prompt, slots=slots, manifest=manifest)

    @staticmethod
    def _story_bible_text(bible: StoryBible) -> str:
        protected = {
            "theme": bible.theme,
            "central_question": bible.central_question,
            "immutable_world_rules": bible.immutable_world_rules,
            "forbidden_deviations": bible.forbidden_deviations,
            "protagonist_contracts": bible.protagonist_contracts,
        }
        optional = {
            "premise": bible.premise,
            "genre": bible.genre,
            "setting_summary": bible.setting_summary,
            "main_conflicts": bible.main_conflicts,
            "ending_direction": bible.ending_direction,
            "source_seed": bible.source_seed,
        }
        return (
            "【最高权威：主题与不可变约束】\n"
            + _json(protected)
            + "\n【可选创作方向】\n"
            + _json(optional)
        )

    @staticmethod
    def _canonical_snapshot(
        state: CanonicalState,
        *,
        relevant_ids: set[str],
        location_id: str,
    ) -> dict[str, Any]:
        selected_ids = set(relevant_ids)
        if not selected_ids:
            selected_ids.update(sorted(state.characters)[:8])
        characters = {
            character_id: state.characters[character_id]
            for character_id in sorted(selected_ids)
            if character_id in state.characters
        }
        items = {
            item_id: item
            for item_id, item in sorted(state.items.items())
            if not selected_ids
            or bool(selected_ids.intersection(map(str, item.get("owners", []))))
            or item.get("location") == location_id
        }
        world = dict(state.world)
        locations = world.get("locations")
        if location_id and isinstance(locations, list):
            world["locations"] = [
                item
                for item in locations
                if isinstance(item, dict)
                and str(item.get("id") or item.get("name") or "") == location_id
            ]
        return {
            "revision": state.revision,
            "world_time": state.world_time,
            "world": world,
            "characters": characters,
            "items": items,
            "relationships": {
                key: value
                for key, value in state.relationships.items()
                if key in selected_ids
            },
            "plot_position": state.plot_position,
            "last_scene_state": state.last_scene_state,
            "canonical_facts": {
                key: value
                for key, value in state.canonical_facts.items()
                if not selected_ids
                or str(value.get("subject", "")) in selected_ids
                or str(value.get("object", "")) in selected_ids
            },
        }

    @staticmethod
    def _references(
        slot: str,
        *,
        section_goal: SectionGoal,
        story_threads: list[StoryThread],
        memories: list[MemoryRecord],
    ) -> list[str]:
        if slot == "section_goal":
            return [section_goal.section_id]
        if slot == "active_story_threads":
            return [thread.id for thread in story_threads]
        if slot == "relevant_long_term_memories":
            return [memory.id for memory in memories]
        if slot == "character_knowledge":
            return list(
                dict.fromkeys(
                    [section_goal.viewpoint_character_id]
                    + section_goal.involved_characters
                )
            )
        return []


__all__ = [
    "ContextBuilder",
    "ContextPackage",
    "DEFAULT_SLOT_BUDGETS",
    "SLOT_ORDER",
]
