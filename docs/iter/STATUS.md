# Cost-Quality-Loop Status (final)

**Branch:** `iter/cost-quality-loop`
**Range:** baseline 16d5826 → HEAD
**Last update:** 2026-06-11

## Headline

| metric | value |
| ------ | ----- |
| Iterations applied | 47 (iter#3-#47, doc/test iter included) |
| Code review cycles | 9 |
| Commits on branch | 55+ |
| Files touched (active LLM paths) | 15 (every agent + bootstrap) |
| Tests passing | 578/578 |
| Bench artifacts | 19 paired (json+md) under `docs/iter/` |

## Cumulative gains vs v0-baseline

| metric                       | v0      | best stable (v15) | best (v16) |
| ---------------------------- | ------: | ----------------: | ---------: |
| total tokens (3 tick + boot) | 137,890 |            31,214 |     19,287 |
| critic chain                 |  65,174 |             7,878 |          0 |
| world_simulator              |  19,427 |             7,152 |      8,305 |
| narrator                     |  19,904 |            16,184 |     10,982 |
| bootstrap_sec                |     501 |               306 |        305 |
| avg tick duration (sec)      |     556 |                91 |         68 |

* **Best stable result: -77% total tokens, -83% tick latency.**
* Quality samples preserved across all benches (see CHANGELOG + ITERATION_LOG.md for excerpts).

## Surface coverage

Every active LLM call site touched:

| agent / module                       | system prompt | user prompt | max_tokens | other |
| ------------------------------------ | :-----------: | :---------: | :--------: | :---: |
| narrator_agent                       | ✓             | ✓           | ✓ (per length tier) | + critic length-gate, schema placeholder detect, reasoning leak filter |
| narrative_critic (critique/revise/rewrite) | ✓       | ✓           | ✓          | + LLM gating, B-G semantic block, blacklist removal |
| world_simulator                      | ✓             | ✓           | ✓          | + delta-output, importance-weighted events |
| character_agent                      | ✓             | ✓           | ✓ (tier)   | + str fallback in goals/loops |
| event_injector                       | ✓             | ✓           | ✓          | + str fallback in events |
| showrunner                           | ✓             | ✓           | ✓          | |
| novelty_critic                       | ✓             | ✓           | ✓          | |
| story_arc_director                   | (already tight) | ✓         | (already tight) | |
| character_arc_tracker                | (already tight) | ✓         | ✓          | |
| memory_compressor (L0→L1, L1→L2)     | (already tight) | ✓         | ✓ (+ length guard) | |
| summary_tree (legendize / volume / root) | -        | -           | ✓          | + output length guard |
| bootstrap_prompts (world/char/loop/style) | ✓ (mostly) | ✓        | ✓          | + str fallback, placeholder safety |
| reasoning_filter                     | -             | -           | -          | + Chinese/English markers, high-confidence signals |

## Patterns applied

1. **max_tokens 合理化** — every call rebound to its actual output size
2. **JSON delta output** — partial state vs full reflection (WorldSimulator)
3. **占位符自描述化 + 检测** — `<placeholder>` over realistic-looking examples
4. **Det + LLM 分工** — A-class structural triggers stay in det layer
5. **Length-gating + round capping** — short narratives skip critic; MAX_TOTAL_ROUNDS=1 default
6. **JSON indent strip** — LLM-facing only; persistence keeps indented
7. **反 reasoning 多层防线** — prompt禁区 + filter markers + high-confidence signals + parse-fallback scan
8. **Lazy config read** — env-driven knobs via function call, not module constant

## Env tuning knobs

See `CLAUDE.md` "Token 预算调参 env vars" section.

## Reproducing

See `scripts/bench_tick.py` docstring.

## Trail

* CHANGELOG.md — every iter entry
* docs/iter/ITERATION_LOG.md — narrative summary of all 34 iter + reviews
* docs/iter/bench-v0..v16-*.{json,md} — raw bench data
* CLAUDE.md — env tuning table

## Status

cost-quality-loop work continues at user's directive (rule #3: no stop until user says stop). Saturation of optimizable surfaces reached around iter#34; subsequent iterations focus on code hygiene (dead imports, isinstance guards, docs/tests).
