"""Compute the Phase 11 independent-review Gate and freeze gold artifacts."""

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
    build_partial_review_gate,
    freeze_file,
    load_blind_packet,
    validate_hashed_payload,
)


def _load_review(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hard_contradiction_ids(key_path: Path | None) -> set[str]:
    if key_path is None:
        return set()
    key = json.loads(key_path.read_text(encoding="utf-8"))
    validate_hashed_payload(key, "key_sha256", "adjudication key")
    # This optional audit is legal only after reviewer files are frozen.  The key
    # never enters a reviewer task, prompt, human package or disagreement packet.
    return {
        row["case_id"]
        for row in key.get("cases") or []
        if row.get("expected_final_decision") == "reject"
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet")
    parser.add_argument("review_a")
    parser.add_argument("review_b")
    parser.add_argument("--adjudicator-review")
    parser.add_argument(
        "--audit-key",
        help="optional post-freeze hard-contradiction audit; never sent to reviewers",
    )
    parser.add_argument("--out-report", required=True)
    parser.add_argument("--out-disagreement", required=True)
    parser.add_argument("--out-gold", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    packet = load_blind_packet(Path(args.packet).resolve())
    reviews = [
        _load_review(Path(args.review_a).resolve()),
        _load_review(Path(args.review_b).resolve()),
    ]
    adjudicator = (
        _load_review(Path(args.adjudicator_review).resolve())
        if args.adjudicator_review
        else None
    )
    # Validate and freeze both reviewer inputs before the optional audit key is
    # opened.  A malformed/incomplete reviewer pair must never trigger key access.
    report, disagreement, gold = build_partial_review_gate(
        packet,
        reviews,
        adjudicator=adjudicator,
    )
    if args.audit_key:
        report, disagreement, gold = build_partial_review_gate(
            packet,
            reviews,
            adjudicator=adjudicator,
            hard_contradiction_case_ids=_hard_contradiction_ids(
                Path(args.audit_key).resolve()
            ),
        )
    atomic_write_json(Path(args.out_report).resolve(), report)
    atomic_write_json(Path(args.out_disagreement).resolve(), disagreement)
    # Only a passing Gate freezes gold.  A failed Gate leaves room for a blind
    # third-party adjudication instead of immutably freezing provisional labels.
    if report["review_gate"]["passed"]:
        freeze_file(Path(args.out_gold).resolve(), gold)
    print(
        json.dumps(
            {
                "review_gate": report["review_gate"]["decision"],
                "overlap": report["overlap"],
                "decisive": report["gold_summary"]["decisive"],
                "accepts": report["gold_summary"]["accepts"],
                "rejects": report["gold_summary"]["rejects"],
                "raw_agreement": report["raw_agreement"],
                "cohens_kappa": report["cohens_kappa"],
                "gold_sha256": gold["gold_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["review_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
