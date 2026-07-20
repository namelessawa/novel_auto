from __future__ import annotations

from agents.narrative_state_guard import NarrativeStateGuard


def _failures(
    *, requirement: str, evidence: list[str], narrative: str, state: dict
) -> list[str]:
    return NarrativeStateGuard._event_evidence_failures(
        required_events=[{
            "id": "evt_regression",
            "required_end_states": [requirement],
        }],
        event_checks=[{
            "event_id": "evt_regression",
            "requirement": requirement,
            "met": True,
            "prose_evidence": evidence,
            "ledger_evidence_paths": [
                "items.地图.status"
                if "地图因雨水" in requirement
                else "characters.char_linxue.location"
                if "两人" in requirement
                else "knowledge.新代价"
            ],
        }],
        narrative_text=narrative,
        declared_state=state,
        entity_names={"char_linxue": "林雪", "char_sumo": "苏莫"},
        tracking_character_id="char_linxue",
    )


def test_rain_damage_accepts_rain_observed_immediately_after_damage() -> None:
    narrative = (
        "防水袋里的地图已经湿了三分之一，红圈洇成一团模糊的红色。"
        "林雪折好地图，塞回防水袋。雨越下越大。"
    )
    failures = _failures(
        requirement="本段结束前：地图因雨水受损",
        evidence=[
            "防水袋里的地图已经湿了三分之一，红圈洇成一团模糊的红色",
            "林雪折好地图，塞回防水袋",
        ],
        narrative=narrative,
        state={"items": {"地图": {"status": "雨水浸湿，红圈洇开"}}},
    )

    assert failures == []


def test_rain_damage_accepts_map_plate_alias_with_acid_rain_contact() -> None:
    narrative = (
        "苏莫掏出钛合金板。刻痕边缘开始泛白——酸雨渗进金属纹理，"
        "线条正在变模糊。苏莫把板子塞回背包。"
    )
    failures = _failures(
        requirement="本段结束前：地图因雨水受损",
        evidence=[
            "刻痕边缘开始泛白——酸雨渗进金属纹理，线条正在变模糊",
            "苏莫把板子塞回背包",
        ],
        narrative=narrative,
        state={"items": {"地图": {"status": "酸雨渗入刻痕，线条模糊"}}},
    )

    assert failures == []


def test_group_crossing_accepts_companion_then_tracking_character() -> None:
    narrative = (
        "林雪把苏莫推进门缝。林雪跟着钻过去。"
        "铁门砸进地面槽口，锁死。"
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
                "林雪把苏莫推进门缝",
                "林雪跟着钻过去",
                "铁门砸进地面槽口，锁死",
            ],
            "ledger_evidence_paths": [
                "characters.char_linxue.location",
                "characters.char_sumo.location",
            ],
        }],
        narrative_text=narrative,
        declared_state={
            "characters": {
                "char_linxue": {"location": "出口外"},
                "char_sumo": {"location": "出口外"},
            }
        },
        entity_names={"char_linxue": "林雪", "char_sumo": "苏莫"},
        tracking_character_id="char_linxue",
    )

    assert failures == []


def test_group_crossing_accepts_first_person_assisted_entry() -> None:
    narrative = "我架着苏莫往里走。城门在身后合拢。"
    failures = NarrativeStateGuard._event_evidence_failures(
        required_events=[{
            "id": "evt_gate",
            "required_end_states": ["本段结束前：两人已进入城内"],
        }],
        event_checks=[{
            "event_id": "evt_gate",
            "requirement": "本段结束前：两人已进入城内",
            "met": True,
            "prose_evidence": ["我架着苏莫往里走", "城门在身后合拢"],
            "ledger_evidence_paths": [
                "characters.char_linxue.location",
                "characters.char_sumo.location",
            ],
        }],
        narrative_text=narrative,
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


def test_group_crossing_accepts_pronoun_companion_then_named_follower() -> None:
    narrative = (
        "她从林雪手里接过包，先钻过铁门。"
        "林雪跟在她后面，肩膀擦过门底边缘的铁锈。"
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
            "prose_evidence": [narrative],
            "ledger_evidence_paths": [
                "characters.char_linxue.location",
                "characters.char_sumo.location",
            ],
        }],
        narrative_text=narrative,
        declared_state={
            "characters": {
                "char_linxue": {"location": "出口外"},
                "char_sumo": {"location": "出口外"},
            }
        },
        entity_names={"char_linxue": "林雪", "char_sumo": "苏墨"},
        tracking_character_id="char_linxue",
    )

    assert failures == []


def test_group_crossing_rejects_named_follower_stopping_outside() -> None:
    failure = NarrativeStateGuard._semantic_evidence_failure(
        requirement="本段结束前：主角与伤员已越过出口",
        prose_evidence=[
            "她先钻过铁门。林雪跟在她后面，却停在门外。",
        ],
        narrative_text="她先钻过铁门。林雪跟在她后面，却停在门外。",
        entity_names={"char_linxue": "林雪", "char_sumo": "苏墨"},
        tracking_character_id="char_linxue",
    )

    assert "两名参与者" in failure


def test_new_cost_accepts_explicit_debt_obligation() -> None:
    failures = _failures(
        requirement="本段结束前：谈判产生一项正文明写的新代价",
        evidence=["地图只够买进门", "抗生素另算，你欠我一次"],
        narrative="守门人说：地图只够买进门。抗生素另算，你欠我一次。",
        state={"knowledge": ["新代价"]},
    )

    assert failures == []


def test_new_cost_accepts_explicit_tactical_knife_handoff() -> None:
    failure = NarrativeStateGuard._semantic_evidence_failure(
        requirement="本段结束前：谈判产生一项正文明写的新代价",
        prose_evidence=[
            "你腰上那把刀",
            "林雪拔出战术刀，她把刀递过去，守门人接过刀",
        ],
        narrative_text=(
            "守门人说：你腰上那把刀。"
            "林雪拔出战术刀，她把刀递过去，守门人接过刀。"
        ),
        entity_names={},
        tracking_character_id="",
    )

    assert failure == ""


def test_rain_damage_accepts_same_scene_rain_beyond_two_sentences() -> None:
    narrative = (
        "雨砸在屋顶上。林雪重新背起苏墨。两人绕过倒塌的水塔。"
        "她从内袋掏出地图，纸已经湿透，炭笔线条洇开。"
    )
    failures = _failures(
        requirement="本段结束前：地图因雨水受损",
        evidence=["她从内袋掏出地图，纸已经湿透，炭笔线条洇开"],
        narrative=narrative,
        state={"items": {"地图": {"status": "雨水浸湿，线条洇开"}}},
    )

    assert failures == []


def test_rain_damage_rejects_explicit_fire_cause_even_when_raining() -> None:
    failures = _failures(
        requirement="本段结束前：地图因雨水受损",
        evidence=["雨砸在屋顶，火星落下烧破了地图"],
        narrative="雨砸在屋顶，火星落下烧破了地图。",
        state={"items": {"地图": {"status": "被火星烧破"}}},
    )

    assert failures
    assert "雨水作用" in failures[0]


def test_actionable_findings_drop_self_negating_item_owner_and_refinement() -> None:
    findings = NarrativeStateGuard._actionable_findings([
        {
            "type": "item_owner_mismatch",
            "item": "工程图纸",
            "declared_owner": "缺耳守门人",
            "actual_owner": "缺耳守门人",
            "note": "措辞有些模糊",
        },
        {
            "type": "item_location_mismatch",
            "item": "硬币",
            "declared_location": "旧供水神殿屋顶",
            "actual_location": "旧供水神殿屋顶锈水滩中",
        },
        {
            "type": "item_owner_mismatch",
            "item": "地图",
            "declared_owner": "林雪",
            "actual_owner": "守门人",
        },
    ])

    assert findings == [{
        "type": "item_owner_mismatch",
        "item": "地图",
        "declared_owner": "林雪",
        "actual_owner": "守门人",
    }]
