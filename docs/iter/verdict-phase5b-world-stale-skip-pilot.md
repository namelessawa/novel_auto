# Phase 5-B Verdict — world_simulator stale-skip (pilot)

> Status: **det gate PASS — but dial set aggressively**
> Date: 2026-06-16
> Provider: ARK volces deepseek-v4-pro (custom)
> Judge: not yet run (mimo gate pending)

## What changed

* `backend/nf_core/world_stale_detector.py` (new):
  * Pure det-layer predicate, no LLM, no IO.
  * `evaluate_stale(current_world_time, last_llm_world_time, last_tick_events, ...)`
    returns `StaleDecision(should_skip, reason)`.
  * Skip when all of: not cold-start, ticks_since_llm < `WORLD_STALE_MAX_SKIP` (default 3),
    max `narrative_value` < `WORLD_STALE_VALUE_CAP` (default 5), no event with
    `type='dramatic'`.
* `backend/agents/world_simulator.py`:
  * `simulate()` calls `evaluate_stale()` first. Stale → `_stale_output(...)` returns
    zero-delta WorldState + 1 stale natural event (value=1) + skipped_llm=True.
  * `_last_llm_world_time` tracked on instance — updated only when LLM actually ran.
  * `WorldSimulatorOutput` adds `skipped_llm: bool` + `skip_reason: str`.
  * `_stale_skip_enabled()` reads `WORLD_STALE_SKIP_ENABLED` env (default ON).
* Tests:
  * `test_world_stale_detector.py` (new, 13 cases covering all boundary conditions)
  * `test_orchestrator_close_loops.py` — 2 tests fixed (env-disable stale-skip since
    they rely on fixed mock_llm response queue alignment)
  * `test_sideline_runtime_cap.py` — 2 tests fixed (same reason)

## Empirical (bench-phase5b-stale-skip-pilot, 5 ticks)

| metric | Phase 5-A baseline | Phase 5-B | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 39,143 | **17,967** | **-54.1%** |
| narrator tokens | 22,427 | 8,833 | -60.6% |
| world_simulator tokens | 11,551 | 4,333 | -62.5% |
| call_count | 11 | 5 | -54.5% |
| narrative_chars_total | 3,272 | **791** | **-75.8%** |
| silent ticks | 0/5 | **3/5** | +60pp |

### Per-tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6,722 | 78.6 | 321 | narrator + world_sim (cold start) |
| 2 | 0 | 0.05 | 0 | **stale-skip → entire chain frozen** |
| 3 | 0 | 0.05 | 0 | **stale-skip → entire chain frozen** |
| 4 | 6,444 | 71.3 | 470 | force-refresh triggered (ticks_since_llm=3) |
| 5 | 4,801 | 62.5 | 0 | showrunner only (cadence=5), narrator silent |

## Gate evaluation

| PHASE5_PLAN target | actual | verdict |
| --- | --- | --- |
| skip rate 30-50% | 40% (2/5 world_sim ticks) | ✓ in range |
| world_sim cost -15~25% | -62.5% | ✓ exceeded (far) |
| total cost -5~8% | -54.1% | ✓✓ exceeded (one order of magnitude) |

## Concern — Stale-skip cascade effect

A stale tick triggers a chain reaction beyond just world_simulator:

1. world_sim emits 1 `stale_event` with `narrative_value=1`
2. EventInjector cadence permits skip (no high-value events to chain off)
3. CharacterAgent batch_decide skips (no actionable events for any character)
4. Narrator sees `total_score < NARRATE_SKIP_THRESHOLD` → silent
5. Entire tick produces 0 LLM calls + 0 narrative content

This IS the documented design philosophy (CLAUDE.md: "Narrator 沉默 - 事件总价值 < 5
时 Narrator 跳过 — 这是 feature, 不是 bug"). But Phase 5-B amplifies it from
"occasional silence" to "60% of ticks silent" in the test seed.

## Tuning knobs (env)

* `WORLD_STALE_SKIP_ENABLED=0` — disable Phase 5-B entirely (rollback escape)
* `WORLD_STALE_MAX_SKIP=2` — force LLM every 2 ticks instead of 3 (less aggressive)
* `WORLD_STALE_MAX_SKIP=5` — allow 4 consecutive skips (more aggressive)
* `WORLD_STALE_VALUE_CAP=3` — make narrative_value >= 3 already block skip (sensitive)

## Recommendations

1. **Code itself: ship** — det gate passed, architecture sound, knobs in place.
2. **Mimo pairwise gate REQUIRED before promoting** — PHASE5_PLAN.md mandates
   `mandatory cross-seed ×3` for architectural changes. The 60% silent-tick rate
   could either be:
   - **Good** (world really is static at low event density, Phase 5-B saves wasted LLM calls
     in plot-light passages while preserving narrator quality at active beats), OR
   - **Bad** (long stretches of nothing read like a dead chapter — judge will catch this).
3. **Consider tuning** before judging:
   - If pilot seed is plot-dense the silence is suspicious — try `WORLD_STALE_MAX_SKIP=2`
   - If pilot seed is plot-light the silence is expected — keep default
4. **Long-range stress (PHASE5_PLAN candidate J)** — 100+ tick run is essential
   to verify stale accumulation doesn't drift the world state away from coherence.

## Sources

* Code: world_stale_detector.py (new), world_simulator.py:80-160 (updated)
* Bench reports:
  * `docs/iter/bench-phase5a-cache-vis-pilot.md` (Phase 5-A baseline)
  * `docs/iter/bench-phase5b-stale-skip-pilot.json/.md` (this pilot)
* Tests: `test_world_stale_detector.py` (13 cases)
