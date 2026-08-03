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


def _run_in_isolated_loop(awaitable):
    """Run a CLI coroutine without replacing pytest-asyncio's policy loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(awaitable)
    finally:
        loop.close()


def _run_probe_with_mock(mock_chat) -> int:
    """Patch llm_client.chat with the given AsyncMock and run _probe()."""
    with patch("nf_core.llm_client.llm_client.chat", mock_chat):
        return _run_in_isolated_loop(probe_quota._probe())


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
    assert "我在" not in out


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


def test_main_uses_read_only_provider_file(
    tmp_path, monkeypatch, capsys
) -> None:
    """main() applies its provider file before the lightweight client is used."""
    mock_resp = MagicMock()
    mock_resp.content = "ok"
    mock_resp.usage = {"total_tokens": 30}
    provider_file = tmp_path / "coding.txt"
    provider_file.write_text(
        "KEY=test-only\n"
        "URL=https://provider.invalid/v1\n"
        "MODEL=glm-5.2\n",
        encoding="utf-8",
    )
    original = provider_file.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        ["probe_quota", "--provider-file", str(provider_file)],
    )
    with (
        patch("nf_core.llm_client.llm_client.chat", AsyncMock(return_value=mock_resp)),
        patch("probe_quota.asyncio.run", side_effect=_run_in_isolated_loop),
    ):
        rc = probe_quota.main()
    assert rc == 0
    assert provider_file.read_bytes() == original
    output = capsys.readouterr().out
    assert '"provider": "custom"' in output
    assert '"model": "glm-5.2"' in output
    assert '"credential_present": true' in output
    assert "test-only" not in output
    assert "provider.invalid" not in output


def test_main_checks_runtime_contract_before_call(
    tmp_path, monkeypatch, capsys
) -> None:
    provider_file = tmp_path / "coding.txt"
    provider_file.write_text(
        "KEY=test-only\n"
        "URL=https://provider.invalid/v1\n"
        "MODEL=wrong-model\n"
        "THINKING_MODE=disabled\n"
        "MAX_RETRIES=0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe_quota",
            "--provider-file",
            str(provider_file),
            "--provider",
            "custom",
            "--expect-model",
            "glm-5.2",
            "--expect-thinking-mode",
            "disabled",
            "--expect-max-retries",
            "0",
        ],
    )
    chat = AsyncMock()

    with patch("nf_core.llm_client.llm_client.chat", chat):
        rc = probe_quota.main()

    assert rc == 2
    chat.assert_not_awaited()
    assert "provider configuration unavailable" in capsys.readouterr().out


def test_main_fails_closed_when_provider_file_is_missing(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe_quota",
            "--provider-file",
            str(tmp_path / "missing-provider.txt"),
        ],
    )

    rc = probe_quota.main()

    assert rc == 2
    assert "provider configuration unavailable" in capsys.readouterr().out
