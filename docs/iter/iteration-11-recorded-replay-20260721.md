# Iteration 11 — recorded response and Phase 7 guard replay

- iteration_id: `20260721-11-recorded-replay`
- date: `2026-07-21`
- base_git_sha: `a786db0`
- candidate_git_sha: `48e20a9`

```text
Iteration: 11
Observation:
Iteration 10 routes external JSON responses but labels the only CLI mode `mock`.
Phase 7 has 56 complete guard decision traces but does not retain full rejected
Narrator/repair prose.

Root cause:
Recorded transport provenance and evidence completeness are not explicit, and there
is no converter/replayer for the existing Phase 7 guard traces.

Primary hypothesis:
An explicit recorded mode plus a loss-aware Phase 7 decision-trace conversion can
replay all available evidence at zero model cost without pretending missing payloads
exist.

Single behavioral change:
None in production. Add recorded fixture mode and guard-decision replay tooling.

Measurement-only changes:
Stable evidence hash; response completeness fields; source artifact hashes; exact
reproduction of final recorded decisions; completed-checkpoint resume validation.

Expected benefit:
New full-runtime recorded fixtures become byte-comparable at the evidence layer, and
all 56 Phase 7 Tick decisions become usable by the later calibration set.

Safety risk:
Decision replay could be mislabeled as full-response replay or silently infer absent
drafts, repairs or ground truth.

Cost estimate:
0 real-model tokens.

Validation:
Recorded mode twice with equal evidence hash; source converter emits 56 unique cases;
all recorded final decisions reproduce; completeness flags identify all missing
rejected drafts; full backend suite.

Rollback condition:
Any invented prose/response, lost source hash, non-reproducible evidence, unexpected
provider call, or production behavior change.
```

## Result

- verdict: `ACCEPT_MEASUREMENT`
- production_behavior_changed: `false`
- real_llm_calls: `0`
- provider_tokens: `0`
- files_changed:
  - `scripts/replay_runtime_sequence.py`
  - `scripts/convert_phase7_guard_replays.py`
  - `backend/tests/test_runtime_replay.py`
  - `backend/tests/test_phase7_guard_replay_conversion.py`
  - `docs/iter/phase8-runtime-replay-recorded-20260721.json`
  - `docs/iter/phase8-phase7-guard-recorded-v1.json`
- tests_added: 5
- tests:
  - focused: `9 passed`
  - backend full: `1263 passed, 1 existing warning`

Recorded runtime evidence:

- Mode: `recorded`; response provenance: `synthetic`.
- Full-runtime expectations: passed; fixture transport calls: 6; provider calls: 0.
- Stable evidence SHA-256:
  `616e89687d4d164434f1e399500433cff0a796fd999a2fafc94c8ea49c599fa2`.
- A second independent run produced the same evidence hash.
- `--resume` validated and reused the completed checkpoint without creating a new
  work directory. Resume support is deliberately limited to completed checkpoints;
  partial multi-Tick resume is not claimed.

Phase 7 recorded guard conversion:

- Source SHA-256 values:
  - run 1: `cdc088f57d9e984caea279ea2e6d4a4ca0eaffc6fbe24d2ccaa7f8bed777317a`
  - run 2: `58a6a8ecee0e102e5b596956b651b7d355ccc37e2ffcf5927742d1483c50b9a7`
- 56 unique cases converted; 20 recorded accepts and 36 recorded rejects.
- 56/56 final decisions reproduced from trace state and persistence outcome.
- Cases SHA-256:
  `529f42977b2cb7f39f480a48d42d84bc5a987a966c8263b139a0e4a6171cf8c2`.
- Accepted full text exists in the source for 20 cases but is not duplicated into
  the conversion artifact. Rejected draft availability is 0/36. Complete repair
  prose availability is 0/56. Verifier payloads and bounded evidence excerpts are
  retained.
- All 56 cases remain `unreviewed`; recorded production decisions are not treated
  as human ground truth.

Acceptance reason:

The measurement path is reproducible, zero-cost and loss-aware. It changes no
StateGuard threshold or production acceptance behavior and preserves the exact
boundary between available evidence and absent response bodies. The converted set
may enter manual double-labeling, but it cannot support a full-response quality
claim.
