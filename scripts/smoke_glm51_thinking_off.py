"""验证 glm-5.1 在 ARK 关掉 thinking 后能否做 judge 输出 (pairwise 形)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI


_REAL_PAIRWISE_PROMPT = """你是一名严格的中文文学评审。下面是两段中文小说,请判断哪段更好,从这些维度综合考虑: (1) 连贯性 (2) 角色声音 (3) 情节推进 (4) 文笔具象度。

# 段 A
雨打在锈蚀的铁皮屋顶上,声音密得像缝纫机。苏默拉低帽檐,靴子踩进街面的积水,油花溅到裤脚,散开一圈虹彩。他侧身避开一辆陷在泥里的板车,车辙深得能没过脚踝,远处山道传来金属摩擦的吱呀——生锈的货运缆车又卡住了。

# 段 B
雨下得很大,他低着头走。地上有水,他踩进去了。远处有声音。他不知道是什么。他继续走。

# 输出格式 (严格 JSON, 无 markdown 围栏)
{"winner": "A" or "B" or "TIE", "reason": "1 句中文理由"}
"""


async def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.environ.get("CUSTOM_API_KEY", "")
    base_url = os.environ.get("CUSTOM_BASE_URL", "")
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)

    for label, extra in [
        ("baseline (thinking on)", None),
        ("thinking disabled", {"thinking": {"type": "disabled"}}),
    ]:
        print(f"--- {label} ---")
        try:
            kwargs = {
                "model": "glm-5.1",
                "messages": [
                    {"role": "system", "content": "You output only JSON."},
                    {"role": "user", "content": _REAL_PAIRWISE_PROMPT},
                ],
                "temperature": 0.0,
                "max_tokens": 500,
            }
            if extra:
                kwargs["extra_body"] = extra
            r = await client.chat.completions.create(**kwargs)
            content = (r.choices[0].message.content or "").strip()
            reasoning = getattr(r.choices[0].message, "reasoning_content", None)
            print(f"      reasoning_content len: {len(reasoning) if reasoning else 0}")
            print(f"      content len: {len(content)}")
            print(f"      content: {content[:200]}")
            try:
                p = json.loads(content)
                print(f"      OK JSON: winner={p.get('winner')} reason={p.get('reason','')[:80]}")
            except Exception as e:
                print(f"      JSON parse FAIL: {e}")
        except Exception as e:
            print(f"      error: {type(e).__name__}: {str(e)[:200]}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
