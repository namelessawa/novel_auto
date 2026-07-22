"""Deterministic validator for prose-level NarrativeContract compliance."""

from __future__ import annotations

import re
from typing import Iterable

from story.narrative_contract import (
    EndStateResult,
    NarrativeContract,
    NarrativeValidationReport,
    NarrativeViolation,
    narrative_char_count,
)


_KINSHIP = re.compile(
    r"父亲|母亲|祖父|祖母|爷爷|奶奶|外祖父|外祖母|二叔|叔父|叔叔|伯父|"
    r"兄长|哥哥|弟弟|姐姐|妹妹|儿子|女儿|丈夫|妻子|舅舅|姑姑|姨母"
)
_CASUALTY = re.compile(
    r"([零〇一二两三四五六七八九十百千万\d]+)(?:条|名|个)?"
    r"(?:人命|人(?:死亡|丧生|遇难)|死者|伤亡)"
)
_AGE = re.compile(r"([零〇一二两三四五六七八九十百\d]+)岁")
_DATED = re.compile(
    r"(?:\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?|"
    r"[零〇一二两三四五六七八九十]+月[零〇一二两三四五六七八九十]+日|"
    r"(?:前|后)[零〇一二两三四五六七八九十百\d]+(?:日|天|小时))"
)
_BACKSTORY_DURATION = re.compile(
    r"(?:护|照顾|相识|认识|陪|守)[^。！？]{0,8}"
    r"[零〇一二两三四五六七八九十百\d]+年"
)
_ORGANIZATION = re.compile(
    r"[\u3400-\u9fff]{2,14}(?:公司|集团|协会|商会|船行|委员会|学院|帮派|门派)"
)
_EXTRA_PERSON_COUNT = re.compile(
    r"(?:门外|门口|调查员.{0,8}(?:身边|身后))[^。！？]{0,12}"
    r"(?:站着|来了|出现)[^。！？]{0,8}(?:两|二|2)个(?:人|身影)"
)
_VIOLENCE_OR_INJURY = re.compile(
    r"一拳砸|拳头砸|甩开.{0,12}手|反手扣住|割破虎口|虎口滴血|"
    r"血顺着手腕|新增伤口|打伤|刺伤|枪伤|骨折|断肢"
)
_NAMED_PERSON_INTRO = re.compile(
    r"(?:名叫|叫作|自称)([\u3400-\u9fff]{2,4}?)(?=的?(?:人|水手|工人|医生|警官|调查员))"
)


def _rank(severity: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(severity, 0)


def _matches(text: str, patterns: Iterable[str]) -> re.Match[str] | None:
    for pattern in patterns:
        try:
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        except re.error:
            match = re.search(re.escape(pattern), text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def _evidence(match: re.Match[str] | None) -> str:
    return match.group(0)[:180] if match else ""


def _keywords(text: str) -> list[str]:
    chunks = re.split(r"[，。！？；：、,/|\s与和并且让使将把的了]+", text)
    return [item for item in chunks if 2 <= len(item) <= 18]


def _entity_names(contract: NarrativeContract, identifier: str) -> list[str]:
    for group in (
        contract.allowed_entities.characters,
        contract.allowed_entities.locations,
        contract.allowed_entities.items,
        contract.allowed_entities.organizations,
    ):
        for item in group:
            if identifier in item.all_names:
                return [name for name in item.all_names if name]
    return [identifier] if identifier else []


def _event_fallback_match(contract: NarrativeContract, event, text: str) -> tuple[bool, str]:
    keywords = event.keywords or _keywords(event.description or event.action)
    keyword_hits = [item for item in keywords if item in text]
    if len(keyword_hits) >= min(event.min_keyword_matches, max(1, len(keywords))):
        return True, "、".join(keyword_hits[:4])
    actors = _entity_names(contract, event.actor)
    targets = _entity_names(contract, event.target)
    action_terms = _keywords(event.action) or ([event.action] if event.action else [])
    for sentence in re.split(r"[。！？\n]+", text):
        actor_ok = not actors or any(item in sentence for item in actors)
        action_ok = any(item in sentence for item in action_terms)
        target_ok = not targets or any(item in sentence for item in targets)
        if actor_ok and action_ok and target_ok:
            return True, sentence[:180]
    return False, ""


def _end_state_fallback_match(contract: NarrativeContract, state, text: str) -> str:
    """Conservative semantic fallback for path-only end-state contracts."""
    parts = [item for item in state.path.split("/") if item]
    expected_names = _entity_names(contract, str(state.expected))
    if parts and parts[-1] in {"holder", "owner", "owners"}:
        item_names = _entity_names(contract, parts[-2] if len(parts) >= 2 else "")
        possession = (
            "接过",
            "收下",
            "拿到",
            "持有",
            "保管",
            "放进",
            "塞进",
            "滑进",
            "装进",
            "收好",
        )
        for sentence in re.split(r"[。！？\n]+", text):
            if (
                any(name in sentence for name in expected_names)
                and any(name in sentence for name in item_names)
                and any(word in sentence for word in possession)
            ):
                return sentence[:180]
        return ""
    if parts and parts[-1] == "action":
        actor_names = _entity_names(contract, parts[-2] if len(parts) >= 2 else "")
        terms = _keywords(str(state.expected))
        for sentence in re.split(r"[。！？\n]+", text):
            if (
                (not actor_names or any(name in sentence for name in actor_names))
                and terms
                and sum(term in sentence for term in terms) >= min(2, len(terms))
            ):
                return sentence[:180]
        return ""
    if parts and parts[-1] in {"light", "lamp"} and str(state.expected).lower() in {
        "on",
        "true",
        "亮",
        "亮起",
    }:
        match = re.search(r"(?:灯|光柱|灯泡).{0,50}(?:重新)?(?:亮起|亮着|点亮)", text)
        return _evidence(match)
    expected = str(state.expected)
    return expected[:180] if expected and expected in text else ""


def _authorised_text(contract: NarrativeContract) -> str:
    parts: list[str] = []
    for fact in contract.required_facts:
        parts.extend([fact.subject, fact.predicate, fact.object, fact.time, fact.statement])
    for event in contract.required_events:
        parts.extend([event.actor, event.action, event.target, event.description])
    for item in contract.required_end_state:
        parts.extend([item.path, str(item.expected), item.description])
    for item in contract.time_constraints:
        parts.extend([item.description, item.deadline])
    for item in contract.protected_relationships:
        parts.extend([*item.parties, item.relationship])
    for group in (
        contract.allowed_entities.characters,
        contract.allowed_entities.locations,
        contract.allowed_entities.items,
        contract.allowed_entities.organizations,
    ):
        for entity in group:
            parts.extend(entity.all_names)
    return "\n".join(part for part in parts if part)


def _known_organizations(contract: NarrativeContract) -> set[str]:
    return {
        name
        for item in contract.allowed_entities.organizations
        for name in item.all_names
        if name
    }


class NarrativeContractValidator:
    """Check prose before StateDelta is considered for authority."""

    def validate(
        self, contract: NarrativeContract, narrative_text: str
    ) -> NarrativeValidationReport:
        text = narrative_text or ""
        violations: list[NarrativeViolation] = []
        missing_events: list[str] = []
        unsupported: list[str] = []
        end_results: list[EndStateResult] = []
        passed_facts = 0
        required_facts = [item for item in contract.required_facts if item.required_in_prose]
        passed_events = 0
        passed_ends = 0
        passed_times = 0

        def add(
            code: str,
            message: str,
            severity: str = "high",
            *,
            path: str = "",
            evidence: str = "",
            repair_hint: str = "",
        ) -> None:
            key = (code, path, evidence)
            if any((item.code, item.path, item.evidence) == key for item in violations):
                return
            violations.append(
                NarrativeViolation(
                    code=code,
                    message=message,
                    severity=severity,
                    path=path,
                    evidence=evidence,
                    repair_hint=repair_hint,
                )
            )

        for fact in required_facts:
            contradicted = _matches(text, fact.contradiction_patterns)
            mutated = _matches(text, fact.mutation_patterns)
            if contradicted:
                add(
                    "REQUIRED_FACT_CONTRADICTED",
                    f"必要事实 {fact.id} 被正文否定",
                    path=f"/required_facts/{fact.id}",
                    evidence=_evidence(contradicted),
                    repair_hint="恢复契约中的既定事实，不增加解释性背景",
                )
                continue
            if mutated:
                add(
                    "REQUIRED_FACT_MUTATED",
                    f"必要事实 {fact.id} 被改写",
                    path=f"/required_facts/{fact.id}",
                    evidence=_evidence(mutated),
                    repair_hint="按契约原义恢复事实",
                )
                continue
            evidence = _matches(text, fact.evidence_patterns)
            if not evidence and not fact.evidence_patterns:
                terms = _keywords(
                    fact.statement
                    or " ".join([fact.subject, fact.predicate, fact.object, fact.time])
                )
                if terms and sum(item in text for item in terms) >= min(2, len(terms)):
                    passed_facts += 1
                    continue
            if evidence:
                passed_facts += 1
            else:
                add(
                    "REQUIRED_FACT_MISSING",
                    f"正文没有保留必要事实 {fact.id}",
                    path=f"/required_facts/{fact.id}",
                    repair_hint="用最短句补回该事实",
                )

        for event in contract.required_events:
            incomplete = _matches(text, event.incomplete_patterns)
            evidence = _matches(text, event.evidence_patterns)
            fallback, fallback_evidence = _event_fallback_match(contract, event, text)
            if evidence or ((event.keywords or not event.evidence_patterns) and fallback):
                passed_events += 1
                continue
            missing_events.append(event.id)
            if incomplete:
                code = "REQUIRED_EVENT_INCOMPLETE"
                message = f"必要事件 {event.id} 只被提及但未完成"
                found = _evidence(incomplete)
            else:
                actor_names = _entity_names(contract, event.actor)
                target_names = _entity_names(contract, event.target)
                action_terms = _keywords(event.action)
                actor_seen = not actor_names or any(item in text for item in actor_names)
                target_seen = not target_names or any(item in text for item in target_names)
                action_seen = any(item in text for item in action_terms)
                if action_seen and not actor_seen:
                    code = "REQUIRED_EVENT_ACTOR_MISMATCH"
                elif actor_seen and action_seen and not target_seen:
                    code = "REQUIRED_EVENT_TARGET_MISMATCH"
                else:
                    code = "REQUIRED_EVENT_MISSING"
                message = f"正文没有完成必要事件 {event.id}"
                found = fallback_evidence
            add(
                code,
                message,
                path=f"/required_events/{event.id}",
                evidence=found,
                repair_hint="只补写该事件的完成动作，不新增人物或原因",
            )
            if incomplete:
                add(
                    "REQUIRED_EVENT_MISSING",
                    f"必要事件 {event.id} 尚未实际完成",
                    path=f"/required_events/{event.id}",
                    evidence=found,
                    repair_hint="把讨论或假设改成已完成的实际动作",
                )

        for state in contract.required_end_state:
            evidence = _matches(text, state.evidence_patterns)
            semantic_evidence = (
                ""
                if state.evidence_patterns
                else _end_state_fallback_match(contract, state, text)
            )
            wrong = _matches(text, state.wrong_state_patterns)
            if evidence or semantic_evidence:
                passed_ends += 1
                end_results.append(
                    EndStateResult(
                        id=state.id,
                        path=state.path,
                        expected=state.expected,
                        reached=True,
                        evidence=_evidence(evidence) or semantic_evidence,
                    )
                )
                continue
            if wrong and state.path.endswith("/holder"):
                code = "END_STATE_WRONG_HOLDER"
            elif wrong and state.path.endswith("/action"):
                code = "END_STATE_WRONG_ACTOR"
            elif wrong:
                code = "END_STATE_MISSING"
            else:
                code = "END_STATE_NOT_REACHED"
            found = _evidence(wrong)
            add(
                code,
                f"最终状态 {state.id} 未达到: {state.path} 应为 {state.expected}",
                path=state.path,
                evidence=found,
                repair_hint="在正文结尾落实该状态，不要只讨论或计划",
            )
            end_results.append(
                EndStateResult(
                    id=state.id,
                    path=state.path,
                    expected=state.expected,
                    reached=False,
                    evidence=found,
                    violation_code=code,
                )
            )

        for constraint in contract.time_constraints:
            mutated = _matches(text, constraint.mutation_patterns)
            required = _matches(text, constraint.required_patterns)
            causal = _matches(text, constraint.causal_patterns)
            weakened = _matches(text, constraint.weakened_patterns)
            passed = True
            if mutated:
                passed = False
                add(
                    "TIME_CONSTRAINT_MUTATED",
                    f"时间约束 {constraint.id} 被改写",
                    path=f"/time_constraints/{constraint.id}",
                    evidence=_evidence(mutated),
                    repair_hint="恢复原截止时间",
                )
            if constraint.required_patterns and not required:
                passed = False
                add(
                    "TIME_CONSTRAINT_MISSING",
                    f"正文遗漏时间约束 {constraint.id}",
                    path=f"/time_constraints/{constraint.id}",
                    repair_hint="补回截止时间",
                )
            if weakened or (constraint.causal_patterns and not causal):
                passed = False
                add(
                    "CAUSAL_LINK_WEAKENED",
                    f"时间约束 {constraint.id} 的后果链被削弱",
                    path=f"/time_constraints/{constraint.id}",
                    evidence=_evidence(weakened),
                    repair_hint="明确保留不按时行动会造成的既定后果",
                )
            if passed:
                passed_times += 1

        authorised = _authorised_text(contract)
        self._validate_builtin_additions(
            contract,
            text,
            authorised,
            add=add,
            unsupported=unsupported,
        )
        for addition in contract.forbidden_additions:
            match = _matches(text, addition.patterns)
            if not match or _matches(match.group(0), addition.allowed_patterns):
                continue
            code = addition.code or self._category_code(addition.category)
            add(
                code,
                addition.description,
                addition.severity,
                path=f"/forbidden_additions/{addition.id}",
                evidence=_evidence(match),
                repair_hint="删除未授权细节，不用另一项新增事实替代",
            )
            unsupported.append(addition.id)

        for outcome in contract.forbidden_outcomes:
            match = _matches(text, outcome.patterns)
            if match:
                add(
                    "FORBIDDEN_OUTCOME_MENTIONED",
                    f"正文提出了禁止结果: {outcome.description}",
                    outcome.severity,
                    path=f"/forbidden_outcomes/{outcome.id}",
                    evidence=_evidence(match),
                    repair_hint="删除该选项及其讨论，不改变固定结局",
                )

        for relationship in contract.protected_relationships:
            match = _matches(text, relationship.forbidden_patterns)
            if match:
                add(
                    "NARRATIVE_RELATION_MUTATED",
                    f"受保护关系 {relationship.id} 被改写",
                    path=f"/protected_relationships/{relationship.id}",
                    evidence=_evidence(match),
                )

        for link in contract.protected_causal_links:
            weakened = _matches(text, link.weakened_patterns)
            required = _matches(text, link.required_patterns)
            if weakened or (link.required_patterns and not required):
                add(
                    "CAUSAL_LINK_WEAKENED",
                    f"受保护因果链 {link.id} 被削弱",
                    path=f"/protected_causal_links/{link.id}",
                    evidence=_evidence(weakened),
                    repair_hint="保留原因、后果和触发顺序",
                )

        chars = narrative_char_count(text)
        if chars < contract.length_constraint.min_chars:
            add(
                "NARRATIVE_TOO_SHORT",
                f"正文 {chars} 字，低于最小值 {contract.length_constraint.min_chars}",
                path="/length_constraint/min_chars",
                repair_hint="只补足既定事件的动作与必要过渡",
            )
        elif chars > contract.length_constraint.max_chars:
            add(
                "NARRATIVE_TOO_LONG",
                f"正文 {chars} 字，超过最大值 {contract.length_constraint.max_chars}",
                path="/length_constraint/max_chars",
                repair_hint="删减重复描写，不删除必要事件",
            )

        fact_cov = passed_facts / len(required_facts) if required_facts else 1.0
        event_cov = passed_events / len(contract.required_events) if contract.required_events else 1.0
        end_cov = passed_ends / len(contract.required_end_state) if contract.required_end_state else 1.0
        time_cov = passed_times / len(contract.time_constraints) if contract.time_constraints else 1.0
        coverage = (fact_cov + event_cov + end_cov + time_cov) / 4
        severity = max(
            (item.severity for item in violations), key=_rank, default="low"
        )
        return NarrativeValidationReport(
            accepted=not any(item.severity == "high" for item in violations),
            severity=severity,
            violations=violations,
            missing_required_events=list(dict.fromkeys(missing_events)),
            unsupported_additions=list(dict.fromkeys(unsupported)),
            end_state_results=end_results,
            contract_coverage=round(coverage, 4),
            required_fact_coverage=round(fact_cov, 4),
            required_event_coverage=round(event_cov, 4),
            required_end_state_coverage=round(end_cov, 4),
            narrative_char_count=chars,
            repairable=True,
        )

    def _validate_builtin_additions(
        self,
        contract: NarrativeContract,
        text: str,
        authorised: str,
        *,
        add,
        unsupported: list[str],
    ) -> None:
        kinships = [item for item in _KINSHIP.findall(text) if item not in authorised]
        if kinships:
            evidence = "、".join(dict.fromkeys(kinships))
            add(
                "UNSUPPORTED_KINSHIP_ADDED",
                "正文新增了契约未授权的亲属关系",
                evidence=evidence,
                repair_hint="删除亲属身份，改用已授权人物关系",
            )
            add(
                "NARRATIVE_RELATION_ADDED",
                "新增亲属使人物关系超出实体白名单",
                evidence=evidence,
            )
            unsupported.append("kinship")

        casualty = next(
            (item for item in _CASUALTY.finditer(text) if item.group(0) not in authorised),
            None,
        )
        if casualty:
            add(
                "UNSUPPORTED_CASUALTY_ADDED",
                "正文新增了未授权的伤亡统计",
                evidence=casualty.group(0),
                repair_hint="删除伤亡数字，只保留契约已有的事件称谓",
            )
            add(
                "UNSUPPORTED_NUMBER_ADDED",
                "伤亡数字不在 NarrativeContract 数字白名单中",
                evidence=casualty.group(1),
            )
            unsupported.append("casualty")

        dated = next(
            (item for item in _DATED.finditer(text) if item.group(0) not in authorised),
            None,
        )
        if dated:
            add(
                "UNSUPPORTED_DATE_ADDED",
                "正文新增了未授权的具体日期或相对时间点",
                evidence=dated.group(0),
                repair_hint="恢复契约中的宽粒度时间，不补具体日期",
            )
            unsupported.append("date")

        age = next(
            (item for item in _AGE.finditer(text) if item.group(0) not in authorised),
            None,
        )
        duration = next(
            (
                item
                for item in _BACKSTORY_DURATION.finditer(text)
                if item.group(0) not in authorised
            ),
            None,
        )
        if age or duration:
            evidence = (age or duration).group(0)
            add(
                "UNSUPPORTED_BACKSTORY_ADDED",
                "正文新增了未授权的人物年龄或相处年限",
                evidence=evidence,
                repair_hint="删除年龄和经历年限",
            )
            add(
                "UNSUPPORTED_NUMBER_ADDED",
                "人物背景数字不在 NarrativeContract 数字白名单中",
                evidence=evidence,
            )
            unsupported.append("backstory")

        violence = _VIOLENCE_OR_INJURY.search(text)
        authorised_injury = any(
            token in authorised for token in ("打斗", "击打", "沈砚受伤", "沈砚流血")
        )
        if violence and not authorised_injury:
            add(
                "UNSUPPORTED_INJURY_ADDED",
                "正文新增了未授权的暴力动作或伤势",
                evidence=violence.group(0),
                repair_hint="删除新伤势与肢体冲突，使用既定事件表达风格",
            )
            unsupported.append("injury")

        extra = _EXTRA_PERSON_COUNT.search(text)
        max_generic_people = sum(
            item.max_count
            for item in contract.allowed_entities.characters
            if item.id in {"investigator", "调查员"} or "调查员" in item.all_names
        )
        if extra and max_generic_people <= 1:
            add(
                "NARRATIVE_CHARACTER_ADDED",
                "正文在门外新增了第二个实际人物",
                evidence=extra.group(0),
                repair_hint="只保留契约授权的单个调查员",
            )
            unsupported.append("character")

        known_orgs = _known_organizations(contract)
        organization = next(
            (
                item
                for item in _ORGANIZATION.finditer(text)
                if not any(name and name in item.group(0) for name in known_orgs)
            ),
            None,
        )
        if organization:
            add(
                "UNSUPPORTED_ORGANIZATION_ADDED",
                "正文新增了契约未授权的组织",
                evidence=organization.group(0),
                repair_hint="删除新增组织，只保留白名单实体",
            )
            add(
                "NARRATIVE_ORGANIZATION_ADDED",
                "新增组织超出实体白名单",
                evidence=organization.group(0),
            )
            unsupported.append("organization")

        known_people = {
            name
            for item in contract.allowed_entities.characters
            for name in item.all_names
            if name
        }
        unknown_person = next(
            (
                item
                for item in _NAMED_PERSON_INTRO.finditer(text)
                if item.group(1) not in known_people
            ),
            None,
        )
        if unknown_person:
            add(
                "NARRATIVE_ENTITY_UNKNOWN",
                "正文新增了实体白名单之外的命名人物",
                evidence=unknown_person.group(0),
                repair_hint="删除新命名人物，改用契约已授权的人物或无事实负担的环境描写",
            )
            add(
                "NARRATIVE_CHARACTER_ADDED",
                "正文新增了未授权的命名人物",
                evidence=unknown_person.group(1),
            )
            unsupported.append("character")

    @staticmethod
    def _category_code(category: str) -> str:
        return {
            "number": "UNSUPPORTED_NUMBER_ADDED",
            "date": "UNSUPPORTED_DATE_ADDED",
            "kinship": "UNSUPPORTED_KINSHIP_ADDED",
            "casualty": "UNSUPPORTED_CASUALTY_ADDED",
            "injury": "UNSUPPORTED_INJURY_ADDED",
            "backstory": "UNSUPPORTED_BACKSTORY_ADDED",
            "character": "NARRATIVE_CHARACTER_ADDED",
            "relation": "NARRATIVE_RELATION_ADDED",
            "organization": "UNSUPPORTED_ORGANIZATION_ADDED",
            "entity": "NARRATIVE_ENTITY_UNKNOWN",
        }.get(category, "UNSUPPORTED_ADDITION")


__all__ = ["NarrativeContractValidator"]
