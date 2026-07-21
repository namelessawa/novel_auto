"""Read-only CanonicalFact reconciliation CLI (writes report only)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for entry in (str(BACKEND), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from memory.tick_state import TickState  # noqa: E402
from narrative.canonical_facts import CanonicalFactStore  # noqa: E402
from narrative.canonical_reconciliation import reconcile_all  # noqa: E402
from narrative.fact_ledger import FactLedger  # noqa: E402


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp.json", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare canonical_facts.json with TickState, FactLedger, KG and "
            "continuity_state without modifying any source view."
        )
    )
    parser.add_argument("data_dir", help="Per-novel data directory")
    parser.add_argument(
        "--out",
        default="",
        help="Output JSON path (default: <data_dir>/canonical_reconciliation.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_dir = Path(args.data_dir).resolve()
    if not data_dir.is_dir():
        print(f"data directory not found: {data_dir}", file=sys.stderr)
        return 2

    store = CanonicalFactStore(str(data_dir))
    if not store.load():
        print("canonical_facts.json missing or invalid", file=sys.stderr)
        return 2
    tick_state = TickState(str(data_dir))
    if not tick_state.load():
        print("tick_state.json missing or invalid", file=sys.stderr)
        return 2
    ledger = FactLedger(str(data_dir))
    ledger.load()
    graph = _load_json(data_dir / "knowledge_graph.json")
    report = reconcile_all(
        store,
        character_states=tick_state.list_character_states(),
        legacy_facts=ledger.active_facts(),
        knowledge_graph=graph,
        continuity_state=tick_state.get_narrative_continuity_state(),
    ).to_dict()
    report.update(
        {
            "schema_version": 1,
            "data_dir_name": data_dir.name,
            "canonical_fact_count": store.size,
        }
    )
    out_path = (
        Path(args.out).resolve()
        if args.out
        else data_dir / "canonical_reconciliation.json"
    )
    _atomic_write_json(out_path, report)
    print(
        json.dumps(
            {
                "out": str(out_path),
                "checked": report["checked"],
                "issues": report["issue_count"],
                "hard_conflicts": report["hard_conflict_count"],
                "coverage_gaps": report["coverage_gap_count"],
            },
            ensure_ascii=False,
        )
    )
    return 1 if report["hard_conflict_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

