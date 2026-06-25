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
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

# 默认走 LLM_PROVIDER (本 repo 现 custom = deepseek).
os.environ.setdefault("LLM_PROVIDER", "custom")


async def _probe() -> int:
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
        )
    except Exception as e:  # broad — we want to inspect error class
        msg = str(e)
        # DeepSeek 429 出 AccountQuotaExceeded / RateLimitExceeded
        # ARK 同样 ServerOverloaded / RateLimit
        lower = msg.lower()
        if any(
            s in lower
            for s in (
                "accountquotaexceeded",
                "ratelimitexceeded",
                "429",
                "too many requests",
                "quotaexceeded",
                "serveroverloaded",
            )
        ):
            print(f"[QUOTA] {msg[:300]}")
            return 1
        print(f"[ERR] {type(e).__name__}: {msg[:300]}")
        return 2

    content = (resp.content or "").strip()
    tokens = getattr(resp, "usage", {}).get("total_tokens", "?")
    if not content:
        print(f"[ERR] empty content from LLM. tokens={tokens}")
        return 2
    print(f"[OK] quota healthy. content_len={len(content)} tokens={tokens}")
    print(f"     sample: {content[:60]}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="LLM quota smoke probe")
    p.add_argument("--provider", default="", help="覆盖 LLM_PROVIDER env (e.g. deepseek)")
    args = p.parse_args()
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    return asyncio.run(_probe())


if __name__ == "__main__":
    sys.exit(main())
