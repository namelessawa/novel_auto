from __future__ import annotations

import json
from pathlib import Path

from story.narrative_contract import (
    AllowedEntities,
    EntityReference,
    ForbiddenAddition,
    ForbiddenOutcome,
    LengthConstraint,
    NarrativeContractInput,
    ProtectedCausalLink,
    RequiredEndState,
    RequiredEvent,
    RequiredFact,
    TimeConstraint,
)


ROOT = Path(__file__).resolve().parents[2]
REAL_SAMPLE_REPORT = (
    ROOT / "docs" / "iter" / "style-generation-samples-glm52-20260722.json"
)


def real_style_samples() -> dict[str, str]:
    payload = json.loads(REAL_SAMPLE_REPORT.read_text(encoding="utf-8"))
    return {
        item["style_key"]: item["output"]["text"]
        for item in payload["results"]
    }


def lighthouse_constraints() -> NarrativeContractInput:
    return NarrativeContractInput(
        allowed_entities=AllowedEntities(
            characters=[
                EntityReference(id="shen_yan", name="沈砚", aliases=["他"]),
                EntityReference(id="lin_qiu", name="林秋", aliases=["她"]),
                EntityReference(
                    id="investigator",
                    name="调查员",
                    aliases=["门外的人"],
                    max_count=1,
                ),
            ],
            locations=[EntityReference(id="lighthouse", name="旧灯塔")],
            items=[
                EntityReference(id="letter", name="信", aliases=["旧信", "信封"]),
                EntityReference(id="lighthouse_light", name="灯", aliases=["灯塔灯"]),
            ],
            organizations=[EntityReference(id="harbor_office", name="港务处")],
            generic_terms=["玻璃", "纱布", "工具", "抽屉"],
        ),
        required_facts=[
            RequiredFact(
                id="fact_warning_received",
                subject="港务处",
                predicate="收到",
                object="风暴警告",
                time="十二年前港难发生前",
                statement="港务处在港难发生前收到过风暴警告",
                evidence_patterns=[
                    r"港务处.{0,80}(?:收到|收悉|发来|送到|风暴警告)",
                    r"风暴警告.{0,100}(?:送到|发来|收到|收悉|港务处)",
                ],
            ),
            RequiredFact(
                id="fact_warning_suppressed",
                subject="未定身份的人",
                predicate="压下",
                object="风暴警告",
                statement="有人压下风暴警告，责任人尚未定案",
                evidence_patterns=[
                    r"(?:有人|港务处|签字的人).{0,35}(?:压下|压了|暂缓通报).{0,20}(?:警告|风暴警告)",
                    r"(?:警告|风暴警告).{0,25}(?:被|遭).{0,10}(?:压下|压住)",
                    r"风暴警告.{0,100}(?:已收悉|暂缓通报)",
                ],
            ),
        ],
        required_events=[
            RequiredEvent(
                id="evt_repair_light",
                actor="shen_yan",
                action="修灯",
                target="lighthouse_light",
                evidence_patterns=[
                    r"沈砚.{0,100}(?:修灯|螺丝刀|树脂胶|灯罩|玻璃刀)",
                    r"沈砚.{0,100}(?:更换|裁换|嵌稳|卸下).{0,40}(?:灯|灯罩|玻璃)",
                ],
            ),
            RequiredEvent(
                id="evt_take_letter_and_minor_cut",
                actor="lin_qiu",
                action="从抽屉夹层取信并受轻伤",
                target="letter",
                evidence_patterns=[
                    r"林秋.{0,500}(?:抽屉|夹层).{0,260}(?:划|伤口|血)",
                    r"林秋.{0,500}(?:划|伤口|血).{0,260}(?:信|信封|抽屉|夹层)",
                    r"林秋[\s\S]{0,700}(?:抽屉|夹层)[\s\S]{0,350}(?:划|伤口|血)",
                ],
            ),
            RequiredEvent(
                id="evt_bandage",
                actor="shen_yan",
                action="清理并包扎",
                target="lin_qiu",
                evidence_patterns=[
                    r"沈砚.{0,260}(?:包扎|棉布|纱布|胶带|医用胶布).{0,120}(?:林秋|她|伤口|手)",
                    r"沈砚.{0,120}(?:林秋|她|伤口|手).{0,180}(?:包扎|棉布|纱布|胶带|医用胶布)",
                ],
            ),
            RequiredEvent(
                id="evt_disagreement",
                actor="shen_yan",
                action="与林秋发生明确分歧",
                target="lin_qiu",
                evidence_patterns=[
                    r"(?:交出去|交吧|交信|公开|护).{0,160}[“\"]?.{0,100}(?:家|真相|旧事|档案)",
                ],
            ),
            RequiredEvent(
                id="evt_shared_choice",
                actor="shen_yan",
                action="与林秋共同决定交信",
                target="lin_qiu",
                evidence_patterns=[
                    r"(?:那一起|我开门|你拿着|让旧事见光|交吧|拿好|开门).{0,160}(?:信|调查员|门|真相)",
                    r"(?:林秋|她).{0,120}(?:握住门闩|拉开铁栓|拉开|打开|推开).{0,40}(?:门|铁门|门轴)",
                ],
            ),
            RequiredEvent(
                id="evt_shen_holds_letter",
                actor="shen_yan",
                action="持信走向门口",
                target="letter",
                evidence_patterns=[
                    r"沈砚.{0,80}(?:拿起|拿着|攥|捏|持|怀中揣着).{0,20}(?:信|信封)",
                    r"(?:信|信封).{0,20}(?:在|由)沈砚.{0,20}(?:手|掌|怀)",
                    r"沈砚.{0,40}(?:将|把)?信(?:封)?.{0,20}(?:递出|递给|交给)",
                ],
            ),
            RequiredEvent(
                id="evt_lin_opens_door",
                actor="lin_qiu",
                action="亲手打开灯塔门",
                evidence_patterns=[
                    r"林秋.{0,140}(?:拉开|打开|推开).{0,20}(?:门|铁门)",
                    r"林秋.{0,120}(?:握住门闩|拉开铁栓).{0,100}(?:门轴|门往外|铁门|门向外)",
                    r"林秋.{0,350}(?:用力一推|门向外打开|门向外推开)",
                ],
            ),
            RequiredEvent(
                id="evt_letter_handover",
                actor="shen_yan",
                action="把信交给调查员",
                target="investigator",
                evidence_patterns=[
                    r"沈砚.{0,80}(?:递|交).{0,30}(?:信|信封).{0,30}(?:调查员|门外)",
                    r"(?:调查员|门外的人).{0,50}(?:接过|收下).{0,30}(?:信|信封)",
                    r"(?:信|信封).{0,30}(?:递|交).{0,20}(?:调查员|门外的人)",
                    r"(?:调查员|门外的人|门外).{0,500}沈砚.{0,40}(?:将|把)?信(?:封)?.{0,20}(?:递出|递了出去|递给|交给)",
                    r"(?:调查员|门外的人|门外)[\s\S]{0,600}沈砚.{0,40}(?:将|把)?信(?:封)?.{0,20}(?:递出|递了出去|递给|交给)",
                ],
                incomplete_patterns=[
                    r"(?:是否|要不要|若要|准备|决定).{0,20}(?:交信|交出去|递出去)"
                ],
            ),
            RequiredEvent(
                id="evt_light_on",
                actor="shen_yan",
                action="让修好的灯重新亮起",
                target="lighthouse_light",
                evidence_patterns=[
                    r"(?:灯|光柱|灯泡).{0,50}(?:重新亮|亮起来|亮起|射出|嗡然亮|亮着)"
                ],
            ),
        ],
        required_end_state=[
            RequiredEndState(
                id="end_letter_with_investigator",
                path="/items/letter/holder",
                expected="investigator",
                description="调查员已经实际接过旧信",
                evidence_patterns=[
                    r"(?:调查员|门外的人).{0,50}(?:接过|收下).{0,30}(?:信|信封)",
                    r"(?:信|信封).{0,30}(?:递|交).{0,20}(?:调查员|门外的人)",
                    r"(?:调查员|门外的人|门外).{0,500}沈砚.{0,40}(?:将|把)?信(?:封)?.{0,20}(?:递出|递了出去|递给|交给)",
                    r"(?:调查员|门外的人|门外)[\s\S]{0,600}沈砚.{0,40}(?:将|把)?信(?:封)?.{0,20}(?:递出|递了出去|递给|交给)",
                ],
                wrong_state_patterns=[
                    r"林秋(?:接过来|拿着|持着|握着).{0,25}(?:信|信封)",
                    r"(?:信|信封).{0,20}(?:在|由)林秋.{0,20}(?:手|掌|怀)",
                ],
            ),
            RequiredEndState(
                id="end_lin_opened_door",
                path="/characters/lin_qiu/action",
                expected="亲手打开灯塔门",
                evidence_patterns=[
                    r"林秋.{0,140}(?:拉开|打开|推开).{0,20}(?:门|铁门)",
                    r"林秋.{0,120}(?:握住门闩|拉开铁栓).{0,100}(?:门轴|门往外|铁门|门向外)",
                    r"林秋.{0,350}(?:用力一推|门向外打开|门向外推开)",
                ],
            ),
            RequiredEndState(
                id="end_lighthouse_light_on",
                path="/world/lighthouse/light",
                expected="on",
                evidence_patterns=[
                    r"(?:灯|光柱|灯泡).{0,50}(?:重新亮|亮起来|亮起|射出|嗡然亮|亮着)"
                ],
            ),
        ],
        time_constraints=[
            TimeConstraint(
                id="deadline_before_dawn",
                description="必须在天亮前交信，否则档案室拆除会让线索永久断掉",
                deadline="天亮前",
                required_patterns=[r"天亮前|离天亮不到|天快亮|黎明前|凌晨"],
                mutation_patterns=[r"下周拆|以后.{0,10}拆|将来.{0,10}拆"],
                weakened_patterns=[r"下周拆|以后可能拆|将来可能拆"],
            )
        ],
        forbidden_additions=[
            ForbiddenAddition(
                id="shen_new_injury",
                category="injury",
                code="UNSUPPORTED_INJURY_ADDED",
                description="沈砚不得新增伤势",
                patterns=[r"(?:沈砚|他).{0,100}(?:割破虎口|虎口滴血|血顺着手腕)"],
            )
        ],
        forbidden_outcomes=[
            ForbiddenOutcome(
                id="letter_destroyed_or_offered",
                description="不得烧信、藏信或拒绝交信",
                patterns=[r"(?:把|将)?信.{0,12}(?:烧了|烧掉|烧毁|藏起)|把信烧"],
                severity="high",
            )
        ],
        protected_causal_links=[
            ProtectedCausalLink(
                id="deadline_archive_evidence",
                cause="天亮前不交信",
                effect="档案室拆除导致线索永久断掉",
                weakened_patterns=[r"下周拆|以后可能拆"],
            )
        ],
        length_constraint=LengthConstraint(min_chars=900, max_chars=1200),
    )
