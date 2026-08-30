"""Focused test: compare chapter WRITER reliability between glm-5.3 and deepseek-v4-pro.

The E2E failures showed 'Writer output too short (1 chars)' — this tests whether
deepseek-v4-pro produces more reliable prose output than glm-5.3.

Usage:
    python scripts/test_writer_deepseek.py --provider-file coding.txt --deepseek-file coding_deepseek_v4_pro.txt
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
_PROJECT_ROOT = _BACKEND_DIR.parent
for p in (str(_PROJECT_ROOT), str(_BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


SAMPLE_SYNOPSIS = (
    "二十八岁的林小满被互联网公司裁员后，退掉了合租公寓，搬进城中村。"
    "清晨她被隔壁肠粉店的蒸汽声吵醒，开始盘点人生：存款只够撑三个月。"
    "房东王婶看她可怜，提出让她帮忙看店抵扣部分房租。"
    "她在巷口吃肠粉时偶遇同样失意的落魄设计师周远，两人不打不相识。"
    "当天下午，她终于收到一家小创业公司的面试通知。"
)


async def test_writer(provider_file: Path, deepseek_file: Path | None, attempts: int = 3):
    from nf_core import provider_runtime
    from story.stateful_pipeline.llm_roles import write_chapter_simplified
    import dataclasses

    results = {}

    # Test 1: default provider (glm-5.3)
    print("\n=== Writer Test: Default provider (glm-5.3) ===")
    config1 = provider_runtime.ProviderRuntimeConfig.from_provider_file(provider_file)
    config1 = dataclasses.replace(config1, thinking_mode="")
    provider_runtime.set_request_provider_config(config1)
    print(f"Model: {config1.model}")

    try:
        prose1 = await write_chapter_simplified(
            novel_id="test",
            chapter_number=1,
            synopsis=SAMPLE_SYNOPSIS,
            style_prefix="",
            pacing_mode="flat",
            transfer_context="",
            max_attempts=attempts,
        )
        results["glm-5.3"] = len(prose1)
        print(f"SUCCESS: {len(prose1)} chars")
        print(f"Preview: {prose1[:150]}...")
    except Exception as exc:
        results["glm-5.3"] = 0
        print(f"FAILED: {exc}")

    # Test 2: deepseek-v4-pro
    if deepseek_file and deepseek_file.exists():
        print("\n=== Writer Test: deepseek-v4-pro ===")
        config2 = provider_runtime.ProviderRuntimeConfig.from_provider_file(deepseek_file)
        config2 = dataclasses.replace(config2, thinking_mode="")
        provider_runtime.set_request_provider_config(config2)
        print(f"Model: {config2.model}")

        try:
            prose2 = await write_chapter_simplified(
                novel_id="test",
                chapter_number=1,
                synopsis=SAMPLE_SYNOPSIS,
                style_prefix="",
                pacing_mode="flat",
                transfer_context="",
                max_attempts=attempts,
            )
            results["deepseek-v4-pro"] = len(prose2)
            print(f"SUCCESS: {len(prose2)} chars")
            print(f"Preview: {prose2[:150]}...")
        except Exception as exc:
            results["deepseek-v4-pro"] = 0
            print(f"FAILED: {exc}")

    print("\n=== Summary ===")
    for model, length in results.items():
        status = f"SUCCESS ({length} chars)" if length > 0 else "FAILED"
        print(f"{model}: {status}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Test writer with deepseek-v4-pro")
    parser.add_argument("--provider-file", type=Path, default=Path("coding.txt"))
    parser.add_argument("--deepseek-file", type=Path, default=Path("coding_deepseek_v4_pro.txt"))
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()

    if not args.provider_file.exists():
        print(f"Error: provider file not found: {args.provider_file}")
        sys.exit(1)

    asyncio.run(test_writer(args.provider_file, args.deepseek_file, args.attempts))


if __name__ == "__main__":
    main()
