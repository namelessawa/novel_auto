"""Matrix bench — 跑 (theme × style) 笛卡儿积, 验证 narrator 在每个组合
能否产出合适风格的中文小说.

每个 cell = 一次 ``bench_tick.py`` 子进程, 用 ``--seed`` 喂主题种子, 用
``NOVEL_STYLE_PRESET`` env 喂风格 preset key. 并发用 ``ThreadPoolExecutor +
subprocess`` 控制 (不用 asyncio 是因为子进程跑得多, GIL 不咬). 每个子进程
独立 tracker / log / data_dir, 互不干扰.

输出:
* 每 cell: ``docs/iter/bench-matrix-{theme}-{style}.json/.md``
* 总报告: ``docs/iter/matrix-bench-{timestamp}.md`` — per-cell first sample +
  char count + tokens + cache hit + 失败原因 (子进程 exit code != 0)

Usage:
    python scripts/matrix_bench.py \\
        --themes xianxia_cultivation,urban_mystery,apocalypse_wasteland \\
        --styles literary,xianxia_fast,somber \\
        --ticks 3 \\
        --concurrency 4

CLI 不传 --themes/--styles 则跑全注册表笛卡儿积 (15 × 13 = 195 cells, 慎用).
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")

from novel_presets import (  # noqa: E402
    THEME_SEEDS,
    STYLE_PRESETS,
    get_style_preset,
    get_theme_seed,
    list_style_keys,
    list_theme_keys,
)
from quality_metrics.judge import (  # noqa: E402
    make_active_judge_fn,
    rubric_judge,
)

# Per-thread judge client cache — AsyncOpenAI 不跨 event loop 安全, 一线程
# 一份 (judge_fn, model_name). 主线程 main() 进 fail-fast 探针验证全局可用.
_thread_judge_cache = threading.local()


def _get_thread_judge() -> tuple:
    cached = getattr(_thread_judge_cache, "pair", None)
    if cached is None:
        cached = make_active_judge_fn()
        _thread_judge_cache.pair = cached
    return cached


_OUT_DIR = _REPO_ROOT / "docs" / "iter"


@dataclass
class CellResult:
    theme_key: str
    style_key: str
    bench_label: str
    exit_code: int
    duration_sec: float
    total_tokens: int = 0
    cache_hit_rate: float = 0.0
    narrative_chars: int = 0
    first_sample: str = ""
    error_excerpt: str = ""
    # Phase 5+ judge: glm-5.1 rubric scores on longest narrative of the cell
    judge_model: str = ""
    judge_coherence: int = 0  # 1-5, 0 = parse error / not judged
    judge_character_voice: int = 0
    judge_plot_progression: int = 0
    judge_reason: str = ""
    judge_error: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.narrative_chars > 0

    @property
    def judge_mean(self) -> float:
        if not (self.judge_coherence and self.judge_character_voice and self.judge_plot_progression):
            return 0.0
        return round(
            (self.judge_coherence + self.judge_character_voice + self.judge_plot_progression) / 3,
            2,
        )


def _bench_label(theme: str, style: str) -> str:
    """Compact label fitting novel_manager._NOVEL_ID_RE ({1,64} char cap).

    bench_tick.py 把 novel_id 构造成 ``bench_{label}_{int(time.time())}``.
    timestamp 10 digits + 'bench_' (6) + 2 underscores → 19 char overhead.
    Label budget 45 chars. 用每个 key 前 18 字符足够防撞 (人工 audit 16×13 唯一).
    """
    return f"m_{theme[:18]}_{style[:18]}"


def _judge_longest_narrative(narratives: list[dict]) -> tuple[dict, str]:
    """Pick the longest narrative for judge. Returns ({}, '') if none."""
    best: dict = {}
    best_len = 0
    for n in narratives or []:
        txt = (n.get("text") or "").strip()
        if len(txt) > best_len:
            best = n
            best_len = len(txt)
    return best, (best.get("text") or "").strip()


def _run_cell(theme_key: str, style_key: str, ticks: int) -> CellResult:
    """跑一个 cell — 子进程 bench_tick.py + per-cell NOVEL_STYLE_PRESET env + glm-5.1 rubric judge."""
    theme = get_theme_seed(theme_key)
    style = get_style_preset(style_key)
    label = _bench_label(theme_key, style_key)
    bench_json_path = _OUT_DIR / f"bench-{label}.json"

    env = os.environ.copy()
    env["NOVEL_STYLE_PRESET"] = style.key
    # Matrix bench 验证 'narrator 能否产生合适风格内容', 必须每 tick 都跑 LLM.
    # Phase 5-B stale-skip 默认 on 会让低事件密度的早期 tick 沉默 → 部分 cell
    # 0 narrative_chars 无法 judge. 这里强制关掉, 让矩阵看每 cell 真实生成能力.
    env["WORLD_STALE_SKIP_ENABLED"] = "0"

    cmd = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "bench_tick.py"),
        "--ticks", str(ticks),
        "--label", label,
        "--seed", theme.seed,
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd, env=env, capture_output=True, text=True, encoding="utf-8",
    )
    dt = time.perf_counter() - t0
    result = CellResult(
        theme_key=theme_key,
        style_key=style_key,
        bench_label=label,
        exit_code=proc.returncode,
        duration_sec=round(dt, 2),
    )
    if proc.returncode != 0:
        result.error_excerpt = (proc.stderr or proc.stdout or "")[-600:]
        return result

    # 解析 bench JSON 取关键 metric
    if not bench_json_path.exists():
        result.error_excerpt = f"bench json not found: {bench_json_path}"
        return result

    try:
        with open(bench_json_path, encoding="utf-8") as f:
            payload = json.load(f)
        result.total_tokens = int(payload.get("total_tokens", 0))
        result.cache_hit_rate = float(payload.get("cache_hit_rate", 0.0))
        narratives = payload.get("narratives") or []
        chars = sum(int(n.get("chars", 0) or 0) for n in narratives)
        result.narrative_chars = chars
        # first_sample: 第一个非空的, judge 用的 longest_sample
        for n in narratives:
            txt = (n.get("text") or "").strip()
            if txt:
                result.first_sample = txt[:600]
                break
        longest_meta, longest_text = _judge_longest_narrative(narratives)
    except Exception as e:
        result.error_excerpt = f"parse_bench_json_failed: {e}"
        return result

    # glm-5.1 rubric judge — 没 narrative 就跳过 (judge 不会评空文)
    if not longest_text:
        result.judge_error = "no_narrative_to_judge"
        return result

    try:
        judge_fn, model_name = _get_thread_judge()
        result.judge_model = model_name
        # asyncio.run new event loop per call — thread-local judge_fn 仍合法,
        # AsyncOpenAI client 在每次 chat 调用时按需启 connector, 不需粘 loop.
        r = asyncio.run(rubric_judge(longest_text, judge_fn=judge_fn, model_name=model_name))
        result.judge_coherence = r.coherence
        result.judge_character_voice = r.character_voice
        result.judge_plot_progression = r.plot_progression
        result.judge_reason = r.reason
    except RuntimeError as e:
        # judge 初始化失败 — 应当 hard-stop 但这里只能记录, main() 看分布判
        result.judge_error = f"judge_init_failed: {e}"
    except Exception as e:
        result.judge_error = f"{type(e).__name__}: {str(e)[:200]}"
    return result


def _render_matrix_md(results: list[CellResult], ticks: int) -> str:
    ok_cells = [r for r in results if r.ok]
    fail_cells = [r for r in results if not r.ok]
    judged = [r for r in ok_cells if r.judge_mean > 0]
    avg_judge = (
        sum(r.judge_mean for r in judged) / len(judged) if judged else 0.0
    )
    # 排名: 高 mean 在前 (≥ 4.0 = 优), 标问题 cell (judge_mean < 3.0)
    rows = [
        "# Matrix bench — theme × style coverage + glm-5.1 judge",
        "",
        f"- timestamp: bench-matrix run @ {int(time.time())}",
        f"- ticks per cell: {ticks}",
        f"- total cells: {len(results)}",
        f"- OK: {len(ok_cells)} / FAIL: {len(fail_cells)}",
        f"- judged: {len(judged)} cells, avg rubric mean = **{avg_judge:.2f}** / 5.00",
        f"- 优 (mean ≥ 4): {sum(1 for r in judged if r.judge_mean >= 4)}",
        f"- 中 (3 ≤ mean < 4): {sum(1 for r in judged if 3 <= r.judge_mean < 4)}",
        f"- 差 (mean < 3): {sum(1 for r in judged if r.judge_mean < 3)}",
        "",
        "## Per-cell summary (judge mean 降序)",
        "",
        "| theme | style | tokens | cache% | chars | coh | voice | plot | mean | note |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in sorted(
        results,
        key=lambda x: (-x.judge_mean if x.ok else 99, x.theme_key, x.style_key),
    ):
        if not r.ok:
            note = (r.error_excerpt[:40] or "no narrative") if r.error_excerpt else "no narrative"
            rows.append(
                f"| {r.theme_key} | {r.style_key} | {r.total_tokens} | "
                f"{r.cache_hit_rate*100:.1f}% | {r.narrative_chars} | - | - | - | - | {note} |"
            )
        else:
            judge_note = "OK" if r.judge_mean else (r.judge_error[:30] or "no judge")
            rows.append(
                f"| {r.theme_key} | {r.style_key} | {r.total_tokens} | "
                f"{r.cache_hit_rate*100:.1f}% | {r.narrative_chars} | "
                f"{r.judge_coherence or '-'} | {r.judge_character_voice or '-'} | "
                f"{r.judge_plot_progression or '-'} | "
                f"**{r.judge_mean if r.judge_mean else '-'}** | {judge_note} |"
            )

    if fail_cells:
        rows += ["", "## Failed cells (excerpt)", ""]
        for r in fail_cells:
            rows += [
                f"### {r.theme_key} × {r.style_key}",
                "",
                "```",
                r.error_excerpt or "(no error captured)",
                "```",
                "",
            ]

    # 风格 × 主题 cross-tab on judge mean
    rows += ["", "## Judge mean — style × theme cross-tab", ""]
    theme_keys = sorted({r.theme_key for r in results})
    style_keys = sorted({r.style_key for r in results})
    header = "| style \\ theme | " + " | ".join(theme_keys) + " | row_avg |"
    sep = "| --- | " + " | ".join(["---:"] * (len(theme_keys) + 1)) + " |"
    rows += [header, sep]
    by_key = {(r.theme_key, r.style_key): r for r in results}
    for sk in style_keys:
        cells_md: list[str] = []
        row_means: list[float] = []
        for tk in theme_keys:
            r = by_key.get((tk, sk))
            m = r.judge_mean if r and r.judge_mean else 0.0
            cells_md.append(f"{m:.1f}" if m else "-")
            if m:
                row_means.append(m)
        row_avg = sum(row_means) / len(row_means) if row_means else 0.0
        rows.append(
            "| " + sk + " | " + " | ".join(cells_md) + f" | **{row_avg:.2f}** |"
        )

    rows += ["", "## OK cells — first narrative sample (高分在前)", ""]
    for r in sorted(ok_cells, key=lambda x: -x.judge_mean):
        rows += [
            f"### {r.theme_key} × {r.style_key} — judge mean {r.judge_mean or '?'}",
            "",
            f"- coherence={r.judge_coherence}, voice={r.judge_character_voice}, plot={r.judge_plot_progression}",
            f"- judge reason: {r.judge_reason or '(none)'}",
            "",
            "```",
            r.first_sample or "(empty)",
            "```",
            "",
        ]

    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--themes",
        default="",
        help="csv of theme keys (default: all). list: " + ",".join(list_theme_keys()),
    )
    parser.add_argument(
        "--styles",
        default="",
        help="csv of style keys (default: all). list: " + ",".join(list_style_keys()),
    )
    parser.add_argument("--ticks", type=int, default=3, help="ticks per cell")
    parser.add_argument(
        "--concurrency", type=int, default=4, help="parallel subprocess count"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="just print themes + styles registry, no bench",
    )
    args = parser.parse_args()

    if args.list:
        print("THEMES:")
        for k, v in sorted(THEME_SEEDS.items()):
            print(f"  {k:25s} ({v.category:13s}) {v.label}")
        print()
        print("STYLES:")
        for k, v in sorted(STYLE_PRESETS.items()):
            print(f"  {k:25s} {v.label}")
        return 0

    themes = args.themes.split(",") if args.themes else list_theme_keys()
    styles = args.styles.split(",") if args.styles else list_style_keys()
    themes = [t.strip() for t in themes if t.strip()]
    styles = [s.strip() for s in styles if s.strip()]

    # validate keys up front
    for t in themes:
        get_theme_seed(t)
    for s in styles:
        get_style_preset(s)

    cells = [(t, s) for t in themes for s in styles]
    print(
        f"Matrix bench: {len(themes)} themes × {len(styles)} styles = {len(cells)} cells. "
        f"ticks={args.ticks}, concurrency={args.concurrency}"
    )
    print(f"themes: {themes}")
    print(f"styles: {styles}")
    print()

    # Fail-fast probe: 主线程探一次 judge 可用性, 失败立刻退 (hard-stop 风格).
    # 比让每个 cell 各自挂强 — 用户已声明 'judge 不可用立即停止'.
    try:
        _, judge_model = make_active_judge_fn()
        print(f"judge fail-fast probe OK: {judge_model}")
    except RuntimeError as e:
        print(f"HARD STOP: judge init failed up-front — {e}")
        print("Aborting matrix bench (per user rule: judge 不可用立即停止).")
        return 2
    print()

    results: list[CellResult] = []
    t_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concurrency
    ) as pool:
        futures = {
            pool.submit(_run_cell, t, s, args.ticks): (t, s) for t, s in cells
        }
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            t, s = futures[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = CellResult(
                    theme_key=t,
                    style_key=s,
                    bench_label=_bench_label(t, s),
                    exit_code=-1,
                    duration_sec=0.0,
                    error_excerpt=f"future_raised: {type(e).__name__}: {e}",
                )
            results.append(r)
            done += 1
            mark = "OK" if r.ok else "FAIL"
            print(
                f"  [{done:3d}/{len(cells)}] {mark:4s} {t} × {s} "
                f"({r.duration_sec}s, {r.narrative_chars}c, exit={r.exit_code})"
            )

    elapsed = time.perf_counter() - t_start
    out_path = _OUT_DIR / f"matrix-bench-{int(time.time())}.md"
    out_path.write_text(_render_matrix_md(results, args.ticks), encoding="utf-8")
    print()
    print(f"=== {len(results)} cells done in {elapsed:.0f}s ({elapsed/60:.1f}min) ===")
    print(f"verdict: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
