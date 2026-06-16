"""Phase 5+: 验证 glm-5.1 在 ARK volces 上可作 judge 端点用.

试几种常见 model id 字符串 (ARK 命名不统一):
  - glm-5.1
  - glm-4.6
  - glm-4-plus
  - glm-4-flash

对每个 id 跑一次 pairwise-shaped prompt, 看哪个返回 valid JSON.

退出码: 0=有可用 id, 1=全部 fail
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI


_CANDIDATE_MODELS = ["glm-5.1", "glm-4.6", "glm-4.5", "glm-4-plus", "glm-4-flash"]

# pairwise-style judge prompt (短版)
_PROMPT = """对比段 A / 段 B 哪段更好, 只输出 JSON.

段 A: 雨打在铁皮屋顶上, 声音又硬又脆.
段 B: 雨下得很大, 屋顶很吵.

输出: {"winner": "A" or "B" or "TIE", "reason": "<one sentence>"}"""


async def try_model(client: AsyncOpenAI, model: str) -> tuple[bool, str]:
    try:
        r = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You output only JSON."},
                {"role": "user", "content": _PROMPT},
            ],
            temperature=0.0,
            max_tokens=200,
        )
        content = (r.choices[0].message.content or "").strip()
        try:
            payload = json.loads(content)
            if "winner" in payload:
                return True, f"OK winner={payload.get('winner')} usage={r.usage.total_tokens}"
            return False, f"missing winner field, content={content[:120]}"
        except json.JSONDecodeError:
            return False, f"non-JSON, content={content[:120]}"
    except Exception as e:
        msg = str(e)
        return False, f"{type(e).__name__}: {msg[:200]}"


async def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.environ.get("CUSTOM_API_KEY", "")
    base_url = os.environ.get("CUSTOM_BASE_URL", "")
    if not (api_key and base_url):
        print("CUSTOM_API_KEY/BASE_URL 不全, 退出.")
        return 1
    print(f"endpoint={base_url}\n")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30.0)

    any_ok = False
    for model_id in _CANDIDATE_MODELS:
        ok, info = await try_model(client, model_id)
        mark = "OK" if ok else "fail"
        print(f"  [{mark:4s}] {model_id:20s} {info}")
        if ok:
            any_ok = True
    return 0 if any_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
