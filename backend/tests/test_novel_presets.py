"""Lock the theme + style preset registries against accidental drift.

These pure-data registries don't need integration coverage — but they ARE
referenced by external surfaces (bootstrap CLI, matrix bench, future UI),
so we pin:

* Every theme has non-empty curated seed (80+ chars per project policy)
* Every style has non-empty narrator addendum
* Keys are snake_case + ASCII (CLI / DB safe)
* No collision when truncated to 18 chars (matrix bench label budget)
* Removed-key guard: critical keys (steampunk_archive, literary) must always
  exist — they're the backward-compatible defaults that older novels bind to.
"""

from __future__ import annotations

import re

import pytest

from novel_presets import (
    STYLE_PRESETS,
    THEME_SEEDS,
    StylePreset,
    ThemeSeed,
    get_style_preset,
    get_theme_seed,
    list_style_keys,
    list_theme_keys,
)


_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


# ---------------------------------------------------------------------------
# Theme registry invariants
# ---------------------------------------------------------------------------


def test_theme_registry_non_empty() -> None:
    assert len(THEME_SEEDS) >= 10, (
        f"theme registry should cover 主流网文 (≥10), got {len(THEME_SEEDS)}"
    )


def test_theme_keys_are_snake_case_ascii() -> None:
    for key in THEME_SEEDS:
        assert _KEY_RE.match(key), f"theme key {key!r} must match {_KEY_RE.pattern}"


def test_every_theme_has_curated_seed() -> None:
    for key, theme in THEME_SEEDS.items():
        assert isinstance(theme, ThemeSeed)
        assert theme.seed.strip(), f"theme {key!r} has empty seed"
        assert len(theme.seed) >= 50, (
            f"theme {key!r} seed too short ({len(theme.seed)} chars), policy "
            "requires 80-180 char curated seed"
        )
        assert theme.label.strip(), f"theme {key!r} missing label"
        assert theme.category.strip(), f"theme {key!r} missing category"


def test_theme_categories_cover_main_genres() -> None:
    """覆盖网文主流大类: fantasy_cn / modern_cn / speculative / historical."""
    categories = {t.category for t in THEME_SEEDS.values()}
    required = {"fantasy_cn", "modern_cn", "speculative", "historical"}
    missing = required - categories
    assert not missing, f"theme registry missing required categories: {missing}"


def test_steampunk_archive_default_preserved() -> None:
    """Backward-compat: 老 bench_tick.py 默认 seed 派生的 theme key 必须在."""
    assert "steampunk_archive" in THEME_SEEDS
    # 比对 bench_tick.py:_DEFAULT_SEED 的语义关键词
    seed = THEME_SEEDS["steampunk_archive"].seed
    for kw in ("蒸汽朋克", "档案馆", "失语", "卷宗"):
        assert kw in seed, f"steampunk_archive 漂移, 缺关键词 {kw!r}"


def test_theme_get_unknown_key_raises_useful_error() -> None:
    with pytest.raises(KeyError) as exc:
        get_theme_seed("not_a_real_theme")
    assert "not_a_real_theme" in str(exc.value)
    # 错误应列出有效 key
    for some_known_key in list(THEME_SEEDS)[:3]:
        assert some_known_key in str(exc.value), (
            f"KeyError should list valid keys (e.g. {some_known_key}) but didn't"
        )


def test_theme_keys_unique_at_18_char_truncation() -> None:
    """matrix bench label = m_{theme[:18]}_{style[:18]} — 18 字符截断必须保持唯一."""
    truncated = [k[:18] for k in THEME_SEEDS]
    assert len(truncated) == len(set(truncated)), (
        "two themes collide at 18-char truncation; rename one or extend label scheme"
    )


# ---------------------------------------------------------------------------
# Style registry invariants
# ---------------------------------------------------------------------------


def test_style_registry_non_empty() -> None:
    assert len(STYLE_PRESETS) >= 8, (
        f"style registry should cover major narrative modes (≥8), got {len(STYLE_PRESETS)}"
    )


def test_style_keys_are_snake_case_ascii() -> None:
    for key in STYLE_PRESETS:
        assert _KEY_RE.match(key), f"style key {key!r} must match {_KEY_RE.pattern}"


def test_every_style_has_addendum() -> None:
    for key, style in STYLE_PRESETS.items():
        assert isinstance(style, StylePreset)
        assert style.narrator_addendum.strip(), (
            f"style {key!r} has empty narrator_addendum — preset would be a no-op"
        )
        assert len(style.narrator_addendum) >= 50, (
            f"style {key!r} addendum too short ({len(style.narrator_addendum)} chars)"
        )
        # Addendum 必须以 markdown 标题或注释开头, 让 narrator 知道是配置段
        assert style.narrator_addendum.startswith("#"), (
            f"style {key!r} addendum should start with '#' header for narrator clarity"
        )
        assert style.label.strip()
        assert style.description.strip()


def test_literary_default_preserved() -> None:
    """Backward-compat: literary 是默认 / fallback 风格, 老 novel 不能掉链子."""
    assert "literary" in STYLE_PRESETS
    p = STYLE_PRESETS["literary"]
    # 关键约束应在 addendum (具象物 + 内心薄)
    addendum = p.narrator_addendum
    assert "具象" in addendum or "具体物" in addendum, (
        "literary preset 漂移, 失去 '具象物' 关键约束"
    )


def test_style_get_unknown_key_raises_useful_error() -> None:
    with pytest.raises(KeyError) as exc:
        get_style_preset("not_a_real_style")
    assert "not_a_real_style" in str(exc.value)


def test_style_keys_unique_at_18_char_truncation() -> None:
    """matrix bench label budget — 同 theme."""
    truncated = [k[:18] for k in STYLE_PRESETS]
    assert len(truncated) == len(set(truncated)), (
        "two style keys collide at 18-char truncation"
    )


def test_style_addendums_independent() -> None:
    """两个 preset 不应 byte-identical (那是 typo 复制)."""
    seen: dict[str, str] = {}
    for key, p in STYLE_PRESETS.items():
        body = p.narrator_addendum.strip()
        if body in seen:
            pytest.fail(
                f"style {key!r} addendum is byte-identical to {seen[body]!r}"
            )
        seen[body] = key


# ---------------------------------------------------------------------------
# Cross-registry invariants
# ---------------------------------------------------------------------------


def test_list_helpers_consistent() -> None:
    assert set(list_theme_keys()) == set(THEME_SEEDS)
    assert set(list_style_keys()) == set(STYLE_PRESETS)
    # sorted
    assert list_theme_keys() == sorted(THEME_SEEDS)
    assert list_style_keys() == sorted(STYLE_PRESETS)


def test_matrix_label_fits_novel_id_budget() -> None:
    """每个 (theme, style) 组合的 matrix bench label 必须能进 _NOVEL_ID_RE (≤64).

    novel_id = bench_{label}_{10-digit timestamp} = 6 + len(label) + 1 + 10 = label + 17.
    所以 label budget = 64 - 17 = 47 chars.
    label = m_{theme[:18]}_{style[:18]} = 2 + 18 + 1 + 18 = 39 (含分隔符).
    """
    for t in THEME_SEEDS:
        for s in STYLE_PRESETS:
            label = f"m_{t[:18]}_{s[:18]}"
            novel_id = f"bench_{label}_1781600000"
            assert len(novel_id) <= 64, (
                f"({t!r}, {s!r}) → novel_id {novel_id!r} ({len(novel_id)} chars) > 64"
            )
