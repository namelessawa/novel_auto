"""Phase 5-D follow-up #3 — cross-seed long-range drift verdict aggregator.

Reads N bench JSON files (each = a single seed × N tick stress bench) and
produces a unified markdown verdict comparing drift signals across seeds.

Goal: confirm Phase 5-B (world stale-skip) doesn't introduce drift on
plot-medium / plot-dense themes, not just plot-light steampunk default.

Metrics extracted per seed (no LLM calls — pure data aggregation):
* completed_ticks vs target — crash check
* total tokens + avg tokens/tick — cost monotonicity
* narrative chars in first N ticks vs last N ticks — output growth/decline
* stale_skip rate (tick durations < 1s as proxy) — Phase 5-B activity
* open_loop count progression — drift indicator
* narration rate — sample density

Usage:
    python scripts/verdict_longrange_cross_seed.py \\
        --bench seed1=docs/iter/bench-phase5j-longrange-200tick.json \\
        --bench seed2=docs/iter/bench-phase5j-longrange-seed2-republic.json \\
        --bench seed3=docs/iter/bench-phase5j-longrange-seed3-apocalypse.json \\
        --output docs/iter/verdict-phase5j-3seed-longrange.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SeedReport:
    name: str
    bench_path: Path
    label: str
    ticks_completed: int
    ticks_target: int
    total_tokens: int
    tokens_per_tick_avg: float
    narrative_chars_total: int
    narrative_chars_first_half: int
    narrative_chars_last_half: int
    narration_rate: float
    stale_skip_count: int
    stale_skip_rate: float
    open_loop_progression: list[tuple[int, int, int]]
    by_agent_top: list[tuple[str, int]]
    error: str | None = None


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _summarize(name: str, bench_path: Path) -> SeedReport:
    try:
        d = _load(bench_path)
    except Exception as e:
        return SeedReport(
            name=name,
            bench_path=bench_path,
            label="",
            ticks_completed=0,
            ticks_target=0,
            total_tokens=0,
            tokens_per_tick_avg=0.0,
            narrative_chars_total=0,
            narrative_chars_first_half=0,
            narrative_chars_last_half=0,
            narration_rate=0.0,
            stale_skip_count=0,
            stale_skip_rate=0.0,
            open_loop_progression=[],
            by_agent_top=[],
            error=f"load failed: {type(e).__name__}: {e}",
        )

    completed = int(d.get("completed_ticks") or d.get("ticks") or 0)
    target = int(d.get("ticks") or 0)
    total_tokens = int(d.get("total_tokens") or 0)
    tpt = total_tokens / max(1, completed)

    narratives = d.get("narratives") or []
    chars_total = sum(len((n.get("text") or "")) for n in narratives)
    half = completed // 2 if completed else 0
    first_chars = sum(
        len(n.get("text") or "")
        for n in narratives
        if int(n.get("tick", 0)) <= half
    )
    last_chars = chars_total - first_chars
    narration_rate = len(narratives) / max(1, completed)

    durations = d.get("tick_durations_sec") or []
    stale_count = sum(1 for x in durations if isinstance(x, (int, float)) and x < 1.0)
    stale_rate = stale_count / max(1, len(durations))

    olsnaps = d.get("open_loop_snapshots") or []
    ol_prog = [
        (
            int(s.get("tick", 0)),
            int(s.get("open", s.get("count", 0)) or 0),
            int(s.get("stale", 0) or 0),
        )
        for s in olsnaps
    ]

    by_agent_dict = d.get("by_agent_cumulative") or {}
    by_agent_top = sorted(by_agent_dict.items(), key=lambda kv: -kv[1])[:5]

    return SeedReport(
        name=name,
        bench_path=bench_path,
        label=str(d.get("label") or ""),
        ticks_completed=completed,
        ticks_target=target,
        total_tokens=total_tokens,
        tokens_per_tick_avg=round(tpt, 1),
        narrative_chars_total=chars_total,
        narrative_chars_first_half=first_chars,
        narrative_chars_last_half=last_chars,
        narration_rate=round(narration_rate, 4),
        stale_skip_count=stale_count,
        stale_skip_rate=round(stale_rate, 4),
        open_loop_progression=ol_prog,
        by_agent_top=by_agent_top,
    )


def _drift_verdict(r: SeedReport) -> str:
    """One-line PASS / WARN / FAIL on Phase 5-B drift criteria."""
    if r.error:
        return f"ERROR ({r.error})"
    if r.ticks_completed < r.ticks_target:
        return f"INCOMPLETE ({r.ticks_completed}/{r.ticks_target})"
    # Drift criteria (mirror verdict-phase5j-longrange-200tick.md):
    # 1. completion 100% (already checked)
    # 2. last-half narrative chars >= first-half × 0.7 (no narrator silence shift)
    # 3. open_loops final - initial >= 0 (no foreshadowing collapse)
    first_h = max(1, r.narrative_chars_first_half)
    last_ratio = r.narrative_chars_last_half / first_h
    if r.open_loop_progression:
        ol_initial = r.open_loop_progression[0][1]
        ol_final = r.open_loop_progression[-1][1]
    else:
        ol_initial = ol_final = 0
    notes = []
    if last_ratio < 0.7:
        notes.append(f"narrator output -{(1 - last_ratio) * 100:.0f}% second half")
    if ol_final < ol_initial - 2:
        notes.append(f"open_loops {ol_initial}→{ol_final} (collapse)")
    if notes:
        return f"WARN — {'; '.join(notes)}"
    return "PASS"


def _render_md(reports: list[SeedReport]) -> str:
    lines = [
        "# Phase 5-J cross-seed long-range stress verdict",
        "",
        f"- seeds: {len(reports)} ({[r.name for r in reports]})",
        "- gate: Phase 5-B stale-skip 在 cross-theme 长程不 drift?",
        "- 标准: completion 100% + last-half narrative chars >= first-half × 0.7 "
        "+ open_loops 无 collapse (-3+)",
        "",
        "## Per-seed summary",
        "",
        "| seed | label | completed | tokens | tpt | narr chars | rate | "
        "stale% | drift |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in reports:
        lines.append(
            f"| {r.name} | {r.label} | {r.ticks_completed}/{r.ticks_target} | "
            f"{r.total_tokens} | {r.tokens_per_tick_avg} | "
            f"{r.narrative_chars_total} | {r.narration_rate * 100:.1f}% | "
            f"{r.stale_skip_rate * 100:.1f}% | {_drift_verdict(r)} |"
        )

    lines += [
        "",
        "## Narrative growth (first vs last half)",
        "",
        "Drift indicator: 后半 narrator 沉默 = WARN. PHASE5_PLAN J seed1 是 +37%.",
        "",
        "| seed | first half chars | last half chars | delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for r in reports:
        if r.narrative_chars_first_half:
            delta_pct = (
                r.narrative_chars_last_half / r.narrative_chars_first_half - 1.0
            ) * 100
            delta_str = f"{delta_pct:+.1f}%"
        else:
            delta_str = "n/a"
        lines.append(
            f"| {r.name} | {r.narrative_chars_first_half} | "
            f"{r.narrative_chars_last_half} | {delta_str} |"
        )

    lines += [
        "",
        "## Open-loop progression",
        "",
        "Drift indicator: open_loops 单调累积 = Stage 3 baseline 信号; Phase 5-B "
        "+ Phase 4-E sideline 应该让其稳定. -3+ collapse = WARN.",
        "",
    ]
    for r in reports:
        lines.append(f"### {r.name}")
        if not r.open_loop_progression:
            lines.append("(no open_loop_snapshots)")
            lines.append("")
            continue
        lines.append("| tick | open | stale |")
        lines.append("| ---: | ---: | ---: |")
        # show first 3 + last 3 to keep readable
        snaps = r.open_loop_progression
        if len(snaps) <= 8:
            sel = snaps
        else:
            sel = snaps[:3] + [("…", "…", "…")] + snaps[-3:]
        for t, o, s in sel:
            lines.append(f"| {t} | {o} | {s} |")
        lines.append("")

    lines += [
        "## Per-agent breakdown",
        "",
        "| seed | top-5 agents (tokens) |",
        "| --- | --- |",
    ]
    for r in reports:
        top = " / ".join(f"{a}={t}" for a, t in r.by_agent_top)
        lines.append(f"| {r.name} | {top or '(no data)'} |")

    pass_count = sum(1 for r in reports if _drift_verdict(r) == "PASS")
    lines += [
        "",
        "## Gate decision",
        "",
        f"- PASS seeds: **{pass_count} / {len(reports)}**",
    ]
    if pass_count == len(reports):
        lines.append(
            "- **GATE PASS — SHIP confirmed**: Phase 5-B stale-skip 在 "
            f"{len(reports)} 个 theme 上长程都不 drift."
        )
    elif pass_count >= len(reports) - 1 and len(reports) >= 3:
        lines.append(
            f"- MARGINAL: {pass_count}/{len(reports)} seeds PASS. 1 seed WARN/ERROR. "
            "建议复跑或检查特定 theme."
        )
    else:
        lines.append(
            f"- **GATE FAIL — REVISIT**: {len(reports) - pass_count}/{len(reports)} "
            "seeds 出现 drift. Phase 5-B 不能跨 theme 一致 ship."
        )
    return "\n".join(lines) + "\n"


def _parse_bench(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise argparse.ArgumentTypeError(
            f"--bench must be 'name=path', got {spec!r}"
        )
    name, path = spec.split("=", 1)
    return name.strip(), Path(path.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bench",
        action="append",
        required=True,
        type=_parse_bench,
        help="seed_name=path/to/bench.json (repeat for each seed)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="verdict markdown output path",
    )
    args = parser.parse_args()

    reports = [_summarize(name, path) for name, path in args.bench]
    md = _render_md(reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    print(f"wrote {args.output}")
    for r in reports:
        print(
            f"  {r.name}: {_drift_verdict(r)} — "
            f"{r.ticks_completed}/{r.ticks_target} ticks, "
            f"{r.narrative_chars_total} chars"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
