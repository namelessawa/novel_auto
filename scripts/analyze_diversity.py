"""iter#118 — offline 应用 iter#116 diversity dim 到已有 bench artifacts.

判断: 新 TTR / MATTR / 句长 stats 能否区分 iter#114 narrator-slim 反向
prose 退化与 iter#107 baseline. 也跨 3-seed × close-fix 对比.

不调 LLM, 无 cost. Pure offline analysis on bench JSON.

Usage:
    python scripts/analyze_diversity.py docs/iter/bench-*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from quality_metrics.diversity import diversity_report  # noqa: E402


def _extract_narratives(bench_path: Path) -> list[str]:
    with bench_path.open(encoding="utf-8") as f:
        data = json.load(f)
    narrs = data.get("narratives", [])
    return [n["text"] for n in narrs if n.get("text") and n["text"].strip()]


def _analyze(bench_path: Path) -> dict:
    narrs = _extract_narratives(bench_path)
    rep = diversity_report(narrs)
    return {
        "bench": bench_path.name,
        "narration_count": rep.narration_count,
        **rep.to_dict(),
    }


def _format_row(r: dict) -> str:
    n = r["narration_count"]
    ttr_char = r["ttr"]["char"]
    ttr_word = r["ttr"]["word"]
    mattr = r["ttr"]["mattr_100"]
    sl_mean = r["sentence_rhythm"]["mean_length"]
    sl_std = r["sentence_rhythm"]["mean_length_std"]
    return (
        f"  {r['bench'][:60]:<60} "
        f"n={n:>3}  "
        f"ttr_c={ttr_char:.4f}  "
        f"ttr_w={ttr_word:.4f}  "
        f"mattr={mattr:.4f}  "
        f"sent={sl_mean:>5.1f}±{sl_std:>4.1f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("benches", nargs="+", help="bench JSON paths")
    parser.add_argument(
        "--out-md", help="optional markdown output path", default=None
    )
    parser.add_argument(
        "--out-json", help="optional JSON output path", default=None
    )
    args = parser.parse_args()

    results = []
    for p in args.benches:
        path = Path(p)
        if not path.exists():
            print(f"[WARN] missing: {p}", file=sys.stderr)
            continue
        try:
            results.append(_analyze(path))
        except Exception as e:
            print(f"[ERROR] {p}: {e}", file=sys.stderr)

    print()
    print(
        "diversity dim 离线分析 — bench / narrations / TTR(char,word,mattr) / "
        "sentence(mean,std)"
    )
    print("-" * 130)
    for r in results:
        print(_format_row(r))

    if args.out_md:
        md = ["# Diversity dim cross-bench analysis", "", "| bench | narr | ttr_char | ttr_word | mattr | sent_mean | sent_std |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for r in results:
            md.append(
                f"| `{r['bench']}` | {r['narration_count']} | "
                f"{r['ttr']['char']:.4f} | "
                f"{r['ttr']['word']:.4f} | "
                f"{r['ttr']['mattr_100']:.4f} | "
                f"{r['sentence_rhythm']['mean_length']:.2f} | "
                f"{r['sentence_rhythm']['mean_length_std']:.2f} |"
            )
        Path(args.out_md).write_text("\n".join(md), encoding="utf-8")
        print(f"\n[OK] wrote {args.out_md}")

    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[OK] wrote {args.out_json}")


if __name__ == "__main__":
    main()
