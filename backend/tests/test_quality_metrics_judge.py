"""Tests for quality_metrics.judge (Phase 2 Stage 0 — iter#79).

锁定 position-bias 处理 + 解析容错 + 元数据写入. judge LLM 调用本身用
mock fixture 替换, 不动真实网络.
"""

from __future__ import annotations

import json
import random

import pytest

from quality_metrics.judge import (
    PAIRWISE_VERSION,
    RUBRIC_VERSION,
    PairwiseResult,
    RubricResult,
    pairwise_judge,
    rubric_judge,
)


# ---------------------------------------------------------------------------
# pairwise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pairwise_no_swap_a_wins_maps_to_x() -> None:
    """rng=0.99 → swap=False → A 位是 X. judge 说 A 赢 → caller 看到 x 赢."""

    async def fn(prompt: str) -> str:
        return json.dumps({"winner": "A", "reason": "A 更紧凑"})

    rng = random.Random()
    rng.random = lambda: 0.99  # > 0.5 → no swap
    res = await pairwise_judge(
        "X text", "Y text", judge_fn=fn, model_name="mimo-test", rng=rng
    )
    assert res.winner == "x"
    assert res.meta.swap_applied is False
    assert res.meta.model == "mimo-test"
    assert res.meta.prompt_version == PAIRWISE_VERSION


@pytest.mark.asyncio
async def test_pairwise_swap_a_wins_maps_to_y() -> None:
    """rng=0.1 → swap=True → A 位是 Y. judge 说 A 赢 → caller 看到 y 赢."""

    async def fn(prompt: str) -> str:
        return json.dumps({"winner": "A", "reason": "A 更紧凑"})

    rng = random.Random()
    rng.random = lambda: 0.1  # < 0.5 → swap
    res = await pairwise_judge(
        "X text", "Y text", judge_fn=fn, model_name="m", rng=rng
    )
    assert res.winner == "y"
    assert res.meta.swap_applied is True


@pytest.mark.asyncio
async def test_pairwise_b_wins_inverse_mapping() -> None:
    async def fn(prompt: str) -> str:
        return json.dumps({"winner": "B", "reason": "B 紧凑"})

    rng = random.Random()
    rng.random = lambda: 0.9  # no swap → B 位 = Y
    res = await pairwise_judge(
        "x", "y", judge_fn=fn, model_name="m", rng=rng
    )
    assert res.winner == "y"

    rng.random = lambda: 0.1  # swap → B 位 = X
    res2 = await pairwise_judge("x", "y", judge_fn=fn, model_name="m", rng=rng)
    assert res2.winner == "x"


@pytest.mark.asyncio
async def test_pairwise_tie() -> None:
    async def fn(p):
        return json.dumps({"winner": "tie", "reason": "差不多"})

    res = await pairwise_judge("a", "b", judge_fn=fn, model_name="m")
    assert res.winner == "tie"


@pytest.mark.asyncio
async def test_pairwise_handles_markdown_fence() -> None:
    """LLM 偶发把 JSON 包在 ```json ... ``` 里."""

    async def fn(p):
        return '```json\n{"winner": "A", "reason": "X 简洁"}\n```'

    rng = random.Random()
    rng.random = lambda: 0.99
    res = await pairwise_judge("x", "y", judge_fn=fn, model_name="m", rng=rng)
    assert res.winner == "x"


@pytest.mark.asyncio
async def test_pairwise_parse_error_on_garbage() -> None:
    async def fn(p):
        return "Let me analyze this..."

    res = await pairwise_judge("x", "y", judge_fn=fn, model_name="m")
    assert res.winner == "parse_error"
    assert "json_parse_failed" in res.reason


@pytest.mark.asyncio
async def test_pairwise_parse_error_on_unknown_label() -> None:
    async def fn(p):
        return json.dumps({"winner": "C", "reason": "?"})

    res = await pairwise_judge("x", "y", judge_fn=fn, model_name="m")
    assert res.winner == "parse_error"
    assert "unrecognized_winner_label" in res.reason


@pytest.mark.asyncio
async def test_pairwise_call_failure_captured() -> None:
    async def fn(p):
        raise RuntimeError("boom")

    res = await pairwise_judge("x", "y", judge_fn=fn, model_name="m")
    assert res.winner == "parse_error"
    assert "judge_call_failed" in res.reason


# ---------------------------------------------------------------------------
# rubric
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rubric_normal_scoring() -> None:
    async def fn(p):
        return json.dumps(
            {
                "coherence": 4,
                "character_voice": 3,
                "plot_progression": 5,
                "reason": "推进强",
            }
        )

    res = await rubric_judge("文本", judge_fn=fn, model_name="m")
    assert res.coherence == 4
    assert res.character_voice == 3
    assert res.plot_progression == 5
    assert res.total == 12
    assert res.mean == 4.0
    assert res.meta.prompt_version == RUBRIC_VERSION


@pytest.mark.asyncio
async def test_rubric_clamps_invalid_to_zero() -> None:
    """LLM 偶发越界 / 非整数 → 0 哨兵."""

    async def fn(p):
        return json.dumps(
            {
                "coherence": 6,  # > 5
                "character_voice": "not a number",
                "plot_progression": -1,  # < 1
                "reason": "?",
            }
        )

    res = await rubric_judge("t", judge_fn=fn, model_name="m")
    assert res.coherence == 0
    assert res.character_voice == 0
    assert res.plot_progression == 0


@pytest.mark.asyncio
async def test_rubric_parse_error() -> None:
    async def fn(p):
        return "not json"

    res = await rubric_judge("t", judge_fn=fn, model_name="m")
    assert res.coherence == 0
    assert "json_parse_failed" in res.reason


@pytest.mark.asyncio
async def test_rubric_to_dict_schema() -> None:
    async def fn(p):
        return json.dumps(
            {"coherence": 3, "character_voice": 4, "plot_progression": 3, "reason": ""}
        )

    res = await rubric_judge("t", judge_fn=fn, model_name="mimo-pro")
    d = res.to_dict()
    assert d["coherence"] == 3
    assert d["total"] == 10
    assert d["mean"] == pytest.approx(10 / 3, abs=1e-4)
    assert d["meta"]["model"] == "mimo-pro"
    assert d["meta"]["prompt_version"] == RUBRIC_VERSION


# ---------------------------------------------------------------------------
# make_mimo_judge_fn smoke (no real network)
# ---------------------------------------------------------------------------


def test_make_mimo_judge_fn_raises_without_key(monkeypatch) -> None:
    from quality_metrics.judge import make_mimo_judge_fn

    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MIMO_API_KEY"):
        make_mimo_judge_fn()


def test_make_mimo_judge_fn_returns_callable_with_key(monkeypatch) -> None:
    from quality_metrics.judge import make_mimo_judge_fn

    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    monkeypatch.setenv("MIMO_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MIMO_MODEL", "mimo-test")
    fn, model = make_mimo_judge_fn()
    assert callable(fn)
    assert model == "mimo-test"
