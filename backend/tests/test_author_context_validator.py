from __future__ import annotations

import pytest

from story.context_builder import ContextBudgetExceeded, ContextBuilder, SLOT_ORDER
from story.models import (
    CanonicalState,
    MemoryRecord,
    SectionGoal,
    StateDeltaOperation,
    StoryBible,
    StoryThread,
    StoryThreadRepository,
    ValidationReport,
    WriterCandidate,
)
from story.validator import StoryValidator
from story.writer import AuthorWriter


def _bible() -> StoryBible:
    return StoryBible(
        premise="一名失忆守门人必须决定是否打开潮门。",
        theme="身份与牺牲",
        central_question="守住真实身份是否值得牺牲同伴？",
        setting_summary="雾历旧港，潮门每十年开启一次。",
        immutable_world_rules=["死亡不可逆", "潮门只能由铜钥匙开启"],
        forbidden_deviations=["禁止把故事改成无关的升级任务"],
        main_conflicts=["阿澜必须在身份与同伴之间选择"],
        style_contract={"voice": "克制、具体"},
    )


def _state() -> CanonicalState:
    return CanonicalState(
        revision=3,
        world={
            "locations": [
                {"id": "harbor", "name": "旧港"},
                {"id": "tower", "name": "潮塔"},
            ]
        },
        characters={
            "a": {
                "id": "a",
                "name": "阿澜",
                "alive": True,
                "location": "harbor",
            },
            "b": {
                "id": "b",
                "name": "白芷",
                "alive": True,
                "location": "harbor",
            },
            "dead": {
                "id": "dead",
                "name": "旧王",
                "alive": False,
                "location": "crypt",
            },
            "c": {
                "id": "c",
                "name": "潮官",
                "alive": True,
                "location": "tower",
            },
        },
        items={"铜钥匙": {"id": "铜钥匙", "quantity": 1, "owners": ["a"]}},
        relationships={"a": {"b": {"trust": 2}}},
        character_knowledge={
            "a": ["潮门会吞噬开启者"],
            "b": ["阿澜的真实身份是旧王之子"],
            "c": ["潮塔下藏着第二把钥匙"],
        },
        reader_knowledge={"known_facts": [{"fact": "潮门会吞噬开启者"}]},
        plot_position={"act": 2},
    )


def _goal() -> SectionGoal:
    return SectionGoal(
        section_id="ch1_s2",
        objective="阿澜为保护白芷，第一次公开承担身份带来的代价。",
        viewpoint_character_id="a",
        location_id="harbor",
        involved_characters=["a", "b"],
        target_threads=["gate"],
    )


def _candidate(**updates) -> WriterCandidate:
    base = {
        "narrative_text": "阿澜在旧港握住铜钥匙，承认自己的身份，并决定为白芷承担牺牲的代价。",
        "section_summary": "阿澜以牺牲回应身份冲突。",
    }
    base.update(updates)
    return WriterCandidate(**base)


def test_context_builder_keeps_fixed_authority_slots_under_pressure() -> None:
    threads = [
        StoryThread(id="gate", description="潮门之后是什么", urgency=9),
        StoryThread(id="side", description="无关的旧账", urgency=2),
    ]
    memories = [
        MemoryRecord(
            id=f"m{i}",
            summary=("阿澜在旧港留下选择证据" if i == 0 else "无关历史") + "字" * 600,
            entities=["a"] if i == 0 else ["other"],
            importance=9 if i == 0 else 2,
        )
        for i in range(20)
    ]
    package = ContextBuilder(
        {
            "recent_section_summaries": 300,
            "relevant_long_term_memories": 400,
        }
    ).build(
        novel_id="novel",
        section_id="ch1_s2",
        story_bible=_bible(),
        canonical_state=_state(),
        section_goal=_goal(),
        story_threads=threads,
        previous_prose_tail="上一节结尾" * 800,
        recent_summaries=[{"id": i, "summary": "旧摘要" * 300} for i in range(30)],
        long_term_memories=memories,
    )

    assert list(package.slots) == list(SLOT_ORDER)
    assert "身份与牺牲" in package.slots["story_bible"]
    assert "死亡不可逆" in package.slots["story_bible"]
    assert "禁止把故事改成无关的升级任务" in package.slots["story_bible"]
    assert '"revision": 3' in package.slots["canonical_state"]
    assert "gate" in package.slots["active_story_threads"]
    assert "潮门会吞噬开启者" in package.slots["character_knowledge"]
    assert "真实身份是旧王之子" in package.slots["character_knowledge"]
    assert "第二把钥匙" not in package.slots["character_knowledge"]
    assert package.slots["previous_prose_tail"].endswith("上一节结尾")
    assert package.manifest.total_chars == len(package.prompt)
    assert [slot.name for slot in package.manifest.slots] == list(SLOT_ORDER)
    assert all("身份与牺牲" not in slot.model_dump_json() for slot in package.manifest.slots)
    assert any(slot.truncated for slot in package.manifest.slots)


def test_validator_accepts_narrated_item_transfer() -> None:
    candidate = _candidate(
        narrative_text=(
            "阿澜在旧港承认自己的身份。为了白芷，他把铜钥匙交给白芷，"
            "也接受自己将承担牺牲代价。"
        ),
        state_delta=[
            StateDeltaOperation(
                op="transfer",
                path="/items/铜钥匙/owners",
                value={"from": "a", "to": "b"},
                evidence="他把铜钥匙交给白芷",
            )
        ],
    )
    report = StoryValidator().validate(
        bible=_bible(),
        state=_state(),
        threads=StoryThreadRepository(),
        goal=_goal(),
        candidate=candidate,
    )

    assert report.accepted is True
    assert report.violations == []
    updated = StoryValidator().apply_delta(_state(), report.validated_delta)
    assert updated.items["铜钥匙"]["owners"] == ["b"]
    assert updated.revision == 4


def test_validator_blocks_story_bible_delta_and_dead_character_revival() -> None:
    candidate = _candidate(
        narrative_text="旧王复活，阿澜的身份与牺牲都失去意义。",
        state_delta=[
            StateDeltaOperation(
                op="set",
                path="/story_bible/theme",
                value="力量升级",
                evidence="失去意义",
            ),
            StateDeltaOperation(
                op="set",
                path="/characters/dead/alive",
                value=True,
                evidence="旧王复活",
            ),
        ],
    )
    report = StoryValidator().validate(
        bible=_bible(),
        state=_state(),
        threads=StoryThreadRepository(),
        goal=_goal(),
        candidate=candidate,
    )
    codes = {item.code for item in report.violations}
    assert report.accepted is False
    assert {"STORY_BIBLE_IMMUTABLE", "DEAD_CHARACTER_REVIVAL", "IMMUTABLE_RULE_REVIVAL"} <= codes


def test_validator_blocks_location_jump_and_wrong_item_owner() -> None:
    candidate = _candidate(
        narrative_text="阿澜在身份与牺牲之间犹豫，铜钥匙交给白芷。",
        state_delta=[
            StateDeltaOperation(
                op="set",
                path="/characters/a/location",
                value="tower",
                evidence="阿澜在身份与牺牲之间犹豫",
            ),
            StateDeltaOperation(
                op="transfer",
                path="/items/铜钥匙/owners",
                value={"from": "b", "to": "a"},
                evidence="铜钥匙交给白芷",
            ),
        ],
    )
    report = StoryValidator().validate(
        bible=_bible(),
        state=_state(),
        threads=StoryThreadRepository(),
        goal=_goal(),
        candidate=candidate,
    )
    codes = {item.code for item in report.violations}
    assert report.accepted is False
    assert "LOCATION_JUMP" in codes
    assert "ITEM_OWNER_CONFLICT" in codes


def test_story_thread_cannot_resolve_without_narrative_evidence() -> None:
    current = StoryThreadRepository(
        threads={"gate": StoryThread(id="gate", description="潮门之后是什么")}
    )
    resolved = StoryThread(
        id="gate",
        description="潮门之后是什么",
        status="resolved",
        resolution_evidence=["门后是镜海"],
    )
    report = StoryValidator().validate(
        bible=_bible(),
        state=_state(),
        threads=current,
        goal=_goal(),
        candidate=_candidate(threads_resolved=[resolved]),
    )
    assert report.accepted is False
    assert "THREAD_RESOLUTION_NO_EVIDENCE" in {item.code for item in report.violations}


def test_resolved_thread_cannot_be_reopened_and_theme_drift_is_diagnosed() -> None:
    current = StoryThreadRepository(
        threads={
            "gate": StoryThread(
                id="gate",
                description="潮门之后是什么",
                status="resolved",
                resolution_evidence=["镜海"],
            )
        }
    )
    candidate = _candidate(
        narrative_text="主角获得经验值，接取打怪任务，然后升级技能。" * 12,
        section_summary="继续升级打怪。",
        threads_opened=[StoryThread(id="gate", description="潮门之后是什么")],
    )
    report = StoryValidator().validate(
        bible=_bible(),
        state=_state(),
        threads=current,
        goal=_goal(),
        candidate=candidate,
    )
    codes = {item.code for item in report.violations}
    assert "RESOLVED_THREAD_REOPENED" in codes
    assert "THEME_WEAK_SIGNAL" in codes


def test_reader_known_fact_is_not_allowed_as_first_reveal() -> None:
    candidate = _candidate(
        narrative_text=(
            "阿澜终于揭晓：潮门会吞噬开启者。这个身份秘密让他决定承担牺牲。"
        )
        * 6,
    )
    report = StoryValidator().validate(
        bible=_bible(),
        state=_state(),
        threads=StoryThreadRepository(),
        goal=_goal(),
        candidate=candidate,
    )
    assert "READER_KNOWLEDGE_REVEALED_AGAIN" in {
        item.code for item in report.violations
    }


def test_author_writer_uses_shared_repair_for_common_dirty_json() -> None:
    candidate = AuthorWriter._parse(
        '{"narrative_text":"阿澜说"走吧"。","section_summary":"阿澜决定前进",'
        '"state_delta":[],"threads_opened":[],"threads_advanced":[],'
        '"threads_resolved":[],"memory_records":[],"consistency_notes":[]}'
    )

    assert candidate.section_summary == "阿澜决定前进"
    assert "走吧" in candidate.narrative_text


def test_author_repair_is_a_bounded_patch_and_ignores_invalid_extra_fields() -> None:
    original = _candidate(narrative_text="阿澜停在旧港。")
    repaired = AuthorWriter._parse_repair(
        '{"narrative_text":"阿澜离开旧港，抵达潮塔。",'
        '"threads_advanced":[{"type":"mystery","description":"缺少 id"}],'
        '"memory_records":[{"type":"fact","description":"越权改写"}]}',
        original,
        ValidationReport(accepted=True),
    )

    assert repaired.narrative_text == "阿澜离开旧港，抵达潮塔。"
    assert repaired.section_summary == original.section_summary
    assert repaired.threads_advanced == []
    assert repaired.memory_records == original.memory_records


def test_writer_contract_normalises_safe_singleton_lists() -> None:
    candidate = AuthorWriter._parse(
        '{"narrative_text":"潮门打开。","section_summary":"潮门被打开",'
        '"state_delta":[],"threads_opened":[],"threads_advanced":[],'
        '"threads_resolved":{"id":"gate","type":"mystery",'
        '"description":"潮门之谜","status":"resolved",'
        '"resolution_evidence":"潮门打开"},"memory_records":[],'
        '"consistency_notes":"保持潮门规则"}'
    )

    assert candidate.threads_resolved[0].resolution_evidence == ["潮门打开"]
    assert candidate.consistency_notes == ["保持潮门规则"]


def test_writer_contract_preserves_thread_and_memory_evidence_aliases() -> None:
    candidate = AuthorWriter._parse(
        '{"narrative_text":"潮门打开。","section_summary":"潮门被打开",'
        '"state_delta":[],"threads_opened":[],"threads_advanced":'
        '[{"id":"gate","type":"mystery","description":"潮门之谜",'
        '"evidence":"潮门打开"}],"threads_resolved":[],"memory_records":'
        '[{"id":"memory_gate","type":"revelation","description":"潮门已打开",'
        '"evidence":"潮门打开"}],"consistency_notes":[]}'
    )

    assert candidate.threads_advanced[0].evidence == ["潮门打开"]
    assert candidate.memory_records[0].summary == "潮门已打开"
    assert candidate.memory_records[0].evidence == "潮门打开"


def test_medium_delta_violation_is_removed_from_validated_delta() -> None:
    candidate = _candidate(
        state_delta=[
            StateDeltaOperation(
                op="set", path="/world/weather", value="暴雨", evidence=""
            )
        ]
    )
    report = StoryValidator().validate(
        bible=_bible(), state=_state(), threads=StoryThreadRepository(), goal=_goal(), candidate=candidate
    )
    assert "DELTA_EVIDENCE_MISSING" in {item.code for item in report.violations}
    assert report.validated_delta == []


def test_multiple_deltas_only_validate_individually_valid_operations() -> None:
    candidate = _candidate(
        narrative_text="旧港骤然落下暴雨，阿澜仍为身份与牺牲作出选择。",
        state_delta=[
            StateDeltaOperation(
                op="set", path="/world/weather", value="暴雨", evidence="旧港骤然落下暴雨"
            ),
            StateDeltaOperation(
                op="set", path="/world/current_season", value="冬", evidence=""
            ),
        ],
    )
    report = StoryValidator().validate(
        bible=_bible(), state=_state(), threads=StoryThreadRepository(), goal=_goal(), candidate=candidate
    )
    assert [item.path for item in report.validated_delta] == ["/world/weather"]


def test_set_delta_cannot_change_existing_field_type() -> None:
    candidate = _candidate(
        state_delta=[
            StateDeltaOperation(
                op="set",
                path="/characters/a/alive",
                value="yes",
                evidence="阿澜在旧港握住铜钥匙",
            )
        ]
    )
    report = StoryValidator().validate(
        bible=_bible(),
        state=_state(),
        threads=StoryThreadRepository(),
        goal=_goal(),
        candidate=candidate,
    )
    assert report.validated_delta == []
    assert any(item.code == "DELTA_TYPE_INCOMPATIBLE" for item in report.violations)


def test_thread_open_advance_resolve_paths_preserve_authoritative_fields() -> None:
    existing = StoryThread(
        id="gate",
        type="mystery",
        description="潮门之后是什么",
        origin_refs=["section-1"],
        opened_at_revision=2,
        resolution_requirements=["门后是镜海"],
        urgency=8,
    )
    repository = StoryThreadRepository(threads={"gate": existing})
    advanced = StoryThread(
        id="gate",
        description="潮门之后是什么",
        evidence=["阿澜在门缝里看见镜海"],
        urgency=9,
    )
    advance_report = StoryValidator().validate(
        bible=_bible(),
        state=_state(),
        threads=repository,
        goal=_goal(),
        candidate=_candidate(
            narrative_text="阿澜在门缝里看见镜海，也明白身份与牺牲的代价。",
            threads_advanced=[advanced],
        ),
    )
    assert advance_report.accepted is True
    advanced_repo = StoryValidator().apply_thread_changes(
        repository, advance_report.thread_changes, target_revision=4
    )
    stored = advanced_repo.threads["gate"]
    assert stored.description == existing.description
    assert stored.origin_refs == ["section-1"]
    assert stored.opened_at_revision == 2
    assert stored.status == "advancing"
    assert stored.urgency == 9

    resolved = StoryThread(
        id="gate",
        description="潮门之后是什么",
        resolution_evidence=["门后是镜海"],
    )
    resolve_report = StoryValidator().validate(
        bible=_bible(),
        state=_state(),
        threads=advanced_repo,
        goal=_goal(),
        candidate=_candidate(
            narrative_text="门后是镜海。阿澜终于以牺牲守住身份。",
            threads_resolved=[resolved],
        ),
    )
    assert resolve_report.accepted is True
    resolved_repo = StoryValidator().apply_thread_changes(
        advanced_repo, resolve_report.thread_changes, target_revision=5
    )
    assert resolved_repo.threads["gate"].status == "resolved"
    assert resolved_repo.threads["gate"].origin_refs == ["section-1"]


def test_thread_validation_rejects_unknown_no_evidence_duplicate_and_override() -> None:
    existing = StoryThread(
        id="gate",
        description="潮门之后是什么",
        origin_refs=["section-1"],
        opened_at_revision=2,
    )
    repository = StoryThreadRepository(threads={"gate": existing})
    candidate = _candidate(
        threads_opened=[StoryThread(id="gate", description="潮门之后是什么")],
        threads_advanced=[
            StoryThread(id="missing", description="不存在", evidence=["不存在"]),
            StoryThread(id="gate", description="被覆盖的描述", evidence=[]),
        ],
    )
    report = StoryValidator().validate(
        bible=_bible(), state=_state(), threads=repository, goal=_goal(), candidate=candidate
    )
    codes = {item.code for item in report.violations}
    assert {
        "THREAD_DUPLICATE_OPEN",
        "THREAD_ADVANCE_UNKNOWN",
        "THREAD_ADVANCE_NO_EVIDENCE",
        "THREAD_FIELD_OVERRIDE_FORBIDDEN",
    } <= codes
    assert report.thread_changes == []


def test_context_builder_respects_global_budget() -> None:
    package = ContextBuilder(
        max_context_chars=6000,
        max_context_token_estimate=3000,
    ).build(
        novel_id="novel",
        section_id="budget",
        story_bible=_bible(),
        canonical_state=_state(),
        section_goal=_goal(),
        story_threads=[],
        previous_prose_tail="前文" * 3000,
        recent_summaries=["摘要" * 1000 for _ in range(10)],
        long_term_memories=[
            MemoryRecord(id="budget-memory", summary="记忆" * 2000)
        ],
    )
    assert package.manifest.total_chars <= 6000
    assert package.manifest.total_token_estimate <= 3000
    assert package.manifest.max_context_chars == 6000
    assert package.manifest.max_context_token_estimate == 3000
    assert 0 < package.manifest.budget_utilization <= 1
    assert package.slots["story_bible"]
    assert package.slots["canonical_state"]
    assert package.slots["section_goal"]


def test_oversized_story_bible_fails_explicitly() -> None:
    oversized = _bible().model_copy(
        update={"immutable_world_rules": ["不可截断" * 400]}
    )
    with pytest.raises(ContextBudgetExceeded) as error:
        ContextBuilder().build(
            novel_id="novel",
            section_id="oversized",
            story_bible=oversized,
            canonical_state=_state(),
            section_goal=_goal(),
            story_threads=[],
            previous_prose_tail="",
            recent_summaries=[],
            long_term_memories=[],
        )
    assert "拒绝静默截断" in error.value.reason
    assert error.value.manifest.rejected_reason == error.value.reason


def test_immutable_rules_are_never_silently_dropped() -> None:
    rules = [f"规则-{index}-必须完整保留" for index in range(20)]
    bible = _bible().model_copy(update={"immutable_world_rules": rules})
    package = ContextBuilder().build(
        novel_id="novel",
        section_id="rules",
        story_bible=bible,
        canonical_state=_state(),
        section_goal=_goal(),
        story_threads=[],
        previous_prose_tail="",
        recent_summaries=[],
        long_term_memories=[],
    )
    assert all(rule in package.slots["story_bible"] for rule in rules)


def test_manifest_reports_global_budget() -> None:
    package = ContextBuilder(
        max_context_chars=9000, max_context_token_estimate=4500
    ).build(
        novel_id="novel",
        section_id="manifest-budget",
        story_bible=_bible(),
        canonical_state=_state(),
        section_goal=_goal(),
        story_threads=[],
        previous_prose_tail="",
        recent_summaries=[],
        long_term_memories=[],
    )
    manifest = package.manifest
    assert manifest.max_context_chars == 9000
    assert manifest.max_context_token_estimate == 4500
    assert manifest.rejected_reason == ""
    assert manifest.budget_utilization == round(manifest.total_chars / 9000, 4)


@pytest.mark.parametrize(
    "bible",
    [
        _bible().model_copy(update={"source_seed": "种" * 12001}),
        _bible().model_copy(
            update={"main_conflicts": [f"冲突-{index}" for index in range(101)]}
        ),
    ],
)
def test_story_bible_free_text_and_list_limits_are_explicit(bible) -> None:
    with pytest.raises(ContextBudgetExceeded) as error:
        ContextBuilder().build(
            novel_id="novel",
            section_id="limits",
            story_bible=bible,
            canonical_state=_state(),
            section_goal=_goal(),
            story_threads=[],
            previous_prose_tail="",
            recent_summaries=[],
            long_term_memories=[],
        )

    assert error.value.manifest.rejected_reason
    assert error.value.manifest.total_chars > 0
