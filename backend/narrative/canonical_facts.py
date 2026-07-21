"""Versioned, append-oriented canonical fact sidecar.

The sidecar does not replace TickState or FactLedger.  It gives facts a stable
identity and provenance so existing views can be compared before any consumer
is allowed to depend on it.  Objective current facts are deliberately indexed
separately from beliefs, rumours and historical/summary material.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


logger = logging.getLogger(__name__)


CanonicalFactStatus = Literal[
    "active",
    "superseded",
    "invalidated",
    "historical",
    "rumor",
    "belief",
]

FactSourceKind = Literal[
    "event_consequence",
    "state_transition",
    "state_patch",
    "guarded_narrative",
    "world_state",
    "user_edit",
    "bootstrap",
    "open_loop_resolution",
    "continuity_state",
    "known_fact",
    "fact_ledger",
    "knowledge_graph",
    "summary",
    "legend",
]


AUTHORITATIVE_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "event_consequence",
        "state_transition",
        "state_patch",
        "guarded_narrative",
        "world_state",
        "user_edit",
        "bootstrap",
        "open_loop_resolution",
    }
)

DERIVED_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "continuity_state",
        "known_fact",
        "fact_ledger",
        "knowledge_graph",
        "summary",
        "legend",
    }
)


class FactSourceRef(BaseModel):
    """A compact, non-secret pointer to evidence for a fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: FactSourceKind
    source_id: str = Field(min_length=1)
    tick: int | None = Field(default=None, ge=0)
    path: str = ""

    @property
    def authoritative(self) -> bool:
        return self.kind in AUTHORITATIVE_SOURCE_KINDS


class CanonicalFact(BaseModel):
    """One auditable fact record.

    ``status`` combines objective lifecycle states with the two explicitly
    subjective epistemic states required by Phase 7.  Rumours and beliefs are
    never inserted into the objective-current index.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    value: Any

    source_event_ids: list[str] = Field(default_factory=list)
    source_narrative_ticks: list[int] = Field(default_factory=list)
    source_refs: list[FactSourceRef] = Field(default_factory=list)

    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)
    known_by: list[str] = Field(default_factory=list)

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reversible: bool = True
    supersedes_fact_id: str | None = None
    superseded_by_fact_id: str | None = None
    status: CanonicalFactStatus = "active"

    @model_validator(mode="after")
    def validate_interval_and_sources(self) -> "CanonicalFact":
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick < self.valid_from_tick
        ):
            raise ValueError("valid_until_tick must not precede valid_from_tick")
        if not (
            self.source_event_ids
            or self.source_narrative_ticks
            or self.source_refs
        ):
            raise ValueError("canonical fact requires at least one source")
        if self.status == "active" and not self.has_authoritative_source:
            raise ValueError(
                "active objective fact requires an authoritative source; "
                "derived views may only create historical/rumor/belief records"
            )
        return self

    @property
    def has_authoritative_source(self) -> bool:
        if self.source_event_ids or self.source_narrative_ticks:
            return True
        return any(ref.authoritative for ref in self.source_refs)

    @property
    def is_objective_current(self) -> bool:
        return self.status == "active" and self.valid_until_tick is None

    def semantic_key(self) -> tuple[str, str]:
        return self.subject_id, self.predicate


class CanonicalFactConflictError(ValueError):
    """Raised when the same identity is reused for different semantics."""


class OutOfOrderFactError(ValueError):
    """Raised when an older record attempts to replace a newer current fact."""


def canonical_fact_id(
    *,
    subject_id: str,
    predicate: str,
    value: Any,
    valid_from_tick: int,
    status: CanonicalFactStatus = "active",
) -> str:
    """Return a deterministic record ID without embedding prose or secrets."""

    epistemic_class = status if status in {"rumor", "belief"} else "objective"
    payload = {
        "subject_id": subject_id,
        "predicate": predicate,
        "value": value,
        "valid_from_tick": int(valid_from_tick),
        "epistemic_class": epistemic_class,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"fact_{hashlib.sha256(encoded).hexdigest()[:24]}"


def build_canonical_fact(
    *,
    subject_id: str,
    predicate: str,
    value: Any,
    valid_from_tick: int,
    source_event_ids: Iterable[str] = (),
    source_narrative_ticks: Iterable[int] = (),
    source_refs: Iterable[FactSourceRef] = (),
    known_by: Iterable[str] = (),
    confidence: float = 1.0,
    reversible: bool = True,
    supersedes_fact_id: str | None = None,
    status: CanonicalFactStatus = "active",
) -> CanonicalFact:
    """Build a normalized fact with a reproducible identity."""

    event_ids = sorted({str(item).strip() for item in source_event_ids if str(item).strip()})
    narrative_ticks = sorted({int(item) for item in source_narrative_ticks})
    refs = sorted(
        set(source_refs),
        key=lambda ref: (ref.kind, ref.source_id, ref.tick or -1, ref.path),
    )
    knowers = sorted({str(item).strip() for item in known_by if str(item).strip()})
    fact_id = canonical_fact_id(
        subject_id=subject_id,
        predicate=predicate,
        value=value,
        valid_from_tick=valid_from_tick,
        status=status,
    )
    return CanonicalFact(
        fact_id=fact_id,
        subject_id=subject_id,
        predicate=predicate,
        value=value,
        source_event_ids=event_ids,
        source_narrative_ticks=narrative_ticks,
        source_refs=refs,
        valid_from_tick=valid_from_tick,
        known_by=knowers,
        confidence=confidence,
        reversible=reversible,
        supersedes_fact_id=supersedes_fact_id,
        status=status,
    )


class CanonicalFactStore:
    """Atomic JSON sidecar with objective-current and epistemic queries."""

    FILENAME = "canonical_facts.json"
    VERSION = 1

    def __init__(self, data_dir: str) -> None:
        self._data_dir = os.path.abspath(data_dir)
        self._path = os.path.join(self._data_dir, self.FILENAME)
        self._facts: dict[str, CanonicalFact] = {}
        self._current: dict[tuple[str, str], str] = {}

    @property
    def path(self) -> str:
        return self._path

    @property
    def size(self) -> int:
        return len(self._facts)

    def get(self, fact_id: str) -> CanonicalFact | None:
        return self._facts.get(fact_id)

    def all_facts(self) -> list[CanonicalFact]:
        return list(self._facts.values())

    def current_facts(self) -> list[CanonicalFact]:
        return [
            self._facts[fact_id]
            for fact_id in self._current.values()
            if fact_id in self._facts
        ]

    def current_fact(
        self, subject_id: str, predicate: str
    ) -> CanonicalFact | None:
        fact_id = self._current.get((subject_id, predicate))
        return self._facts.get(fact_id) if fact_id else None

    def facts_known_by(
        self, character_id: str, *, include_subjective: bool = True
    ) -> list[CanonicalFact]:
        allowed = {"active"}
        if include_subjective:
            allowed.update({"rumor", "belief"})
        return [
            fact
            for fact in self._facts.values()
            if character_id in fact.known_by and fact.status in allowed
        ]

    def append(self, fact: CanonicalFact) -> CanonicalFact:
        """Insert idempotently and supersede only objective current facts."""

        existing_same_id = self._facts.get(fact.fact_id)
        if existing_same_id is not None:
            self._assert_same_semantics(existing_same_id, fact)
            merged = self._merge_provenance(existing_same_id, fact)
            self._facts[fact.fact_id] = merged
            return merged

        if fact.status == "active":
            key = fact.semantic_key()
            current_id = self._current.get(key)
            if current_id:
                current = self._facts[current_id]
                # A full continuity snapshot commonly repeats unchanged state.
                # Treat that as corroborating provenance, not a new lifecycle
                # transition with an artificial supersede edge.
                if current.value == fact.value:
                    merged = self._merge_provenance(current, fact)
                    self._facts[current_id] = merged
                    return merged
                if fact.valid_from_tick < current.valid_from_tick:
                    raise OutOfOrderFactError(
                        f"{fact.fact_id} at tick {fact.valid_from_tick} cannot "
                        f"replace {current.fact_id} at tick {current.valid_from_tick}"
                    )
                fact = fact.model_copy(
                    update={"supersedes_fact_id": current.fact_id}
                )
                self._facts[current.fact_id] = current.model_copy(
                    update={
                        "status": "superseded",
                        "valid_until_tick": fact.valid_from_tick,
                        "superseded_by_fact_id": fact.fact_id,
                    }
                )
            self._current[key] = fact.fact_id

        self._facts[fact.fact_id] = fact
        return fact

    def invalidate(
        self,
        fact_id: str,
        *,
        at_tick: int,
        source_ref: FactSourceRef,
    ) -> CanonicalFact:
        """Invalidate a current fact without inventing a replacement value."""

        fact = self._facts[fact_id]
        if at_tick < fact.valid_from_tick:
            raise OutOfOrderFactError("invalidation precedes fact validity")
        refs = sorted(
            set([*fact.source_refs, source_ref]),
            key=lambda ref: (ref.kind, ref.source_id, ref.tick or -1, ref.path),
        )
        updated = fact.model_copy(
            update={
                "status": "invalidated",
                "valid_until_tick": at_tick,
                "source_refs": refs,
            }
        )
        self._facts[fact_id] = updated
        if self._current.get(fact.semantic_key()) == fact_id:
            self._current.pop(fact.semantic_key(), None)
        return updated

    @staticmethod
    def _assert_same_semantics(a: CanonicalFact, b: CanonicalFact) -> None:
        fields = (
            "subject_id",
            "predicate",
            "value",
            "valid_from_tick",
        )
        if any(getattr(a, field) != getattr(b, field) for field in fields):
            raise CanonicalFactConflictError(
                f"fact identity collision for {a.fact_id}"
            )

    @staticmethod
    def _merge_provenance(
        a: CanonicalFact, b: CanonicalFact
    ) -> CanonicalFact:
        refs = sorted(
            set([*a.source_refs, *b.source_refs]),
            key=lambda ref: (ref.kind, ref.source_id, ref.tick or -1, ref.path),
        )
        return a.model_copy(
            update={
                "source_event_ids": sorted(
                    set([*a.source_event_ids, *b.source_event_ids])
                ),
                "source_narrative_ticks": sorted(
                    set([*a.source_narrative_ticks, *b.source_narrative_ticks])
                ),
                "source_refs": refs,
                "known_by": sorted(set([*a.known_by, *b.known_by])),
                "confidence": max(a.confidence, b.confidence),
                "reversible": a.reversible and b.reversible,
            }
        )

    def save(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "facts": [
                fact.model_dump(mode="json") for fact in self._facts.values()
            ],
        }
        fd, tmp_path = tempfile.mkstemp(
            prefix=".canonical_facts_",
            suffix=".tmp.json",
            dir=self._data_dir,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    def load(self) -> bool:
        if not os.path.isfile(self._path):
            return False
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if int(payload.get("version", 0)) != self.VERSION:
                logger.warning(
                    "Unsupported CanonicalFact sidecar version: %r",
                    payload.get("version"),
                )
                return False
            restored = [
                CanonicalFact.model_validate(item)
                for item in payload.get("facts", [])
            ]
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("CanonicalFactStore load failed: %s", exc)
            return False

        facts: dict[str, CanonicalFact] = {}
        current: dict[tuple[str, str], str] = {}
        for fact in restored:
            if fact.fact_id in facts:
                raise CanonicalFactConflictError(
                    f"duplicate fact id in sidecar: {fact.fact_id}"
                )
            facts[fact.fact_id] = fact
            if fact.is_objective_current:
                key = fact.semantic_key()
                previous_id = current.get(key)
                if previous_id is not None:
                    raise CanonicalFactConflictError(
                        f"multiple current facts for {key!r}"
                    )
                current[key] = fact.fact_id
        self._facts = facts
        self._current = current
        return True


__all__ = [
    "AUTHORITATIVE_SOURCE_KINDS",
    "DERIVED_SOURCE_KINDS",
    "CanonicalFact",
    "CanonicalFactConflictError",
    "CanonicalFactStatus",
    "CanonicalFactStore",
    "FactSourceKind",
    "FactSourceRef",
    "OutOfOrderFactError",
    "build_canonical_fact",
    "canonical_fact_id",
]
