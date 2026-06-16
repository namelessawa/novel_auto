"""配额耗尽场景的解药 — 对已存在的 bench JSON 跑 glm-5.1 rubric judge.

设计:
* matrix bench 把每个 cell 的 narratives 写进 docs/iter/bench-<label>.json
* 即使本会话 judge 失败 (quota 耗尽 / 网络断), 生成数据全部持久
* 配额回来后, ``judge_existing.py --pattern 'bench-m_*.json'`` 把已有 bench
  全部补判, 输出 matrix-bench-retro-{ts}.md 等价 verdict

Usage:
    # 只补判, 不重新生成:
    python scripts/judge_existing.py --pattern "docs/iter/bench-m_*.json"

    # 限定 N 个 (省 token):
    python scripts/judge_existing.py --pattern "docs/iter/bench-m_*.json" --max 30

    # 跳过已经有 rubric 字段的 (增量补判):
    python scripts/judge_existing.py --pattern "docs/iter/bench-m_*.json" --skip-judged

HARD STOP: 5 个连续 judge 失败立即退 (per 用户 'judge 不可用立即停止' 约束).
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(_REPO_ROOT / ".env")

from quality_metrics.judge import make_active_judge_fn, rubric_judge  # noqa: E402


@dataclass
class JudgedCell:
    bench_path: str
    label: str
    narrative_chars: int
    total_tokens: int
    cache_hit_rate: float
    coherence: int = 0
    character_voice: int = 0
    plot_progression: int = 0
    reason: str = ""
    error: str = ""

    @property
    def mean(self) -> float:
        if not (self.coherence and self.character_voice and self.plot_progression):
            return 0.0
        return round((self.coherence + self.character_voice + self.plot_progression) / 3, 2)


def _longest_narrative(bench: dict) -> str:
    best = ""
    for n in bench.get("narratives") or []:
        txt = (n.get("text") or "").strip()
        if len(txt) > len(best):
            best = txt
    return best


def _bench_already_judged(bench_path: Path) -> bool:
    """如果 bench JSON 已经 attach 过 rubric, 跳过."""
    try:
        payload = json.loads(bench_path.read_text(encoding="utf-8"))
        return "retro_judge" in payload and payload["retro_judge"].get("coherence")
    except Exception:
        return False


def _attach_judge_to_bench(bench_path: Path, jc: JudgedCell) -> None:
    """把 judge 结果写回原 bench JSON 的 ``retro_judge`` 子字段."""
    try:
        payload = json.loads(bench_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  warn: can't read {bench_path.name}: {e}")
        return
    payload["retro_judge"] = {
        "coherence": jc.coherence,
        "character_voice": jc.character_voice,
        "plot_progression": jc.plot_progression,
        "mean": jc.mean,
        "reason": jc.reason,
        "error": jc.error,
        "judged_at": int(time.time()),
    }
    bench_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def _judge_one(judge_fn, model_name: str, bench_path: Path) -> JudgedCell:
    try:
        payload = json.loads(bench_path.read_text(encoding="utf-8"))
    except Exception as e:
        return JudgedCell(
            bench_path=str(bench_path),
            label=bench_path.stem,
            narrative_chars=0,
            total_tokens=0,
            cache_hit_rate=0.0,
            error=f"read_failed: {e}",
        )
    text = _longest_narrative(payload)
    chars = sum(int(n.get("chars", 0) or 0) for n in (payload.get("narratives") or []))
    jc = JudgedCell(
        bench_path=str(bench_path),
        label=payload.get("label", bench_path.stem),
        narrative_chars=chars,
        total_tokens=int(payload.get("total_tokens", 0) or 0),
        cache_hit_rate=float(payload.get("cache_hit_rate", 0.0) or 0.0),
    )
    if not text:
        jc.error = "no_narrative_in_bench"
        return jc
    try:
        r = await rubric_judge(text, judge_fn=judge_fn, model_name=model_name)
        jc.coherence = r.coherence
        jc.character_voice = r.character_voice
        jc.plot_progression = r.plot_progression
        jc.reason = r.reason
    except Exception as e:
        jc.error = f"{type(e).__name__}: {str(e)[:200]}"
    return jc


def _render_retro_md(judged: list[JudgedCell], pattern: str) -> str:
    ok = [j for j in judged if j.mean > 0]
    avg = sum(j.mean for j in ok) / len(ok) if ok else 0.0
    rows = [
        "# Matrix bench — retroactive judge",
        "",
        f"- pattern: `{pattern}`",
        f"- total cells: {len(judged)}",
        f"- judged OK: {len(ok)} (avg mean = **{avg:.2f}** / 5.00)",
        f"- 优 (≥4): {sum(1 for j in ok if j.mean >= 4)}",
        f"- 中 (3 ≤ x < 4): {sum(1 for j in ok if 3 <= j.mean < 4)}",
        f"- 差 (<3): {sum(1 for j in ok if j.mean < 3)}",
        "",
        "## Per-cell",
        "",
        "| label | chars | tokens | cache% | coh | voice | plot | mean | error |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for j in sorted(judged, key=lambda x: -x.mean):
        rows.append(
            f"| {j.label} | {j.narrative_chars} | {j.total_tokens} | "
            f"{j.cache_hit_rate*100:.1f}% | "
            f"{j.coherence or '-'} | {j.character_voice or '-'} | "
            f"{j.plot_progression or '-'} | **{j.mean if j.mean else '-'}** | "
            f"{j.error[:40] if j.error else ''} |"
        )
    return "\n".join(rows) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pattern",
        default="docs/iter/bench-m_*.json",
        help="glob pattern for bench JSON files (default: matrix bench naming).",
    )
    parser.add_argument(
        "--max", type=int, default=0,
        help="cap on cells to judge (0 = no cap). Token budget guard.",
    )
    parser.add_argument(
        "--skip-judged", action="store_true",
        help="skip bench files already containing retro_judge field.",
    )
    parser.add_argument(
        "--output", default="",
        help="MD output path. Default docs/iter/matrix-bench-retro-{ts}.md",
    )
    args = parser.parse_args()

    bench_paths = sorted(Path(p) for p in glob.glob(args.pattern))
    if args.skip_judged:
        bench_paths = [p for p in bench_paths if not _bench_already_judged(p)]
    if args.max > 0:
        bench_paths = bench_paths[: args.max]
    if not bench_paths:
        print(f"no bench JSON matched {args.pattern!r}")
        return 1
    print(f"will judge {len(bench_paths)} bench files")

    # Fail-fast judge probe
    try:
        judge_fn, model_name = make_active_judge_fn()
        print(f"judge model: {model_name}")
    except RuntimeError as e:
        print(f"HARD STOP: judge init failed — {e}")
        return 2

    judged: list[JudgedCell] = []
    consecutive_failures = 0
    for i, p in enumerate(bench_paths, 1):
        jc = await _judge_one(judge_fn, model_name, p)
        judged.append(jc)
        _attach_judge_to_bench(p, jc)
        mark = "OK " if jc.mean else "ERR"
        print(
            f"  [{i:3d}/{len(bench_paths)}] {mark} {jc.label:40s} "
            f"mean={jc.mean or '-'}  err={jc.error[:60]}"
        )
        if jc.error and "no_narrative" not in jc.error:
            consecutive_failures += 1
            if consecutive_failures >= 5:
                print(
                    "HARD STOP: 5 consecutive judge failures (likely quota/network)."
                )
                break
        else:
            consecutive_failures = 0

    out_path = Path(args.output) if args.output else (
        _REPO_ROOT / "docs" / "iter" / f"matrix-bench-retro-{int(time.time())}.md"
    )
    out_path.write_text(_render_retro_md(judged, args.pattern), encoding="utf-8")
    print()
    print(f"verdict: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
