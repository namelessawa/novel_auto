# Bench: baseline-glm-20260721-gourmet_culinary

- novel_id: `bench_baseline-glm-20260721-gourmet_culinary_1784572925`
- ticks: 3
- bootstrap_sec: 118.35
- tick_durations_sec: [35.18, 0.02, 0.02]
- total_tokens: 8425
- call_count: 3
- narrative_chars_total: 0
- tokens_per_char: 8425.00

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 4704 | 55.8% |
| narrative_state_verifier | 2756 | 32.7% |
| world_simulator | 965 | 11.5% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 965 |
| critical | 7460 |

## Cache hit rate (Phase 5-A)

- total prompt_tokens: 6575
- total cached_tokens: 1024
- overall hit rate: 15.6%

| agent | prompt | cached | hit% |
| --- | ---: | ---: | ---: |
| narrator | 3728 | 1024 | 27.5% |
| narrative_state_verifier | 2248 | 0 | 0.0% |
| world_simulator | 599 | 0 | 0.0% |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 8425 | 35.18 | 0 | narrator=4704, narrative_state_verifier=2756, world_simulator=965 |
| 2 | 0 | 0.02 | 0 |  |
| 3 | 0 | 0.02 | 0 |  |
