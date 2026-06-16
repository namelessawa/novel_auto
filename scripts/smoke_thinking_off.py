"""Phase 5-A 修复探测: 关掉 deepseek-v4-pro 的 thinking, 看 JSON 输出是否稳.

假设: ARK deepseek-v4-pro 默认 thinking 开, 长中文 + complex schema 时推理 trace
泄漏到 content 导致 JSON 失败。试几种 ARK / OpenAI extra_body 参数, 比较:
  - 是否有 reasoning_content 字段
  - content 是否为合法 JSON
  - usage 是否变小 (无 reasoning tokens)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI


_NARRATOR_LIKE_PROMPT = """\
你是一段中文连载小说的执笔人。读完以下材料, 写一段 200-400 字正文。

# 严格输出 JSON 格式 (no markdown, no prose around it)

{
  "narrative_text": "实际中文小说正文 (200-400 字)",
  "viewpoint_characters": ["c1"],
  "scene_focus": "场景一句话概括",
  "events_consumed": ["evt_001"],
  "consistency_flags": []
}

# 素材

时间: 黄昏, 地点: 老巷子, 角色: 苏默 (失语少女管理员), 事件: 苏默走在
雨后的巷子, 听到远处一声金属碰撞响。
"""


async def try_call(label: str, client: AsyncOpenAI, model: str, **extra) -> None:
    print(f"--- {label} ---")
    try:
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": "You output only JSON."},
                {"role": "user", "content": _NARRATOR_LIKE_PROMPT},
            ],
            temperature=0.5,
            max_tokens=2000,
        )
        kwargs.update(extra)
        r = await client.chat.completions.create(**kwargs)
        msg = r.choices[0].message
        content = msg.content or ""
        reasoning = getattr(msg, "reasoning_content", None)
        usage = r.usage

        print(f"      prompt_tokens={usage.prompt_tokens}")
        print(f"      completion_tokens={usage.completion_tokens}")
        if reasoning:
            print(f"      reasoning_content present, len={len(reasoning)}")
        else:
            print("      reasoning_content absent")
        print(f"      content[:120]={content[:120]!r}")
        try:
            payload = json.loads(content)
            print(f"      OK: JSON parsed, keys={list(payload.keys())}")
        except json.JSONDecodeError as e:
            print(f"      FAIL JSON parse: {e}")
            # tail of content tells if reasoning leaked
            print(f"      content[-200:]={content[-200:]!r}")
    except Exception as e:
        print(f"      error: {type(e).__name__}: {str(e)[:300]}")
    print()


async def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.environ.get("CUSTOM_API_KEY", "")
    base_url = os.environ.get("CUSTOM_BASE_URL", "")
    model = os.environ.get("CUSTOM_MODEL", "")
    if not (api_key and base_url and model):
        print("CUSTOM_* 凭据不全")
        return 2

    print(f"endpoint={base_url}  model={model}\n")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

    # 0. Baseline (no thinking toggle)
    await try_call("0 baseline (thinking 默认)", client, model)

    # 1. ARK volces 文档常见: extra_body 传 thinking={"type":"disabled"}
    await try_call(
        "1 extra_body thinking type=disabled",
        client,
        model,
        extra_body={"thinking": {"type": "disabled"}},
    )

    # 2. Qwen 系列常见: enable_thinking=False
    await try_call(
        "2 extra_body enable_thinking=False",
        client,
        model,
        extra_body={"enable_thinking": False},
    )

    # 3. 一些 ARK 模型: thinking=False
    await try_call(
        "3 extra_body thinking=False",
        client,
        model,
        extra_body={"thinking": False},
    )

    # 4. ARK reasoning: 类似 OpenAI o1 的 reasoning={"effort":"low"}
    await try_call(
        "4 extra_body reasoning effort=low",
        client,
        model,
        extra_body={"reasoning": {"effort": "low"}},
    )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
