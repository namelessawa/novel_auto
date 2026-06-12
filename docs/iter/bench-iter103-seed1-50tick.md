# Bench: iter103-seed1-50tick

- novel_id: `bench_iter103-seed1-50tick_1781219317`
- ticks: 50
- bootstrap_sec: 307.44
- tick_durations_sec: [60.12, 91.26, 76.16, 80.2, 144.79, 86.32, 103.07, 69.48, 106.85, 300.77, 158.16, 83.91, 88.98, 112.58, 124.83, 86.76, 112.29, 98.7, 68.11, 155.95, 253.52, 84.0, 129.12, 105.21, 208.52, 95.0, 70.9, 93.85, 115.01, 175.96, 120.85, 284.65, 93.4, 117.12, 162.77, 110.33, 95.45, 131.21, 107.07, 153.84, 102.44, 107.81, 234.19, 74.33, 151.71, 58.12, 89.4, 93.95, 83.47, 121.54]
- total_tokens: 544467
- call_count: 126
- narrative_chars_total: 38485
- tokens_per_char: 14.15

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 274284 | 50.4% |
| world_simulator | 156415 | 28.7% |
| showrunner | 43062 | 7.9% |
| event_injector | 21932 | 4.0% |
| character_agent:char_shenrui | 18388 | 3.4% |
| character_agent:char_linxue | 8440 | 1.6% |
| character_agent:char_sumo | 7272 | 1.3% |
| novelty_critic | 5910 | 1.1% |
| character_arc_tracker | 4440 | 0.8% |
| narrative_critic:critique | 4324 | 0.8% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 221409 |
| critical | 312708 |
| optional | 10350 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6461 | 60.12 | 440 | narrator=5056, world_simulator=1405 |
| 2 | 8604 | 91.26 | 383 | narrator=5445, world_simulator=3159 |
| 3 | 7613 | 76.16 | 649 | narrator=4619, world_simulator=2994 |
| 4 | 7786 | 80.2 | 764 | narrator=4941, world_simulator=2845 |
| 5 | 12256 | 144.79 | 1457 | narrator=5528, showrunner=3591, world_simulator=3137 |
| 6 | 7876 | 86.32 | 374 | narrator=5827, world_simulator=2049 |
| 7 | 8312 | 103.07 | 630 | narrator=4721, world_simulator=3591 |
| 8 | 7370 | 69.48 | 586 | narrator=4989, world_simulator=2381 |
| 9 | 8929 | 106.85 | 747 | narrator=5503, world_simulator=3426 |
| 10 | 28277 | 300.77 | 1188 | narrator=7050, event_injector=5821, showrunner=4713 |
| 11 | 17901 | 158.16 | 0 | narrator=6346, character_agent:char_linxue=4149, character_agent:char_shenrui=4044 |
| 12 | 8485 | 83.91 | 953 | narrator=5322, world_simulator=3163 |
| 13 | 8952 | 88.98 | 108 | narrator=6050, world_simulator=2902 |
| 14 | 9333 | 112.58 | 0 | narrator=5505, world_simulator=3828 |
| 15 | 11640 | 124.83 | 641 | showrunner=5055, narrator=4762, world_simulator=1823 |
| 16 | 8845 | 86.76 | 914 | narrator=5753, world_simulator=3092 |
| 17 | 9632 | 112.29 | 767 | narrator=5970, world_simulator=3662 |
| 18 | 9261 | 98.7 | 169 | narrator=5924, world_simulator=3337 |
| 19 | 7395 | 68.11 | 782 | narrator=4359, world_simulator=3036 |
| 20 | 16810 | 155.95 | 205 | narrator=5920, showrunner=5062, world_simulator=3348 |
| 21 | 23245 | 253.52 | 1221 | event_injector=6168, narrator=6143, character_agent:char_shenrui=4929 |
| 22 | 8617 | 84.0 | 1005 | narrator=5284, world_simulator=3333 |
| 23 | 10185 | 129.12 | 1169 | narrator=5651, world_simulator=4534 |
| 24 | 9130 | 105.21 | 1378 | narrator=5583, world_simulator=3547 |
| 25 | 13646 | 208.52 | 712 | narrator=5583, showrunner=4839, world_simulator=3224 |
| 26 | 8298 | 95.0 | 497 | narrator=5458, world_simulator=2840 |
| 27 | 7023 | 70.9 | 285 | narrator=5395, world_simulator=1628 |
| 28 | 7726 | 93.85 | 647 | narrator=4410, world_simulator=3316 |
| 29 | 8918 | 115.01 | 729 | narrator=4930, world_simulator=3988 |
| 30 | 17213 | 175.96 | 654 | narrator=4679, character_arc_tracker=4440, showrunner=4305 |
| 31 | 9446 | 120.85 | 917 | narrator=5731, world_simulator=3715 |
| 32 | 20654 | 284.65 | 1493 | narrator=7172, character_agent:char_shenrui=5879, event_injector=4669 |
| 33 | 8229 | 93.4 | 778 | narrator=4936, world_simulator=3293 |
| 34 | 9037 | 117.12 | 0 | narrator=5825, world_simulator=3212 |
| 35 | 13001 | 162.77 | 0 | narrator=5865, showrunner=4280, world_simulator=2856 |
| 36 | 8633 | 110.33 | 1415 | narrator=5985, world_simulator=2648 |
| 37 | 8596 | 95.45 | 562 | narrator=5111, world_simulator=3485 |
| 38 | 8781 | 131.21 | 4823 | narrator=5792, world_simulator=2989 |
| 39 | 8371 | 107.07 | 889 | narrator=5242, world_simulator=3129 |
| 40 | 16708 | 153.84 | 0 | narrator=5956, showrunner=4067, novelty_critic=3430 |
| 41 | 9101 | 102.44 | 520 | narrator=5964, world_simulator=3137 |
| 42 | 9349 | 107.81 | 910 | narrator=5014, world_simulator=4335 |
| 43 | 23216 | 234.19 | 1407 | narrator=6187, event_injector=5274, character_agent:char_sumo=4771 |
| 44 | 8099 | 74.33 | 1011 | narrator=5330, world_simulator=2769 |
| 45 | 13762 | 151.71 | 803 | narrator=5845, world_simulator=4076, showrunner=3841 |
| 46 | 7089 | 58.12 | 583 | narrator=4802, world_simulator=2287 |
| 47 | 8477 | 89.4 | 650 | narrator=5597, world_simulator=2880 |
| 48 | 8569 | 93.95 | 708 | narrator=5097, world_simulator=3472 |
| 49 | 7822 | 83.47 | 962 | narrator=4998, world_simulator=2824 |
| 50 | 11788 | 121.54 | 0 | narrator=5129, world_simulator=3350, showrunner=3309 |

## First narrative sample

```
石板路上的积水没过鞋底。苏默把领子竖起来，雨水顺着油布衣的褶皱淌进脖颈，冰凉的一道线。雾气从地下管道的接缝处往上涌，裹着铁锈和煤焦的气味，把半条街的能见度压到了三步以内。

蒸汽钟塔的报时声从雾深处传来——三下，沉闷，尾音被水汽拖得又长又哑。苏默在心里记了一笔。比昨天晚了一刻钟。钟塔不准，要么是齿轮磨损，要么是气压不足，两样都不该发生在城中心的主干道上。

他没有走主干道。

第二条街口他拐进窄巷，巷壁两侧钉满管道支架，锈红色的冷凝水顺着支架滴落，砸在头顶的遮雨棚上，响得密集而零碎。远处某根露天管道的接口发出一声尖锐的嘶鸣，像铁被活活撕开。雨已经下了七天，整个灰烬城泡在一层洗不掉的灰蒙蒙的水汽里，连铜质路牌都挂上了绿锈。

苏默加快脚步。他左手攥着一张折了三折的纸条，纸条被雨水洇湿了一角，墨迹晕开，但上面的地址和时间还看得清。第三区，锈巷十七号，今夜子时。还有一个他不认识的名字。

巷子深处的光线暗下去，蒸汽管道在头顶嘶嘶低吼。冷凝水滴进衣领，他没擦，步子迈得更大了。
```
