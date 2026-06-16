"""Phase 5 准备: 验证两个 endpoint 都活着, 不改 .env.

1. mimo-v2.5-pro (judge 路径) — 用户硬约束: 不可用立即停止
2. deepseek-v4-pro on ARK volces — coding.txt 新模型, 待接 CUSTOM_*

退出码:
  0 = 两个都通
  1 = mimo 死 (按硬约束 HARD STOP)
  2 = mimo 通 + 新 endpoint 死 (可继续 Phase 5 但不能切生成)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI


def load_env() -> None:
    here = Path(__file__).resolve().parent.parent
    load_dotenv(here / ".env")


async def ping(label: str, api_key: str, base_url: str, model: str) -> tuple[bool, str]:
    if not api_key:
        return False, "api_key 为空"
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
    try:
        rsp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=4,
            temperature=0.0,
        )
        text = (rsp.choices[0].message.content or "").strip()
        return True, f"reply={text!r} usage={rsp.usage.total_tokens}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def main() -> int:
    load_env()

    mimo_key = os.environ.get("MIMO_API_KEY", "")
    mimo_url = os.environ.get(
        "MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1"
    )
    mimo_model = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

    print(f"[1/2] mimo judge ({mimo_model}) @ {mimo_url}")
    mimo_ok, mimo_info = await ping("mimo", mimo_key, mimo_url, mimo_model)
    print(f"      {'OK' if mimo_ok else 'FAIL'}: {mimo_info}")

    if not mimo_ok:
        print()
        print("HARD STOP: mimo 不可用. 按用户约束停止 Phase 5 工作.")
        print("可能原因: 401 (key 失效) / 429 (quota) / 网络 / 模型 404")
        return 1

    # coding.txt 数据 — 直接硬编码, 还没写入 .env
    ark_key = "b5e36001-0f63-4b25-a4e7-71bf3fb70035"
    ark_url = "https://ark.cn-beijing.volces.com/api/coding/v3"
    ark_model = "deepseek-v4-pro"

    print(f"[2/2] new gen ({ark_model}) @ {ark_url}")
    ark_ok, ark_info = await ping("ark", ark_key, ark_url, ark_model)
    print(f"      {'OK' if ark_ok else 'FAIL'}: {ark_info}")

    if not ark_ok:
        print()
        print("新 endpoint 不通. 不能切 LLM_PROVIDER=custom.")
        print("建议: 1) 核对 URL (/api/coding/v3 是否正确, 一般 ARK 是 /api/v3)")
        print("      2) 核对 model id (deepseek-v4-pro 是否 ARK 注册名)")
        print("      3) 核对 key 权限")
        return 2

    print()
    print("OK: mimo + 新 endpoint 都通. 可继续 .env 切换.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
