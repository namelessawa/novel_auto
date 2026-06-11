"""Quality judge self-sanity check (Phase 2 Stage 0 退出条件).

Loads narratives from an existing bench artifact and runs pairwise A/B
where both sides are the SAME text. If the judge runner is unbiased,
swap-randomised tie/win/lose should converge to roughly 50/50 tie or
small-sample noise — anything else means the judge or position-bias
randomisation is broken.

Usage:
    LLM_PROVIDER=anything python scripts/quality_self_sanity.py \\
        docs/iter/bench-v15-final-iter29.json --rounds 6

Output:
    docs/iter/judge-self-sanity-{label}.{json,md}

Aborts (non-zero exit) if the win rate skews further than 2/3 in either
direction — Phase 2 §3.4 mandate "judge 流程有偏先修".
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


async def _run(args) -> dict:
    from quality_metrics import make_mimo_judge_fn, pairwise_judge

    with open(args.bench, encoding="utf-8") as f:
        bench = json.load(f)
    narratives = [n["text"] for n in bench.get("narratives", []) if n.get("text")]
    if not narratives:
        raise RuntimeError(f"no narratives in {args.bench}")

    judge_fn, judge_model = make_mimo_judge_fn()

    results: list[dict] = []
    rounds = max(1, args.rounds)
    target = narratives[0]
    t0 = time.perf_counter()
    for i in range(rounds):
        res = await pairwise_judge(
            target, target, judge_fn=judge_fn, model_name=judge_model
        )
        results.append(res.to_dict())
    elapsed = time.perf_counter() - t0

    winners = [r["winner"] for r in results]
    counts = {
        "x": winners.count("x"),
        "y": winners.count("y"),
        "tie": winners.count("tie"),
        "parse_error": winners.count("parse_error"),
    }
    valid = counts["x"] + counts["y"] + counts["tie"]
    bias_score = (counts["x"] - counts["y"]) / valid if valid else 0.0

    return {
        "bench_source": str(args.bench),
        "rounds": rounds,
        "elapsed_sec": round(elapsed, 2),
        "judge_model": judge_model,
        "counts": counts,
        "valid_count": valid,
        "bias_score": round(bias_score, 4),  # 应接近 0, |>0.34| 判异常
        "results": results,
    }


def _render_md(rep: dict) -> str:
    counts = rep["counts"]
    valid = rep["valid_count"]
    bias = rep["bias_score"]
    verdict = "OK" if abs(bias) < 0.34 else "BIAS_DETECTED"
    lines = [
        "# Quality Judge Self-Sanity",
        "",
        f"- source: `{rep['bench_source']}`",
        f"- rounds: {rep['rounds']}",
        f"- elapsed: {rep['elapsed_sec']}s",
        f"- judge_model: `{rep['judge_model']}`",
        "",
        "## Outcome",
        "",
        f"- x_wins: {counts['x']}",
        f"- y_wins: {counts['y']}",
        f"- tie: {counts['tie']}",
        f"- parse_error: {counts['parse_error']}",
        f"- valid_total: {valid}",
        f"- bias_score: {bias} ({verdict})",
        "",
        "> bias_score = (x_wins - y_wins) / valid. 同 text 两侧应 ≈ 0. "
        "|bias| ≥ 0.34 视作 judge 流程有偏, 必须先修.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bench", help="path to bench json artifact (provides target text)")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--label", default="default")
    args = parser.parse_args()

    if "MIMO_API_KEY" not in os.environ:
        # Allow .env to fill it.
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except Exception:
            pass

    rep = asyncio.run(_run(args))

    out_dir = _REPO_ROOT / "docs" / "iter"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"judge-self-sanity-{args.label}.json"
    md_path = out_dir / f"judge-self-sanity-{args.label}.md"
    json_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(rep), encoding="utf-8")

    print(f"[OK] wrote {json_path}")
    print(f"[OK] wrote {md_path}")
    print(
        f"bias_score={rep['bias_score']} "
        f"counts={rep['counts']} elapsed={rep['elapsed_sec']}s"
    )
    if abs(rep["bias_score"]) >= 0.34:
        print("[FAIL] |bias_score| ≥ 0.34 — judge biased, fix before Stage 1!")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
