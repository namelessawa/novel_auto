"""Tests for pipeline LLM role retry mechanisms.

Covers: writer retry on empty output, retry helper validation,
and successful recovery after initial failures.
"""

from __future__ import annotations

import pytest

from story.stateful_pipeline import llm_roles
from story.stateful_pipeline.llm_roles import (
    MIN_VALID_PROSE_CHARS,
    PipelineLLMError,
    _extract_prose,
    _retry_llm_call,
    write_chapter_simplified,
)


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    """Fake llm_client that returns queued responses."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._index = 0
        self.call_count = 0

    async def chat(self, **kwargs):
        self.call_count += 1
        if self._index >= len(self._responses):
            return FakeResponse("")
        content = self._responses[self._index]
        self._index += 1
        return FakeResponse(content)


# ---------------------------------------------------------------------------
# _extract_prose Tests
# ---------------------------------------------------------------------------


class TestExtractProse:
    def test_extract_with_tags(self):
        content = "<prose>\n这是正文。\n</prose>"
        assert _extract_prose(content) == "这是正文。"

    def test_extract_without_tags(self):
        content = "这是没有标签的正文。"
        assert _extract_prose(content) == "这是没有标签的正文。"

    def test_extract_empty_tags(self):
        content = "<prose></prose>"
        assert _extract_prose(content) == ""

    def test_extract_only_opening_tag(self):
        content = "<prose>只有开头"
        assert _extract_prose(content) == "<prose>只有开头"


# ---------------------------------------------------------------------------
# Writer Retry Tests
# ---------------------------------------------------------------------------


class TestWriterRetry:
    @pytest.mark.asyncio
    async def test_success_first_attempt(self, monkeypatch):
        fake = FakeLLM(["<prose>" + "内容" * 100 + "</prose>"])
        monkeypatch.setattr(llm_roles, "llm_client", fake)

        result = await write_chapter_simplified(
            novel_id="n1",
            chapter_number=1,
            synopsis="梗概",
            style_prefix="",
            pacing_mode="flat",
            transfer_context="",
        )
        assert len(result) >= MIN_VALID_PROSE_CHARS
        assert fake.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_empty_then_success(self, monkeypatch):
        fake = FakeLLM([
            "",
            "<prose>" + "内容" * 100 + "</prose>",
        ])
        monkeypatch.setattr(llm_roles, "llm_client", fake)

        result = await write_chapter_simplified(
            novel_id="n1",
            chapter_number=1,
            synopsis="梗概",
            style_prefix="",
            pacing_mode="flat",
            transfer_context="",
        )
        assert len(result) >= MIN_VALID_PROSE_CHARS
        assert fake.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_too_short_then_success(self, monkeypatch):
        fake = FakeLLM([
            "<prose>太短</prose>",
            "<prose>x</prose>",
            "<prose>" + "内容" * 100 + "</prose>",
        ])
        monkeypatch.setattr(llm_roles, "llm_client", fake)

        result = await write_chapter_simplified(
            novel_id="n1",
            chapter_number=1,
            synopsis="梗概",
            style_prefix="",
            pacing_mode="flat",
            transfer_context="",
        )
        assert len(result) >= MIN_VALID_PROSE_CHARS
        assert fake.call_count == 3

    @pytest.mark.asyncio
    async def test_all_attempts_fail_raises(self, monkeypatch):
        fake = FakeLLM(["", "", ""])
        monkeypatch.setattr(llm_roles, "llm_client", fake)

        with pytest.raises(PipelineLLMError):
            await write_chapter_simplified(
                novel_id="n1",
                chapter_number=1,
                synopsis="梗概",
                style_prefix="",
                pacing_mode="flat",
                transfer_context="",
                max_attempts=3,
            )
        assert fake.call_count == 3

    @pytest.mark.asyncio
    async def test_custom_max_attempts(self, monkeypatch):
        fake = FakeLLM(["", "", "", "", ""])
        monkeypatch.setattr(llm_roles, "llm_client", fake)

        with pytest.raises(PipelineLLMError):
            await write_chapter_simplified(
                novel_id="n1",
                chapter_number=1,
                synopsis="梗概",
                style_prefix="",
                pacing_mode="flat",
                transfer_context="",
                max_attempts=2,
            )
        assert fake.call_count == 2


# ---------------------------------------------------------------------------
# _retry_llm_call Tests
# ---------------------------------------------------------------------------


class TestRetryLLMCall:
    @pytest.mark.asyncio
    async def test_no_validate_returns_content(self):
        async def call():
            return FakeResponse("some content")

        result = await _retry_llm_call(call, role_name="test")
        assert result == "some content"

    @pytest.mark.asyncio
    async def test_empty_content_retries(self):
        responses = iter(["", "", "valid"])
        call_count = 0

        async def call():
            nonlocal call_count
            call_count += 1
            return FakeResponse(next(responses))

        result = await _retry_llm_call(call, role_name="test")
        assert result == "valid"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_validate_success(self):
        async def call():
            return FakeResponse("42")

        result = await _retry_llm_call(
            call, validate=lambda c: int(c), role_name="test"
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_validate_failure_retries(self):
        responses = iter(["bad", "bad", "42"])
        call_count = 0

        async def call():
            nonlocal call_count
            call_count += 1
            return FakeResponse(next(responses))

        def validate(content):
            return int(content)

        result = await _retry_llm_call(call, validate=validate, role_name="test")
        assert result == 42
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_validate_returns_none_retries(self):
        responses = iter(["x", "y", "z"])
        call_count = 0

        async def call():
            nonlocal call_count
            call_count += 1
            return FakeResponse(next(responses))

        results = iter([None, None, "ok"])

        def validate(content):
            return next(results)

        result = await _retry_llm_call(call, validate=validate, role_name="test")
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_all_attempts_exhausted_raises(self):
        async def call():
            return FakeResponse("")

        with pytest.raises(PipelineLLMError):
            await _retry_llm_call(call, max_attempts=2, role_name="test")

    @pytest.mark.asyncio
    async def test_call_exception_retries(self):
        call_count = 0

        async def call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("network error")
            return FakeResponse("recovered")

        result = await _retry_llm_call(call, role_name="test")
        assert result == "recovered"
        assert call_count == 3
