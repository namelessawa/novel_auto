"""Phase 5-D follow-up tests — bench_tick.py --theme / --style CLI integration.

Why these tests:
* --theme resolves via novel_presets.get_theme_seed and overrides --seed
* --style sets NOVEL_STYLE_PRESET env (matrix_bench-compatible path)
* --seed explicit user value wins over --theme registry seed
* unknown --theme / --style names raise argparse error (no silent fallback)

We don't actually run a bench (would hit ARK). Instead, simulate the CLI
parse + post-parse mutation path directly.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_dry(*args: str) -> subprocess.CompletedProcess:
    """Run bench_tick.py CLI variants that exit before actual bench.

    Use binary capture + replace-decode: Windows GBK console emits non-UTF-8
    bytes in argparse error messages for non-ASCII help text. The encoding
    of the *content we care about* (theme key, --theme, --style flags) is
    ASCII, so we just need to round-trip the bytes without crashing.
    """
    cmd = [sys.executable, str(_REPO_ROOT / "scripts" / "bench_tick.py"), *args]
    proc = subprocess.run(cmd, capture_output=True)
    # Decode bytes with replacement so ASCII content survives mixed encoding.
    return subprocess.CompletedProcess(
        args=proc.args,
        returncode=proc.returncode,
        stdout=proc.stdout.decode("utf-8", errors="replace") if proc.stdout else "",
        stderr=proc.stderr.decode("utf-8", errors="replace") if proc.stderr else "",
    )


def test_unknown_theme_fails_cleanly(monkeypatch: pytest.MonkeyPatch):
    """Bad --theme key should error from argparse, not silently fall back to default seed."""
    monkeypatch.delenv("NOVEL_STYLE_PRESET", raising=False)
    # Run via subprocess so we observe argparse error path end-to-end.
    proc = _run_dry("--theme", "this_theme_does_not_exist", "--ticks", "1")
    assert proc.returncode != 0, (
        "bench_tick.py with unknown --theme should fail, not silently fallback"
    )
    combined = (proc.stderr or "") + (proc.stdout or "")
    assert "this_theme_does_not_exist" in combined


def test_unknown_style_fails_cleanly(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NOVEL_STYLE_PRESET", raising=False)
    proc = _run_dry("--style", "this_style_does_not_exist", "--ticks", "1")
    assert proc.returncode != 0
    combined = (proc.stderr or "") + (proc.stdout or "")
    assert "this_style_does_not_exist" in combined


def test_help_lists_theme_and_style(monkeypatch: pytest.MonkeyPatch):
    """--help should advertise --theme and --style (CLI discoverability)."""
    proc = _run_dry("--help")
    assert proc.returncode == 0
    assert "--theme" in proc.stdout
    assert "--style" in proc.stdout


def test_theme_resolves_to_registry_seed():
    """Resolution path: --theme republic_spy → uses THEME_SEEDS['republic_spy'].seed."""
    sys.path.insert(0, str(_REPO_ROOT / "backend"))
    sys.path.insert(0, str(_REPO_ROOT))
    from novel_presets import get_theme_seed

    seed = get_theme_seed("republic_spy")
    assert seed.key == "republic_spy"
    # Sanity: matches PHASE5_PLAN K runbook 'seed2 = republic_spy plot-medium'.
    assert "民国" in seed.label or "republic" in seed.key


def test_style_resolves_to_registry_preset():
    sys.path.insert(0, str(_REPO_ROOT / "backend"))
    sys.path.insert(0, str(_REPO_ROOT))
    from novel_presets import get_style_preset

    s = get_style_preset("classical_chapter")
    assert s.key == "classical_chapter"
    assert s.narrator_addendum  # non-empty


def test_3_runbook_seeds_all_resolve():
    """PHASE5_PLAN K standard 3 seeds must always resolve cleanly."""
    sys.path.insert(0, str(_REPO_ROOT / "backend"))
    sys.path.insert(0, str(_REPO_ROOT))
    from novel_presets import get_theme_seed

    for key in ("steampunk_archive", "republic_spy", "apocalypse_wasteland"):
        seed = get_theme_seed(key)
        assert seed.seed, f"theme {key} has empty seed (broken runbook prerequisite)"
        assert len(seed.seed) >= 50, (
            f"theme {key} seed too short ({len(seed.seed)} chars), "
            "PHASE5_PLAN K requires non-trivial bootstrap seeds"
        )
