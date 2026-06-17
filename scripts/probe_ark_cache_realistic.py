"""Phase 5-A follow-up #2 — realistic narrator-size cache probe.

> 首次 probe_ark_cache.py 探针在 970-token system prompt 下全 0 命中, 但 5-tick
> pilot bench-phase5a-cache-vis-pilot.json 报 narrator 56.9% / showrunner 48.9%
> cache hit. 差异可能是 prompt 体积没顶到 ARK cache 触发阈值.
>
> 本 probe 用真实 NARRATOR_SYSTEM_PROMPT (~1500 chars 中文 = ~800-1100 tokens)
> + 真实长度 USER prompt, 模拟 narrator 实际 ~3000 tokens/call 场景, 连发 6 次
> 测 cache 命中是否随 prompt 体积上 ARK 阈值后激活.
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


_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from agents.narrator_agent import NARRATOR_SYSTEM_PROMPT  # noqa: E402


@dataclass(frozen=True)
class CallResult:
    label: str
    elapsed_sec: float
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cache_hit_rate: float
    sys_chars: int
    user_chars: int
    error: str | None = None


_USER_PROMPT_REALISTIC = (
    "# 连载进度\n"
    "tick=42, world_time=2026-03-15 18:42:00\n"
    "tracking_character_id=char_su_mo (苏默)\n\n"
    "# 当前 tick 事件\n"
    + json.dumps(
        [
            {
                "id": "evt_042_01",
                "type": "observation",
                "tick": 42,
                "description": "苏默走进赤铜巷, 闻到雨后铁锈味",
                "narrative_value": 7,
                "narrative_value_hint": 7,
            },
            {
                "id": "evt_042_02",
                "type": "exogenous",
                "tick": 42,
                "description": "巷口传来一声金属碰撞响, 距离约 30 米",
                "narrative_value": 8,
                "narrative_value_hint": 8,
            },
            {
                "id": "evt_042_03",
                "type": "dialogue",
                "tick": 42,
                "description": "苏默贴墙停步, 摸到布袋里的卷宗硬壳",
                "narrative_value": 6,
                "narrative_value_hint": 6,
            },
        ],
        ensure_ascii=False,
        indent=2,
    )
    + "\n\n# 简报: 角色\n"
    + json.dumps(
        [
            {
                "id": "char_su_mo",
                "name": "苏默",
                "role": "失语少女管理员",
                "goal": "把三份机密卷宗送达内城",
                "secret": "她其实知道卷宗里某份是栽赃自己的",
                "facts": ["颈后有刺青", "右手腕戴铁链", "今天刚领回三份卷宗"],
            }
        ],
        ensure_ascii=False,
        indent=2,
    )
    + "\n\n# 开放 loops\n"
    + json.dumps(
        [
            {
                "id": "loop_001",
                "summary": "守备官递卷宗时手心出汗, '尽快'二字没头没尾",
                "urgency": 7,
                "opened_tick": 35,
            },
            {
                "id": "loop_002",
                "summary": "外城与内城的赤铜巷有铸铁栏杆, 雨水会嘶嘶冒白烟",
                "urgency": 4,
                "opened_tick": 40,
            },
        ],
        ensure_ascii=False,
        indent=2,
    )
    + "\n\n# 前文结尾\n"
    + "酸雨落了整夜。天亮时没停。\n"
    + "铁影城的屋顶在雾中只露出轮廓, 像一排生锈的锯齿. 街巷窄, 两面高墙夹着,\n"
    + "雨水沿墙根淌下来, 颜色发黄, 碰到铁栏杆就嘶嘶响, 冒一点白烟. 栏杆上\n"
    + "原本有漆, 早被蚀光了, 露出底下坑洼的铸铁.\n"
    + "玄烛低头走过赤铜巷. 外套领子竖着, 还是挡不住那股味道 — 煤烟混铁锈,\n"
    + "呛嗓子. 他把布袋换到另一边肩上, 里面的东西硌着肋骨. 三份卷宗, 封蜡完\n"
    + "好, 是昨夜从外城守备处领回来的. 编号 6-17、6-18、6-19. 守备官递过来\n"
    + "的时候手心出汗, 说了句'尽快', 多余的话一个字没有.\n\n"
    + "# 任务\n严格按 schema 输出本 tick narrative_text 等字段。"
)


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


async def _call(
    client: AsyncOpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
    label: str,
    extra_body: dict | None = None,
    *,
    max_tokens: int = 1200,
) -> CallResult:
    t0 = time.monotonic()
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.85,
        max_tokens=max_tokens,
    )
    if extra_body is not None:
        kwargs["extra_body"] = extra_body
    try:
        rsp = await client.chat.completions.create(**kwargs)
        usage = rsp.usage
        elapsed = time.monotonic() - t0
        pt = int(usage.prompt_tokens) if usage else 0
        ct = int(usage.completion_tokens) if usage else 0
        cached = _extract_cached(usage)
        return CallResult(
            label=label,
            elapsed_sec=round(elapsed, 2),
            prompt_tokens=pt,
            completion_tokens=ct,
            cached_tokens=cached,
            cache_hit_rate=round(cached / max(1, pt), 4),
            sys_chars=len(system_prompt),
            user_chars=len(user_prompt),
        )
    except Exception as e:
        return CallResult(
            label=label,
            elapsed_sec=round(time.monotonic() - t0, 2),
            prompt_tokens=0,
            completion_tokens=0,
            cached_tokens=0,
            cache_hit_rate=0.0,
            sys_chars=len(system_prompt),
            user_chars=len(user_prompt),
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )


async def main() -> int:
    load_dotenv(_REPO_ROOT / ".env")
    api_key = os.environ.get("CUSTOM_API_KEY", "")
    base_url = os.environ.get("CUSTOM_BASE_URL", "")
    model = os.environ.get("CUSTOM_MODEL", "")
    if not (api_key and base_url and model):
        print("CUSTOM_* 凭据不全")
        return 1

    print(f"endpoint={base_url}")
    print(f"model={model}")
    print(f"NARRATOR_SYSTEM_PROMPT len={len(NARRATOR_SYSTEM_PROMPT)} chars")
    print(f"USER_PROMPT_REALISTIC len={len(_USER_PROMPT_REALISTIC)} chars\n")

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=180.0)

    print(
        "== Realistic narrator-size repeat probe "
        "(6 calls, identical system+user, thinking off, 2s apart) =="
    )
    results: list[CallResult] = []
    for i in range(6):
        r = await _call(
            client,
            model,
            NARRATOR_SYSTEM_PROMPT,
            _USER_PROMPT_REALISTIC,
            label=f"R{i + 1}",
            extra_body={"thinking": {"type": "disabled"}},
        )
        results.append(r)
        print(
            f"  R{i + 1}: prompt={r.prompt_tokens} cached={r.cached_tokens} "
            f"hit={r.cache_hit_rate * 100:.1f}% completion={r.completion_tokens} "
            f"t={r.elapsed_sec}s"
            + (f"  ERR={r.error}" if r.error else "")
        )
        await asyncio.sleep(2.0)

    out_dir = _REPO_ROOT / "docs" / "iter"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    out_path = out_dir / f"probe-ark-cache-realistic-{ts}.json"

    payload = {
        "started_at": ts,
        "endpoint": base_url,
        "model": model,
        "system_prompt_chars": len(NARRATOR_SYSTEM_PROMPT),
        "user_prompt_chars": len(_USER_PROMPT_REALISTIC),
        "calls": [asdict(r) for r in results],
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print("== Verdict ==")
    first = results[0].cached_tokens if results else 0
    later = [r.cached_tokens for r in results[1:]]
    any_hit_later = any(c > 0 for c in later)
    if any_hit_later:
        print(
            f"  Cache IS active on realistic prompts: "
            f"first={first}, subsequent={later}"
        )
    else:
        print(
            f"  Cache STILL silent on realistic prompts: "
            f"first={first}, subsequent={later}"
        )
        print(
            "  → ARK volces coding-endpoint deepseek-v4-pro likely 不暴露 cached_tokens"
        )
        print(
            "  → 5-tick pilot 的 56.9% 数字可能是 metadata 短期暴露后 ARK 改了, "
            "或来自不同 endpoint"
        )

    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
