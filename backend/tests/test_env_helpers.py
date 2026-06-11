"""Tests for nf_core.env_helpers — env_bool / env_bool_tri.

v2.38 iter#68 — 锁定 robust env parsing 行为, 防止 4 个 agent (critic /
narrator / story-arc / arc-tracker / orchestrator) 单独抄一份后漂移.
"""

from __future__ import annotations

import pytest

from nf_core.env_helpers import env_bool, env_bool_tri


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0", False),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("no", False),
        ("No", False),
        ("off", False),
        ("1", True),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
    ],
)
def test_env_bool_recognized_values(raw, expected) -> None:
    assert env_bool("DUMMY", raw=raw, default=not expected) is expected


@pytest.mark.parametrize("raw", ["", "  ", "anything", "yesno", "?"])
def test_env_bool_unrecognized_returns_default(raw) -> None:
    assert env_bool("DUMMY", raw=raw, default=True) is True
    assert env_bool("DUMMY", raw=raw, default=False) is False


def test_env_bool_reads_actual_environ(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_X", "yes")
    assert env_bool("FEATURE_X", default=False) is True

    monkeypatch.setenv("FEATURE_X", "off")
    assert env_bool("FEATURE_X", default=True) is False

    monkeypatch.delenv("FEATURE_X", raising=False)
    assert env_bool("FEATURE_X", default=True) is True
    assert env_bool("FEATURE_X", default=False) is False


def test_env_bool_tri_three_states(monkeypatch) -> None:
    monkeypatch.setenv("X", "1")
    assert env_bool_tri("X") is True

    monkeypatch.setenv("X", "off")
    assert env_bool_tri("X") is False

    monkeypatch.setenv("X", "")
    assert env_bool_tri("X") is None

    monkeypatch.setenv("X", "unknown")
    assert env_bool_tri("X") is None

    monkeypatch.delenv("X", raising=False)
    assert env_bool_tri("X") is None
