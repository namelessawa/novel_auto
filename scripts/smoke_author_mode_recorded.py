"""Provider-free recorded smoke for the author authority and recovery chain.

This deliberately validates persistence and transaction semantics only.  It
uses a deterministic Writer and therefore makes no claim about literary
quality.  No provider credentials are read and no network call is made.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))


class RecordedWriter:
    def __init__(self, candidates) -> None:
        self.candidates = list(candidates)
        self.contexts = []
        self.generate_calls = 0
        self.repair_calls = 0

    async def generate(self, context, goal):
        from story.chapter_plan import ChapterEvidence
        from story.writer import WriterResult

        self.contexts.append(context)
        self.generate_calls += 1
        if not self.candidates:
            raise AssertionError("recorded Writer candidate queue exhausted")
        candidate = self.candidates.pop(0)
        narrative_text = candidate.narrative_text
        event_plan = context.event_execution_plan
        if event_plan is not None:
            completion_lines = [
                item.minimum_completion_evidence
                for item in [
                    *event_plan.ordered_events,
                    *event_plan.required_end_states,
                ]
                if item.minimum_completion_evidence
                and item.minimum_completion_evidence not in narrative_text
            ]
            if completion_lines:
                narrative_text = "".join([narrative_text, *completion_lines])
        chapter_evidence = [
            ChapterEvidence(
                segment=segment.order,
                events_completed=segment.events,
            )
            for segment in (context.chapter_plan.segments if context.chapter_plan else [])
        ]
        return WriterResult(
            candidate=candidate.model_copy(
                update={
                    "narrative_text": narrative_text,
                    "chapter_evidence": chapter_evidence,
                }
            ),
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    async def repair(self, candidate, report):
        from story.repair_patch import RepairPatchSet
        from story.repair_plan import repair_patch_prompt_payload
        from story.writer import WriterResult

        self.repair_calls += 1
        # Repair authority is patch-only. Structured proposals stay on the
        # original candidate and are rechecked/dropped by the server.
        return WriterResult(
            candidate=candidate,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            repair_patches=RepairPatchSet.model_validate(
                {
                    "patches": repair_patch_prompt_payload(
                        report,
                        candidate.narrative_text,
                    )["suggested_patch_templates"]
                }
            ),
        )


def _candidate(text: str, summary: str, *, delta=None, memories=None):
    from story.models import WriterCandidate

    padding = "沈砚仍在旧灯塔核对旧信，只确认当前已经发生的事实。"
    narrative = text
    while sum(not char.isspace() for char in narrative) < 420:
        narrative += padding
    return WriterCandidate(
        narrative_text=narrative,
        title=summary[:12],
        section_summary=summary,
        state_delta=delta or [],
        memory_records=memories or [],
    )


def _goal(objective: str):
    from story.models import SectionGoal

    return SectionGoal(
        objective=objective,
        viewpoint_character_id="shen_yan",
        location_id="lighthouse",
        involved_characters=["shen_yan"],
        desired_length=400,
    )


def _revise_style(service) -> int:
    from story.models import StoryBibleUpdate

    current = service.bibles.load()
    updated = service.bibles.update(
        StoryBibleUpdate(
            expected_revision=current.revision,
            title=current.title,
            source_seed=current.source_seed,
            theme_key=current.theme_key,
            positioning=current.positioning,
            reference_preferences=current.reference_preferences,
            premise=current.premise,
            theme=current.theme,
            central_question=current.central_question,
            genre=current.genre,
            setting_summary=current.setting_summary,
            immutable_world_rules=current.immutable_world_rules,
            forbidden_deviations=current.forbidden_deviations,
            protagonist_contracts=current.protagonist_contracts,
            main_conflicts=current.main_conflicts,
            ending_direction=current.ending_direction,
            style_contract={"key": "restrained_v2", "tone": "克制、具体"},
        )
    )
    return updated.revision


async def run_recorded(data_dir: Path) -> dict:
    from sections.section_store import _clear_for_tests
    from story.models import (
        CanonicalState,
        MemoryRecord,
        StateDeltaOperation,
    )
    from story.service import AuthorGenerationService, StaleStoryBibleError

    exact_seed = "潮退后的旧港。  保留两个空格\n第二行：破折号——与引号“原样”。"
    first = _candidate(
        "沈砚在旧灯塔握紧旧信，警觉地望向门口。",
        "沈砚因旧信提高警觉。",
        delta=[
            StateDeltaOperation(
                op="set",
                path="/characters/shen_yan/emotional_state",
                value="警觉",
                evidence="沈砚在旧灯塔握紧旧信，警觉地望向门口。",
            )
        ],
    )
    stale_candidate = _candidate(
        "沈砚已经实际完成“让沈砚暂缓选择。”，动作结果已经发生。"
        "他把旧信放回桌面，没有作出新的事实承诺。",
        "沈砚暂停决定。",
    )
    fresh_memory = MemoryRecord(
        id="decision_disclose_truth",
        type="decision",
        entities=["shen_yan"],
        summary="沈砚决定承担公开港难真相的关系代价。",
        evidence="沈砚决定公开真相。",
        importance=9,
    )
    fresh = _candidate(
        "沈砚决定公开真相，也接受这会伤害家族关系。",
        "沈砚作出公开真相的决定。",
        memories=[fresh_memory],
    )
    missing_evidence = _candidate(
        "窗外仍旧平静，沈砚继续核对旧信。",
        "沈砚继续核对旧信。",
        delta=[
            StateDeltaOperation(
                op="set",
                path="/world/weather",
                value="暴雨",
                evidence="",
            )
        ],
    )
    writer = RecordedWriter([first, stale_candidate, fresh, missing_evidence])
    _clear_for_tests()
    service = AuthorGenerationService(
        user_id="recorded_smoke",
        novel_id="recorded_authority",
        data_dir=str(data_dir),
        title="潮痕",
        writer=writer,
    )

    # 1-2. Persist the user's exact bootstrap input before any Writer call.
    persisted = service.bibles.initialise_from_user_inputs(
        title="潮痕",
        source_seed=exact_seed,
        theme_key="republic_spy",
        theme_label="记忆、责任与诚实的代价",
        positioning="克制的现实主义悬疑",
        references="只参考节奏，不复制表达",
        style_contract={"key": "restrained_v1", "tone": "克制"},
        preset_seed=False,
    )
    if persisted.source_seed != exact_seed:
        raise AssertionError("StoryBible did not preserve the exact seed")
    service.states.save(
        CanonicalState(
            revision=1,
            world={
                "locations": [
                    {"id": "lighthouse", "name": "旧灯塔"},
                    {"id": "archive", "name": "档案室"},
                ]
            },
            characters={
                "shen_yan": {
                    "name": "沈砚",
                    "alive": True,
                    "location": "lighthouse",
                    "emotional_state": "迟疑",
                    "inventory": ["sealed_letter"],
                }
            },
            items={
                "sealed_letter": {
                    "name": "旧信",
                    "owners": ["shen_yan"],
                    "location": "lighthouse",
                }
            },
        )
    )

    # 3. First normal commit.
    first_tx = await service.run(_goal("让沈砚察觉旧信带来的风险。"), request_id="recorded_first")

    # 4-5. Stage on the old Bible, revise the Bible, then prove commit/recovery guard.
    stale_prepared = service.prepare(
        _goal("让沈砚暂缓选择。"), request_id="recorded_stale"
    )
    generated = await service.generate(stale_prepared)
    stale_tx = service._record_generated(stale_prepared.transaction, generated)
    stale_report = service.validate(stale_prepared, generated.candidate)
    staged = service._stage(
        stale_prepared, stale_tx, generated.candidate, stale_report
    )
    before_stale = {
        "state": service.states.load().model_dump(mode="json"),
        "threads": service.threads.load().model_dump(mode="json"),
        "memory": service.memories.load().model_dump(mode="json"),
        "sections": service.sections.count(),
    }
    revised_bible_revision = _revise_style(service)
    try:
        service.commit(staged)
    except StaleStoryBibleError as exc:
        stale_result = exc.transaction
    else:
        raise AssertionError("stale StoryBible transaction unexpectedly committed")
    after_stale = {
        "state": service.states.load().model_dump(mode="json"),
        "threads": service.threads.load().model_dump(mode="json"),
        "memory": service.memories.load().model_dump(mode="json"),
        "sections": service.sections.count(),
    }
    if before_stale != after_stale:
        raise AssertionError("stale transaction caused a partial commit")

    # 6. A fresh request on the new Bible revision succeeds and writes memory.
    fresh_tx = await service.run(
        _goal("让沈砚决定承担公开真相的代价。"),
        request_id="recorded_fresh",
    )

    # 7-8. Evidence-less StateDelta can be diagnosed/repaired but not persisted.
    evidence_tx = await service.run(
        _goal("让沈砚继续核对旧信。"),
        request_id="recorded_missing_evidence",
    )
    if "weather" in service.states.load().world:
        raise AssertionError("evidence-less delta entered CanonicalState")
    if evidence_tx.validation_report is None or evidence_tx.validation_report.validated_delta:
        raise AssertionError("evidence-less delta entered validated_delta")

    # 9-10. Reconstruct stores/runtime and inspect the exact Writer context.
    restart_candidate = _candidate(
        "重启后，沈砚仍记得自己决定公开真相，并继续承担关系代价。",
        "重启后继续执行既有决定。",
    )
    restarted_writer = RecordedWriter([restart_candidate])
    del service
    _clear_for_tests()
    restarted = AuthorGenerationService(
        user_id="recorded_smoke",
        novel_id="recorded_authority",
        data_dir=str(data_dir),
        title="潮痕",
        writer=restarted_writer,
    )
    if restarted.bibles.load().source_seed != exact_seed:
        raise AssertionError("exact seed changed after runtime reconstruction")
    restart_tx = await restarted.run(
        _goal("延续公开真相决定的后果。"), request_id="recorded_restart"
    )
    final_context = restarted_writer.contexts[-1]
    bible_slot = final_context.slots["story_bible"]
    memory_slot = final_context.slots["relevant_long_term_memories"]
    if not all(line in bible_slot for line in exact_seed.splitlines()):
        raise AssertionError("restarted Writer context omitted the original StoryBible seed")
    if fresh_memory.summary not in memory_slot:
        raise AssertionError("restarted Writer context omitted long-term memory")

    result = {
        "ok": True,
        "evidence_source": "deterministic_recorded_writer",
        "literary_quality_claimed": False,
        "provider_calls": 0,
        "provider_tokens": 0,
        "steps": {
            "1_custom_seed_created": True,
            "2_exact_seed_persisted": restarted.bibles.load().source_seed == exact_seed,
            "3_first_section_committed": first_tx.committed,
            "4_story_bible_revision_modified": revised_bible_revision,
            "5_stale_transaction_blocked": (
                stale_result.phase == "stale_context"
                and stale_result.error_code == "STORY_BIBLE_REVISION_STALE"
                and not stale_result.committed
            ),
            "6_fresh_transaction_committed": fresh_tx.committed,
            "7_missing_evidence_delta_constructed": True,
            "8_missing_evidence_delta_excluded": "weather" not in restarted.states.load().world,
            "9_runtime_reconstructed": True,
            "10_original_bible_and_memory_reused": (
                all(line in bible_slot for line in exact_seed.splitlines())
                and fresh_memory.summary in memory_slot
                and restart_tx.committed
            ),
        },
        "final": {
            "story_bible_revision": restarted.bibles.load().revision,
            "canonical_state_revision": restarted.states.load().revision,
            "section_count": restarted.sections.count(),
            "memory_count": len(restarted.memories.load().records),
            "writer_calls": writer.generate_calls + restarted_writer.generate_calls,
            "repair_calls": writer.repair_calls + restarted_writer.repair_calls,
        },
    }
    boolean_steps = [
        value
        for key, value in result["steps"].items()
        if key != "4_story_bible_revision_modified"
    ]
    if not all(value is True for value in boolean_steps):
        raise AssertionError("recorded smoke did not complete all ten steps")
    _clear_for_tests()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    if args.data_dir:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        result = asyncio.run(run_recorded(args.data_dir.resolve()))
    else:
        with tempfile.TemporaryDirectory(prefix="author-recorded-smoke-") as temp:
            result = asyncio.run(run_recorded(Path(temp)))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
