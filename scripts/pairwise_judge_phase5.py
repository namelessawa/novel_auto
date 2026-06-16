"""Phase 5 mimo pairwise gate runner.

输入: 两个 bench 报告 (A = baseline, B = Phase 5-B 启用).
对每个 *同 tick* 都有 narrative 的 pair, 调 mimo pairwise_judge.
聚合 win/loss/tie + 报告。

HARD STOP per user rule: mimo 不可用 (401 / 429 / timeout) 立即停止并退出码 = 2.
不静默 fallback 到 det-only.

Usage:
    python scripts/pairwise_judge_phase5.py \\
        --bench-a docs/iter/bench-phase5-mimo-A-no-stale.json \\
        --bench-b docs/iter/bench-phase5-mimo-B-stale-on.json \\
        --output docs/iter/verdict-phase5-mimo-gate.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / ".env")

from quality_metrics.judge import make_active_judge_fn, pairwise_judge  # noqa: E402


def _load_bench(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _narratives_by_tick(bench: dict) -> dict[int, str]:
    """返回 {tick_number: narrative_text}."""
    out: dict[int, str] = {}
    for n in bench.get("narratives", []) or []:
        t = int(n.get("tick", -1))
        text = (n.get("text") or "").strip()
        if t >= 0 and text:
            out[t] = text
    return out


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bench-a",
        type=Path,
        required=True,
        help="baseline bench JSON (e.g. Phase 5-A only, no stale-skip)",
    )
    parser.add_argument(
        "--bench-b",
        type=Path,
        required=True,
        help="candidate bench JSON (e.g. Phase 5-A + 5-B stale-skip on)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="verdict markdown output path",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=20,
        help="hard cap on pair count (budget protection). Default 20.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for position swap (reproducibility)",
    )
    args = parser.parse_args()

    bench_a = _load_bench(args.bench_a)
    bench_b = _load_bench(args.bench_b)
    a_by_tick = _narratives_by_tick(bench_a)
    b_by_tick = _narratives_by_tick(bench_b)
    shared_ticks = sorted(set(a_by_tick) & set(b_by_tick))

    if not shared_ticks:
        print("FAIL: no overlapping ticks have narrative in both benches.")
        print(f"      A ticks with content: {sorted(a_by_tick)[:10]}...")
        print(f"      B ticks with content: {sorted(b_by_tick)[:10]}...")
        return 3

    if len(shared_ticks) > args.max_pairs:
        # 均匀采样
        step = len(shared_ticks) / args.max_pairs
        shared_ticks = [shared_ticks[int(i * step)] for i in range(args.max_pairs)]

    print(f"Comparing {len(shared_ticks)} tick pairs: {shared_ticks}")
    print(f"A label: {bench_a.get('label')!r}")
    print(f"B label: {bench_b.get('label')!r}")

    # HARD STOP guard: 构造 judge client (JUDGE_PROVIDER 决定), 任何失败立即退
    try:
        judge_fn, model_name = make_active_judge_fn()
    except RuntimeError as e:
        print(f"HARD STOP: judge init failed — {e}")
        return 2

    print(f"judge model: {model_name}")
    print()

    rng = random.Random(args.seed)
    results: list[dict] = []
    counts = {"a_wins": 0, "b_wins": 0, "tie": 0, "parse_error": 0}
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 3  # hard stop threshold for mimo死亡

    for tick in shared_ticks:
        a_text = a_by_tick[tick]
        b_text = b_by_tick[tick]
        # 我们的 pairwise_judge: x = A, y = B
        r = await pairwise_judge(
            text_x=a_text,
            text_y=b_text,
            judge_fn=judge_fn,
            model_name=model_name,
            rng=rng,
        )
        winner_letter = {"x": "A", "y": "B", "tie": "TIE", "parse_error": "ERR"}[r.winner]
        print(
            f"  tick {tick:3d}: winner={winner_letter:3s} "
            f"({len(a_text)}/{len(b_text)} chars) — {r.reason[:80]}"
        )
        results.append(
            {
                "tick": tick,
                "winner": winner_letter,
                "reason": r.reason,
                "a_chars": len(a_text),
                "b_chars": len(b_text),
                "swap_applied": r.meta.swap_applied,
            }
        )
        if r.winner == "x":
            counts["a_wins"] += 1
            consecutive_failures = 0
        elif r.winner == "y":
            counts["b_wins"] += 1
            consecutive_failures = 0
        elif r.winner == "tie":
            counts["tie"] += 1
            consecutive_failures = 0
        else:
            counts["parse_error"] += 1
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(
                    f"HARD STOP: {consecutive_failures} consecutive judge failures. "
                    f"Mimo likely down. Aborting (per user rule)."
                )
                return 2

    decisive = counts["a_wins"] + counts["b_wins"]
    b_win_rate = counts["b_wins"] / decisive if decisive else 0.0
    print()
    print(f"=== Summary ===")
    print(f"  A wins (baseline): {counts['a_wins']}")
    print(f"  B wins (Phase 5-B): {counts['b_wins']}")
    print(f"  TIE              : {counts['tie']}")
    print(f"  parse_error      : {counts['parse_error']}")
    print(f"  B win rate (decisive only): {b_win_rate*100:.1f}%")

    # 写 verdict markdown
    args.output.parent.mkdir(parents=True, exist_ok=True)
    md_lines = [
        "# Phase 5 mimo pairwise gate — verdict",
        "",
        f"- bench A (baseline): `{args.bench_a.name}` — label `{bench_a.get('label')}`",
        f"- bench B (candidate): `{args.bench_b.name}` — label `{bench_b.get('label')}`",
        f"- judge model: `{model_name}`",
        f"- pair count: {len(shared_ticks)}",
        "",
        "## Counts",
        "",
        f"- A wins: **{counts['a_wins']}**",
        f"- B wins: **{counts['b_wins']}**",
        f"- TIE: {counts['tie']}",
        f"- parse_error: {counts['parse_error']}",
        f"- **B win rate (decisive only): {b_win_rate*100:.1f}%**",
        "",
        "## Per-tick",
        "",
        "| tick | winner | A chars | B chars | reason |",
        "| ---: | --- | ---: | ---: | --- |",
    ]
    for r in results:
        md_lines.append(
            f"| {r['tick']} | {r['winner']} | {r['a_chars']} | {r['b_chars']} | {r['reason'][:120]} |"
        )

    # PHASE5_PLAN: ≥ 45% win → 进 3-seed promote
    md_lines += ["", "## Decision (PHASE5_PLAN gate)"]
    if decisive == 0:
        md_lines.append("- INSUFFICIENT_DATA — all pairs were tie/parse_error")
    elif b_win_rate >= 0.45:
        md_lines.append(
            f"- **PASS**: B win rate {b_win_rate*100:.1f}% >= 45% threshold. "
            "Candidate quality is neutral-to-positive vs baseline. "
            "PROMOTE per PHASE5_PLAN."
        )
    else:
        md_lines.append(
            f"- **FAIL**: B win rate {b_win_rate*100:.1f}% < 45% threshold. "
            "Candidate hurts quality. REVERT per Phase 4-F lesson."
        )

    args.output.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"verdict written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
