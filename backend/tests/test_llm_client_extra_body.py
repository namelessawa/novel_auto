"""Phase 5-A helpers: env-driven extra_body + cached_tokens extraction.

These are tiny pure functions but they're on the hot path for every LLM call,
so pin their behavior:

* ``_resolve_extra_body()`` reads ``LLM_THINKING_MODE`` env. The contract is:
  - "disabled" → return ARK-shaped thinking-disable dict
  - anything else (unset / empty / "auto" / "on") → return None (no extra_body)
* ``_extract_cached_tokens()`` pulls ``usage.prompt_tokens_details.cached_tokens``
  defensively. Provider may return any of: missing attr, None, int, str-int.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nf_core.llm_client import _extract_cached_tokens, _resolve_extra_body


def test_resolve_extra_body_disabled(monkeypatch) -> None:
    monkeypatch.setenv("LLM_THINKING_MODE", "disabled")
    assert _resolve_extra_body() == {"thinking": {"type": "disabled"}}


def test_resolve_extra_body_disabled_case_insensitive(monkeypatch) -> None:
    monkeypatch.setenv("LLM_THINKING_MODE", "  DISABLED  ")
    assert _resolve_extra_body() == {"thinking": {"type": "disabled"}}


def test_resolve_extra_body_unset(monkeypatch) -> None:
    monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
    assert _resolve_extra_body() is None


def test_resolve_extra_body_other_values_yield_none(monkeypatch) -> None:
    for v in ("", "auto", "on", "enabled", "true", "1"):
        monkeypatch.setenv("LLM_THINKING_MODE", v)
        assert _resolve_extra_body() is None, f"value={v!r} should not enable extra_body"


def test_extract_cached_tokens_present() -> None:
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=500,
        prompt_tokens_details=SimpleNamespace(cached_tokens=750),
    )
    assert _extract_cached_tokens(usage) == 750


def test_extract_cached_tokens_missing_details() -> None:
    """mimo / old deepseek-chat 不暴露 prompt_tokens_details 字段."""
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=500)
    assert _extract_cached_tokens(usage) == 0


def test_extract_cached_tokens_details_none() -> None:
    """details 字段存在但为 None (provider 返回 0 hit 的某些写法)."""
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=500,
        prompt_tokens_details=None,
    )
    assert _extract_cached_tokens(usage) == 0


def test_extract_cached_tokens_cached_none() -> None:
    """details 在但 cached_tokens=None — 视作 0 hit."""
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=500,
        prompt_tokens_details=SimpleNamespace(cached_tokens=None),
    )
    assert _extract_cached_tokens(usage) == 0


def test_extract_cached_tokens_string_int_coerced() -> None:
    """某些 provider 返回 str — 我们 int() 转, 失败时 0."""
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=500,
        prompt_tokens_details=SimpleNamespace(cached_tokens="512"),
    )
    assert _extract_cached_tokens(usage) == 512


def test_extract_cached_tokens_bad_string_safe() -> None:
    """坏值不能 crash — 返回 0."""
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=500,
        prompt_tokens_details=SimpleNamespace(cached_tokens="not-a-number"),
    )
    assert _extract_cached_tokens(usage) == 0


def test_extract_cached_tokens_usage_none() -> None:
    """调用方在 usage=None 时也不能崩."""
    assert _extract_cached_tokens(None) == 0
