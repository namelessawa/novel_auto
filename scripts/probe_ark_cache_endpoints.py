"""Phase 5-A follow-up #3 — compare ARK endpoints for cache exposure.

> probe_ark_cache.py + probe_ark_cache_realistic.py 在 ``/api/coding/v3``
> endpoint 上 22 次调用全 0 命中. 假设 coding endpoint 关了 prefix cache
> 暴露 (或干脆没启用), 试标准 ``/api/v3`` endpoint 看是否暴露.
>
> 注意: 标准 ``/api/v3`` 可能 model 注册名不一样, deepseek-v4-pro 在两
> endpoint 上可能不同. 如果 405/404, 说明 endpoint 不兼容 — 已知信号.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI


@dataclass(frozen=True)
class CallResult:
    endpoint_tag: str
    base_url: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    elapsed_sec: float
    error: str | None = None


_PROBE_USER = (
    "请用 200 字写一段中文小说: 黄昏老巷, 角色苏默听见远处金属碰撞响。"
    "输出纯文本, 不要 JSON 围栏。"
)
_PROBE_SYS = "你是一段中文连载小说的执笔人。" * 30  # ~330 chars to push token count up


def _extract_cached(usage_obj: Any) -> int:
    if usage_obj is None:
        return 0
    details = getattr(usage_obj, "prompt_tokens_details", None)
    if details is None:
        return 0
    val = getattr(details, "cached_tokens", None)
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


async def _call_pair(
    base_url: str, model: str, api_key: str, tag: str
) -> list[CallResult]:
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
    out: list[CallResult] = []
    for i in range(3):
        t0 = time.monotonic()
        try:
            rsp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _PROBE_SYS},
                    {"role": "user", "content": _PROBE_USER},
                ],
                temperature=0.0,
                max_tokens=400,
                extra_body={"thinking": {"type": "disabled"}},
            )
            usage = rsp.usage
            out.append(
                CallResult(
                    endpoint_tag=f"{tag}#{i + 1}",
                    base_url=base_url,
                    model=model,
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    cached_tokens=_extract_cached(usage),
                    elapsed_sec=round(time.monotonic() - t0, 2),
                )
            )
        except Exception as e:
            out.append(
                CallResult(
                    endpoint_tag=f"{tag}#{i + 1}",
                    base_url=base_url,
                    model=model,
                    prompt_tokens=0,
                    completion_tokens=0,
                    cached_tokens=0,
                    elapsed_sec=round(time.monotonic() - t0, 2),
                    error=f"{type(e).__name__}: {str(e)[:200]}",
                )
            )
        await asyncio.sleep(1.5)
    return out


async def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.environ.get("CUSTOM_API_KEY", "")
    coding_url = os.environ.get("CUSTOM_BASE_URL", "")  # /api/coding/v3
    model_name = os.environ.get("CUSTOM_MODEL", "deepseek-v4-pro")
    if not (api_key and coding_url and model_name):
        print("CUSTOM_* 凭据不全")
        return 1

    # Derive standard endpoint from coding endpoint
    standard_url = coding_url.replace("/api/coding/v3", "/api/v3")

    print(f"Coding endpoint: {coding_url}")
    print(f"Standard endpoint: {standard_url}")
    print(f"Model: {model_name}")
    print(f"Probe sys chars: {len(_PROBE_SYS)}")
    print(f"Probe user chars: {len(_PROBE_USER)}\n")

    all_results: list[CallResult] = []

    print("== Coding endpoint /api/coding/v3 ==")
    coding_results = await _call_pair(coding_url, model_name, api_key, "coding")
    for r in coding_results:
        print(
            f"  {r.endpoint_tag}: prompt={r.prompt_tokens} cached={r.cached_tokens} "
            f"t={r.elapsed_sec}s"
            + (f"  ERR={r.error}" if r.error else "")
        )
    all_results.extend(coding_results)

    print("\n== Standard endpoint /api/v3 ==")
    standard_results = await _call_pair(
        standard_url, model_name, api_key, "standard"
    )
    for r in standard_results:
        print(
            f"  {r.endpoint_tag}: prompt={r.prompt_tokens} cached={r.cached_tokens} "
            f"t={r.elapsed_sec}s"
            + (f"  ERR={r.error}" if r.error else "")
        )
    all_results.extend(standard_results)

    # Also try with the ARK_JUDGE endpoint (glm-5.1) as control — should not affect coding
    judge_url = os.environ.get("ARK_JUDGE_BASE_URL", "")
    judge_model = os.environ.get("ARK_JUDGE_MODEL", "")
    judge_key = os.environ.get("ARK_JUDGE_API_KEY", api_key)
    if judge_url and judge_model:
        print(f"\n== Judge endpoint ({judge_url}, model={judge_model}) ==")
        judge_results = await _call_pair(judge_url, judge_model, judge_key, "judge")
        for r in judge_results:
            print(
                f"  {r.endpoint_tag}: prompt={r.prompt_tokens} cached={r.cached_tokens} "
                f"t={r.elapsed_sec}s"
                + (f"  ERR={r.error}" if r.error else "")
            )
        all_results.extend(judge_results)

    out_dir = Path(__file__).resolve().parent.parent / "docs" / "iter"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    out_path = out_dir / f"probe-ark-endpoints-{ts}.json"
    payload = {
        "started_at": ts,
        "probe_sys_chars": len(_PROBE_SYS),
        "probe_user_chars": len(_PROBE_USER),
        "calls": [asdict(r) for r in all_results],
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nWrote {out_path}")

    print("\n== Verdict ==")
    for tag in ("coding", "standard", "judge"):
        hits = [r.cached_tokens for r in all_results if r.endpoint_tag.startswith(tag)]
        ok = [r for r in all_results if r.endpoint_tag.startswith(tag) and not r.error]
        err = [r for r in all_results if r.endpoint_tag.startswith(tag) and r.error]
        if not (ok or err):
            continue
        any_cache = any(h > 0 for h in hits)
        print(
            f"  {tag}: {len(ok)} ok / {len(err)} err / "
            f"cached={hits} "
            f"{'(CACHE EXPOSED)' if any_cache else '(no cache exposed)'}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
