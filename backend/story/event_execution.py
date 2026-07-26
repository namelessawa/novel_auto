"""Deterministic ordered event plan and completion classification.

Writer evidence is only a localization hint. Completion is always re-derived
from the prose, the NarrativeContract and the server-owned execution plan.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import Field

from story.narrative_contract import (
    EventCompletionResult,
    LengthConstraint,
    NarrativeContract,
    NarrativeModel,
    RequiredEndState,
)


CompletionType = Literal[
    "completed_action",
    "item_transfer",
    "state_transition",
    "dialogue_commitment",
]


class EventCompletionTest(NarrativeModel):
    actor_required: bool = True
    target_required: bool = True
    completed_tense_required: bool = True


class PlannedEvent(NarrativeModel):
    id: str = Field(min_length=1)
    order: int = Field(ge=1)
    actor: str = ""
    actor_aliases: list[str] = Field(default_factory=list)
    action: str = Field(min_length=1)
    target: str = ""
    target_aliases: list[str] = Field(default_factory=list)
    description: str = ""
    completion_type: CompletionType = "completed_action"
    required: bool = True
    allow_omission: bool = False
    minimum_completion_evidence: str = ""
    completion_test: EventCompletionTest = Field(default_factory=EventCompletionTest)


class EventExecutionPlan(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    section_id: str = Field(min_length=1)
    contract_hash: str = Field(min_length=1)
    ordered_events: list[PlannedEvent] = Field(default_factory=list)
    required_end_states: list[RequiredEndState] = Field(default_factory=list)
    preserve_facts: list[dict[str, Any]] = Field(default_factory=list)
    forbidden_additions: list[str] = Field(default_factory=list)
    style_constraints: dict[str, Any] = Field(default_factory=dict)
    length_constraint: LengthConstraint = Field(default_factory=LengthConstraint)


def _entity_aliases(contract: NarrativeContract, identifier: str) -> list[str]:
    if not identifier:
        return []
    for group in (
        contract.allowed_entities.characters,
        contract.allowed_entities.locations,
        contract.allowed_entities.items,
        contract.allowed_entities.organizations,
    ):
        for item in group:
            if identifier in item.all_names:
                return [name for name in item.all_names if name]
    return [identifier]


def _completion_type(action: str, end_states: list[RequiredEndState]) -> CompletionType:
    if any(state.path.endswith(("/holder", "/owner", "/owners")) for state in end_states):
        if any(token in action for token in ("交", "递", "接", "转", "给")):
            return "item_transfer"
    if any(token in action for token in ("打开", "关闭", "离开", "亮起", "点亮")):
        return "state_transition"
    return "completed_action"


def _completion_example(contract: NarrativeContract, event: Any) -> str:
    actor_names = _entity_aliases(contract, event.actor)
    target_names = _entity_aliases(contract, event.target)
    actor = next((name for name in actor_names if name != event.actor), event.actor)
    target = next((name for name in target_names if name != event.target), event.target)
    if "核对" in event.action and "保管" in event.action:
        return f"{actor}实际核对完{target}的指定记录，并将{target}收好继续保管。"
    if "交信" in event.action:
        return f"{actor}把信实际交给{target}，{target}接过信并收好。"
    if any(token in event.action for token in ("交给", "递给", "交到", "递到")):
        return f"{actor}把物品实际交给{target}，{target}接过并收好。"
    target_clause = f"对{target}" if target else ""
    return (
        f"{actor}已经{target_clause}实际完成“{event.action}”，"
        "动作结果已经发生。"
    )


class EventExecutionPlanBuilder:
    """Build an immutable Writer-facing plan without an LLM."""

    def build(
        self,
        *,
        contract: NarrativeContract,
        section_goal: Any,
        story_threads: list[Any],
        canonical_state: Any,
        style_contract: dict[str, Any] | None = None,
    ) -> EventExecutionPlan:
        del story_threads  # Contract already contains selected thread requirements.
        del canonical_state  # Revision is bound by contract_hash; facts are copied below.
        events = [
            PlannedEvent(
                id=event.id,
                order=index,
                actor=event.actor,
                actor_aliases=_entity_aliases(contract, event.actor),
                action=event.action,
                target=event.target,
                target_aliases=_entity_aliases(contract, event.target),
                description=event.description or event.action,
                completion_type=_completion_type(
                    event.action, list(contract.required_end_state)
                ),
                required=bool(event.required_evidence),
                allow_omission=not event.required_evidence,
                minimum_completion_evidence=_completion_example(contract, event),
                completion_test=EventCompletionTest(
                    actor_required=bool(event.actor),
                    target_required=bool(event.target),
                    completed_tense_required=True,
                ),
            )
            for index, event in enumerate(contract.required_events, start=1)
        ]
        contract_hash = contract.contract_hash or hashlib.sha256(
            json.dumps(
                contract.model_dump(mode="json", exclude={"contract_hash"}),
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return EventExecutionPlan(
            section_id=contract.section_id or section_goal.section_id,
            contract_hash=contract_hash,
            ordered_events=events,
            required_end_states=list(contract.required_end_state),
            preserve_facts=[
                {
                    "id": fact.id,
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                    "object": fact.object,
                    "time": fact.time,
                    "statement": fact.statement,
                }
                for fact in contract.required_facts
            ],
            forbidden_additions=[item.description for item in contract.forbidden_additions],
            style_constraints=dict(style_contract or {}),
            length_constraint=contract.length_constraint,
        )


def event_execution_plan_prompt_payload(plan: EventExecutionPlan) -> dict[str, Any]:
    return {
        "schema_version": plan.schema_version,
        "section_id": plan.section_id,
        "contract_hash": plan.contract_hash,
        "instruction": "按 order 顺序在正文中实际完成每个 required 事件；计划、未遂、假设和否定不算完成。",
        "non_completion_examples": [
            "准备……",
            "打算……",
            "走向……",
            "想要……",
            "即将……",
            "如果……",
            "也许……",
            "原本可以……",
        ],
        "ordered_events": [
            item.model_dump(mode="json") for item in plan.ordered_events
        ],
        "required_end_states": [
            {
                "id": item.id,
                "path": item.path,
                "expected": item.expected,
                "description": item.description,
            }
            for item in plan.required_end_states
        ],
        "preserve_facts": plan.preserve_facts,
        "forbidden_additions": plan.forbidden_additions,
        "style_constraints": plan.style_constraints,
        "length_constraint": plan.length_constraint.model_dump(mode="json"),
    }


_ACTION_TERMS = (
    "交给",
    "递给",
    "交到",
    "递到",
    "接过",
    "收下",
    "包扎",
    "清理",
    "打开",
    "推开",
    "离开",
    "抵达",
    "点亮",
    "亮起",
    "核对",
    "复核",
    "查看",
    "保管",
    "收好",
)
_ATTEMPT = re.compile(r"试图|尝试|想要|想把|差点|未能|没能")
_STARTED = re.compile(r"准备|打算|即将|将要|正要|走向|靠近|伸手(?:去|想)")
_HYPOTHETICAL = re.compile(r"如果|假如|倘若|也许|可能|原本可以|本可以|或许")
_NEGATIVE = re.compile(r"没有|并未|未曾|不曾|尚未|拒绝|并没有|未能|没能")
_MENTION = re.compile(r"提到|谈到|说起|讨论|商量|提及")
_TRANSFER_COMPLETED = (
    "接过",
    "收下",
    "放进",
    "塞进",
    "滑进",
    "装进",
    "收好",
    "保管",
    "持有",
    "抽出",
    "取出",
    "拿着",
    "拿住",
    "握住",
    "攥紧",
    "拍进",
    "落在",
    "塞回",
    "收进",
    "藏进",
    "藏好",
    "藏于",
    "藏入",
    "纳入",
    "贴胸藏",
    "接回",
    "拿回",
    "放回",
    "攥在",
    "握在",
    "拿在",
    "在我身上",
    "按进",
)
_COREFERENCE_PRONOUNS = ("他", "她", "其", "对方")
_VERIFY_COMPLETED = re.compile(
    r"核对(?:完|毕|过|无误|了.{0,4}遍)|复核(?:完|毕)|核毕|核明|确(?:认|系无误)|"
    r"逐字(?:比照|比对|念出|读出|移动|对到)|逐行(?:点过|看过)|"
    r"一字一字(?:对|核|看|读)|一字字(?:默诵|比对|核对|对照)|"
    r"看了(?:一|两|三)遍|看见了|默念了.{0,4}遍|对得上|一一吻合|无丝毫差池|勘验已毕|"
    r"(?:与|同).{0,40}对照|分毫不差|对着.{0,30}看|"
    r"(?:日期|记录|数字).{0,20}(?:不对|有误|改过|一致)|"
    r"举到灯前|沿第[0-9一二三四五六七八九十]+行(?:往下走|点过|划过)|"
    r"手指沿着.{0,30}(?:墨迹|记录)|记录.{0,30}(?:还能辨认|没有变化|无误)"
)
_ORDINALS = {
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
    "10": "十",
}


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[。！？!?])|\n+", text) if item.strip()]


def _keywords(value: str) -> list[str]:
    chunks = re.split(r"[，。！？；：、,/|\s与和并且让使将把的了]+", value)
    return [item for item in chunks if 2 <= len(item) <= 18]


def _event_terms(action: str) -> list[str]:
    terms = [item for item in _ACTION_TERMS if item in action]
    return terms or _keywords(action)


def _matches_any(sentence: str, values: list[str]) -> bool:
    return not values or any(value and value in sentence for value in values)


def _non_completion_status(sentence: str) -> str:
    if _MENTION.search(sentence):
        return "mentioned"
    if _HYPOTHETICAL.search(sentence):
        return "attempted"
    if _ATTEMPT.search(sentence):
        return "attempted"
    if _STARTED.search(sentence):
        return "started"
    if _NEGATIVE.search(sentence):
        return "contradicted"
    return ""


def completion_blocker_status(text: str) -> str:
    """Public helper shared by event and final-state validation."""
    return _non_completion_status(text)


def _regex_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        try:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        except re.error:
            match = re.search(re.escape(pattern), text, flags=re.IGNORECASE)
        if match:
            return match.group(0)[:300]
    return ""


def _transfer_completion_evidence(
    *,
    contract: NarrativeContract,
    event: PlannedEvent,
    sentences: list[str],
) -> str:
    """Resolve a narrow transfer chain ending in the target's possession.

    This accepts natural multi-sentence prose such as an actor placing an item,
    the target reaching for it, and the item subsequently sliding into "her"
    pocket.  The final sentence itself must express completed possession; a
    reach/plan sentence alone can never satisfy the fallback.
    """
    item_names = [
        name
        for item in contract.allowed_entities.items
        if any(
            alias and (alias in event.action or alias in event.description)
            for alias in item.all_names
        )
        for name in item.all_names
        if name
    ]
    if not item_names:
        item_names = [
            name
            for item in contract.allowed_entities.items
            for name in item.all_names
            if name
        ]
    if any("信" in name for name in item_names) and "信" not in item_names:
        item_names.append("信")
    actor_names = event.actor_aliases or ([event.actor] if event.actor else [])
    target_names = event.target_aliases or ([event.target] if event.target else [])
    for index, sentence in enumerate(sentences):
        if completion_blocker_status(sentence):
            continue
        if not any(term in sentence for term in _TRANSFER_COMPLETED):
            continue
        if item_names and not any(name in sentence for name in item_names):
            continue
        prior = "".join(sentences[max(0, index - 16) : index])[-500:]
        actor_ok = not actor_names or any(name in sentence + prior for name in actor_names)
        target_explicit = not target_names or any(name in sentence for name in target_names)
        target_coreference = (
            any(name in prior for name in target_names)
            and any(pronoun in sentence for pronoun in _COREFERENCE_PRONOUNS)
        )
        if actor_ok and (target_explicit or target_coreference):
            return sentence
    return ""


def holder_state_evidence(
    *,
    contract: NarrativeContract,
    path: str,
    expected: Any,
    narrative_text: str,
) -> tuple[bool, str, str]:
    """Return (determined, final_holder_id, evidence) for a holder path.

    The last completed possession statement wins.  Earlier temporary handling
    cannot certify the final state when a later sentence explicitly gives the
    item to another allowed character.
    """
    parts = [part for part in path.split("/") if part]
    if not parts or parts[-1] not in {"holder", "owner", "owners"}:
        return False, "", ""
    item_id = parts[-2] if len(parts) >= 2 else ""
    item_names: list[str] = []
    for item in contract.allowed_entities.items:
        if item_id in item.all_names:
            item_names = [name for name in item.all_names if name]
            break
    if not item_names:
        return False, "", ""
    if any("信" in name for name in item_names) and "信" not in item_names:
        item_names.append("信")
    characters = {
        item.id: [name for name in item.all_names if name]
        for item in contract.allowed_entities.characters
    }
    sentences = _sentences(narrative_text)
    recent_entity = ""
    pronoun_map: dict[str, str] = {}
    final_holder = ""
    final_evidence = ""
    for sentence in sentences:
        leading_pronoun = re.match(r'^[“”"\s]*(他|她)', sentence)
        leading_entity = ""
        if leading_pronoun:
            pronoun = leading_pronoun.group(1)
            leading_entity = recent_entity or pronoun_map.get(pronoun, "")
            if not leading_entity:
                remaining = [
                    identifier
                    for identifier in characters
                    if identifier not in pronoun_map.values()
                ]
                leading_entity = (
                    remaining[0]
                    if len(remaining) == 1
                    else recent_entity
                )
                if leading_entity:
                    pronoun_map[pronoun] = leading_entity
            elif leading_entity:
                pronoun_map[pronoun] = leading_entity
        explicit_in_sentence = [
            (sentence.rfind(name), identifier)
            for identifier, names in characters.items()
            for name in names
            if name in sentence
        ]
        if completion_blocker_status(sentence):
            if leading_entity:
                recent_entity = leading_entity
            elif explicit_in_sentence:
                recent_entity = max(explicit_in_sentence)[1]
            continue
        if not any(item in sentence for item in item_names):
            if leading_entity:
                recent_entity = leading_entity
            elif explicit_in_sentence:
                recent_entity = max(explicit_in_sentence)[1]
            continue
        term_positions = [
            (sentence.rfind(term), term)
            for term in _TRANSFER_COMPLETED
            if term in sentence
        ]
        if not term_positions:
            if leading_entity:
                recent_entity = leading_entity
            elif explicit_in_sentence:
                recent_entity = max(explicit_in_sentence)[1]
            continue
        term_position, term = max(term_positions)
        holder = ""
        # "物品落在林秋怀中" names the receiver after the verb.
        if term in {"落在", "交给", "递给", "交到", "递到"}:
            after = sentence[term_position : term_position + 50]
            for identifier, names in characters.items():
                if any(name in after for name in names):
                    holder = identifier
                    break
        if not holder:
            before = sentence[:term_position]
            observer_subject = ""
            observer = re.search(
                r"(?:看着|望着|瞧着)(他|她|对方|[\u3400-\u9fff]{2,4}).{0,8}把",
                before,
            )
            if observer:
                observed = observer.group(1)
                for identifier, names in characters.items():
                    if observed in names:
                        observer_subject = identifier
                        break
                if not observer_subject:
                    observer_subject = pronoun_map.get(observed, "")
            # A leading pronoun remains the subject of "把...塞回/收进"
            # even if an earlier object names another character, as in
            # "他看了沈砚一眼，把信塞回内袋".  An observer construction
            # such as "他看着沈砚把信收好" is the narrow exception.
            if observer_subject:
                holder = observer_subject
            elif leading_entity and "把" in before:
                holder = leading_entity
            explicit = [
                (before.rfind(name), identifier)
                for identifier, names in characters.items()
                for name in names
                if name in before
            ]
            if not holder and explicit:
                position, holder = max(explicit)
                tail = before[position:]
                observer = re.search(r"(?:看着|望着|见)(他|她|对方).{0,8}把", tail)
                if observer:
                    holder = recent_entity or pronoun_map.get(observer.group(1), "") or holder
            elif recent_entity and any(
                pronoun in before for pronoun in (*_COREFERENCE_PRONOUNS, "自己")
            ):
                subject = re.search(r"(他|她|对方).{0,8}把", before)
                holder = (
                    pronoun_map.get(subject.group(1), "")
                    if subject
                    else ""
                ) or leading_entity or recent_entity
        if holder:
            recent_entity = holder
            final_holder = holder
            final_evidence = sentence[:300]
        elif leading_entity:
            recent_entity = leading_entity
        elif explicit_in_sentence:
            recent_entity = max(explicit_in_sentence)[1]
    return bool(final_holder), final_holder, final_evidence


def _verification_completion_evidence(
    *,
    event: PlannedEvent,
    sentences: list[str],
) -> str:
    if "核对" not in event.action:
        return ""
    ordinal = re.search(r"第\s*([0-9一二三四五六七八九十]+)\s*(?:处|节|行)", event.action)
    markers: set[str] = set()
    if ordinal:
        value = ordinal.group(1)
        variants = {value, _ORDINALS.get(value, value)}
        markers = {
            f"第{variant}{suffix}"
            for variant in variants
            for suffix in ("处", "节", "行")
        }
    actor_names = event.actor_aliases or ([event.actor] if event.actor else [])
    for index, sentence in enumerate(sentences):
        if completion_blocker_status(sentence):
            continue
        if not _VERIFY_COMPLETED.search(sentence):
            continue
        window = "".join(
            sentences[max(0, index - 16) : min(len(sentences), index + 4)]
        )[-900:]
        actor_ok = not actor_names or any(name in window for name in actor_names)
        ordinal_ok = not markers or any(marker in window for marker in markers)
        if not (actor_ok and ordinal_ok):
            continue
        return sentence[:300]
    return ""


class EventCompletionValidator:
    """Classify every planned event without trusting Writer assertions."""

    def validate(
        self,
        *,
        contract: NarrativeContract,
        plan: EventExecutionPlan,
        narrative_text: str,
        evidence_hints: list[Any] | None = None,
    ) -> list[EventCompletionResult]:
        text = narrative_text or ""
        sentences = _sentences(text)
        hints = {
            str(getattr(item, "event_id", "")): str(getattr(item, "evidence", ""))
            for item in (evidence_hints or [])
        }
        contract_events = {item.id: item for item in contract.required_events}
        results: list[EventCompletionResult] = []
        for event in plan.ordered_events:
            source = contract_events[event.id]
            hint = hints.get(event.id, "").strip()
            hint_matched = bool(hint and hint in text)
            pattern_evidence = _regex_match(source.evidence_patterns, text)
            incomplete_evidence = _regex_match(source.incomplete_patterns, text)
            actor_names = event.actor_aliases or ([event.actor] if event.actor else [])
            target_names = event.target_aliases or ([event.target] if event.target else [])
            action_terms = _event_terms(event.action)
            candidates = [
                sentence
                for sentence in sentences
                if (
                    any(term in sentence for term in action_terms)
                    or (hint_matched and hint in sentence)
                )
            ]
            evidence = pattern_evidence or (hint if hint_matched else "")
            evidence_sentence = next(
                (
                    sentence
                    for sentence in sentences
                    if evidence and (evidence in sentence or sentence in evidence)
                ),
                evidence,
            )
            status = "missing"
            chosen = evidence_sentence
            actor_ok = _matches_any(chosen, actor_names) if chosen else False
            target_ok = _matches_any(chosen, target_names) if chosen else False
            action_ok = any(term in chosen for term in action_terms) if chosen else False

            if incomplete_evidence and not pattern_evidence:
                chosen = incomplete_evidence
                status = _non_completion_status(incomplete_evidence) or "started"
                actor_ok = _matches_any(chosen, actor_names)
                target_ok = _matches_any(chosen, target_names)
                action_ok = any(term in chosen for term in action_terms)

            if chosen and not (incomplete_evidence and not pattern_evidence):
                non_completion = _non_completion_status(chosen)
                if non_completion:
                    status = non_completion
                elif actor_ok and target_ok and action_ok:
                    status = "completed"

            if status != "completed":
                for sentence in candidates:
                    sentence_actor = _matches_any(sentence, actor_names)
                    sentence_target = _matches_any(sentence, target_names)
                    sentence_action = any(term in sentence for term in action_terms)
                    non_completion = _non_completion_status(sentence)
                    if incomplete_evidence and (
                        sentence in incomplete_evidence
                        or incomplete_evidence in sentence
                    ):
                        if status in {"missing", "mentioned"}:
                            status = non_completion or "started"
                            chosen = sentence
                        continue
                    if non_completion:
                        if status in {"missing", "mentioned"}:
                            status = non_completion
                            chosen = sentence
                        continue
                    if sentence_actor and sentence_target and sentence_action:
                        status = "completed"
                        chosen = sentence
                        actor_ok = target_ok = action_ok = True
                        break
                    if sentence_action and sentence_target and not sentence_actor:
                        status = "wrong_actor"
                    elif sentence_action and sentence_actor and not sentence_target:
                        status = "wrong_target"
                    elif sentence_action and status == "missing":
                        status = "mentioned"
                    if not chosen:
                        chosen = sentence
                    actor_ok = actor_ok or sentence_actor
                    target_ok = target_ok or sentence_target
                    action_ok = action_ok or sentence_action

            if status != "completed" and event.completion_type == "item_transfer":
                transfer_evidence = _transfer_completion_evidence(
                    contract=contract,
                    event=event,
                    sentences=sentences,
                )
                if transfer_evidence:
                    status = "completed"
                    chosen = transfer_evidence
                    actor_ok = target_ok = action_ok = True

            if status != "completed":
                verification_evidence = _verification_completion_evidence(
                    event=event,
                    sentences=sentences,
                )
                if verification_evidence:
                    status = "completed"
                    chosen = verification_evidence
                    actor_ok = target_ok = action_ok = True

            # Existing explicit regexes remain authoritative only when their
            # matched prose is not a plan, hypothesis, denial or failed attempt.
            if pattern_evidence and not _non_completion_status(pattern_evidence):
                actor_ok = _matches_any(pattern_evidence, actor_names)
                target_ok = _matches_any(pattern_evidence, target_names)
                action_ok = True
                if actor_ok and target_ok:
                    status = "completed"
                    chosen = pattern_evidence

            if (
                status == "missing"
                and not source.evidence_patterns
                and source.keywords
                and sum(keyword in text for keyword in source.keywords)
                >= min(source.min_keyword_matches, len(source.keywords))
            ):
                status = "completed"
                chosen = "、".join(
                    keyword for keyword in source.keywords if keyword in text
                )[:300]
                actor_ok = not event.actor or any(name in text for name in actor_names)
                target_ok = not event.target or any(name in text for name in target_names)
                action_ok = True

            if status == "completed" and "保管" in event.action:
                determined, final_holder, holder_evidence = holder_state_evidence(
                    contract=contract,
                    path=f"/items/{event.target}/holder",
                    expected=event.actor,
                    narrative_text=text,
                )
                if determined and final_holder != event.actor:
                    status = "contradicted"
                    chosen = holder_evidence
                    target_ok = False

            violation_code = {
                "missing": "REQUIRED_EVENT_MISSING",
                "mentioned": "REQUIRED_EVENT_INCOMPLETE",
                "started": "REQUIRED_EVENT_INCOMPLETE",
                "attempted": "REQUIRED_EVENT_INCOMPLETE",
                "contradicted": "REQUIRED_EVENT_INCOMPLETE",
                "wrong_actor": "REQUIRED_EVENT_ACTOR_MISMATCH",
                "wrong_target": "REQUIRED_EVENT_TARGET_MISMATCH",
            }.get(status, "")
            results.append(
                EventCompletionResult(
                    event_id=event.id,
                    status=status,
                    evidence=chosen[:300],
                    actor_matched=actor_ok,
                    target_matched=target_ok,
                    action_matched=action_ok,
                    evidence_hint_matched=hint_matched,
                    violation_code=violation_code,
                )
            )
        return results


__all__ = [
    "EventCompletionTest",
    "EventCompletionValidator",
    "EventExecutionPlan",
    "EventExecutionPlanBuilder",
    "PlannedEvent",
    "completion_blocker_status",
    "event_execution_plan_prompt_payload",
    "holder_state_evidence",
]
