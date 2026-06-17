"""DeepSeek LLM client wrapper using OpenAI-compatible API."""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass
from typing import AsyncIterator

import httpx
from openai import AsyncOpenAI

from config.settings import settings
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


_user_llm_var: ContextVar[UserLLMConfig | None] = ContextVar(
    "llm_user_config", default=None
)


def set_user_llm_config(*, api_key: str, base_url: str = "", model: str = "") -> None:
    """Middleware 调用 — 把请求里的用户凭据写入 ContextVar。"""
    _user_llm_var.set(
        UserLLMConfig(api_key=api_key, base_url=base_url, model=model)
    )


def get_user_llm_config() -> UserLLMConfig | None:
    return _user_llm_var.get()


# 客户端缓存: 按 (api_key, base_url) 缓存 AsyncOpenAI; 避免每请求重建连接池。
# LRU + 上限 — 防止恶意 / 误传大量不同 key 造成内存膨胀。
_USER_CLIENT_CACHE_MAX = 32
_user_client_cache: "OrderedDict[tuple[str, str], AsyncOpenAI]" = OrderedDict()
_user_client_lock = threading.Lock()


def _get_user_client(cfg: UserLLMConfig) -> AsyncOpenAI:
    base = cfg.base_url or "https://api.deepseek.com"
    key = (cfg.api_key, base)
    with _user_client_lock:
        client = _user_client_cache.get(key)
        if client is not None:
            _user_client_cache.move_to_end(key)
            return client
        # _get_user_client also picks up LLM_MAX_RETRIES — per-user clients
        # benefit from the same backoff knob during bench / batch flows.
        client = AsyncOpenAI(
            api_key=cfg.api_key,
            base_url=base,
            max_retries=_resolve_max_retries(),
            timeout=httpx.Timeout(_resolve_timeout(), connect=15.0),
        )
        _user_client_cache[key] = client
        while len(_user_client_cache) > _USER_CLIENT_CACHE_MAX:
            _user_client_cache.popitem(last=False)
        return client


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage_prompt_tokens: int
    usage_completion_tokens: int
    # Phase 5-A: 暴露 OpenAI SDK 的 prompt_tokens_details.cached_tokens (provider
    # 不支持时为 0). 让 narrator cache 重排能直接量化命中率, 而不是只看总 token
    # 趋势猜测。
    usage_cached_tokens: int = 0


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


def _clamp_max_tokens(n: int) -> int:
    """HIGH fix (code review 2026-06-17): lazy 读 env, 与其他 _resolve_* helper 一致.

    历史 module-level 冻结的 _MAX_TOKENS_CAP 让 hot-reload 路径无法切换 cap —
    生产 server 启动后改 LLM_MAX_TOKENS_CAP 静默无效. 现在每次 chat() 调用都按
    当前 env 解析.
    """
    cap = _resolve_max_tokens_cap()
    return min(n, cap) if n > 0 else cap


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


def _resolve_extra_body() -> dict | None:
    """Phase 5-A: env-driven extra_body for provider-specific quirks.

    现在只用于 ARK volces 的 thinking-disable. ``LLM_THINKING_MODE=disabled``
    时把 ARK 的 thinking trace 关掉 — 实测 deepseek-v4-pro 在长中文 + complex
    schema 下推理 trace 漏进 content, JSON 解析 60% 失败. 关掉后 5/5 通过且
    completion_tokens 直接降 ~16%.

    其他取值留作未来扩展 (例如 enabled / auto), 当前一律忽略, 返回 None.
    返回 None 时调用方不传 extra_body, 与原生 OpenAI 调用完全一致.
    """
    mode = (os.environ.get("LLM_THINKING_MODE") or "").strip().lower()
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
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            max_retries=_resolve_max_retries(),
            timeout=httpx.Timeout(_resolve_timeout(), connect=15.0),
        )
        self._model = settings.deepseek_model

    # v2.17 — 热更新入口。PUT /api/config/llm 写完 config.json 后调用本方法,
    # 调用方无需重启进程。注意: 主项目 .env 设置的 LLM_PROVIDER 仍然优先 ——
    # _resolve_llm_block 的源优先级保持不变。
    def reload(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> dict:
        """重建 AsyncOpenAI 客户端。

        显式参数为 None 时,从 config.json/主项目 .env 重新解析当前值。
        返回应用到客户端的有效配置(供调用方记日志)。
        """
        from config.settings import resolve_llm_block_now

        if api_key is None or base_url is None or model is None:
            block = resolve_llm_block_now()
            eff_key = api_key if api_key is not None else block.get("api_key", "")
            eff_url = base_url if base_url is not None else block.get("base_url", "")
            eff_model = model if model is not None else block.get("model", "")
            source = block.get("source", "unknown")
        else:
            eff_key, eff_url, eff_model, source = api_key, base_url, model, "explicit"

        # AsyncOpenAI 没有显式 close() 同步方法; 释放旧 client 引用即可让 GC 接管
        # httpx 连接池。下次 chat() 用新 _client 发起新连接,旧连接随 GC 释放。
        self._client = AsyncOpenAI(
            api_key=eff_key,
            base_url=eff_url,
            max_retries=_resolve_max_retries(),
            timeout=httpx.Timeout(_resolve_timeout(), connect=15.0),
        )
        self._model = eff_model
        # v2.17 — 故意不 logger.info() base_url/model/source 字符串: 它们在 CodeQL
        # 视图里都从含 api_key 的 block dict 派生, 直接日志会触发
        # py/clear-text-logging-sensitive-data。调用方拿到返回 dict 后可自行决定
        # 是否记账, 是否脱敏。
        logger.info("LLMClient reloaded (model length=%d, base_url length=%d)",
                    len(eff_model), len(eff_url))
        return {"base_url": eff_url, "model": eff_model, "source": source}

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
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
    ) -> LLMResponse:
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

        # v2.28 — 优先用 ContextVar 里的用户 LLM 凭据 (per-request),
        # 没有才退回 self._client (config.json 兜底, 兼容 dev / 后台任务)。
        user_cfg = get_user_llm_config()
        if user_cfg and user_cfg.api_key:
            client = _get_user_client(user_cfg)
            effective_model = (
                model_override
                or user_cfg.model
                or self._model
            )
        else:
            client = self._client
            effective_model = model_override or self._model
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
            "temperature": temperature,
            "max_tokens": _clamp_max_tokens(max_tokens),
        }
        _extra = _resolve_extra_body()
        if _extra:
            _create_kwargs["extra_body"] = _extra
        # Phase 5+: per-call throttle 跨 ARK TPM 窗口. 默认 0 = 无 sleep.
        _sleep = _resolve_per_call_sleep()
        if _sleep > 0:
            import asyncio as _async
            await _async.sleep(_sleep)
        response = await client.chat.completions.create(**_create_kwargs)
        choice = response.choices[0]
        usage = response.usage
        # extract_message_text: content 空时退到 reasoning_content, 兼容
        # MiMo / DeepSeek-Reasoner 等推理模型在 max_tokens 不够时正文丢失.
        result = LLMResponse(
            content=extract_message_text(choice.message),
            usage_prompt_tokens=usage.prompt_tokens if usage else 0,
            usage_completion_tokens=usage.completion_tokens if usage else 0,
            usage_cached_tokens=_extract_cached_tokens(usage),
        )
        # v2.16 — 调用方未显式传 tick 时, 用 ContextVar 中 orchestrator 设的当前 tick。
        # 这让 CharacterAgent / NarratorAgent 等内层 agent 无需修改签名也能正确归账。
        effective_tick = tick if tick != -1 else _current_tick_var.get()
        # 记账 — 失败不阻塞主流程
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

    async def chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        # v2.19 — 与 chat() 对齐, 让节级 SSE (writer_agent.write_stream)
        # 也走 budget pre-check + ContextVar tick + tracker 记账。
        agent_id: str = "unknown",
        priority: str = "medium",
        tick: int = -1,
        model_override: str | None = None,
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

        # v2.28 — 同 chat(): 用户凭据优先
        user_cfg = get_user_llm_config()
        if user_cfg and user_cfg.api_key:
            client = _get_user_client(user_cfg)
            effective_model = (
                model_override
                or user_cfg.model
                or self._model
            )
        else:
            client = self._client
            effective_model = model_override or self._model
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
            "temperature": temperature,
            "max_tokens": _clamp_max_tokens(max_tokens),
            "stream": True,
            # v2.19 — 请求提供商在最后一个 chunk 返回 usage; 提供商不支持时
            # 自动忽略, 我们的 _capture_usage 静默兼容 None。
            "stream_options": {"include_usage": True},
        }
        _extra = _resolve_extra_body()
        if _extra:
            _stream_kwargs["extra_body"] = _extra
        # Phase 5+: per-call throttle. 与 chat() 同源.
        _sleep = _resolve_per_call_sleep()
        if _sleep > 0:
            import asyncio as _async
            await _async.sleep(_sleep)
        stream = await client.chat.completions.create(**_stream_kwargs)

        usage_obj: object | None = None
        # v2.19.5 — 用 try/finally 包裹 stream 消费, 让失败 (provider 502 /
        # 网络断 / safety filter mid-stream) 也至少 record 一次。否则失败的大段
        # 写作完全不进 tracker, 生产监控的失败率全是虚低数据。
        try:
            async for chunk in stream:
                # usage chunk 在 stream_options.include_usage=True 时通常 choices=[]
                # 且 usage 非 None — 不要因为 choices 空就崩溃。
                choices = getattr(chunk, "choices", None) or []
                if choices:
                    delta = choices[0].delta
                    if getattr(delta, "content", None):
                        yield delta.content
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    # 用最后一个含 usage 的 chunk — 提供商规范是最后一帧给最终统计
                    usage_obj = chunk_usage
        finally:
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
