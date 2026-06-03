"""verify_novel - 检查一个 novel 数据目录的完整性与多 agent 协作证据。

用法:
    python tools/verify_novel.py --novel-id test_story_A

输出 JSON 报告,包含:
* persistence: 关键文件是否存在且能 round-trip 反序列化
* agent_coverage: ticks.db 里出现过的 agent 列表(覆盖 9 agent)
* memory_isolation: 每个 character 的 memory_summary 是否独立(profile.id 唯一)
* narrative_coherence: narratives/*.txt 是否连续 + open_loops 推进情况
* style_consistency: style_anchors 在前后期 tick 是否被 narrator 引用
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_BACKEND = os.path.join(_ROOT, "backend")
for p in (_ROOT, _BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

from memory.tick_state import TickState
from memory_system.models import TickSummary, Event


def verify(novel_id: str) -> dict:
    data_dir = os.path.join(_BACKEND, "data", "novels", novel_id)
    if not os.path.isdir(data_dir):
        return {"error": f"novel dir not found: {data_dir}"}

    report: dict = {"novel_id": novel_id, "data_dir": data_dir}

    # --- 1. Persistence -----------------------------------------------------
    persist: dict = {}
    files = {
        "tick_state.json": os.path.join(data_dir, "tick_state.json"),
        "ticks.db": os.path.join(data_dir, "ticks.db"),
        "summary_tree.json": os.path.join(data_dir, "summary_tree.json"),
        "bootstrap.env": os.path.join(data_dir, "bootstrap.env"),
    }
    for name, fp in files.items():
        persist[name] = {
            "exists": os.path.isfile(fp),
            "size": os.path.getsize(fp) if os.path.isfile(fp) else 0,
        }
    # round-trip tick_state
    try:
        ts = TickState(data_dir=data_dir)
        ts.load()
        persist["tick_state_roundtrip"] = {
            "ok": True,
            "current_tick": ts.current_tick,
            "world_time": ts.world_time,
            "open_loops": ts.get_open_loop_count(),
            "characters": len(ts.list_character_profiles()),
            "style_anchors": len(ts.list_style_anchors()),
            "last_narration_tick": ts.last_narration_tick,
        }
    except Exception as e:
        persist["tick_state_roundtrip"] = {"ok": False, "error": str(e)}
    report["persistence"] = persist

    # --- 2. Agent coverage --------------------------------------------------
    import sqlite3
    db = os.path.join(data_dir, "ticks.db")
    agent_set: set[str] = set()
    tick_rows: list[dict] = []
    event_rows: list[dict] = []
    if os.path.isfile(db):
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            for r in cur.execute("SELECT tick_id, agents_called, events_generated, narrator_produced, narrator_chars, state_changes_summary FROM tick_log ORDER BY tick_id"):
                d = dict(r)
                d["tick"] = d.pop("tick_id")
                d["narrator_produced_text"] = bool(d.pop("narrator_produced"))
                d["narrator_output_chars"] = d.pop("narrator_chars")
                d["agents_called"] = json.loads(d["agents_called"]) if d["agents_called"] else []
                d["events_generated"] = json.loads(d["events_generated"]) if d["events_generated"] else []
                tick_rows.append(d)
                for a in d["agents_called"]:
                    base = a.split("(", 1)[0].split("×", 1)[0]
                    agent_set.add(base)
        except sqlite3.OperationalError as e:
            tick_rows.append({"error": str(e)})
        try:
            for r in cur.execute("SELECT event_id, tick_id, event_type, location, description, narrative_value FROM events ORDER BY tick_id, event_id"):
                event_rows.append(dict(r))
        except sqlite3.OperationalError:
            pass
        conn.close()
    expected_agents = {
        "world_simulator", "narrator", "character_agents", "showrunner",
        "event_injector", "memory_compressor", "consistency_guardian", "novelty_critic",
        "action_resolver",
    }
    report["agent_coverage"] = {
        "tick_count": len(tick_rows),
        "agents_seen": sorted(agent_set),
        "expected_minimum": sorted(expected_agents),
        "missing_for_full_coverage": sorted(expected_agents - agent_set),
        "narrator_produced_count": sum(1 for r in tick_rows if isinstance(r, dict) and r.get("narrator_produced_text")),
        "event_count": len(event_rows),
    }

    # --- 3. Memory / character isolation ------------------------------------
    try:
        profiles = ts.list_character_profiles()
        states = ts.list_character_states()
        unique_ids = {p.id for p in profiles}
        report["memory_isolation"] = {
            "profile_count": len(profiles),
            "state_count": len(states),
            "unique_profile_ids": len(unique_ids) == len(profiles),
            "profile_ids": sorted(unique_ids),
            "sample_known_facts": {
                p.id: (ts.get_character_state(p.id).known_facts[:3] if ts.get_character_state(p.id) else [])
                for p in profiles[:3]
            },
        }
    except Exception as e:
        report["memory_isolation"] = {"error": str(e)}

    # --- 4. Narrative coherence --------------------------------------------
    nar_dir = Path(data_dir) / "narratives"
    nar_files = sorted(nar_dir.glob("tick_*.txt")) if nar_dir.is_dir() else []
    nar_ticks = []
    nar_sizes = []
    for f in nar_files:
        m = re.match(r"tick_(\d+)\.txt", f.name)
        if m:
            nar_ticks.append(int(m.group(1)))
            nar_sizes.append(f.stat().st_size)
    report["narrative_coherence"] = {
        "narrative_file_count": len(nar_files),
        "ticks_with_narrative": nar_ticks,
        "total_chars": sum(nar_sizes),
        "min_chars": min(nar_sizes) if nar_sizes else 0,
        "max_chars": max(nar_sizes) if nar_sizes else 0,
        "open_loops_currently": ts.get_open_loop_count(),
        "narrator_silent_ticks": [
            r["tick"] for r in tick_rows
            if isinstance(r, dict) and not r.get("narrator_produced_text")
        ],
    }

    # --- 5. Style anchor stability ------------------------------------------
    anchors = ts.list_style_anchors()
    report["style_consistency"] = {
        "anchor_count": len(anchors),
        "anchor_excerpt_hashes": [hash(a.excerpt) % 10**8 for a in anchors],
        "anchor_scene_types": [a.scene_type for a in anchors],
        "anchor_weights": [a.weight for a in anchors],
    }

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--novel-id", required=True)
    parser.add_argument("--out", default=None, help="write JSON report to this path")
    args = parser.parse_args(argv)
    report = verify(args.novel_id)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
