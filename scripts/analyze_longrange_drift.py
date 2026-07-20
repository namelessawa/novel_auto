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
    # iter#Z — D7: ≥ N consecutive buckets with narrate_rate ≥ threshold → 报
    # narrate-rate cascade. Phase 6-A run 1 stuck-state pattern (t201-300 100%).
    "d7_narrate_threshold": 0.70,  # bucket narrate_rate ≥ this 算入 cascade
    "d7_min_buckets": 2,  # 连续 ≥ this 个 bucket 才报
}


def _env_float(key: str, default: float) -> float:
    """Lazy env read for analyzer thresholds (test monkeypatch friendly)."""
    import os
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    import os
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

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

    # 新 schema 直接记录 cumulative_tokens；老 bench 至少有 tick_total_tokens，
    # 可无损重建本次 run 内的累计曲线。两者都没有时才保持 unknown。
    cumulative_by_tick: dict[int, int] = {}
    running_tokens = 0
    for rec in sorted(
        per_tick, key=lambda item: item.get("tick") or item.get("tick_num") or 0
    ):
        tick = rec.get("tick") or rec.get("tick_num")
        if not isinstance(tick, int):
            continue
        explicit = rec.get("cumulative_tokens")
        if not isinstance(explicit, (int, float)):
            explicit = rec.get("tokens_used") or rec.get("tokens")
        if isinstance(explicit, (int, float)):
            running_tokens = int(explicit)
            cumulative_by_tick[tick] = running_tokens
            continue
        delta = rec.get("tick_total_tokens")
        if isinstance(delta, (int, float)):
            running_tokens += int(delta)
            cumulative_by_tick[tick] = running_tokens

    loop_snapshots_by_bucket: dict[int, list[int]] = {}
    for snapshot in report.get("open_loop_snapshots") or []:
        tick = snapshot.get("tick") if isinstance(snapshot, dict) else None
        count = snapshot.get("open") if isinstance(snapshot, dict) else None
        if isinstance(tick, int) and isinstance(count, int):
            loop_snapshots_by_bucket.setdefault(_bucket_index(tick), []).append(count)

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
        toks = [
            cumulative_by_tick[tick]
            for r in recs
            for tick in [r.get("tick") or r.get("tick_num")]
            if isinstance(tick, int) and tick in cumulative_by_tick
        ]
        critic_observed: list[dict] = []
        for r in recs:
            if r.get("critic_evaluated") is True:
                critic_observed.append(r)
            elif "critic_evaluated" not in r and (
                "critic_surviving_codes" in r or "surviving_codes" in r
            ):
                critic_observed.append(r)
        clean = [
            1 for r in critic_observed
            if not (r.get("critic_surviving_codes") or r.get("surviving_codes"))
        ]
        open_loop_counts = [
            r.get("open_loop_count")
            for r in recs
            if isinstance(r.get("open_loop_count"), int)
        ]
        if not open_loop_counts:
            open_loop_counts = loop_snapshots_by_bucket.get(bid, [])
        # bench_tick.py per_tick records leave agents_called=[] in current
        # schema, so "MemoryCompressor" in agents_called is a perma-FP. The
        # honest signal is in `by_agent_tokens` per-tick (when present) or
        # `cumulative_tokens` deltas. Until per_tick gets memcompress traces,
        # we skip D4 for individual buckets and re-derive at the report level
        # via by_agent_cumulative growth (see post-bucket loop below).
        memcompress = sum(
            1
            for r in recs
            if any(
                "memory_compressor" in k.lower()
                or "memorycompressor" in k.lower()
                for k in (r.get("agents_called") or [])
            )
        )
        contradictions = [
            r.get("contradiction_count")
            for r in recs
            if isinstance(r.get("contradiction_count"), int)
        ]
        # iter#Z — narrate_rate per bucket (依赖 iter#K 加的 narrator_produced 字段).
        # 老 schema 无此字段 → 返回 None (D7 detection 跳过).
        produced_flags = [
            r.get("narrator_produced") for r in recs
            if "narrator_produced" in r
        ]
        narrate_rate = (
            sum(1 for x in produced_flags if x) / len(produced_flags)
            if produced_flags
            else None
        )
        per_bucket.append(
            {
                "bucket": _bucket_label(bid),
                "n": len(recs),
                "avg_dur_sec": round(_avg(durs), 1) if durs else None,
                "cumulative_tokens_at_end": toks[-1] if toks else None,
                "narrate_rate": (
                    round(narrate_rate, 3) if narrate_rate is not None else None
                ),
                "clean_rate_pct": (
                    round(100.0 * len(clean) / len(critic_observed), 1)
                    if critic_observed else None
                ),
                "critic_evaluated_ticks": len(critic_observed),
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
                "compression_expected": any(
                    (r.get("tick") or r.get("tick_num"))
                    == (bid + 1) * _BUCKET_SIZE
                    for r in recs
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
            if (
                first["clean_rate_pct"] is None
                or b["clean_rate_pct"] is None
            ):
                continue
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

    # D4 — bench schema currently does NOT populate per-tick agents_called,
    # so per-bucket memcompress count is unreliable. We instead derive D4 at
    # the REPORT level: if by_agent_cumulative['memory_compressor:l0_l1'] is
    # zero AND completed_ticks >= 50, that's a real silent-compressor signal.
    by_agent = report.get("by_agent_cumulative") or {}
    mem_keys = [k for k in by_agent.keys() if "memory_compressor" in k.lower()]
    mem_tokens = sum(by_agent.get(k, 0) for k in mem_keys)
    completed = report.get("completed_ticks") or 0
    if completed >= 50 and mem_tokens == 0:
        findings.append(
            f"[D4] memory_compressor silent: 0 tokens across {completed} ticks "
            f"— L0→L1 never ran (expected at least once per ~50 ticks)"
        )

    # iter#S — Per-bucket D4 upgrade (依赖 iter#K schema). Only fire when
    # schema is "new" (at least one tick in this report has non-empty
    # agents_called) — 否则 legacy bench JSON 会 FP 报 D4 across all buckets.
    has_new_schema = any(
        bool(r.get("agents_called"))
        for r in per_tick
        if isinstance(r, dict)
    )
    if has_new_schema:
        threshold = _DRIFT_THRESHOLDS["memory_compress_min_per_bucket"]
        for b in per_bucket:
            if b["compression_expected"] and b["memcompress_hits"] < threshold:
                findings.append(
                    f"[D4-bucket] memory_compressor silent in bucket "
                    f"{b['bucket']}: {b['memcompress_hits']} hits "
                    f"(expected ≥ {threshold})"
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

    # iter#Z — D7 narrate-rate cascade detection.
    # ≥ MIN_BUCKETS consecutive buckets with narrate_rate ≥ THRESHOLD → 报.
    # Phase 6-A run 1 (24 日) t201-300 全 100% narrate 4 个 bucket 直到 quota wall —
    # 这正是 D7 想抓的 pattern. iter#M (guard) 是预防, D7 是 post-hoc detection.
    d7_thr = _env_float(
        "D7_NARRATE_THRESHOLD", _DRIFT_THRESHOLDS["d7_narrate_threshold"]
    )
    d7_min = _env_int(
        "D7_MIN_BUCKETS", _DRIFT_THRESHOLDS["d7_min_buckets"]
    )
    consec = 0
    cascade_start = None
    cascade_end = None
    for b in per_bucket:
        rate = b.get("narrate_rate")
        if rate is None:
            # 老 schema 无 narrator_produced → skip D7 整段 (重置 streak).
            consec = 0
            cascade_start = None
            continue
        if rate >= d7_thr:
            if consec == 0:
                cascade_start = b["bucket"]
            consec += 1
            cascade_end = b["bucket"]
        else:
            if consec >= d7_min:
                findings.append(
                    f"[D7] narrate-rate cascade: {consec} consecutive buckets "
                    f"≥ {int(d7_thr * 100)}% narrate ({cascade_start} → {cascade_end}) "
                    "— Phase 6-A run 1 stuck-state pattern"
                )
            consec = 0
            cascade_start = None
    # Tail flush — 如 cascade 延伸到最后 bucket
    if consec >= d7_min:
        findings.append(
            f"[D7] narrate-rate cascade: {consec} consecutive buckets "
            f"≥ {int(d7_thr * 100)}% narrate ({cascade_start} → {cascade_end}) "
            "— Phase 6-A run 1 stuck-state pattern"
        )

    # iter#TTT — D8 quota wall detection. ≥1 bucket avg_dur < threshold (+
    # narrate_rate < 5% if new schema). Phase 6-A Run 1 + Republic_spy 都触底
    # quota, 后段 LLM 429 退化 (orchestrator 跑 7 阶段但 LLM no-op, avg_dur
    # 0.3-0.7s, narrate 0%). 显式 flag 让 verdict 不把 quota-degenerate
    # 视作 healthy bucket. 0 = disable.
    d8_avg_dur_max = _env_float("D8_AVG_DUR_MAX", 5.0)
    d8_narrate_max = _env_float("D8_NARRATE_MAX", 0.05)
    if d8_avg_dur_max > 0:
        quota_buckets = []
        for b in per_bucket:
            # D8 是 50-Tick bucket 级信号。短冒烟中几个合法低价值 silent
            # tick 同样会呈现“低时延 + 0% narrate”，不能在周期未结束时当 quota wall。
            if not b.get("compression_expected"):
                continue
            dur = b.get("avg_dur_sec")
            if dur is None or dur >= d8_avg_dur_max:
                continue
            rate = b.get("narrate_rate")
            # rate=None (老 schema): 仅按 avg_dur 判.
            # rate < threshold (新 schema): quota wall.
            if rate is None or rate < d8_narrate_max:
                quota_buckets.append(b["bucket"])
        if quota_buckets:
            findings.append(
                f"[D8] quota wall: {len(quota_buckets)} bucket(s) avg_dur < "
                f"{d8_avg_dur_max}s + narrate < {int(d8_narrate_max * 100)}% "
                f"({', '.join(quota_buckets[:3])}"
                f"{'…' if len(quota_buckets) > 3 else ''}) — LLM 429 退化模式"
            )

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
    """iter#V — Render drift analysis as markdown. 老版 row builder 因
    inline ternary 把 f-string 拼坏 (只输出部分 cell). 重写为 explicit
    cell list + .join. 加 D7 narrate_rate 列 (iter#Z), 修 memC hits 列.
    """
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
        lines.append("\n## Findings\n* (none — all 7 drift signals within range)")
    lines.append("\n## Per-bucket\n")
    # 列: bucket | n | avg_dur | cum_tok end | narrate_rate | clean% | OL avg |
    #     OL@cap% | memC | contradictions
    header = (
        "| bucket | n | avg_dur | cum_tok end | narrate% | clean% | "
        "OL avg | OL@cap% | memC | contradictions |"
    )
    sep = "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"
    lines.append(header)
    lines.append(sep)
    for b in out.get("per_bucket", []):
        cells = [
            str(b.get("bucket") or "—"),
            str(b.get("n") or 0),
            f"{b['avg_dur_sec']}s" if b.get("avg_dur_sec") is not None else "—",
            f"{b['cumulative_tokens_at_end']:,}"
            if b.get("cumulative_tokens_at_end") else "—",
            f"{int(round(b['narrate_rate'] * 100))}%"
            if b.get("narrate_rate") is not None else "—",
            f"{b['clean_rate_pct']}%" if b.get("clean_rate_pct") is not None else "—",
            f"{b['open_loop_avg']}" if b.get("open_loop_avg") is not None else "—",
            f"{b['open_loop_at_cap_pct']}%"
            if b.get("open_loop_at_cap_pct") is not None else "—",
            str(b.get("memcompress_hits", 0)),
            f"{b['contradictions_last']}"
            if b.get("contradictions_last") is not None else "—",
        ]
        lines.append("| " + " | ".join(cells) + " |")
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
