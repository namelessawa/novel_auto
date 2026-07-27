"""Deterministic fixed-slot context assembly for the author writer."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from story.chapter_plan import ChapterPlan
from story.event_execution import (
    EventExecutionPlan,
    event_execution_plan_prompt_payload,
)
from story.models import (
    CanonicalState,
    ContextManifest,
    ContextSlotManifest,
    MemoryRecord,
    SectionGoal,
    StoryBible,
    StoryThread,
)
from story.narrative_contract import (
    NarrativeContract,
    narrative_contract_prompt_payload,
)
from story.section_budget import (
    SectionBudgetPlan,
    section_budget_plan_prompt_payload,
)
from story.writing_plan import (
    SectionWritingPlan,
    section_writing_plan_prompt_payload,
)


SLOT_ORDER = (
    "story_bible",
    "canonical_state",
    "narrative_contract",
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
    "narrative_contract": 9000,
    "section_goal": 1800,
    "active_story_threads": 2800,
    "reader_knowledge": 1800,
    "character_knowledge": 2400,
    "previous_prose_tail": 2600,
    "recent_section_summaries": 2600,
    "relevant_long_term_memories": 3200,
    "style_contract": 1800,
}

MAX_CONTEXT_CHARS = 24000
MAX_CONTEXT_TOKEN_ESTIMATE = 12000
MAX_IMMUTABLE_RULES = 80
MAX_IMMUTABLE_RULE_CHARS = 1000
MAX_BIBLE_FREE_TEXT_CHARS = 12000
MAX_BIBLE_LIST_ITEMS = 100


class ContextBudgetExceeded(ValueError):
    def __init__(self, reason: str, manifest: ContextManifest) -> None:
        super().__init__(reason)
        self.reason = reason
        self.manifest = manifest


@dataclass(frozen=True)
class ContextPackage:
    prompt: str
    slots: dict[str, str]
    manifest: ContextManifest
    narrative_contract: NarrativeContract | None = None
    event_execution_plan: EventExecutionPlan | None = None
    writing_plan: SectionWritingPlan | None = None
    section_budget_plan: SectionBudgetPlan | None = None
    chapter_plan: ChapterPlan | None = None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _head(text: str, budget: int) -> tuple[str, bool]:
    if budget <= 0:
        return "", bool(text)
    if len(text) <= budget:
        return text, False
    return text[: max(0, budget - 16)].rstrip() + "\n…[槽位已截断]", True


def _tail(text: str, budget: int) -> tuple[str, bool]:
    if budget <= 0:
        return "", bool(text)
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
    def __init__(
        self,
        slot_budgets: dict[str, int] | None = None,
        *,
        max_context_chars: int = MAX_CONTEXT_CHARS,
        max_context_token_estimate: int = MAX_CONTEXT_TOKEN_ESTIMATE,
    ) -> None:
        self.slot_budgets = dict(DEFAULT_SLOT_BUDGETS)
        if slot_budgets:
            unknown = set(slot_budgets) - set(SLOT_ORDER)
            if unknown:
                raise ValueError(f"unknown context slots: {sorted(unknown)}")
            self.slot_budgets.update(
                {name: max(200, int(value)) for name, value in slot_budgets.items()}
            )
        self.max_context_chars = max(1000, int(max_context_chars))
        self.max_context_token_estimate = max(
            500, int(max_context_token_estimate)
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
        narrative_contract: NarrativeContract | None = None,
        event_execution_plan: EventExecutionPlan | None = None,
        section_writing_plan: SectionWritingPlan | None = None,
        section_budget_plan: SectionBudgetPlan | None = None,
    ) -> ContextPackage:
        relevant_ids = set(section_goal.involved_characters)
        if section_goal.viewpoint_character_id:
            relevant_ids.add(section_goal.viewpoint_character_id)
        relevant_threads = set(section_goal.target_threads)

        bible_text = self._story_bible_text(story_bible)
        self._validate_story_bible_limits(
            story_bible,
            bible_text,
            novel_id=novel_id,
            section_id=section_id,
            canonical_revision=canonical_state.revision,
        )
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
            "narrative_contract": (
                _json(
                    {
                        "narrative_contract": narrative_contract_prompt_payload(
                            narrative_contract
                        ),
                        "event_execution_plan": (
                            event_execution_plan_prompt_payload(event_execution_plan)
                            if event_execution_plan
                            else {}
                        ),
                        "section_writing_plan": (
                            section_writing_plan_prompt_payload(section_writing_plan)
                            if section_writing_plan
                            else {}
                        ),
                        "section_budget_plan": (
                            section_budget_plan_prompt_payload(section_budget_plan)
                            if section_budget_plan
                            else {}
                        ),
                    }
                )
                if narrative_contract
                else _json({})
            ),
            "section_goal": _json(
                {
                    **section_goal.model_dump(
                        mode="json", exclude={"narrative_constraints"}
                    ),
                    "narrative_constraints": "see protected narrative_contract slot",
                }
            ),
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
        effective_budgets = dict(self.slot_budgets)
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

        hard_char_cap = min(
            self.max_context_chars,
            self.max_context_token_estimate * 2,
        )
        mandatory = {
            "story_bible",
            "canonical_state",
            "narrative_contract",
            "section_goal",
        }
        mandatory_prompt = self._render_prompt(
            {name: slots[name] if name in mandatory else "" for name in SLOT_ORDER}
        )
        if len(mandatory_prompt) > hard_char_cap:
            self._raise_budget(
                novel_id=novel_id,
                section_id=section_id,
                story_bible_revision=story_bible.revision,
                canonical_revision=canonical_state.revision,
                total_chars=len(mandatory_prompt),
                reason=(
                    "StoryBible、CanonicalState、NarrativeContract 与 SectionGoal "
                    "的必要上下文超过全局硬上限，"
                    "请缩小权威数据后重试。"
                ),
            )

        shrink_order = (
            "relevant_long_term_memories",
            "recent_section_summaries",
            "previous_prose_tail",
            "active_story_threads",
            "character_knowledge",
            "reader_knowledge",
            "style_contract",
        )
        prompt = self._render_prompt(slots)
        for name in shrink_order:
            if len(prompt) <= hard_char_cap:
                break
            excess = len(prompt) - hard_char_cap
            current_budget = len(slots[name])
            next_budget = max(0, current_budget - excess)
            if name == "previous_prose_tail":
                rendered, was_truncated = _tail(raw_slots[name], next_budget)
            else:
                rendered, was_truncated = _head(raw_slots[name], next_budget)
            slots[name] = rendered
            truncated[name] = truncated[name] or was_truncated
            effective_budgets[name] = next_budget
            prompt = self._render_prompt(slots)
        if len(prompt) > hard_char_cap:
            self._raise_budget(
                novel_id=novel_id,
                section_id=section_id,
                story_bible_revision=story_bible.revision,
                canonical_revision=canonical_state.revision,
                total_chars=len(prompt),
                reason="上下文无法在保留四项权威槽位的前提下收缩到全局硬上限。",
            )

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
                    budget_chars=effective_budgets[name],
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

        manifest = ContextManifest(
            novel_id=novel_id,
            section_id=section_id,
            story_bible_revision=story_bible.revision,
            canonical_state_revision=canonical_state.revision,
            total_chars=len(prompt),
            total_token_estimate=_token_estimate(prompt),
            max_context_chars=self.max_context_chars,
            max_context_token_estimate=self.max_context_token_estimate,
            budget_utilization=round(len(prompt) / hard_char_cap, 4),
            slots=manifests,
        )
        return ContextPackage(
            prompt=prompt,
            slots=slots,
            manifest=manifest,
            narrative_contract=narrative_contract,
            event_execution_plan=event_execution_plan,
            writing_plan=section_writing_plan,
            section_budget_plan=section_budget_plan,
        )

    @staticmethod
    def _render_prompt(slots: dict[str, str]) -> str:
        return "\n\n".join(
            f"## {index}. {name}\n{slots[name] or '（空）'}"
            for index, name in enumerate(SLOT_ORDER, start=1)
        )

    def _validate_story_bible_limits(
        self,
        bible: StoryBible,
        bible_text: str,
        *,
        novel_id: str,
        section_id: str,
        canonical_revision: int,
    ) -> None:
        rules = list(
            dict.fromkeys(bible.immutable_world_rules + bible.forbidden_deviations)
        )
        reason = ""
        list_fields = {
            "reference_preferences": bible.reference_preferences,
            "immutable_world_rules": bible.immutable_world_rules,
            "forbidden_deviations": bible.forbidden_deviations,
            "protagonist_contracts": bible.protagonist_contracts,
            "main_conflicts": bible.main_conflicts,
        }
        oversized_lists = [
            name for name, values in list_fields.items() if len(values) > MAX_BIBLE_LIST_ITEMS
        ]
        free_text_fields = {
            "title": bible.title,
            "source_seed": bible.source_seed,
            "theme_key": bible.theme_key,
            "positioning": bible.positioning,
            "premise": bible.premise,
            "theme": bible.theme,
            "central_question": bible.central_question,
            "genre": bible.genre,
            "setting_summary": bible.setting_summary,
            "ending_direction": bible.ending_direction,
        }
        oversized_text = [
            name
            for name, value in free_text_fields.items()
            if len(value) > MAX_BIBLE_FREE_TEXT_CHARS
        ]
        if oversized_lists:
            reason = (
                f"StoryBible 列表 {', '.join(oversized_lists)} 超过单字段 "
                f"{MAX_BIBLE_LIST_ITEMS} 项上限。"
            )
        elif oversized_text:
            reason = (
                f"StoryBible 自由文本 {', '.join(oversized_text)} 超过单字段 "
                f"{MAX_BIBLE_FREE_TEXT_CHARS} 字上限。"
            )
        elif len(_json(bible.style_contract)) > MAX_BIBLE_FREE_TEXT_CHARS:
            reason = (
                f"StoryBible style_contract 超过 {MAX_BIBLE_FREE_TEXT_CHARS} 字上限。"
            )
        elif len(rules) > MAX_IMMUTABLE_RULES:
            reason = f"不可变规则与禁止偏移共 {len(rules)} 条，超过上限 {MAX_IMMUTABLE_RULES}。"
        else:
            oversized = [rule for rule in rules if len(rule) > MAX_IMMUTABLE_RULE_CHARS]
            if oversized:
                reason = (
                    "单条不可变规则超过 "
                    f"{MAX_IMMUTABLE_RULE_CHARS} 字，系统拒绝静默截断。"
                )
        protected_len = bible_text.find("\n【可选创作方向】")
        protected_len = len(bible_text) if protected_len < 0 else protected_len
        if not reason and protected_len > self.slot_budgets["story_bible"]:
            reason = (
                f"StoryBible 受保护规则区为 {protected_len} 字，超过槽位硬上限 "
                f"{self.slot_budgets['story_bible']}；不可变规则不会被静默截断。"
            )
        if reason:
            self._raise_budget(
                novel_id=novel_id,
                section_id=section_id,
                story_bible_revision=bible.revision,
                canonical_revision=canonical_revision,
                total_chars=len(bible_text),
                reason=reason,
            )

    def _raise_budget(
        self,
        *,
        novel_id: str,
        section_id: str,
        story_bible_revision: int,
        canonical_revision: int,
        total_chars: int,
        reason: str,
    ) -> None:
        hard_char_cap = min(
            self.max_context_chars,
            self.max_context_token_estimate * 2,
        )
        manifest = ContextManifest(
            novel_id=novel_id,
            section_id=section_id,
            story_bible_revision=story_bible_revision,
            canonical_state_revision=canonical_revision,
            total_chars=total_chars,
            total_token_estimate=math.ceil(total_chars / 2),
            max_context_chars=self.max_context_chars,
            max_context_token_estimate=self.max_context_token_estimate,
            budget_utilization=round(total_chars / hard_char_cap, 4),
            rejected_reason=reason,
        )
        raise ContextBudgetExceeded(reason, manifest)

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
            "title": bible.title,
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
    "ContextBudgetExceeded",
    "ContextPackage",
    "DEFAULT_SLOT_BUDGETS",
    "MAX_CONTEXT_CHARS",
    "MAX_CONTEXT_TOKEN_ESTIMATE",
    "MAX_BIBLE_FREE_TEXT_CHARS",
    "MAX_BIBLE_LIST_ITEMS",
    "SLOT_ORDER",
]
