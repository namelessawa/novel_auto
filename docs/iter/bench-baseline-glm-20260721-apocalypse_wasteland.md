# Bench: baseline-glm-20260721-apocalypse_wasteland

- novel_id: `bench_baseline-glm-20260721-apocalypse_wasteland_1784573111`
- ticks: 3
- bootstrap_sec: 117.2
- tick_durations_sec: [88.32, 0.02, 0.02]
- total_tokens: 20950
- call_count: 7
- narrative_chars_total: 0
- tokens_per_char: 20950.00

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrative_state_verifier | 8893 | 42.4% |
| narrative_state_repair | 6248 | 29.8% |
| narrator | 4835 | 23.1% |
| world_simulator | 974 | 4.6% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 974 |
| critical | 19976 |

## Cache hit rate (Phase 5-A)

- total prompt_tokens: 15648
- total cached_tokens: 3072
- overall hit rate: 19.6%

| agent | prompt | cached | hit% |
| --- | ---: | ---: | ---: |
| narrative_state_verifier | 7122 | 2048 | 28.8% |
| narrative_state_repair | 4166 | 0 | 0.0% |
| narrator | 3755 | 1024 | 27.3% |
| world_simulator | 605 | 0 | 0.0% |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 20950 | 88.32 | 0 | narrative_state_verifier=8893, narrative_state_repair=6248, narrator=4835 |
| 2 | 0 | 0.02 | 0 |  |
| 3 | 0 | 0.02 | 0 |  |
