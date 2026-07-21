"""Validate human review files and merge partial StateGuard submissions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.state_guard_review_workflow import (  # noqa: E402
    atomic_write_json,
    import_human_review,
    merge_review_parts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    importer = commands.add_parser("import", help="validate a filled CSV/JSON file")
    importer.add_argument("package_dir")
    importer.add_argument("--input", required=True)
    importer.add_argument("--allow-partial", action="store_true")
    importer.add_argument("--review-started-at")
    importer.add_argument("--review-finished-at")
    importer.add_argument("--out-part", required=True)

    merger = commands.add_parser("merge", help="merge non-overlapping reviewer parts")
    merger.add_argument("packet")
    merger.add_argument("parts", nargs="+")
    merger.add_argument("--out-review", required=True)
    merger.add_argument("--out-coverage", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "import":
        part = import_human_review(
            Path(args.package_dir).resolve(),
            Path(args.input).resolve(),
            allow_partial=args.allow_partial,
            review_started_at=args.review_started_at,
            review_finished_at=args.review_finished_at,
        )
        atomic_write_json(Path(args.out_part).resolve(), part)
        print(
            json.dumps(
                {
                    "reviewer_id": part["reviewer_id"],
                    "reviewer_type": part["reviewer_type"],
                    "case_count": len(part["results"]),
                    "part_id": part["part_id"],
                    "provider_calls": 0,
                },
                ensure_ascii=False,
            )
        )
        return 0
    merged, coverage = merge_review_parts(
        Path(args.packet).resolve(),
        [Path(value).resolve() for value in args.parts],
    )
    atomic_write_json(Path(args.out_review).resolve(), merged)
    atomic_write_json(Path(args.out_coverage).resolve(), coverage)
    print(json.dumps(coverage, ensure_ascii=False))
    return 0 if coverage["valid_for_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
