"""LLM-judge runner — pairwise + rubric (Phase 2 §3.2).

设计:

* judge LLM 调用走独立 client (不复用 production 路径的 llm_client), 由
  Phase 2 §7 固化为 mimo-v2.5-pro 跨家族评判 (`MIMO_API_KEY` + `MIMO_BASE_URL`
  + `MIMO_MODEL`). 单独 client 避免 production 切换 provider 时把 judge 也带跑.
* 预算硬上限 50k tokens / bench (caller 在外面递减计数; 这里只产单次结果).
* pairwise A/B 位置随机化在 runner 一层做 — caller 给 v_x_text / v_y_text,
  我们内部随机决定哪个是 'A' 哪个是 'B', 然后把 winner 映射回 v_x_wins /
  v_y_wins / tie. 这样 caller 不需要管 position bias.
* 每条结果同时写元数据 (model / prompt version / 随机化 seed), 进 bench 产物.

iter#79 落地 runner + 单元测试 (mock LLM response). iter#80 才会在
bench_tick.py 接通真实调用.
"""

from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

from quality_metrics.judge_prompts import (
    PAIRWISE_PROMPT_V1,
    PAIRWISE_VERSION,
    RUBRIC_PROMPT_V1,
    RUBRIC_VERSION,
)

logger = logging.getLogger(__name__)


# Type for a judge LLM call: takes a prompt string, returns model JSON-as-string.
# Caller-provided so tests can mock without touching real LLM.
JudgeFn = Callable[[str], Awaitable[str]]


@dataclass
class JudgeMeta:
    """Metadata that travels with every judge result for audit."""

    model: str
    prompt_version: str
    # Used for pairwise. Empty for rubric.
    swap_applied: bool = False
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "prompt_version": self.prompt_version,
            "swap_applied": self.swap_applied,
            "extra": dict(self.extra),
        }


@dataclass
class PairwiseResult:
    winner: Literal["x", "y", "tie", "parse_error"]
    reason: str
    meta: JudgeMeta
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "winner": self.winner,
            "reason": self.reason,
            "meta": self.meta.to_dict(),
            "raw_response": self.raw_response,
        }


@dataclass
class RubricResult:
    coherence: int  # 1-5; 0 means parse_error
    character_voice: int
    plot_progression: int
    reason: str
    meta: JudgeMeta
    raw_response: str = ""

    @property
    def total(self) -> int:
        return self.coherence + self.character_voice + self.plot_progression

    @property
    def mean(self) -> float:
        return self.total / 3 if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "coherence": self.coherence,
            "character_voice": self.character_voice,
            "plot_progression": self.plot_progression,
            "total": self.total,
            "mean": round(self.mean, 4),
            "reason": self.reason,
            "meta": self.meta.to_dict(),
            "raw_response": self.raw_response,
        }


# ---------------------------------------------------------------------------
# Internal parsing helpers
# ---------------------------------------------------------------------------


def _safe_json_loads(raw: str) -> dict | None:
    """LLM 偶发用 markdown 围栏包 JSON; 多层 fallback."""
    if not raw:
        return None
    txt = raw.strip()
    # Strip ```json ... ```
    if txt.startswith("```"):
        first_nl = txt.find("\n")
        if first_nl > 0:
            txt = txt[first_nl + 1 :]
        if txt.endswith("```"):
            txt = txt[: -3]
    txt = txt.strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        # Try grabbing the first {...} block
        start = txt.find("{")
        end = txt.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(txt[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _clamp_score(v) -> int:
    """1-5 clamp; non-int or out-of-range → 0 (parse error sentinel)."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    if 1 <= n <= 5:
        return n
    return 0


# ---------------------------------------------------------------------------
# Public runners
# ---------------------------------------------------------------------------


async def pairwise_judge(
    text_x: str,
    text_y: str,
    *,
    judge_fn: JudgeFn,
    model_name: str,
    rng: random.Random | None = None,
) -> PairwiseResult:
    """跑一次 pairwise A/B 盲评. 调用方给 X/Y, 我们随机化 A/B 顺序.

    ``judge_fn`` 接受 prompt 字符串, 返回 LLM raw 响应 (async).
    """
    rng = rng or random.Random()
    swap = rng.random() < 0.5
    if swap:
        # X 占 B 位
        prompt = PAIRWISE_PROMPT_V1.format(text_a=text_y, text_b=text_x)
    else:
        prompt = PAIRWISE_PROMPT_V1.format(text_a=text_x, text_b=text_y)

    meta = JudgeMeta(
        model=model_name,
        prompt_version=PAIRWISE_VERSION,
        swap_applied=swap,
    )
    try:
        raw = await judge_fn(prompt)
    except Exception as e:
        logger.warning("pairwise judge call failed: %s", e)
        return PairwiseResult(
            winner="parse_error",
            reason=f"judge_call_failed: {type(e).__name__}",
            meta=meta,
            raw_response="",
        )

    payload = _safe_json_loads(raw)
    if not payload:
        return PairwiseResult(
            winner="parse_error",
            reason="json_parse_failed",
            meta=meta,
            raw_response=raw,
        )

    label = str(payload.get("winner", "")).strip().upper()
    reason = str(payload.get("reason", "")).strip()[:200]
    # Map judge's A/B → caller's X/Y
    if label == "A":
        winner = "y" if swap else "x"
    elif label == "B":
        winner = "x" if swap else "y"
    elif label == "TIE":
        winner = "tie"
    else:
        return PairwiseResult(
            winner="parse_error",
            reason=f"unrecognized_winner_label={label!r}",
            meta=meta,
            raw_response=raw,
        )
    return PairwiseResult(winner=winner, reason=reason, meta=meta, raw_response=raw)


async def rubric_judge(
    text: str,
    *,
    judge_fn: JudgeFn,
    model_name: str,
) -> RubricResult:
    """跑一次 rubric 打分. 三维独立 1-5, parse 失败给 0 哨兵."""
    prompt = RUBRIC_PROMPT_V1.format(text=text)
    meta = JudgeMeta(model=model_name, prompt_version=RUBRIC_VERSION)
    try:
        raw = await judge_fn(prompt)
    except Exception as e:
        logger.warning("rubric judge call failed: %s", e)
        return RubricResult(
            coherence=0,
            character_voice=0,
            plot_progression=0,
            reason=f"judge_call_failed: {type(e).__name__}",
            meta=meta,
            raw_response="",
        )

    payload = _safe_json_loads(raw)
    if not payload:
        return RubricResult(
            coherence=0,
            character_voice=0,
            plot_progression=0,
            reason="json_parse_failed",
            meta=meta,
            raw_response=raw,
        )

    return RubricResult(
        coherence=_clamp_score(payload.get("coherence")),
        character_voice=_clamp_score(payload.get("character_voice")),
        plot_progression=_clamp_score(payload.get("plot_progression")),
        reason=str(payload.get("reason", "")).strip()[:200],
        meta=meta,
        raw_response=raw,
    )


# ---------------------------------------------------------------------------
# Default judge_fn factory — production wiring for Phase 2 §7
# ---------------------------------------------------------------------------


def make_mimo_judge_fn(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    timeout_sec: float = 120.0,
    max_tokens: int = 1024,
) -> tuple[JudgeFn, str]:
    """Return (judge_fn, resolved_model_name).

    Defaults pull from MIMO_* env vars set in .env. Phase 2 §7 default judge
    is `mimo-v2.5-pro` (跨家族评判 — narrator 是 qwen, judge 用 mimo).

    Caller in bench_tick.py wraps the returned function with budget accounting.
    """
    api_key = api_key or os.environ.get("MIMO_API_KEY", "")
    base_url = base_url or os.environ.get(
        "MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1"
    )
    model = model or os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

    if not api_key:
        raise RuntimeError(
            "MIMO_API_KEY 未配置. Phase 2 judge 用 mimo 跨家族, "
            "请在 .env 设置 MIMO_API_KEY / MIMO_BASE_URL / MIMO_MODEL."
        )

    # Lazy import — keep heavy openai SDK out of import path until first use.
    import httpx
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        max_retries=0,
        timeout=httpx.Timeout(timeout_sec, connect=15.0),
    )

    async def _judge(prompt: str) -> str:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是严格的中文小说编辑, 只输出 JSON, 不解释.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        content = (choice.message.content or "").strip()
        if not content:
            # reasoning model fallback
            content = (
                getattr(choice.message, "reasoning_content", "") or ""
            ).strip()
        return content

    return _judge, model


__all__ = [
    "JudgeFn",
    "JudgeMeta",
    "PairwiseResult",
    "RubricResult",
    "pairwise_judge",
    "rubric_judge",
    "make_mimo_judge_fn",
]
