"""Analyse a long-range bench artifact (Phase 2 Stage 3 §6).

Input: a bench_tick.py JSON artifact that includes open_loop_snapshots
and (eventually) novelty_records. Output: foreshadowing curve + novelty
trend + drift analysis as docs/iter/longrange-{label}.{json,md}.

Usage:
    python scripts/analyze_longrange.py \\
        --bench docs/iter/bench-stage3-longrange-50tick.json \\
        --label stage3-50tick
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))


def _build_report(bench: dict, label: str) -> dict:
    from quality_metrics import (
        NoveltySample,
        OpenLoopSnapshot,
        foreshadowing_curve,
        novelty_decay_curve,
        repetition_report,
    )

    snaps_raw = bench.get("open_loop_snapshots", []) or []
    open_loop_snaps: list[OpenLoopSnapshot] = []
    closed_unknown = False
    for s in snaps_raw:
        if "error" in s:
            continue
        if s.get("closed_source") == "not_implemented":
            closed_unknown = True
        open_loop_snaps.append(
            OpenLoopSnapshot(
                tick=s["tick"],
                open_count=s["open"],
                closed_count=s["closed"],
                stale_open_count=s["stale_open"],
                avg_urgency=s.get("avg_urgency", 0.0),
            )
        )
    fs_curve = foreshadowing_curve(open_loop_snaps)
    fs_dict = fs_curve.to_dict()
    if closed_unknown:
        fs_dict.setdefault("notes", []).append(
            "closed_count_field_not_implemented_yet — ratio open/closed not"
            " meaningful; only open_count + stale trend可用"
        )

    novelty_raw = bench.get("novelty_records", []) or []
    novelty_samples = [
        NoveltySample(
            tick=n["tick"],
            pattern_count=n.get("pattern_count", 0),
            overall_score=n.get("overall_score", 5),
        )
        for n in novelty_raw
    ]
    nov_curve = novelty_decay_curve(novelty_samples)

    # repetition over the full sequence
    nars = [n["text"] for n in bench.get("narratives", []) if n.get("text", "").strip()]
    rep_view = repetition_report(nars).to_dict()

    # high-level drift indicators
    # 1. open_loop 是否单调上涨 (堆积)
    drift_signals: list[str] = []
    open_series = [s.open_count for s in open_loop_snaps]
    if len(open_series) >= 3 and open_series[-1] > open_series[0] * 1.5:
        drift_signals.append(
            f"open_loop_accumulation: {open_series[0]} → {open_series[-1]} (+{open_series[-1] - open_series[0]})"
        )
    stale_series = [s.stale_open_count for s in open_loop_snaps]
    if stale_series and stale_series[-1] >= 3:
        drift_signals.append(
            f"stale_loops_at_end={stale_series[-1]} (≥3 — 伏笔僵死苗头)"
        )
    # 2. 跨段 overlap 偏高 (长程套路化)
    over = rep_view.get("overlap_consecutive", {})
    if over.get("char_4", 0) > 0.15:
        drift_signals.append(
            f"char-4 cross-tick overlap = {over['char_4']} (>0.15 — 句式套路化)"
        )

    return {
        "label": label,
        "source": bench.get("novel_id", "?"),
        "tick_count": bench.get("ticks", 0),
        "narrations": len(nars),
        "total_tokens": bench.get("total_tokens", 0),
        "longrange": {
            "foreshadowing": fs_dict,
            "novelty": nov_curve.to_dict(),
            "repetition_global": rep_view,
        },
        "drift_signals": drift_signals,
    }


def _render_md(rep: dict) -> str:
    lines = [
        f"# Long-range analysis — {rep['label']}",
        "",
        f"- source: `{rep['source']}`",
        f"- ticks: {rep['tick_count']}, narrations: {rep['narrations']}",
        f"- total_tokens: {rep['total_tokens']}",
        "",
        "## Foreshadowing curve",
        "",
        f"- samples: {rep['longrange']['foreshadowing']['sample_count']}",
        f"- open/closed ratio at end: {rep['longrange']['foreshadowing']['open_to_closed_ratio_at_end']}",
        f"- stale ratio at end: {rep['longrange']['foreshadowing']['stale_ratio_at_end']}",
    ]
    # show per-tick snapshot
    samples = rep["longrange"]["foreshadowing"].get("samples", [])
    if samples:
        lines.extend(["", "| tick | open | stale | closed | avg_urg |", "| ---: | ---: | ---: | ---: | ---: |"])
        for s in samples:
            lines.append(
                f"| {s['tick']} | {s['open']} | {s['stale_open']} | {s['closed']} | {s['avg_urgency']} |"
            )
    notes = rep["longrange"]["foreshadowing"].get("notes", [])
    if notes:
        lines += ["", "**foreshadowing notes:**"]
        for n in notes:
            lines.append(f"- {n}")

    nov = rep["longrange"]["novelty"]
    lines += [
        "",
        "## Novelty trend",
        "",
        f"- samples: {nov['sample_count']}",
        f"- mean score: {nov['mean_score']}",
        f"- trend: **{nov['trend']}**",
    ]

    rep_glob = rep["longrange"]["repetition_global"]
    lines += [
        "",
        "## Repetition (global, all narrations as 1 sequence)",
        "",
        f"- narration_count: {rep_glob['narration_count']}",
        f"- distinct char-2/3/4: {rep_glob['distinct']['char_2']} / {rep_glob['distinct']['char_3']} / {rep_glob['distinct']['char_4']}",
        f"- overlap consec char-2/3/4: {rep_glob['overlap_consecutive']['char_2']} / {rep_glob['overlap_consecutive']['char_3']} / {rep_glob['overlap_consecutive']['char_4']}",
    ]

    lines += ["", "## Drift signals", ""]
    if rep["drift_signals"]:
        for d in rep["drift_signals"]:
            lines.append(f"- **{d}**")
    else:
        lines.append("- (no drift signal triggered)")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--label", default="default")
    args = parser.parse_args()

    with open(args.bench, encoding="utf-8") as f:
        bench = json.load(f)
    rep = _build_report(bench, args.label)
    out_dir = _REPO_ROOT / "docs" / "iter"
    json_path = out_dir / f"longrange-{args.label}.json"
    md_path = out_dir / f"longrange-{args.label}.md"
    json_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(rep), encoding="utf-8")
    print(f"[OK] wrote {json_path}")
    print(f"[OK] wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
