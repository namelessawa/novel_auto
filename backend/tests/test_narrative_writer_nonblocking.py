"""Orchestrator._default_narrative_writer 不阻塞 event loop (v2.19.4)。

Narrator 每 tick 产出后调用 _default_narrative_writer 落盘 1.5k-3k 字 narrative。
此前实现是 ``async def`` + 内部裸 ``os.makedirs`` / ``with open(...)`` 同步 IO,
async 函数 await 这层时整个 event loop 被磁盘 IO 阻塞 5-50ms。

v2.18 Phase 7 把 Narrator 与只读 agent (Guardian / Critic / ArcTracker) 并行,
预期通过 asyncio.gather 让他们和 Narrator 拉 LLM 时间重叠。但如果 Narrator 写盘
依然阻塞 event loop, 只读 agent 的 LLM 回调也无法继续处理 — 并发收益打折。

修复: 用 asyncio.to_thread 把同步 IO 卸到 worker 线程。

本测试钉死:
* 文件实际被写入 + 内容正确 (黑盒回归)
* 写入操作不在主 asyncio 线程上执行 (white-box 闭环验证)
* 与一个 await asyncio.sleep(0.05) 并发时, 两者总耗时 ≈ max(各自耗时),
  而不是 sum (event loop 没被阻塞)
"""

from __future__ import annotations

import asyncio
import os
import threading
import time

import pytest

from agents.orchestrator import Orchestrator
from memory.tick_state import TickState
from memory_system.models import WorldState


@pytest.fixture
def orch(tmp_path):
    """最小 Orchestrator — 只用 _default_narrative_writer, 不跑完整 tick。"""
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(WorldState())
    # 无视所有可选 agent — 我们只测 narrative_writer
    o = Orchestrator(
        tick_state=ts,
        world_simulator=None,  # type: ignore[arg-type]
        character_agents={},
        narrator=None,  # type: ignore[arg-type]
        action_resolver=None,  # type: ignore[arg-type]
    )
    return o, ts


@pytest.mark.asyncio
async def test_narrative_writer_writes_file_correctly(orch) -> None:
    """黑盒回归: 文件按预期写入 + 编码正确。"""
    o, ts = orch
    await o._default_narrative_writer(tick=42, text="风雪夜归人。")
    path = os.path.join(ts.data_dir, "narratives", "tick_000042.txt")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        assert f.read() == "风雪夜归人。"


@pytest.mark.asyncio
async def test_narrative_writer_runs_off_main_thread(orch, monkeypatch) -> None:
    """关键: 同步 IO 必须卸到 worker 线程, 不在主 asyncio loop 线程跑。

    实现方式: monkeypatch open() 让它记录所在线程 id; 主线程 id (调用方所在
    的 asyncio loop 线程) 必须 != 记录到的写入线程 id。
    """
    o, _ = orch
    import builtins
    real_open = builtins.open
    write_thread_id = {"value": None}

    def tracking_open(*args, **kwargs):
        write_thread_id["value"] = threading.get_ident()
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", tracking_open)
    main_thread_id = threading.get_ident()
    await o._default_narrative_writer(tick=1, text="x")
    assert write_thread_id["value"] is not None, "open() 没被调用"
    assert write_thread_id["value"] != main_thread_id, (
        f"narrative_writer 仍在主 event loop 线程上跑 IO (tid="
        f"{write_thread_id['value']}, main={main_thread_id}); "
        "应通过 asyncio.to_thread 卸到 worker。"
    )


@pytest.mark.asyncio
async def test_narrative_writer_does_not_block_loop(orch, monkeypatch) -> None:
    """端到端: 模拟一个 80ms 慢写盘 + 并行 80ms asyncio.sleep,
    并发应在 ~80-130ms 完成, 而不是 ~160ms (= 写 + sleep)。"""
    o, _ = orch
    import builtins
    real_open = builtins.open

    def slow_open(*args, **kwargs):
        time.sleep(0.08)  # 模拟 80ms 慢盘
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", slow_open)
    t0 = time.monotonic()
    await asyncio.gather(
        o._default_narrative_writer(tick=99, text="slow disk test"),
        asyncio.sleep(0.08),
    )
    elapsed = time.monotonic() - t0
    # 若仍同步 IO: ≈ 0.16s (串行); 若 to_thread: ≈ 0.08-0.13s (并行)
    # 留 50ms buffer for Windows scheduler 抖动
    assert elapsed < 0.13, (
        f"async narrative_writer 不该阻塞 event loop; "
        f"并发耗时 {elapsed*1000:.0f}ms, 期望 < 130ms (= max(80, 80) + buffer)"
    )
