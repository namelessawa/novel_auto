# Bench: stage5-seed3-30tick-retry

- novel_id: `bench_stage5-seed3-30tick-retry_1781183312`
- ticks: 30
- bootstrap_sec: 347.28
- tick_durations_sec: [117.28, 89.95, 91.92, 107.22, 131.13, 81.11, 111.3, 112.57, 101.55, 314.5, 112.57, 131.33, 74.79, 113.49, 161.17, 70.93, 87.38, 91.1, 102.81, 203.56, 258.41, 46.02, 108.22, 119.52, 192.57, 118.6, 125.3, 115.11, 84.37, 190.4]
- total_tokens: 303290
- call_count: 73
- narrative_chars_total: 14550
- tokens_per_char: 20.84

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 158150 | 52.1% |
| world_simulator | 88034 | 29.0% |
| showrunner | 24733 | 8.2% |
| event_injector | 9229 | 3.0% |
| character_arc_tracker | 5000 | 1.6% |
| character_agent:char_sumo | 3963 | 1.3% |
| narrative_critic:critique | 3961 | 1.3% |
| character_agent:char_wunian | 3790 | 1.2% |
| novelty_critic | 3523 | 1.2% |
| character_agent:char_chenduishou | 2907 | 1.0% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 124903 |
| critical | 169864 |
| optional | 8523 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 7210 | 117.28 | 40 | narrator=5005, world_simulator=2205 |
| 2 | 7059 | 89.95 | 0 | narrator=3572, world_simulator=3487 |
| 3 | 7085 | 91.92 | 687 | narrator=4748, world_simulator=2337 |
| 4 | 8118 | 107.22 | 978 | narrator=4991, world_simulator=3127 |
| 5 | 11175 | 131.13 | 678 | narrator=5150, showrunner=3466, world_simulator=2559 |
| 6 | 7326 | 81.11 | 1049 | narrator=4858, world_simulator=2468 |
| 7 | 8530 | 111.3 | 0 | narrator=5831, world_simulator=2699 |
| 8 | 8940 | 112.57 | 61 | narrator=5866, world_simulator=3074 |
| 9 | 7876 | 101.55 | 737 | narrator=4235, world_simulator=3641 |
| 10 | 26592 | 314.5 | 505 | narrator=7409, event_injector=4749, showrunner=4557 |
| 11 | 8702 | 112.57 | 628 | narrator=5628, world_simulator=3074 |
| 12 | 9127 | 131.33 | 392 | narrator=5735, world_simulator=3392 |
| 13 | 6634 | 74.79 | 1154 | narrator=4771, world_simulator=1863 |
| 14 | 8805 | 113.49 | 262 | narrator=5852, world_simulator=2953 |
| 15 | 12681 | 161.17 | 476 | narrator=5462, world_simulator=3770, showrunner=3449 |
| 16 | 6655 | 70.93 | 912 | narrator=4751, world_simulator=1904 |
| 17 | 7558 | 87.38 | 690 | narrator=5138, world_simulator=2420 |
| 18 | 7619 | 91.1 | 1086 | narrator=5002, world_simulator=2617 |
| 19 | 8591 | 102.81 | 0 | narrator=5842, world_simulator=2749 |
| 20 | 18423 | 203.56 | 0 | narrator=5883, world_simulator=4829, showrunner=4188 |
| 21 | 21755 | 258.41 | 949 | narrator=7737, event_injector=4480, narrative_critic:critique=3961 |
| 22 | 2928 | 46.02 | 0 | world_simulator=2928 |
| 23 | 8468 | 108.22 | 118 | narrator=6034, world_simulator=2434 |
| 24 | 8520 | 119.52 | 549 | narrator=5137, world_simulator=3383 |
| 25 | 13652 | 192.57 | 0 | narrator=5795, showrunner=4440, world_simulator=3417 |
| 26 | 9141 | 118.6 | 0 | narrator=5815, world_simulator=3326 |
| 27 | 8810 | 125.3 | 800 | narrator=5355, world_simulator=3455 |
| 28 | 9566 | 115.11 | 477 | narrator=5981, world_simulator=3585 |
| 29 | 7794 | 84.37 | 679 | narrator=4974, world_simulator=2820 |
| 30 | 17950 | 190.4 | 643 | narrator=5593, character_arc_tracker=5000, showrunner=4633 |

## First narrative sample

```
沙打在集装箱壁上，像有人一把一把往上撒铁屑。苏默蹲在滤风单元前，扳手卡住锈死的螺
```
