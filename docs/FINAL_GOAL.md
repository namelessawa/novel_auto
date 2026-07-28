# Novel Auto final goal

The final-goal work makes Author mode a fail-closed, auditable long-form
generation system. The formal path is:

```text
Frozen Authority Context
  -> Deterministic SectionExecutionSpec / ChapterPlan
  -> one Writer call
  -> deterministic validation
  -> at most one bounded local Repair
  -> complete revalidation
  -> RevisionGuard
  -> atomic commit
```

The default path never calls an LLM Planner and never performs a full-section
Writer Retry. `ChapterPlan` remains a persisted, validated diagnostic contract.
Simulation remains an explicit experimental mode and cannot bypass the same
authority and transaction boundary.

## Delivered scope

- auditable `ContextManifest` with revision, selection, discard, budget and
  execution-spec evidence;
- revision-aware semantic memory retrieval and seven semantic-use probes;
- deterministic StoryThread liveness and main-line progress requirements;
- one local Patch Repair followed by complete narrative/authority revalidation;
- atomic transaction recovery, stale-context rejection and revision guards;
- an Author evidence ledger, allowlisted recovery APIs and committed-only
  manuscript/evidence exports;
- a unified fail-closed acceptance runner with machine results, hashes, secret
  scan and recovery instructions.

## Final execution status

P0 through P5 passed. P6 did not pass its historical seed after the maximum two
allowed repair rounds. The final attempt completed the required event and end
state but produced a 656-character draft against the frozen 900-character
minimum; its only Repair used a non-existent anchor. The candidate was correctly
rejected and no fact, state, thread or transaction corruption was committed.

Therefore this execution is `NOVEL_AUTO_FINAL_FAIL`. P7, P8 and human review
were not entered. This is a quality-gate failure, not a provider-budget block,
and the Validator was not weakened.
