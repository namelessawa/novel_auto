# Bench: iter126-seed1-cast120

- novel_id: `bench_iter126-seed1-cast120_1781278211`
- ticks: 50
- bootstrap_sec: 507.45
- tick_durations_sec: [113.48, 100.3, 118.64, 115.86, 184.56, 122.57, 112.13, 97.89, 143.83, 442.89, 102.77, 129.84, 153.91, 119.37, 186.91, 117.74, 128.29, 137.29, 120.45, 176.29, 236.6, 135.87, 120.11, 105.55, 178.9, 121.83, 125.15, 95.17, 110.76, 182.04, 106.74, 229.52, 123.74, 114.82, 181.89, 66.29, 108.23, 62.65, 99.75, 127.82, 106.2, 98.27, 212.65, 121.06, 164.87, 86.55, 100.07, 85.92, 106.95, 185.61]
- total_tokens: 483617
- call_count: 122
- narrative_chars_total: 25240
- tokens_per_char: 19.16

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 251220 | 51.9% |
| world_simulator | 142969 | 29.6% |
| showrunner | 42231 | 8.7% |
| event_injector | 17644 | 3.6% |
| character_agent:char_sumo | 7021 | 1.5% |
| novelty_critic | 7007 | 1.4% |
| character_agent:char_linxue | 6899 | 1.4% |
| character_arc_tracker | 4936 | 1.0% |
| narrative_critic:rewrite | 3690 | 0.8% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 209865 |
| critical | 261809 |
| optional | 11943 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6591 | 113.48 | 297 | narrator=3843, world_simulator=2748 |
| 2 | 6740 | 100.3 | 828 | narrator=4331, world_simulator=2409 |
| 3 | 7956 | 118.64 | 488 | narrator=5269, world_simulator=2687 |
| 4 | 7529 | 115.86 | 740 | narrator=4365, world_simulator=3164 |
| 5 | 11461 | 184.56 | 939 | narrator=4878, showrunner=3654, world_simulator=2929 |
| 6 | 7122 | 122.57 | 183 | narrator=5515, world_simulator=1607 |
| 7 | 7055 | 112.13 | 598 | narrator=4105, world_simulator=2950 |
| 8 | 6756 | 97.89 | 750 | narrator=4409, world_simulator=2347 |
| 9 | 8108 | 143.83 | 1249 | narrator=5092, world_simulator=3016 |
| 10 | 25243 | 442.89 | 611 | narrator=7191, event_injector=4217, showrunner=3978 |
| 11 | 7077 | 102.77 | 942 | narrator=4495, world_simulator=2582 |
| 12 | 7947 | 129.84 | 0 | narrator=5508, world_simulator=2439 |
| 13 | 9227 | 153.91 | 468 | narrator=5556, world_simulator=3671 |
| 14 | 7602 | 119.37 | 314 | narrator=4546, world_simulator=3056 |
| 15 | 11775 | 186.91 | 571 | showrunner=4763, narrator=4003, world_simulator=3009 |
| 16 | 7889 | 117.74 | 601 | narrator=4920, world_simulator=2969 |
| 17 | 8086 | 128.29 | 711 | narrator=4502, world_simulator=3584 |
| 18 | 8149 | 137.29 | 942 | narrator=4916, world_simulator=3233 |
| 19 | 7955 | 120.45 | 359 | narrator=5450, world_simulator=2505 |
| 20 | 14810 | 176.29 | 326 | narrator=4586, showrunner=3746, novelty_critic=3307 |
| 21 | 15745 | 236.6 | 834 | narrator=4697, event_injector=4517, character_agent:char_sumo=3337 |
| 22 | 8651 | 135.87 | 801 | narrator=4788, world_simulator=3863 |
| 23 | 8330 | 120.11 | 930 | narrator=4834, world_simulator=3496 |
| 24 | 8113 | 105.55 | 803 | narrator=4493, world_simulator=3620 |
| 25 | 12732 | 178.9 | 248 | narrator=5449, showrunner=4396, world_simulator=2887 |
| 26 | 7999 | 121.83 | 0 | narrator=5081, world_simulator=2918 |
| 27 | 8482 | 125.15 | 671 | narrator=4982, world_simulator=3500 |
| 28 | 7333 | 95.17 | 682 | narrator=4620, world_simulator=2713 |
| 29 | 8328 | 110.76 | 508 | narrator=5495, world_simulator=2833 |
| 30 | 16754 | 182.04 | 664 | narrator=4979, character_arc_tracker=4936, showrunner=4010 |
| 31 | 8590 | 106.74 | 519 | narrator=5460, world_simulator=3130 |
| 32 | 16461 | 229.52 | 0 | narrator=6209, event_injector=4311, character_agent:char_sumo=3684 |
| 33 | 8802 | 123.74 | 71 | narrator=5485, world_simulator=3317 |
| 34 | 7933 | 114.82 | 628 | narrator=4728, world_simulator=3205 |
| 35 | 12342 | 181.89 | 0 | narrator=5539, showrunner=4044, world_simulator=2759 |
| 36 | 6498 | 66.29 | 633 | narrator=4572, world_simulator=1926 |
| 37 | 8438 | 108.23 | 6 | narrator=5660, world_simulator=2778 |
| 38 | 5703 | 62.65 | 538 | narrator=4061, world_simulator=1642 |
| 39 | 7484 | 99.75 | 1240 | narrator=4776, world_simulator=2708 |
| 40 | 14948 | 127.82 | 0 | narrator=5610, showrunner=4103, novelty_critic=3700 |
| 41 | 8382 | 106.2 | 0 | narrator=5614, world_simulator=2768 |
| 42 | 8292 | 98.27 | 336 | narrator=5261, world_simulator=3031 |
| 43 | 16360 | 212.65 | 249 | narrator=5651, event_injector=4599, character_agent:char_linxue=3716 |
| 44 | 8862 | 121.06 | 458 | narrator=5295, world_simulator=3567 |
| 45 | 12614 | 164.87 | 438 | narrator=5366, showrunner=4587, world_simulator=2661 |
| 46 | 7313 | 86.55 | 756 | narrator=4794, world_simulator=2519 |
| 47 | 8034 | 100.07 | 704 | narrator=4593, world_simulator=3441 |
| 48 | 7521 | 85.92 | 0 | narrator=4910, world_simulator=2611 |
| 49 | 8118 | 106.95 | 606 | narrator=5391, world_simulator=2727 |
| 50 | 13377 | 185.61 | 0 | narrator=5347, showrunner=4950, world_simulator=3080 |

## First narrative sample

```
锈蚀的金属屋顶被雨点敲击，声音稠密而均匀，像无数根手指在铁皮上练习同一段敲打乐。苏默靠在峡谷边缘的残破墙根下，仰头看着灰褐色的天。能见度不好，远处谷壁的轮廓在雾气里时隐时现，像一笔被水洇开的淡墨。工业烟囱的蒸汽混进雨雾，带着硫磺和铁锈的气味漫过来，他侧过头，用手背抵住口鼻，喉咙里泛起一阵熟悉的痒，忍不住压着嗓子咳了几声。那声音闷在胸腔里，没能完全挣出来。他低头看自己的手背，水汽凝在皮肤纹路里，细密冰凉。雨没有停的意思，敲击声成了背景里恒常的节拍。他得移动了，但两条腿沉得像灌了铅，不是疲劳，是另一种东西拽着，从身体内部往外扯。他望向峡谷深处，雾气在那里更浓，缓慢翻滚，吞没了所有路径的细节。
```
