"""compare_novels - 对两个 novel 数据目录做横向对比验证。

用法:
    python tools/compare_novels.py test_story_A test_story_B

输出:
* character_isolation: 两个故事角色 id / known_facts 是否完全不交叉
* world_isolation: 世界 era / locations / factions 是否独立
* style_distinction: style_anchors / narratives 词汇主题应明显不同
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_BACKEND = os.path.join(_ROOT, "backend")
for p in (_ROOT, _BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

from memory.tick_state import TickState


def _load(novel_id: str) -> TickState:
    data_dir = os.path.join(_BACKEND, "data", "novels", novel_id)
    ts = TickState(data_dir=data_dir)
    ts.load()
    return ts


def _collect_narrative_keywords(novel_id: str, top_n: int = 30) -> list[tuple[str, int]]:
    """Return top-N 2-gram keywords from this novel's narratives.

    Coarse but effective: zh tokens are dense, so 2-char windows surface theme
    words like 灯塔/迷雾 vs 霓虹/记忆.
    """
    nar_dir = Path(_BACKEND) / "data" / "novels" / novel_id / "narratives"
    if not nar_dir.is_dir():
        return []
    counter: Counter[str] = Counter()
    for f in sorted(nar_dir.glob("tick_*.txt")):
        text = f.read_text(encoding="utf-8")
        # Filter only CJK chars then 2-gram window
        cjk = re.findall(r"[一-鿿]+", text)
        for run in cjk:
            for i in range(len(run) - 1):
                counter[run[i : i + 2]] += 1
    # filter out trivial common Chinese particles
    junk = {"的他", "是一", "是个", "一个", "一种", "一只", "一直", "他的", "她的", "在他", "在她"}
    return [(w, c) for w, c in counter.most_common(top_n * 3) if w not in junk][:top_n]


def compare(a_id: str, b_id: str) -> dict:
    a = _load(a_id)
    b = _load(b_id)

    a_profiles = {p.id for p in a.list_character_profiles()}
    b_profiles = {p.id for p in b.list_character_profiles()}
    a_facts: set[str] = set()
    b_facts: set[str] = set()
    for p in a.list_character_profiles():
        st = a.get_character_state(p.id)
        if st:
            a_facts.update(st.known_facts)
    for p in b.list_character_profiles():
        st = b.get_character_state(p.id)
        if st:
            b_facts.update(st.known_facts)

    a_kw = dict(_collect_narrative_keywords(a_id))
    b_kw = dict(_collect_narrative_keywords(b_id))
    overlap_kw = set(a_kw) & set(b_kw)
    distinct_a = sorted(set(a_kw) - set(b_kw), key=lambda k: -a_kw[k])[:15]
    distinct_b = sorted(set(b_kw) - set(a_kw), key=lambda k: -b_kw[k])[:15]

    return {
        "novel_a": a_id,
        "novel_b": b_id,
        "character_isolation": {
            "a_profile_count": len(a_profiles),
            "b_profile_count": len(b_profiles),
            "shared_profile_ids": sorted(a_profiles & b_profiles),
            "isolated": len(a_profiles & b_profiles) == 0,
            "a_facts_count": len(a_facts),
            "b_facts_count": len(b_facts),
            "shared_facts_count": len(a_facts & b_facts),
        },
        "world_isolation": {
            "a_era": a.world_state.era,
            "b_era": b.world_state.era,
            "a_locations": [l.name for l in a.world_state.locations],
            "b_locations": [l.name for l in b.world_state.locations],
            "a_factions": [f.name for f in a.world_state.factions],
            "b_factions": [f.name for f in b.world_state.factions],
            "shared_location_names": sorted(
                {l.name for l in a.world_state.locations}
                & {l.name for l in b.world_state.locations}
            ),
            "shared_faction_names": sorted(
                {f.name for f in a.world_state.factions}
                & {f.name for f in b.world_state.factions}
            ),
        },
        "style_distinction": {
            "a_anchor_scenes": [
                (anc.scene_type, anc.weight) for anc in a.list_style_anchors()
            ],
            "b_anchor_scenes": [
                (anc.scene_type, anc.weight) for anc in b.list_style_anchors()
            ],
            "a_top_keywords": sorted(a_kw.items(), key=lambda x: -x[1])[:15],
            "b_top_keywords": sorted(b_kw.items(), key=lambda x: -x[1])[:15],
            "shared_top_keyword_count": len(overlap_kw),
            "a_distinct_keywords": distinct_a,
            "b_distinct_keywords": distinct_b,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("a")
    parser.add_argument("b")
    args = parser.parse_args(argv)
    report = compare(args.a, args.b)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
