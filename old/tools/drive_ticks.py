"""[ARCHIVED v2.22] drive_ticks — 不要再运行此脚本。

此脚本自 v2.15 起已与生产 tick_runtime 不兼容: 它直接写 _tr._runtime 单例
(参见下方代码), 而真实运行时使用 _runtimes 注册表 + per-novel TickRuntime
实例。继续运行会旁路 register_to_routes 的注册表查找, 且 close_runtime()
的旧外壳只是 close_all_runtimes() 别名, 不保证清理本脚本创建的 runtime。

要做真实 LLM 端到端冒烟, 请用 tools/run_ticks.py 或直接 POST /api/tick/run。
保留此文件仅供历史参考。

----- 历史文档 -----

drive_ticks - 用真实 LLM 驱动 Orchestrator 跑 N 个 tick, 做端到端冒烟。

历史用法:

    python tools/drive_ticks.py --novel-id test_story_A --max-ticks 30

输出:
* 每 tick 的 TickSummary 一行 JSON 到 stdout
* 持久化写入 backend/data/novels/{novel_id}/  (tick_state.json / narratives/ / ticks.db)
* 退出时打印汇总 + 各 agent 触发次数
"""

import sys

sys.stderr.write(
    "[archived] tools/drive_ticks.py 已归档到 old/tools/, "
    "不再与 v2.15+ tick_runtime 注册表兼容。"
    "请用 tools/run_ticks.py 或 POST /api/tick/run 替代。\n"
)
sys.exit(2)

# --- 以下历史代码保留供参考, 上方 sys.exit 已阻止执行 ---

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_BACKEND = os.path.join(_ROOT, "backend")
for p in (_ROOT, _BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("drive_ticks")


async def run(novel_id: str, max_ticks: int) -> dict:
    data_dir = os.path.join(_BACKEND, "data", "novels", novel_id)
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"novel dir not found: {data_dir}")

    os.environ["ACTIVE_NOVEL_ID"] = novel_id
    os.environ["ACTIVE_NOVEL_DATA_DIR"] = data_dir
    boot_env = os.path.join(data_dir, "bootstrap.env")
    if os.path.exists(boot_env):
        with open(boot_env, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    from tick_runtime import TickRuntime, close_runtime
    import tick_runtime as _tr

    _tr._runtime = TickRuntime(novel_id=novel_id)
    runtime = _tr._runtime
    runtime.register_to_routes()

    logger.info(
        "tick_runtime loaded: tick=%d, chars=%d, open_loops=%d, anchors=%d",
        runtime.tick_state.current_tick,
        len(runtime.character_agents),
        runtime.tick_state.get_open_loop_count(),
        len(runtime.tick_state.list_style_anchors()),
    )

    agent_counts: Counter[str] = Counter()
    narrator_ticks: list[int] = []
    summaries: list[dict] = []

    for _ in range(max_ticks):
        try:
            summary = await runtime.orchestrator.run_tick()
        except Exception as e:
            logger.exception("tick failed: %s", e)
            break

        s = summary.model_dump(mode="json")
        summaries.append(s)
        print(json.dumps({
            "tick": s["tick"],
            "agents": s["agents_called"],
            "events": len(s["events_generated"]),
            "narr": s["narrator_produced_text"],
            "narr_chars": s["narrator_output_chars"],
            "delta": s["state_changes_summary"],
            "hints": s["next_tick_recommendations"][:2],
        }, ensure_ascii=False))

        for a in s["agents_called"]:
            base = a.split("(", 1)[0].split("×", 1)[0]
            agent_counts[base] += 1
        if s["narrator_produced_text"]:
            narrator_ticks.append(s["tick"])

    close_runtime()

    return {
        "ticks_run": len(summaries),
        "agent_counts": dict(agent_counts),
        "narrator_ticks": narrator_ticks,
        "final_tick": summaries[-1]["tick"] if summaries else -1,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--novel-id", required=True)
    parser.add_argument("--max-ticks", type=int, default=30)
    args = parser.parse_args(argv)
    result = asyncio.run(run(args.novel_id, args.max_ticks))
    print("=" * 60)
    print("RESULT:", json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
