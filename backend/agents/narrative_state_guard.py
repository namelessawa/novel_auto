"""High-precision semantic guard for one Narrator tick.

The Narrator emits prose plus an end-of-tick continuity ledger.  This guard
checks the ordered prose against the previous and declared ledgers, performs at
most two bounded surgical repairs, then verifies every repair independently.  It is
deliberately conservative: plausibility concerns and omitted reminders are not
state contradictions.
"""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from dataclasses import dataclass, field

from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client
from nf_core.reasoning_filter import strip_reasoning_leak


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NarrativeStateGuardOutput:
    narrative_text: str
    continuity_state: dict
    safe: bool
    adopted: bool = False
    trace: dict = field(default_factory=dict)


class NarrativeStateGuard:
    """Check and, only when necessary, repair one completed narrative tick."""

    async def guard(
        self,
        *,
        narrative_text: str,
        previous_state: dict,
        declared_state: dict,
        required_events: list[dict] | None = None,
        style_contract: str = "",
        protected_terms: list[str] | None = None,
        entity_names: dict[str, str] | None = None,
        tracking_character_id: str = "",
        tick: int = 0,
    ) -> NarrativeStateGuardOutput:
        required_events = required_events or []
        known_entities = sorted({
            term.strip() for term in (protected_terms or []) if term.strip()
        })
        entity_names = {
            str(entity_id): str(name).strip()
            for entity_id, name in (entity_names or {}).items()
            if str(name).strip()
        }
        protected = sorted({
            term.strip()
            for term in known_entities
            if term.strip() and term.strip() in narrative_text
        })
        trace: dict = {
            "attempted": True,
            "repair_attempted": False,
            "required_events": required_events,
            "known_entities": known_entities,
            "entity_names": entity_names,
            "tracking_character_id": tracking_character_id,
        }
        first = await self._verify(
            previous_state=previous_state,
            narrative_text=narrative_text,
            declared_state=declared_state,
            original_text=narrative_text,
            required_events=required_events,
            known_entities=known_entities,
            entity_names=entity_names,
            tracking_character_id=tracking_character_id,
            tick=tick,
        )
        trace["before"] = first
        if first.get("safe", False):
            return NarrativeStateGuardOutput(
                narrative_text=narrative_text,
                continuity_state=declared_state,
                safe=True,
                trace=trace,
            )

        trace["repair_attempted"] = True
        repaired_text, repaired_state, repair_payload = await self._repair(
            narrative_text=narrative_text,
            previous_state=previous_state,
            declared_state=declared_state,
            findings=first,
            required_events=required_events,
            known_entities=known_entities,
            style_contract=style_contract,
            tick=tick,
        )
        trace["repair_declared"] = repair_payload.get("repairs", [])
        repaired_text, leaked = strip_reasoning_leak(repaired_text)
        ratio = len(repaired_text) / max(1, len(narrative_text))
        missing_terms = [term for term in protected if term not in repaired_text]
        max_ratio = (
            1.70 if first.get("event_fulfillment_conflicts") else 1.15
        )
        length_ok = 0.72 <= ratio <= max_ratio or abs(
            len(repaired_text) - len(narrative_text)
        ) <= 120
        guard_ok = bool(repaired_text and repaired_state) and (
            not leaked and length_ok and not missing_terms
        )
        trace["repair_guard"] = {
            "length_ratio": round(ratio, 4),
            "reasoning_leak": leaked,
            "missing_protected_terms": missing_terms,
            "passed": guard_ok,
        }
        if not guard_ok:
            trace["reject_reason"] = "deterministic_repair_guard_failed"
            return NarrativeStateGuardOutput(
                narrative_text=narrative_text,
                continuity_state=declared_state,
                safe=False,
                trace=trace,
            )

        second = await self._verify(
            previous_state=previous_state,
            narrative_text=repaired_text,
            declared_state=repaired_state,
            original_text=narrative_text,
            required_events=required_events,
            known_entities=known_entities,
            entity_names=entity_names,
            tracking_character_id=tracking_character_id,
            tick=tick,
        )
        trace["after"] = second
        if not second.get("safe", False):
            # One verifier-directed retry is cheaper than discarding a high-value
            # tick, and specifically handles repairs that stop short of or overshoot
            # an exact endpoint.  It remains bounded: no third repair is attempted.
            trace["repair_retry_attempted"] = True
            retry_text, retry_state, retry_payload = await self._repair(
                narrative_text=repaired_text,
                previous_state=previous_state,
                declared_state=repaired_state,
                findings=second,
                required_events=required_events,
                known_entities=known_entities,
                style_contract=style_contract,
                tick=tick,
            )
            trace["repair_retry_declared"] = retry_payload.get("repairs", [])
            retry_text, retry_leaked = strip_reasoning_leak(retry_text)
            retry_ratio = len(retry_text) / max(1, len(repaired_text))
            retry_missing_terms = [term for term in protected if term not in retry_text]
            retry_max_ratio = (
                1.35 if second.get("event_fulfillment_conflicts") else 1.15
            )
            retry_length_ok = 0.78 <= retry_ratio <= retry_max_ratio or abs(
                len(retry_text) - len(repaired_text)
            ) <= 120
            retry_guard_ok = bool(retry_text and retry_state) and (
                not retry_leaked
                and retry_length_ok
                and not retry_missing_terms
            )
            trace["repair_retry_guard"] = {
                "length_ratio": round(retry_ratio, 4),
                "reasoning_leak": retry_leaked,
                "missing_protected_terms": retry_missing_terms,
                "passed": retry_guard_ok,
            }
            if not retry_guard_ok:
                trace["reject_reason"] = "semantic_repair_verification_failed"
                return NarrativeStateGuardOutput(
                    narrative_text=narrative_text,
                    continuity_state=declared_state,
                    safe=False,
                    trace=trace,
                )
            third = await self._verify(
                previous_state=previous_state,
                narrative_text=retry_text,
                declared_state=retry_state,
                original_text=narrative_text,
                required_events=required_events,
                known_entities=known_entities,
                entity_names=entity_names,
                tracking_character_id=tracking_character_id,
                tick=tick,
            )
            trace["after_retry"] = third
            if not third.get("safe", False):
                trace["reject_reason"] = "semantic_repair_retry_verification_failed"
                return NarrativeStateGuardOutput(
                    narrative_text=narrative_text,
                    continuity_state=declared_state,
                    safe=False,
                    trace=trace,
                )
            repaired_text = retry_text
            repaired_state = retry_state
            trace["repair_retry_adopted"] = True
        trace["adopted"] = True
        return NarrativeStateGuardOutput(
            narrative_text=repaired_text,
            continuity_state=repaired_state,
            safe=True,
            adopted=True,
            trace=trace,
        )

    async def _verify(
        self,
        *,
        previous_state: dict,
        narrative_text: str,
        declared_state: dict,
        original_text: str,
        required_events: list[dict],
        known_entities: list[str],
        entity_names: dict[str, str],
        tracking_character_id: str = "",
        tick: int,
    ) -> dict:
        try:
            resp = await llm_client.chat(
                system_prompt=(
                    "你是高精度小说状态审校员。逐句按原文顺序核对，不做文学批评，"
                    "不把可能性、合理省略或未重复提醒当成矛盾。严格输出 JSON。"
                ),
                user_prompt=f"""\
【上一段结束状态】
{json.dumps(previous_state, ensure_ascii=False)}

【本段正文（顺序不可打乱）】
{narrative_text}

【本段声明的结束状态】
{json.dumps(declared_state, ensure_ascii=False)}

【修订前原文；首次检查时与正文相同】
{original_text}

【本段已声明消费、必须兑现的源事件】
{json.dumps(required_events, ensure_ascii=False)}

【此前已经建立、允许直接使用的专名】
{json.dumps(known_entities, ensure_ascii=False)}

只检查下列硬矛盾：
1. 上一段仍有效的伤势、存亡、地点、持有者、数量、损坏状态在正文中无明确事件
   就改变；已经交付、用完、丢弃或损坏的物品无依据恢复。
2. 正文内部把伤势/物品归错人，或后句与前句的明确状态冲突。
   人物在对白里说“某物还在我这里/由我保管”同样是持有状态声明，必须与前文
   动作和账本核对，不能因为它只是台词就跳过。
3. 声明的结束状态与正文最后实际状态不一致。
4. 若这是修订稿，修订是否删除、增加或改变了独立事件、决定、结果或知识来源。
5. 已声明消费的源事件是本段事实边界。源事件明写“已经/必须/本段完成”
   的结果必须在正文里真正发生，不得停在行动之前，也不得重演源事件
   已声明完成的前态。把源事件漏写的结果补回正文不算“新增事件”。
   required_end_states 中每一条都必须在正文结尾与 declared_state 同时成立；
   少一条即 event_fulfillment_conflicts，不能用气氛、意图或接近目标代替结果。
6. 若正文新增不在“允许专名”和源事件中的姓名，并借此新增旧债、搭档、亲属、
   交易、遗言或悬念，列入 entity_grounding_conflicts。素材只给“守门人”等称谓
   时可继续使用该称谓，不要擅自命名；普通无名路人不算冲突。

对 required_end_states 必须逐条输出 event_checks，并原样回填 requirement。
prose_evidence 必须是正文中的逐字短引文数组；ledger_evidence_paths 必须是从
declared_state 根开始、用点分隔的真实字段路径数组（如 characters.char_linxue.location、
items.地图.holder、time_marker；knowledge 是列表时可写 knowledge.完整条目）。复合要求
可给多个引文/路径。二者缺一、引文或路径
不存在、或 met=false，都不能判安全。event_id 原样回填源事件 id。

高精度边界：必须按句子出现顺序判断，不得把前面的动作误说成发生在后面；角色
没有再次提到夹板、伤口或物品不等于状态消失；受伤者借助支撑站起不自动矛盾；
半张纸仍可以折叠或展开；“应该处理伤口”等合理性建议不是状态矛盾。每个冲突都
必须给出前后两处短引文。“往/向某处走”只表示开始移动，不等于已进入目的地；
若 declared_location 与你写出的 actual_location 相同，禁止再报 location_mismatch。
禁止把 note/reason 明写“无冲突/状态一致/有正文依据”的项目塞进冲突数组。
证据不足就判安全。

严格输出：
{{"safe":true,"event_checks":[{{"event_id":"源事件id","requirement":"原样要求","met":true,"prose_evidence":["正文逐字引文"],"ledger_evidence_paths":["characters.char_id.location"]}}],"event_fulfillment_conflicts":[],"entity_grounding_conflicts":[],"prior_state_conflicts":[],"internal_conflicts":[],"ledger_conflicts":[],"fact_changes_from_original":[],"reason":"一句话"}}
""",
                temperature=0.0,
                max_tokens=1600,
                agent_id="narrative_state_verifier",
                priority="critical",
                tick=tick,
            )
            payload = parse_llm_json(resp.content)
        except Exception as exc:
            logger.warning("NarrativeStateGuard verifier failed: %s", exc)
            return {"safe": False, "error": str(exc)[:240]}

        keys = (
            "event_fulfillment_conflicts",
            "entity_grounding_conflicts",
            "prior_state_conflicts",
            "internal_conflicts",
            "ledger_conflicts",
            "fact_changes_from_original",
        )
        findings = {
            key: self._actionable_findings(payload.get(key, []) or [])
            for key in keys
        }
        event_checks = [
            check for check in (payload.get("event_checks", []) or [])
            if isinstance(check, dict)
        ]
        evidence_failures = self._event_evidence_failures(
            required_events=required_events,
            event_checks=event_checks,
            narrative_text=narrative_text,
            declared_state=declared_state,
            entity_names=entity_names,
            tracking_character_id=tracking_character_id,
        )
        findings["event_fulfillment_conflicts"].extend(evidence_failures)
        findings["event_fulfillment_conflicts"].extend(
            self._deterministic_required_location_conflicts(
                required_events=required_events,
                declared_state=declared_state,
            )
        )
        findings["entity_grounding_conflicts"].extend(
            self._deterministic_named_entity_conflicts(
                narrative_text=narrative_text,
                known_entities=known_entities,
                required_events=required_events,
            )
        )
        findings["prior_state_conflicts"].extend(
            self._deterministic_holder_conflicts(
                previous_state=previous_state,
                narrative_text=narrative_text,
                entity_names=entity_names,
            )
        )
        safe = not any(findings.values())
        return {
            "safe": safe,
            "reported_safe": bool(payload.get("safe")),
            "event_checks": event_checks,
            **findings,
            "reason": str(payload.get("reason", "") or "")[:300],
        }

    async def _repair(
        self,
        *,
        narrative_text: str,
        previous_state: dict,
        declared_state: dict,
        findings: dict,
        required_events: list[dict],
        known_entities: list[str],
        style_contract: str,
        tick: int,
    ) -> tuple[str, dict, dict]:
        try:
            resp = await llm_client.chat(
                system_prompt=(
                    "你是小说连续性外科修订器。只改验证器已有逐句证据的矛盾，"
                    "源事件终态高于文风和悬念，严格输出 JSON。"
                ),
                user_prompt=f"""\
上一段结束状态：{json.dumps(previous_state, ensure_ascii=False)}
本段原文：
{narrative_text}
本段原声明状态：{json.dumps(declared_state, ensure_ascii=False)}
验证器发现：{json.dumps(findings, ensure_ascii=False)}
必须兑现的源事件：{json.dumps(required_events, ensure_ascii=False)}
允许专名：{json.dumps(known_entities, ensure_ascii=False)}
风格契约：{style_contract or '保持原文风格'}

最高优先级：逐条完成 required_end_states。若原文尾段主动阻止某一结束状态成立，
必须替换或收束该尾段，不能只在后面继续扩写同一个障碍。不得新增敌人、战斗、条件、
门槛或悬念来拖延结果。例如要求“地图已交、两人已入城”时，修订稿必须明确写门已
打开、两人都越过门线，并把两人的 location 更新到城内；“仍在门外/门没开/继续交战”
一律是不合格。反过来，要求“到达城墙外/门前/入口外”时必须停在外侧，不能越过
门线写到城内；“已经进入”不是超额完成，而是位置错误。风格钩子只能放在全部终态
兑现之后。

只要验证结果中的 event_fulfillment_conflicts 非空，禁止原文不改、禁止声称“验证器
误报”或只改 repairs 说明；必须实际修改 narrative_text，并让对应终态在正文和账本中
都有可逐字核对的证据。若要求“新的代价”，不得把源事件已经指定的地图付款重复算作
新代价，必须明写另一项损失、义务、限制或风险。

只修有前后引文证明的状态矛盾。优先改后出现的错误称谓、持有者或重复消耗；若
正文已经清楚写出合法变化而只是结束账本写错，只改账本。源事件已明写但
原文停在结果之前，或 required_end_states 尚有一条未成立时，必须用原有人物/物品
补齐全部结束状态，并同步 continuity_state。除此之外不得删除、
新增、改序独立事件，不得用修改前文为后文圆谎。删除无源专名及其凭空关系时，
保留源事件要求的无名角色和交易结果。输出修订后完整正文和完整结束状态。
严格输出：
{{"narrative_text":"完整正文","continuity_state":{{}},"repairs":["修复项"]}}
""",
                temperature=0.0,
                max_tokens=min(6000, max(1800, len(narrative_text) * 2)),
                agent_id="narrative_state_repair",
                priority="critical",
                tick=tick,
            )
            payload = parse_llm_json(resp.content)
            text = str(payload.get("narrative_text", "") or "").strip()
            state = payload.get("continuity_state", {})
            return text, dict(state) if isinstance(state, dict) else {}, payload
        except Exception as exc:
            logger.warning("NarrativeStateGuard repair failed: %s", exc)
            return "", {}, {"error": str(exc)[:240]}

    @staticmethod
    def _event_evidence_failures(
        *,
        required_events: list[dict],
        event_checks: list[dict],
        narrative_text: str,
        declared_state: dict,
        entity_names: dict[str, str] | None = None,
        tracking_character_id: str = "",
    ) -> list[str]:
        """Fail closed when a required end state lacks quoted prose + ledger evidence."""
        failures: list[str] = []
        for event in required_events:
            event_id = str(event.get("id", "") or "")
            for raw_requirement in event.get("required_end_states", []) or []:
                requirement = str(raw_requirement or "").strip()
                if not requirement:
                    continue
                check = NarrativeStateGuard._matching_event_check(
                    requirement, event_checks
                )
                if check is None:
                    failures.append(
                        f"源事件 {event_id} 的结束状态缺少逐条核验：{requirement}"
                    )
                    continue
                raw_prose = check.get("prose_evidence", []) or []
                prose_evidence = (
                    [str(raw_prose).strip()]
                    if isinstance(raw_prose, str)
                    else [str(item).strip() for item in raw_prose if str(item).strip()]
                )
                raw_paths = check.get("ledger_evidence_paths", []) or []
                ledger_paths = (
                    [str(raw_paths).strip()]
                    if isinstance(raw_paths, str)
                    else [str(item).strip() for item in raw_paths if str(item).strip()]
                )
                prose_ok = bool(prose_evidence) and all(
                    NarrativeStateGuard._evidence_appears(quote, narrative_text)
                    for quote in prose_evidence
                )
                ledger_ok = bool(ledger_paths) and all(
                    NarrativeStateGuard._ledger_path_exists(declared_state, path)
                    for path in ledger_paths
                )
                semantic_failure = NarrativeStateGuard._semantic_evidence_failure(
                    requirement=requirement,
                    prose_evidence=prose_evidence,
                    narrative_text=narrative_text,
                    entity_names=entity_names or {},
                    tracking_character_id=tracking_character_id,
                )
                if check.get("met") is not True:
                    failures.append(
                        f"源事件 {event_id} 的结束状态未兑现：{requirement}"
                    )
                elif not prose_ok or not ledger_ok or semantic_failure:
                    bad_quotes = [
                        quote for quote in prose_evidence
                        if not NarrativeStateGuard._evidence_appears(
                            quote, narrative_text
                        )
                    ]
                    bad_paths = [
                        path for path in ledger_paths
                        if not NarrativeStateGuard._ledger_path_exists(
                            declared_state, path
                        )
                    ]
                    failures.append(
                        f"源事件 {event_id} 的结束状态缺少正文/账本实证：{requirement}"
                        f"；无效引文={bad_quotes[:2]}；无效路径={bad_paths[:3]}"
                        + (f"；语义证据={semantic_failure}" if semantic_failure else "")
                    )
        return failures

    @staticmethod
    def _semantic_evidence_failure(
        *,
        requirement: str,
        prose_evidence: list[str],
        narrative_text: str,
        entity_names: dict[str, str],
        tracking_character_id: str,
    ) -> str:
        """Validate high-value causal and multi-participant evidence explicitly."""
        if "因雨水" in requirement or "因酸雨" in requirement:
            if not NarrativeStateGuard._rain_damage_evidence_ok(
                prose_evidence=prose_evidence,
                narrative_text=narrative_text,
            ):
                return "没有逐字引文或相邻正文证明雨水作用于地图并造成损坏"

        if "新代价" in requirement:
            combined = " ".join(prose_evidence)
            cost_marker = re.compile(
                r"(?:条件|必须|还要|任务|负责|修好|维修|寻找|带路|服役|"
                r"抵押|没收|扣下|留下|留在|隔离|等待|禁止|不得|不能|"
                r"交出(?![^，。；]{0,6}(?:地图|图纸|路线图))|外加|"
                r"欠.{0,8}(?:一次|人情|债|账)|"
                r"需要.{0,16}(?:你|修|找|带|滤芯|零件|任务|工作))"
            )
            non_map_item_cost = re.compile(
                r"(?:扳手|背包|净水片|滤芯|药|徽章|武器|工具).{0,16}"
                r"(?:交|留|扣|换|抵押|没收)"
            )
            additional_item = re.compile(
                r"(?:还有|另加|另外).{0,24}"
                r"(?:扳手|背包|净水片|滤芯|药|徽章|武器|工具)"
            )
            if not any(pattern.search(combined) for pattern in (
                cost_marker,
                non_map_item_cost,
                additional_item,
            )):
                return "证据只覆盖既定地图付款，没有独立的新损失、义务、限制或风险"

        group_endpoint = re.search(
            r"(?:两人|主角与伤员).{0,8}(?:已)?(?:进入|越过|穿过)",
            requirement,
        )
        if group_endpoint is None:
            return ""

        completion = re.compile(
            r"(?:进入|越过|穿过|跨过|钻过|挤进|走进|进到|"
            r"(?:往|向)(?:里|内|外|城内|门内).{0,3}(?:走|挪|移)|"
            r"(?:挤|滑|滚|钻|跨|迈|拖).{0,4}(?:过|进)|"
            r"(?:推|拉|拖|塞).{0,6}(?:出去|进去|过门|进门|进门缝|出门))"
        )
        group_subject = re.compile(r"(?:两人|二人|他们|她们|我们)")
        if any(group_subject.search(quote) and completion.search(quote)
               for quote in prose_evidence):
            return ""

        actor_ids: set[str] = set()
        for quote in prose_evidence:
            if completion.search(quote) is None:
                continue
            named_here = {
                entity_id
                for entity_id, name in entity_names.items()
                if name and name in quote
            }
            # “A 把 B 推进门缝”只证明 B 过门，不能顺带把 A 算作已过门；
            # A 若随后“跟着钻过去”，下一条证据会单独计入 A。
            passenger_ids = {
                entity_id
                for entity_id, name in entity_names.items()
                if name and re.search(
                    rf"把\s*{re.escape(name)}.{{0,6}}(?:推|拉|拖|塞)"
                    rf".{{0,6}}(?:进|出|过)",
                    quote,
                )
            }
            if passenger_ids:
                actor_ids.update(passenger_ids)
            else:
                actor_ids.update(named_here)
                if tracking_character_id and re.search(
                    r"(?:我|本人|她自己|他自己)", quote
                ):
                    actor_ids.add(tracking_character_id)
                elif (
                    tracking_character_id
                    and re.search(r"(?:她|他)", quote)
                    and any(
                        entity_id != tracking_character_id
                        for entity_id in named_here
                    )
                ):
                    actor_ids.add(tracking_character_id)
            # “A扶/背/拖着B穿过门”本身明确覆盖动作双方。
            if re.search(r"(?:扶|架|背|拖|搀|抱).{0,12}(?:进入|越过|穿过|跨过|钻过|挤进|走进)", quote):
                for entity_id, name in entity_names.items():
                    if name and name in quote:
                        actor_ids.add(entity_id)

        if len(actor_ids) < 2:
            return "复合终态没有逐字证明两名参与者都越过边界"
        return ""

    @staticmethod
    def _rain_damage_evidence_ok(
        *, prose_evidence: list[str], narrative_text: str
    ) -> bool:
        item = re.compile(r"(?:图|图纸|地图|防水纸|水文|钛合金板|板子)")
        damage = re.compile(r"(?:损|坏|破|蚀|糊|洞|烂|湿|洇|模糊|泛白)")
        direct_rain = re.compile(r"(?:雨|酸雨|雨水|水滴|滴水|第[一二三四五六七八九十]+滴水)")
        for quote in prose_evidence:
            if item.search(quote) and damage.search(quote) and direct_rain.search(quote):
                return True

        # 真实输出常用“钛合金板/板子”承接上一句的水文地图，并在下一条
        # evidence 写“酸雨渗进刻痕”。要求三类词都出现在同组逐字引文中。
        combined_evidence = "。".join(prose_evidence)
        rain_contact = re.compile(
            r"(?:雨|酸雨|雨水).{0,12}(?:淋|浸|渗|蚀|落|打|砸)|"
            r"(?:淋|浸|渗|蚀).{0,8}(?:雨|酸雨|雨水)"
        )
        if (
            item.search(combined_evidence)
            and damage.search(combined_evidence)
            and rain_contact.search(combined_evidence)
        ):
            return True

        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？!?])|\n+", narrative_text)
            if sentence.strip()
        ]
        rain_started = re.compile(
            r"(?:雨|酸雨).{0,10}(?:下|落|打|砸|飘|开始)|"
            r"(?:下|落|开始).{0,8}(?:雨|酸雨)"
        )
        for index, sentence in enumerate(sentences):
            if not (item.search(sentence) and damage.search(sentence)):
                continue
            # 中文叙事也会先写“地图湿了”，紧接着补一句“雨越下越大”。
            # 只放宽到前后各两句，避免把远处无关天气误接为因果。
            context = "".join(
                sentences[max(0, index - 2):min(len(sentences), index + 3)]
            )
            if rain_started.search(context):
                return True
        return False

    @staticmethod
    def _ledger_path_exists(state: dict, path: str) -> bool:
        current: object = state
        for part in (piece for piece in path.split(".") if piece):
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, dict):
                aliases = [
                    key for key in current
                    if len(str(key)) >= 2
                    and (
                        str(key) in part
                        or part in str(key)
                        or ("图" in str(key) and "图" in part)
                    )
                ]
                if len(aliases) != 1:
                    return False
                current = current[aliases[0]]
            elif isinstance(current, list):
                if part.isdigit() and int(part) < len(current):
                    current = current[int(part)]
                elif part in current:
                    current = part
                else:
                    return False
            else:
                return False
        return bool(path.strip())

    @staticmethod
    def _matching_event_check(
        requirement: str, event_checks: list[dict]
    ) -> dict | None:
        exact = next((
            item for item in event_checks
            if str(item.get("requirement", "") or "").strip() == requirement
        ), None)
        if exact is not None:
            return exact
        expected = re.sub(r"^本段结束前[：:]", "", requirement).strip()
        clauses = [
            clause.strip() for clause in re.split(r"[，；;]", expected)
            if clause.strip()
        ]
        matches: list[dict] = []
        for clause in clauses:
            match = next((
                item for item in event_checks
                if clause in re.sub(
                    r"^本段结束前[：:]", "",
                    str(item.get("requirement", "") or "").strip(),
                )
            ), None)
            if match is None:
                return None
            matches.append(match)
        if not matches:
            return None
        prose: list = []
        paths: list = []
        for item in matches:
            raw_prose = item.get("prose_evidence", []) or []
            prose.extend([raw_prose] if isinstance(raw_prose, str) else raw_prose)
            raw_paths = item.get("ledger_evidence_paths", []) or []
            paths.extend([raw_paths] if isinstance(raw_paths, str) else raw_paths)
        return {
            "requirement": requirement,
            "met": all(item.get("met") is True for item in matches),
            "prose_evidence": prose,
            "ledger_evidence_paths": paths,
        }

    @staticmethod
    def _evidence_appears(quote: str, text: str) -> bool:
        def normalise(value: str) -> str:
            return re.sub(
                r"[\s\"'“”‘’，。！？、：；—…（）()《》〈〉]+", "", value
            )

        needle = normalise(quote)
        haystack = normalise(text)
        if len(needle) < 2:
            return False
        if needle in haystack:
            return True
        if len(needle) < 4:
            return False
        for sentence in re.split(r"[。！？!?\n]+", text):
            candidate = normalise(sentence)
            if len(candidate) < 4:
                continue
            matcher = SequenceMatcher(None, needle, candidate)
            matched = sum(block.size for block in matcher.get_matching_blocks())
            if matched / max(1, min(len(needle), len(candidate))) >= 0.86:
                return True
        return False

    @staticmethod
    def _actionable_findings(raw_findings: object) -> list:
        findings = list(raw_findings) if isinstance(raw_findings, list) else []
        actionable: list = []
        for finding in findings:
            if isinstance(finding, dict):
                declared = finding.get("declared_location")
                actual = finding.get("actual_location")
                if declared and declared == actual:
                    continue
                note = " ".join(
                    str(finding.get(key, "") or "")
                    for key in ("note", "reason", "conflict")
                )
            else:
                note = str(finding)
            if re.search(
                r"(?:无冲突|不构成矛盾|状态一致|持有者一致|有正文依据|"
                r"与上一段结束状态一致|声明的结束状态已正确反映)",
                note,
            ):
                continue
            actionable.append(finding)
        return actionable

    @staticmethod
    def _deterministic_holder_conflicts(
        *,
        previous_state: dict,
        narrative_text: str,
        entity_names: dict[str, str],
    ) -> list[dict]:
        """Catch a different character taking a tracked item from own storage."""
        conflicts: list[dict] = []
        items = previous_state.get("items", {})
        if not isinstance(items, dict):
            return conflicts
        sentences = [
            sentence.strip() for sentence in re.split(r"(?<=[。！？!?])", narrative_text)
            if sentence.strip()
        ]
        prefix = ""
        for sentence in sentences:
            for item_name, item_state in items.items():
                if not isinstance(item_state, dict):
                    continue
                holder_id = str(item_state.get("holder", "") or "")
                holder_name = entity_names.get(holder_id, "")
                if not holder_name:
                    continue
                aliases = [str(item_name)]
                if "图" in str(item_name):
                    aliases.extend(["地图", "图纸", "路线图", "工程图"])
                alias_pattern = "(?:" + "|".join(
                    re.escape(alias) for alias in sorted(set(aliases), key=len, reverse=True)
                ) + ")"
                for actor_id, actor_name in entity_names.items():
                    if actor_id == holder_id or not actor_name:
                        continue
                    own_storage = re.search(
                        rf"{re.escape(actor_name)}[^。！？!?\n]{{0,10}}"
                        rf"从(?:自己)?(?:怀里|胸袋|口袋|腰包|内袋|靴筒)"
                        rf"[^。！？!?\n]{{0,6}}(?:掏|摸|拿|抽)出"
                        rf"[^。！？!?\n]{{0,10}}{alias_pattern}",
                        sentence,
                    )
                    if own_storage is None:
                        continue
                    handoff = re.search(
                        rf"{re.escape(holder_name)}[^。！？!?\n]{{0,18}}"
                        rf"(?:把|将)?[^。！？!?\n]{{0,8}}{alias_pattern}"
                        rf"[^。！？!?\n]{{0,8}}(?:递|交|塞|扔|拍)给"
                        rf"[^。！？!?\n]{{0,5}}{re.escape(actor_name)}",
                        prefix,
                    )
                    if handoff is None:
                        conflicts.append({
                            "type": "det_unmotivated_holder_change",
                            "item": str(item_name),
                            "previous_holder": holder_id,
                            "unexpected_actor": actor_id,
                            "evidence": own_storage.group(0),
                            "reason": (
                                f"上一段由{holder_name}持有，但{actor_name}从自己的随身"
                                "收纳处取出，前文没有明确交接"
                            ),
                        })
            prefix += sentence
        return conflicts

    @staticmethod
    def _deterministic_named_entity_conflicts(
        *,
        narrative_text: str,
        known_entities: list[str],
        required_events: list[dict],
    ) -> list[dict]:
        """Catch high-confidence names added to source material's unnamed roles."""
        permitted_text = " ".join(known_entities) + " " + json.dumps(
            required_events, ensure_ascii=False
        )
        candidates: set[str] = set()
        intro_pattern = re.compile(
            r"(?:名叫|叫作|叫做|人称|绰号(?:叫|是)?|外号(?:叫|是)?|"
            r"我认识，叫)[“\"'‘’]?([\u4e00-\u9fff]{2,4})"
        )
        candidates.update(match.group(1) for match in intro_pattern.finditer(narrative_text))
        surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜"
        titled_pattern = re.compile(
            rf"(?:老[{surnames}]|[{surnames}](?:队长|团长|主任|先生|女士|"
            r"师傅|医生|博士))"
        )
        candidates.update(match.group(0) for match in titled_pattern.finditer(narrative_text))
        ignored = {"叫人", "叫我", "叫他", "叫她", "叫住", "叫醒"}
        return [
            {
                "type": "det_ungrounded_named_entity",
                "name": candidate,
                "reason": "正文给无名角色新增了源事件和既有人物表均未提供的专名",
            }
            for candidate in sorted(candidates)
            if candidate not in ignored and candidate not in permitted_text
        ]

    @staticmethod
    def _deterministic_required_location_conflicts(
        *, required_events: list[dict], declared_state: dict
    ) -> list[str]:
        """Verify explicit ``已到达 X`` endpoints against character locations."""
        characters = declared_state.get("characters", {})
        if not isinstance(characters, dict):
            characters = {}
        locations = [
            str(state.get("location", "") or "")
            for state in characters.values()
            if isinstance(state, dict) and str(state.get("location", "") or "")
        ]
        conflicts: list[str] = []
        for event in required_events:
            event_id = str(event.get("id", "") or "")
            for raw_requirement in event.get("required_end_states", []) or []:
                requirement = str(raw_requirement or "").strip()
                match = re.search(r"(?:两人|主角与伤员)?已到达([^，；。]+)", requirement)
                entered = False
                if match is None:
                    match = re.search(
                        r"(?:两人|主角与伤员)?已进入([^，；。]+)", requirement
                    )
                    entered = match is not None
                if match is None:
                    continue
                target = match.group(1).strip()
                expected_count = 2 if ("两人" in requirement or "主角与伤员" in requirement) else 1

                def at_target(location: str) -> bool:
                    if target in location:
                        return True
                    if target == "城墙外":
                        near_wall = any(
                            marker in location
                            for marker in ("城墙", "城门", "城邦", "外墙")
                        )
                        outside = any(
                            marker in location for marker in ("外", "门前", "墙根")
                        )
                        inside = any(
                            marker in location for marker in ("城内", "门内", "内侧")
                        )
                        return near_wall and outside and not inside
                    if entered and target in ("城内", "城邦内", "门内"):
                        outside = any(
                            marker in location for marker in ("城外", "门外", "墙外")
                        )
                        inside = any(
                            marker in location
                            for marker in ("城内", "城邦内", "门内", "内侧")
                        )
                        inside = inside or bool(re.search(
                            r"(?:城|城邦|城墙).{0,12}"
                            r"(?:隧道内|值班室内|检疫站内|哨卡内|甬道内)",
                            location,
                        ))
                        return inside and not outside
                    return False

                actual_count = sum(at_target(location) for location in locations)
                if actual_count < expected_count:
                    conflicts.append(
                        f"源事件 {event_id} 要求终态位于{target}，但结束账本位置"
                        f"仅匹配 {actual_count}/{expected_count} 人：{locations[:4]}"
                    )
        return conflicts


__all__ = ["NarrativeStateGuard", "NarrativeStateGuardOutput"]
