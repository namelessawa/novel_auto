# Bench: v12-cumulative-iter15

- novel_id: `bench_v12-cumulative-iter15_1781128109`
- ticks: 3
- bootstrap_sec: 266.03
- tick_durations_sec: [177.08, 83.81, 75.47]
- total_tokens: 35901
- call_count: 10

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 12145 | 33.8% |
| world_simulator | 7939 | 22.1% |
| narrative_critic:critique | 7120 | 19.8% |
| narrative_critic:revise | 5158 | 14.4% |
| narrative_critic:rewrite | 3539 | 9.9% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 7939 |
| critical | 27962 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 15341 | 177.08 | 10 | narrative_critic:revise=5158, narrator=3894, narrative_critic:rewrite=3539 |
| 2 | 10515 | 83.81 | 494 | narrative_critic:critique=3945, narrator=3837, world_simulator=2733 |
| 3 | 10045 | 75.47 | 524 | narrator=4414, narrative_critic:critique=3175, world_simulator=2456 |

## First narrative sample

```
完整修订后的段落正文
```
