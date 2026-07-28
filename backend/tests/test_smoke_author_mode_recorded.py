"""Regression coverage for the provider-free author-mode acceptance smoke."""

from __future__ import annotations

import pytest

from scripts.smoke_author_mode_recorded import run_recorded


@pytest.mark.asyncio
async def test_recorded_author_smoke_completes_without_provider(tmp_path) -> None:
    result = await run_recorded(tmp_path / "recorded-author")

    assert result["ok"] is True
    assert result["provider_calls"] == 0
    assert result["provider_tokens"] == 0
    assert all(
        value is True
        for key, value in result["steps"].items()
        if key != "4_story_bible_revision_modified"
    )
