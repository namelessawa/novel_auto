"""从 docs/iter/bench-m_*.json 聚合 retro_judge → 生成 RECOMMENDED_PAIRS.md.

Phase 5 收尾产物 — 把 208-cell matrix 数据变成 user-facing 推荐表.

Usage:
    python scripts/gen_recommended_pairs.py
        # 默认输出 docs/iter/RECOMMENDED_PAIRS.md

    python scripts/gen_recommended_pairs.py --output other/path.md
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from novel_presets import STYLE_PRESETS, THEME_SEEDS  # noqa: E402


def _parse_cell_label(name: str, themes_full: list[str], styles_full: list[str]):
    """label = 'm_{theme[:18]}_{style[:18]}' (matrix_bench convention)."""
    for tk in themes_full:
        t_trunc = tk[:18]
        if name.startswith(t_trunc + "_"):
            rest = name[len(t_trunc) + 1 :]
            for sk in styles_full:
                if rest == sk[:18]:
                    return tk, sk
    return None, None


def collect_cells(pattern: str) -> dict[tuple[str, str], tuple[int, int, int, float]]:
    """Return {(theme, style): (coh, voice, plot, mean)} for cells with judge."""
    themes_full = sorted(THEME_SEEDS)
    styles_full = sorted(STYLE_PRESETS)
    out: dict[tuple[str, str], tuple[int, int, int, float]] = {}
    for fp in glob.glob(pattern):
        try:
            d = json.loads(Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        rj = d.get("retro_judge") or {}
        mean = rj.get("mean", 0) or 0
        if not mean:
            continue
        name = Path(fp).stem.replace("bench-m_", "", 1)
        t, s = _parse_cell_label(name, themes_full, styles_full)
        if t and s:
            out[(t, s)] = (
                int(rj.get("coherence", 0) or 0),
                int(rj.get("character_voice", 0) or 0),
                int(rj.get("plot_progression", 0) or 0),
                float(mean),
            )
    return out


def render_md(cells: dict, judge_source: str) -> str:
    themes_full = sorted(THEME_SEEDS)
    styles_full = sorted(STYLE_PRESETS)

    def tiebreak_key(item):
        _, (coh, voice, plot, m) = item
        return (-m, -voice, -plot, -coh)

    lines: list[str] = [
        "# 推荐配对 — 16 主题 × 13 风格 matrix 数据驱动",
        "",
        f"> 数据源: {len(cells)}/208 cell 含 glm-5.1 retro judge",
        f"> 评分 mean (1-5): 见 `{judge_source}`",
        "> 重生成: `python scripts/gen_recommended_pairs.py`",
        "",
        "## 速查 — 每主题 top-3 推荐风格",
        "",
        "| 主题 key | 中文名 | 推荐风格 (mean) |",
        "| --- | --- | --- |",
    ]
    for tk in themes_full:
        ts = THEME_SEEDS[tk]
        ranked = sorted(
            [(s, cells[(tk, s)]) for s in styles_full if (tk, s) in cells],
            key=tiebreak_key,
        )[:3]
        rec = (
            " / ".join(f"**{s}** ({m[3]:.2f})" for s, m in ranked)
            if ranked
            else "(无数据)"
        )
        lines.append(f"| `{tk}` | {ts.label} | {rec} |")

    lines += [
        "",
        "## 速查 — 每风格 top-3 适配主题",
        "",
        "| 风格 key | 中文名 | 适配主题 (mean) |",
        "| --- | --- | --- |",
    ]
    for sk in styles_full:
        sp = STYLE_PRESETS[sk]
        ranked = sorted(
            [(t, cells[(t, sk)]) for t in themes_full if (t, sk) in cells],
            key=tiebreak_key,
        )[:3]
        rec = (
            " / ".join(f"**{t}** ({m[3]:.2f})" for t, m in ranked)
            if ranked
            else "(无数据)"
        )
        lines.append(f"| `{sk}` | {sp.label} | {rec} |")

    style_avgs: dict[str, float] = {}
    for sk in styles_full:
        scores = [cells[(t, sk)][3] for t in themes_full if (t, sk) in cells]
        if scores:
            style_avgs[sk] = sum(scores) / len(scores)
    universal = sorted(style_avgs.items(), key=lambda x: -x[1])

    lines += [
        "",
        "## 风格通配排名 (跨主题平均 mean 降序)",
        "",
        "| 风格 key | 中文名 | 跨主题平均 mean | 覆盖主题数 |",
        "| --- | --- | --- | --- |",
    ]
    for sk, avg in universal:
        sp = STYLE_PRESETS[sk]
        n = sum(1 for t in themes_full if (t, sk) in cells)
        lines.append(f"| `{sk}` | {sp.label} | {avg:.2f} | {n}/{len(themes_full)} |")

    perfect = [(t, s) for (t, s), v in cells.items() if v[3] >= 5.0]
    lines += ["", "## 满分配对 (mean = 5.0)", ""]
    if perfect:
        for t, s in perfect:
            lines.append(
                f"- `{t}` × `{s}` — {THEME_SEEDS[t].label} 配 {STYLE_PRESETS[s].label}"
            )
    else:
        lines.append("(无)")

    avoid = [(t, s, cells[(t, s)]) for (t, s) in cells if cells[(t, s)][3] < 4.0]
    lines += ["", "## 避雷配对 (mean < 4)", ""]
    if avoid:
        lines += [
            "| 主题 | 风格 | mean | judge 失败维度 |",
            "| --- | --- | --- | --- |",
        ]
        for t, s, v in sorted(avoid, key=lambda x: x[2][3]):
            low_dim: list[str] = []
            if v[0] < 4:
                low_dim.append(f"coh={v[0]}")
            if v[1] < 4:
                low_dim.append(f"voice={v[1]}")
            if v[2] < 4:
                low_dim.append(f"plot={v[2]}")
            lines.append(f"| `{t}` | `{s}` | {v[3]:.2f} | {', '.join(low_dim)} |")
    else:
        lines.append("(无 — Phase 5-E preset patch 后全部 cell mean ≥ 4.00)")

    lines += [
        "",
        "## Notes",
        "",
        "* glm-5.1 在 3-tick 短样本上分辨力有限 (大量 4.67 并列). 长程 (50+ tick)",
        "  才能拉开差距 — 长程数据待 PHASE5_PLAN J 完成后更新本表.",
        "* 'avoid' 列里部分 cell 仅 voice 或 plot 单维度低, 长样本可能补回.",
        "* 满分 5.0 是高置信信号 — 即使短样本也能识别完美匹配.",
    ]
    return "\n".join(lines) + "\n"


def build_recommendation_data(cells: dict) -> dict:
    """Build a structured dict suitable for JSON / API consumption.

    Output schema:
        {
            "version": 1,
            "total_cells": 208,
            "scored_cells": <count>,
            "by_theme": {
                "<theme_key>": [
                    {"style": "<style_key>", "mean": 4.67, "coh": 5,
                     "voice": 4, "plot": 5, "rank": 1, "is_top": true}
                ]
            },
            "perfect_pairs": [{"theme": "<k>", "style": "<k>", "mean": 5.0}],
            "avoid_pairs": [{"theme": "<k>", "style": "<k>", "mean": 3.0,
                             "low_dimensions": ["voice"]}],
            "style_universal_avg": {"<style_key>": 4.50},
        }
    """
    themes_full = sorted(THEME_SEEDS)
    styles_full = sorted(STYLE_PRESETS)

    def _tiebreak(item):
        _, (coh, voice, plot, m) = item
        return (-m, -voice, -plot, -coh)

    by_theme: dict = {}
    for tk in themes_full:
        ranked = sorted(
            [(s, cells[(tk, s)]) for s in styles_full if (tk, s) in cells],
            key=_tiebreak,
        )
        by_theme[tk] = [
            {
                "style": sk,
                "mean": round(v[3], 4),
                "coh": v[0],
                "voice": v[1],
                "plot": v[2],
                "rank": idx + 1,
                "is_top": idx < 3,
            }
            for idx, (sk, v) in enumerate(ranked)
        ]

    perfect_pairs = [
        {"theme": t, "style": s, "mean": round(v[3], 4)}
        for (t, s), v in cells.items()
        if v[3] >= 5.0
    ]
    avoid_pairs = []
    for (t, s), v in cells.items():
        if v[3] < 4.0:
            low_dims = []
            if v[0] < 4:
                low_dims.append("coh")
            if v[1] < 4:
                low_dims.append("voice")
            if v[2] < 4:
                low_dims.append("plot")
            avoid_pairs.append(
                {
                    "theme": t,
                    "style": s,
                    "mean": round(v[3], 4),
                    "low_dimensions": low_dims,
                }
            )
    avoid_pairs.sort(key=lambda x: x["mean"])

    style_universal_avg: dict = {}
    for sk in styles_full:
        scores = [cells[(t, sk)][3] for t in themes_full if (t, sk) in cells]
        if scores:
            style_universal_avg[sk] = round(sum(scores) / len(scores), 4)

    return {
        "version": 1,
        "total_cells": len(themes_full) * len(styles_full),
        "scored_cells": len(cells),
        "by_theme": by_theme,
        "perfect_pairs": perfect_pairs,
        "avoid_pairs": avoid_pairs,
        "style_universal_avg": style_universal_avg,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pattern", default="docs/iter/bench-m_*.json")
    parser.add_argument("--output", default="docs/iter/RECOMMENDED_PAIRS.md")
    parser.add_argument(
        "--json-output",
        default="backend/novel_presets/recommended_pairs.json",
        help=(
            "Path to also write structured JSON for API/UI consumption. "
            "Set to '' to skip."
        ),
    )
    parser.add_argument(
        "--judge-source",
        default="matrix-bench-retro-1781668495.md",
        help="aggregate judge MD referenced in doc header",
    )
    args = parser.parse_args()

    pattern = str(_REPO_ROOT / args.pattern)
    cells = collect_cells(pattern)
    md = render_md(cells, args.judge_source)
    out = _REPO_ROOT / args.output
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out}")
    print(f"  cells: {len(cells)}/208")
    print(f"  >=4.0: {sum(1 for v in cells.values() if v[3] >= 4.0)}")
    print(f"  <4.0:  {sum(1 for v in cells.values() if v[3] < 4.0)}")
    print(f"  =5.0:  {sum(1 for v in cells.values() if v[3] >= 5.0)}")

    if args.json_output:
        data = build_recommendation_data(cells)
        json_out = _REPO_ROOT / args.json_output
        json_out.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
