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
    # iter#121 Phase 3-B: 透传 cast-confound 控制. None 时保持 wide 默认.
    await bootstrap_world(
        novel_id=novel_id,
        data_dir=data_dir,
        seed=args.seed,
        positioning="冷峻克制 / 阴翳氛围 / 短句节奏 / 物件描写优先",
        references="石黑一雄 / 江户川乱步",
        title="档案馆的失语者",
        cast_a_count=getattr(args, "cast_a_count", None),
        cast_b_count=getattr(args, "cast_b_count", None),
        cast_c_count=getattr(args, "cast_c_count", None),
    )
    bootstrap_sec = time.perf_counter() - t0

    # --- Hot path: N ticks --------------------------------------------------
    rt = TickRuntime(user_id=user_id, novel_id=novel_id)
    tracker = rt.token_budget

    tick_records: list[dict] = []
    tick_durations: list[float] = []
    narratives: list[dict] = []
    # v2.38 Phase 2 Stage 3 (iter#87) — longrange 采样.
    open_loop_snapshots: list[dict] = []  # foreshadowing 曲线原料
    # v2.38 (iter#88 review fix) — novelty_records 字段保留作 schema 占位,
    # 实际填充逻辑 (从 NoveltyCriticOutput 回调累计) 留给 iter#89+ 加 orchestrator
    # hook 后接通. 当前 bench 跑出来此字段恒为空, 是 by design 而非 bug.
    novelty_records: list[dict] = []  # 占位 — TODO iter#89 接 novelty_critic hook
    longrange_sample_every = max(1, getattr(args, "longrange_every", 5))

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

        # v2.38 Phase 2 Stage 3 (iter#87) — 长程采样.
        cur_tick = summary.tick
        if cur_tick % longrange_sample_every == 0:
            try:
                loops = rt.tick_state.get_open_loops()
                open_count = len(loops)
                stale_open = sum(
                    1
                    for l in loops
                    if (cur_tick - max(
                        getattr(l, "last_referenced_tick", 0) or 0,
                        getattr(l, "opened_tick", 0) or 0,
                    )) > 20
                )
                avg_urg = (
                    sum(getattr(l, "urgency", 0) or 0 for l in loops) / open_count
                    if open_count
                    else 0.0
                )
                # v2.38 (iter#88 review fix) → iter#91 — TickState 已加
                # loops_closed_total 属性, 直接读. 老 state 兼容 attr 不存在.
                closed_count = int(
                    getattr(rt.tick_state, "loops_closed_total", 0) or 0
                )
                closed_source = (
                    "tick_state.loops_closed_total"
                    if hasattr(rt.tick_state, "loops_closed_total")
                    else "not_implemented"
                )
                open_loop_snapshots.append(
                    {
                        "tick": cur_tick,
                        "open": open_count,
                        "closed": closed_count,
                        "closed_source": closed_source,
                        "stale_open": stale_open,
                        "avg_urgency": round(avg_urg, 2),
                    }
                )
            except Exception as e:  # pragma: no cover — defensive
                open_loop_snapshots.append(
                    {"tick": cur_tick, "error": f"snapshot_failed: {e}"}
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
        # v2.38 Phase 2 Stage 3 (iter#87) — longrange 原料.
        "open_loop_snapshots": open_loop_snapshots,
        "novelty_records": novelty_records,
    }

    # v2.38 (iter#80) — Phase 2 quality metrics integration.
    if getattr(args, "quality", False):
        report["quality"] = await _compute_quality(
            narratives=narratives,
            rt=rt,
            tick_records=tick_records,
            judge_density=getattr(args, "judge_density", 10),
            judge_budget=getattr(args, "judge_budget", 50_000),
        )

    rt.close()
    return report


async def _compute_quality(
    *,
    narratives: list[dict],
    rt,
    tick_records: list[dict],
    judge_density: int,
    judge_budget: int,
) -> dict:
    """Det 三类 + judge 采样. judge 失败/未配置时只跑 det.

    Phase 2 §3.1 + §3.2. 此函数 deterministic 部分必跑, judge 部分按
    budget 截断.
    """
    from quality_metrics import (
        CharacterFact,
        LocationFact,
        NarrationRecord,
        WorldSnapshot,
        compliance_report,
        consistency_report,
        repetition_report,
    )

    # --- Det 1: repetition ----------------------------------------------
    texts = [n["text"] for n in narratives]
    rep_view = repetition_report(texts).to_dict()

    # --- Det 2: consistency ----------------------------------------------
    # 用本次 bench 结束时的 TickState 装 snapshot (近似: 每个 narration
    # 用同一 final snapshot; long bench 会扩展为 per-tick).
    try:
        chars = [
            CharacterFact(
                id=p.id,
                name=p.name,
                current_location=(
                    next(
                        (
                            s.current_location
                            for s in rt.tick_state.list_character_states()
                            if s.character_id == p.id
                        ),
                        "",
                    )
                ),
                alive=True,
            )
            for p in rt.tick_state.list_character_profiles()
        ]
        locs = [
            LocationFact(id=l.id, name=l.name)
            for l in rt.tick_state.world_state.locations
        ]
        snap = WorldSnapshot(characters=chars, locations=locs)
        cons_view = consistency_report(texts, [snap] * len(texts)).to_dict()
    except Exception as e:  # pragma: no cover — defensive
        cons_view = {"error": f"snapshot_assembly_failed: {e}"}

    # --- Det 3: compliance ----------------------------------------------
    # Bench narratives 现暂未保存 estimated_length / consistency_flags;
    # 用 text 长度近似 tier (与 narrator 启发式一致): 落 medium 默认.
    # 后续 iter 可让 bench 保存完整 NarratorOutput dict 以获得真实 flag.
    comp_records = [
        NarrationRecord(
            text=n["text"],
            estimated_length=_guess_tier_for(n.get("chars", len(n["text"]))),
            consistency_flags=[],
            should_narrate=True,
        )
        for n in narratives
    ]
    comp_view = compliance_report(comp_records).to_dict()

    quality = {
        "det": {
            "repetition": rep_view,
            "consistency": cons_view,
            "compliance": comp_view,
        },
        "judge": None,
        "judge_meta": {
            "configured_density_per_30_tick": judge_density,
            "configured_budget_tokens": judge_budget,
        },
    }

    # --- Judge layer (optional) -----------------------------------------
    # Self-sanity mode (无 _judge_pair_against — iter#80 self-bench 不做 pairwise,
    # 仅 rubric on 自身). Pairwise 留给 iter#81 v15-vs-v16 Stage 1 裁决.
    if texts and len(texts) >= 1:
        try:
            from quality_metrics import make_mimo_judge_fn, rubric_judge
        except Exception as e:
            quality["judge"] = {"error": f"import_failed: {e}"}
            return quality

        try:
            judge_fn, judge_model = make_mimo_judge_fn()
        except RuntimeError as e:
            quality["judge"] = {"error": f"judge_unconfigured: {e}"}
            return quality
        except Exception as e:  # pragma: no cover — defensive
            quality["judge"] = {"error": f"judge_init_failed: {e}"}
            return quality

        # 单 bench rubric: 给每段叙述独立打分. 预算意义: 假设每次 rubric
        # ~ 1500 tokens 输入 + 500 输出 = 2k, 50k 预算可跑 25 段.
        rubric_results: list[dict] = []
        approx_cost_each = 2000
        max_samples = max(0, judge_budget // approx_cost_each)
        sampled = texts[:max_samples]
        for t in sampled:
            if not t or not t.strip():
                continue
            try:
                r = await rubric_judge(t, judge_fn=judge_fn, model_name=judge_model)
                rubric_results.append(r.to_dict())
            except Exception as e:
                rubric_results.append({"error": f"rubric_call_failed: {e}"})

        quality["judge"] = {
            "rubric_samples": rubric_results,
            "rubric_count": len(rubric_results),
            "judge_model": judge_model,
        }
        if rubric_results:
            valid = [
                r for r in rubric_results if r.get("mean") and r["mean"] > 0
            ]
            if valid:
                quality["judge"]["rubric_mean"] = round(
                    sum(r["mean"] for r in valid) / len(valid), 4
                )
                quality["judge"]["rubric_mean_count"] = len(valid)

    return quality


def _guess_tier_for(narrator_chars: int) -> str:
    """Approximate narrator's own tier rule for compliance reporting."""
    if narrator_chars <= 0:
        return "none"
    if narrator_chars < 500:
        return "short"
    if narrator_chars < 1100:
        return "medium"
    return "long"


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

    # v2.38 Phase 2 (iter#80) — quality section, mirror image of cost table.
    if "quality" in rep and rep["quality"]:
        q = rep["quality"]
        lines += ["", "## Quality (Phase 2 §3 det + judge)"]

        # Det 1: repetition
        det_rep = q.get("det", {}).get("repetition") or {}
        if det_rep:
            d = det_rep.get("distinct", {})
            o = det_rep.get("overlap_consecutive", {})
            lines += [
                "",
                "### Repetition (det, zero LLM cost)",
                "",
                f"- narration_count: {det_rep.get('narration_count', 0)}",
                f"- distinct char-2/3/4: {d.get('char_2', 0)} / {d.get('char_3', 0)} / {d.get('char_4', 0)}",
                f"- distinct word-2/3/4: {d.get('word_2', 0)} / {d.get('word_3', 0)} / {d.get('word_4', 0)}",
                f"- overlap consecutive char-2/3/4: {o.get('char_2', 0)} / {o.get('char_3', 0)} / {o.get('char_4', 0)}",
                f"- overlap consecutive word-2/3/4: {o.get('word_2', 0)} / {o.get('word_3', 0)} / {o.get('word_4', 0)}",
            ]
            if det_rep.get("notes"):
                lines.append(f"- notes: {', '.join(det_rep['notes'])}")

        # Det 2: consistency
        det_cons = q.get("det", {}).get("consistency") or {}
        if det_cons:
            lines += [
                "",
                "### Consistency (det)",
                "",
                f"- violation_count: {det_cons.get('violation_count', 0)} (high={det_cons.get('high_count', 0)}, medium={det_cons.get('medium_count', 0)})",
            ]
            for v in (det_cons.get("violations") or [])[:5]:
                lines.append(
                    f"  - [{v['severity']}] {v['kind']} @ tick#{v['narration_index']}: `{v['evidence']}`"
                )
            if det_cons.get("notes"):
                lines.append(f"- notes: {', '.join(det_cons['notes'])}")

        # Det 3: compliance
        det_comp = q.get("det", {}).get("compliance") or {}
        if det_comp:
            lines += [
                "",
                "### Compliance (det)",
                "",
                f"- tier_hit_rate: {det_comp.get('tier_hit_rate', 0)} ({det_comp.get('tier_hit_count', 0)}/{det_comp.get('evaluated_count', 0)})",
                f"- schema_violation_rate: {det_comp.get('schema_violation_rate', 0)}",
                f"- reasoning_leak_rate: {det_comp.get('reasoning_leak_rate', 0)}",
                f"- placeholder_leak_rate: {det_comp.get('placeholder_leak_rate', 0)}",
                f"- skipped (should_narrate=False): {det_comp.get('skipped_records', 0)}",
            ]
            if det_comp.get("notes"):
                lines.append(f"- notes: {', '.join(det_comp['notes'])}")

        # Judge layer
        j = q.get("judge")
        lines += ["", "### Judge (LLM, mimo 跨家族)", ""]
        if j is None:
            lines.append("- skipped (no narratives or no config)")
        elif "error" in j:
            lines.append(f"- error: `{j['error']}`")
        else:
            mean = j.get("rubric_mean")
            lines += [
                f"- judge_model: {j.get('judge_model', '?')}",
                f"- rubric samples: {j.get('rubric_count', 0)}",
                f"- rubric mean (3 维平均): {mean if mean is not None else 'n/a'} ({j.get('rubric_mean_count', 0)} valid)",
            ]

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=3)
    parser.add_argument("--seed", default=_DEFAULT_SEED)
    parser.add_argument("--label", default="v0-baseline")
    parser.add_argument("--log-level", default="WARNING")
    # v2.38 Phase 2 (iter#80) — quality metrics integration.
    parser.add_argument(
        "--quality",
        action="store_true",
        help="跑 det 三类指标 + rubric judge (mimo). 见 §3.1+§3.2.",
    )
    parser.add_argument(
        "--judge-density",
        type=int,
        default=10,
        help="每 30 tick 抽多少对 pairwise (Stage 1+). 默认 10 (§7).",
    )
    parser.add_argument(
        "--judge-budget",
        type=int,
        default=50_000,
        help="单次 quality bench judge tokens 总预算 (§7 默认 50k).",
    )
    parser.add_argument(
        "--longrange-every",
        type=int,
        default=5,
        help="Stage 3 longrange 采样间隔 (默认每 5 tick 一次).",
    )
    # iter#121 Phase 3-B cast-confound 控制 — 跨 seed cost variance 实验用.
    parser.add_argument(
        "--cast-a-count", type=int, default=None,
        help="精确 A 级角色数. 不设则 LLM 自由 (wide).",
    )
    parser.add_argument(
        "--cast-b-count", type=int, default=None,
        help="精确 B 级角色数. 不设则 LLM 自由 (wide).",
    )
    parser.add_argument(
        "--cast-c-count", type=int, default=None,
        help="精确 C 级角色数. 不设则 LLM 自由 (wide).",
    )
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
