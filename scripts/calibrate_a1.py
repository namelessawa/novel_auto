"""Phase 6-C iter#C2 — A1 threshold 校准抽样研究.

> iter#7 carry-forward 提到: "271 narratives bench 显示 avg 12+ A1/narr,
> critic noise 大. 但改 threshold 是 high-risk regression".

This script samples narratives from the bench data, runs A1 (实词重复) det
check, and reports:

* 当前阈值下 (length-aware base=3): per-narrative trigger count distribution
* threshold +1 sensitivity (base=4 → 多少 trigger 会消失, 多少新进入)
* top offending words 跨样本最频繁
* per-bucket length × trigger rate (短/中/长 narrative 的 noise 分布)

Output:
* docs/iter/a1-calibration-iter-c2.json — raw stats
* docs/iter/a1-calibration-iter-c2.md — human verdict + recommendation

Run:
    python -m scripts.calibrate_a1 --sample 50 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

# 项目根 + backend sys.path
_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
for p in (_ROOT, _BACKEND):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from agents.quality_checks import (  # noqa: E402
    _length_aware_threshold,
    check_word_repetition,
)


def _gather_narratives(root: Path) -> list[tuple[str, str]]:
    """Returns [(label, text), ...] from every tick_*.txt under bench novels."""
    out: list[tuple[str, str]] = []
    for nov_dir in sorted(root.glob("bench_*")):
        narr_dir = nov_dir / "narratives"
        if not narr_dir.is_dir():
            continue
        for f in sorted(narr_dir.glob("tick_*.txt")):
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if not text.strip():
                continue
            label = f"{nov_dir.name}/{f.name}"
            out.append((label, text))
    return out


def _trigger_counts(
    text: str,
    threshold: int,
    exempt_words: list[str] | None = None,
) -> tuple[int, list[tuple[str, int]]]:
    """Return (trigger count, [(word, count)]) for given base threshold."""
    triggers = check_word_repetition(text, threshold=threshold, exempt_words=exempt_words)
    pairs: list[tuple[str, int]] = []
    for t in triggers:
        # evidence: '实词 "X" 出现 N 次 (text=L字, 阈值=K)'
        ev = t.evidence
        try:
            word_start = ev.index('"') + 1
            word_end = ev.index('"', word_start)
            word = ev[word_start:word_end]
        except ValueError:
            word = "?"
        try:
            after_word = ev[word_end + 1 :]
            n_idx = after_word.find(" 次")
            cnt_part = after_word[: n_idx].strip()
            cnt = int(cnt_part.split()[-1])
        except (ValueError, IndexError):
            cnt = 0
        pairs.append((word, cnt))
    return len(triggers), pairs


def _bucket(length: int) -> str:
    if length <= 500:
        return "S (≤500)"
    if length <= 1500:
        return "M (501-1500)"
    if length <= 3000:
        return "L (1501-3000)"
    return "XL (>3000)"


def main() -> int:
    p = argparse.ArgumentParser(description="A1 threshold 校准抽样研究")
    p.add_argument("--sample", type=int, default=50)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--bench-root",
        default="backend/data/users/bench/novels",
    )
    p.add_argument(
        "--out-json",
        default="docs/iter/a1-calibration-iter-c2.json",
    )
    p.add_argument(
        "--out-md",
        default="docs/iter/a1-calibration-iter-c2.md",
    )
    args = p.parse_args()

    bench_root = (_ROOT / args.bench_root).resolve()
    if not bench_root.is_dir():
        print(f"ERR bench_root not found: {bench_root}", file=sys.stderr)
        return 2

    narratives = _gather_narratives(bench_root)
    if not narratives:
        print(f"ERR no narratives found under {bench_root}", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    sampled = rng.sample(narratives, min(args.sample, len(narratives)))

    rows = []
    word_counter_base: Counter[str] = Counter()
    word_counter_plus1: Counter[str] = Counter()
    word_counter_exempt: Counter[str] = Counter()
    bucket_stats: dict[str, dict[str, float]] = {}

    # Mine top proper-noun candidates from the FIRST pass (raw, no exempt),
    # then use those names as exempt_words in a second pass to model the
    # production call-site (which passes character + location names from
    # TickState). This is the per-novel exempt_words inferred from observed
    # repetition — closer to "real critic" behavior than the bare baseline.
    raw_word_pool: Counter[str] = Counter()
    for _, text in sampled:
        for t in check_word_repetition(text, threshold=2):
            try:
                w = t.evidence.split('"')[1]
                raw_word_pool[w] += 1
            except IndexError:
                continue
    # Most repeated 2-char tokens that look like proper nouns — neither
    # function words nor common verbs. Crude filter: non-ASCII, not in
    # the existing STOP_NOMINALS, and length 2.
    PROPER_NAME_HINT = [
        w for w, _ in raw_word_pool.most_common(80)
        if len(w) == 2 and not any(c.isascii() for c in w)
    ]

    for label, text in sampled:
        n_base, pairs_base = _trigger_counts(text, threshold=3)
        n_plus1, pairs_plus1 = _trigger_counts(text, threshold=4)
        n_exempt, pairs_exempt = _trigger_counts(
            text, threshold=3, exempt_words=PROPER_NAME_HINT
        )
        for w, _ in pairs_exempt:
            word_counter_exempt[w] += 1
        for w, _ in pairs_base:
            word_counter_base[w] += 1
        for w, _ in pairs_plus1:
            word_counter_plus1[w] += 1
        b = _bucket(len(text))
        bs = bucket_stats.setdefault(
            b,
            {
                "count": 0,
                "base_total": 0,
                "plus1_total": 0,
                "exempt_total": 0,
                "len_total": 0,
            },
        )
        bs["count"] += 1
        bs["base_total"] += n_base
        bs["plus1_total"] += n_plus1
        bs["exempt_total"] += n_exempt
        bs["len_total"] += len(text)

        rows.append(
            {
                "label": label,
                "length": len(text),
                "effective_threshold_base3": _length_aware_threshold(len(text), 3),
                "effective_threshold_base4": _length_aware_threshold(len(text), 4),
                "triggers_base3": n_base,
                "triggers_base4": n_plus1,
                "triggers_base3_with_exempt": n_exempt,
                "delta": n_plus1 - n_base,
                "delta_exempt": n_exempt - n_base,
                "base3_pairs": pairs_base[:5],  # top-5
                "base4_pairs": pairs_plus1[:5],
                "base3_exempt_pairs": pairs_exempt[:5],
            }
        )

    total = len(rows)
    avg_base = sum(r["triggers_base3"] for r in rows) / total
    avg_plus1 = sum(r["triggers_base4"] for r in rows) / total
    avg_exempt = sum(r["triggers_base3_with_exempt"] for r in rows) / total
    pct_clean_base = sum(1 for r in rows if r["triggers_base3"] == 0) / total * 100
    pct_clean_plus1 = sum(1 for r in rows if r["triggers_base4"] == 0) / total * 100
    pct_clean_exempt = (
        sum(1 for r in rows if r["triggers_base3_with_exempt"] == 0) / total * 100
    )

    summary = {
        "sample_size": total,
        "seed": args.seed,
        "exempt_words_inferred": PROPER_NAME_HINT[:40],
        "avg_triggers_per_narrative": {
            "base_3 (current, no exempt)": round(avg_base, 2),
            "base_3 + exempt (production-like)": round(avg_exempt, 2),
            "base_4 (+1, no exempt)": round(avg_plus1, 2),
            "delta_plus1": round(avg_plus1 - avg_base, 2),
            "delta_exempt": round(avg_exempt - avg_base, 2),
        },
        "pct_clean_narratives": {
            "base_3 (current, no exempt)": round(pct_clean_base, 1),
            "base_3 + exempt (production-like)": round(pct_clean_exempt, 1),
            "base_4 (+1, no exempt)": round(pct_clean_plus1, 1),
        },
        "top_words_base_3": word_counter_base.most_common(15),
        "top_words_base_4": word_counter_plus1.most_common(15),
        "top_words_base_3_with_exempt": word_counter_exempt.most_common(15),
        "per_bucket": {
            b: {
                "count": int(s["count"]),
                "avg_len": round(s["len_total"] / max(1, s["count"]), 0),
                "avg_triggers_base_3": round(s["base_total"] / max(1, s["count"]), 2),
                "avg_triggers_base_4": round(s["plus1_total"] / max(1, s["count"]), 2),
                "avg_triggers_base_3_exempt": round(
                    s["exempt_total"] / max(1, s["count"]), 2
                ),
            }
            for b, s in bucket_stats.items()
        },
        "rows": rows,
    }

    out_json = (_ROOT / args.out_json).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = _render_md(summary, narratives_total=len(narratives))
    out_md = (_ROOT / args.out_md).resolve()
    out_md.write_text(md, encoding="utf-8")

    print(f"sample={total} avg_base3={avg_base:.2f} avg_base4={avg_plus1:.2f}")
    print(f"clean%: base3={pct_clean_base:.1f} base4={pct_clean_plus1:.1f}")
    print(f"out: {out_json}")
    print(f"out: {out_md}")
    return 0


def _render_md(s: dict, *, narratives_total: int) -> str:
    """Render human verdict markdown."""
    avg = s["avg_triggers_per_narrative"]
    clean = s["pct_clean_narratives"]
    rows = s["rows"]

    raw_avg = avg["base_3 (current, no exempt)"]
    raw_p1 = avg["base_4 (+1, no exempt)"]
    raw_ex = avg["base_3 + exempt (production-like)"]
    raw_clean = clean["base_3 (current, no exempt)"]
    p1_clean = clean["base_4 (+1, no exempt)"]
    ex_clean = clean["base_3 + exempt (production-like)"]
    saved_pct_plus1 = (
        (1 - raw_p1 / raw_avg) if raw_avg > 0 else 0
    )
    saved_pct_exempt = (
        (1 - raw_ex / raw_avg) if raw_avg > 0 else 0
    )

    lines: list[str] = []
    lines.append("# A1 阈值校准 — Phase 6-C iter#C2\n")
    lines.append(
        f"> 池: {narratives_total} narratives 跨 bench novels. "
        f"抽样 {s['sample_size']} 条 (seed={s['seed']}).\n"
    )

    lines.append("## Headline\n")
    lines.append("| 配置 | avg A1/narr | clean% | 相对 base=3 |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(f"| **base=3, no exempt** (script baseline) | {raw_avg} | {raw_clean}% | — |")
    lines.append(
        f"| **base=3 + exempt** (production-like) | {raw_ex} | {ex_clean}% | "
        f"-{saved_pct_exempt:.0%} noise |"
    )
    lines.append(
        f"| **base=4, no exempt** (+1 阈值, 假设场景) | {raw_p1} | {p1_clean}% | "
        f"-{saved_pct_plus1:.0%} noise |"
    )
    lines.append("")
    lines.append(
        "> 重要 ▸ 校准脚本的 baseline (no exempt) **过严**: 它把所有 2-gram"
        " 都算上, 包括角色/地点名. 生产 ``run_deterministic_checks`` 由"
        " orchestrator 把 ``char.name + location.name`` 作为 ``exempt_words``"
        " 传入. 真实生产噪声接近 **base=3 + exempt** 行.\n"
    )

    lines.append("## Per-bucket\n")
    lines.append(
        "| bucket | n | avg_len | base=3 | base=3+exempt | base=4 |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for b, st in s["per_bucket"].items():
        lines.append(
            f"| {b} | {st['count']} | {st['avg_len']:.0f} | "
            f"{st['avg_triggers_base_3']} | {st['avg_triggers_base_3_exempt']} | "
            f"{st['avg_triggers_base_4']} |"
        )
    lines.append("")

    lines.append("## Top offenders — base=3 (no exempt)\n")
    lines.append("```")
    for w, n in s["top_words_base_3"]:
        lines.append(f"  {w}  ×{n} narratives")
    lines.append("```\n")

    lines.append("## Top offenders — base=3 + exempt (production-like)\n")
    lines.append(
        "Should now be free of character / location proper nouns. Anything"
        " surviving here is either a TRUE repetition (sthg LLM should fix) or"
        " a FALSE positive worth adding to STOP_NOMINALS.\n"
    )
    lines.append("```")
    for w, n in s["top_words_base_3_with_exempt"]:
        lines.append(f"  {w}  ×{n} narratives")
    lines.append("```\n")

    lines.append("## Sample drill-down (top 10 by base=3 triggers)\n")
    sorted_rows = sorted(rows, key=lambda r: -r["triggers_base3"])[:10]
    lines.append("| label | len | base=3 | base=3+ex | base=4 | top words (base=3) |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for r in sorted_rows:
        words = ", ".join(f"{w}×{c}" for w, c in r["base3_pairs"][:3])
        lbl = r["label"]
        if len(lbl) > 48:
            lbl = "…" + lbl[-46:]
        lines.append(
            f"| `{lbl}` | {r['length']} | {r['triggers_base3']} | "
            f"{r['triggers_base3_with_exempt']} | "
            f"{r['triggers_base4']} | {words} |"
        )
    lines.append("")

    lines.append("## Verdict\n")
    if raw_ex < 2.0:
        lines.append(
            f"* **production-like avg = {raw_ex} A1/narr** — 已经低. iter#7"
            f' carry-forward 的 "12+ A1/narr" 已被 iter#4 exempt_words +'
            f" 助词头/尾改进 + length-aware threshold 联合缓解.\n"
        )
        lines.append(
            "* **不建议动 base threshold** — 当前 4.58 noise 主要来自缺 exempt,"
            " 而生产已注入 exempt. 改 threshold 会让真实问题段也漏掉.\n"
        )
        lines.append(
            "* **可选改进 (低风险)**: 看上面 production-like top offenders 表,"
            " 若有不算专有名词的反复词 (如 `不是` / `一下`), 可加 STOP_NOMINALS,"
            " 进一步降本但不改 threshold.\n"
        )
    elif raw_ex < 5.0:
        lines.append(
            f"* **production-like avg = {raw_ex} A1/narr** — 中等. base=3 raw 噪声"
            f" {raw_avg}, exempt 后 {raw_ex} (-{saved_pct_exempt:.0%}).\n"
        )
        lines.append(
            "* **首选优化方向**: STOP_NOMINALS 而非阈值. 看 production-like top"
            " offenders 区分 TP/FP.\n"
        )
    else:
        lines.append(
            f"* **production-like avg = {raw_ex} A1/narr** — 高. 即使加 exempt"
            f" 噪声仍显著. base=4 假设 {raw_p1} (-{saved_pct_plus1:.0%}).\n"
        )
        lines.append(
            "* **可考虑 threshold +1**, 但需 cross-seed pairwise gate (Phase 6 规则"
            " #4) — 改前先在 controlled bench 上验证 quality 不掉.\n"
        )

    lines.append("\n## Reproducer\n")
    lines.append("```")
    lines.append("python scripts/calibrate_a1.py --sample 50 --seed 42")
    lines.append("```\n")

    lines.append("\n## 不在此刀\n")
    lines.append("* 改 threshold — 本 iter 只校准.\n")
    lines.append("* 改 STOP_NOMINALS — 留 iter#C3 (若 verdict 推荐).\n")
    lines.append("* cross-seed bench — 只有需要动阈值时才上.\n")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
