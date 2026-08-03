"""Compatibility entry for the current long-novel acceptance orchestrator."""

from __future__ import annotations

if __package__:
    from scripts.run_final_long_novel_acceptance import (
        _is_actionable_secret_finding,
        _overall_verdict,
        main,
    )
else:
    from run_final_long_novel_acceptance import (
        _is_actionable_secret_finding,
        _overall_verdict,
        main,
    )

__all__ = ["_is_actionable_secret_finding", "_overall_verdict", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
