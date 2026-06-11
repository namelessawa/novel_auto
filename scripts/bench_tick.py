"""Tick-cost benchmark — measures per-agent token usage on N ticks.

Usage:
    LLM_PROVIDER=custom python scripts/bench_tick.py [--ticks 3] [--seed ...] [--label v0-baseline]

Output:
    docs/iter/bench-<label>.json   structured per-agent + per-tick breakdown
    docs/iter/bench-<label>.md     human-readable summary
    backend/data/users/bench/novels/<id>/narratives/...  generated text

The bench runs a fresh bootstrap + N ticks on a dedicated "bench" user so it
never collides with real novels.  Re-invoking with the same --label overwrites
output files but uses a new novel id so each run is independent.

Reproducing v2.38 cost-quality-loop benches:

  # baseline (before iter#3)
  git checkout main -- backend/agents/ backend/bootstrap_prompts.py
  python scripts/bench_tick.py --label v0-baseline

  # final state
  git checkout iter/cost-quality-loop -- .
  python scripts/bench_tick.py --label v15-final

Expected: total_tokens drops 137,890 → ~31,000 (-77%), avg tick 556s → ~91s.

Note: stochastic provider variance means single-bench numbers fluctuate;
the trend across 3+ benches at same SHA is what's meaningful.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

# Force custom provider before any imports that resolve the LLM config.
os.environ.setdefault("LLM_PROVIDER", "custom")
# v2.38 (iter#57) — bench 跑长 tick 时 reasoning 模型偶发卡 300s+, 默认
# LLM_TIMEOUT=600 已够. 显式 setdefault 让 bench 在裸环境也有合理超时,
# 不依赖 .env 缺失/错配.
os.environ.setdefault("LLM_TIMEOUT", "600")

import novel_manager  # noqa: E402
from bootstrap_prompts import bootstrap_world  # noqa: E402
from tick_runtime import TickRuntime  # noqa: E402


_DEFAULT_SEED = (
    "蒸汽朋克都市边缘的破败档案馆,一个失语的少女管理员每夜整理着不该存在的卷宗,"
    "卷宗里记录的未来事件正在一件件成真。"
)


async def _bench(args) -> dict:
    # v2.38 (iter#52) — bench user_id 固定 "bench" (≠ 任何真实用户 id 格式),
    # 隔离 cost-quality-loop bench 数据与生产数据.
    user_id = "bench"
    assert user_id != "_legacy", "bench user_id 与 legacy 冲突"
    novel_id = f"bench_{args.label}_{int(time.time())}"
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
    os.makedirs(data_dir, exist_ok=True)

    # --- Cold-start: bootstrap world (5 prompts) ----------------------------
    t0 = time.perf_counter()
    await bootstrap_world(
        novel_id=novel_id,
        data_dir=data_dir,
        seed=args.seed,
        positioning="冷峻克制 / 阴翳氛围 / 短句节奏 / 物件描写优先",
        references="石黑一雄 / 江户川乱步",
        title="档案馆的失语者",
    )
    bootstrap_sec = time.perf_counter() - t0

    # --- Hot path: N ticks --------------------------------------------------
    rt = TickRuntime(user_id=user_id, novel_id=novel_id)
    tracker = rt.token_budget

    tick_records: list[dict] = []
    tick_durations: list[float] = []
    narratives: list[dict] = []

    for i in range(args.ticks):
        before = dict(tracker.snapshot.by_agent)
        before_total = tracker.snapshot.total_tokens
        tt = time.perf_counter()
        summary = await rt.orchestrator.run_tick()
        dt = time.perf_counter() - tt
        after = dict(tracker.snapshot.by_agent)
        delta = {
            k: after[k] - before.get(k, 0)
            for k in after
            if after[k] - before.get(k, 0) > 0
        }
        tick_total = tracker.snapshot.total_tokens - before_total
        tick_records.append(
            {
                "tick": summary.tick,
                "tick_total_tokens": tick_total,
                "duration_sec": round(dt, 2),
                "narrator_chars": summary.narrator_output_chars,
                "agents": delta,
            }
        )
        tick_durations.append(dt)
        if summary.narrator_output_chars > 0:
            narr_path = os.path.join(
                data_dir, "narratives", f"tick_{summary.tick:06d}.txt"
            )
            text = ""
            try:
                with open(narr_path, encoding="utf-8") as f:
                    text = f.read()
            except FileNotFoundError:
                pass
            narratives.append(
                {"tick": summary.tick, "chars": summary.narrator_output_chars, "text": text}
            )

    snap = tracker.snapshot
    report = {
        "label": args.label,
        "novel_id": novel_id,
        "ticks": args.ticks,
        "bootstrap_sec": round(bootstrap_sec, 2),
        "tick_durations_sec": [round(d, 2) for d in tick_durations],
        "total_tokens": snap.total_tokens,
        "by_agent_cumulative": dict(snap.by_agent),
        "by_priority": dict(snap.by_priority),
        "call_count": snap.call_count,
        "per_tick": tick_records,
        "narratives": narratives,
    }

    rt.close()
    return report


def _render_markdown(rep: dict) -> str:
    lines = [
        f"# Bench: {rep['label']}",
        "",
        f"- novel_id: `{rep['novel_id']}`",
        f"- ticks: {rep['ticks']}",
        f"- bootstrap_sec: {rep['bootstrap_sec']}",
        f"- tick_durations_sec: {rep['tick_durations_sec']}",
        f"- total_tokens: {rep['total_tokens']}",
        f"- call_count: {rep['call_count']}",
        # v2.38 (iter#58) — narrative chars 累计, 便于 per-char cost 计算.
        # v2.38 (iter#59) — per-char cost 直接算出, 跨 bench 比较的核心指标.
        f"- narrative_chars_total: {sum(r['narrator_chars'] for r in rep['per_tick'])}",
        f"- tokens_per_char: {(rep['total_tokens'] / max(1, sum(r['narrator_chars'] for r in rep['per_tick']))):.2f}",
        "",
        "## By agent (cumulative, bootstrap + ticks)",
        "",
        "| agent | tokens | % |",
        "| --- | ---: | ---: |",
    ]
    total = max(rep["total_tokens"], 1)
    for agent, tok in sorted(
        rep["by_agent_cumulative"].items(), key=lambda kv: -kv[1]
    ):
        lines.append(f"| {agent} | {tok} | {tok * 100 / total:.1f}% |")
    lines += [
        "",
        "## By priority",
        "",
        "| priority | tokens |",
        "| --- | ---: |",
    ]
    for p, tok in rep["by_priority"].items():
        lines.append(f"| {p} | {tok} |")

    lines += ["", "## Per tick", "", "| tick | tokens | sec | narr_chars | top agents |", "| ---: | ---: | ---: | ---: | --- |"]
    for r in rep["per_tick"]:
        top = ", ".join(
            f"{k}={v}"
            for k, v in sorted(r["agents"].items(), key=lambda kv: -kv[1])[:3]
        )
        lines.append(
            f"| {r['tick']} | {r['tick_total_tokens']} | {r['duration_sec']} | {r['narrator_chars']} | {top} |"
        )

    if rep["narratives"]:
        lines += ["", "## First narrative sample", "", "```"]
        first = rep["narratives"][0]
        lines.append(first["text"][:1200])
        lines.append("```")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=3)
    parser.add_argument("--seed", default=_DEFAULT_SEED)
    parser.add_argument("--label", default="v0-baseline")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    rep = asyncio.run(_bench(args))

    out_dir = _REPO_ROOT / "docs" / "iter"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"bench-{args.label}.json"
    md_path = out_dir / f"bench-{args.label}.md"
    json_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(rep), encoding="utf-8")

    print(f"[OK] wrote {json_path}")
    print(f"[OK] wrote {md_path}")
    print(f"total_tokens={rep['total_tokens']} call_count={rep['call_count']}")
    print(f"top by_agent: " + ", ".join(
        f"{k}={v}" for k, v in sorted(rep["by_agent_cumulative"].items(), key=lambda kv: -kv[1])[:5]
    ))


def _self_check() -> None:
    """Smoke-test the public surface without actually calling LLM.

    Usage: python scripts/bench_tick.py --self-check
    """
    sample = {
        "label": "self-check",
        "novel_id": "sample",
        "ticks": 1,
        "bootstrap_sec": 0.0,
        "tick_durations_sec": [0.0],
        "total_tokens": 0,
        "by_agent_cumulative": {},
        "by_priority": {},
        "call_count": 0,
        "per_tick": [],
        "narratives": [],
    }
    out = _render_markdown(sample)
    assert isinstance(out, str) and "self-check" in out
    print("[OK] _render_markdown surface intact")
    print(f"[OK] _DEFAULT_SEED len={len(_DEFAULT_SEED)} chars")
    print("[OK] bench_tick.py self-check passed")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        main()
