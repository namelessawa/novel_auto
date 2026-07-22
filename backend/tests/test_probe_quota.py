"""Phase 6 iter#PPP — probe_quota.py exit code logic tests.

scripts/probe_quota.py 是 standalone smoke (iter#HHH). 测试锁定 3 个分流路径:

* OK → exit 0
* quota error 字眼 → exit 1
* 其他 exception → exit 2
* empty content → exit 2

Mock llm_client.chat.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backend"))

import asyncio  # noqa: E402

import pytest  # noqa: E402

import probe_quota  # noqa: E402


def _run_probe_with_mock(mock_chat) -> int:
    """Patch llm_client.chat with the given AsyncMock and run _probe()."""
    with patch("nf_core.llm_client.llm_client.chat", mock_chat):
        return asyncio.run(probe_quota._probe())


# ---------------------------------------------------------------------------
# Healthy path
# ---------------------------------------------------------------------------


def test_healthy_returns_0(capsys) -> None:
    mock_resp = MagicMock()
    mock_resp.content = "我在."
    mock_resp.usage = {"total_tokens": 50}
    mock_chat = AsyncMock(return_value=mock_resp)
    rc = _run_probe_with_mock(mock_chat)
    assert rc == 0
    out = capsys.readouterr().out
    assert "[OK]" in out
    assert "我在" in out


def test_empty_content_returns_2(capsys) -> None:
    """LLM 返回但 content 空 → 视作错误 (exit 2)."""
    mock_resp = MagicMock()
    mock_resp.content = ""
    mock_resp.usage = {}
    mock_chat = AsyncMock(return_value=mock_resp)
    rc = _run_probe_with_mock(mock_chat)
    assert rc == 2
    assert "[ERR]" in capsys.readouterr().out


def test_whitespace_only_content_returns_2(capsys) -> None:
    """content 全空白 → 视作空 (exit 2)."""
    mock_resp = MagicMock()
    mock_resp.content = "   \n  "
    mock_resp.usage = {}
    mock_chat = AsyncMock(return_value=mock_resp)
    rc = _run_probe_with_mock(mock_chat)
    assert rc == 2


# ---------------------------------------------------------------------------
# Quota errors → exit 1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg",
    [
        "Error code: 429 - {'error': {'code': 'AccountQuotaExceeded', 'message': '...'}}",
        "Error code: 429 - {'error': {'code': 'AccountRateLimitExceeded'}}",
        "Error code: 429 - {'error': {'code': 'RateLimitExceeded'}}",
        "{'code': 'ServerOverloaded'}",
        "429 Too Many Requests",
        "tooManyRequests",
    ],
)
def test_quota_errors_return_1(msg, capsys) -> None:
    mock_chat = AsyncMock(side_effect=RuntimeError(msg))
    rc = _run_probe_with_mock(mock_chat)
    assert rc == 1, f"expected quota exit (1) for: {msg}"
    out = capsys.readouterr().out
    assert "[QUOTA]" in out


# ---------------------------------------------------------------------------
# Other errors → exit 2
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg",
    [
        "Connection refused",
        "DNS lookup failed",
        "ProviderConfigError: ARK_BASE_URL not set",
        "Timeout after 600s",
        "JSONDecodeError",
    ],
)
def test_other_errors_return_2(msg, capsys) -> None:
    mock_chat = AsyncMock(side_effect=RuntimeError(msg))
    rc = _run_probe_with_mock(mock_chat)
    assert rc == 2, f"expected error exit (2) for: {msg}"
    out = capsys.readouterr().out
    assert "[ERR]" in out


def test_quota_match_case_insensitive(capsys) -> None:
    """quota 字眼大小写不区分."""
    mock_chat = AsyncMock(side_effect=RuntimeError("ACCOUNTQUOTAEXCEEDED"))
    rc = _run_probe_with_mock(mock_chat)
    assert rc == 1


# ---------------------------------------------------------------------------
# main() dispatcher
# ---------------------------------------------------------------------------


def test_main_no_args_uses_default_provider(monkeypatch, capsys) -> None:
    """main() 不带 --provider 仍跑."""
    mock_resp = MagicMock()
    mock_resp.content = "ok"
    mock_resp.usage = {"total_tokens": 30}
    monkeypatch.setattr(sys, "argv", ["probe_quota"])
    with patch("nf_core.llm_client.llm_client.chat", AsyncMock(return_value=mock_resp)):
        rc = probe_quota.main()
    assert rc == 0
