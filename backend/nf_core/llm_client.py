"""DeepSeek LLM client wrapper using OpenAI-compatible API."""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, AsyncIterator

from nf_core.provider_runtime import (
    ProviderError,
    ProviderRuntimeConfig,
    ProviderRuntimeReceipt,
    classify_provider_exception,
    get_request_provider_config,
    provider_client_registry,
    provider_output_invalid,
    reset_request_provider_config,
    resolve_provider_runtime,
    set_request_provider_config,
)
from nf_core.token_budget import BudgetExceeded, get_global_tracker

logger = logging.getLogger(__name__)


# v2.16 — Observability: current tick propagated via ContextVar so every LLM
# call can be attributed to a tick without threading the value through every
# agent signature. Orchestrator sets this at the start of run_tick(); inner
# agents (CharacterAgent, NarratorAgent, ...) leave their chat() kwarg
# ``tick`` at the default and the client resolves -1 → contextvar value.
# asyncio gather/Task inherits the parent context, so batch_decide() and any
# nested concurrent agent calls automatically see the right tick.
_current_tick_var: ContextVar[int] = ContextVar("llm_current_tick", default=-1)


def set_current_tick(tick: int) -> None:
    """Set the tick attribution for subsequent llm_client.chat() calls.

    Called by Orchestrator at the start of every run_tick. Safe to call from
    any context (test setup also uses this to fix tick=0 / tick=42 ...).
    """
    _current_tick_var.set(tick)


def get_current_tick() -> int:
    """Read the tick attribution. Returns -1 when nobody has set it yet."""
    return _current_tick_var.get()


# v2.28 — 用户态 LLM 凭据 ContextVar.
#
# 设计: middleware (backend/middleware/user_llm.py) 在请求入口读 header
# (X-User-LLM-Key / Base-Url / Model) 写入这个 ContextVar; LLMClient.chat()
# 在调用前检查 — 有值就用用户的 key, 没值就退回 self._client (config.json
# 兜底)。
#
# 与 _current_tick_var 同样原理 — asyncio.create_task 默认拷贝 context,
# 用户在 /api/section/generate 触发的后台任务自动继承请求时的凭据。
@dataclass(frozen=True)
class UserLLMConfig:
    api_key: str
    base_url: str = ""
    model: str = ""
    provider: str = ""
    thinking_mode: str = ""
    timeout: float = 600.0
    max_retries: int = 0
    temperature: float = 0.7
    max_tokens_cap: int = 65536


def set_user_llm_config(
    *,
    api_key: str,
    base_url: str = "",
    model: str = "",
    provider: str = "",
    thinking_mode: str = "",
    timeout: float | None = None,
    max_retries: int | None = None,
    temperature: float | None = None,
    max_tokens_cap: int | None = None,
) -> Token[ProviderRuntimeConfig | None]:
    """Middleware 调用 — 把请求里的用户凭据写入 ContextVar。"""
    config = ProviderRuntimeConfig.from_user_request(
        api_key=api_key,
        provider=provider,
        base_url=base_url,
        model=model,
        thinking_mode=thinking_mode,
        timeout=timeout if timeout is not None else 600.0,
        max_retries=max_retries if max_retries is not None else 0,
        temperature=temperature if temperature is not None else 0.7,
        max_tokens_cap=max_tokens_cap if max_tokens_cap is not None else 65536,
    )
    return set_request_provider_config(config)


def reset_user_llm_config(
    token: Token[ProviderRuntimeConfig | None],
) -> None:
    reset_request_provider_config(token)


def get_user_llm_config() -> UserLLMConfig | None:
    config = get_request_provider_config()
    if config is None:
        return None
    return UserLLMConfig(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        provider=config.provider,
        thinking_mode=config.thinking_mode,
        timeout=config.timeout,
        max_retries=config.max_retries,
        temperature=config.temperature,
        max_tokens_cap=config.max_tokens_cap,
    )


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage_prompt_tokens: int
    usage_completion_tokens: int
    # Phase 5-A: 暴露 OpenAI SDK 的 prompt_tokens_details.cached_tokens (provider
    # 不支持时为 0). 让 narrator cache 重排能直接量化命中率, 而不是只看总 token
    # 趋势猜测。
    usage_cached_tokens: int = 0
    provider: str = ""
    model: str = ""
    provider_source: str = ""
    provider_config_fingerprint: str = ""
    provider_runtime_receipt: ProviderRuntimeReceipt | None = None


def _resolve_timeout() -> float:
    raw = os.environ.get("LLM_TIMEOUT") or os.environ.get("DEEPSEEK_TIMEOUT") or "600"
    try:
        return float(raw)
    except ValueError:
        return 600.0


def _resolve_max_tokens_cap() -> int:
    """Hard ceiling for completion tokens, clamping over-aggressive call sites.

    Different providers cap completion tokens differently (mimo-v2.5-pro: 131072,
    deepseek-chat: 8192). Set ``LLM_MAX_TOKENS_CAP`` to override; default 65536
    is safe for both and large enough for any single completion.
    """
    raw = os.environ.get("LLM_MAX_TOKENS_CAP", "65536")
    try:
        v = int(raw)
        return v if v > 0 else 65536
    except ValueError:
        return 65536


def _clamp_max_tokens(n: int, cap: int | None = None) -> int:
    """HIGH fix (code review 2026-06-17): lazy 读 env, 与其他 _resolve_* helper 一致.

    历史 module-level 冻结的 _MAX_TOKENS_CAP 让 hot-reload 路径无法切换 cap —
    生产 server 启动后改 LLM_MAX_TOKENS_CAP 静默无效. 现在每次 chat() 调用都按
    当前 env 解析.
    """
    effective_cap = cap if cap is not None else _resolve_max_tokens_cap()
    return min(n, effective_cap) if n > 0 else effective_cap


def _resolve_max_retries() -> int:
    """env-driven retry count for AsyncOpenAI client.

    历史默认 0 (不重试) — 为了让真错误 (bad input / config 错) 立即可见, 不被
    silent retry 掩盖. ARK 配额耗尽场景下任何瞬时 429 也立挂 → matrix bench
    全军覆没. 用 env override 让 bench/批处理路径选择性开启指数退避.

    返回值传给 ``AsyncOpenAI(max_retries=...)``, SDK 自带 exponential backoff
    + 仅对 429/500/502/503/504 重试 (不重试 400 类用户错).
    """
    raw = os.environ.get("LLM_MAX_RETRIES", "0").strip()
    try:
        v = int(raw)
        return max(0, v)
    except ValueError:
        return 0


def _resolve_per_call_sleep() -> float:
    """env-driven per-call throttle (seconds) — 跨 ARK TPM 窗口的救命旋钮.

    历史默认 0 (无 sleep) 保持 production 路径 bit-identical.
    bench / 批处理场景设 ``LLM_PER_CALL_SLEEP=N`` 在每个 chat() 调用前 asyncio.sleep(N).
    ARK 经验: 单 cell bench_tick ~30 LLM calls 在 30s 内突发, 撞 TPM 窗口立 429.
    sleep(3) 摊到 ~90s/cell, 让 TPM 窗口有时间 refill.

    注意: asyncio.sleep 释放 event loop, 同 cell 内并发的 character_agents 仍
    用 asyncio.gather 并发, 但每个 worker 自己 sleep 3s, 总体节流 ~5-6x 慢.
    """
    raw = os.environ.get("LLM_PER_CALL_SLEEP", "0").strip()
    try:
        v = float(raw)
        return max(0.0, v)
    except ValueError:
        return 0.0


def _resolve_extra_body(thinking_mode: str | None = None) -> dict | None:
    """Phase 5-A: env-driven extra_body for provider-specific quirks.

    现在只用于 ARK volces 的 thinking-disable. ``LLM_THINKING_MODE=disabled``
    时把 ARK 的 thinking trace 关掉 — 实测 deepseek-v4-pro 在长中文 + complex
    schema 下推理 trace 漏进 content, JSON 解析 60% 失败. 关掉后 5/5 通过且
    completion_tokens 直接降 ~16%.

    其他取值留作未来扩展 (例如 enabled / auto), 当前一律忽略, 返回 None.
    返回 None 时调用方不传 extra_body, 与原生 OpenAI 调用完全一致.
    """
    mode = (
        thinking_mode
        if thinking_mode is not None
        else os.environ.get("LLM_THINKING_MODE")
    )
    mode = (mode or "").strip().lower()
    if mode == "disabled":
        return {"thinking": {"type": "disabled"}}
    return None


def _extract_cached_tokens(usage_obj) -> int:
    """Safe pull of usage.prompt_tokens_details.cached_tokens (provider-optional).

    OpenAI / DeepSeek / ARK 等暴露 prefix cache hit 数通过 ``prompt_tokens_details``
    嵌套字段. 不存在时 (mimo / 老 deepseek-chat) 直接 0, 不影响调用方。
    """
    if usage_obj is None:
        return 0
    details = getattr(usage_obj, "prompt_tokens_details", None)
    if details is None:
        return 0
    val = getattr(details, "cached_tokens", None)
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def extract_message_text(message) -> str:
    """OpenAI 响应 message 抽正文 — 兼容 reasoning 模型.

    DeepSeek-Reasoner / MiMo / QwQ 等推理模型在 max_tokens 不够时, 思维链
    会占满 budget, ``message.content`` 是空字符串, 真正答案在
    ``message.reasoning_content``. 这种情况下取 reasoning_content 的尾段
    比向上抛 "LLM 返回为空" 友好得多.

    OpenAI 官方 SDK 的 ChatCompletionMessage 是 pydantic 模型, 未知字段
    塞 ``model_extra``; 部分二改 SDK 直接挂属性. 两路都试.
    """
    content = (getattr(message, "content", None) or "").strip()
    if content:
        return content
    extra = getattr(message, "model_extra", None) or {}
    rc = (
        extra.get("reasoning_content")
        or getattr(message, "reasoning_content", None)
        or ""
    )
    return str(rc).strip()


class LLMClient:
    """Async wrapper around any OpenAI-compatible API (DeepSeek / mimo / custom)."""

    def __init__(self) -> None:
        # Intentionally empty: importing this module must not resolve credentials
        # or create a network client.
        pass

    @property
    def _client(self):
        """Compatibility view used by older tests and diagnostics."""
        config = resolve_provider_runtime()
        return provider_client_registry.get_client(config)

    @property
    def _model(self) -> str:
        return resolve_provider_runtime().model

    def reload(
        self,
        *,
        config: ProviderRuntimeConfig | None = None,
        provider: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        thinking_mode: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        temperature: float | None = None,
        max_tokens_cap: int | None = None,
    ) -> dict:
        """Resolve a runtime and retire cached clients without changing context."""
        has_overrides = any(
            value is not None
            for value in (
                provider,
                api_key,
                base_url,
                model,
                thinking_mode,
                timeout,
                max_retries,
                temperature,
                max_tokens_cap,
            )
        )
        if config is not None:
            current = config
        elif (
            api_key is not None
            and base_url is not None
            and model is not None
        ):
            current = ProviderRuntimeConfig.from_explicit(
                provider=provider or "custom",
                api_key=api_key,
                base_url=base_url,
                model=model,
                thinking_mode=thinking_mode or "",
                timeout=timeout if timeout is not None else 600,
                max_retries=max_retries if max_retries is not None else 0,
                temperature=temperature if temperature is not None else 0.7,
                max_tokens_cap=(
                    max_tokens_cap if max_tokens_cap is not None else 65536
                ),
                source="explicit",
            )
            has_overrides = False
        else:
            current = resolve_provider_runtime()
        if has_overrides:
            current = ProviderRuntimeConfig.from_explicit(
                provider=provider or current.provider,
                api_key=api_key if api_key is not None else current.api_key,
                base_url=(
                    base_url if base_url is not None else current.base_url
                ),
                model=model if model is not None else current.model,
                thinking_mode=(
                    thinking_mode
                    if thinking_mode is not None
                    else current.thinking_mode
                ),
                timeout=timeout if timeout is not None else current.timeout,
                max_retries=(
                    max_retries
                    if max_retries is not None
                    else current.max_retries
                ),
                temperature=(
                    temperature
                    if temperature is not None
                    else current.temperature
                ),
                max_tokens_cap=(
                    max_tokens_cap
                    if max_tokens_cap is not None
                    else current.max_tokens_cap
                ),
                source="explicit",
            )
        provider_client_registry.invalidate()
        logger.info(
            "LLM runtime reloaded (provider=%s, fingerprint=%s)",
            current.provider,
            current.config_fingerprint,
        )
        return current.diagnostics()

    async def aclose(self) -> None:
        await provider_client_registry.aclose_all()

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int = 4096,
        # v2.7 — 调用方可标注用途, 自动入 TokenBudgetTracker
        agent_id: str = "unknown",
        priority: str = "medium",
        tick: int = -1,
        # v2.18 Phase 6 — Guardian 监控建议降级时, Orchestrator 阶段 3 注入。
        # 非 None / 非空字符串时直接替换 self._model 传给底层 OpenAI 客户端 ——
        # 上层 provider (deepseek/mimo/custom) 暴露的 model 名是字符串, 替换后
        # 直接被 chat.completions.create() 路由。调用方在 logger.info 里能看到
        # override 长度作为可观测信号。
        model_override: str | None = None,
        provider_config: ProviderRuntimeConfig | None = None,
        client_override: Any | None = None,
        response_format: dict[str, str] | None = None,
    ) -> LLMResponse:
        if response_format is not None and response_format != {
            "type": "json_object"
        }:
            raise ValueError(
                "response_format must be exactly {'type': 'json_object'}"
            )
        # v2.17 — 调用前硬拦截。token_budget 之前只「记账」, README 写的
        # 「optional 退化、medium 拒绝」从未连到执行路径。现在: priority=critical
        # 一律放行(Narrator/Guardian 不可被掐断); medium/optional 由 tracker
        # 按全局/本 tick 预算阈值决定。被拒绝时抛 BudgetExceeded — 调用方既有的
        # ``try/except`` 兜底会把它视作软失败, 自动落回降级输出。
        tracker = get_global_tracker()
        try:
            allowed = tracker.can_afford(
                priority=priority,  # type: ignore[arg-type]
                # 用 max_tokens 作为开销上限的乐观估计 — 调用方传 4096 我们就
                # 按 4096 占预算; 高估总好过低估让 critic/novelty 把 budget 吃光。
                estimated_tokens=max_tokens,
            )
        except Exception as e:  # pragma: no cover — tracker 故障不应阻塞主流程
            logger.debug("TokenBudgetTracker can_afford raised: %s", e)
            allowed = True
        if not allowed:
            raise BudgetExceeded(
                agent_id=agent_id,
                priority=priority,
                reason=(
                    f"tracker rejected (max_total={tracker.max_total}, "
                    f"max_per_tick={tracker.max_per_tick}, "
                    f"used={tracker.snapshot.total_tokens})"
                ),
            )

        config = resolve_provider_runtime(provider_config)
        lease = (
            None
            if client_override is not None
            else provider_client_registry.acquire(config)
        )
        client = client_override if client_override is not None else lease.client
        effective_model = model_override or config.model
        if model_override:
            logger.info(
                "LLMClient.chat override model: agent_id=%s priority=%s override length=%d",
                agent_id,
                priority,
                len(model_override),
            )
        # Phase 5-A: env-driven extra_body (现在用于 ARK thinking-disable).
        # _resolve_extra_body 返回 None 时不传, 保持与老调用 bit-identical.
        _create_kwargs: dict = {
            "model": effective_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": (
                config.temperature if temperature is None else temperature
            ),
            "max_tokens": _clamp_max_tokens(max_tokens, config.max_tokens_cap),
        }
        _extra = _resolve_extra_body(config.thinking_mode)
        if _extra:
            _create_kwargs["extra_body"] = _extra
        if response_format is not None:
            # The GLM-compatible API documents JSON-object mode. It improves
            # syntactic reliability only; callers must still validate their
            # JSON schema and all semantic/length contracts locally.
            _create_kwargs["response_format"] = {"type": "json_object"}
        try:
            # Phase 5+: per-call throttle 跨 ARK TPM 窗口. 默认 0 = 无 sleep.
            _sleep = _resolve_per_call_sleep()
            if _sleep > 0:
                import asyncio as _async

                await _async.sleep(_sleep)
            try:
                response = await client.chat.completions.create(**_create_kwargs)
            except Exception as exc:
                raise classify_provider_exception(exc, config) from exc
            try:
                choices = getattr(response, "choices", None) or []
                if not choices:
                    raise provider_output_invalid(config)
                choice = choices[0]
                usage = getattr(response, "usage", None)
                content = extract_message_text(choice.message)
                if not content:
                    raise provider_output_invalid(
                        config,
                        "模型服务返回为空",
                    )
                result = LLMResponse(
                    content=content,
                    usage_prompt_tokens=(
                        int(getattr(usage, "prompt_tokens", 0) or 0)
                        if usage
                        else 0
                    ),
                    usage_completion_tokens=(
                        int(getattr(usage, "completion_tokens", 0) or 0)
                        if usage
                        else 0
                    ),
                    usage_cached_tokens=_extract_cached_tokens(usage),
                    provider=config.provider,
                    model=config.model,
                    provider_source=config.source,
                    provider_config_fingerprint=config.config_fingerprint,
                    provider_runtime_receipt=ProviderRuntimeReceipt(
                        provider=config.provider,
                        model=config.model,
                        thinking_mode=config.thinking_mode,
                        max_retries=config.max_retries,
                        source=config.source,
                        config_fingerprint=config.config_fingerprint,
                    ),
                )
            except ProviderError:
                raise
            except Exception as exc:
                raise provider_output_invalid(config) from exc
            # v2.16 — 调用方未显式传 tick 时, 用 ContextVar 中 orchestrator 设的当前 tick。
            effective_tick = tick if tick != -1 else _current_tick_var.get()
            try:
                get_global_tracker().record(
                    agent_id=agent_id,
                    priority=priority,  # type: ignore[arg-type]
                    prompt_tokens=result.usage_prompt_tokens,
                    completion_tokens=result.usage_completion_tokens,
                    cached_tokens=result.usage_cached_tokens,
                    model=effective_model,
                    tick=effective_tick,
                )
            except Exception as e:  # pragma: no cover
                logger.debug("TokenBudgetTracker record failed: %s", e)
            return result
        finally:
            if lease is not None:
                lease.release()

    async def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int = 4096,
        # v2.19 — 与 chat() 对齐, 让节级 SSE (writer_agent.write_stream)
        # 也走 budget pre-check + ContextVar tick + tracker 记账。
        agent_id: str = "unknown",
        priority: str = "medium",
        tick: int = -1,
        model_override: str | None = None,
        provider_config: ProviderRuntimeConfig | None = None,
        client_override: Any | None = None,
    ) -> AsyncIterator[str]:
        # v2.19 — 调用前 budget pre-check, 与 chat() 同源逻辑。
        # 注意: async generator 的 body 在第一次 __anext__ 时才执行, 因此调用方
        # `async for chunk in chat_stream(...)` 的第一次拉取就会触发 BudgetExceeded,
        # 在底层 _client.chat.completions.create 被调用之前完成拦截。
        tracker = get_global_tracker()
        try:
            allowed = tracker.can_afford(
                priority=priority,  # type: ignore[arg-type]
                estimated_tokens=max_tokens,
            )
        except Exception as e:  # pragma: no cover — tracker 故障不阻塞主流程
            logger.debug("TokenBudgetTracker can_afford raised: %s", e)
            allowed = True
        if not allowed:
            raise BudgetExceeded(
                agent_id=agent_id,
                priority=priority,
                reason=(
                    f"tracker rejected stream (max_total={tracker.max_total}, "
                    f"max_per_tick={tracker.max_per_tick}, "
                    f"used={tracker.snapshot.total_tokens})"
                ),
            )

        config = resolve_provider_runtime(provider_config)
        lease = (
            None
            if client_override is not None
            else provider_client_registry.acquire(config)
        )
        client = client_override if client_override is not None else lease.client
        effective_model = model_override or config.model
        if model_override:
            logger.info(
                "LLMClient.chat_stream override model: agent_id=%s priority=%s override length=%d",
                agent_id,
                priority,
                len(model_override),
            )

        # Phase 5-A: 与 chat() 同源, env-driven extra_body 关 ARK thinking.
        _stream_kwargs: dict = {
            "model": effective_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": (
                config.temperature if temperature is None else temperature
            ),
            "max_tokens": _clamp_max_tokens(max_tokens, config.max_tokens_cap),
            "stream": True,
            # v2.19 — 请求提供商在最后一个 chunk 返回 usage; 提供商不支持时
            # 自动忽略, 我们的 _capture_usage 静默兼容 None。
            "stream_options": {"include_usage": True},
        }
        _extra = _resolve_extra_body(config.thinking_mode)
        if _extra:
            _stream_kwargs["extra_body"] = _extra
        usage_obj: object | None = None
        emitted_content = False
        # v2.19.5 — 用 try/finally 包裹 stream 消费, 让失败 (provider 502 /
        # 网络断 / safety filter mid-stream) 也至少 record 一次。否则失败的大段
        # 写作完全不进 tracker, 生产监控的失败率全是虚低数据。
        try:
            # Phase 5+: per-call throttle. 与 chat() 同源.
            _sleep = _resolve_per_call_sleep()
            if _sleep > 0:
                import asyncio as _async

                await _async.sleep(_sleep)
            stream = await client.chat.completions.create(**_stream_kwargs)
            async for chunk in stream:
                # usage chunk 在 stream_options.include_usage=True 时通常 choices=[]
                # 且 usage 非 None — 不要因为 choices 空就崩溃。
                choices = getattr(chunk, "choices", None) or []
                if choices:
                    delta = getattr(choices[0], "delta", None)
                    if getattr(delta, "content", None):
                        emitted_content = True
                        yield delta.content
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    # 用最后一个含 usage 的 chunk — 提供商规范是最后一帧给最终统计
                    usage_obj = chunk_usage
            if not emitted_content:
                raise provider_output_invalid(config, "模型服务返回为空")
        except Exception as exc:
            raise classify_provider_exception(exc, config) from exc
        finally:
            if lease is not None:
                lease.release()
            # 不管成功还是异常, 都尝试记账一次。usage 缺失时记 0 token, 让调用
            # 频次仍能反映在 snapshot.call_count 与 by_agent 上。
            effective_tick = tick if tick != -1 else _current_tick_var.get()
            prompt_tokens = (
                int(getattr(usage_obj, "prompt_tokens", 0) or 0)
                if usage_obj is not None
                else 0
            )
            completion_tokens = (
                int(getattr(usage_obj, "completion_tokens", 0) or 0)
                if usage_obj is not None
                else 0
            )
            # Phase 5-A: stream API 也尝试取 cached_tokens (provider 不暴露时 0).
            cached_tokens = _extract_cached_tokens(usage_obj)
            try:
                tracker.record(
                    agent_id=agent_id,
                    priority=priority,  # type: ignore[arg-type]
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cached_tokens=cached_tokens,
                    model=effective_model,
                    tick=effective_tick,
                )
            except Exception as e:  # pragma: no cover
                logger.debug("TokenBudgetTracker record (stream) failed: %s", e)


llm_client = LLMClient()
