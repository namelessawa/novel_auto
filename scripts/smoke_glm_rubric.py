"""诊断: glm-5.1 对 rubric_judge prompt 返回了什么 (用真 narrative)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_R))
sys.path.insert(0, str(_R / "backend"))
load_dotenv(_R / ".env")

from quality_metrics.judge import make_active_judge_fn  # noqa: E402
from quality_metrics.judge_prompts import RUBRIC_PROMPT_V1  # noqa: E402


_SAMPLE = """铁锈味比雨先散开。苏默把兜帽往下拽了拽，帽檐滴下来的水顺着鼻梁滑进嘴角，咸的，带着金属的腥。他站在巷口，看街对面的积水映出码头起重机的倒影，骨架似的铁臂在雾里只露出下半截，像被什么咬断了。

汽笛声从雾深处传来，闷闷的，像隔了好几层棉布。码头那边有人影晃动，弯着腰用铁铲把积水往排水沟里赶，铲刃刮过石板的声音尖锐，一下一下，像在磨什么。"""


async def main() -> int:
    judge_fn, model = make_active_judge_fn()
    print(f"judge model: {model}")
    prompt = RUBRIC_PROMPT_V1.format(text=_SAMPLE)
    print(f"prompt length: {len(prompt)} chars")
    print()
    raw = await judge_fn(prompt)
    print(f"--- raw response ({len(raw)} chars) ---")
    print(raw[:1500])
    print()
    print(f"--- starts with: {raw[:80]!r} ---")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
