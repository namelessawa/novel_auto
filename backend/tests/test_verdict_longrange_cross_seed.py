"""Phase 5-D follow-up #3 — verdict_longrange_cross_seed.py aggregator tests.

Why these tests:
* Drift verdict logic encodes PASS/WARN/FAIL thresholds — schema lock
* Aggregator must read seed1 (real production bench) without crashing
* Empty / partial / corrupted bench JSON → ERROR row (not exception)
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _run(*args: str) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "verdict_longrange_cross_seed.py"),
        *args,
    ]
    proc = subprocess.run(cmd, capture_output=True)
    return subprocess.CompletedProcess(
        args=proc.args,
        returncode=proc.returncode,
        stdout=(proc.stdout or b"").decode("utf-8", errors="replace"),
        stderr=(proc.stderr or b"").decode("utf-8", errors="replace"),
    )


def _write_fake_bench(
    p: pathlib.Path,
    *,
    label: str = "fake",
    ticks: int = 100,
    completed: int = 100,
    narratives: list | None = None,
    open_loop_snapshots: list | None = None,
    by_agent: dict | None = None,
    tick_durations: list | None = None,
    total_tokens: int = 500_000,
) -> None:
    payload = {
        "label": label,
        "ticks": ticks,
        "completed_ticks": completed,
        "total_tokens": total_tokens,
        "narratives": narratives or [],
        "open_loop_snapshots": open_loop_snapshots or [],
        "by_agent_cumulative": by_agent or {},
        "tick_durations_sec": tick_durations or [60.0] * completed,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_seed1_production_bench_pass(tmp_path: pathlib.Path):
    """Production bench (commit 82820a5) must still verdict PASS."""
    seed1_path = _REPO_ROOT / "docs" / "iter" / "bench-phase5j-longrange-200tick.json"
    if not seed1_path.is_file():
        pytest.skip("seed1 production bench not available")
    out = tmp_path / "verdict.md"
    proc = _run("--bench", f"seed1={seed1_path}", "--output", str(out))
    assert proc.returncode == 0, proc.stderr
    text = out.read_text(encoding="utf-8")
    assert "GATE PASS" in text
    assert "200/200" in text


def test_incomplete_bench_marked(tmp_path: pathlib.Path):
    """Partial bench (e.g. killed mid-run) should be marked INCOMPLETE."""
    fake = tmp_path / "fake.json"
    _write_fake_bench(fake, completed=50, ticks=100)
    out = tmp_path / "verdict.md"
    proc = _run("--bench", f"seedX={fake}", "--output", str(out))
    assert proc.returncode == 0
    text = out.read_text(encoding="utf-8")
    assert "INCOMPLETE" in text
    assert "50/100" in text


def test_narrator_silence_second_half_warns(tmp_path: pathlib.Path):
    """If second half has narration_chars < first half × 0.7 → WARN."""
    fake = tmp_path / "drift.json"
    # First 50 ticks: lots of chars. Last 50: very little.
    narratives = []
    for tick in range(1, 51):
        narratives.append({"tick": tick, "text": "正文" * 100})  # 200 chars each
    for tick in range(51, 101):
        narratives.append({"tick": tick, "text": "短"})  # 1 char
    _write_fake_bench(fake, completed=100, ticks=100, narratives=narratives)
    out = tmp_path / "verdict.md"
    proc = _run("--bench", f"drifty={fake}", "--output", str(out))
    assert proc.returncode == 0
    text = out.read_text(encoding="utf-8")
    assert "WARN" in text
    assert "narrator output" in text


def test_open_loop_collapse_warns(tmp_path: pathlib.Path):
    """If open_loops drops by 3+ AND closures don't account for it → WARN.

    Updated 2026-06-18 after Phase 6-A.2 500-tick: 'open_loops down + closed up' is
    healthy resolution, not drift. The signal is *unexplained* loop loss.
    """
    fake = tmp_path / "collapse.json"
    snaps = [
        {"tick": 5, "open": 8, "stale": 0, "closed": 0},
        {"tick": 50, "open": 7, "stale": 1, "closed": 0},
        {"tick": 100, "open": 2, "stale": 0, "closed": 1},  # -6 vs initial, only 1 closed
    ]
    narratives = [
        {"tick": t, "text": "正文" * 100} for t in range(1, 101)
    ]
    _write_fake_bench(
        fake,
        completed=100,
        ticks=100,
        narratives=narratives,
        open_loop_snapshots=snaps,
    )
    out = tmp_path / "verdict.md"
    proc = _run("--bench", f"collapser={fake}", "--output", str(out))
    assert proc.returncode == 0
    text = out.read_text(encoding="utf-8")
    assert "WARN" in text
    assert "open_loops" in text


def test_open_loop_drop_with_closures_passes(tmp_path: pathlib.Path):
    """500-tick reality: open 5→1 with 8 closures = healthy resolution, PASS.

    Added 2026-06-18 after observing Phase 6-A.2: long-running novels NATURALLY
    close foreshadowing — that should never read as drift.
    """
    fake = tmp_path / "healthy_closure.json"
    snaps = [
        {"tick": 5, "open": 5, "stale": 0, "closed": 0},
        {"tick": 250, "open": 3, "stale": 0, "closed": 4},
        {"tick": 500, "open": 1, "stale": 0, "closed": 8},  # 5→1 but 8 closed during
    ]
    narratives = [
        {"tick": t, "text": "正文" * 100} for t in range(1, 501)
    ]
    _write_fake_bench(
        fake,
        completed=500,
        ticks=500,
        narratives=narratives,
        open_loop_snapshots=snaps,
    )
    out = tmp_path / "verdict.md"
    proc = _run("--bench", f"healthy={fake}", "--output", str(out))
    assert proc.returncode == 0
    text = out.read_text(encoding="utf-8")
    assert "PASS" in text
    assert "GATE PASS" in text
    assert "WARN" not in text or "WARN —" not in text


def test_corrupted_bench_marked_error_no_crash(tmp_path: pathlib.Path):
    """Corrupted JSON should produce an ERROR row, not crash the aggregator."""
    bad = tmp_path / "bad.json"
    bad.write_text("{this is not valid", encoding="utf-8")
    good = tmp_path / "good.json"
    _write_fake_bench(good, completed=100, ticks=100)
    out = tmp_path / "verdict.md"
    proc = _run(
        "--bench",
        f"bad={bad}",
        "--bench",
        f"good={good}",
        "--output",
        str(out),
    )
    assert proc.returncode == 0, proc.stderr
    text = out.read_text(encoding="utf-8")
    assert "ERROR" in text  # bad row should be flagged
    # Good seed should still be processed
    assert "good" in text


def test_pass_seed_with_growing_narrative(tmp_path: pathlib.Path):
    """Healthy bench: second half has more chars → PASS."""
    fake = tmp_path / "ok.json"
    narratives = []
    for tick in range(1, 51):
        narratives.append({"tick": tick, "text": "正文" * 80})
    for tick in range(51, 101):
        narratives.append({"tick": tick, "text": "正文" * 110})  # 37% more
    snaps = [
        {"tick": 5, "open": 4, "stale": 0},
        {"tick": 100, "open": 3, "stale": 0},  # mild decrement, not collapse
    ]
    _write_fake_bench(
        fake,
        completed=100,
        ticks=100,
        narratives=narratives,
        open_loop_snapshots=snaps,
    )
    out = tmp_path / "verdict.md"
    proc = _run("--bench", f"healthy={fake}", "--output", str(out))
    assert proc.returncode == 0
    text = out.read_text(encoding="utf-8")
    assert "PASS" in text
    assert "GATE PASS" in text
