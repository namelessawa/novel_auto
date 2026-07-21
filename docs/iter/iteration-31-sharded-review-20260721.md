# Iteration 31 — deterministic sharded review tasks

```text
Iteration: 31
Evidence gap:
Phase 10 required one 25-case response, so malformed output invalidated the entire
review and completed cases had no addressable checkpoint.

Hypothesis:
Stable opaque tasks containing 1–3 cases can isolate failure and preserve the blind
packet boundary.

Single primary change:
Add a versioned task/index contract with stable partition, task ID, input hash and
per-case status. Default batch size is one; values above three are rejected.

Provider calls allowed: no
Authorized budget: 0
Expected benefit: local failure and deterministic resume identity
Safety risk: case order or task metadata could leak labels
Validation: stable hashes across creation times, batch sizes 1/2/3, recursive leak scan
Rollback condition: unstable partition, label leak or task evidence loss
```

## Result

- Tests: task split produces 25/13/9 tasks for batch size 1/2/3.
- Prepared review tasks: 25 single-case tasks.
- Definition SHA-256:
  `97fa6e01c2a10636f3a667a0526c1e147f0f06493238cd0010ccc902daafa140`.
- Review tasks complete/invalid/human/model: 0 / 0 / 0 / 0.
- Provider calls / known tokens / uncertain upper bound: 0 / 0 / 0.
- Decision: `ACCEPT_INFRASTRUCTURE`.
- Rollback: not required.
