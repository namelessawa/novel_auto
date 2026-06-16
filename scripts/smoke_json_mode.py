"""Phase 5-A 修复: 验证 ARK deepseek-v4-pro 支持 response_format=json_object.

ARK volces 号称 OpenAI 兼容, 但旁路 chat.completions 是否完整支持 JSON mode
取决于具体模型。Pilot 显示 deepseek-v4-pro 不按 prompt 指令吐 JSON, 我们想看
传 response_format 能否强制它做。

退出码:
  0 = JSON mode 支持, content 是合法 JSON
  1 = endpoint 接受 response_format 但返回内容不是 JSON
  2 = endpoint 不接受 response_format (BadRequest)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI


async def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    api_key = os.environ.get("CUSTOM_API_KEY", "")
    base_url = os.environ.get("CUSTOM_BASE_URL", "")
    model = os.environ.get("CUSTOM_MODEL", "")
    if not (api_key and base_url and model):
        print("CUSTOM_* 凭据不全, 退出.")
        return 2

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)

    print(f"endpoint={base_url} model={model}")
    print()

    sys_prompt = (
        "You output only JSON. Schema: "
        '{"greeting": str, "lucky_number": int}. No prose, no markdown.'
    )
    user_prompt = "Greet me and give me a lucky number."

    # 测试 1: 不传 response_format (baseline, 看模型是否自动遵守 prompt JSON 指令)
    print("[1/2] Baseline (no response_format)")
    try:
        r = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=100,
        )
        content = r.choices[0].message.content or ""
        print(f"      raw: {content!r}")
        try:
            parsed = json.loads(content)
            print(f"      OK: parsed as JSON = {parsed}")
        except json.JSONDecodeError:
            print("      FAIL: content NOT JSON (prompt-only mode broken)")
    except Exception as e:
        print(f"      error: {type(e).__name__}: {e}")

    print()

    # 测试 2: 显式传 response_format=json_object
    print("[2/2] With response_format={'type': 'json_object'}")
    try:
        r = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        content = r.choices[0].message.content or ""
        print(f"      raw: {content!r}")
        try:
            parsed = json.loads(content)
            print(f"      OK: parsed as JSON = {parsed}")
            return 0
        except json.JSONDecodeError as e:
            print(f"      FAIL: response_format accepted but content NOT JSON: {e}")
            return 1
    except Exception as e:
        msg = str(e)
        print(f"      error: {type(e).__name__}: {msg[:300]}")
        if "response_format" in msg or "json_object" in msg or "400" in msg:
            print("      → endpoint REJECTS response_format. ARK 不支持 JSON mode.")
            return 2
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
