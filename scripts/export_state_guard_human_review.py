"""Export a label-blind Markdown/CSV/JSON package for one human reviewer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.state_guard_review_workflow import export_human_review_package  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", help="label-blind packet JSON")
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--shuffle-seed", type=int, default=0)
    parser.add_argument("--out-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = export_human_review_package(
        Path(args.packet).resolve(),
        Path(args.out_dir).resolve(),
        reviewer_id=args.reviewer_id,
        shuffle_seed=args.shuffle_seed,
    )
    print(
        json.dumps(
            {
                "reviewer_id": manifest["reviewer_id"],
                "reviewer_type": "human",
                "case_count": manifest["case_count"],
                "packet_hash": manifest["packet_hash"],
                "manifest_sha256": manifest["manifest_sha256"],
                "labels_exposed": False,
                "provider_calls": 0,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
