"""Adapter from the experimental Tick simulator to author-mode authorities."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from story.models import SectionGoal, StateDeltaOperation, WriterCandidate
from story.service import AuthorGenerationService, StaleStoryBibleError


class SimulationNarrativeGateway:
    """Validate a narrator candidate before it becomes official prose/state.

    TickState remains the simulator's working memory.  Only typed projections
    attached to an accepted narrative cross this boundary into CanonicalState.
    Rejected candidates return ``False`` and are neither published nor committed.
    """

    def __init__(self, *, user_id: str, novel_id: str, data_dir: str, title: str) -> None:
        self.data_dir = os.path.realpath(os.path.abspath(data_dir))
        self.service = AuthorGenerationService(
            user_id=user_id,
            novel_id=novel_id,
            data_dir=self.data_dir,
            title=title,
        )

    async def __call__(
        self,
        tick: int,
        text: str,
        *,
        viewpoint_character_id: str = "",
        state_projection: Any = None,
    ) -> bool:
        state = self.service.states.load()
        operations = self._operations(state_projection, text, state)
        candidate = WriterCandidate(
            narrative_text=text,
            title=f"模拟记录 · Tick {tick}",
            section_summary=self._summary(text),
            state_delta=operations,
            consistency_notes=["candidate_source=simulation", f"tick={tick}"],
        )
        try:
            transaction = await self.service.submit_candidate(
                SectionGoal(
                    objective=f"将实验模拟 tick {tick} 的已验证结果纳入主叙事",
                    viewpoint_character_id=viewpoint_character_id,
                    involved_characters=(
                        [viewpoint_character_id] if viewpoint_character_id else []
                    ),
                    desired_length=max(200, min(10000, len(text))),
                ),
                candidate,
                request_id=f"simulation_tick_{tick:08d}",
                generation_mode="simulation",
            )
        except StaleStoryBibleError:
            return False
        if not transaction.committed:
            return False
        self._publish_legacy_narrative(
            tick,
            text,
            viewpoint_character_id=viewpoint_character_id,
            canonical_revision=transaction.target_canonical_revision,
        )
        return True

    @staticmethod
    def _summary(text: str) -> str:
        compact = " ".join(text.split())
        return compact[:220] or "模拟候选无正文摘要"

    def _operations(
        self, projection: Any, narrative: str, state
    ) -> list[StateDeltaOperation]:
        facts = list(getattr(projection, "facts", []) or [])
        operations: list[StateDeltaOperation] = []
        for fact in facts:
            evidence = self._narrative_evidence(fact, narrative, state)
            operation = self._fact_operation(fact, evidence)
            if operation is not None:
                operations.append(operation)
        # Last typed fact for a path wins within the same tick.
        by_path = {operation.path: operation for operation in operations}
        return list(by_path.values())

    @staticmethod
    def _fact_operation(
        fact: Any, evidence: str = ""
    ) -> StateDeltaOperation | None:
        subject = str(getattr(fact, "subject_id", "") or "")
        predicate = str(getattr(fact, "predicate", "") or "")
        value = getattr(fact, "value", None)
        if subject == "world" and predicate == "world_time":
            return StateDeltaOperation(
                op="set", path="/world_time", value=value, evidence=evidence
            )
        if subject == "world" and predicate in {
            "era",
            "current_season",
            "weather",
            "active_global_events",
            "world_rules",
        }:
            return StateDeltaOperation(
                op="set", path=f"/world/{predicate}", value=value, evidence=evidence
            )
        if predicate == "character_location" and isinstance(value, dict):
            return StateDeltaOperation(
                op="set",
                path=f"/characters/{subject}/location",
                value=value.get("location_id"),
                evidence=evidence,
            )
        if predicate == "alive_status":
            return StateDeltaOperation(
                op="set",
                path=f"/characters/{subject}/alive",
                value=value != "dead",
                evidence=evidence,
            )
        if predicate == "money_balance":
            return StateDeltaOperation(
                op="set",
                path=f"/characters/{subject}/money",
                value=value,
                evidence=evidence,
            )
        if predicate.startswith("trust:"):
            other = predicate.split(":", 1)[1]
            return StateDeltaOperation(
                op="set",
                path=f"/relationships/{subject}:{other}/trust",
                value=value,
                evidence=evidence,
            )
        if predicate.startswith("character_knows:") and isinstance(value, dict):
            proposition = value.get("proposition")
            if proposition:
                return StateDeltaOperation(
                    op="append",
                    path=f"/character_knowledge/{subject}",
                    value=proposition,
                    evidence=evidence,
                )
        return None

    @staticmethod
    def _narrative_evidence(fact: Any, narrative: str, state) -> str:
        """Return an exact prose span proving the projection, or empty."""

        subject = str(getattr(fact, "subject_id", "") or "")
        predicate = str(getattr(fact, "predicate", "") or "")
        value = getattr(fact, "value", None)
        subject_name = str(state.characters.get(subject, {}).get("name") or subject)
        required = [subject_name] if subject != "world" and subject_name else []
        if predicate == "character_location" and isinstance(value, dict):
            location_id = str(value.get("location_id") or "")
            location_name = location_id
            locations = state.world.get("locations", [])
            iterable = locations.values() if isinstance(locations, dict) else locations
            for item in iterable:
                if not isinstance(item, dict):
                    continue
                if str(item.get("id") or item.get("name") or "") == location_id:
                    location_name = str(item.get("name") or location_id)
                    break
            if location_name:
                required.append(location_name)
        elif predicate == "alive_status":
            required.append("死亡" if value == "dead" else "活")
        elif isinstance(value, (str, int, float)):
            required.append(str(value))

        for sentence in re.split(r"(?<=[。！？!?])", narrative):
            span = sentence.strip()
            if span and required and all(token in span for token in required):
                return span
        return ""

    def _publish_legacy_narrative(
        self,
        tick: int,
        text: str,
        *,
        viewpoint_character_id: str,
        canonical_revision: int,
    ) -> None:
        directory = Path(self.data_dir) / "narratives"
        directory.mkdir(parents=True, exist_ok=True)
        self._atomic_text(directory / f"tick_{tick:06d}.txt", text)
        sidecar = {
            "viewpoint_character_id": viewpoint_character_id or None,
            "canonical_state_revision": canonical_revision,
            "authority": "validated_simulation_candidate",
        }
        self._atomic_text(
            directory / f"tick_{tick:06d}.meta.json",
            json.dumps(sidecar, ensure_ascii=False, indent=2),
        )

    @staticmethod
    def _atomic_text(path: Path, content: str) -> None:
        descriptor, temp_path = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise


__all__ = ["SimulationNarrativeGateway"]
