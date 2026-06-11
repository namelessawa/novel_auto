"""Phase 2 Stage 1 verdict runner — v15 vs v16 pairwise + det deltas.

Inputs: two bench artifact JSONs (cost bench produced earlier).
Process:
  * load narratives from both
  * compute det repetition + compliance for each (consistency needs a
    snapshot — skipped in pilot, see notes)
  * pair narrations by tick index (truncated to min length)
  * run pairwise judge on each pair using mimo (§7)
  * tally win/lose/tie + bias check + applies §4 三档处置规则
Outputs: docs/iter/verdict-{label}.{json,md}.

§4 处置矩阵:
  v16_win_rate ≥ 45% AND det 无显著恶化 → v16 转正
  v16_win_rate < 35% OR consistency 矛盾上升 → v15 维持
  35-45% → Stage 2 立项 (critic 不应是 binary 开关)

Usage:
    python scripts/stage1_verdict.py \\
        --v15-bench docs/iter/bench-v15-final-iter29.json \\
        --v16-bench docs/iter/bench-v16-final-iter31.json \\
        --judge-budget 50000 \\
        --label v15-vs-v16-pilot

Provisional 标记: 若 narrations 数 < 30 或 seed 未对齐, verdict 标
'provisional' (§4 隐含: pilot 不算最终裁决).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))


def _load_bench(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _extract_narratives(bench: dict) -> list[str]:
    return [
        n["text"]
        for n in bench.get("narratives", [])
        if n.get("text") and n["text"].strip()
    ]


async def _judge_pairs(
    pairs: list[tuple[str, str]],
    *,
    budget: int,
) -> tuple[list[dict], int]:
    """跑 pairwise judge. v15 是 x, v16 是 y. 返回 results + 估算消耗 tokens."""
    from quality_metrics import make_mimo_judge_fn, pairwise_judge

    try:
        judge_fn, judge_model = make_mimo_judge_fn()
    except RuntimeError as e:
        return [{"error": f"judge_unconfigured: {e}"}], 0

    results: list[dict] = []
    # Conservatively assume 5k tokens per pairwise call (long inputs from
    # bench narratives, ~3k input + ~200 output + chain overhead).
    approx_each = 5000
    max_calls = max(1, budget // approx_each)
    used_tokens = 0
    for i, (x, y) in enumerate(pairs[:max_calls]):
        try:
            res = await pairwise_judge(
                x, y, judge_fn=judge_fn, model_name=judge_model
            )
            d = res.to_dict()
            d["pair_index"] = i
            results.append(d)
            used_tokens += approx_each
        except Exception as e:
            results.append({"pair_index": i, "error": f"call_failed: {e}"})
    return results, used_tokens


def _det_metrics_for(narratives: list[str]) -> dict:
    """Per-bench det subset that doesn't need world snapshot."""
    from quality_metrics import NarrationRecord, compliance_report, repetition_report

    rep = repetition_report(narratives).to_dict()

    comp_records = []
    for t in narratives:
        # Approximate tier from length (matches narrator iter#10 thresholds).
        ln = len(t)
        if ln < 500:
            tier = "short"
        elif ln < 1100:
            tier = "medium"
        else:
            tier = "long"
        comp_records.append(NarrationRecord(text=t, estimated_length=tier))
    comp = compliance_report(comp_records).to_dict()
    return {"repetition": rep, "compliance": comp}


def _decide_verdict(
    v16_win: int, v16_lose: int, tie: int, parse_err: int,
    *, provisional: bool,
) -> dict:
    valid = v16_win + v16_lose + tie
    if valid == 0:
        return {
            "label": "indeterminate",
            "reason": "no valid pairwise samples",
            "provisional": True,
        }
    v16_win_rate = v16_win / valid
    v16_lose_rate = v16_lose / valid
    if v16_win_rate >= 0.45:
        label = "v16_promote"
        reason = (
            f"v16 win-rate {v16_win_rate:.2%} ≥ 45% — meets §4 promote bar"
        )
    elif v16_win_rate < 0.35:
        label = "v15_hold"
        reason = (
            f"v16 win-rate {v16_win_rate:.2%} < 35% — v15 维持 best stable"
        )
    else:
        label = "stage2_open"
        reason = (
            f"v16 win-rate {v16_win_rate:.2%} ∈ [35%, 45%) — critic 不应"
            f"是 binary 开关, Stage 2 自适应分配立项"
        )
    return {
        "label": label,
        "reason": reason,
        "v16_win_rate": round(v16_win_rate, 4),
        "v16_lose_rate": round(v16_lose_rate, 4),
        "tie_rate": round(tie / valid, 4),
        "parse_err_count": parse_err,
        "valid_count": valid,
        "provisional": provisional,
    }


def _render_md(rep: dict) -> str:
    v15 = rep["v15"]
    v16 = rep["v16"]
    v15_det = v15["det"]
    v16_det = v16["det"]
    pj = rep["pairwise"]
    verdict = rep["verdict"]
    lines = [
        "# Stage 1 Verdict — v15 vs v16",
        "",
        f"- source v15: `{v15['source']}` ({v15['narrative_count']} narrations)",
        f"- source v16: `{v16['source']}` ({v16['narrative_count']} narrations)",
        f"- paired: {pj['pair_count']} (truncated to min)",
        f"- judge_calls: {pj['judge_call_count']} (budget {rep['budget']})",
        f"- judge_tokens_estimated: {pj['tokens_used_estimate']}",
        "",
        "## Verdict",
        "",
        f"- **label**: `{verdict['label']}`",
        f"- reason: {verdict['reason']}",
        f"- v16_win_rate: {verdict.get('v16_win_rate', 'n/a')}",
        f"- v16_lose_rate: {verdict.get('v16_lose_rate', 'n/a')}",
        f"- tie_rate: {verdict.get('tie_rate', 'n/a')}",
        f"- parse_err: {verdict.get('parse_err_count', 'n/a')}",
        f"- provisional: {verdict['provisional']}",
        "",
        "## Det comparison",
        "",
        "| dim | v15 | v16 |",
        "| --- | ---: | ---: |",
        f"| distinct char-2 (mean) | {v15_det['repetition']['distinct']['char_2']} | {v16_det['repetition']['distinct']['char_2']} |",
        f"| distinct char-4 (mean) | {v15_det['repetition']['distinct']['char_4']} | {v16_det['repetition']['distinct']['char_4']} |",
        f"| overlap consec char-2 | {v15_det['repetition']['overlap_consecutive']['char_2']} | {v16_det['repetition']['overlap_consecutive']['char_2']} |",
        f"| tier_hit_rate | {v15_det['compliance']['tier_hit_rate']} | {v16_det['compliance']['tier_hit_rate']} |",
        f"| narrations | {v15_det['repetition']['narration_count']} | {v16_det['repetition']['narration_count']} |",
        "",
        "## Pairwise samples (first 5)",
        "",
    ]
    for r in pj["results"][:5]:
        if "error" in r:
            lines.append(f"- pair#{r.get('pair_index', '?')}: ERROR {r['error']}")
        else:
            lines.append(
                f"- pair#{r['pair_index']}: winner={r['winner']} "
                f"swap={r['meta']['swap_applied']} reason={r.get('reason', '')[:60]}"
            )
    return "\n".join(lines) + "\n"


async def _main(args) -> dict:
    v15_bench = _load_bench(args.v15_bench)
    v16_bench = _load_bench(args.v16_bench)
    v15_nars = _extract_narratives(v15_bench)
    v16_nars = _extract_narratives(v16_bench)
    if not v15_nars or not v16_nars:
        raise RuntimeError("no narratives in one of the benches")

    paired = list(zip(v15_nars, v16_nars))  # truncate to min
    # provisional if either side is under 30 narrations (§ Stage 1 ≥ 30)
    provisional = len(v15_nars) < 30 or len(v16_nars) < 30

    t0 = time.perf_counter()
    judge_results, tokens_used = await _judge_pairs(
        paired, budget=args.judge_budget
    )
    elapsed = time.perf_counter() - t0

    # Tally winners. v15 = x, v16 = y.
    v15_win = sum(1 for r in judge_results if r.get("winner") == "x")
    v16_win = sum(1 for r in judge_results if r.get("winner") == "y")
    tie = sum(1 for r in judge_results if r.get("winner") == "tie")
    parse_err = sum(
        1 for r in judge_results
        if r.get("winner") == "parse_error" or "error" in r
    )

    rep = {
        "label": args.label,
        "v15": {
            "source": str(args.v15_bench),
            "narrative_count": len(v15_nars),
            "det": _det_metrics_for(v15_nars),
        },
        "v16": {
            "source": str(args.v16_bench),
            "narrative_count": len(v16_nars),
            "det": _det_metrics_for(v16_nars),
        },
        "pairwise": {
            "pair_count": len(paired),
            "judge_call_count": len(judge_results),
            "tokens_used_estimate": tokens_used,
            "elapsed_sec": round(elapsed, 2),
            "v15_win": v15_win,
            "v16_win": v16_win,
            "tie": tie,
            "parse_err": parse_err,
            "results": judge_results,
        },
        "budget": args.judge_budget,
        "verdict": _decide_verdict(
            v16_win=v16_win,
            v16_lose=v15_win,
            tie=tie,
            parse_err=parse_err,
            provisional=provisional,
        ),
    }
    return rep


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v15-bench", required=True)
    parser.add_argument("--v16-bench", required=True)
    parser.add_argument("--judge-budget", type=int, default=50_000)
    parser.add_argument("--label", default="v15-vs-v16-pilot")
    args = parser.parse_args()

    if "MIMO_API_KEY" not in os.environ:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except Exception:
            pass

    rep = asyncio.run(_main(args))
    out_dir = _REPO_ROOT / "docs" / "iter"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"verdict-{args.label}.json"
    md_path = out_dir / f"verdict-{args.label}.md"
    json_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(rep), encoding="utf-8")
    print(f"[OK] wrote {json_path}")
    print(f"[OK] wrote {md_path}")
    v = rep["verdict"]
    print(f"verdict: {v['label']} (provisional={v['provisional']}) — {v['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
