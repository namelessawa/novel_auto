"""Blind multi-class style identification over existing validation artifacts.

The judge receives only prose plus anonymous candidate contracts.  The expected
style key/label is never included in the model prompt.  Results are checkpointed
after every sample and summarized as top-1/top-3 accuracy + confusion matrix.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "backend"), str(ROOT / "scripts")]

PROMPT_VERSION = "blind-style-v1"
DEFAULT_JUDGE_BUDGET = 50_000
JUDGE_CALL_RESERVE = 5_500


def _response_total_tokens(response) -> int:
    """Read the repository's typed LLMResponse usage fields.

    A small compatibility fallback is retained for script tests and older
    response wrappers that exposed an OpenAI-like ``usage`` dictionary.
    """
    prompt_tokens = getattr(response, "usage_prompt_tokens", None)
    completion_tokens = getattr(response, "usage_completion_tokens", None)
    if prompt_tokens is not None or completion_tokens is not None:
        return int(prompt_tokens or 0) + int(completion_tokens or 0)
    usage = getattr(response, "usage", {}) or {}
    if isinstance(usage, dict):
        return int(usage.get("total_tokens", 0) or 0)
    return int(getattr(usage, "total_tokens", 0) or 0)


def _budget_allows_call(spent: int, budget: int, reserve: int) -> bool:
    """Fail closed before another judge call can silently exceed its budget."""
    return budget <= 0 or spent + reserve <= budget


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _sanitised_contract(preset) -> str:
    """Keep behavioral style features while removing registry identity strings."""
    addendum = re.sub(r"^#.*(?:\r?\n)?", "", preset.narrator_addendum.strip())
    text = "\n".join((preset.description.strip(), addendum, preset.final_checklist.strip()))
    for identity in (preset.key, preset.label):
        text = text.replace(identity, "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()[:1100]


def _anonymous_candidates(style_keys: list[str], salt: str) -> tuple[str, dict[str, str]]:
    from novel_presets import get_style_preset

    ordered = sorted(
        style_keys,
        key=lambda key: hashlib.sha256(f"{salt}:{key}".encode()).hexdigest(),
    )
    id_to_key: dict[str, str] = {}
    blocks: list[str] = []
    for index, key in enumerate(ordered, 1):
        candidate_id = f"C{index:02d}"
        id_to_key[candidate_id] = key
        blocks.append(
            f"<{candidate_id}>\n{_sanitised_contract(get_style_preset(key))}\n"
            f"</{candidate_id}>"
        )
    return "\n\n".join(blocks), id_to_key


def _build_judge_prompts(
    *, text: str, style_keys: list[str], salt: str
) -> tuple[str, str, dict[str, str]]:
    options, id_to_key = _anonymous_candidates(style_keys, salt)
    system = (
        "你是独立的中文小说文风盲测员。只根据正文可观察到的句式、节奏、"
        "视点距离、对白/心理/动作比例、感官密度和收尾方式做多类识别。"
        "候选编号是随机匿名编号；不得猜测编号含义。严格输出 JSON。"
    )
    user = f"""\
下面是全部匿名候选写作契约：

{options}

下面是一段未标注正文。题材事件不等于文风；不要因世界设定直接选某候选。

<PROSE>
{text[:7000]}
</PROSE>

从全部候选中给出互不重复的前三名。evidence 必须引用正文中可观察的短特征，
不得输出未提供的 style key/中文标签。
严格输出：
{{"top3":[{{"candidate_id":"C01","confidence":0.0,"evidence":["短证据"]}},
{{"candidate_id":"C02","confidence":0.0,"evidence":["短证据"]}},
{{"candidate_id":"C03","confidence":0.0,"evidence":["短证据"]}}],
"observed_features":["特征"]}}
"""
    return system, user, id_to_key


def _normalise_judgment(payload: dict, id_to_key: dict[str, str]) -> dict:
    raw_top = payload.get("top3") or []
    if not isinstance(raw_top, list):
        raw_top = []
    top3: list[dict] = []
    seen: set[str] = set()
    for raw in raw_top:
        if isinstance(raw, str):
            candidate_id = raw.strip()
            raw = {"candidate_id": candidate_id}
        elif isinstance(raw, dict):
            candidate_id = str(raw.get("candidate_id", "") or "").strip()
        else:
            continue
        if candidate_id not in id_to_key or candidate_id in seen:
            continue
        seen.add(candidate_id)
        try:
            confidence = float(raw.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        evidence = raw.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        top3.append({
            "candidate_id": candidate_id,
            "style": id_to_key[candidate_id],
            "confidence": round(max(0.0, min(1.0, confidence)), 4),
            "evidence": [str(item)[:240] for item in evidence[:4]],
        })
        if len(top3) == 3:
            break
    observed = payload.get("observed_features") or []
    if isinstance(observed, str):
        observed = [observed]
    return {
        "valid": len(top3) == 3,
        "top3": top3,
        "observed_features": [str(item)[:240] for item in observed[:8]],
        "error": "" if len(top3) == 3 else "judge_did_not_return_three_valid_candidates",
    }


def _summarise(results: list[dict], style_keys: list[str]) -> dict:
    valid = [row for row in results if row.get("judgment", {}).get("valid")]
    matrix = {
        expected: {predicted: 0 for predicted in style_keys}
        for expected in style_keys
    }
    top1_hits = 0
    top3_hits = 0
    by_scenario: dict[str, dict[str, int]] = {}
    confusions: dict[tuple[str, str], int] = {}
    for row in valid:
        expected = row["expected_style"]
        predicted = row["judgment"]["top3"][0]["style"]
        predicted_top3 = [item["style"] for item in row["judgment"]["top3"]]
        if expected in matrix and predicted in matrix[expected]:
            matrix[expected][predicted] += 1
        top1_hits += int(predicted == expected)
        top3_hits += int(expected in predicted_top3)
        if predicted != expected:
            confusions[(expected, predicted)] = confusions.get((expected, predicted), 0) + 1
        scenario = row.get("scenario", "unknown") or "unknown"
        bucket = by_scenario.setdefault(scenario, {"total": 0, "top1": 0, "top3": 0})
        bucket["total"] += 1
        bucket["top1"] += int(predicted == expected)
        bucket["top3"] += int(expected in predicted_top3)
    total = len(valid)
    return {
        "total_samples": len(results),
        "valid_samples": total,
        "top1_hits": top1_hits,
        "top3_hits": top3_hits,
        "top1_accuracy": round(top1_hits / total, 4) if total else None,
        "top3_accuracy": round(top3_hits / total, 4) if total else None,
        "by_scenario": by_scenario,
        "confusion_matrix": matrix,
        "top_confusions": [
            {"expected": pair[0], "predicted": pair[1], "count": count}
            for pair, count in sorted(
                confusions.items(), key=lambda item: (-item[1], item[0])
            )
        ],
    }


def _render_markdown(report: dict) -> str:
    summary = report.get("summary") or {}
    execution = report.get("execution") or {}
    lines = [
        "# Blind style classification\n",
        f"- Git: `{report.get('metadata', {}).get('git_sha')}`",
        f"- Model: `{report.get('metadata', {}).get('provider', {}).get('model')}`",
        f"- Samples: `{summary.get('valid_samples')}/{summary.get('total_samples')}` valid",
        f"- Top-1: `{summary.get('top1_accuracy')}`",
        f"- Top-3: `{summary.get('top3_accuracy')}`",
        f"- Execution: `{execution.get('status', 'UNKNOWN')}`",
        f"- Judge tokens: `{execution.get('actual_judge_tokens', 'unknown')}` / "
        f"`{execution.get('configured_judge_budget_tokens', 'unknown')}`\n",
        "## Samples\n",
        "| scenario | theme | expected | top-1 | top-3 | hit |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("results", []):
        top = row.get("judgment", {}).get("top3", [])
        predicted = top[0]["style"] if top else "ERROR"
        top_styles = ", ".join(item["style"] for item in top) or "—"
        hit = "TOP1" if predicted == row.get("expected_style") else (
            "TOP3" if row.get("expected_style") in [item["style"] for item in top]
            else "MISS"
        )
        lines.append(
            f"| {row.get('scenario')} | {row.get('theme')} | "
            f"{row.get('expected_style')} | {predicted} | {top_styles} | {hit} |"
        )
    lines.extend(["\n## Top confusions\n"])
    for item in summary.get("top_confusions", []):
        lines.append(
            f"- `{item['expected']}` → `{item['predicted']}`: {item['count']}"
        )
    if not summary.get("top_confusions"):
        lines.append("- none")
    return "\n".join(lines) + "\n"


async def _judge_sample(text: str, style_keys: list[str], salt: str) -> tuple[dict, int]:
    from nf_core.json_utils import parse_llm_json
    from nf_core.llm_client import llm_client

    system, user, id_to_key = _build_judge_prompts(
        text=text, style_keys=style_keys, salt=salt
    )
    response = await llm_client.chat(
        system_prompt=system,
        user_prompt=user,
        temperature=0.0,
        max_tokens=1800,
        agent_id="blind_style_judge",
        priority="medium",
        tick=0,
    )
    judgment = _normalise_judgment(parse_llm_json(response.content), id_to_key)
    return judgment, _response_total_tokens(response)


async def _run(args, report: dict, output: Path) -> dict:
    from novel_presets import list_style_keys

    input_path = (ROOT / args.input).resolve()
    source = json.loads(input_path.read_text(encoding="utf-8"))
    all_style_keys = list_style_keys()
    sample_filter = set(all_style_keys) if args.sample_styles == "all" else {
        item.strip() for item in args.sample_styles.split(",") if item.strip()
    }
    unknown = sample_filter - set(all_style_keys)
    if unknown:
        raise ValueError(f"unknown sample styles: {sorted(unknown)}")
    samples: list[dict] = []
    for index, row in enumerate(source.get("results") or []):
        expected = str(row.get("style", "") or "")
        text = str(row.get("text", "") or "").strip()
        if expected not in sample_filter or not text:
            continue
        samples.append({
            "sample_id": f"{row.get('scenario')}:{row.get('theme')}:{expected}:{index}",
            "scenario": row.get("scenario", ""),
            "theme": row.get("theme", ""),
            "expected_style": expected,
            "char_count": len(text),
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "text": text,
        })
    if args.max_samples:
        samples = samples[:args.max_samples]
    completed = {row.get("sample_id") for row in report.get("results", [])}
    budget_exhausted = False
    for index, sample in enumerate(samples, 1):
        if sample["sample_id"] in completed:
            continue
        spent = sum(int(row.get("judge_tokens", 0) or 0) for row in report.get("results", []))
        if not _budget_allows_call(spent, args.judge_budget, JUDGE_CALL_RESERVE):
            budget_exhausted = True
            break
        try:
            judgment, tokens = await _judge_sample(
                sample["text"], all_style_keys, sample["text_sha256"]
            )
            result = {k: v for k, v in sample.items() if k != "text"}
            result["judgment"] = judgment
            result["judge_tokens"] = tokens
        except Exception as exc:
            result = {k: v for k, v in sample.items() if k != "text"}
            result["judgment"] = {
                "valid": False, "top3": [], "observed_features": [],
                "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            }
            result["judge_tokens"] = 0
        report.setdefault("results", []).append(result)
        completed.add(sample["sample_id"])
        report["summary"] = _summarise(report["results"], all_style_keys)
        _atomic_json(output, report)
        print(
            f"[{index}/{len(samples)}] {sample['sample_id']}: "
            f"{'OK' if result['judgment']['valid'] else 'ERROR'}",
            flush=True,
        )
    report.setdefault("metadata", {})["finished_at"] = int(time.time())
    report["summary"] = _summarise(report.get("results", []), all_style_keys)
    target_ids = {sample["sample_id"] for sample in samples}
    completed_targets = target_ids & {
        row.get("sample_id") for row in report.get("results", [])
    }
    report["execution"] = {
        "status": "BUDGET_EXHAUSTED" if budget_exhausted else (
            "COMPLETE" if completed_targets == target_ids else "INCOMPLETE"
        ),
        "configured_judge_budget_tokens": args.judge_budget,
        "per_call_reserve_tokens": JUDGE_CALL_RESERVE,
        "actual_judge_tokens": sum(
            int(row.get("judge_tokens", 0) or 0)
            for row in report.get("results", [])
        ),
        "target_samples": len(target_ids),
        "completed_samples": len(completed_targets),
        "remaining_samples": len(target_ids - completed_targets),
    }
    _atomic_json(output, report)
    output.with_suffix(".md").write_text(_render_markdown(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="validate_styles JSON")
    parser.add_argument("--provider-file", default="coding.txt")
    parser.add_argument("--sample-styles", default="all")
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument(
        "--judge-budget",
        type=int,
        default=int(os.getenv("JUDGE_BUDGET_PER_BENCH", DEFAULT_JUDGE_BUDGET)),
        help="hard judge-token budget; 0 disables the cap (default: 50000)",
    )
    parser.add_argument("--out", default="docs/iter/blind-style-classification.json")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    from validate_styles import _configure_provider
    from novel_presets import (
        STYLE_PRESET_SCHEMA_VERSION,
        get_style_preset,
        list_style_keys,
    )

    provider = _configure_provider((ROOT / args.provider_file).resolve())
    output = (ROOT / args.out).resolve()
    if args.resume and output.exists():
        report = json.loads(output.read_text(encoding="utf-8"))
        report.setdefault("metadata", {})["configured_judge_budget_tokens"] = (
            args.judge_budget
        )
    else:
        contracts = {
            key: get_style_preset(key).prompt_hash for key in list_style_keys()
        }
        report = {
            "metadata": {
                "started_at": int(time.time()),
                "git_sha": _git_sha(),
                "provider": provider,
                "input": str((ROOT / args.input).resolve()),
                "input_sha256": hashlib.sha256(
                    (ROOT / args.input).read_bytes()
                ).hexdigest(),
                "prompt_version": PROMPT_VERSION,
                "style_schema_version": STYLE_PRESET_SCHEMA_VERSION,
                "candidate_prompt_hashes": contracts,
                "target_identity_sent_to_judge": False,
                "configured_judge_budget_tokens": args.judge_budget,
            },
            "results": [],
        }
    final = asyncio.run(_run(args, report, output))
    summary = final["summary"]
    print(
        f"[DONE] top1={summary['top1_accuracy']} top3={summary['top3_accuracy']} "
        f"valid={summary['valid_samples']}/{summary['total_samples']} "
        f"status={final['execution']['status']} out={output}"
    )


if __name__ == "__main__":
    main()
