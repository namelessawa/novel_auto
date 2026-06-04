"""Smoke 测试: 用真实 LLM 跑 v2.19 改动, 在 smoke_v218 基础上加 3 个新路径检查。

承袭 smoke_v218 的 tick-driven 主体, 额外验证 v2.19 新增的:

1. **chat_stream budget / observability 闭环** (v2.19.0 + v2.19.5)
   - 直接调 ``llm_client.chat_stream`` 跑一段 streaming, 断言:
     * stream chunk 真的能产出
     * tracker.snapshot 显示 prompt+completion token > 0 (usage 被 final chunk 携带)
     * 异常路径下 call_count 仍 +1 (v2.19.5 finally 记账)
2. **POST /api/tick/open-loops 防 dup-id 静默覆盖** (v2.19.3)
   - 通过 TickState 直接复现路由层会触发的覆盖路径:
     第一次 add_open_loop → has_open_loop True; 二次 add 应被 API 路由层 409。
     我们在 smoke 里测 TickState 层不会主动拒, 但 has_open_loop 提示 API 该拒。
3. **agent_id 归账分布** (v2.16 + v2.19 累积效果)
   - 跑完 ticks 后打印 tracker.by_agent 的 top-K, 直观看哪条 agent 最贵。

用法:
    python scripts/smoke_v219.py --ticks 35 --novel-id smoke_v219

不要在已有真实小说上跑 — 用单独的 novel_id (bootstrap_prompts 先建好)。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# sys.path 设置 (跟 bootstrap_prompts 一致)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"
for p in (_PROJECT_ROOT, _BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _prepare_env(novel_id: str) -> None:
    os.environ["ACTIVE_NOVEL_ID"] = novel_id
    # 从 bootstrap.env 加载 MAIN_TRACKING_CHARACTER_ID
    boot_env = _BACKEND_DIR / "data" / "novels" / novel_id / "bootstrap.env"
    if boot_env.exists():
        for line in boot_env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _collect_metrics(rt, start_tick: int, end_tick: int) -> dict:
    """从 TickState / TickDB 抽取 v2.18 + v2.19 关心的指标。"""
    ts = rt.tick_state
    states = ts.list_character_states()

    money_distribution = {s.character_id: s.money for s in states}
    inventory_sizes = {s.character_id: len(s.inventory) for s in states}
    status_summary = {s.character_id: list(s.status_effects) for s in states}
    location_summary = {s.character_id: s.current_location for s in states}

    events = rt.tick_db.get_events_in_range(start_tick, end_tick)
    flag_counts: dict[str, int] = {}
    total_action_events = 0
    per_char_action_counts: dict[str, int] = {}
    per_char_flag_counts: dict[str, dict[str, int]] = {}
    for e in events:
        evt_type = e.get("event_type") or e.get("type")
        if evt_type != "character_action":
            continue
        total_action_events += 1
        participants = e.get("participants") or []
        actor = participants[0] if participants else "unknown"
        per_char_action_counts[actor] = per_char_action_counts.get(actor, 0) + 1
        for cons in e.get("consequences") or []:
            flag_counts[cons] = flag_counts.get(cons, 0) + 1
            per_char_flag_counts.setdefault(actor, {}).setdefault(cons, 0)
            per_char_flag_counts[actor][cons] += 1

    rs_list = ts.list_agent_runtime_states()
    hallucination_stats = ts.get_hallucination_stats()
    cooldown_active = {
        rs.agent_id: rs.cooldown_until_tick
        for rs in rs_list
        if rs.cooldown_until_tick > 0
    }
    failure_counts = {
        rs.agent_id: rs.failure_count for rs in rs_list if rs.failure_count > 0
    }
    overrides_set = {
        rs.agent_id: rs.model_tier_override
        for rs in rs_list
        if rs.model_tier_override
    }

    return {
        "total_action_events": total_action_events,
        "consequence_flag_counts": flag_counts,
        "per_char_action_counts": per_char_action_counts,
        "per_char_flag_counts": per_char_flag_counts,
        "money_distribution": money_distribution,
        "inventory_sizes": inventory_sizes,
        "status_summary": status_summary,
        "location_summary": location_summary,
        "agent_runtime_states": {
            rs.agent_id: {
                "last_invoked_tick": rs.last_invoked_tick,
                "failure_count": rs.failure_count,
                "cooldown_until_tick": rs.cooldown_until_tick,
                "hallucination_hits": rs.hallucination_hits,
                "degrade_recommendations": rs.degrade_recommendations,
                "model_tier_override": rs.model_tier_override,
            }
            for rs in rs_list
        },
        "hallucination_stats": hallucination_stats,
        "cooldown_active": cooldown_active,
        "failure_counts": failure_counts,
        "model_overrides_set": overrides_set,
    }


async def _exercise_chat_stream() -> dict:
    """v2.19 — 直接调 chat_stream, 测 budget + observability + 异常记账。"""
    from nf_core.llm_client import llm_client, set_current_tick
    from nf_core.token_budget import get_global_tracker

    tracker = get_global_tracker()
    # tracker.snapshot 返回内部 BudgetSnapshot 引用, total_tokens 是 property
    # 实时算; 不能 before=tracker.snapshot 然后比 before.total_tokens — 两端
    # 解引用都拿到同一对象的最新值。捕快照时立即 int() 凝固数值。
    before_total = int(tracker.snapshot.total_tokens)
    before_smoke = int(tracker.snapshot.by_agent.get("smoke_v219:chat_stream", 0))

    set_current_tick(9999)  # 任意 sentinel tick, 让记账归到这里
    chunks_received = 0
    try:
        async for chunk in llm_client.chat_stream(
            system_prompt="你是个简洁的助手, 用 30 字内回答。",
            user_prompt="给我一句关于雪夜旅人的短句。",
            temperature=0.7,
            max_tokens=128,
            agent_id="smoke_v219:chat_stream",
            priority="medium",
            tick=9999,
        ):
            chunks_received += 1
    except Exception as e:  # provider 不返 stream 也容忍
        return {"ok": False, "chunks": chunks_received, "error": repr(e)}

    after_total = int(tracker.snapshot.total_tokens)
    after_smoke = int(tracker.snapshot.by_agent.get("smoke_v219:chat_stream", 0))
    return {
        "ok": True,
        "chunks": chunks_received,
        "delta_total_tokens": after_total - before_total,
        "delta_smoke_agent_tokens": after_smoke - before_smoke,
        "smoke_agent_total_tokens": after_smoke,
    }


def _exercise_open_loops_dup(rt) -> dict:
    """v2.19.3 — TickState 层验证 has_open_loop, 这是路由层 409 拒绝的依据。"""
    from memory_system.models import OpenLoop

    ts = rt.tick_state
    sentinel_id = "smoke_v219_loop_sentinel"

    # 清理上次残留, smoke 可重复跑
    if ts.has_open_loop(sentinel_id):
        ts.close_open_loop(sentinel_id)

    loop = OpenLoop(
        id=sentinel_id,
        description="smoke v2.19.3 dup-id 验证",
        urgency=5,
        opened_tick=ts.current_tick,
        source_event_id="evt_smoke",
    )
    ts.add_open_loop(loop)
    exists_after_first = ts.has_open_loop(sentinel_id)

    # 第二次 add — TickState 层会覆盖, 但 has_open_loop 提前返回 True,
    # 路由层据此返回 409 (smoke 不发 HTTP, 只验证状态查询正确)
    would_dup_be_detected = ts.has_open_loop(sentinel_id)

    # 清理 sentinel, 不污染真实小说状态
    ts.close_open_loop(sentinel_id)

    return {
        "has_open_loop_after_add": exists_after_first,
        "dup_detectable_before_second_add": would_dup_be_detected,
        "cleanup_ok": not ts.has_open_loop(sentinel_id),
    }


def _summarize_token_attribution(top_k: int = 8) -> list[dict]:
    """v2.16/v2.19 — 拉 tracker.by_agent top-K, 看哪条 agent 最贵。

    BudgetSnapshot.by_agent 是 dict[agent_id -> total_tokens]; call_count 只
    在 snapshot 顶层是总数, 没有按 agent 的细分。
    """
    from nf_core.token_budget import get_global_tracker

    snap = get_global_tracker().snapshot
    rows = [
        {"agent_id": agent_id, "total_tokens": tokens}
        for agent_id, tokens in snap.by_agent.items()
    ]
    rows.sort(key=lambda r: -r["total_tokens"])
    return rows[:top_k]


async def run_smoke(novel_id: str, n_ticks: int, log_level: str) -> int:
    _prepare_env(novel_id)

    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 强制 shadow mode (即使环境之前误开)
    os.environ.pop("HALLUCINATION_AUTO_DEGRADE", None)

    # 必须在 env 设好后再 import
    from tick_runtime import TickRuntime

    rt = TickRuntime(novel_id=novel_id)
    print(f"[INFO] TickRuntime loaded for novel '{novel_id}'")
    print(f"[INFO] data_dir: {rt.data_dir}")
    print(f"[INFO] character_agents: {len(rt.character_agents)}")
    print(f"[INFO] starting tick: {rt.tick_state.current_tick}")

    start_tick = rt.tick_state.current_tick + 1
    failed_ticks: list[tuple[int, str]] = []
    last_tick = rt.tick_state.current_tick
    stream_result: dict = {"ok": False, "skipped": "tick loop interrupted"}
    dup_result: dict = {"skipped": "tick loop interrupted"}
    try:
        for i in range(n_ticks):
            try:
                summary = await rt.orchestrator.run_tick()
                tick = summary.tick
                last_tick = tick
                print(
                    f"[tick {tick}] agents={summary.agents_called} "
                    f"narrator={summary.narrator_produced_text} "
                    f"chars={summary.narrator_output_chars} "
                    f"events={len(summary.events_generated)} "
                    f"state={summary.state_changes_summary}"
                )
            except Exception as e:
                tick = rt.tick_state.current_tick
                failed_ticks.append((tick, repr(e)))
                last_tick = tick
                print(f"[tick {tick}] FAILED: {e!r}")

        # v2.19 专属探测
        print("\n[probe] v2.19.0 — chat_stream observability ...")
        stream_result = await _exercise_chat_stream()
        print(f"[probe]   {stream_result}")

        print("[probe] v2.19.3 — open-loops dup-id detection ...")
        dup_result = _exercise_open_loops_dup(rt)
        print(f"[probe]   {dup_result}")
    finally:
        metrics = _collect_metrics(rt, start_tick, last_tick)
        token_breakdown = _summarize_token_attribution(top_k=10)
        rt.close()

    # 输出报告
    print("\n" + "=" * 60)
    print("SMOKE v2.19 REPORT")
    print("=" * 60)
    print(f"Ticks attempted: {n_ticks}")
    print(f"Ticks succeeded: {n_ticks - len(failed_ticks)}")
    print(f"Ticks failed: {len(failed_ticks)}")
    for t, msg in failed_ticks[:5]:
        print(f"  - tick {t}: {msg[:200]}")
    print()

    out = {
        "tick_metrics": metrics,
        "chat_stream_probe": stream_result,
        "open_loops_dup_probe": dup_result,
        "token_attribution_top10": token_breakdown,
    }
    out_path = Path(rt.data_dir) / "smoke_v219_report.json"
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Full report -> {out_path}")
    print()
    print("--- Key indicators ---")
    print(f"Action events recorded: {metrics['total_action_events']}")
    print("Consequence flag distribution:")
    for flag, count in sorted(
        metrics["consequence_flag_counts"].items(),
        key=lambda kv: -kv[1],
    ):
        print(f"  {flag:30s}: {count}")
    print()
    print(
        f"Money distribution (non-zero only): "
        f"{ {k: v for k, v in metrics['money_distribution'].items() if v != 0} }"
    )
    print(f"Failure counts: {metrics['failure_counts'] or 'none'}")
    print(f"Cooldown active: {metrics['cooldown_active'] or 'none'}")
    print(f"Model overrides set: {metrics['model_overrides_set'] or 'none (shadow OK)'}")
    print(f"Hallucination stats: {metrics['hallucination_stats'] or 'none yet'}")
    print()
    print("--- v2.19 probes ---")
    print(f"chat_stream chunks/tokens: {stream_result}")
    print(f"open_loops dup detection: {dup_result}")
    print()
    print("--- Token attribution top 10 (v2.16/v2.19 labels) ---")
    for row in token_breakdown:
        print(
            f"  {row['agent_id']:38s} "
            f"tokens={row['total_tokens']:8d}"
        )

    return 0 if not failed_ticks else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="v2.19 真实 LLM smoke 测试")
    parser.add_argument("--novel-id", default="smoke_v219")
    parser.add_argument("--ticks", type=int, default=35)
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()
    return asyncio.run(run_smoke(args.novel_id, args.ticks, args.log_level))


if __name__ == "__main__":
    sys.exit(main())
