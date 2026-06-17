"""User-facing presets for novel generation.

* ``theme_seeds`` — registry of 主流网文 themes with curated bootstrap seeds.
* ``style_presets`` — registry of narrator style presets (爽文 / 描写细致 / 等).

These are pure data registries. Bootstrap CLI / matrix bench / future UI all
consume the same registry without re-defining lists. Adding a new theme or
style is a single-line addition to the registry dict.
"""

from __future__ import annotations

from .recommended_pairs import (
    avoid_pairs as recommended_avoid_pairs,
)
from .recommended_pairs import (
    is_available as recommended_pairs_available,
)
from .recommended_pairs import (
    perfect_pairs as recommended_perfect_pairs,
)
from .recommended_pairs import (
    style_universal_avg as recommended_style_universal_avg,
)
from .recommended_pairs import (
    to_api_payload as recommended_pairs_api_payload,
)
from .recommended_pairs import (
    top_styles_for_theme,
)
from .style_presets import (
    STYLE_PRESETS,
    StylePreset,
    get_style_preset,
    list_style_keys,
)
from .theme_seeds import (
    THEME_SEEDS,
    ThemeSeed,
    get_theme_seed,
    list_theme_keys,
)

__all__ = [
    "STYLE_PRESETS",
    "StylePreset",
    "get_style_preset",
    "list_style_keys",
    "THEME_SEEDS",
    "ThemeSeed",
    "get_theme_seed",
    "list_theme_keys",
    "recommended_avoid_pairs",
    "recommended_pairs_available",
    "recommended_perfect_pairs",
    "recommended_style_universal_avg",
    "recommended_pairs_api_payload",
    "top_styles_for_theme",
]
