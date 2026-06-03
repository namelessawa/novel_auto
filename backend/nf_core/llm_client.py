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
from nf_core.token_budget import get_global_tracker

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
    ) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=self._model,
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
                model=self._model,
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
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=_clamp_max_tokens(max_tokens),
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content


llm_client = LLMClient()
