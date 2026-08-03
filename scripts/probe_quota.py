"""Phase 6 iter#HHH — standalone LLM quota smoke.

替代 ``python scripts/bench_tick.py --ticks 1`` — 后者跑完整 orchestrator
7 阶段 (~3s, 4k tokens, 写盘等), 仅做 quota 健康检查浪费. 本 script 直接
调用 ``llm_client.chat`` 一次 (~200 tokens 输出, 1 LLM call), 快速判定.

Exit code:
* 0 — quota 健康, LLM 返回有效 content
* 1 — quota 触底 (429 AccountQuotaExceeded / RateLimitExceeded)
* 2 — 其他错误 (provider 配置错 / 网络 / timeout)

Usage:
    python scripts/probe_quota.py
    python scripts/probe_quota.py --provider deepseek  # 覆盖 LLM_PROVIDER

Output (stdout):
    [OK] quota healthy. content_len=X tokens=Y
or:
    [QUOTA] {error message}
or:
    [ERR] {exception}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

# 默认走 LLM_PROVIDER (本 repo 现 custom = deepseek).
async def _probe(*, provider_config=None, client_override=None) -> int:
    from nf_core.llm_client import llm_client  # noqa: E402

    try:
        resp = await llm_client.chat(
            system_prompt="You are a quota probe. Reply with one short Chinese sentence.",
            user_prompt="一句话证明你还活着.",
            temperature=0.3,
            max_tokens=80,
            agent_id="probe",
            priority="critical",
            tick=0,
            provider_config=provider_config,
            client_override=client_override,
        )
    except Exception as e:  # broad — CLI maps every provider failure to an exit code
        code = str(getattr(e, "code", "") or "")
        msg = str(e)
        # DeepSeek 429 出 AccountQuotaExceeded / RateLimitExceeded
        # ARK 同样 ServerOverloaded / RateLimit
        lower = msg.lower()
        if code == "PROVIDER_RATE_LIMITED" or any(
            s in lower
            for s in (
                "accountquotaexceeded",
                "ratelimitexceeded",
                "429",
                "too many requests",
                "toomanyrequests",  # DeepSeek/ARK type field (no spaces)
                "quotaexceeded",
                "serveroverloaded",
            )
        ):
            print("[QUOTA] provider rate limit or quota reached")
            return 1
        safe_code = code or "PROVIDER_PROBE_FAILED"
        print(f"[ERR] {safe_code}")
        return 2

    content = (resp.content or "").strip()
    prompt_tokens = getattr(resp, "usage_prompt_tokens", None)
    completion_tokens = getattr(resp, "usage_completion_tokens", None)
    if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
        tokens: int | str = prompt_tokens + completion_tokens
    else:
        usage = getattr(resp, "usage", {})
        tokens = usage.get("total_tokens", "?") if isinstance(usage, dict) else "?"
    if not content:
        print(f"[ERR] empty content from LLM. tokens={tokens}")
        return 2
    print(f"[OK] quota healthy. content_len={len(content)} tokens={tokens}")
    return 0


async def _run_configured_probe(config) -> int:
    """Use a one-shot client that never retains the probe credential."""
    from nf_core.provider_runtime import ephemeral_provider_client

    async with ephemeral_provider_client(config) as client:
        return await _probe(
            provider_config=config,
            client_override=client,
        )


def main() -> int:
    p = argparse.ArgumentParser(description="LLM quota smoke probe")
    p.add_argument(
        "--provider-file",
        type=Path,
        default=_REPO_ROOT / "coding.txt",
        help="read-only provider configuration file (default: repository coding.txt)",
    )
    p.add_argument(
        "--provider",
        default="",
        help="optional assertion; must match the provider declared by the file",
    )
    p.add_argument(
        "--expect-model",
        default="",
        help="optional exact model assertion evaluated before the Provider call",
    )
    p.add_argument(
        "--expect-thinking-mode",
        default="",
        help="optional exact thinking-mode assertion evaluated before the call",
    )
    p.add_argument(
        "--expect-max-retries",
        type=int,
        default=None,
        help="optional SDK retry assertion evaluated before the Provider call",
    )
    args = p.parse_args()
    from nf_core.provider_runtime import (
        ProviderConfigurationError,
        stage_provider_file_scope,
    )

    try:
        with stage_provider_file_scope(args.provider_file.resolve()) as config:
            if args.provider and args.provider.strip().lower() != config.provider:
                raise ProviderConfigurationError(
                    "provider assertion does not match provider file"
                )
            if args.expect_model and args.expect_model.strip() != config.model:
                raise ProviderConfigurationError(
                    "model assertion does not match provider file"
                )
            if (
                args.expect_thinking_mode
                and args.expect_thinking_mode.strip().lower()
                != config.thinking_mode
            ):
                raise ProviderConfigurationError(
                    "thinking-mode assertion does not match provider file"
                )
            if (
                args.expect_max_retries is not None
                and args.expect_max_retries != config.max_retries
            ):
                raise ProviderConfigurationError(
                    "SDK retry assertion does not match provider file"
                )
            diagnostics = config.diagnostics()
            print(
                "[RUNTIME] "
                + json.dumps(
                    {
                        key: diagnostics[key]
                        for key in (
                            "provider",
                            "model",
                            "source",
                            "thinking_mode",
                            "retries",
                            "credential_present",
                            "config_fingerprint",
                        )
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return asyncio.run(_run_configured_probe(config))
    except (FileNotFoundError, ProviderConfigurationError):
        print("[ERR] provider configuration unavailable")
        return 2


if __name__ == "__main__":
    sys.exit(main())
