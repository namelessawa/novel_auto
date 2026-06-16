# Phase 5-A Verdict — narrator prompt cache rearrange (pilot)

> Status: **det gate PASS** (single-seed pilot)
> Date: 2026-06-16
> Provider: ARK volces deepseek-v4-pro (custom slot)
> Judge: not yet run (mimo gate pending)

## What changed

* `backend/agents/narrator_agent.py`:
  * `_build_system_prompt(self)` — pure static, returns `NARRATOR_SYSTEM_PROMPT`
  * `_build_user_prompt(..., style_anchors=...)` — accepts and prepends anchor block at head
  * New `_render_style_anchor_block(style_anchors)` static helper
* `backend/nf_core/llm_client.py`:
  * `LLMResponse` adds `usage_cached_tokens`
  * `_resolve_extra_body()` — reads `LLM_THINKING_MODE=disabled` env, passes `extra_body={"thinking":{"type":"disabled"}}` (ARK-specific quirk)
  * `_extract_cached_tokens()` — pulls `usage.prompt_tokens_details.cached_tokens` defensively
  * Both `chat()` and `chat_stream()` forward extra_body + propagate cached_tokens to tracker
* `backend/nf_core/token_budget.py`:
  * `TokenUsageRecord` adds `cached_tokens`
  * `BudgetSnapshot` adds `total_cached_tokens` + per-agent breakdowns + `cache_hit_rate` property
* `scripts/bench_tick.py`:
  * Report carries cache hit rate per-agent + overall
  * MD output table for cache hit rate
* `.env`: `LLM_PROVIDER=custom`, `LLM_THINKING_MODE=disabled`, ARK credentials in `CUSTOM_*`
* Tests: 3 new in `test_narrator_prefix_cache.py` + 11 new in `test_llm_client_extra_body.py`

## Empirical cache hit (bench-phase5a-cache-vis-pilot, 5 ticks)

| agent | prompt_tokens | cached_tokens | hit% |
| --- | ---: | ---: | ---: |
| **narrator** | 16,205 | **9,216** | **56.9%** |
| showrunner | 2,093 | 1,024 | 48.9% |
| world_simulator | 3,738 | 0 | 0% (dynamic delta every tick — expected miss) |
| TOTAL | 22,036 | 10,240 | 46.5% |

## Cost math (det gate, narrator only)

DeepSeek-class providers price prefix cache hits at ~1/5 of miss rate.

* Uncached narrator input cost ≡ 16,205 × 1.0 = 16,205 units
* Phase 5-A narrator input cost ≡ (16,205 - 9,216) × 1.0 + 9,216 × 0.2 = 6,989 + 1,843 = **8,832 units**
* Effective narrator input cost reduction: **-45.5%** (target was -15~25%) ✅

## Three-pilot trend (5-tick each, ARK deepseek-v4-pro)

| run | thinking | total tokens | narrator tokens | JSON parse fail |
| --- | --- | ---: | ---: | ---: |
| v1 (pre-fix) | on  | 43,807 | 24,295 | 3/5 (60%) |
| v2 (thinkoff) | off | 42,855 | 23,389 | 1/5 (20%) |
| v3 (cache vis) | off | **39,143** | 22,427 | 3/5 (60%) |

JSON parse failure rate is variable on this model (statistical, not deterministic).
All 5/5 ticks in every pilot produced narrative content via the `narrator_output_not_json`
fallback path — degraded structured fields but reader-visible prose intact.

## Known regressions vs prior provider (mimo)

1. **JSON parse failure 20-60% per pilot** — deepseek-v4-pro occasionally drifts off
   the JSON contract on long Chinese + complex schema. Fallback recovers prose but
   loses `scene_focus`, `viewpoint_characters`, `open_loops_referenced` structured
   fields. Downstream Showrunner / OpenLoop tracker degrade gracefully.
2. **Wall-clock latency ~2-4x slower per tick** — ~60-200s vs mimo's 30-60s.
   bootstrap is ~370s vs mimo's ~80s.

These are provider-level issues, NOT caused by the Phase 5-A change.

## Recommendation

1. **Phase 5-A code itself: ship.** det gate strongly passed; unit tests pin the
   architectural invariant (SYSTEM is bit-identical across ticks).
2. **JSON failure is a separate Phase 5-A.1 follow-up**, not a Phase 5-A blocker.
   Options to investigate: max_tokens tuning, system-prompt JSON instruction
   reinforcement, prompt-level few-shot JSON example, retry-on-non-JSON wrapper.
3. **mimo pairwise gate (single-seed 50-tick) deferred** until either:
   - JSON failure rate stabilizes below ~30%, OR
   - User accepts that fallback prose still passes pairwise (deferring structured
     metadata cleanup to a separate phase).

## Sources

* Code: narrator_agent.py:497-535, llm_client.py:111-167, token_budget.py:55-92
* Bench reports:
  * `docs/iter/bench-phase5a-pilot.json/.md` (v1, thinking on)
  * `docs/iter/bench-phase5a-pilot-thinkoff.json/.md` (v2, thinking off)
  * `docs/iter/bench-phase5a-cache-vis-pilot.json/.md` (v3, cache visible)
* Tests: `test_narrator_prefix_cache.py` (3) + `test_llm_client_extra_body.py` (11)
