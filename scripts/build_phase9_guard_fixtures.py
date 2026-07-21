"""Build the deterministic Phase 9 complete Guard replay suites.

The generated fixtures are synthetic, current-Tick-only and contain no credentials
or private novel text.  Every negative explicitly records three verifier responses
and two complete repair responses so it traverses the bounded production Guard
control flow before rejection.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path


def _character(
    character_id: str,
    location_id: str,
    *,
    injuries: list[dict] | None = None,
    knowledge_fact_ids: list[str] | None = None,
) -> dict:
    return {
        "character_id": character_id,
        "location_id": location_id,
        "movement_status": "arrived",
        "destination_location_id": None,
        "alive_status": "alive",
        "injuries": injuries or [],
        "supporting_character_ids": [],
        "carried_by_character_id": None,
        "knowledge_fact_ids": knowledge_fact_ids or [],
    }


def _item(
    holders: list[str],
    *,
    condition: str = "damaged",
    quantity: int | float | None = 1,
) -> dict:
    return {
        "item_id": "map",
        "holder_character_ids": holders,
        "location_id": None,
        "quantity": quantity,
        "condition": condition,
        "container_item_id": None,
    }


def _typed_state(
    *,
    alice_location: str = "city_gate_outer",
    bob_location: str = "city_gate_outer",
    holders: list[str] | None = None,
    condition: str = "damaged",
    quantity: int | float | None = 1,
    alice_injuries: list[dict] | None = None,
    alice_knowledge: list[str] | None = None,
    newly_known: dict[str, list[str]] | None = None,
) -> dict:
    return {
        "schema_version": "1",
        "time_marker": "tick:1",
        "characters": {
            "alice": _character(
                "alice",
                alice_location,
                injuries=alice_injuries,
                knowledge_fact_ids=alice_knowledge,
            ),
            "bob": _character("bob", bob_location),
        },
        "items": {
            "map": _item(
                holders if holders is not None else ["alice"],
                condition=condition,
                quantity=quantity,
            )
        },
        "newly_known_fact_ids": newly_known or {},
        "active_open_loop_ids": [],
    }


def _typed_audit(state: dict) -> dict:
    return {
        "source_schema": "typed_v1",
        "typed_state": deepcopy(state),
        "raw_payload": deepcopy(state),
        "issues": [],
        "authoritative_eligible": True,
        "references_checked": True,
    }


def _narrator(text: str, state: dict) -> dict:
    return {
        "content": {
            "narrative_text": text,
            "estimated_length": "short",
            "viewpoint_characters": ["alice"],
            "scene_focus": "Phase 9 StateGuard calibration",
            "events_consumed": ["evt_map_gate"],
            "open_loops_referenced": [],
            "resolved_open_loops": [],
            "newly_opened_loops": [],
            "continuity_state": state,
            "style_diagnostics": {},
            "consistency_flags": [],
        }
    }


def _verdict(
    requirement: str,
    *,
    message: str,
    error_types: list[str],
    met: bool = False,
    evidence: list[str] | None = None,
    paths: list[str] | None = None,
) -> dict:
    event_conflicts = [message] if (
        not met
        or "event_endpoint_unfulfilled" in error_types
        or "location_mismatch" in error_types
    ) else []
    return {
        "content": {
            "safe": False,
            "event_checks": [{
                "event_id": "evt_map_gate",
                "requirement": requirement,
                "met": met,
                "prose_evidence": evidence or [],
                "ledger_evidence_paths": paths or [],
            }],
            "event_fulfillment_conflicts": event_conflicts,
            "entity_grounding_conflicts": [message] if (
                "new_ungrounded_fact" in error_types
            ) else [],
            "prior_state_conflicts": [message] if any(code in error_types for code in (
                "item_holder_conflict",
                "item_condition_conflict",
                "knowledge_leak",
            )) else [],
            "internal_conflicts": [],
            "ledger_conflicts": [message] if any(code in error_types for code in (
                "ledger_wrong_type", "ledger_missing_field"
            )) else [],
            "fact_changes_from_original": [message] if (
                "repair_fact_change" in error_types
            ) else [],
            "reason": message,
        }
    }


def _repair(text: str, state: dict, message: str) -> dict:
    return {
        "content": {
            "narrative_text": text,
            "continuity_state": state,
            "repairs": [message],
        }
    }


def _case(
    *,
    case_id: str,
    title: str,
    previous: dict,
    narrative: str,
    declared: dict,
    requirement: str,
    error_types: list[str],
    message: str,
    repair_text: str | None = None,
    repair_state: dict | None = None,
    first_verdict: dict | None = None,
    force_critic: bool = False,
) -> dict:
    failed = _verdict(
        requirement,
        message=message,
        error_types=error_types,
    )
    repair_text = repair_text or narrative
    repair_state = repair_state or declared
    return {
        "case_id": case_id,
        "title": title,
        "previous_continuity_state": previous,
        "previous_continuity_audit": _typed_audit(previous),
        "narrator_response": _narrator(narrative, declared),
        "critic_responses": ({
            "narrative_critic:critique": [{
                "content": {
                    "triggers": [],
                    "rationale": "无文学层触发，交由 StateGuard 核对终态。",
                    "red_team_critiques": [],
                }
            }]
        } if force_critic else {}),
        "verifier_responses": [
            first_verdict or failed,
            failed,
            failed,
        ],
        "repair_responses": [
            _repair(repair_text, repair_state, "保留完整修订候选供复验"),
            _repair(repair_text, repair_state, "第二次完整修订候选仍供独立复验"),
        ],
        "required_end_states": [requirement],
        "expected_final_decision": "reject",
        "expected_error_types": error_types,
        "force_critic": force_critic,
    }


def build_hard_negative_suite() -> dict:
    outside = _typed_state()
    cases: list[dict] = []
    cases.append(_case(
        case_id="phase9-hn-location-outer-fort",
        title="要求进入城内但只到外堡",
        previous=outside,
        narrative="Alice穿过第一道拒马，在外堡门洞停住；内城门仍紧闭。Bob还在她身后喘息。",
        declared=_typed_state(alice_location="city_gate_outer"),
        requirement="本段结束前：Alice已进入city_gate_inner",
        error_types=["event_endpoint_unfulfilled", "location_mismatch"],
        message="正文与ledger均停在外侧，未进入city_gate_inner。",
        force_critic=True,
    ))
    cases.append(_case(
        case_id="phase9-hn-location-watchtower",
        title="守望塔不等于城内终点",
        previous=outside,
        narrative="Alice爬上门外守望塔，隔着铁栅看见城内灯火；她没有越过内门。",
        declared=_typed_state(alice_location="gate_watchtower"),
        requirement="本段结束前：Alice已进入city_gate_inner",
        error_types=[
            "event_endpoint_unfulfilled", "location_mismatch", "ledger_missing_field"
        ],
        message="gate_watchtower不在已提供地点目录，也不能证明进入城内。",
    ))
    bad_location = _typed_state()
    bad_location["characters"]["alice"]["location_id"] = "由Alice架着"
    cases.append(_case(
        case_id="phase9-hn-location-action-phrase",
        title="支撑动作污染地点字段",
        previous=outside,
        narrative="Bob架着Alice向门边挪动，两人最终仍停在外侧。",
        declared=bad_location,
        requirement="本段结束前：Alice已进入city_gate_inner",
        error_types=[
            "event_endpoint_unfulfilled", "location_mismatch", "ledger_wrong_type"
        ],
        message="location_id保存支撑动作且正文未越过门线。",
    ))
    cases.append(_case(
        case_id="phase9-hn-holder-reverts",
        title="地图交付后holder回退",
        previous=outside,
        narrative="Bob接过地图，封进自己的铁匣。Alice空着手退开。",
        declared=_typed_state(holders=["alice"]),
        requirement="本段结束前：map由bob持有",
        error_types=["item_holder_conflict"],
        message="正文明确交给Bob，ledger却仍声明Alice持有。",
    ))
    bad_holder = _typed_state()
    bad_holder["items"]["map"]["holder_character_ids"] = "alice"
    cases.append(_case(
        case_id="phase9-hn-holder-wrong-type",
        title="holder列表被错误写成字符串",
        previous=outside,
        narrative="Bob把地图收进铁匣，Alice松开了手。",
        declared=bad_holder,
        requirement="本段结束前：map由bob持有",
        error_types=[
            "item_holder_conflict", "ledger_wrong_type", "ledger_missing_field"
        ],
        message="holder字段类型错误且无法证明Bob持有。",
    ))
    cases.append(_case(
        case_id="phase9-hn-holder-and-knowledge-missing",
        title="物品holder缺失且角色越权知道暗号",
        previous=outside,
        narrative="Bob收下地图。Alice却无来源地说出了只有守门人才知道的内门暗号。",
        declared=_typed_state(holders=[]),
        requirement="本段结束前：map由bob持有",
        error_types=[
            "item_holder_conflict", "ledger_missing_field", "knowledge_leak"
        ],
        message="holder遗漏，且Alice说出无合法来源的暗号。",
    ))
    damaged = _typed_state(condition="damaged")
    cases.append(_case(
        case_id="phase9-hn-condition-restored",
        title="损坏地图无修复恢复完好",
        previous=damaged,
        narrative="Alice只是把湿透开裂的地图重新折好，没有进行任何修复。",
        declared=_typed_state(condition="intact"),
        requirement="本段结束前：map仍为damaged",
        error_types=["item_condition_conflict", "new_ungrounded_fact"],
        message="没有修复事件，map却从damaged恢复为intact。",
    ))
    consumed = _typed_state(condition="damaged", quantity=0)
    repaired_restore = _typed_state(condition="intact", quantity=1)
    initial_format_verdict = _verdict(
        "本段结束前：map仍为damaged且quantity为0",
        message="初稿状态格式需要复核。",
        error_types=["ledger_missing_field"],
        met=True,
        evidence=["最后一片地图也被酸雨泡烂"],
        paths=["items.map.condition", "items.map.quantity"],
    )
    cases.append(_case(
        case_id="phase9-hn-repair-restores-item",
        title="repair凭空恢复已耗尽物品",
        previous=consumed,
        narrative="最后一片地图也被酸雨泡烂，Alice确认已经没有可用副本。",
        declared=consumed,
        requirement="本段结束前：map仍为damaged且quantity为0",
        error_types=[
            "repair_fact_change", "item_condition_conflict", "new_ungrounded_fact"
        ],
        message="repair把damaged/0改成intact/1，改变既成事实。",
        repair_text="Alice从口袋取出一张完好地图，数量重新变成一。",
        repair_state=repaired_restore,
        first_verdict=initial_format_verdict,
    ))
    bad_knowledge = _typed_state()
    bad_knowledge["newly_known_fact_ids"] = {"alice": "fact_secret_route"}
    cases.append(_case(
        case_id="phase9-hn-knowledge-leak",
        title="角色无来源知道密道",
        previous=outside,
        narrative="Alice说密道就在钟楼第三块砖后，但此前没有人向她透露这个位置。",
        declared=bad_knowledge,
        requirement="本段结束前：Alice不得新增无来源的密道知识",
        error_types=[
            "knowledge_leak", "new_ungrounded_fact", "ledger_wrong_type",
            "ledger_missing_field"
        ],
        message="知识无来源且newly_known_fact_ids类型错误。",
    ))
    cases.append(_case(
        case_id="phase9-hn-cost-omitted-secret",
        title="入城完成但必达代价缺失并越权知道口令",
        previous=outside,
        narrative="内门打开，Alice和Bob进入城内。Alice随后无来源地念出值班口令。谈判没有产生任何代价。",
        declared=_typed_state(
            alice_location="city_gate_inner",
            bob_location="city_gate_inner",
        ),
        requirement="本段结束前：谈判产生一项正文明写的新代价",
        error_types=[
            "event_endpoint_unfulfilled", "ledger_missing_field", "knowledge_leak",
            "new_ungrounded_fact"
        ],
        message="正文没有新代价，口令知识也没有来源。",
    ))
    delivered = _typed_state(holders=["bob"])
    delete_handoff = _typed_state(holders=["alice"])
    first_handoff = _verdict(
        "本段结束前：map由bob持有",
        message="初稿交付已完成，仅要求复核ledger格式。",
        error_types=["ledger_missing_field"],
        met=True,
        evidence=["Bob接过地图，锁进铁匣"],
        paths=["items.map.holder"],
    )
    cases.append(_case(
        case_id="phase9-hn-repair-deletes-handoff",
        title="repair删除地图交付结果",
        previous=outside,
        narrative="Bob接过地图，锁进铁匣。Alice摊开空手。",
        declared=delivered,
        requirement="本段结束前：map由bob持有",
        error_types=["repair_fact_change", "item_holder_conflict"],
        message="repair删除交付并把holder改回Alice。",
        repair_text="Alice把地图收回自己的内袋，Bob没有拿到它。",
        repair_state=delete_handoff,
        first_verdict=first_handoff,
    ))
    injured = _typed_state(
        condition="damaged",
        alice_injuries=[{
            "injury_id": "injury_arm",
            "body_part": "arm",
            "severity": "moderate",
            "status": "active",
            "source_event_id": "evt_map_gate",
        }],
    )
    invented = _typed_state(condition="intact")
    invented["newly_known_fact_ids"] = {"alice": ["fact_clara_sister"]}
    first_injury = _verdict(
        "本段结束前：Alice伤势仍active且map仍damaged",
        message="初稿事实完整，仅要求局部格式复核。",
        error_types=["ledger_missing_field"],
        met=True,
        evidence=["手臂伤口仍在流血", "破损地图"],
        paths=["characters.alice.injuries", "items.map.condition"],
    )
    cases.append(_case(
        case_id="phase9-hn-repair-invents-sister",
        title="repair删除伤势并新增无来源亲属",
        previous=injured,
        narrative="Alice手臂伤口仍在流血，她把破损地图压在胸前。",
        declared=injured,
        requirement="本段结束前：Alice伤势仍active且map仍damaged",
        error_types=[
            "repair_fact_change", "item_condition_conflict", "knowledge_leak",
            "new_ungrounded_fact"
        ],
        message="repair令伤势消失、地图复原并新增从未建立的妹妹Clara。",
        repair_text="Alice毫发无伤地展开完好地图，想起妹妹Clara留下的密道遗言。",
        repair_state=invented,
        first_verdict=first_injury,
    ))
    return {
        "guard_replay_suite_version": "1",
        "suite_id": "phase9-hard-negative-v1",
        "base_fixture": "mock_full_runtime_v1.json",
        "response_provenance": "synthetic",
        "cases": cases,
    }


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp.json", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Phase 9 complete synthetic Guard replay fixtures."
    )
    parser.add_argument("--hard-negative-out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = Path(args.hard_negative_out).resolve()
    suite = build_hard_negative_suite()
    _atomic_write(output, suite)
    print(json.dumps({
        "out": str(output),
        "cases": len(suite["cases"]),
        "expected_rejects": sum(
            case["expected_final_decision"] == "reject"
            for case in suite["cases"]
        ),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
