"""Section-level prose editor for assembled multi-tick drafts.

The editor may remove replay, bridge seams and rebalance pacing.  It may not
invent, delete or reorder story facts.  A separate verifier plus deterministic
guards decide whether the candidate is adopted; any uncertainty keeps the raw
assembly.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from nf_core.json_utils import parse_llm_json
from nf_core.llm_client import llm_client
from nf_core.reasoning_filter import strip_reasoning_leak
from quality_metrics.section_seams import section_seam_report


logger = logging.getLogger(__name__)


_META_MARKERS = (
    "narrative_text",
    "tick ",
    "素材简报",
    "修改说明",
    "以下是",
    "首先，我",
    "Let me",
)


@dataclass(frozen=True)
class SectionEditOutput:
    final_content: str
    adopted: bool = False
    trace: dict = field(default_factory=dict)


class SectionEditor:
    """One conservative edit pass followed by a fact-preservation verdict."""

    async def edit(
        self,
        *,
        parts: list[str],
        combined_text: str,
        novel_title: str = "",
        style_contract: str = "",
        protected_terms: list[str] | None = None,
        verify: bool = True,
    ) -> SectionEditOutput:
        clean_parts = [p.strip() for p in parts if p and p.strip()]
        seam_report = section_seam_report(clean_parts)
        trace: dict = {
            "attempted": False,
            "adopted": False,
            "part_count": len(clean_parts),
            "original_chars": len(combined_text),
            "seam_report_before": seam_report.to_dict(),
        }
        if len(clean_parts) < 2 or len(combined_text.strip()) < 400:
            trace["skip_reason"] = "needs_at_least_two_substantial_parts"
            return SectionEditOutput(combined_text, trace=trace)

        trace["attempted"] = True
        protected = sorted(
            {
                term.strip()
                for term in (protected_terms or [])
                if len(term.strip()) >= 2 and combined_text.count(term.strip()) >= 2
            }
        )
        parts_dump = "\n\n".join(
            f"<PART_{idx}>\n{part}\n</PART_{idx}>"
            for idx, part in enumerate(clean_parts, 1)
        )
        style_note = style_contract.strip() or "保持原稿已经形成的叙述风格。"
        prompt = f"""\
作品：{novel_title or '(未命名)'}

你收到的是同一节小说按时间顺序生成的多个片段。请把它编辑成可以连续阅读的
完整一节。片段标签不是正文。

编辑权限：
1. 删除后片段对前片段已经完成动作、倒计时、物件取得和场景介绍的重复演绎。
2. 补最少量过渡词，统一视点、称谓、时态和段落节奏。
3. 可合并重复句、调整段落边界；不得把多个不同事件误合并。
4. 编辑前先在心里建立逐片段状态表：每个人的伤势及部位、存亡、所在地点、
   手中物品及数量、物资的交易/使用/消耗、已经知道的事实。前段已经明确的
   状态持续有效，直到后文出现改变它的具体事件。若后片段无事件依据却把
   伤势/物品/位置转给另一个人，或让已交付、用完、损坏的物资无故恢复，
   修正后片段使其恢复到已确立状态，并在 continuity_repairs 里列出依据。

绝对禁止：
1. 新增、删除或改变事件结果、人物决定、伤势、物品归属、地点、数字和知识边界。
   例外仅限上一条所述的“修复后段无依据漂移”，它是恢复原有事实，不是创作新事实。
2. 改变因果顺序；把后果写到原因之前；让死者复活或让角色瞬移。
3. 为了“更完整”自行补结局、解释谜底或制造新伏笔。
4. 输出编辑说明、PART/tick/素材等系统词。

风格约束：
{style_note}

必须保留的反复出现实体：{json.dumps(protected, ensure_ascii=False)}
接缝诊断：{json.dumps(seam_report.to_dict(), ensure_ascii=False)}

原始片段：
{parts_dump}

严格输出 JSON：
{{"final_content":"完整连续正文","removed_replays":["删除了什么重复"],"continuity_repairs":["把后段错误归到林雪的肋伤恢复为前段已确立的苏默肋伤"],"fact_changes":[],"residual_risks":[]}}
fact_changes 只要非空，候选就会被拒绝。不要解释。
"""
        try:
            resp = await llm_client.chat(
                system_prompt=(
                    "你是严谨的中文长篇小说责任编辑，只处理跨片段接缝。"
                    "事实守恒优先于文采，严格输出 JSON。"
                ),
                user_prompt=prompt,
                temperature=0.2,
                max_tokens=min(9000, max(2600, len(combined_text) * 2)),
                agent_id="section_editor",
                priority="medium",
            )
            payload = parse_llm_json(resp.content)
            candidate = str(payload.get("final_content", "") or "").strip()
            trace["removed_replays"] = list(payload.get("removed_replays", []) or [])
            trace["continuity_repairs"] = list(
                payload.get("continuity_repairs", []) or []
            )
            trace["self_reported_fact_changes"] = list(
                payload.get("fact_changes", []) or []
            )
            trace["residual_risks"] = list(payload.get("residual_risks", []) or [])
        except Exception as exc:
            logger.warning("SectionEditor edit failed (raw section kept): %s", exc)
            trace["error"] = str(exc)[:240]
            return SectionEditOutput(combined_text, trace=trace)

        candidate, leaked = strip_reasoning_leak(candidate)
        ratio = len(candidate) / max(1, len(combined_text))
        trace["candidate_chars"] = len(candidate)
        trace["length_ratio"] = round(ratio, 4)
        trace["reasoning_leak"] = leaked
        failed_terms = [term for term in protected if term not in candidate]
        trace["missing_protected_terms"] = failed_terms
        meta_hits = [marker for marker in _META_MARKERS if marker in candidate]
        trace["meta_hits"] = meta_hits

        if (
            not candidate
            or leaked
            or not 0.55 <= ratio <= 1.12
            or failed_terms
            or meta_hits
            or trace["self_reported_fact_changes"]
        ):
            trace["reject_reason"] = "deterministic_guard_failed"
            return SectionEditOutput(combined_text, trace=trace)

        if verify:
            verdict = await self._verify(
                original=combined_text,
                candidate=candidate,
                protected_terms=protected,
                declared_repairs=trace["continuity_repairs"],
            )
            trace["verifier"] = verdict
            if not verdict.get("safe", False):
                repairable = bool(
                    verdict.get("original_contradictions")
                    or verdict.get("residual_contradictions")
                ) and not any(
                    verdict.get(key)
                    for key in (
                        "fact_changes",
                        "causal_changes",
                        "knowledge_violations",
                    )
                )
                if repairable:
                    trace["repair_attempted"] = True
                    repaired, repair_payload = await self._repair_contradictions(
                        original=combined_text,
                        candidate=candidate,
                        verdict=verdict,
                        style_contract=style_note,
                    )
                    trace["repair_declared"] = list(
                        repair_payload.get("continuity_repairs", []) or []
                    )
                    repaired, repair_leaked = strip_reasoning_leak(repaired)
                    repair_ratio = len(repaired) / max(1, len(combined_text))
                    repair_missing = [
                        term for term in protected if term not in repaired
                    ]
                    repair_meta = [
                        marker for marker in _META_MARKERS if marker in repaired
                    ]
                    repair_guard_ok = bool(repaired) and (
                        not repair_leaked
                        and 0.55 <= repair_ratio <= 1.12
                        and not repair_missing
                        and not repair_meta
                        and not list(repair_payload.get("fact_changes", []) or [])
                    )
                    trace["repair_guard"] = {
                        "candidate_chars": len(repaired),
                        "length_ratio": round(repair_ratio, 4),
                        "reasoning_leak": repair_leaked,
                        "missing_protected_terms": repair_missing,
                        "meta_hits": repair_meta,
                        "passed": repair_guard_ok,
                    }
                    if repair_guard_ok:
                        repair_verdict = await self.verify_fact_preservation(
                            original=combined_text,
                            candidate=repaired,
                            protected_terms=protected,
                            declared_repairs=trace["repair_declared"],
                        )
                        trace["repair_verifier"] = repair_verdict
                        if repair_verdict.get("safe", False):
                            candidate = repaired
                            trace["continuity_repairs"].extend(
                                trace["repair_declared"]
                            )
                        else:
                            trace["reject_reason"] = (
                                "continuity_repair_verification_failed"
                            )
                            return SectionEditOutput(combined_text, trace=trace)
                    else:
                        trace["reject_reason"] = "continuity_repair_guard_failed"
                        return SectionEditOutput(combined_text, trace=trace)
                else:
                    trace["reject_reason"] = "semantic_fact_guard_failed"
                    return SectionEditOutput(combined_text, trace=trace)

        candidate_paragraphs = [
            paragraph for paragraph in candidate.split("\n\n") if paragraph.strip()
        ]
        after_report = section_seam_report(candidate_paragraphs)
        trace["seam_report_after"] = after_report.to_dict()
        if after_report.requires_edit:
            trace["reject_reason"] = "high_confidence_replay_survived"
            return SectionEditOutput(combined_text, trace=trace)
        trace["adopted"] = True
        return SectionEditOutput(candidate, adopted=True, trace=trace)

    async def verify_fact_preservation(
        self,
        *,
        original: str,
        candidate: str,
        protected_terms: list[str],
        declared_repairs: list[str],
    ) -> dict:
        try:
            resp = await llm_client.chat(
                system_prompt=(
                    "你是小说事实审校员。只比较事实、因果顺序、角色知识与物品归属，"
                    "不按文采打分。严格输出 JSON。"
                ),
                user_prompt=f"""\
【原始拼接稿】
{original}

【编辑候选】
{candidate}

受保护实体：{json.dumps(protected_terms, ensure_ascii=False)}
编辑器声明的连续性修复：{json.dumps(declared_repairs, ensure_ascii=False)}

先独立检查原始拼接稿内部是否有状态矛盾：尤其逐人核对伤势部位、存亡、地点、
物品归属与数量、交易/使用/消耗记录和知识。已经交付、用完、损坏的物资不得
无事件依据恢复数量。前段明确状态持续到有具体改变事件为止。候选允许删除重复演绎，
也允许把后段无事件依据的状态漂移恢复为前段已确立状态；除此之外不得新增/删除/
改变独立事件、结果、决定、伤势、死亡、地点、物品、数字、知识或因果顺序。
若候选只为修复一条已列入 original_contradictions 的硬矛盾，而对同一个低层状态
细节作最小且全篇一致的替换（例如把受伤者无法使用的藏物位置统一改为其背心内袋，
持有者、取得时机、交付结果都不变），列入 allowed_repair_changes，不列 fact_changes。
删除独立成行的 text/markdown/代码围栏也不算事实变化。只有无修复依据的新人物、
新物品、新决定、新结果、持有者改变或因果改变才列 fact_changes。
即使候选与原稿一字不差，只要原稿存在未修复矛盾，也必须 safe=false。
严格输出：
{{"safe":true,"original_contradictions":[],"repaired_contradictions":[],"allowed_repair_changes":[],"residual_contradictions":[],"fact_changes":[],"causal_changes":[],"knowledge_violations":[],"reason":"一句话"}}
只要 residual_contradictions / fact_changes / causal_changes / knowledge_violations 任一非空，safe 必须为 false。
""",
                temperature=0.0,
                max_tokens=900,
                agent_id="section_editor_verifier",
                priority="medium",
            )
            payload = parse_llm_json(resp.content)
        except Exception as exc:
            logger.warning("SectionEditor verifier failed (candidate rejected): %s", exc)
            return {"safe": False, "error": str(exc)[:240]}

        fact_changes = list(payload.get("fact_changes", []) or [])
        causal_changes = list(payload.get("causal_changes", []) or [])
        knowledge = list(payload.get("knowledge_violations", []) or [])
        original_contradictions = list(
            payload.get("original_contradictions", []) or []
        )
        repaired = list(payload.get("repaired_contradictions", []) or [])
        allowed_repairs = list(payload.get("allowed_repair_changes", []) or [])
        residual = list(payload.get("residual_contradictions", []) or [])
        safe = bool(payload.get("safe")) and not (
            residual or fact_changes or causal_changes or knowledge
        )
        return {
            "safe": safe,
            "original_contradictions": original_contradictions,
            "repaired_contradictions": repaired,
            "allowed_repair_changes": allowed_repairs,
            "residual_contradictions": residual,
            "fact_changes": fact_changes,
            "causal_changes": causal_changes,
            "knowledge_violations": knowledge,
            "reason": str(payload.get("reason", "") or "")[:240],
        }

    async def _repair_contradictions(
        self,
        *,
        original: str,
        candidate: str,
        verdict: dict,
        style_contract: str,
    ) -> tuple[str, dict]:
        """把 verifier 已经定位的原稿矛盾退回给一次外科式修复。"""
        try:
            resp = await llm_client.chat(
                system_prompt=(
                    "你是小说连续性修复编辑。只修复已定位的状态矛盾，"
                    "不润色、不扩写、不改变独立事件。严格输出 JSON。"
                ),
                user_prompt=f"""\
【原始拼接稿】
{original}

【首次编辑候选】
{candidate}

【事实审校定位】
{json.dumps(verdict, ensure_ascii=False)}

【风格契约】
{style_contract}

以原始拼接稿的早期明确状态为准，只改后文中无事件依据的漂移。
若物资已交付/用完/损坏，后文不得让它恢复；若伤势已建立，
后文不得转给他人或无故消失。不得修改前文来为后文圆谎。
严格输出：
{{"final_content":"完整正文","continuity_repairs":["修了什么"],"fact_changes":[]}}
""",
                temperature=0.0,
                max_tokens=min(9000, max(2600, len(original) * 2)),
                agent_id="section_editor_continuity_repair",
                priority="medium",
            )
            payload = parse_llm_json(resp.content)
            return str(payload.get("final_content", "") or "").strip(), payload
        except Exception as exc:
            logger.warning("SectionEditor continuity repair failed: %s", exc)
            return "", {"error": str(exc)[:240]}

    # 保留旧的私有入口，避免下游测试/扩展在迁移期间断裂。
    async def _verify(self, **kwargs) -> dict:
        return await self.verify_fact_preservation(**kwargs)


__all__ = ["SectionEditOutput", "SectionEditor"]
