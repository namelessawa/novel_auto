"""DeepSeek LLM client wrapper using OpenAI-compatible API."""

from __future__ import annotations

import logging
import os
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


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage_prompt_tokens: int
    usage_completion_tokens: int


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


_MAX_TOKENS_CAP = _resolve_max_tokens_cap()


def _clamp_max_tokens(n: int) -> int:
    return min(n, _MAX_TOKENS_CAP) if n > 0 else _MAX_TOKENS_CAP


class LLMClient:
    """Async wrapper around any OpenAI-compatible API (DeepSeek / mimo / custom)."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            max_retries=1,
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
            max_retries=1,
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
        # 非 None / 非空字符串时用本值替代 self._model。当前生产仅支持单 model,
        # 实际生效需在 provider 层做模型路由 (config.json llm.fallback_model);
        # 当 fallback_model 未配置时本字段仅作为标签写入日志, 让调用方可观测。
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

        effective_model = self._model
        if model_override:
            effective_model = model_override
            logger.info(
                "LLMClient.chat override model: agent_id=%s priority=%s override length=%d",
                agent_id,
                priority,
                len(model_override),
            )
        response = await self._client.chat.completions.create(
            model=effective_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=_clamp_max_tokens(max_tokens),
        )
        choice = response.choices[0]
        usage = response.usage
        result = LLMResponse(
            content=choice.message.content or "",
            usage_prompt_tokens=usage.prompt_tokens if usage else 0,
            usage_completion_tokens=usage.completion_tokens if usage else 0,
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

        effective_model = self._model
        if model_override:
            effective_model = model_override
            logger.info(
                "LLMClient.chat_stream override model: agent_id=%s priority=%s override length=%d",
                agent_id,
                priority,
                len(model_override),
            )

        stream = await self._client.chat.completions.create(
            model=effective_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=_clamp_max_tokens(max_tokens),
            stream=True,
            # v2.19 — 请求提供商在最后一个 chunk 返回 usage; 提供商不支持时
            # 自动忽略, 我们的 _capture_usage 静默兼容 None。
            stream_options={"include_usage": True},
        )

        usage_obj: object | None = None
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

        # v2.19 — stream 结束后记账。usage 缺失时仍 record 0 token, 让调用频次
        # 仍可被 snapshot.call_count 看到, 避免静默成无形成本。
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
        try:
            tracker.record(
                agent_id=agent_id,
                priority=priority,  # type: ignore[arg-type]
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=effective_model,
                tick=effective_tick,
            )
        except Exception as e:  # pragma: no cover
            logger.debug("TokenBudgetTracker record (stream) failed: %s", e)


llm_client = LLMClient()
