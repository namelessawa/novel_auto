"""Focused test: compare information extraction between glm-5.3 and deepseek-v4-pro.

Uses a sample urban-life prose to test whether deepseek-v4-pro produces
parseable structured output where glm-5.3 returned empty.

Usage:
    python scripts/test_extraction_deepseek.py --provider-file coding.txt --deepseek-file coding_deepseek_v4_pro.txt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
_PROJECT_ROOT = _BACKEND_DIR.parent
for p in (str(_PROJECT_ROOT), str(_BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


SAMPLE_PROSE = """
凌晨一点，林晓发来两行短信："我们不合适""祝好"。陈默看过没回，短信躺在收件箱里，像一张过期的车票。

第二天早上，房东发消息通知下季度房租涨两成，"市场行情，月底前答复"，态度冷硬。陈默算了算存款，只够撑三个月。

下午三点，总监发来四字修改意见"再打磨打磨"。陈默想起去年项目给部门省了两百多万，总监拍着他肩膀说晋升"今年稳了"。现在裁员通知下来，承诺化为泡影。

合租室友小马搬走了，东西全部搬走，沙发上的人形凹陷弹回来了，留下纸条："默哥，我先撤了，押金我自己找房东退，你别管"，落款画了个笑脸。

凌晨五点半，保洁阿姨见到他又通宵，说"小陈，又通宵啊""你们年轻人，命硬"。

母亲从六百公里外的县城来电，信号断断续续，劝他考老家公务员、告知父亲体检情况，挂电话前说"生日快乐，妈记得呢"——唯一记得他生日的人。
"""


async def test_extraction(provider_file: Path, deepseek_file: Path | None):
    from nf_core import provider_runtime
    from story.stateful_pipeline.llm_roles import extract_information
    from story.stateful_pipeline.models import InformationField, InformationSchema

    # Build a schema for urban life
    schema = InformationSchema(
        novel_id="test",
        revision=1,
        fields=[
            InformationField(key="character_relations", name="人物关系", description="人物之间的关系", order=0),
            InformationField(key="finance_status", name="经济状况", description="经济相关事件", order=1),
            InformationField(key="career_status", name="职业状态", description="职业相关事件", order=2),
            InformationField(key="emotional_state", name="情绪状态", description="主角情绪变化", order=3),
        ],
        source="user_defined",
    )

    results = {}

    # Test 1: default provider (glm-5.3 from coding.txt)
    print("\n=== Test 1: Default provider (glm-5.3) ===")
    config1 = provider_runtime.ProviderRuntimeConfig.from_provider_file(provider_file)
    import dataclasses
    config1 = dataclasses.replace(config1, thinking_mode="")
    provider_runtime.set_request_provider_config(config1)
    print(f"Provider: {config1.provider}, Model: {config1.model}")

    try:
        result1 = await extract_information(
            novel_id="test",
            chapter_number=1,
            prose_text=SAMPLE_PROSE,
            schema=schema,
        )
        results["glm-5.3"] = result1
        total_items = sum(len(v) for v in result1.values())
        print(f"SUCCESS: extracted {total_items} items across {len(result1)} fields")
        for key, items in result1.items():
            print(f"  {key}: {len(items)} items")
    except Exception as exc:
        results["glm-5.3"] = None
        print(f"FAILED: {exc}")

    # Test 2: deepseek-v4-pro (if provider file given)
    if deepseek_file and deepseek_file.exists():
        print("\n=== Test 2: deepseek-v4-pro ===")
        config2 = provider_runtime.ProviderRuntimeConfig.from_provider_file(deepseek_file)
        config2 = dataclasses.replace(config2, thinking_mode="")
        print(f"Provider: {config2.provider}, Model: {config2.model}")

        try:
            result2 = await extract_information(
                novel_id="test",
                chapter_number=1,
                prose_text=SAMPLE_PROSE,
                schema=schema,
                provider_config=config2,
            )
            results["deepseek-v4-pro"] = result2
            total_items = sum(len(v) for v in result2.values())
            print(f"SUCCESS: extracted {total_items} items across {len(result2)} fields")
            for key, items in result2.items():
                print(f"  {key}: {len(items)} items")
        except Exception as exc:
            results["deepseek-v4-pro"] = None
            print(f"FAILED: {exc}")

    # Summary
    print("\n=== Summary ===")
    for model, result in results.items():
        if result is None:
            print(f"{model}: FAILED")
        else:
            total = sum(len(v) for v in result.values())
            print(f"{model}: SUCCESS ({total} items)")

    return results


def main():
    parser = argparse.ArgumentParser(description="Test extraction with deepseek-v4-pro")
    parser.add_argument("--provider-file", type=Path, default=Path("coding.txt"))
    parser.add_argument("--deepseek-file", type=Path, default=Path("coding_deepseek_v4_pro.txt"))
    args = parser.parse_args()

    if not args.provider_file.exists():
        print(f"Error: provider file not found: {args.provider_file}")
        sys.exit(1)

    asyncio.run(test_extraction(args.provider_file, args.deepseek_file))


if __name__ == "__main__":
    main()
