"""LLMClient 可观测性验证 (v2.16)。

确认:
1. ContextVar 注入的 tick 能被 chat() 自动捕获 (调用方不传 tick 时)
2. 调用方显式传 tick / agent_id / priority 时, TokenBudgetTracker 准确记录
3. set_current_tick 后跨 asyncio.gather 仍然继承

之前的问题: 所有 chat() 调用都没填 agent_id/priority/tick, 导致
TokenBudgetTracker 里全是 "unknown / medium / tick=-1", 无法分析成本结构。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import nf_core.llm_client as llm_module
from nf_core.llm_client import (
    LLMResponse,
    get_current_tick,
    set_current_tick,
)
from nf_core.provider_runtime import (
    ProviderRuntimeConfig,
    provider_client_registry,
    reset_stage_provider_config,
    set_stage_provider_config,
)
from nf_core.token_budget import TokenBudgetTracker, set_global_tracker


@pytest.fixture(autouse=True)
def offline_provider():
    config = ProviderRuntimeConfig.from_explicit(
        provider="test",
        api_key="test-only-key",
        base_url="https://provider.invalid/v1",
        model="test-model",
        source="test_fixture",
    )
    token = set_stage_provider_config(config)
    provider_client_registry.invalidate()
    try:
        yield
    finally:
        provider_client_registry.invalidate()
        reset_stage_provider_config(token)


@pytest.fixture
def fresh_tracker():
    """构造一个干净的 TokenBudgetTracker, 替换全局单例。"""
    tracker = TokenBudgetTracker()
    set_global_tracker(tracker)
    yield tracker
    # 测试结束后重置 contextvar
    set_current_tick(-1)


@pytest.mark.asyncio
async def test_chat_forwards_only_supported_json_object_mode(fresh_tracker):
    seen: dict = {}

    async def fake_create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=fake_create),
        )
    )
    await llm_module.llm_client.chat(
        system_prompt="Return JSON.",
        user_prompt="{}",
        client_override=client,
        response_format={"type": "json_object"},
    )

    assert seen["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_chat_rejects_unsupported_response_format_before_call():
    with pytest.raises(ValueError, match="json_object"):
        await llm_module.llm_client.chat(
            system_prompt="Return JSON.",
            user_prompt="{}",
            response_format={"type": "json_schema"},
        )


@pytest.mark.asyncio
async def test_chat_records_agent_id_and_priority(monkeypatch, fresh_tracker):
    """显式传 agent_id/priority 必须落到 TokenBudgetTracker。"""
    async def fake_create(**kw):
        class _Choice:
            class message:
                content = "ok"
        class _Usage:
            prompt_tokens = 10
            completion_tokens = 5
        class _R:
            choices = [_Choice()]
            usage = _Usage()
        return _R()

    monkeypatch.setattr(
        llm_module.llm_client._client.chat.completions, "create", fake_create
    )

    resp = await llm_module.llm_client.chat(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="narrator",
        priority="critical",
        tick=42,
    )
    assert isinstance(resp, LLMResponse)
    assert fresh_tracker.snapshot.call_count == 1
    assert fresh_tracker.snapshot.by_agent.get("narrator") == 15
    assert fresh_tracker.snapshot.by_priority.get("critical") == 15
    assert fresh_tracker.records[0].tick == 42


@pytest.mark.asyncio
async def test_chat_falls_back_to_contextvar_tick(monkeypatch, fresh_tracker):
    """调用方不传 tick (默认 -1) 时, 必须 fallback 到 contextvar 当前 tick。"""
    async def fake_create(**kw):
        class _Choice:
            class message:
                content = "ok"
        class _Usage:
            prompt_tokens = 4
            completion_tokens = 6
        class _R:
            choices = [_Choice()]
            usage = _Usage()
        return _R()

    monkeypatch.setattr(
        llm_module.llm_client._client.chat.completions, "create", fake_create
    )

    set_current_tick(7)
    await llm_module.llm_client.chat(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="character_agent:alice",
        priority="medium",
        # tick 显式不传, 默认 -1
    )
    # 记录里的 tick 不应是 -1, 而是 contextvar 里的 7
    assert fresh_tracker.records[0].tick == 7
    assert fresh_tracker.records[0].agent_id == "character_agent:alice"


@pytest.mark.asyncio
async def test_contextvar_propagates_into_gather(monkeypatch, fresh_tracker):
    """asyncio.gather 启动的子任务继承父 context, 因此多个角色 agent 并发也归到本 tick。"""
    async def fake_create(**kw):
        class _Choice:
            class message:
                content = "ok"
        class _Usage:
            prompt_tokens = 1
            completion_tokens = 1
        class _R:
            choices = [_Choice()]
            usage = _Usage()
        return _R()

    monkeypatch.setattr(
        llm_module.llm_client._client.chat.completions, "create", fake_create
    )

    set_current_tick(99)

    async def inner(name: str) -> int:
        # 内层不知道 tick, 但 contextvar 已被父设置
        await llm_module.llm_client.chat(
            system_prompt="sys",
            user_prompt="usr",
            agent_id=f"character_agent:{name}",
            priority="medium",
        )
        return get_current_tick()

    ticks = await asyncio.gather(inner("a"), inner("b"), inner("c"))
    assert ticks == [99, 99, 99]
    assert fresh_tracker.snapshot.call_count == 3
    for rec in fresh_tracker.records:
        assert rec.tick == 99


@pytest.mark.asyncio
async def test_explicit_tick_overrides_contextvar(monkeypatch, fresh_tracker):
    """调用方显式传 tick 时不受 contextvar 影响 — bootstrap 场景需要锁 tick=0。"""
    async def fake_create(**kw):
        class _Choice:
            class message:
                content = "ok"
        class _Usage:
            prompt_tokens = 0
            completion_tokens = 0
        class _R:
            choices = [_Choice()]
            usage = _Usage()
        return _R()

    monkeypatch.setattr(
        llm_module.llm_client._client.chat.completions, "create", fake_create
    )

    set_current_tick(50)
    await llm_module.llm_client.chat(
        system_prompt="sys",
        user_prompt="usr",
        agent_id="bootstrap:world",
        priority="medium",
        tick=0,  # 显式 0, 覆盖 contextvar=50
    )
    assert fresh_tracker.records[0].tick == 0
