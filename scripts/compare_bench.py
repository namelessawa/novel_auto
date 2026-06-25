"""Phase 6 iter#TT3 — bench-compare: 多 bench JSON side-by-side 对比.

Phase 6-A 之后 cross-seed (republic_spy + apocalypse_wasteland) bench
完成时, 手工对比 3 个 JSON 太烦. 本 script 一行 batch 出 markdown 表:

    python scripts/compare_bench.py \\
        docs/iter/bench-phase6a-500tick-seed1-retry-0625.json \\
        docs/iter/bench-phase6a-500tick-republic-iterN.json \\
        docs/iter/bench-phase6a-500tick-apocalypse-iterN.json \\
        > docs/iter/verdict-3seed-compare.md

输出 columns: label / completed_ticks / total_tokens / avg_dur / narrate% /
top burner / drift findings count / verdict (PASS/WARN/FAIL).

接 analyze_longrange_drift.py — 每个 bench 跑 analyze, 拼一行.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import analyze_longrange_drift  # noqa: E402


def _safe_avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _summarize_bench(bench_path: Path) -> dict:
    """Read bench JSON + run analyzer, return single-row summary dict."""
    rep = json.loads(bench_path.read_text(encoding="utf-8"))
    drift = analyze_longrange_drift.analyze(rep)

    durs = rep.get("tick_durations_sec") or []
    narrs = rep.get("narratives") or []
    completed = rep.get("completed_ticks") or 0
    by_agent = rep.get("by_agent_cumulative") or {}
    top = sorted(by_agent.items(), key=lambda kv: -kv[1])[:1]
    top_str = f"{top[0][0]} ({top[0][1]:,})" if top else "—"

    narrate_rate = (
        len(narrs) / completed if completed > 0 else 0.0
    )
    avg_dur = _safe_avg(durs)
    # effective avg: exclude quota-degenerate <1s tail
    effective_durs = [d for d in durs if d >= 1.0]
    avg_dur_eff = _safe_avg(effective_durs)

    return {
        "label": rep.get("label") or bench_path.stem,
        "completed_ticks": completed,
        "target_ticks": rep.get("ticks"),
        "total_tokens": rep.get("total_tokens", 0),
        "call_count": rep.get("call_count", 0),
        "avg_dur_sec": round(avg_dur, 1),
        "avg_dur_eff_sec": round(avg_dur_eff, 1),
        "narratives": len(narrs),
        "narrate_pct": round(narrate_rate * 100, 1),
        "top_burner": top_str,
        "drift_findings": len(drift.get("drift_findings") or []),
        "drift_verdict": drift.get("overall_verdict") or "—",
    }


def _render_table(rows: list[dict]) -> str:
    """Render side-by-side comparison markdown."""
    if not rows:
        return "# bench-compare\n\n(no input)\n"
    lines = ["# bench-compare\n"]
    lines.append(f"> {len(rows)} bench JSON 对比. analyzer = analyze_longrange_drift.py.\n")

    # Per-metric table
    metrics = [
        ("label", "label"),
        ("完成 tick", "completed_ticks_str"),
        ("total tokens", "total_tokens_str"),
        ("LLM calls", "call_count"),
        ("avg dur (effective)", "avg_dur_eff_str"),
        ("narratives", "narratives"),
        ("narrate%", "narrate_pct_str"),
        ("top burner", "top_burner"),
        ("drift findings", "drift_findings"),
        ("drift verdict", "drift_verdict"),
    ]
    # decorate
    for r in rows:
        r["completed_ticks_str"] = f"{r['completed_ticks']}/{r['target_ticks']}"
        r["total_tokens_str"] = f"{r['total_tokens']:,}"
        r["avg_dur_eff_str"] = f"{r['avg_dur_eff_sec']}s"
        r["narrate_pct_str"] = f"{r['narrate_pct']}%"

    # Header
    head = "| metric | " + " | ".join(r["label"] for r in rows) + " |"
    sep = "| --- | " + " | ".join(["---:" for _ in rows]) + " |"
    lines.append(head)
    lines.append(sep)
    for label, key in metrics:
        if key == "label":
            continue
        vals = " | ".join(str(r.get(key, "—")) for r in rows)
        lines.append(f"| {label} | {vals} |")

    # Drift verdict summary
    lines.append("\n## Drift verdict 汇总\n")
    for r in rows:
        verdict = r["drift_verdict"]
        emoji = "✓" if verdict == "PASS" else ("⚠" if verdict == "WARN" else "❌")
        lines.append(f"* {emoji} **{r['label']}**: {verdict} ({r['drift_findings']} findings)")

    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="多 bench JSON side-by-side 对比")
    p.add_argument(
        "bench_paths",
        nargs="+",
        help="bench JSON 路径 (docs/iter/bench-*.json), 顺序保留到输出表",
    )
    p.add_argument(
        "--out-md",
        default="",
        help="可选 markdown 输出路径 (默认 stdout). Windows GBK stdout 友好.",
    )
    args = p.parse_args()

    rows = []
    for s in args.bench_paths:
        path = Path(s)
        if not path.is_file():
            print(f"ERR bench JSON not found: {s}", file=sys.stderr)
            return 2
        try:
            rows.append(_summarize_bench(path))
        except (json.JSONDecodeError, KeyError) as e:
            print(f"ERR parsing {s}: {e}", file=sys.stderr)
            return 2

    md = _render_table(rows)
    if args.out_md:
        out_path = Path(args.out_md)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"[OK] wrote {out_path}")
    else:
        # stdout UTF-8 友好 (Windows GBK 不支持 emoji ❌). 用 sys.stdout.buffer.
        try:
            sys.stdout.buffer.write(md.encode("utf-8"))
        except AttributeError:
            # IDLE / 非 buffer stdout — 退到普通 print, emoji ascii 化.
            print(md.encode("ascii", errors="replace").decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
