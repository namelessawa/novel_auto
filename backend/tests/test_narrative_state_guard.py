from __future__ import annotations

import pytest

from agents.narrative_state_guard import NarrativeStateGuard


@pytest.mark.asyncio
async def test_state_guard_keeps_safe_ordered_transition(mock_llm) -> None:
    text = "林雪从内袋取出地图，递到苏默手里。苏默折好后收进外套。"
    mock_llm.set_responses([{
        "safe": True,
        "prior_state_conflicts": [],
        "internal_conflicts": [],
        "ledger_conflicts": [],
        "fact_changes_from_original": [],
        "reason": "正文明写了交接",
    }])
    out = await NarrativeStateGuard().guard(
        narrative_text=text,
        previous_state={"items": {"地图": {"holder": "林雪"}}},
        declared_state={"items": {"地图": {"holder": "苏默"}}},
        protected_terms=["林雪", "苏默"],
        tick=2,
    )
    assert out.safe is True
    assert out.adopted is False
    assert out.narrative_text == text


@pytest.mark.asyncio
async def test_state_guard_repairs_injury_owner_and_reverifies(mock_llm) -> None:
    original = (
        "苏默左肩的绷带已经被血浸透。"
        "两人爬出通风井后，林雪回头说：‘你左肩还在漏。’"
        "她让苏默靠墙坐下，自己检查前方出口。"
    )
    repaired = original.replace("林雪回头说", "林雪回头看见苏默按住伤口，说")
    final_state = {
        "characters": {
            "林雪": {"injuries": []},
            "苏默": {"injuries": ["左肩持续出血"]},
        }
    }
    mock_llm.set_responses([
        {
            "safe": False,
            "prior_state_conflicts": [],
            "internal_conflicts": [
                "前句‘苏默左肩’，后句对林雪说‘你左肩’"
            ],
            "ledger_conflicts": [],
            "fact_changes_from_original": [],
            "reason": "伤势称谓错位",
        },
        {
            "narrative_text": repaired,
            "continuity_state": final_state,
            "repairs": ["明确受伤者仍为苏默"],
        },
        {
            "safe": True,
            "prior_state_conflicts": [],
            "internal_conflicts": [],
            "ledger_conflicts": [],
            "fact_changes_from_original": [],
            "reason": "后句已指向苏默的伤口",
        },
    ])
    out = await NarrativeStateGuard().guard(
        narrative_text=original,
        previous_state=final_state,
        declared_state=final_state,
        protected_terms=["林雪", "苏默"],
        tick=3,
    )
    assert out.safe is True
    assert out.adopted is True
    assert out.narrative_text == repaired
    assert out.trace["after"]["safe"] is True


@pytest.mark.asyncio
async def test_state_guard_repairs_unfulfilled_consumed_event(mock_llm) -> None:
    original = "林雪撞开控制室的门，守门人刚刚转过身。"
    repaired = (
        original
        + "她用扳手压住对方的手腕，夺回地图，赶在闸门落下前钻进通风井。"
    )
    old_state = {
        "characters": {"林雪": {"location": "闸门内"}},
        "items": {"地图": {"holder": "守门人"}},
    }
    new_state = {
        "characters": {"林雪": {"location": "通风井"}},
        "items": {"地图": {"holder": "林雪"}},
    }
    mock_llm.set_responses([
        {
            "safe": False,
            "event_fulfillment_conflicts": [
                "源事件要求‘必须夺回地图’，正文停在‘守门人转身’"
            ],
            "prior_state_conflicts": [],
            "internal_conflicts": [],
            "ledger_conflicts": [],
            "fact_changes_from_original": [],
            "reason": "消费事件未完成",
        },
        {
            "narrative_text": repaired,
            "continuity_state": new_state,
            "repairs": ["补齐夺图与撤离结果"],
        },
        {
            "safe": True,
            "event_checks": [
                {
                    "event_id": "evt_map",
                    "requirement": "地图由林雪持有",
                    "met": True,
                    "prose_evidence": ["夺回地图"],
                    "ledger_evidence_paths": ["items.地图.holder"],
                },
                {
                    "event_id": "evt_map",
                    "requirement": "林雪已经撤离闸门",
                    "met": True,
                    "prose_evidence": ["钻进通风井"],
                    "ledger_evidence_paths": ["characters.林雪.location"],
                },
            ],
            "event_fulfillment_conflicts": [],
            "entity_grounding_conflicts": [],
            "prior_state_conflicts": [],
            "internal_conflicts": [],
            "ledger_conflicts": [],
            "fact_changes_from_original": [],
            "reason": "源事件结果已补齐",
        },
    ])
    out = await NarrativeStateGuard().guard(
        narrative_text=original,
        previous_state=old_state,
        declared_state=old_state,
        required_events=[{
            "id": "evt_map",
            "description": "地图被守门人扣住，主角必须立即夺回并撤离。",
            "required_end_states": ["地图由林雪持有", "林雪已经撤离闸门"],
        }],
        protected_terms=["林雪"],
        tick=1,
    )
    assert out.safe is True
    assert out.adopted is True
    assert "夺回地图" in out.narrative_text
    assert out.continuity_state["items"]["地图"]["holder"] == "林雪"
    assert out.trace["required_events"][0]["required_end_states"] == [
        "地图由林雪持有",
        "林雪已经撤离闸门",
    ]
    assert "源事件终态高于文风和悬念" in mock_llm.calls[1][0]
    assert "不能只在后面继续扩写同一个障碍" in mock_llm.calls[1][1]
    assert "已经进入”不是超额完成" in mock_llm.calls[1][1]
    assert "禁止原文不改" in mock_llm.calls[1][1]
    assert "不得把源事件已经指定的地图付款重复算作" in mock_llm.calls[1][1]


@pytest.mark.asyncio
async def test_state_guard_retries_once_when_first_repair_overshoots(mock_llm) -> None:
    original = "林雪扶着苏莫朝城墙走去，两人还在废车之间。"
    overshot = "林雪扶着苏莫穿过城门，两人已经进入城内。"
    corrected = "林雪扶着苏莫走到城门外，两人在墙根停下。"
    inside_state = {
        "characters": {
            "char_linxue": {"location": "城内"},
            "char_sumo": {"location": "城内"},
        }
    }
    outside_state = {
        "characters": {
            "char_linxue": {"location": "城门外"},
            "char_sumo": {"location": "城墙根"},
        }
    }
    event = {
        "id": "evt_wall",
        "description": "两人必须抵达城墙外。",
        "required_end_states": ["本段结束前：两人已到达城墙外"],
    }
    mock_llm.set_responses([
        {
            "safe": False,
            "event_checks": [],
            "event_fulfillment_conflicts": ["正文尚未到达城墙外"],
            "prior_state_conflicts": [],
            "internal_conflicts": [],
            "ledger_conflicts": [],
            "fact_changes_from_original": [],
        },
        {
            "narrative_text": overshot,
            "continuity_state": inside_state,
            "repairs": ["让两人抵达城门"],
        },
        {
            "safe": True,
            "event_checks": [{
                "event_id": "evt_wall",
                "requirement": "本段结束前：两人已到达城墙外",
                "met": True,
                "prose_evidence": ["两人已经进入城内"],
                "ledger_evidence_paths": [
                    "characters.char_linxue.location",
                    "characters.char_sumo.location",
                ],
            }],
            "event_fulfillment_conflicts": [],
            "prior_state_conflicts": [],
            "internal_conflicts": [],
            "ledger_conflicts": [],
            "fact_changes_from_original": [],
        },
        {
            "narrative_text": corrected,
            "continuity_state": outside_state,
            "repairs": ["把终点收回城门外，不越过门线"],
        },
        {
            "safe": True,
            "event_checks": [{
                "event_id": "evt_wall",
                "requirement": "本段结束前：两人已到达城墙外",
                "met": True,
                "prose_evidence": ["林雪扶着苏莫走到城门外"],
                "ledger_evidence_paths": [
                    "characters.char_linxue.location",
                    "characters.char_sumo.location",
                ],
            }],
            "event_fulfillment_conflicts": [],
            "prior_state_conflicts": [],
            "internal_conflicts": [],
            "ledger_conflicts": [],
            "fact_changes_from_original": [],
        },
    ])

    out = await NarrativeStateGuard().guard(
        narrative_text=original,
        previous_state={},
        declared_state={},
        required_events=[event],
        protected_terms=["林雪", "苏莫"],
        entity_names={"char_linxue": "林雪", "char_sumo": "苏莫"},
        tracking_character_id="char_linxue",
        tick=3,
    )

    assert out.safe is True
    assert out.narrative_text == corrected
    assert out.trace["after"]["safe"] is False
    assert out.trace["after_retry"]["safe"] is True
    assert out.trace["repair_retry_adopted"] is True


@pytest.mark.asyncio
async def test_state_guard_rejects_unquoted_required_end_state(mock_llm) -> None:
    mock_llm.set_responses([{
        "safe": True,
        "event_checks": [],
        "event_fulfillment_conflicts": [],
        "entity_grounding_conflicts": [],
        "prior_state_conflicts": [],
        "internal_conflicts": [],
        "ledger_conflicts": [],
        "fact_changes_from_original": [],
        "reason": "误称已经完成",
    }])
    guard = NarrativeStateGuard()

    verdict = await guard._verify(
        previous_state={},
        narrative_text="两人仍在废车之间赶路。",
        declared_state={"location": "锈蚀公路废车区"},
        original_text="两人仍在废车之间赶路。",
        required_events=[{
            "id": "evt_wall",
            "description": "必须抵达城墙",
            "required_end_states": ["两人已到达城墙外"],
        }],
        known_entities=["林雪", "苏莫"],
        entity_names={"char_linxue": "林雪", "char_sumo": "苏莫"},
        tick=3,
    )

    assert verdict["safe"] is False
    assert "缺少逐条核验" in verdict["event_fulfillment_conflicts"][0]


def test_event_evidence_rejects_nonexistent_ledger_path() -> None:
    failures = NarrativeStateGuard._event_evidence_failures(
        required_events=[{
            "id": "evt_wall",
            "required_end_states": ["两人已到达城墙外"],
        }],
        event_checks=[{
            "event_id": "evt_wall",
            "requirement": "两人已到达城墙外",
            "met": True,
            "prose_evidence": ["他们站在城墙下"],
            "ledger_evidence_paths": ["characters.char_linxue.nowhere"],
        }],
        narrative_text="他们站在城墙下。",
        declared_state={"characters": {"char_linxue": {"location": "城墙外"}}},
    )

    assert failures
    assert "缺少正文/账本实证" in failures[0]


def test_event_evidence_accepts_compound_checks_and_list_path() -> None:
    narrative = "井盖咔嗒一声锁死。林雪把地图塞回口袋。"
    state = {
        "items": {"地图": {"holder": "char_linxue"}},
        "knowledge": ["井盖已经锁死"],
    }
    failures = NarrativeStateGuard._event_evidence_failures(
        required_events=[{
            "id": "evt_roof",
            "required_end_states": ["本段结束前：井盖已闭合，地图仍由主角一方持有"],
        }],
        event_checks=[
            {
                "requirement": "本段结束前：井盖已闭合",
                "met": True,
                "prose_evidence": ["井盖“咔嗒”一声锁死"],
                "ledger_evidence_paths": ["knowledge.井盖已经锁死"],
            },
            {
                "requirement": "本段结束前：地图仍由主角一方持有",
                "met": True,
                "prose_evidence": ["林雪把地图塞回口袋"],
                "ledger_evidence_paths": ["items.地图.holder"],
            },
        ],
        narrative_text=narrative,
        declared_state=state,
    )

    assert failures == []


def test_self_negating_and_identical_location_findings_are_filtered() -> None:
    findings = NarrativeStateGuard._actionable_findings([
        {
            "type": "location_mismatch",
            "declared_location": "屋顶",
            "actual_location": "屋顶",
            "reason": "人物正往楼梯间走",
        },
        {
            "type": "item_condition_change",
            "note": "变化有正文依据，与上一段结束状态一致，无冲突",
        },
        {"type": "holder_mismatch", "reason": "地图无交接却换了持有者"},
    ])

    assert findings == [
        {"type": "holder_mismatch", "reason": "地图无交接却换了持有者"}
    ]


def test_ledger_path_accepts_unique_item_alias_only() -> None:
    state = {
        "items": {
            "地图": {"holder": "char_linxue"},
            "水壶": {"holder": "char_sumo"},
        }
    }

    assert NarrativeStateGuard._ledger_path_exists(
        state, "items.南方循环站路线图.holder"
    )
    assert not NarrativeStateGuard._ledger_path_exists(
        {"items": {"旧地图": {}, "新地图": {}}},
        "items.地图.holder",
    )


def test_deterministic_holder_guard_catches_item_from_wrong_pocket() -> None:
    conflicts = NarrativeStateGuard._deterministic_holder_conflicts(
        previous_state={"items": {"南方路线图": {"holder": "char_linxue"}}},
        narrative_text="苏莫从怀里掏出图纸，卷成筒递过去。",
        entity_names={"char_linxue": "林雪", "char_sumo": "苏莫"},
    )

    assert conflicts
    assert conflicts[0]["type"] == "det_unmotivated_holder_change"


def test_deterministic_holder_guard_allows_explicit_handoff() -> None:
    conflicts = NarrativeStateGuard._deterministic_holder_conflicts(
        previous_state={"items": {"南方路线图": {"holder": "char_linxue"}}},
        narrative_text="林雪把图纸交给苏莫。苏莫从怀里掏出图纸，卷成筒递过去。",
        entity_names={"char_linxue": "林雪", "char_sumo": "苏莫"},
    )

    assert conflicts == []


def test_evidence_matching_tolerates_one_word_variation() -> None:
    assert NarrativeStateGuard._evidence_appears(
        "然后我开门。但地图归城邦。",
        "守门人说：然后我开门，但图归城邦。",
    )


def test_evidence_matching_accepts_exact_short_quote() -> None:
    assert NarrativeStateGuard._evidence_appears(
        "成交。",
        "守门人收下地图。莫铁说：\"成交。\"",
    )


def test_required_location_guard_rejects_moving_toward_destination() -> None:
    conflicts = NarrativeStateGuard._deterministic_required_location_conflicts(
        required_events=[{
            "id": "evt_wall",
            "required_end_states": ["本段结束前：两人已到达城墙外"],
        }],
        declared_state={
            "characters": {
                "char_linxue": {"location": "锈蚀公路，向城墙移动"},
                "char_sumo": {"location": "锈蚀公路，向城墙移动"},
            }
        },
    )

    assert conflicts
    assert "0/2" in conflicts[0]


def test_required_location_guard_accepts_two_characters_outside_wall() -> None:
    conflicts = NarrativeStateGuard._deterministic_required_location_conflicts(
        required_events=[{
            "id": "evt_wall",
            "required_end_states": ["本段结束前：两人已到达城墙外"],
        }],
        declared_state={
            "characters": {
                "char_linxue": {"location": "铁壁城邦南门外"},
                "char_sumo": {"location": "城墙根排水沟"},
            }
        },
    )

    assert conflicts == []


def test_required_location_guard_accepts_outer_wall_alias() -> None:
    conflicts = NarrativeStateGuard._deterministic_required_location_conflicts(
        required_events=[{
            "id": "evt_wall",
            "required_end_states": ["本段结束前：两人已到达城墙外"],
        }],
        declared_state={
            "characters": {
                "char_linxue": {"location": "锈水港外墙外，旧国道边缘"},
                "char_sumo": {"location": "锈水港外墙外，废车旁"},
            }
        },
    )

    assert conflicts == []


def test_group_endpoint_evidence_rejects_only_one_character_inside() -> None:
    failures = NarrativeStateGuard._event_evidence_failures(
        required_events=[{
            "id": "evt_gate",
            "required_end_states": ["本段结束前：地图已交给守门人，两人已进入城内"],
        }],
        event_checks=[{
            "event_id": "evt_gate",
            "requirement": "本段结束前：地图已交给守门人，两人已进入城内",
            "met": True,
            "prose_evidence": [
                "林雪把地图递给守门人",
                "林雪侧身挤进城门内侧",
                "苏莫仍靠在五十米外的卡车边",
            ],
            "ledger_evidence_paths": [
                "items.地图.holder",
                "characters.char_linxue.location",
                "characters.char_sumo.location",
            ],
        }],
        narrative_text=(
            "林雪把地图递给守门人。林雪侧身挤进城门内侧。"
            "苏莫仍靠在五十米外的卡车边。"
        ),
        declared_state={
            "items": {"地图": {"holder": "守门人"}},
            "characters": {
                "char_linxue": {"location": "城内"},
                "char_sumo": {"location": "城内"},
            },
        },
        entity_names={"char_linxue": "林雪", "char_sumo": "苏莫"},
        tracking_character_id="char_linxue",
    )

    assert failures
    assert "两名参与者" in failures[0]


def test_group_endpoint_evidence_accepts_explicit_joint_crossing() -> None:
    failures = NarrativeStateGuard._event_evidence_failures(
        required_events=[{
            "id": "evt_gate",
            "required_end_states": ["本段结束前：两人已进入城内"],
        }],
        event_checks=[{
            "event_id": "evt_gate",
            "requirement": "本段结束前：两人已进入城内",
            "met": True,
            "prose_evidence": ["我扶着苏莫穿过城门，两人进入城内"],
            "ledger_evidence_paths": [
                "characters.char_linxue.location",
                "characters.char_sumo.location",
            ],
        }],
        narrative_text="我扶着苏莫穿过城门，两人进入城内。",
        declared_state={
            "characters": {
                "char_linxue": {"location": "城内"},
                "char_sumo": {"location": "城内"},
            }
        },
        entity_names={"char_linxue": "林雪", "char_sumo": "苏莫"},
        tracking_character_id="char_linxue",
    )

    assert failures == []


def test_group_endpoint_evidence_accepts_two_pronoun_crossing_actions() -> None:
    narrative = (
        "她先把莫铁推出去，他滚到门外碎石地上。"
        "然后她自己侧身挤过去，闸门在身后落锁。"
    )
    failures = NarrativeStateGuard._event_evidence_failures(
        required_events=[{
            "id": "evt_exit",
            "required_end_states": ["本段结束前：主角与伤员已越过出口"],
        }],
        event_checks=[{
            "event_id": "evt_exit",
            "requirement": "本段结束前：主角与伤员已越过出口",
            "met": True,
            "prose_evidence": [
                "她先把莫铁推出去，他滚到门外碎石地上",
                "然后她自己侧身挤过去",
            ],
            "ledger_evidence_paths": [
                "characters.char_linxue.location",
                "characters.char_motie.location",
            ],
        }],
        narrative_text=narrative,
        declared_state={
            "characters": {
                "char_linxue": {"location": "出口外"},
                "char_motie": {"location": "出口外"},
            }
        },
        entity_names={"char_linxue": "林雪", "char_motie": "莫铁"},
        tracking_character_id="char_linxue",
    )

    assert failures == []


def test_rain_damage_requirement_rejects_unrelated_dirty_water() -> None:
    failures = NarrativeStateGuard._event_evidence_failures(
        required_events=[{
            "id": "evt_rain",
            "required_end_states": ["本段结束前：地图因雨水受损"],
        }],
        event_checks=[{
            "event_id": "evt_rain",
            "requirement": "本段结束前：地图因雨水受损",
            "met": True,
            "prose_evidence": ["井底污水浸湿地图，路线糊成一团"],
            "ledger_evidence_paths": ["items.地图.status"],
        }],
        narrative_text="井底污水浸湿地图，路线糊成一团。",
        declared_state={"items": {"地图": {"status": "受损"}}},
    )

    assert failures
    assert "雨水作用" in failures[0]


def test_rain_damage_requirement_accepts_direct_causal_evidence() -> None:
    failures = NarrativeStateGuard._event_evidence_failures(
        required_events=[{
            "id": "evt_rain",
            "required_end_states": ["本段结束前：地图因雨水受损"],
        }],
        event_checks=[{
            "event_id": "evt_rain",
            "requirement": "本段结束前：地图因雨水受损",
            "met": True,
            "prose_evidence": ["酸雨落在地图上，纸面被蚀出三个破洞"],
            "ledger_evidence_paths": ["items.地图.status"],
        }],
        narrative_text="酸雨落在地图上，纸面被蚀出三个破洞。",
        declared_state={"items": {"地图": {"status": "酸雨蚀损"}}},
    )

    assert failures == []


def test_rain_damage_requirement_accepts_adjacent_causal_sentences() -> None:
    narrative = "雨在这时候下起来了。莫铁掏出地图，防水纸上的墨迹正在洇开。"
    failures = NarrativeStateGuard._event_evidence_failures(
        required_events=[{
            "id": "evt_rain",
            "required_end_states": ["本段结束前：地图因雨水受损"],
        }],
        event_checks=[{
            "event_id": "evt_rain",
            "requirement": "本段结束前：地图因雨水受损",
            "met": True,
            "prose_evidence": ["莫铁掏出地图，防水纸上的墨迹正在洇开"],
            "ledger_evidence_paths": ["items.地图.status"],
        }],
        narrative_text=narrative,
        declared_state={"items": {"地图": {"status": "墨迹洇开"}}},
    )

    assert failures == []


def test_required_location_guard_rejects_one_character_outside_city() -> None:
    conflicts = NarrativeStateGuard._deterministic_required_location_conflicts(
        required_events=[{
            "id": "evt_gate",
            "required_end_states": ["本段结束前：两人已进入城内"],
        }],
        declared_state={
            "characters": {
                "char_linxue": {"location": "城门内侧"},
                "char_sumo": {"location": "城门外卡车旁"},
            }
        },
    )

    assert conflicts
    assert "1/2" in conflicts[0]


def test_required_location_guard_accepts_named_city_interior_facilities() -> None:
    conflicts = NarrativeStateGuard._deterministic_required_location_conflicts(
        required_events=[{
            "id": "evt_gate",
            "required_end_states": ["本段结束前：两人已进入城内"],
        }],
        declared_state={
            "characters": {
                "char_linxue": {"location": "北望城城墙值班室内"},
                "char_sumo": {"location": "北望城检疫站内"},
            }
        },
    )

    assert conflicts == []


def test_new_cost_evidence_rejects_repeated_map_payment_only() -> None:
    failure = NarrativeStateGuard._semantic_evidence_failure(
        requirement="本段结束前：谈判产生一项正文明写的新代价",
        prose_evidence=["地图换入城", "地图被哨兵抽走"],
        narrative_text="守门人说地图换入城。地图被哨兵抽走。",
        entity_names={},
        tracking_character_id="",
    )

    assert "既定地图付款" in failure

    disguised = NarrativeStateGuard._semantic_evidence_failure(
        requirement="本段结束前：谈判产生一项正文明写的新代价",
        prose_evidence=["还有，交出那张路线图"],
        narrative_text="守门人说：还有，交出那张路线图。",
        entity_names={},
        tracking_character_id="",
    )
    assert "既定地图付款" in disguised


def test_new_cost_evidence_accepts_distinct_backpack_constraint() -> None:
    failure = NarrativeStateGuard._semantic_evidence_failure(
        requirement="本段结束前：谈判产生一项正文明写的新代价",
        prose_evidence=["地图先交", "背包留在墙根，检查完还你"],
        narrative_text="地图先交。背包留在墙根，检查完还你。",
        entity_names={},
        tracking_character_id="",
    )

    assert failure == ""


def test_named_entity_guard_rejects_unsourced_nickname_and_titled_name() -> None:
    conflicts = NarrativeStateGuard._deterministic_named_entity_conflicts(
        narrative_text=(
            "为首那个我认识，叫铁牙，专干扣货。老周开门后说赵队长不同意。"
        ),
        known_entities=["林雪", "苏默", "老王"],
        required_events=[{"description": "守门人提出交换条件"}],
    )

    assert {item["name"] for item in conflicts} == {"铁牙", "老周", "赵队长"}


def test_named_entity_guard_allows_names_from_profiles_or_source_event() -> None:
    conflicts = NarrativeStateGuard._deterministic_named_entity_conflicts(
        narrative_text="老王说赵队长会开门。",
        known_entities=["林雪", "老王"],
        required_events=[{"description": "赵队长负责守门"}],
    )

    assert conflicts == []
