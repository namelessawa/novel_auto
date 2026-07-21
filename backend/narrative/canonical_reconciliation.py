"""Read-only reconciliation between CanonicalFact and legacy projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from memory_system.models import CharacterState
from narrative.canonical_facts import CanonicalFact, CanonicalFactStore
from narrative.fact_ledger import Fact
from narrative.typed_continuity import continuity_legacy_view


@dataclass(frozen=True)
class ReconciliationIssue:
    code: str
    view: str
    severity: str
    subject_id: str
    predicate: str
    canonical_fact_id: str
    expected: Any
    actual: Any
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "view": self.view,
            "severity": self.severity,
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "canonical_fact_id": self.canonical_fact_id,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }


@dataclass
class ReconciliationReport:
    checked: int = 0
    matched: int = 0
    skipped: int = 0
    issues: list[ReconciliationIssue] = field(default_factory=list)
    coverage_gaps: list[dict] = field(default_factory=list)

    @property
    def hard_conflict_count(self) -> int:
        return sum(
            issue.severity == "high" for issue in self.issues
        )

    def add_match(self) -> None:
        self.checked += 1
        self.matched += 1

    def add_issue(self, issue: ReconciliationIssue) -> None:
        self.checked += 1
        self.issues.append(issue)

    def add_skip(self) -> None:
        self.skipped += 1

    def merge(self, other: "ReconciliationReport") -> None:
        self.checked += other.checked
        self.matched += other.matched
        self.skipped += other.skipped
        self.issues.extend(other.issues)
        self.coverage_gaps.extend(other.coverage_gaps)

    def to_dict(self) -> dict:
        by_view: dict[str, dict[str, int]] = {}
        for issue in self.issues:
            item = by_view.setdefault(
                issue.view, {"issues": 0, "hard_conflicts": 0}
            )
            item["issues"] += 1
            if issue.severity == "high":
                item["hard_conflicts"] += 1
        return {
            "checked": self.checked,
            "matched": self.matched,
            "skipped": self.skipped,
            "issue_count": len(self.issues),
            "hard_conflict_count": self.hard_conflict_count,
            "coverage_gap_count": len(self.coverage_gaps),
            "by_view": by_view,
            "issues": [issue.to_dict() for issue in self.issues],
            "coverage_gaps": list(self.coverage_gaps),
        }


def _issue(
    fact: CanonicalFact,
    *,
    view: str,
    expected: Any,
    actual: Any,
    code: str = "view_mismatch",
    severity: str = "high",
    detail: str = "",
) -> ReconciliationIssue:
    return ReconciliationIssue(
        code=code,
        view=view,
        severity=severity,
        subject_id=fact.subject_id,
        predicate=fact.predicate,
        canonical_fact_id=fact.fact_id,
        expected=expected,
        actual=actual,
        detail=detail,
    )


def _compare(
    report: ReconciliationReport,
    fact: CanonicalFact,
    *,
    view: str,
    expected: Any,
    actual: Any,
    severity: str = "high",
) -> None:
    if expected == actual:
        report.add_match()
    else:
        report.add_issue(
            _issue(
                fact,
                view=view,
                expected=expected,
                actual=actual,
                severity=severity,
            )
        )


def reconcile_tick_state(
    store: CanonicalFactStore,
    character_states: Iterable[CharacterState],
) -> ReconciliationReport:
    report = ReconciliationReport()
    states = {state.character_id: state for state in character_states}
    inventories: dict[str, list[str]] = {}
    for state in states.values():
        for item in state.inventory:
            inventories.setdefault(item, []).append(state.character_id)

    for fact in store.current_facts():
        predicate = fact.predicate
        state = states.get(fact.subject_id)
        if predicate == "character_location":
            if state is None:
                report.add_skip()
                continue
            value = fact.value if isinstance(fact.value, dict) else {}
            movement_state = value.get("state")
            if movement_state == "moving_to":
                # Intent is not arrival and TickState has no transit field.
                report.add_skip()
                continue
            expected = value.get("location_id")
            _compare(
                report,
                fact,
                view="tick_state",
                expected=expected,
                actual=state.current_location or None,
            )
        elif predicate == "item_holder" and fact.subject_id.startswith("item:"):
            item = fact.subject_id[len("item:") :]
            owners = sorted(inventories.get(item, []))
            actual: Any = owners[0] if len(owners) == 1 else None
            if len(owners) > 1:
                actual = owners
            _compare(
                report,
                fact,
                view="tick_state",
                expected=fact.value,
                actual=actual,
            )
        elif predicate.startswith("status_effect:"):
            if state is None:
                report.add_skip()
                continue
            status = predicate.split(":", 1)[1]
            _compare(
                report,
                fact,
                view="tick_state",
                expected=bool(fact.value),
                actual=status in state.status_effects,
            )
        elif predicate == "alive_status":
            if state is None:
                report.add_skip()
                continue
            actual = "dead" if "dead" in state.status_effects else "alive"
            _compare(
                report,
                fact,
                view="tick_state",
                expected=fact.value,
                actual=actual,
            )
        elif predicate.startswith("relationship_state:"):
            if state is None:
                report.add_skip()
                continue
            other = predicate.split(":", 1)[1]
            relation = state.relationships.get(other)
            _compare(
                report,
                fact,
                view="tick_state",
                expected=fact.value,
                actual=relation.type if relation else None,
            )
        elif predicate.startswith("trust:"):
            if state is None:
                report.add_skip()
                continue
            other = predicate.split(":", 1)[1]
            relation = state.relationships.get(other)
            _compare(
                report,
                fact,
                view="tick_state",
                expected=fact.value,
                actual=relation.trust if relation else None,
            )
        elif predicate == "money_balance":
            if state is None:
                report.add_skip()
                continue
            _compare(
                report,
                fact,
                view="tick_state",
                expected=fact.value,
                actual=state.money,
            )
        elif predicate.startswith("character_knows:"):
            if state is None or not isinstance(fact.value, dict):
                report.add_skip()
                continue
            proposition = fact.value.get("proposition")
            _compare(
                report,
                fact,
                view="tick_state",
                expected=True,
                actual=proposition in state.known_facts,
            )
        else:
            report.add_skip()
    return report


def reconcile_fact_ledger(
    store: CanonicalFactStore,
    legacy_facts: Iterable[Fact],
) -> ReconciliationReport:
    report = ReconciliationReport()
    legacy = [fact for fact in legacy_facts if fact.status == "active"]
    compared_ids: set[str] = set()
    for old in legacy:
        canonical: CanonicalFact | None = None
        expected: Any = None
        if old.kind == "location":
            canonical = store.current_fact(old.subject, "character_location")
            expected = (
                canonical.value.get("location_id")
                if canonical and isinstance(canonical.value, dict)
                else None
            )
            actual = old.predicate
        elif old.kind == "death":
            canonical = store.current_fact(old.subject, "alive_status")
            expected = canonical.value if canonical else None
            actual = "dead"
        elif old.kind == "possession":
            canonical = store.current_fact(
                f"item:{old.object}", "item_holder"
            )
            expected = canonical.value if canonical else None
            actual = old.subject
        else:
            report.add_skip()
            continue
        if canonical is None:
            report.coverage_gaps.append(
                {
                    "view": "fact_ledger",
                    "legacy_fact_id": old.id,
                    "subject": old.subject,
                    "kind": old.kind,
                }
            )
            continue
        compared_ids.add(canonical.fact_id)
        _compare(
            report,
            canonical,
            view="fact_ledger",
            expected=expected,
            actual=actual,
        )
    return report


def reconcile_knowledge_graph(
    store: CanonicalFactStore,
    graph: dict,
) -> ReconciliationReport:
    report = ReconciliationReport()
    entities = {
        str(entity.get("id"))
        for entity in graph.get("entities", [])
        if isinstance(entity, dict) and entity.get("id")
    }
    located_at: dict[str, str] = {}
    for relation in graph.get("relations", []):
        if not isinstance(relation, dict):
            continue
        relation_type = str(relation.get("relation_type", "")).lower()
        if relation_type == "located_at":
            located_at[str(relation.get("source"))] = str(
                relation.get("target")
            )

    for fact in store.current_facts():
        if fact.predicate != "character_location":
            continue
        value = fact.value if isinstance(fact.value, dict) else {}
        if value.get("state") == "moving_to":
            report.add_skip()
            continue
        if fact.subject_id not in entities:
            report.coverage_gaps.append(
                {
                    "view": "knowledge_graph",
                    "fact_id": fact.fact_id,
                    "reason": "entity_missing",
                }
            )
            continue
        _compare(
            report,
            fact,
            view="knowledge_graph",
            expected=value.get("location_id"),
            actual=located_at.get(fact.subject_id),
        )
    return report


def reconcile_continuity_state(
    store: CanonicalFactStore,
    continuity_state: dict,
) -> ReconciliationReport:
    """Compare only fields present in continuity; omission is never healing."""

    report = ReconciliationReport()
    continuity_state = continuity_legacy_view(continuity_state)
    characters = continuity_state.get("characters", {})
    if isinstance(characters, dict):
        for cid, state in characters.items():
            if not isinstance(state, dict):
                continue
            if "location" in state:
                fact = store.current_fact(str(cid), "character_location")
                if fact is None:
                    report.coverage_gaps.append(
                        {
                            "view": "continuity_state",
                            "subject": str(cid),
                            "predicate": "character_location",
                        }
                    )
                else:
                    value = fact.value if isinstance(fact.value, dict) else {}
                    _compare(
                        report,
                        fact,
                        view="continuity_state",
                        expected=value.get("location_id"),
                        actual=state.get("location"),
                    )
            injuries = state.get("injuries")
            if isinstance(injuries, list):
                for injury in injuries:
                    fact = store.current_fact(str(cid), f"injury:{injury}")
                    if fact is not None:
                        _compare(
                            report,
                            fact,
                            view="continuity_state",
                            expected=True,
                            actual=True,
                        )

    items = continuity_state.get("items", {})
    field_map = {
        "holder": "item_holder",
        "quantity": "item_quantity",
        "condition": "item_condition",
        "location": "item_location",
    }
    if isinstance(items, dict):
        for name, state in items.items():
            if not isinstance(state, dict):
                continue
            for field_name, predicate in field_map.items():
                if field_name not in state:
                    continue
                fact = store.current_fact(f"item:{name}", predicate)
                if fact is None:
                    report.coverage_gaps.append(
                        {
                            "view": "continuity_state",
                            "subject": f"item:{name}",
                            "predicate": predicate,
                        }
                    )
                    continue
                _compare(
                    report,
                    fact,
                    view="continuity_state",
                    expected=fact.value,
                    actual=state.get(field_name),
                )
    return report


def reconcile_all(
    store: CanonicalFactStore,
    *,
    character_states: Iterable[CharacterState],
    legacy_facts: Iterable[Fact] = (),
    knowledge_graph: dict | None = None,
    continuity_state: dict | None = None,
) -> ReconciliationReport:
    report = ReconciliationReport()
    report.merge(reconcile_tick_state(store, character_states))
    report.merge(reconcile_fact_ledger(store, legacy_facts))
    if knowledge_graph is not None:
        report.merge(reconcile_knowledge_graph(store, knowledge_graph))
    if continuity_state is not None:
        report.merge(reconcile_continuity_state(store, continuity_state))
    return report


__all__ = [
    "ReconciliationIssue",
    "ReconciliationReport",
    "reconcile_all",
    "reconcile_continuity_state",
    "reconcile_fact_ledger",
    "reconcile_knowledge_graph",
    "reconcile_tick_state",
]
