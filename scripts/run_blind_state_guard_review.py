"""Run one isolated external-model review over a blind StateGuard packet.

The provider secret is loaded inside the client and is never printed or persisted.
The script accepts only the blind packet; it has no blind-key argument or key-loading
code.  One valid review artifact is written atomically per invocation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.state_guard_review_workflow import (  # noqa: E402
    CASE_RESULT_SCHEMA,
    PART_SCHEMA,
    atomic_write_json,
    create_task_checkpoint,
    load_blind_packet,
    load_task,
    merge_review_parts,
    now_utc,
    stable_hash as workflow_hash,
    validate_model_case_result,
    validate_task_index,
    write_task_index,
)


ALLOWED_ERROR_TYPES = (
    "event_endpoint_unfulfilled",
    "location_mismatch",
    "item_holder_conflict",
    "item_condition_conflict",
    "knowledge_leak",
    "new_ungrounded_fact",
    "ledger_wrong_type",
    "ledger_missing_field",
    "repair_fact_change",
    "evidence_extraction_failure",
    "reasonable_omission",
)

SYSTEM_PROMPT = """你是隔离的小说事实审查者，只看盲包，不得索取或推断系统决定、verifier、fixture 标签、实验假设或 key。逐例检查必达终态、无来源变化、ledger 与结尾、知识越权、repair 改删增事实。无合法变化时前态持续；撒谎/传闻不覆盖客观事实；typed ledger 不能替代正文；证据不足用 ambiguous；坏 repair 必须 reject。
只返回 JSON：{"r":[[case_id,"a|r|u",[error_type],confidence,"简短中文理由"],...]}。a=accept,r=reject,u=ambiguous。覆盖全部 case_id 且保持顺序。error_type 只能取：
""" + ", ".join(ALLOWED_ERROR_TYPES)


class InvalidReviewResponse(ValueError):
    def __init__(self, message: str, failure_payload: dict[str, Any]):
        super().__init__(message)
        self.failure_payload = failure_payload


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _load_provider_config(
    *,
    provider_file: Path | None,
    env_prefix: str | None,
    env_file: Path | None,
    model_override: str | None,
) -> tuple[str, str, str]:
    if bool(provider_file) == bool(env_prefix):
        raise ValueError("choose exactly one of --provider-file or --env-prefix")
    if provider_file:
        values = _parse_assignments(provider_file)
        base_url = values.get("URL") or values.get("BASE_URL") or ""
        api_key = values.get("KEY") or values.get("API_KEY") or ""
        model = model_override or values.get("MODEL") or ""
    else:
        values = _parse_assignments(env_file) if env_file else {}
        prefix = str(env_prefix or "").upper()
        base_url = os.getenv(f"{prefix}_BASE_URL") or values.get(
            f"{prefix}_BASE_URL", ""
        )
        api_key = os.getenv(f"{prefix}_API_KEY") or values.get(
            f"{prefix}_API_KEY", ""
        )
        model = model_override or os.getenv(f"{prefix}_MODEL") or values.get(
            f"{prefix}_MODEL", ""
        )
    if not base_url or not api_key or not model:
        raise ValueError("provider URL, key, and model must all be configured")
    return base_url, api_key, model


def estimate_tokens(text: str) -> int:
    """Conservative tokenizer-free estimate for mixed Chinese/JSON prompts."""

    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    remaining = len(text) - cjk
    return cjk + math.ceil(remaining / 3.2)


def compact_packet_for_prompt(packet: dict[str, Any]) -> dict[str, Any]:
    """Deduplicate repeated state/context without removing reviewer evidence."""

    catalogs: dict[str, dict[str, Any]] = {
        "states": {},
        "locations": {},
        "knowledge": {},
    }
    lookup: dict[str, dict[str, str]] = {name: {} for name in catalogs}

    def reference(catalog_name: str, value: Any) -> str:
        digest = _stable_hash(value)
        existing = lookup[catalog_name].get(digest)
        if existing:
            return existing
        prefix = {"states": "S", "locations": "L", "knowledge": "K"}[
            catalog_name
        ]
        ref = f"{prefix}{len(catalogs[catalog_name]) + 1:03d}"
        catalogs[catalog_name][ref] = value
        lookup[catalog_name][digest] = ref
        return ref

    cases: list[dict[str, Any]] = []
    questions: list[str] = []
    for case in packet.get("cases") or []:
        if not questions:
            questions = list(case.get("questions") or [])
        repairs = [
            {
                "round": repair.get("round"),
                "prose": repair.get("prose"),
                "declared_ledger_ref": reference(
                    "states", repair.get("declared_ledger") or {}
                ),
            }
            for repair in case.get("repair_attempts") or []
        ]
        cases.append(
            {
                "case_id": case.get("case_id"),
                "previous_state_ref": reference(
                    "states", case.get("previous_state") or {}
                ),
                "required_end_states": case.get("required_end_states") or [],
                "prose": case.get("prose") or "",
                "declared_ledger_ref": reference(
                    "states", case.get("declared_ledger") or {}
                ),
                "repair_attempts": repairs,
                "location_relations_ref": reference(
                    "locations", case.get("location_relations") or []
                ),
                "knowledge_boundaries_ref": reference(
                    "knowledge", case.get("knowledge_boundaries") or []
                ),
            }
        )
    return {
        "schema_version": packet.get("schema_version"),
        "packet_id": packet.get("packet_id"),
        "packet_sha256": packet.get("packet_sha256"),
        "reviewer_instructions": packet.get("reviewer_instructions"),
        "reference_rule": (
            "每个 *_ref 必须在对应 catalog 中解析；引用只是无损去重，不代表标签。"
        ),
        "questions": questions,
        "catalogs": catalogs,
        "case_count": len(cases),
        "cases": cases,
    }


def _json_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _render_state(value: dict[str, Any]) -> str:
    if not isinstance(value, dict) or not (
        "characters" in value or "items" in value
    ):
        return _json_compact(value)
    parts = [f"v={value.get('schema_version', '-')}", f"t={value.get('time_marker', '-')}"]
    characters = []
    for character_id, character in (value.get("characters") or {}).items():
        fields = [
            f"loc={character.get('location_id', '-')}",
            f"move={character.get('movement_status', '-')}",
            f"alive={character.get('alive_status', '-')}",
            f"inj={_json_compact(character.get('injuries') or [])}",
            f"support={_json_compact(character.get('supporting_character_ids') or [])}",
            f"carried_by={character.get('carried_by_character_id', '-')}",
            f"know={_json_compact(character.get('knowledge_fact_ids') or [])}",
        ]
        characters.append(f"{character_id}({';'.join(fields)})")
    items = []
    for item_id, item in (value.get("items") or {}).items():
        fields = [
            f"holders={_json_compact(item.get('holder_character_ids') or [])}",
            f"loc={item.get('location_id', '-')}",
            f"qty={item.get('quantity', '-')}",
            f"cond={item.get('condition', '-')}",
            f"box={item.get('container_item_id', '-')}",
        ]
        items.append(f"{item_id}({';'.join(fields)})")
    parts.extend(
        [
            "C=" + "|".join(characters),
            "I=" + "|".join(items),
            "new=" + _json_compact(value.get("newly_known_fact_ids") or {}),
            "loops=" + _json_compact(value.get("active_open_loop_ids") or []),
        ]
    )
    return ";".join(parts)


def render_packet_for_prompt(packet: dict[str, Any]) -> str:
    """Render a lossless compact reference table for low-budget review calls."""

    compact = compact_packet_for_prompt(packet)
    lines = [
        f"packet={compact['packet_id']} hash={compact['packet_sha256']}",
        "REF: *_ref 指向下列 catalog，仅为去重，不是标签。",
        "Q=" + _json_compact(compact["questions"]),
    ]
    for ref, state in compact["catalogs"]["states"].items():
        lines.append(f"{ref}={_render_state(state)}")
    for ref, locations in compact["catalogs"]["locations"].items():
        lines.append(f"{ref}={_json_compact(locations)}")
    for ref, knowledge in compact["catalogs"]["knowledge"].items():
        lines.append(f"{ref}={_json_compact(knowledge)}")
    for case in compact["cases"]:
        repairs = [
            [
                repair.get("round"),
                repair.get("prose"),
                repair.get("declared_ledger_ref"),
            ]
            for repair in case.get("repair_attempts") or []
        ]
        lines.append(
            "CASE="
            + _json_compact(
                [
                    case.get("case_id"),
                    case.get("previous_state_ref"),
                    case.get("required_end_states"),
                    case.get("prose"),
                    case.get("declared_ledger_ref"),
                    repairs,
                    case.get("location_relations_ref"),
                    case.get("knowledge_boundaries_ref"),
                ]
            )
        )
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("reviewer did not return a JSON object") from None
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("reviewer response must be a JSON object")
    return payload


def _validate_results(
    payload: dict[str, Any], packet_case_ids: list[str]
) -> list[dict[str, Any]]:
    results = payload.get("results")
    if results is None and isinstance(payload.get("r"), list):
        decision_map = {"a": "accept", "r": "reject", "u": "ambiguous"}
        results = []
        for row in payload["r"]:
            if not isinstance(row, list) or len(row) != 5:
                raise ValueError("compact review rows must have five fields")
            results.append(
                {
                    "case_id": row[0],
                    "decision": decision_map.get(str(row[1]), str(row[1])),
                    "error_types": row[2],
                    "confidence": row[3],
                    "rationale": row[4],
                }
            )
    if not isinstance(results, list):
        raise ValueError("reviewer response lacks results array")
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    allowed = set(ALLOWED_ERROR_TYPES)
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("each review result must be an object")
        case_id = str(item.get("case_id") or "")
        decision = str(item.get("decision") or "")
        error_types = item.get("error_types") or []
        rationale = str(item.get("rationale") or "").strip()
        confidence = item.get("confidence")
        if case_id in seen:
            raise ValueError(f"duplicate review case: {case_id}")
        if decision not in {"accept", "reject", "ambiguous"}:
            raise ValueError(f"invalid decision for {case_id}")
        if not isinstance(error_types, list) or any(
            str(value) not in allowed for value in error_types
        ):
            raise ValueError(f"invalid error taxonomy for {case_id}")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise ValueError(f"invalid confidence for {case_id}")
        if not 0 <= float(confidence) <= 1:
            raise ValueError(f"confidence out of range for {case_id}")
        if not rationale:
            raise ValueError(f"empty rationale for {case_id}")
        seen.add(case_id)
        validated.append(
            {
                "case_id": case_id,
                "decision": decision,
                "error_types": list(dict.fromkeys(str(value) for value in error_types)),
                "confidence": round(float(confidence), 6),
                "rationale": rationale,
            }
        )
    if [item["case_id"] for item in validated] != packet_case_ids:
        missing = sorted(set(packet_case_ids) - seen)
        extra = sorted(seen - set(packet_case_ids))
        raise ValueError(
            f"review coverage/order mismatch; missing={missing}, extra={extra}"
        )
    return validated


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.remove(temp_name)
        except OSError:
            pass
        raise


def run_review(
    *,
    packet_path: Path,
    provider_file: Path | None,
    env_prefix: str | None,
    env_file: Path | None,
    model_override: str | None,
    reviewer_id: str,
    model_family: str,
    provider_name: str,
    max_input_tokens: int,
    max_output_tokens: int,
    budget_tokens: int,
    timeout: float,
    disable_thinking: bool = False,
) -> dict[str, Any]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet_without_hash = dict(packet)
    packet_hash = packet_without_hash.pop("packet_sha256", None)
    if packet_hash != _stable_hash(packet_without_hash):
        raise ValueError("blind packet hash mismatch")
    case_ids = [str(case.get("case_id") or "") for case in packet.get("cases") or []]
    if not case_ids or len(case_ids) != len(set(case_ids)):
        raise ValueError("blind packet has missing or duplicate case IDs")
    compact_packet = render_packet_for_prompt(packet)
    user_prompt = "审查以下盲化 packet，严格返回指定 JSON：\n" + compact_packet
    input_estimate = estimate_tokens(SYSTEM_PROMPT + user_prompt)
    if input_estimate > max_input_tokens:
        raise ValueError(
            f"estimated input {input_estimate} exceeds --max-input-tokens "
            f"{max_input_tokens}"
        )
    if input_estimate + max_output_tokens > budget_tokens:
        raise ValueError("estimated request exceeds reviewer token budget")

    base_url, api_key, model = _load_provider_config(
        provider_file=provider_file,
        env_prefix=env_prefix,
        env_file=env_file,
        model_override=model_override,
    )
    started = _now()
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    try:
        request_kwargs: dict[str, Any] = {
            "model": model,
            "temperature": 0,
            "max_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        }
        if disable_thinking:
            request_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = client.chat.completions.create(**request_kwargs)
    except Exception as exc:
        finished = _now()
        failure = {
            "schema_version": "state-guard-adjudication-review-failure-v1",
            "status": "provider_request_failed",
            "packet_id": packet["packet_id"],
            "packet_hash": packet_hash,
            "reviewer_id": reviewer_id,
            "reviewer_type": "independent_model",
            "model_family": model_family,
            "model_name": model,
            "provider_name": provider_name,
            "review_started_at": started,
            "review_finished_at": finished,
            "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            "temperature": 0.0,
            "blind_key_accessed": False,
            "review_input_files": [packet_path.name],
            "usage": {
                "provider_requests": 1,
                "model_calls": 0,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "estimated_input_tokens": input_estimate,
            },
            "raw_response_sha256": None,
            "raw_response": None,
            "error_type": type(exc).__name__,
            "http_status": getattr(exc, "status_code", None),
            "validation_error": "provider request failed before a model response",
        }
        failure["failure_sha256"] = _stable_hash(failure)
        raise InvalidReviewResponse(failure["validation_error"], failure) from exc
    finished = _now()
    content = response.choices[0].message.content or ""
    usage = response.usage
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    response_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if total_tokens > budget_tokens:
        failure = {
            "schema_version": "state-guard-adjudication-review-failure-v1",
            "status": "reviewer_budget_exceeded",
            "packet_id": packet["packet_id"],
            "packet_hash": packet_hash,
            "reviewer_id": reviewer_id,
            "reviewer_type": "independent_model",
            "model_family": model_family,
            "model_name": model,
            "provider_name": provider_name,
            "review_started_at": started,
            "review_finished_at": finished,
            "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            "temperature": 0.0,
            "blind_key_accessed": False,
            "review_input_files": [packet_path.name],
            "usage": {
                "provider_calls": 1,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "estimated_input_tokens": input_estimate,
                "budget_tokens": budget_tokens,
            },
            "raw_response_sha256": response_hash,
            "raw_response": content,
            "validation_error": "provider-reported usage exceeds reviewer token budget",
        }
        failure["failure_sha256"] = _stable_hash(failure)
        raise InvalidReviewResponse(failure["validation_error"], failure)
    try:
        results = _validate_results(_extract_json(content), case_ids)
    except (ValueError, json.JSONDecodeError) as exc:
        failure = {
            "schema_version": "state-guard-adjudication-review-failure-v1",
            "status": "invalid_reviewer_response",
            "packet_id": packet["packet_id"],
            "packet_hash": packet_hash,
            "reviewer_id": reviewer_id,
            "reviewer_type": "independent_model",
            "model_family": model_family,
            "model_name": model,
            "provider_name": provider_name,
            "review_started_at": started,
            "review_finished_at": finished,
            "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            "temperature": 0.0,
            "blind_key_accessed": False,
            "review_input_files": [packet_path.name],
            "usage": {
                "provider_calls": 1,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "estimated_input_tokens": input_estimate,
            },
            "raw_response_sha256": response_hash,
            "raw_response": content,
            "validation_error": str(exc),
        }
        failure["failure_sha256"] = _stable_hash(failure)
        raise InvalidReviewResponse(str(exc), failure) from exc
    review = {
        "schema_version": "state-guard-adjudication-review-v2",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet_hash,
        "packet_hash": packet_hash,
        "reviewer_id": reviewer_id,
        "reviewer_type": "independent_model",
        "model_family": model_family,
        "model_name": model,
        "provider_name": provider_name,
        "review_started_at": started,
        "review_finished_at": finished,
        "prompt_hash": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "temperature": 0.0,
        "blind_key_accessed": False,
        "review_input_files": [packet_path.name],
        "usage": {
            "provider_calls": 1,
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_input_tokens": input_estimate,
        },
        "raw_response_sha256": response_hash,
        "results": results,
    }
    return review


SHARDED_SYSTEM_PROMPT = """你是隔离的小说事实一致性审查者。只依据当前盲化任务作答，不得索取或推断 blind key、expected label、fixture 类型、verifier、baseline/candidate 决定或其他 reviewer 答案。不要重复正文、输出 Markdown 或长篇分析。

每个结果只返回 case_id、五个布尔判断、decision、error_types、confidence 和一句简短理由。布尔字段不得省略。decision 只能是 accept、reject、ambiguous。error_types 只能取：""" + ", ".join(ALLOWED_ERROR_TYPES)

PROBE_SYSTEM_PROMPT = """这是连接能力探针，不是审查任务。请只返回 JSON，不要分析。不得要求或处理任何小说、blind case、case ID 或隐藏标签。"""
PROBE_USER_PROMPT = """返回 {"probe":"ok","json_supported":true,"length_probe":"0123456789abcdef0123456789abcdef"}。"""


def build_probe_messages() -> list[dict[str, str]]:
    """Return a synthetic capability probe containing no blind-case material."""

    return [
        {"role": "system", "content": PROBE_SYSTEM_PROMPT},
        {"role": "user", "content": PROBE_USER_PROMPT},
    ]


def _single_case_schema() -> dict[str, Any]:
    return {
        "case_id": "opaque-id",
        "endpoint_complete": True,
        "ungrounded_change": False,
        "ledger_matches": True,
        "knowledge_leak": False,
        "repair_changed_fact": False,
        "decision": "accept",
        "error_types": [],
        "confidence": 0.9,
        "rationale": "简短事实依据。",
    }


def build_task_messages(
    task: dict[str, Any],
    *,
    case_ids: list[str] | None = None,
    retry_error_type: str | None = None,
) -> list[dict[str, str]]:
    selected_ids = set(case_ids or task["case_ids"])
    cases = [case for case in task["cases"] if case["case_id"] in selected_ids]
    if not cases or len(cases) != len(selected_ids):
        raise ValueError("retry case selection does not match review task")
    payload = {
        "packet_hash": task["packet_hash"],
        "task_id": task["task_id"],
        "questions": task["questions"],
        "cases": cases,
        "response_schema": (
            _single_case_schema()
            if len(cases) == 1
            else {"results": [_single_case_schema()]}
        ),
    }
    if retry_error_type:
        payload["format_retry"] = {
            "previous_error_type": retry_error_type,
            "instruction": "只修复响应格式；重新独立审查当前案例。",
        }
    text_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    forbidden = (
        "expected_final_decision",
        "baseline_decision",
        "candidate_decision",
        "verifier_safe",
        "blind-key",
    )
    if any(marker in text_payload.casefold() for marker in forbidden):
        raise ValueError("sharded review prompt contains forbidden label material")
    return [
        {"role": "system", "content": SHARDED_SYSTEM_PROMPT},
        {"role": "user", "content": text_payload},
    ]


def validate_probe_reply(reply: dict[str, Any]) -> dict[str, Any]:
    content = str(reply.get("content") or "")
    final_present = bool(content.strip())
    json_supported = False
    if final_present:
        try:
            payload = _extract_json(content)
            json_supported = (
                payload.get("probe") == "ok"
                and payload.get("json_supported") is True
                and bool(payload.get("length_probe"))
            )
        except ValueError:
            json_supported = False
    usage = reply.get("usage") or {}
    usage_reported = all(
        isinstance(usage.get(name), int)
        for name in ("input_tokens", "output_tokens", "total_tokens")
    )
    result = {
        "schema_version": "state-guard-review-provider-probe-v1",
        "authenticated": True,
        "final_content_present": final_present,
        "json_supported": json_supported,
        "usage_reported": usage_reported,
        "reasoning_field_present": bool(reply.get("reasoning_field_present")),
        "recommended_batch_size": 1,
        "recommended_max_output_tokens": 800,
        "passed": final_present and json_supported,
        "usage": usage,
    }
    result["probe_sha256"] = workflow_hash(result)
    return result


def _extract_task_results(
    content: str, expected_case_ids: list[str]
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    if not content.strip():
        return {}, {case_id: "empty_final_content" for case_id in expected_case_ids}
    try:
        payload = _extract_json(content)
    except (ValueError, json.JSONDecodeError):
        return {}, {case_id: "malformed_json" for case_id in expected_case_ids}
    if len(expected_case_ids) == 1 and "results" not in payload:
        rows = [payload]
    else:
        rows = payload.get("results")
    if not isinstance(rows, list):
        return {}, {case_id: "missing_results_array" for case_id in expected_case_ids}
    supplied: dict[str, dict[str, Any]] = {}
    structural_error = False
    for row in rows:
        if not isinstance(row, dict):
            structural_error = True
            continue
        case_id = str(row.get("case_id") or "")
        if case_id in supplied:
            structural_error = True
            continue
        supplied[case_id] = row
    expected = set(expected_case_ids)
    if structural_error or set(supplied) - expected:
        return {}, {case_id: "unknown_or_duplicate_case" for case_id in expected_case_ids}
    valid: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for case_id in expected_case_ids:
        row = supplied.get(case_id)
        if row is None:
            errors[case_id] = "missing_case_result"
            continue
        try:
            valid[case_id] = validate_model_case_result(row, case_id)
        except ValueError as exc:
            errors[case_id] = type(exc).__name__ + ":" + str(exc)[:160]
    return valid, errors


def _usage_from_reply(reply: dict[str, Any]) -> tuple[dict[str, int | None], bool]:
    usage = reply.get("usage") or {}
    values = {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    known = all(isinstance(value, int) and value >= 0 for value in values.values())
    return values, known


def _account_reply(
    index: dict[str, Any],
    reply: dict[str, Any] | None,
    *,
    evidence_mode: str,
    max_input_tokens: int,
    max_output_tokens: int,
) -> dict[str, Any]:
    if evidence_mode == "provider":
        index["usage"]["provider_calls"] += 1
    else:
        index["usage"]["recorded_calls"] += 1
    if evidence_mode != "provider":
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    if reply is None:
        bound = max_input_tokens + max_output_tokens
        index["budget"]["uncertain_usage_upper_bound"] += bound
        return {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "uncertain_usage_upper_bound": bound,
        }
    values, known = _usage_from_reply(reply)
    if known:
        index["budget"]["current_run_exact_input_tokens"] += int(
            values["input_tokens"] or 0
        )
        index["budget"]["current_run_exact_output_tokens"] += int(
            values["output_tokens"] or 0
        )
        index["budget"]["current_run_exact_usage"] += int(values["total_tokens"] or 0)
        return values
    bound = max_input_tokens + max_output_tokens
    index["budget"]["uncertain_usage_upper_bound"] += bound
    return {
        **values,
        "uncertain_usage_upper_bound": bound,
    }


def _budget_upper(index: dict[str, Any]) -> int:
    return int(index["budget"]["current_run_exact_usage"]) + int(
        index["budget"]["uncertain_usage_upper_bound"]
    )


def _refresh_budget_flags(index: dict[str, Any]) -> None:
    authorized = int(index["budget"]["new_authorized_budget"])
    upper = _budget_upper(index)
    index["budget"]["provider_calls_allowed"] = authorized > 0 and upper < authorized
    if authorized <= 0:
        index["budget"]["warning_70_percent"] = False
        index["budget"]["stop_opening_new_cases_85_percent"] = True
        return
    ratio = upper / authorized
    index["budget"]["warning_70_percent"] = ratio >= 0.70
    index["budget"]["stop_opening_new_cases_85_percent"] = ratio >= 0.85


def _can_open_call(
    index: dict[str, Any], *, max_input_tokens: int, max_output_tokens: int
) -> bool:
    _refresh_budget_flags(index)
    authorized = int(index["budget"]["new_authorized_budget"])
    if authorized <= 0 or index["budget"]["stop_opening_new_cases_85_percent"]:
        return False
    conservative_next = _budget_upper(index) + max_input_tokens + max_output_tokens
    return conservative_next <= authorized


def _checkpoint_failure(
    checkpoint_dir: Path,
    *,
    task_id: str,
    attempt: int,
    case_ids: list[str],
    error_type: str,
    reply: dict[str, Any] | None,
    usage: dict[str, Any],
) -> str:
    failure = {
        "schema_version": "state-guard-sharded-review-failure-v1",
        "task_id": task_id,
        "attempt": attempt,
        "case_ids": case_ids,
        "error_type": error_type,
        "raw_response": (reply or {}).get("content"),
        "raw_response_sha256": hashlib.sha256(
            str((reply or {}).get("content") or "").encode("utf-8")
        ).hexdigest(),
        "usage": usage,
        "created_at": now_utc(),
    }
    failure["failure_sha256"] = workflow_hash(failure)
    case_tag = workflow_hash(case_ids)[:8]
    relative = f"failures/{task_id}-{case_tag}-attempt-{attempt:02d}.json"
    atomic_write_json(checkpoint_dir / relative, failure)
    return relative


def _write_completed_case(
    checkpoint_dir: Path,
    *,
    index: dict[str, Any],
    task: dict[str, Any],
    result: dict[str, Any],
    evidence_mode: str,
    attempt: int,
    response_sha256: str,
    usage: dict[str, Any],
) -> str:
    case_id = result["case_id"]
    payload = {
        "schema_version": CASE_RESULT_SCHEMA,
        "packet_id": index["packet_id"],
        "packet_hash": index["packet_hash"],
        "task_id": task["task_id"],
        "task_sha256": task["task_sha256"],
        "reviewer_id": index["reviewer_id"],
        "reviewer_type": index["reviewer_type"],
        "evidence_mode": evidence_mode,
        "case_id": case_id,
        "attempt": attempt,
        "response_sha256": response_sha256,
        "usage": usage,
        "completed_at": now_utc(),
        "result": result,
    }
    payload["result_sha256"] = workflow_hash(payload)
    relative = f"completed/{case_id}.json"
    atomic_write_json(checkpoint_dir / relative, payload)
    return relative


def _validate_completed_case(
    path: Path,
    *,
    packet_hash: str,
    reviewer_id: str,
    case_id: str,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CASE_RESULT_SCHEMA:
        raise ValueError("unsupported completed-case schema")
    without_hash = dict(payload)
    stored = without_hash.pop("result_sha256", None)
    if stored != workflow_hash(without_hash):
        raise ValueError("completed-case hash mismatch")
    if payload.get("packet_hash") != packet_hash:
        raise ValueError("completed-case packet hash mismatch")
    if payload.get("reviewer_id") != reviewer_id:
        raise ValueError("completed-case reviewer mismatch")
    validate_model_case_result(payload["result"], case_id)
    return payload


def _make_partial_from_checkpoint(
    checkpoint_dir: Path,
    index: dict[str, Any],
    *,
    evidence_mode: str,
    model_family: str,
    model_name: str,
    provider_name: str,
) -> Path | None:
    results: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for row in index["tasks"]:
        for case_id in row["case_ids"]:
            relative = row.get("result_paths", {}).get(case_id)
            if not relative:
                continue
            payload = _validate_completed_case(
                checkpoint_dir / relative,
                packet_hash=index["packet_hash"],
                reviewer_id=index["reviewer_id"],
                case_id=case_id,
            )
            results.append(payload["result"])
            sources.append(
                {
                    "case_id": case_id,
                    "result_path": relative,
                    "result_sha256": payload["result_sha256"],
                }
            )
    if not results:
        return None
    part = {
        "schema_version": PART_SCHEMA,
        "packet_id": index["packet_id"],
        "packet_hash": index["packet_hash"],
        "reviewer_id": index["reviewer_id"],
        "reviewer_type": index["reviewer_type"],
        "evidence_mode": evidence_mode,
        "model_family": model_family,
        "model_name": model_name,
        "provider_name": provider_name,
        "blind_key_accessed": False,
        "review_started_at": index["created_at"],
        "review_finished_at": now_utc(),
        "source": {"checkpoint_definition_sha256": index["definition_sha256"], "cases": sources},
        "results": results,
        "usage": {
            "provider_calls": index["usage"]["provider_calls"],
            "input_tokens": index["budget"].get("current_run_exact_input_tokens", 0),
            "output_tokens": index["budget"].get("current_run_exact_output_tokens", 0),
            "total_tokens": index["budget"]["current_run_exact_usage"],
            "uncertain_usage_upper_bound": index["budget"]["uncertain_usage_upper_bound"],
        },
    }
    part["part_id"] = f"part-{workflow_hash(part)[:16]}"
    part["part_sha256"] = workflow_hash(part)
    path = checkpoint_dir / "parts" / "checkpoint-part.json"
    atomic_write_json(path, part)
    return path


def execute_sharded_checkpoint(
    checkpoint_dir: Path,
    *,
    call_fn: Any | None,
    evidence_mode: str,
    authorized_budget: int,
    max_calls: int,
    max_input_tokens: int,
    max_output_tokens: int,
    retry_invalid: bool,
    resume: bool,
    probe_only: bool = False,
    model_family: str = "",
    model_name: str = "",
    provider_name: str = "",
    out_review: Path | None = None,
    out_coverage: Path | None = None,
) -> tuple[dict[str, Any], int]:
    index_path = checkpoint_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    validate_task_index(index)
    if resume:
        index["resume_count"] += 1
    index["budget"]["new_authorized_budget"] = int(authorized_budget)
    _refresh_budget_flags(index)
    if evidence_mode == "provider" and authorized_budget <= 0:
        index["run_status"] = "budget_blocked"
        for row in index["tasks"]:
            if row["status"] != "complete":
                row["status"] = "budget_blocked"
        write_task_index(index_path, index)
        return index, 3
    if evidence_mode not in {"provider", "recorded", "mock"}:
        raise ValueError("unsupported sharded runner evidence mode")
    if call_fn is None:
        raise ValueError("call_fn is required when execution is authorized")

    # Provider mode must pass one synthetic probe before any blind task is opened.
    if evidence_mode == "provider":
        probe_path = checkpoint_dir / "probe.json"
        probe_ok = False
        if resume and probe_path.exists():
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            probe_ok = bool(probe.get("passed"))
        if not probe_ok:
            if index["usage"]["provider_calls"] >= max_calls or not _can_open_call(
                index,
                max_input_tokens=max_input_tokens,
                max_output_tokens=min(max_output_tokens, 300),
            ):
                index["run_status"] = "budget_blocked"
                write_task_index(index_path, index)
                return index, 3
            try:
                reply = call_fn(build_probe_messages(), min(max_output_tokens, 300))
                usage = _account_reply(
                    index,
                    reply,
                    evidence_mode=evidence_mode,
                    max_input_tokens=max_input_tokens,
                    max_output_tokens=min(max_output_tokens, 300),
                )
                probe = validate_probe_reply(reply)
                probe["usage_accounted"] = usage
                probe["created_at"] = now_utc()
                probe.pop("probe_sha256", None)
                probe["probe_sha256"] = workflow_hash(probe)
                atomic_write_json(probe_path, probe)
                if not probe["passed"]:
                    index["run_status"] = "provider_probe_failed"
                    write_task_index(index_path, index)
                    return index, 4
            except Exception as exc:
                usage = _account_reply(
                    index,
                    None,
                    evidence_mode=evidence_mode,
                    max_input_tokens=max_input_tokens,
                    max_output_tokens=min(max_output_tokens, 300),
                )
                probe = {
                    "schema_version": "state-guard-review-provider-probe-v1",
                    "authenticated": False,
                    "final_content_present": False,
                    "json_supported": False,
                    "usage_reported": False,
                    "reasoning_field_present": False,
                    "recommended_batch_size": 1,
                    "recommended_max_output_tokens": 800,
                    "passed": False,
                    "error_type": type(exc).__name__,
                    "usage_accounted": usage,
                    "created_at": now_utc(),
                }
                probe["probe_sha256"] = workflow_hash(probe)
                atomic_write_json(probe_path, probe)
                index["run_status"] = "provider_probe_failed"
                write_task_index(index_path, index)
                return index, 4

        if probe_only:
            index["run_status"] = "provider_probe_passed"
            write_task_index(index_path, index)
            return index, 0

    calls_opened = (
        index["usage"]["provider_calls"]
        if evidence_mode == "provider"
        else index["usage"]["recorded_calls"]
    )
    stop = False
    for row in index["tasks"]:
        if stop:
            break
        task = load_task(
            checkpoint_dir / row["input_path"], expected_sha256=row["input_sha256"]
        )
        pending: list[str] = []
        for case_id in row["case_ids"]:
            relative = row.get("result_paths", {}).get(case_id)
            if relative:
                _validate_completed_case(
                    checkpoint_dir / relative,
                    packet_hash=index["packet_hash"],
                    reviewer_id=index["reviewer_id"],
                    case_id=case_id,
                )
                row["case_statuses"][case_id] = "complete"
                continue
            if row["case_statuses"].get(case_id) == "needs_human_review":
                continue
            if row["status"] in {"provider_failed", "invalid"} and not retry_invalid:
                continue
            pending.append(case_id)
        if not pending:
            if all(value == "complete" for value in row["case_statuses"].values()):
                row["status"] = "complete"
            continue
        if calls_opened >= max_calls:
            index["run_status"] = "max_calls_reached"
            break
        if evidence_mode == "provider" and not _can_open_call(
            index,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
        ):
            row["status"] = "budget_blocked"
            index["run_status"] = "budget_blocked"
            stop = True
            break
        row["status"] = "running"
        for case_id in pending:
            row["case_attempts"][case_id] = row["case_attempts"].get(case_id, 0) + 1
        row["attempts"] += 1
        write_task_index(index_path, index)
        messages = build_task_messages(task, case_ids=pending)
        reply: dict[str, Any] | None = None
        try:
            reply = call_fn(messages, max_output_tokens)
            usage = _account_reply(
                index,
                reply,
                evidence_mode=evidence_mode,
                max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens,
            )
            calls_opened += 1
        except Exception as exc:
            usage = _account_reply(
                index,
                None,
                evidence_mode=evidence_mode,
                max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens,
            )
            calls_opened += 1
            row["status"] = "provider_failed"
            row["last_error"] = type(exc).__name__
            for case_id in pending:
                row["case_statuses"][case_id] = "provider_failed"
            _checkpoint_failure(
                checkpoint_dir,
                task_id=row["task_id"],
                attempt=row["attempts"],
                case_ids=pending,
                error_type=type(exc).__name__,
                reply=None,
                usage=usage,
            )
            _refresh_budget_flags(index)
            write_task_index(index_path, index)
            continue
        content = str(reply.get("content") or "")
        response_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        valid, errors = _extract_task_results(content, pending)
        for case_id, result in valid.items():
            relative = _write_completed_case(
                checkpoint_dir,
                index=index,
                task=task,
                result=result,
                evidence_mode=evidence_mode,
                attempt=row["case_attempts"][case_id],
                response_sha256=response_sha,
                usage=usage,
            )
            row["result_paths"][case_id] = relative
            row["case_statuses"][case_id] = "complete"
        retry_ids = list(errors)
        if errors:
            row["invalid_attempts"] += 1
            row["last_error"] = ";".join(sorted(set(errors.values())))[:400]
            failure_type = (
                "empty_final_content"
                if set(errors.values()) == {"empty_final_content"}
                else "invalid_response"
            )
            _checkpoint_failure(
                checkpoint_dir,
                task_id=row["task_id"],
                attempt=row["attempts"],
                case_ids=retry_ids,
                error_type=failure_type,
                reply=reply,
                usage=usage,
            )
            for case_id in retry_ids:
                row["case_statuses"][case_id] = (
                    "provider_failed" if failure_type == "empty_final_content" else "invalid"
                )
        # One local format retry per invalid case.  Valid sibling cases are never rerun.
        if retry_invalid and errors and set(errors.values()) != {"empty_final_content"}:
            for case_id in retry_ids:
                if row["case_attempts"][case_id] >= 2:
                    row["case_statuses"][case_id] = "needs_human_review"
                    continue
                if calls_opened >= max_calls:
                    break
                if evidence_mode == "provider" and not _can_open_call(
                    index,
                    max_input_tokens=max_input_tokens,
                    max_output_tokens=max_output_tokens,
                ):
                    row["case_statuses"][case_id] = "budget_blocked"
                    stop = True
                    break
                row["case_attempts"][case_id] += 1
                index["usage"]["retries"] += 1
                retry_messages = build_task_messages(
                    task,
                    case_ids=[case_id],
                    retry_error_type=errors[case_id].split(":", 1)[0],
                )
                retry_reply: dict[str, Any] | None = None
                try:
                    retry_reply = call_fn(retry_messages, max_output_tokens)
                    retry_usage = _account_reply(
                        index,
                        retry_reply,
                        evidence_mode=evidence_mode,
                        max_input_tokens=max_input_tokens,
                        max_output_tokens=max_output_tokens,
                    )
                    calls_opened += 1
                    retry_content = str(retry_reply.get("content") or "")
                    retry_valid, retry_errors = _extract_task_results(
                        retry_content, [case_id]
                    )
                    if case_id in retry_valid:
                        relative = _write_completed_case(
                            checkpoint_dir,
                            index=index,
                            task=task,
                            result=retry_valid[case_id],
                            evidence_mode=evidence_mode,
                            attempt=row["case_attempts"][case_id],
                            response_sha256=hashlib.sha256(
                                retry_content.encode("utf-8")
                            ).hexdigest(),
                            usage=retry_usage,
                        )
                        row["result_paths"][case_id] = relative
                        row["case_statuses"][case_id] = "complete"
                    else:
                        row["case_statuses"][case_id] = "needs_human_review"
                        _checkpoint_failure(
                            checkpoint_dir,
                            task_id=row["task_id"],
                            attempt=row["attempts"] + 1,
                            case_ids=[case_id],
                            error_type=next(iter(retry_errors.values())),
                            reply=retry_reply,
                            usage=retry_usage,
                        )
                except Exception as exc:
                    retry_usage = _account_reply(
                        index,
                        None,
                        evidence_mode=evidence_mode,
                        max_input_tokens=max_input_tokens,
                        max_output_tokens=max_output_tokens,
                    )
                    calls_opened += 1
                    row["case_statuses"][case_id] = "needs_human_review"
                    _checkpoint_failure(
                        checkpoint_dir,
                        task_id=row["task_id"],
                        attempt=row["attempts"] + 1,
                        case_ids=[case_id],
                        error_type=type(exc).__name__,
                        reply=None,
                        usage=retry_usage,
                    )
        statuses = set(row["case_statuses"].values())
        if statuses == {"complete"}:
            row["status"] = "complete"
            row["result_path"] = (
                next(iter(row["result_paths"].values()))
                if len(row["result_paths"]) == 1
                else None
            )
        elif "needs_human_review" in statuses:
            row["status"] = "needs_human_review"
        elif "provider_failed" in statuses:
            row["status"] = "provider_failed"
        elif "budget_blocked" in statuses:
            row["status"] = "budget_blocked"
        else:
            row["status"] = "invalid"
        _refresh_budget_flags(index)
        if evidence_mode == "provider" and index["budget"]["stop_opening_new_cases_85_percent"]:
            index["run_status"] = "budget_blocked"
            stop = True
        write_task_index(index_path, index)

    index["usage"]["completed_cases"] = sum(
        status == "complete"
        for row in index["tasks"]
        for status in row["case_statuses"].values()
    )
    if index["usage"]["completed_cases"] == sum(
        len(row["case_ids"]) for row in index["tasks"]
    ):
        index["run_status"] = "complete"
    elif index["run_status"] == "pending":
        index["run_status"] = "partial"
    write_task_index(index_path, index)
    part_path = _make_partial_from_checkpoint(
        checkpoint_dir,
        index,
        evidence_mode=evidence_mode,
        model_family=model_family,
        model_name=model_name,
        provider_name=provider_name,
    )
    if part_path and out_review:
        packet_path = checkpoint_dir / "packet.ref.json"
        # The caller writes the validated packet reference before execution.
        merged, coverage = merge_review_parts(packet_path, [part_path])
        atomic_write_json(out_review, merged)
        if out_coverage:
            atomic_write_json(out_coverage, coverage)
    return index, 0 if index["run_status"] == "complete" else 2


def _openai_reply(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    *,
    disable_thinking: bool = False,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    if disable_thinking:
        request["extra_body"] = {"thinking": {"type": "disabled"}}
    response = client.chat.completions.create(**request)
    message = response.choices[0].message
    usage = response.usage
    return {
        "content": message.content or "",
        "reasoning_field_present": bool(
            getattr(message, "reasoning_content", None)
            or getattr(message, "reasoning", None)
        ),
        "usage": {
            "input_tokens": getattr(usage, "prompt_tokens", None),
            "output_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        },
    }


def _recorded_call_factory(path: Path) -> Any:
    payload = json.loads(path.read_text(encoding="utf-8"))
    queue = list(payload.get("responses") or [])

    def call(messages: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
        del messages, max_tokens
        if not queue:
            raise RuntimeError("recorded response queue exhausted")
        value = queue.pop(0)
        if value.get("raise"):
            raise RuntimeError(str(value["raise"]))
        return {
            "content": str(value.get("content") or ""),
            "reasoning_field_present": bool(value.get("reasoning_field_present")),
            "usage": value.get("usage") or {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        }

    return call


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", nargs="?", help="legacy positional blind packet")
    parser.add_argument("--packet", dest="packet_option", help="blind packet JSON")
    parser.add_argument("--template", help="blank review template (metadata only)")
    provider = parser.add_mutually_exclusive_group()
    provider.add_argument("--provider-file")
    provider.add_argument("--env-prefix")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--model")
    parser.add_argument("--reviewer-id")
    parser.add_argument(
        "--reviewer-type",
        choices=("human", "independent_model", "project_agent"),
        default="independent_model",
    )
    parser.add_argument("--model-family", default="")
    parser.add_argument("--provider-name", default="")
    parser.add_argument("--batch-size", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--shuffle-seed", type=int, default=0)
    parser.add_argument("--max-calls", type=int, default=100)
    parser.add_argument("--max-input-tokens", type=int, default=6000)
    parser.add_argument("--max-output-tokens", type=int, default=800)
    parser.add_argument(
        "--budget-tokens",
        type=int,
        default=0,
        help="new Phase 11 authorization only; default 0 blocks providers",
    )
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--checkpoint-dir")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-invalid", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument(
        "--recorded-responses",
        help="offline response queue; produces recorded, non-independent evidence",
    )
    parser.add_argument("--out-review")
    parser.add_argument("--out", dest="out_review_alias")
    parser.add_argument("--out-coverage")
    parser.add_argument(
        "--out-failure",
        help="sanitized failed-response checkpoint (default: OUT_REVIEW.failed.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    packet_value = args.packet_option or args.packet
    sharded_mode = bool(args.checkpoint_dir or args.packet_option)
    if sharded_mode:
        if not packet_value:
            raise SystemExit("--packet is required for sharded review")
        if not args.checkpoint_dir:
            raise SystemExit("--checkpoint-dir is required for sharded review")
        if not args.reviewer_id:
            raise SystemExit("--reviewer-id is required for sharded review")
        packet_path = Path(packet_value).resolve()
        checkpoint_dir = Path(args.checkpoint_dir).resolve()
        if args.template:
            template = json.loads(Path(args.template).read_text(encoding="utf-8"))
            packet_for_template = load_blind_packet(packet_path)
            if template.get("packet_sha256") != packet_for_template["packet_sha256"]:
                raise SystemExit("--template packet hash mismatch")
            template_text = json.dumps(template, ensure_ascii=False).casefold()
            if any(
                marker in template_text
                for marker in (
                    "expected_final_decision",
                    "baseline_decision",
                    "candidate_decision",
                    "verifier_safe",
                )
            ):
                raise SystemExit("--template contains forbidden review labels")
        prompt_hash = hashlib.sha256(
            SHARDED_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest()
        index = create_task_checkpoint(
            packet_path,
            checkpoint_dir,
            reviewer_id=args.reviewer_id,
            reviewer_type=args.reviewer_type,
            batch_size=args.batch_size,
            shuffle_seed=args.shuffle_seed,
            prompt_hash=prompt_hash,
        )
        packet_ref = checkpoint_dir / "packet.ref.json"
        if not packet_ref.exists():
            atomic_write_json(packet_ref, load_blind_packet(packet_path))
        if args.prepare_only:
            print(
                json.dumps(
                    {
                        "status": "prepared",
                        "task_count": index["task_count"],
                        "definition_sha256": index["definition_sha256"],
                        "provider_calls": 0,
                        "new_authorized_budget": 0,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        out_review_value = args.out_review_alias or args.out_review
        out_review = Path(out_review_value).resolve() if out_review_value else None
        out_coverage = (
            Path(args.out_coverage).resolve() if args.out_coverage else None
        )
        if args.recorded_responses:
            evidence_mode = "recorded"
            call_fn = _recorded_call_factory(Path(args.recorded_responses).resolve())
            model_name = args.model or "recorded-fixture"
        else:
            evidence_mode = "provider"
            model_name = args.model or ""
            call_fn = None
            # Zero authorization must block before provider configuration or client
            # construction, so secrets are never touched by an unauthorized run.
            if args.budget_tokens > 0:
                base_url, api_key, model_name = _load_provider_config(
                    provider_file=(
                        Path(args.provider_file).resolve()
                        if args.provider_file
                        else None
                    ),
                    env_prefix=args.env_prefix,
                    env_file=(Path(args.env_file).resolve() if args.env_file else None),
                    model_override=args.model,
                )
                client = OpenAI(api_key=api_key, base_url=base_url, timeout=args.timeout)

                def call_fn(messages: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
                    return _openai_reply(
                        client,
                        model_name,
                        messages,
                        max_tokens,
                        disable_thinking=args.disable_thinking,
                    )

        final_index, exit_code = execute_sharded_checkpoint(
            checkpoint_dir,
            call_fn=call_fn,
            evidence_mode=evidence_mode,
            authorized_budget=args.budget_tokens,
            max_calls=args.max_calls,
            max_input_tokens=args.max_input_tokens,
            max_output_tokens=args.max_output_tokens,
            retry_invalid=args.retry_invalid,
            resume=args.resume,
            probe_only=args.probe_only,
            model_family=args.model_family,
            model_name=model_name,
            provider_name=args.provider_name,
            out_review=out_review,
            out_coverage=out_coverage,
        )
        print(
            json.dumps(
                {
                    "status": final_index["run_status"],
                    "task_count": final_index["task_count"],
                    "completed_cases": final_index["usage"]["completed_cases"],
                    "provider_calls": final_index["usage"]["provider_calls"],
                    "recorded_calls": final_index["usage"]["recorded_calls"],
                    "retries": final_index["usage"]["retries"],
                    "new_authorized_budget": final_index["budget"]["new_authorized_budget"],
                    "exact_tokens": final_index["budget"]["current_run_exact_usage"],
                    "uncertain_usage_upper_bound": final_index["budget"]["uncertain_usage_upper_bound"],
                },
                ensure_ascii=False,
            )
        )
        return exit_code

    # Backward-compatible Phase 10 whole-packet mode.  It now also defaults to a
    # zero budget, so callers must explicitly authorize any legacy provider call.
    if not packet_value or not args.out_review:
        raise SystemExit(
            "legacy mode requires PACKET and --out-review; use --packet with "
            "--checkpoint-dir for Phase 11"
        )
    if not args.reviewer_id or not args.model_family or not args.provider_name:
        raise SystemExit("legacy mode requires reviewer/model/provider metadata")
    if args.budget_tokens <= 0:
        print(
            json.dumps(
                {
                    "status": "budget_blocked",
                    "provider_calls": 0,
                    "new_authorized_budget": 0,
                },
                ensure_ascii=False,
            )
        )
        return 3
    out_path = Path(args.out_review).resolve()
    try:
        review = run_review(
            packet_path=Path(packet_value).resolve(),
            provider_file=(Path(args.provider_file).resolve() if args.provider_file else None),
            env_prefix=args.env_prefix,
            env_file=(Path(args.env_file).resolve() if args.env_file else None),
            model_override=args.model,
            reviewer_id=args.reviewer_id,
            model_family=args.model_family,
            provider_name=args.provider_name,
            max_input_tokens=args.max_input_tokens,
            max_output_tokens=args.max_output_tokens,
            budget_tokens=args.budget_tokens,
            timeout=args.timeout,
            disable_thinking=args.disable_thinking,
        )
    except InvalidReviewResponse as exc:
        failure_path = (
            Path(args.out_failure).resolve()
            if args.out_failure
            else out_path.with_suffix(out_path.suffix + ".failed.json")
        )
        _atomic_write(failure_path, exc.failure_payload)
        print(
            json.dumps(
                {
                    "status": "invalid_reviewer_response",
                    "failure_out": str(failure_path),
                    "reviewer_id": args.reviewer_id,
                    "model_family": args.model_family,
                    "provider_calls": 1,
                    "total_tokens": exc.failure_payload["usage"]["total_tokens"],
                    "validation_error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 2
    _atomic_write(out_path, review)
    print(
        json.dumps(
            {
                "out": str(out_path),
                "reviewer_id": review["reviewer_id"],
                "reviewer_type": review["reviewer_type"],
                "model_family": review["model_family"],
                "model_name": review["model_name"],
                "case_count": len(review["results"]),
                "provider_calls": review["usage"]["provider_calls"],
                "input_tokens": review["usage"]["input_tokens"],
                "output_tokens": review["usage"]["output_tokens"],
                "total_tokens": review["usage"]["total_tokens"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
