"""真实推 tick 的最小驱动脚本 — 不启动 FastAPI, 直接调用 Orchestrator。

用法:
    python tools/run_ticks.py --novel-id critique_test --n 5

会调用真实 LLM (按 .env 的 LLM_PROVIDER 选定 provider)。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))
_BACKEND = os.path.join(_ROOT, "backend")
for p in (_ROOT, _BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

logger = logging.getLogger(__name__)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Drive Orchestrator for N ticks")
    parser.add_argument("--novel-id", required=True)
    parser.add_argument("--n", type=int, default=3, help="ticks to advance")
    parser.add_argument(
        "--disable-critic",
        action="store_true",
        help="跳过 NarrativeCritic LLM 调用 (省 token)",
    )
    args = parser.parse_args()

    if args.disable_critic:
        os.environ["NARRATOR_ENABLE_CRITIC"] = "0"

    os.environ["ACTIVE_NOVEL_ID"] = args.novel_id
    os.environ["ACTIVE_NOVEL_DATA_DIR"] = os.path.join(
        _BACKEND, "data", "novels", args.novel_id
    )

    # 读 bootstrap.env 里的 MAIN_TRACKING_CHARACTER_ID
    env_path = os.path.join(os.environ["ACTIVE_NOVEL_DATA_DIR"], "bootstrap.env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    from tick_runtime import TickRuntime

    rt = TickRuntime(novel_id=args.novel_id)
    print(
        f"Driving novel '{rt.novel_id}' from tick={rt.tick_state.current_tick} "
        f"for {args.n} ticks..."
    )
    print(
        f"  agents wired: memory_store={rt.memory_store.size}, "
        f"fact_ledger={rt.fact_ledger.size}, "
        f"branches={[m.branch_id for m in rt.branch_manager.list_branches()]}"
    )

    for i in range(args.n):
        try:
            summary = await rt.orchestrator.run_tick()
        except Exception as e:
            logger.exception("Tick failed: %s", e)
            break
        print(
            f"  tick {summary.tick}: agents={summary.agents_called[:4]}... "
            f"events={len(summary.events_generated)} "
            f"narrator={'YES' if summary.narrator_produced_text else 'no'} "
            f"chars={summary.narrator_output_chars}"
        )

    rt.close()
    # 报告
    snap = rt.token_budget.snapshot
    print(
        f"Done. Total tokens: prompt={snap.total_prompt_tokens}, "
        f"completion={snap.total_completion_tokens}, calls={snap.call_count}"
    )
    print(f"  by_agent: {dict(snap.by_agent)}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "WARNING"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    sys.exit(asyncio.run(main()))
