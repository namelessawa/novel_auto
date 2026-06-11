# Long-range analysis — stage3-50tick

- source: `bench_stage3-longrange-50tick_1781155934`
- ticks: 50, narrations: 42
- total_tokens: 509417

## Foreshadowing curve

- samples: 10
- open/closed ratio at end: 9.0
- stale ratio at end: 0.3333

| tick | open | stale | closed | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 5 | 0 | 0 | 7.0 |
| 10 | 6 | 0 | 0 | 6.67 |
| 15 | 7 | 0 | 0 | 6.43 |
| 20 | 8 | 0 | 0 | 6.25 |
| 25 | 8 | 2 | 0 | 6.25 |
| 30 | 8 | 1 | 0 | 6.25 |
| 35 | 8 | 2 | 0 | 6.25 |
| 40 | 9 | 3 | 0 | 6.11 |
| 45 | 9 | 3 | 0 | 6.11 |
| 50 | 9 | 3 | 0 | 6.11 |

**foreshadowing notes:**
- closed_count_field_not_implemented_yet — ratio open/closed not meaningful; only open_count + stale trend可用

## Novelty trend

- samples: 0
- mean score: 0.0
- trend: **insufficient_data**

## Repetition (global, all narrations as 1 sequence)

- narration_count: 42
- distinct char-2/3/4: 0.8945 / 0.9789 / 0.9959
- overlap consec char-2/3/4: 0.0823 / 0.0266 / 0.0099

## Drift signals

- **open_loop_accumulation: 5 → 9 (+4)**
- **stale_loops_at_end=3 (≥3 — 伏笔僵死苗头)**
