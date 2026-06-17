"""Phase 5-A follow-up — ARK prefix-cache behavior probe.

> 200-tick longrange bench (commit 82820a5) 报 cached_tokens=0, 但 5-tick
> pilot 报 56.9% hit. 异常落在三种可能:
>
>  1. ARK 端 cache TTL < tick 间隔, 长程下大部分 tick 命中"刚 refresh 的冷 cache"
>  2. thinking-disabled 模式不暴露 cached_tokens metadata
>  3. ARK prefix cache 启用度按时间窗/地区波动
>
> 这个 probe 不动 narrator 主路径, 跑独立 LLM 调用矩阵, 直接观察 ARK
> 返回的 ``usage.prompt_tokens_details.cached_tokens``。
>
> Test matrix:
>
>  A. Warm-up baseline: 同 SYSTEM + 同 USER 连发 5 次, 间隔 1s — 看 first miss
>     vs subsequent hit。
>  B. 长间隔: 同 prompt 间隔 30s / 90s / 180s / 300s — 测 TTL 上限。
>  C. Thinking on vs off: 同 prompt 两种模式, 看 cached_tokens 是否仅在
>     thinking-disabled 暴露。
>  D. SYSTEM 长度梯度: 256 / 1024 / 4096 chars — 测最小 prefix 命中长度。
>
> 退出码:
>   0 = 全部跑通, 数据写入 docs/iter/probe-ark-cache-{ts}.json
>   1 = ARK 凭据缺失
>   2 = 第一次调用就失败 (网络/quota)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI


@dataclass(frozen=True)
class CallResult:
    label: str
    elapsed_sec: float
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cache_hit_rate: float
    error: str | None = None


@dataclass
class MatrixReport:
    started_at: float
    ended_at: float = 0.0
    endpoint: str = ""
    model: str = ""
    a_warmup: list[CallResult] = field(default_factory=list)
    b_ttl: list[CallResult] = field(default_factory=list)
    c_thinking: list[CallResult] = field(default_factory=list)
    d_prefix_length: list[CallResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


_NARRATOR_LIKE_SYSTEM_SHORT = (
    "你是一段中文连载小说的执笔人。输出 JSON, 不要 markdown 围栏。"
)

_NARRATOR_LIKE_SYSTEM_MEDIUM = (
    _NARRATOR_LIKE_SYSTEM_SHORT
    + "\n\n# 输出 schema\n"
    + json.dumps(
        {
            "narrative_text": "<中文正文 200-400 字>",
            "viewpoint_characters": ["<id>"],
            "scene_focus": "<一句话>",
            "events_consumed": ["<evt_id>"],
            "consistency_flags": [],
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n\n# 写作要求\n"
    + "- 用具象意象,避免抽象议论\n"
    + "- 每段视点角色至少 1 个具体动作\n"
    + "- 信息克制,留白让读者推断\n"
)

_NARRATOR_LIKE_SYSTEM_LONG = (
    _NARRATOR_LIKE_SYSTEM_MEDIUM
    + "\n\n# 风格示范 (literary 默认)\n"
    + (
        "酸雨落了整夜。天亮时没停。\n"
        "铁影城的屋顶在雾中只露出轮廓, 像一排生锈的锯齿. 街巷窄, "
        "两面高墙夹着, 雨水沿墙根淌下来, 颜色发黄, 碰到铁栏杆就嘶嘶响, "
        "冒一点白烟. 栏杆上原本有漆, 早被蚀光了, 露出底下坑洼的铸铁.\n\n"
    )
    * 8  # repeat to push length
)


_USER_PROMPT_FIXED = (
    "# 连载进度\n"
    "tick=42, world_time=2026-03-15 18:42, 苏默 (失语少女管理员) 走在赤铜巷。\n\n"
    "# 当 tick 事件\n"
    '[{"id":"evt_42_01","type":"observation",'
    '"description":"金属碰撞声从巷口传来",'
    '"narrative_value":7}]\n\n'
    "# 任务\n按上面 schema 输出本 tick 叙述。"
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
    *,
    extra_body: dict | None = None,
    max_tokens: int = 600,
) -> CallResult:
    t0 = time.monotonic()
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
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
        )
    except Exception as e:
        return CallResult(
            label=label,
            elapsed_sec=round(time.monotonic() - t0, 2),
            prompt_tokens=0,
            completion_tokens=0,
            cached_tokens=0,
            cache_hit_rate=0.0,
            error=f"{type(e).__name__}: {str(e)[:200]}",
        )


async def matrix_a_warmup(
    client: AsyncOpenAI, model: str, *, n: int = 5
) -> list[CallResult]:
    """Same prompt N times, ~1s apart — see first miss vs subsequent hit."""
    out: list[CallResult] = []
    for i in range(n):
        r = await _call(
            client,
            model,
            _NARRATOR_LIKE_SYSTEM_MEDIUM,
            _USER_PROMPT_FIXED,
            label=f"A{i + 1}/N{n}",
            extra_body={"thinking": {"type": "disabled"}},
        )
        out.append(r)
        print(
            f"  A{i + 1}: prompt={r.prompt_tokens} cached={r.cached_tokens} "
            f"hit={r.cache_hit_rate * 100:.1f}% t={r.elapsed_sec}s"
            + (f"  ERR={r.error}" if r.error else "")
        )
        await asyncio.sleep(1.0)
    return out


async def matrix_b_ttl(
    client: AsyncOpenAI, model: str, *, intervals_sec: list[int]
) -> list[CallResult]:
    """Same prompt with growing intervals — find TTL ceiling."""
    out: list[CallResult] = []
    # Prime: fire 2 back-to-back so cache is definitely populated.
    print("  prime (2 calls back-to-back to populate cache)")
    for k in range(2):
        r = await _call(
            client,
            model,
            _NARRATOR_LIKE_SYSTEM_MEDIUM,
            _USER_PROMPT_FIXED,
            label=f"B_prime_{k + 1}",
            extra_body={"thinking": {"type": "disabled"}},
        )
        out.append(r)
        print(
            f"    B_prime_{k + 1}: cached={r.cached_tokens} "
            f"hit={r.cache_hit_rate * 100:.1f}%"
        )

    for interval in intervals_sec:
        print(f"  sleep {interval}s ...")
        await asyncio.sleep(interval)
        r = await _call(
            client,
            model,
            _NARRATOR_LIKE_SYSTEM_MEDIUM,
            _USER_PROMPT_FIXED,
            label=f"B_after_{interval}s",
            extra_body={"thinking": {"type": "disabled"}},
        )
        out.append(r)
        print(
            f"    B_after_{interval}s: cached={r.cached_tokens} "
            f"hit={r.cache_hit_rate * 100:.1f}%"
            + (f"  ERR={r.error}" if r.error else "")
        )
    return out


async def matrix_c_thinking(
    client: AsyncOpenAI, model: str
) -> list[CallResult]:
    """Thinking on vs off — see if cached_tokens metadata depends on mode."""
    out: list[CallResult] = []
    scenarios: list[tuple[str, dict | None]] = [
        ("C_thinking_disabled_1", {"thinking": {"type": "disabled"}}),
        ("C_thinking_disabled_2", {"thinking": {"type": "disabled"}}),
        ("C_thinking_default_1", None),
        ("C_thinking_default_2", None),
    ]
    for label, eb in scenarios:
        r = await _call(
            client,
            model,
            _NARRATOR_LIKE_SYSTEM_MEDIUM,
            _USER_PROMPT_FIXED,
            label=label,
            extra_body=eb,
        )
        out.append(r)
        print(
            f"  {label}: prompt={r.prompt_tokens} cached={r.cached_tokens} "
            f"hit={r.cache_hit_rate * 100:.1f}% t={r.elapsed_sec}s"
            + (f"  ERR={r.error}" if r.error else "")
        )
        await asyncio.sleep(1.0)
    return out


async def matrix_d_prefix_length(
    client: AsyncOpenAI, model: str
) -> list[CallResult]:
    """SYSTEM prompt length gradient — find minimum prefix length for cache."""
    out: list[CallResult] = []
    scenarios = [
        ("D_system_short", _NARRATOR_LIKE_SYSTEM_SHORT),
        ("D_system_short_repeat", _NARRATOR_LIKE_SYSTEM_SHORT),
        ("D_system_medium", _NARRATOR_LIKE_SYSTEM_MEDIUM),
        ("D_system_medium_repeat", _NARRATOR_LIKE_SYSTEM_MEDIUM),
        ("D_system_long", _NARRATOR_LIKE_SYSTEM_LONG),
        ("D_system_long_repeat", _NARRATOR_LIKE_SYSTEM_LONG),
    ]
    for label, system in scenarios:
        r = await _call(
            client,
            model,
            system,
            _USER_PROMPT_FIXED,
            label=label,
            extra_body={"thinking": {"type": "disabled"}},
        )
        out.append(r)
        print(
            f"  {label}: sys_chars={len(system)} prompt={r.prompt_tokens} "
            f"cached={r.cached_tokens} hit={r.cache_hit_rate * 100:.1f}%"
            + (f"  ERR={r.error}" if r.error else "")
        )
        await asyncio.sleep(1.0)
    return out


def _summarize(report: MatrixReport) -> list[str]:
    notes: list[str] = []

    # A — warm-up
    a = report.a_warmup
    if a:
        first_hit = a[0].cached_tokens
        last_hits = [r.cached_tokens for r in a[1:]]
        any_subsequent = any(h > 0 for h in last_hits)
        notes.append(
            f"A (warm-up x{len(a)}): first_cached={first_hit}, "
            f"subsequent_cached={last_hits}, "
            f"cache_active={'YES' if any_subsequent else 'NO'}"
        )

    # B — TTL
    b = report.b_ttl
    if b:
        for r in b:
            tag = "HIT" if r.cached_tokens > 0 else "MISS"
            notes.append(
                f"B {r.label}: cached={r.cached_tokens} ({tag}) "
                f"hit_rate={r.cache_hit_rate * 100:.1f}%"
            )

    # C — thinking mode
    c = report.c_thinking
    if c:
        disabled = [r.cached_tokens for r in c if "disabled" in r.label]
        default = [r.cached_tokens for r in c if "default" in r.label]
        notes.append(
            f"C thinking_disabled cached: {disabled}, "
            f"thinking_default cached: {default}"
        )

    # D — prefix length
    d = report.d_prefix_length
    if d:
        for r in d:
            notes.append(
                f"D {r.label}: prompt={r.prompt_tokens} "
                f"cached={r.cached_tokens} hit={r.cache_hit_rate * 100:.1f}%"
            )

    return notes


async def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.environ.get("CUSTOM_API_KEY", "")
    base_url = os.environ.get("CUSTOM_BASE_URL", "")
    model = os.environ.get("CUSTOM_MODEL", "")
    if not (api_key and base_url and model):
        print("CUSTOM_* 凭据不全 (need CUSTOM_API_KEY / CUSTOM_BASE_URL / CUSTOM_MODEL)")
        return 1

    print(f"endpoint={base_url}")
    print(f"model={model}\n")

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
    report = MatrixReport(
        started_at=time.time(), endpoint=base_url, model=model
    )

    print("== A. Warm-up baseline (5 back-to-back, 1s apart) ==")
    try:
        report.a_warmup = await matrix_a_warmup(client, model)
    except Exception as e:
        print(f"  A FAILED outright: {e}")
        if not report.a_warmup:
            return 2

    print()
    print("== C. Thinking mode comparison (disabled x2 + default x2) ==")
    report.c_thinking = await matrix_c_thinking(client, model)

    print()
    print("== D. Prefix length gradient (short / medium / long, each x2) ==")
    report.d_prefix_length = await matrix_d_prefix_length(client, model)

    print()
    print("== B. TTL probe (30s / 90s / 180s after prime) ==")
    print("  (only run if A showed cache active — saves ~5 min if cache is off)")
    cache_active_in_a = any(
        r.cached_tokens > 0 for r in report.a_warmup[1:]
    )
    if cache_active_in_a:
        report.b_ttl = await matrix_b_ttl(
            client, model, intervals_sec=[30, 90, 180]
        )
    else:
        print("  SKIPPED — A 没观察到 cache 命中, TTL probe 无意义")
        report.notes.append("B_skipped: A 无命中故跳过 TTL 测")

    report.ended_at = time.time()
    report.notes.extend(_summarize(report))

    out_dir = Path(__file__).resolve().parent.parent / "docs" / "iter"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(report.started_at)
    out_path = out_dir / f"probe-ark-cache-{ts}.json"

    def _serialize(obj: Any) -> Any:
        if isinstance(obj, MatrixReport):
            d = asdict(obj)
            return d
        if isinstance(obj, CallResult):
            return asdict(obj)
        raise TypeError(f"unserializable: {type(obj)}")

    payload = {
        "started_at": report.started_at,
        "ended_at": report.ended_at,
        "duration_sec": round(report.ended_at - report.started_at, 1),
        "endpoint": report.endpoint,
        "model": report.model,
        "a_warmup": [asdict(r) for r in report.a_warmup],
        "b_ttl": [asdict(r) for r in report.b_ttl],
        "c_thinking": [asdict(r) for r in report.c_thinking],
        "d_prefix_length": [asdict(r) for r in report.d_prefix_length],
        "notes": report.notes,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print("== Summary ==")
    for line in report.notes:
        print(f"  {line}")
    print()
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
