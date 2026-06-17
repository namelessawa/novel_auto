"""Phase 5-D follow-up tests — recommended_pairs lazy loader + API payload.

Why these tests:
* The JSON file might be missing in a fresh checkout; loader must fail soft
* Top-N + avoid_pairs + style_universal_avg are user-facing — schema lock
* API payload trims dimension fields; verify the slim wire format

Don't test against the actual checked-in JSON content (208 bench-derived
numbers). Use a tmp file injected via _DATA_PATH monkeypatch.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from novel_presets import recommended_pairs as rp


_FAKE_PAYLOAD = {
    "version": 1,
    "total_cells": 208,
    "scored_cells": 4,
    "by_theme": {
        "fake_theme_a": [
            {
                "style": "style_top",
                "mean": 5.0,
                "coh": 5,
                "voice": 5,
                "plot": 5,
                "rank": 1,
                "is_top": True,
            },
            {
                "style": "style_mid",
                "mean": 4.33,
                "coh": 5,
                "voice": 4,
                "plot": 4,
                "rank": 2,
                "is_top": True,
            },
            {
                "style": "style_low",
                "mean": 3.0,
                "coh": 4,
                "voice": 2,
                "plot": 3,
                "rank": 3,
                "is_top": True,
            },
        ],
        "fake_theme_b": [
            {
                "style": "style_top",
                "mean": 4.67,
                "coh": 5,
                "voice": 4,
                "plot": 5,
                "rank": 1,
                "is_top": True,
            },
        ],
    },
    "perfect_pairs": [{"theme": "fake_theme_a", "style": "style_top", "mean": 5.0}],
    "avoid_pairs": [
        {
            "theme": "fake_theme_a",
            "style": "style_low",
            "mean": 3.0,
            "low_dimensions": ["voice", "plot"],
        }
    ],
    "style_universal_avg": {"style_top": 4.83, "style_mid": 4.33, "style_low": 3.0},
}


@pytest.fixture
def fake_data(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Inject a tmp JSON path and clear the lru_cache so each test sees fresh data."""
    p = tmp_path / "recommended_pairs.json"
    p.write_text(json.dumps(_FAKE_PAYLOAD, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(rp, "_DATA_PATH", p)
    rp._load_data.cache_clear()
    yield p
    rp._load_data.cache_clear()


def test_missing_file_returns_unavailable(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(rp, "_DATA_PATH", tmp_path / "does_not_exist.json")
    rp._load_data.cache_clear()
    try:
        assert rp.is_available() is False
        assert rp.top_styles_for_theme("anything") == []
        assert rp.perfect_pairs() == []
        assert rp.avoid_pairs() == []
        assert rp.style_universal_avg() == {}
        payload = rp.to_api_payload()
        assert payload == {"available": False, "version": 0}
    finally:
        rp._load_data.cache_clear()


def test_corrupted_json_returns_unavailable(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    p = tmp_path / "corrupted.json"
    p.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(rp, "_DATA_PATH", p)
    rp._load_data.cache_clear()
    try:
        assert rp.is_available() is False
        assert rp.to_api_payload()["available"] is False
    finally:
        rp._load_data.cache_clear()


def test_is_available_when_data_present(fake_data):
    assert rp.is_available() is True


def test_top_styles_for_theme_respects_n(fake_data):
    top1 = rp.top_styles_for_theme("fake_theme_a", n=1)
    top2 = rp.top_styles_for_theme("fake_theme_a", n=2)
    top10 = rp.top_styles_for_theme("fake_theme_a", n=10)
    assert len(top1) == 1
    assert len(top2) == 2
    # only 3 in fixture, so n=10 clamps to available
    assert len(top10) == 3
    assert top1[0]["style"] == "style_top"
    assert top1[0]["rank"] == 1
    assert top1[0]["is_top"] is True


def test_top_styles_returns_empty_for_unknown_theme(fake_data):
    assert rp.top_styles_for_theme("nonexistent_theme") == []


def test_top_styles_for_theme_n_clamped_to_minimum_one(fake_data):
    # n=0 or negative should clamp to 1
    out = rp.top_styles_for_theme("fake_theme_a", n=0)
    assert len(out) == 1


def test_perfect_pairs_returned(fake_data):
    pairs = rp.perfect_pairs()
    assert len(pairs) == 1
    assert pairs[0]["theme"] == "fake_theme_a"
    assert pairs[0]["mean"] == 5.0


def test_avoid_pairs_returned_with_low_dimensions(fake_data):
    avoid = rp.avoid_pairs()
    assert len(avoid) == 1
    assert avoid[0]["theme"] == "fake_theme_a"
    assert avoid[0]["low_dimensions"] == ["voice", "plot"]


def test_style_universal_avg_floats(fake_data):
    avg = rp.style_universal_avg()
    assert avg["style_top"] == 4.83
    assert isinstance(avg["style_top"], float)


def test_api_payload_trims_dimension_fields(fake_data):
    payload = rp.to_api_payload()
    assert payload["available"] is True
    assert payload["version"] == 1
    # by_theme entries should only have style/mean/rank/is_top — NOT coh/voice/plot
    row = payload["by_theme"]["fake_theme_a"][0]
    assert set(row.keys()) == {"style", "mean", "rank", "is_top"}
    assert row["style"] == "style_top"
    assert row["mean"] == 5.0


def test_api_payload_preserves_avoid_dimensions(fake_data):
    payload = rp.to_api_payload()
    assert payload["avoid_pairs"][0]["low_dimensions"] == ["voice", "plot"]


def test_top_styles_returns_copy_not_reference(fake_data):
    """Caller mutation must not corrupt cached data."""
    out = rp.top_styles_for_theme("fake_theme_a", n=1)
    out[0]["mean"] = 0.0
    # Re-fetch from cache — must still see original 5.0
    again = rp.top_styles_for_theme("fake_theme_a", n=1)
    assert again[0]["mean"] == 5.0
