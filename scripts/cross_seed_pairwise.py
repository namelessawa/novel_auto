"""Phase 5+ PHASE5_PLAN candidate K — 3-seed pairwise judge aggregator.

PHASE5_PLAN 教训: 架构改动 mandatory cross-seed ×3 (plot-light / medium /
dense), 单 seed n=4 mimo pairwise 50% = 噪音.

本脚本 = 3 个 (baseline_bench_json, candidate_bench_json) pair 上跑
pairwise_judge_phase5 → 聚合 3-seed verdict.

不自动 bootstrap / 不跑 bench — 输入是已跑完的 6 个 bench JSON. 这让 cost
完全可控 (用户决定何时启 bench), 脚本只管 judge + 聚合.

Usage:
    python scripts/cross_seed_pairwise.py \\
        --pair seed1=docs/iter/bench-seed1-A.json,docs/iter/bench-seed1-B.json \\
        --pair seed2=docs/iter/bench-seed2-A.json,docs/iter/bench-seed2-B.json \\
        --pair seed3=docs/iter/bench-seed3-A.json,docs/iter/bench-seed3-B.json \\
        --output docs/iter/verdict-3seed-{ts}.md

PHASE5_PLAN ship gate: avg B win rate >= 60% across 3 seeds → ship.
单 seed >= 45% → 该 seed PASS 当 seed 级证据.

HARD STOP: 任一 seed 的 pairwise 进程退出码 = 2 (judge 不可用) → 总流程 abort.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _parse_pair(spec: str) -> tuple[str, Path, Path]:
    """Parse 'seedN=path/a.json,path/b.json' into (name, a_path, b_path)."""
    if "=" not in spec or "," not in spec:
        raise argparse.ArgumentTypeError(
            f"--pair must be 'name=path_a,path_b', got {spec!r}"
        )
    name, paths = spec.split("=", 1)
    a, b = paths.split(",", 1)
    return name.strip(), Path(a.strip()), Path(b.strip())


def _run_pairwise(
    name: str, a_path: Path, b_path: Path, out_dir: Path, max_pairs: int
) -> dict:
    """Spawn pairwise_judge_phase5 subprocess, capture verdict + parse counts.

    Returns dict with keys: name, a_wins, b_wins, ties, parse_errors, b_win_rate,
    verdict_path, exit_code, error (if any).
    """
    verdict_path = out_dir / f"verdict-3seed-{name}-{int(time.time())}.md"
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "pairwise_judge_phase5.py"),
        "--bench-a", str(a_path),
        "--bench-b", str(b_path),
        "--output", str(verdict_path),
        "--max-pairs", str(max_pairs),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    result: dict = {
        "name": name,
        "a_path": str(a_path),
        "b_path": str(b_path),
        "verdict_path": str(verdict_path),
        "exit_code": proc.returncode,
        "a_wins": 0,
        "b_wins": 0,
        "ties": 0,
        "parse_errors": 0,
        "b_win_rate": 0.0,
        "error": "",
    }
    if proc.returncode == 2:
        result["error"] = "HARD_STOP_judge_unavailable"
        return result
    if proc.returncode != 0:
        result["error"] = (proc.stderr or proc.stdout or "")[-400:]
        return result

    if not verdict_path.exists():
        result["error"] = "verdict_md_not_written"
        return result

    md = verdict_path.read_text(encoding="utf-8")
    for line in md.splitlines():
        m = re.match(r"- A wins: \*\*(\d+)\*\*", line)
        if m:
            result["a_wins"] = int(m.group(1))
        m = re.match(r"- B wins: \*\*(\d+)\*\*", line)
        if m:
            result["b_wins"] = int(m.group(1))
        m = re.match(r"- TIE: (\d+)", line)
        if m:
            result["ties"] = int(m.group(1))
        m = re.match(r"- parse_error: (\d+)", line)
        if m:
            result["parse_errors"] = int(m.group(1))
        m = re.match(r"- \*\*B win rate \(decisive only\): ([\d.]+)%\*\*", line)
        if m:
            result["b_win_rate"] = float(m.group(1)) / 100.0

    decisive = result["a_wins"] + result["b_wins"]
    if decisive and not result["b_win_rate"]:
        result["b_win_rate"] = result["b_wins"] / decisive
    return result


def _render_3seed_md(results: list[dict]) -> str:
    seed_count = len(results)
    successful = [r for r in results if not r["error"]]
    a_total = sum(r["a_wins"] for r in successful)
    b_total = sum(r["b_wins"] for r in successful)
    tie_total = sum(r["ties"] for r in successful)
    decisive_total = a_total + b_total
    overall_rate = b_total / decisive_total if decisive_total else 0.0

    lines = [
        f"# Cross-seed pairwise verdict ({seed_count}-seed)",
        "",
        f"- timestamp: {int(time.time())}",
        f"- seeds run: {seed_count} ({len(successful)} OK, {seed_count - len(successful)} ERROR)",
        f"- TOTAL A wins: {a_total}",
        f"- TOTAL B wins: {b_total}",
        f"- TOTAL TIE: {tie_total}",
        f"- **OVERALL B win rate (decisive only): {overall_rate * 100:.1f}%**",
        "",
        "## Per-seed",
        "",
        "| seed | A wins | B wins | TIE | err | B win% | verdict |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} | {r['a_wins']} | {r['b_wins']} | {r['ties']} | "
            f"{r['parse_errors']} | {r['b_win_rate'] * 100:.1f}% | "
            f"{r['error'][:30] if r['error'] else '`' + Path(r['verdict_path']).name + '`'} |"
        )

    lines += ["", "## PHASE5_PLAN ship gate", ""]
    if not successful:
        lines.append("- INSUFFICIENT_DATA — 0 seeds succeeded")
    elif overall_rate >= 0.60:
        lines.append(
            f"- **PASS — SHIP**: overall B win rate {overall_rate * 100:.1f}% >= 60% "
            f"(PHASE5_PLAN architectural change ship gate)"
        )
    elif overall_rate >= 0.45:
        lines.append(
            f"- **MARGINAL — RETRY**: overall B win rate {overall_rate * 100:.1f}% in "
            f"45-60% range. 中性, 建议追加 seed 或反向 candidate 减证."
        )
    else:
        lines.append(
            f"- **FAIL — REVERT**: overall B win rate {overall_rate * 100:.1f}% < 45%. "
            f"per Phase 4-F lesson revert candidate."
        )

    if successful:
        single_pass = [r for r in successful if r["b_win_rate"] >= 0.45]
        lines += [
            "",
            "## 单 seed PASS 数",
            f"- ≥45% (seed 级有效): {len(single_pass)} / {len(successful)}",
        ]
        seed_passing = [
            r for r in successful if r["b_win_rate"] >= 0.60
        ]
        lines.append(
            f"- ≥60% (seed 级 strong PASS): {len(seed_passing)} / {len(successful)}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pair",
        action="append",
        required=True,
        type=_parse_pair,
        help="seed_name=baseline_bench.json,candidate_bench.json (repeat 3x)",
    )
    parser.add_argument(
        "--output",
        default=f"docs/iter/verdict-3seed-{int(time.time())}.md",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=20,
        help="per-seed pairwise sample cap (forwards to pairwise_judge_phase5)",
    )
    args = parser.parse_args()

    if len(args.pair) < 2:
        parser.error("at least 2 --pair required for cross-seed analysis")

    out_dir = _REPO_ROOT / "docs" / "iter"
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for name, a, b in args.pair:
        print(f">>> Running pairwise for seed={name}: A={a.name} vs B={b.name}")
        r = _run_pairwise(name, a, b, out_dir, args.max_pairs)
        results.append(r)
        if r["error"] == "HARD_STOP_judge_unavailable":
            print(
                "HARD STOP: judge endpoint dead. Aborting remaining seeds "
                "(per user rule)."
            )
            break

    out_path = _REPO_ROOT / args.output
    out_path.write_text(_render_3seed_md(results), encoding="utf-8")
    print()
    print(f"3-seed verdict: {out_path}")
    print(f"  seeds OK: {sum(1 for r in results if not r['error'])}/{len(results)}")
    a_total = sum(r["a_wins"] for r in results)
    b_total = sum(r["b_wins"] for r in results)
    decisive = a_total + b_total
    if decisive:
        print(f"  overall B win rate: {b_total / decisive * 100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
