"""chat_stream 可观测性 + 预算闭环 (v2.19)。

chat() 已通过 v2.16 接入 ContextVar / TokenBudgetTracker, 而 chat_stream() 此前
完全脱离: 不做 budget pre-check, 不记账, 不读 ContextVar, 不支持 model_override。
legacy 节级 SSE 管线 (writer_agent.write_stream → llm_client.chat_stream) 是真实活
路径, 每段 1.5k-3k 字的写作如果不入 tracker, 生产成本完全不可见。

本测试确认 chat_stream 与 chat 行为对齐:
1. 调用前 tracker.can_afford 被检查; 拒绝时抛 BudgetExceeded, 底层 create 不被调
2. 流式过程结束后, usage 从带 usage 字段的 chunk 提取并入 tracker
3. 提供商不返回 usage (mimo / 部分 deepseek 边缘场景) 时, 不崩溃, 静默不记账
4. tick 显式不传时 fallback 到 ContextVar
5. model_override 透传到底层 create() 调用
6. stream_options={"include_usage": True} 被透传给底层
"""

from __future__ import annotations

from typing import Any

import pytest

import nf_core.llm_client as llm_module
from nf_core.llm_client import set_current_tick
from nf_core.token_budget import (
    BudgetExceeded,
    TokenBudgetTracker,
    set_global_tracker,
)


# ------------------------------------------------------------------
# fixtures + stream stub
# ------------------------------------------------------------------


@pytest.fixture
def fresh_tracker():
    tracker = TokenBudgetTracker()
    set_global_tracker(tracker)
    yield tracker
    set_current_tick(-1)


class _FakeDelta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str | None) -> None:
        self.delta = _FakeDelta(content)


class _FakeUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeChunk:
    """模拟 OpenAI SDK 的 ChatCompletionChunk:
    * 普通内容 chunk: choices=[delta(content=...)], usage=None
    * usage chunk (stream_options.include_usage=True 时): choices=[], usage=...
    """

    def __init__(
        self,
        content: str | None = None,
        usage: _FakeUsage | None = None,
    ) -> None:
        self.choices = [_FakeChoice(content)] if content is not None else []
        self.usage = usage


class _AsyncStream:
    def __init__(self, chunks: list[_FakeChunk]) -> None:
        self._iter = iter(chunks)

    def __aiter__(self) -> "_AsyncStream":
        return self

    async def __anext__(self) -> _FakeChunk:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _patch_create(monkeypatch, chunks: list[_FakeChunk]) -> dict[str, Any]:
    """Patch llm_client._client.chat.completions.create to return a fake stream
    of the given chunks. Captures kwargs in the returned dict (single dict so
    asserts can read after the stream completes)."""
    captured: dict[str, Any] = {}

    async def fake_create(**kw):
        captured.clear()
        captured.update(kw)
        # OpenAI SDK 在 stream=True 时直接返回 AsyncStream 对象; 我们的
        # _AsyncStream 满足同样的 async-iter 协议
        return _AsyncStream(chunks)

    monkeypatch.setattr(
        llm_module.llm_client._client.chat.completions,
        "create",
        fake_create,
    )
    return captured


# ------------------------------------------------------------------
# 1. usage 记账 — 从最后含 usage 字段的 chunk 提取
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_records_usage_from_final_chunk(
    monkeypatch, fresh_tracker
):
    chunks = [
        _FakeChunk(content="hello "),
        _FakeChunk(content="world"),
        _FakeChunk(usage=_FakeUsage(prompt_tokens=42, completion_tokens=18)),
    ]
    _patch_create(monkeypatch, chunks)

    pieces: list[str] = []
    async for chunk in llm_module.llm_client.chat_stream(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="writer_agent",
        priority="critical",
        tick=12,
    ):
        pieces.append(chunk)

    assert "".join(pieces) == "hello world"
    assert fresh_tracker.snapshot.call_count == 1
    rec = fresh_tracker.records[0]
    assert rec.agent_id == "writer_agent"
    assert rec.priority == "critical"
    assert rec.prompt_tokens == 42
    assert rec.completion_tokens == 18
    assert rec.tick == 12


# ------------------------------------------------------------------
# 2. tick fallback — 默认 -1 时读 ContextVar
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_tick_falls_back_to_contextvar(
    monkeypatch, fresh_tracker
):
    chunks = [
        _FakeChunk(content="x"),
        _FakeChunk(usage=_FakeUsage(prompt_tokens=3, completion_tokens=2)),
    ]
    _patch_create(monkeypatch, chunks)

    set_current_tick(77)
    # 故意不传 tick — 默认 -1, 应 fallback 到 contextvar=77
    async for _ in llm_module.llm_client.chat_stream(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="writer_agent",
        priority="critical",
    ):
        pass

    assert fresh_tracker.records[0].tick == 77


# ------------------------------------------------------------------
# 3. budget pre-check 拦截 — BudgetExceeded 抛出, 底层 create 不被调
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_rejected_by_budget_does_not_call_create(monkeypatch):
    tracker = TokenBudgetTracker(max_total_tokens=100)
    # 预灌 95 token, 让 optional 的 70% 阈值立刻被超过
    tracker.record(
        agent_id="setup",
        priority="medium",
        prompt_tokens=50,
        completion_tokens=45,
    )
    set_global_tracker(tracker)

    called = {"flag": False}

    async def must_not_be_called(**kw):  # pragma: no cover — 期望永不被调
        called["flag"] = True
        return _AsyncStream([])

    monkeypatch.setattr(
        llm_module.llm_client._client.chat.completions,
        "create",
        must_not_be_called,
    )

    with pytest.raises(BudgetExceeded):
        async for _ in llm_module.llm_client.chat_stream(
            system_prompt="sys",
            user_prompt="usr",
            agent_id="optional_critic",
            priority="optional",
            max_tokens=50,
        ):
            pass

    assert called["flag"] is False, "底层 create 不该被调用"
    set_current_tick(-1)


# ------------------------------------------------------------------
# 4. critical 即使爆预算也放行 — Narrator/Writer 不可掐断
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_critical_bypasses_budget(monkeypatch, fresh_tracker):
    fresh_tracker._max_total = 10  # 强制极小预算
    fresh_tracker.record(
        agent_id="setup",
        priority="critical",
        prompt_tokens=100,
        completion_tokens=100,
    )

    chunks = [
        _FakeChunk(content="ok"),
        _FakeChunk(usage=_FakeUsage(prompt_tokens=1, completion_tokens=1)),
    ]
    _patch_create(monkeypatch, chunks)

    pieces: list[str] = []
    async for c in llm_module.llm_client.chat_stream(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="writer_agent",
        priority="critical",
    ):
        pieces.append(c)
    assert "".join(pieces) == "ok"


# ------------------------------------------------------------------
# 5. 提供商不返回 usage — 不崩溃, 静默
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_handles_missing_usage(monkeypatch, fresh_tracker):
    chunks = [
        _FakeChunk(content="a"),
        _FakeChunk(content="b"),
        # 没有 usage chunk — 部分提供商不支持 stream_options.include_usage
    ]
    _patch_create(monkeypatch, chunks)

    pieces: list[str] = []
    async for c in llm_module.llm_client.chat_stream(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="writer_agent",
        priority="critical",
    ):
        pieces.append(c)
    assert "".join(pieces) == "ab"
    # tracker 记账可以为 0 (record 0 tokens) 或 完全不 record; 两种实现都可接受。
    # 关键: 不崩溃, 调用方拿到完整文本。
    if fresh_tracker.snapshot.call_count == 1:
        rec = fresh_tracker.records[0]
        assert rec.prompt_tokens == 0
        assert rec.completion_tokens == 0


# ------------------------------------------------------------------
# 6. model_override 透传 — 让 Guardian 降级建议也能影响 streaming 写作
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_model_override_passed_to_create(
    monkeypatch, fresh_tracker
):
    chunks = [
        _FakeChunk(content="ok"),
        _FakeChunk(usage=_FakeUsage(prompt_tokens=2, completion_tokens=3)),
    ]
    captured = _patch_create(monkeypatch, chunks)

    async for _ in llm_module.llm_client.chat_stream(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="writer_agent",
        priority="critical",
        model_override="haiku-mini",
    ):
        pass

    assert captured.get("model") == "haiku-mini"
    # 记账上的 model 也应是 override 后的, 跟 chat() 行为一致
    assert fresh_tracker.records[0].model == "haiku-mini"


# ------------------------------------------------------------------
# 7. stream_options.include_usage 透传 — 让提供商返回 usage chunk
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_requests_usage_via_stream_options(
    monkeypatch, fresh_tracker
):
    chunks = [_FakeChunk(content="x")]
    captured = _patch_create(monkeypatch, chunks)

    async for _ in llm_module.llm_client.chat_stream(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="writer_agent",
        priority="critical",
    ):
        pass

    stream_opts = captured.get("stream_options")
    assert stream_opts == {"include_usage": True}, (
        "应透传 stream_options 以获取 usage chunk; "
        f"实际收到: {stream_opts!r}"
    )


# ------------------------------------------------------------------
# 8. stream 中途抛异常 — 至少 record 一次失败尝试, 让监控看到
# ------------------------------------------------------------------


class _ExplodingStream:
    """模拟 OpenAI SDK 在 stream 进行中抛出 APIError 之类的错误
    (实际场景: provider 502 / 网络断 / safety filter 触发)。"""

    def __init__(self, good_chunks_before_boom: list[_FakeChunk]) -> None:
        self._chunks = list(good_chunks_before_boom)

    def __aiter__(self) -> "_ExplodingStream":
        return self

    async def __anext__(self):
        if self._chunks:
            return self._chunks.pop(0)
        # 模拟 stream 中途 502 — 不抛 StopAsyncIteration, 而是真实异常
        raise RuntimeError("upstream API 502 mid-stream")


@pytest.mark.asyncio
async def test_chat_stream_exception_still_records_attempt(
    monkeypatch, fresh_tracker
):
    """stream 中途抛错时, 异常正常传播给调用方, 但 tracker 必须看到这次
    "失败尝试" — 否则失败的大段写作完全不进 monitoring, 生产侧成本/失败率
    全是虚低数据。"""

    async def boom_create(**kw):
        # 先送一个 content chunk, 再在下一次 anext 时炸 — 模拟 partial 输出
        return _ExplodingStream([_FakeChunk(content="开始写...")])

    monkeypatch.setattr(
        llm_module.llm_client._client.chat.completions, "create", boom_create
    )

    with pytest.raises(RuntimeError, match="502"):
        async for _ in llm_module.llm_client.chat_stream(
            system_prompt="sys",
            user_prompt="usr",
            agent_id="writer_agent",
            priority="critical",
            tick=33,
        ):
            pass

    assert fresh_tracker.snapshot.call_count == 1, (
        f"失败的 stream 也应在 tracker 留下 1 条记录, 否则失败率不可观测。"
        f"实际 call_count={fresh_tracker.snapshot.call_count}"
    )
    rec = fresh_tracker.records[0]
    assert rec.agent_id == "writer_agent"
    assert rec.tick == 33
    # 失败时没收到 usage chunk, 记 0 token 是合理的
    assert rec.prompt_tokens == 0
    assert rec.completion_tokens == 0
