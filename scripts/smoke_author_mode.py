"""Real-provider smoke for the default author-mode transaction chain.

Credentials are accepted only through environment variables and never printed:
``SMOKE_LLM_KEY``, ``SMOKE_LLM_BASE_URL``, and ``SMOKE_LLM_MODEL``.
The smoke writes to a temporary directory unless ``--data-dir`` is supplied.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


async def _run(data_dir: Path, desired_length: int) -> dict:
    from nf_core.llm_client import set_user_llm_config
    from story.context_builder import SLOT_ORDER
    from story.models import CanonicalState, SectionGoal, StoryBibleUpdate
    from story.service import AuthorGenerationService, GenerationRejected

    set_user_llm_config(
        api_key=_require_env("SMOKE_LLM_KEY"),
        base_url=_require_env("SMOKE_LLM_BASE_URL"),
        model=_require_env("SMOKE_LLM_MODEL"),
    )
    service = AuthorGenerationService(
        user_id="author_smoke",
        novel_id="harbor_smoke",
        data_dir=str(data_dir),
        title="潮痕",
    )
    bible = service.bibles.load()
    if bible.revision == 1:
        service.bibles.update(
            StoryBibleUpdate(
                expected_revision=1,
                source_seed="退潮后的封港城里，守灯人隐瞒一封会改变家族命运的旧信。",
                premise="年轻守灯人沈砚必须在保住家族名誉与公开港难真相之间选择。",
                theme="记忆、责任与诚实的代价",
                central_question="一个人是否能用沉默保护所爱之人？",
                genre="克制的现实主义悬疑",
                setting_summary="无超自然力量的近代封港城；潮汐、旧灯塔与港务档案决定行动边界。",
                immutable_world_rules=["世界不存在超自然力量", "死亡不可逆"],
                forbidden_deviations=["不得把冲突改写为超能力对决", "不得让旧信无代价地解决所有问题"],
                protagonist_contracts=["沈砚谨慎、重承诺，但会为真相承担关系代价"],
                main_conflicts=["公开港难真相会伤害沈家，但继续隐瞒会让无辜者承担污名"],
                ending_direction="真相被公开，关系留下可见裂痕，但责任开始被重新分配。",
                style_contract={"tone": "克制", "viewpoint": "第三人称限知", "avoid": ["空泛说教"]},
            )
        )
        state = CanonicalState(
            revision=1,
            world_time=1,
            world={
                "name": "临潮港",
                "locations": [
                    {"id": "lighthouse", "name": "旧灯塔"},
                    {"id": "archive", "name": "港务档案室"},
                ],
            },
            characters={
                "shen_yan": {
                    "name": "沈砚",
                    "alive": True,
                    "location": "lighthouse",
                    "emotional_state": "迟疑",
                    "inventory": ["sealed_letter"],
                },
                "lin_qiu": {
                    "name": "林秋",
                    "alive": True,
                    "location": "lighthouse",
                    "emotional_state": "信任沈砚",
                    "inventory": [],
                },
            },
            items={
                "sealed_letter": {
                    "name": "旧信",
                    "owners": ["shen_yan"],
                    "location": "lighthouse",
                    "status": "未拆封",
                }
            },
            character_knowledge={"shen_yan": ["旧信与十二年前港难有关"]},
            relationships={"shen_yan:lin_qiu": {"trust": 7, "description": "共同查找港难记录"}},
            reader_knowledge={"letter_link": "旧信与港难有关，但内容未知"},
            plot_position={"arc": "opening", "beat": "hesitation"},
            last_scene_state={"location": "lighthouse", "time": "退潮后的清晨"},
        )
        service.states.save(state)

    goals = [
        "沈砚在旧灯塔拆开信，确认它关联港难，但暂不公开；写清他选择沉默的具体代价。",
        "林秋带来港务记录抄本，在旧灯塔与沈砚核对；沈砚因继续隐瞒而第一次失去她的信任。",
        "港务调查员来到旧灯塔，沈砚主动交出一份可核验证据，但保留更难面对的家族责任。",
        "重启后继续：所有人仍在旧灯塔，让前一节的关系裂痕产生实际后果，并保持无超自然设定。",
    ]
    results = []
    for index, objective in enumerate(goals[:3], start=1):
        try:
            tx = await service.run(
                SectionGoal(
                    objective=objective,
                    viewpoint_character_id="shen_yan",
                    location_id="lighthouse",
                    involved_characters=["shen_yan", "lin_qiu"],
                    desired_length=desired_length,
                ),
                request_id=f"real_smoke_{index}",
            )
        except GenerationRejected as exc:
            report = exc.transaction.validation_report
            codes = [item.code for item in report.violations] if report else []
            raise RuntimeError(
                f"section {index} rejected after one repair; codes={codes}"
            ) from exc
        results.append(_summary(tx, service))

    # Reconstruct every repository and recovery hook as a process restart would.
    del service
    restarted = AuthorGenerationService(
        user_id="author_smoke",
        novel_id="harbor_smoke",
        data_dir=str(data_dir),
        title="潮痕",
    )
    tx = await restarted.run(
        SectionGoal(
            objective=goals[3],
            viewpoint_character_id="shen_yan",
            location_id="lighthouse",
            involved_characters=["shen_yan", "lin_qiu"],
            desired_length=desired_length,
        ),
        request_id="real_smoke_restart_4",
    )
    results.append(_summary(tx, restarted))

    final_bible = restarted.bibles.load()
    final_state = restarted.states.load()
    sections = restarted.sections.list_all()
    if len(sections) != 4:
        raise AssertionError(f"expected 4 committed sections, got {len(sections)}")
    if final_bible.revision != 2 or final_bible.theme != "记忆、责任与诚实的代价":
        raise AssertionError("StoryBible drifted during generation")
    if final_state.revision != 5:
        raise AssertionError(f"expected CanonicalState revision 5, got {final_state.revision}")
    if any(
        len(item.editor_trace.get("context_manifest", {}).get("slots", []))
        != len(SLOT_ORDER)
        for item in sections
    ):
        raise AssertionError("context manifest slot count changed")
    return {
        "ok": True,
        "provider_model": os.environ["SMOKE_LLM_MODEL"],
        "sections": results,
        "final": {
            "story_bible_revision": final_bible.revision,
            "canonical_state_revision": final_state.revision,
            "section_count": len(sections),
            "memory_count": len(restarted.memories.load().records),
            "restart_generation_committed": results[-1]["committed"],
        },
    }


def _summary(transaction, service) -> dict:
    report = transaction.validation_report
    candidate = transaction.candidate
    return {
        "id": transaction.id,
        "phase": transaction.phase,
        "committed": transaction.committed,
        "writer_calls": transaction.writer_calls,
        "repair_performed": transaction.repair_performed,
        "story_bible_revision": transaction.story_bible_revision,
        "canonical_state_revision": service.states.load().revision,
        "narrative_chars": len(candidate.narrative_text if candidate else ""),
        "validation_severity": report.severity if report else "unknown",
        "violation_codes": [item.code for item in report.violations] if report else [],
        "usage": transaction.usage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--desired-length", type=int, default=500)
    args = parser.parse_args()
    if args.data_dir:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        result = asyncio.run(_run(args.data_dir.resolve(), args.desired_length))
    else:
        with tempfile.TemporaryDirectory(prefix="novel-author-smoke-") as temp_dir:
            result = asyncio.run(_run(Path(temp_dir), args.desired_length))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
