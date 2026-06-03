"""Smoke 测试: 用真实 LLM 跑 v2.18 改动, 验证 mock 测试覆盖不到的真实路径。

观察重点:
1. money_delta / new_location / inventory_added 字段真实出现率
2. *_without_action / location_without_move / money_overdraft 命中
3. hallucination_hits / degrade_recommendations (Guardian 在 tick=30 触发)
4. model_tier_override 不被误激活 (默认 shadow mode)
5. cooldown 命中情况
6. LLM 失败计数

用法:
    python scripts/smoke_v218.py --ticks 35 --novel-id smoke_v218

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

# 设置 ACTIVE_NOVEL_ID 在 import tick_runtime 之前
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
    """从 TickState / TickDB 抽取 v2.18 关心的指标。"""
    ts = rt.tick_state
    states = ts.list_character_states()

    money_distribution = {s.character_id: s.money for s in states}
    inventory_sizes = {s.character_id: len(s.inventory) for s in states}
    status_summary = {s.character_id: list(s.status_effects) for s in states}
    location_summary = {s.character_id: s.current_location for s in states}

    # 一次性 query 全 tick 区间事件
    events = rt.tick_db.get_events_in_range(start_tick, end_tick)
    flag_counts: dict[str, int] = {}
    total_action_events = 0
    per_char_action_counts: dict[str, int] = {}
    per_char_flag_counts: dict[str, dict[str, int]] = {}
    for e in events:
        # ticks.db 列名是 event_type (TickDB._event_row_to_dict 不重命名);
        # Pydantic Event 字段名是 type — 两种来源都要兼容。
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

    # AgentRuntimeState
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
    finally:
        metrics = _collect_metrics(rt, start_tick, last_tick)
        rt.close()

    # 输出报告
    print("\n" + "=" * 60)
    print("SMOKE TEST REPORT")
    print("=" * 60)
    print(f"Ticks attempted: {n_ticks}")
    print(f"Ticks succeeded: {n_ticks - len(failed_ticks)}")
    print(f"Ticks failed: {len(failed_ticks)}")
    for t, msg in failed_ticks[:5]:
        print(f"  ↳ tick {t}: {msg[:200]}")
    print()

    # 把 metrics 写文件 + 屏幕打印 JSON
    out_path = Path(rt.data_dir) / "smoke_report.json"
    out_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Full metrics → {out_path}")
    print()
    print("--- Key indicators ---")
    print(
        f"Action events recorded: {metrics['total_action_events']}"
    )
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

    return 0 if not failed_ticks else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="v2.18 真实 LLM smoke 测试")
    parser.add_argument("--novel-id", default="smoke_v218")
    parser.add_argument("--ticks", type=int, default=35)
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()
    return asyncio.run(
        run_smoke(args.novel_id, args.ticks, args.log_level)
    )


if __name__ == "__main__":
    sys.exit(main())
