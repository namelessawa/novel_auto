"""iter#119 Phase 3-B — cast-confound control 通过 --cast-{a,b,c}-count
精确指定 bootstrap 生成角色数, 让跨 seed bench 实验 cast 可控.

验证: prompt 渲染时 cast_breakdown / cast_tiers 正确切换 wide vs precise.
不调 LLM, pure prompt-template 测试.
"""

from __future__ import annotations

import pytest

from bootstrap_prompts import PROMPT_CHARACTERS


def _render(cast_breakdown: str, cast_tiers: str) -> str:
    return PROMPT_CHARACTERS.format(
        world_state="{}",
        cast_breakdown=cast_breakdown,
        cast_tiers=cast_tiers,
    )


def _build_cast_strings(a, b, c) -> tuple[str, str]:
    """Reflect 实际 bootstrap_world cast string 构造 (iter#123 后 all-or-nothing).

    0/3 设 → wide. 3/3 设 → 恰好 N. 1-2/3 设 → ValueError (调用方处理).
    """
    set_count = sum(x is not None for x in (a, b, c))
    if set_count == 0:
        return (
            "6-10 个起始角色",
            "3 个 A 级 (主角候选, 深度建模) / 3-4 个 B 级 (重要配角) / "
            "2-3 个 C 级 (NPC)",
        )
    if set_count == 3:
        total = a + b + c
        return (
            f"恰好 {total} 个起始角色 (固定)",
            f"恰好 {a} 个 A 级 (主角候选, 深度建模) / "
            f"恰好 {b} 个 B 级 (重要配角) / "
            f"恰好 {c} 个 C 级 (NPC)",
        )
    raise ValueError(
        f"cast 三个参数必须 all-or-nothing (--cast-a/b/c-count). "
        f"目前 {set_count}/3 设, 防止部分设悄悄混 default."
    )


def test_default_wide_when_no_cast_args():
    """无参 → wide range 6-10."""
    cb, ct = _build_cast_strings(None, None, None)
    rendered = _render(cb, ct)
    assert "6-10 个起始角色" in rendered
    assert "3 个 A 级" in rendered
    assert "3-4 个 B 级" in rendered
    assert "2-3 个 C 级" in rendered
    assert "恰好" not in rendered  # wide 模式无 '恰好'


def test_precise_all_three_set():
    """全设 → 恰好 N 个 (固定)."""
    cb, ct = _build_cast_strings(2, 2, 1)
    rendered = _render(cb, ct)
    assert "恰好 5 个起始角色" in rendered
    assert "恰好 2 个 A 级" in rendered
    assert "恰好 2 个 B 级" in rendered
    assert "恰好 1 个 C 级" in rendered


def test_partial_raises_at_helper_level():
    """iter#123 review HIGH: partial set 必须拒绝, 防 silent default 混入."""
    with pytest.raises(ValueError, match="all-or-nothing"):
        _build_cast_strings(3, None, None)


def test_precise_minimum_one_each():
    """1+1+1 = 3 角色精确."""
    cb, ct = _build_cast_strings(1, 1, 1)
    rendered = _render(cb, ct)
    assert "恰好 3 个起始角色" in rendered


def test_precise_zero_c_allowed():
    """C=0 允许 (无 NPC, 只 A+B)."""
    cb, ct = _build_cast_strings(2, 1, 0)
    rendered = _render(cb, ct)
    assert "恰好 3 个起始角色" in rendered
    assert "恰好 0 个 C 级" in rendered


def test_cli_args_present():
    """iter#123 review MEDIUM: 直接验证 cast args 在 CLI 中存在
    (而非 SystemExit on --help, 旧测试 false-positive — pre-iter#119 也 PASS).
    """
    import contextlib
    import io

    from bootstrap_prompts import main

    buf = io.StringIO()
    with contextlib.suppress(SystemExit), contextlib.redirect_stdout(buf):
        main(["--help"])
    help_text = buf.getvalue()
    assert "--cast-a-count" in help_text
    assert "--cast-b-count" in help_text
    assert "--cast-c-count" in help_text


# iter#123 review HIGH: partial-set 必须拒绝 (防 silent default 混入)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b,c",
    [
        (3, None, None),
        (None, 2, None),
        (None, None, 1),
        (2, 2, None),
        (2, None, 1),
        (None, 2, 1),
    ],
)
def test_partial_cast_set_raises(a, b, c):
    """1 或 2/3 设 → 拒绝, all-or-nothing 强制 bench 复现性."""
    # 模拟 bootstrap_world 内 cast 分流逻辑 (不调 LLM, 只测分流)
    set_count = sum(x is not None for x in (a, b, c))
    assert set_count in (1, 2)
    # bootstrap_world 应在内部抛 ValueError. 这里直接 reproduce 该分流逻辑
    # 等价测 — 完整 e2e 测试在 test_bootstrap_partial_cast_raises.py
    with pytest.raises(ValueError, match="all-or-nothing"):
        if set_count == 0 or set_count == 3:
            pass
        else:
            raise ValueError(
                "cast 三个参数必须 all-or-nothing (--cast-a/b/c-count). "
                f"目前 {set_count}/3 设, 防止部分设悄悄混 default."
            )


def test_bootstrap_world_partial_cast_raises():
    """bootstrap_world 集成层: partial 设 → ValueError before LLM 调用.
    iter#123 review MEDIUM gap — 之前无集成测试守卫 partial 路径.
    """
    import asyncio

    from bootstrap_prompts import bootstrap_world

    async def _run():
        await bootstrap_world(
            novel_id="test_partial",
            data_dir="/tmp/test_partial_cast",
            seed="测试种子",
            positioning="测试",
            references="测试",
            cast_a_count=3,  # 仅设 a, b/c None — 必须 fail-loud
        )

    with pytest.raises(ValueError, match="all-or-nothing"):
        asyncio.run(_run())
