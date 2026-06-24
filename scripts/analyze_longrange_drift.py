"""Phase 6-A 长程 drift analyzer — bench JSON 后处理.

> 用法:
>     python scripts/analyze_longrange_drift.py docs/iter/bench-phase6a-500tick-seed1.json
>
> 输出:
>     stdout 6 个 drift 信号的 50-bucket 分桶报告
>     [optional] --out-md docs/iter/longrange-drift-{label}.md 落盘

读 ``bench_tick.py`` 的 JSON, 按 50-tick 一桶切, 报告 6 个 drift 信号:

1. avg_dur_per_tick — 每 tick 平均耗时是否随 bucket 单调上升?
2. total_tokens_cumulative slope — token 累计是否超线性?
3. narrator clean_rate — clean output (无 surviving codes) 比例是否下跌?
4. open_loops snapshot 高位 — 是否长期顶住 cap (说明不能关 loop)?
5. memory_compressor 触发 — 是否每 ~50 tick 至少触发一次?
6. consistency_guardian contradictions 累计 — 是否爆?

阈值在脚本顶部 _DRIFT_THRESHOLDS, 与 PHASE6A_500TICK_RUNBOOK.md §3 对齐.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_DRIFT_THRESHOLDS = {
    "avg_dur_multiplier": 1.5,  # bucket > start_bucket × this → WARN
    "clean_rate_drop_pp": 15.0,  # clean% 下降 ≥ this percentage points → WARN
    "open_loop_cap": 6,  # 默认 EVENT_INJECTOR_OPEN_LOOP_CAP
    "open_loop_long_high_pct": 0.7,  # bucket 内 ≥ 70% 时间顶住 cap → WARN
    "memory_compress_min_per_bucket": 1,  # 每 50-tick bucket 至少 1 次
}

_BUCKET_SIZE = 50


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _bucket_index(tick: int) -> int:
    return (tick - 1) // _BUCKET_SIZE


def _bucketize_tick_records(
    per_tick: list[dict], bucket_size: int = _BUCKET_SIZE
) -> dict[int, list[dict]]:
    """Group per_tick records by 50-tick bucket id."""
    buckets: dict[int, list[dict]] = {}
    for rec in per_tick:
        t = rec.get("tick") or rec.get("tick_num")
        if not isinstance(t, int):
            continue
        bid = _bucket_index(t)
        buckets.setdefault(bid, []).append(rec)
    return buckets


def _bucket_label(bid: int) -> str:
    return f"t{bid * _BUCKET_SIZE + 1:>4}–{(bid + 1) * _BUCKET_SIZE:>4}"


def _avg(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def analyze(report: dict) -> dict:
    """Return drift findings dict + per-bucket stats."""
    per_tick = report.get("per_tick") or []
    if not per_tick:
        return {"error": "no per_tick records"}

    buckets = _bucketize_tick_records(per_tick)
    bucket_ids = sorted(buckets.keys())

    per_bucket: list[dict] = []
    for bid in bucket_ids:
        recs = buckets[bid]
        # avg duration — bench_tick records per-tick "duration_sec" or via
        # global tick_durations_sec parallel array. Try both.
        durs: list[float] = []
        for r in recs:
            d = r.get("duration_sec") or r.get("duration")
            if isinstance(d, (int, float)):
                durs.append(float(d))
        # tokens — total cumulative for this tick (delta from previous tick is
        # harder; use cumulative and diff at bucket level).
        toks: list[int] = []
        for r in recs:
            t = r.get("cumulative_tokens") or r.get("tokens_used") or r.get("tokens")
            if isinstance(t, (int, float)):
                toks.append(int(t))
        clean = [
            1
            for r in recs
            if not (r.get("critic_surviving_codes") or r.get("surviving_codes"))
        ]
        open_loop_counts = [
            r.get("open_loop_count")
            for r in recs
            if isinstance(r.get("open_loop_count"), int)
        ]
        memcompress = sum(
            1
            for r in recs
            if "MemoryCompressor" in (r.get("agents_called") or [])
        )
        contradictions = [
            r.get("contradiction_count")
            for r in recs
            if isinstance(r.get("contradiction_count"), int)
        ]
        per_bucket.append(
            {
                "bucket": _bucket_label(bid),
                "n": len(recs),
                "avg_dur_sec": round(_avg(durs), 1) if durs else None,
                "cumulative_tokens_at_end": toks[-1] if toks else None,
                "clean_rate_pct": (
                    round(100.0 * len(clean) / len(recs), 1) if recs else 0
                ),
                "open_loop_avg": (
                    round(_avg(open_loop_counts), 1) if open_loop_counts else None
                ),
                "open_loop_at_cap_pct": (
                    round(
                        100.0
                        * sum(
                            1
                            for x in open_loop_counts
                            if x >= _DRIFT_THRESHOLDS["open_loop_cap"]
                        )
                        / max(1, len(open_loop_counts)),
                        1,
                    )
                    if open_loop_counts
                    else None
                ),
                "memcompress_hits": memcompress,
                "contradictions_last": (
                    contradictions[-1] if contradictions else None
                ),
            }
        )

    findings: list[str] = []

    if len(per_bucket) >= 2:
        first = per_bucket[0]
        for b in per_bucket[1:]:
            if first["avg_dur_sec"] and b["avg_dur_sec"]:
                ratio = b["avg_dur_sec"] / first["avg_dur_sec"]
                if ratio > _DRIFT_THRESHOLDS["avg_dur_multiplier"]:
                    findings.append(
                        f"[D1] avg_dur drift: {b['bucket']} avg_dur "
                        f"{b['avg_dur_sec']}s = {ratio:.2f}× start "
                        f"({first['avg_dur_sec']}s) — slow drift"
                    )

        for b in per_bucket[1:]:
            drop = first["clean_rate_pct"] - b["clean_rate_pct"]
            if drop > _DRIFT_THRESHOLDS["clean_rate_drop_pp"]:
                findings.append(
                    f"[D2] clean_rate drop: {b['bucket']} clean "
                    f"{b['clean_rate_pct']}% vs start {first['clean_rate_pct']}% "
                    f"(-{drop:.1f}pp)"
                )

    for b in per_bucket:
        if (
            b["open_loop_at_cap_pct"] is not None
            and b["open_loop_at_cap_pct"]
            >= _DRIFT_THRESHOLDS["open_loop_long_high_pct"] * 100
        ):
            findings.append(
                f"[D3] open_loop cap pressure: {b['bucket']} "
                f"{b['open_loop_at_cap_pct']}% ticks at cap "
                f"(≥{_DRIFT_THRESHOLDS['open_loop_cap']})"
            )

    for b in per_bucket:
        if b["memcompress_hits"] < _DRIFT_THRESHOLDS["memory_compress_min_per_bucket"]:
            findings.append(
                f"[D4] memory_compress silent: {b['bucket']} hits="
                f"{b['memcompress_hits']} (expected ≥ "
                f"{_DRIFT_THRESHOLDS['memory_compress_min_per_bucket']})"
            )

    if per_bucket and per_bucket[-1]["contradictions_last"]:
        last = per_bucket[-1]["contradictions_last"]
        if last and last > 300:
            findings.append(
                f"[D5] contradictions cascade: ending count = {last} "
                "(threshold 300)"
            )

    if (
        len(per_bucket) >= 2
        and per_bucket[0]["cumulative_tokens_at_end"]
        and per_bucket[-1]["cumulative_tokens_at_end"]
    ):
        per_bucket_token_growth: list[float] = []
        prev = per_bucket[0]["cumulative_tokens_at_end"]
        for b in per_bucket[1:]:
            cur = b["cumulative_tokens_at_end"]
            if cur and prev:
                per_bucket_token_growth.append(cur - prev)
            prev = cur or prev
        if per_bucket_token_growth:
            base = per_bucket_token_growth[0]
            for i, gw in enumerate(per_bucket_token_growth[1:], 1):
                if base > 0 and gw / base > 1.5:
                    findings.append(
                        f"[D6] token cascade: bucket {per_bucket[i+1]['bucket']} "
                        f"+{gw:,} vs first bucket +{base:,} = "
                        f"{gw/base:.2f}×"
                    )
                    break

    return {
        "label": report.get("label"),
        "ticks_target": report.get("ticks"),
        "ticks_completed": report.get("completed_ticks"),
        "n_buckets": len(per_bucket),
        "per_bucket": per_bucket,
        "drift_findings": findings,
        "overall_verdict": (
            "PASS" if not findings
            else "WARN" if len(findings) <= 2
            else "FAIL"
        ),
    }


def render_md(out: dict) -> str:
    lines = ["# Long-range drift analysis\n"]
    lines.append(
        f"* label: `{out.get('label')}` · ticks {out.get('ticks_completed')}/"
        f"{out.get('ticks_target')} · {out.get('n_buckets')} buckets\n"
    )
    lines.append(f"* **verdict: {out.get('overall_verdict')}**\n")
    if out.get("drift_findings"):
        lines.append("\n## Findings\n")
        for f in out["drift_findings"]:
            lines.append(f"* {f}")
    else:
        lines.append("\n## Findings\n* (none — all 6 drift signals within range)")
    lines.append("\n## Per-bucket\n")
    lines.append(
        "| bucket | n | avg_dur | cum_tok end | clean% | OL avg | OL@cap% | memC | contradictions |"
    )
    lines.append(
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    for b in out.get("per_bucket", []):
        lines.append(
            f"| {b['bucket']} | {b['n']} | {b['avg_dur_sec']}s | "
            f"{b['cumulative_tokens_at_end']:,}" if b['cumulative_tokens_at_end'] else
            f"| {b['bucket']} | {b['n']} | — | —"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("bench_json", help="path to docs/iter/bench-{label}.json")
    p.add_argument("--out-md", default="")
    args = p.parse_args()

    path = Path(args.bench_json)
    if not path.is_file():
        print(f"ERR bench json not found: {path}", file=sys.stderr)
        return 2
    report = _load(path)
    out = analyze(report)

    if "error" in out:
        print(f"ERR: {out['error']}", file=sys.stderr)
        return 2

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    if args.out_md:
        out_md = Path(args.out_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(render_md(out), encoding="utf-8")
        print(f"\nout: {out_md}", file=sys.stderr)
    return 0 if out["overall_verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
