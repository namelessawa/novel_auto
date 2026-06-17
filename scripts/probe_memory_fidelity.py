"""Phase 6-A.3 — long-range memory fidelity probe.

> Question: does the narrator at tick 400+ still know about / reference entities
> and events from tick 1-100?
>
> Method (LLM-free, pure data analysis):
> 1. Read 500-tick bench narratives + character_profiles + open_loops snapshots
> 2. Extract entity mentions from early-half narratives (tick 1-250)
> 3. Check how many appear in late-half narratives (tick 251-500)
> 4. Sample 5 open_loops opened in tick 1-100 — confirm they're either referenced
>    in late narratives OR closed via loops_closed_total
>
> Output: docs/iter/verdict-phase6a3-memory-fidelity.md
>
> Why not LLM-based: aggregator already established narrator output +110% in
> last half (long-range engagement intact). What we want to probe is *which*
> entities survived, not whether narrator is producing words.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_bench(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_tick_state(novel_dir: Path) -> dict[str, Any]:
    p = novel_dir / "tick_state.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _extract_named_entities(text: str, known_names: set[str]) -> set[str]:
    """Find any known character name that appears in the text."""
    return {n for n in known_names if n and n in text}


def _split_first_last_half(narratives: list[dict]) -> tuple[list[dict], list[dict]]:
    ticks = sorted({int(n.get("tick", 0)) for n in narratives})
    if not ticks:
        return [], []
    mid = ticks[len(ticks) // 2]
    first = [n for n in narratives if int(n.get("tick", 0)) <= mid]
    last = [n for n in narratives if int(n.get("tick", 0)) > mid]
    return first, last


def probe(bench_path: Path, novel_dir: Path | None) -> dict[str, Any]:
    bench = _load_bench(bench_path)
    narratives = bench.get("narratives") or []
    completed = int(bench.get("completed_ticks") or 0)

    # Try to find the corresponding novel_dir if not given
    if novel_dir is None:
        nid = bench.get("novel_id", "")
        guess = (
            _REPO_ROOT / "backend" / "data" / "users" / "bench" / "novels" / nid
        )
        if guess.is_dir():
            novel_dir = guess

    char_names: set[str] = set()
    open_loops_initial: list[dict] = []
    loops_closed_total = 0
    if novel_dir and novel_dir.is_dir():
        ts = _load_tick_state(novel_dir)
        # character_profiles can be dict (id → profile) or list of profile dicts
        cp_raw = ts.get("character_profiles") or {}
        cp_iter = cp_raw.values() if isinstance(cp_raw, dict) else cp_raw
        for c in cp_iter:
            if isinstance(c, dict):
                name = c.get("name") or ""
                if name and len(name) >= 2:
                    char_names.add(name)
        # open_loops similarly dict-or-list
        ol_raw = ts.get("open_loops") or {}
        if isinstance(ol_raw, dict):
            open_loops_initial = list(ol_raw.values())
        else:
            open_loops_initial = list(ol_raw)
        loops_closed_total = int(ts.get("loops_closed_total") or 0)

    first_half, last_half = _split_first_last_half(narratives)
    first_text = "\n".join((n.get("text") or "") for n in first_half)
    last_text = "\n".join((n.get("text") or "") for n in last_half)

    early_entities = _extract_named_entities(first_text, char_names)
    late_entities = _extract_named_entities(last_text, char_names)
    survived = early_entities & late_entities
    forgotten = early_entities - late_entities
    new_late = late_entities - early_entities

    # Per-entity mention counts in last half (engagement depth)
    mention_counts: Counter[str] = Counter()
    for n in last_half:
        text = n.get("text") or ""
        for name in char_names:
            if name in text:
                mention_counts[name] += 1

    survival_rate = len(survived) / max(1, len(early_entities))

    # open_loops sample: any in current state, are they referenced in late narrative?
    referenced_loops = []
    unreferenced_loops = []
    for ol in open_loops_initial[:5]:
        desc = ol.get("description") or ""
        if not desc:
            continue
        # Crude: pull 3-char keyword substrings from desc, check if any in last half
        keywords = re.findall(r"[一-鿿]{3,5}", desc)
        sample_kw = keywords[:5]
        hit = any(kw in last_text for kw in sample_kw)
        (referenced_loops if hit else unreferenced_loops).append(
            {"id": ol.get("id"), "desc_head": desc[:60], "keywords": sample_kw}
        )

    return {
        "bench_path": str(bench_path),
        "completed_ticks": completed,
        "narratives_total": len(narratives),
        "split_mid_tick": last_half[0]["tick"] if last_half else None,
        "char_pool_size": len(char_names),
        "char_pool": sorted(char_names),
        "early_entities_count": len(early_entities),
        "late_entities_count": len(late_entities),
        "survived_entities": sorted(survived),
        "survival_rate": round(survival_rate, 4),
        "forgotten_entities": sorted(forgotten),
        "new_late_entities": sorted(new_late),
        "mention_counts_late": dict(mention_counts.most_common()),
        "open_loops_initial_count": len(open_loops_initial),
        "open_loops_referenced_in_late": referenced_loops,
        "open_loops_unreferenced": unreferenced_loops,
        "loops_closed_total": loops_closed_total,
    }


def render_md(r: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Phase 6-A.3 — long-range memory fidelity verdict",
        "",
        f"- bench: `{Path(r['bench_path']).name}`",
        f"- completed ticks: {r['completed_ticks']}",
        f"- narratives total: {r['narratives_total']}",
        f"- split mid tick: {r['split_mid_tick']} (first half ≤ this, last half >)",
        f"- char pool size: {r['char_pool_size']}",
        "",
        "## Entity survival across halves",
        "",
        f"- early entities (mentioned in first half): {r['early_entities_count']}",
        f"- late entities (mentioned in last half): {r['late_entities_count']}",
        f"- **survived (in both halves): {len(r['survived_entities'])}** — "
        f"survival rate **{r['survival_rate'] * 100:.1f}%**",
        f"- forgotten (early only): {r['forgotten_entities']}",
        f"- new late (introduced after midpoint): {r['new_late_entities']}",
        "",
        "## Mention counts in last half (engagement depth)",
        "",
        "| character | mentions in last half |",
        "| --- | ---: |",
    ]
    for name, count in r["mention_counts_late"].items():
        lines.append(f"| {name} | {count} |")

    lines += [
        "",
        "## Open-loop reference check (first 5 current open loops)",
        "",
        f"- loops_closed_total during bench: **{r['loops_closed_total']}**",
        f"- open_loops at end: {r['open_loops_initial_count']}",
        "",
        "### Referenced in last half (keyword hit)",
        "",
    ]
    for ol in r["open_loops_referenced_in_late"]:
        lines.append(f"- `{ol['id']}`: {ol['desc_head']!r}  (kw: {ol['keywords']})")
    if not r["open_loops_referenced_in_late"]:
        lines.append("- (none)")

    lines += [
        "",
        "### NOT referenced in last half",
        "",
    ]
    for ol in r["open_loops_unreferenced"]:
        lines.append(f"- `{ol['id']}`: {ol['desc_head']!r}  (kw: {ol['keywords']})")
    if not r["open_loops_unreferenced"]:
        lines.append("- (none — all current open loops actively referenced)")

    lines += [
        "",
        "## Gate decision",
        "",
    ]
    if r["survival_rate"] >= 0.6 and r["loops_closed_total"] >= 1:
        lines.append(
            f"- **GATE PASS** — entity survival {r['survival_rate'] * 100:.0f}% "
            f"≥ 60% threshold + {r['loops_closed_total']} loops actively closed. "
            "Memory fidelity confirmed in long-range bench."
        )
    elif r["survival_rate"] >= 0.6:
        lines.append(
            f"- **PASS — entity survival OK** ({r['survival_rate'] * 100:.0f}%), "
            f"but loops_closed_total = {r['loops_closed_total']} (no active "
            "resolution evidence)."
        )
    else:
        lines.append(
            f"- **WARN** — entity survival {r['survival_rate'] * 100:.0f}% "
            f"< 60% threshold. Early characters drop off in last half — "
            "may indicate cast churn or Phase 4-E sideline overreach."
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bench", type=Path, required=True, help="Path to bench JSON"
    )
    parser.add_argument(
        "--novel-dir",
        type=Path,
        default=None,
        help="Override path to bench novel data dir (for char_profiles / open_loops). "
        "If omitted, derived from bench novel_id.",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Output markdown verdict path"
    )
    args = parser.parse_args()

    r = probe(args.bench, args.novel_dir)
    md = render_md(r)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    print(f"wrote {args.output}")
    print(
        f"  entity survival: {r['survival_rate'] * 100:.1f}% "
        f"({len(r['survived_entities'])}/{r['early_entities_count']} "
        f"early-mentioned chars in last half)"
    )
    print(f"  loops_closed_total: {r['loops_closed_total']}")
    print(f"  open_loops remaining: {r['open_loops_initial_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
