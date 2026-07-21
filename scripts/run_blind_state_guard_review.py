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
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet")
    provider = parser.add_mutually_exclusive_group(required=True)
    provider.add_argument("--provider-file")
    provider.add_argument("--env-prefix")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--model")
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--model-family", required=True)
    parser.add_argument("--provider-name", required=True)
    parser.add_argument("--max-input-tokens", type=int, default=24000)
    parser.add_argument("--max-output-tokens", type=int, default=5000)
    parser.add_argument("--budget-tokens", type=int, default=30000)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--disable-thinking", action="store_true")
    parser.add_argument("--out-review", required=True)
    parser.add_argument(
        "--out-failure",
        help="sanitized failed-response checkpoint (default: OUT_REVIEW.failed.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_path = Path(args.out_review).resolve()
    try:
        review = run_review(
            packet_path=Path(args.packet).resolve(),
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
