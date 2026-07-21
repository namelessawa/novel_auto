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

SYSTEM_PROMPT = """你是独立的小说事实一致性审查者。你只能依据用户提供的盲化案例裁决，不能请求或推断系统决定、verifier 结论、fixture 标签、实验假设或隐藏 key。

对每个案例分别检查：
1. 正文是否完成全部必达终态；
2. 是否出现无来源状态变化；
3. 声明 ledger 是否与正文结尾一致；
4. 是否有角色知识越权；
5. 任一 repair 是否改变、删除或新增事实；
6. 最终 decision 是 accept、reject 或 ambiguous。

上一状态在没有合法变化事件时持续有效。对白中的撒谎和传闻不能覆盖 objective fact。typed ledger 完整本身不能代替正文兑现；证据不足时用 ambiguous，不要猜 accept。若任一 repair 删除交付、伤势、代价或新增无来源关系，应 reject。

只返回一个 JSON 对象，格式为 {"results":[{"case_id":"...","decision":"accept|reject|ambiguous","error_types":[],"confidence":0.0,"rationale":"一句简洁中文理由"}]}。必须覆盖输入中的每个 case_id，顺序保持一致，不得增加案例。error_types 只能取以下值：
""" + ", ".join(ALLOWED_ERROR_TYPES)


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
) -> dict[str, Any]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet_without_hash = dict(packet)
    packet_hash = packet_without_hash.pop("packet_sha256", None)
    if packet_hash != _stable_hash(packet_without_hash):
        raise ValueError("blind packet hash mismatch")
    case_ids = [str(case.get("case_id") or "") for case in packet.get("cases") or []]
    if not case_ids or len(case_ids) != len(set(case_ids)):
        raise ValueError("blind packet has missing or duplicate case IDs")
    compact_packet = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    user_prompt = "请审查以下盲化 packet，并严格按要求返回 JSON：\n" + compact_packet
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
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=max_output_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    finished = _now()
    content = response.choices[0].message.content or ""
    results = _validate_results(_extract_json(content), case_ids)
    usage = response.usage
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    if total_tokens > budget_tokens:
        raise ValueError("provider-reported usage exceeds reviewer token budget")
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
        "raw_response_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
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
    parser.add_argument("--out-review", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
    )
    out_path = Path(args.out_review).resolve()
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
