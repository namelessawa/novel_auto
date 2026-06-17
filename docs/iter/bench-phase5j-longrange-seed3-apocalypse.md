# Bench: phase5j-longrange-seed3-apocalypse

- novel_id: `bench_phase5j-longrange-seed3-apocalypse_1781689605`
- ticks: 100
- bootstrap_sec: 328.87
- tick_durations_sec: [36.87, 0.02, 0.02, 50.56, 17.71, 0.02, 51.74, 0.02, 0.02, 199.64, 66.37, 0.02, 0.02, 46.07, 18.35, 0.02, 57.89, 0.02, 0.03, 77.52, 155.08, 55.33, 0.02, 0.02, 80.58, 0.03, 0.03, 68.48, 0.03, 42.16, 52.89, 214.25, 97.82, 0.02, 16.89, 46.08, 0.02, 0.02, 67.6, 34.68, 0.02, 55.81, 75.73, 52.66, 17.48, 0.02, 61.04, 0.03, 0.03, 73.58, 0.03, 0.02, 50.01, 108.03, 66.17, 0.02, 0.02, 62.8, 0.03, 51.03, 49.69, 0.02, 0.02, 53.19, 189.51, 60.96, 0.02, 0.02, 55.79, 20.06, 0.02, 49.63, 0.02, 0.03, 62.6, 176.6, 97.62, 0.02, 0.02, 72.44, 0.03, 0.04, 50.04, 0.04, 16.6, 48.57, 95.13, 61.79, 0.04, 47.15, 61.42, 0.03, 0.02, 51.22, 18.59, 0.05, 48.63, 108.99, 54.14, 76.29]
- total_tokens: 438843
- call_count: 157
- narrative_chars_total: 43444
- tokens_per_char: 10.10

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 195770 | 44.6% |
| showrunner | 53002 | 12.1% |
| world_simulator | 47594 | 10.8% |
| event_injector | 29609 | 6.7% |
| narrative_critic:critique | 20980 | 4.8% |
| character_agent:char_linchen | 19148 | 4.4% |
| character_agent:char_yanhua | 17974 | 4.1% |
| narrative_critic:rewrite | 15960 | 3.6% |
| character_agent:char_sumo | 14747 | 3.4% |
| character_arc_tracker | 10228 | 2.3% |
| novelty_critic | 6457 | 1.5% |
| character_agent:char_laohan | 4130 | 0.9% |
| memory_compressor:l0_l1 | 3244 | 0.7% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 134335 |
| critical | 284579 |
| optional | 19929 |

## Cache hit rate (Phase 5-A)

- total prompt_tokens: 330585
- total cached_tokens: 0
- overall hit rate: 0.0%

| agent | prompt | cached | hit% |
| --- | ---: | ---: | ---: |
| narrator | 152249 | 0 | 0.0% |
| showrunner | 43545 | 0 | 0.0% |
| world_simulator | 27256 | 0 | 0.0% |
| event_injector | 23217 | 0 | 0.0% |
| narrative_critic:critique | 15589 | 0 | 0.0% |
| character_agent:char_linchen | 14849 | 0 | 0.0% |
| character_agent:char_yanhua | 14478 | 0 | 0.0% |
| character_agent:char_sumo | 11170 | 0 | 0.0% |
| narrative_critic:rewrite | 10652 | 0 | 0.0% |
| character_arc_tracker | 7625 | 0 | 0.0% |
| novelty_critic | 4514 | 0 | 0.0% |
| character_agent:char_laohan | 3365 | 0 | 0.0% |
| memory_compressor:l0_l1 | 2076 | 0 | 0.0% |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 3949 | 36.87 | 423 | narrator=2987, world_simulator=962 |
| 2 | 0 | 0.02 | 0 |  |
| 3 | 0 | 0.02 | 0 |  |
| 4 | 4640 | 50.56 | 777 | narrator=3632, world_simulator=1008 |
| 5 | 2503 | 17.71 | 0 | showrunner=2503 |
| 6 | 0 | 0.02 | 0 |  |
| 7 | 4816 | 51.74 | 723 | narrator=3833, world_simulator=983 |
| 8 | 0 | 0.02 | 0 |  |
| 9 | 0 | 0.02 | 0 |  |
| 10 | 19738 | 199.64 | 1206 | narrator=4695, event_injector=3447, narrative_critic:critique=2774 |
| 11 | 5939 | 66.37 | 1003 | narrator=4271, world_simulator=1668 |
| 12 | 0 | 0.02 | 0 |  |
| 13 | 0 | 0.02 | 0 |  |
| 14 | 4876 | 46.07 | 703 | narrator=3885, world_simulator=991 |
| 15 | 2594 | 18.35 | 0 | showrunner=2594 |
| 16 | 0 | 0.02 | 0 |  |
| 17 | 5087 | 57.89 | 1124 | narrator=4098, world_simulator=989 |
| 18 | 0 | 0.02 | 0 |  |
| 19 | 0 | 0.03 | 0 |  |
| 20 | 8760 | 77.52 | 899 | narrator=3985, showrunner=2596, novelty_critic=1187 |
| 21 | 18258 | 155.08 | 857 | narrator=4903, narrative_critic:critique=3351, event_injector=3188 |
| 22 | 5395 | 55.33 | 926 | narrator=4091, world_simulator=1304 |
| 23 | 0 | 0.02 | 0 |  |
| 24 | 0 | 0.02 | 0 |  |
| 25 | 8209 | 80.58 | 1200 | narrator=4308, showrunner=2830, world_simulator=1071 |
| 26 | 0 | 0.03 | 0 |  |
| 27 | 0 | 0.03 | 0 |  |
| 28 | 5532 | 68.48 | 1381 | narrator=4402, world_simulator=1130 |
| 29 | 0 | 0.03 | 0 |  |
| 30 | 5309 | 42.16 | 0 | showrunner=2831, character_arc_tracker=2478 |
| 31 | 5085 | 52.89 | 835 | narrator=3937, world_simulator=1148 |
| 32 | 18854 | 214.25 | 1464 | narrator=5648, narrative_critic:critique=4282, narrative_critic:rewrite=3694 |
| 33 | 16183 | 97.82 | 1928 | narrator=6145, character_agent:char_linchen=2357, character_agent:char_yanhua=2223 |
| 34 | 0 | 0.02 | 0 |  |
| 35 | 2611 | 16.89 | 0 | showrunner=2611 |
| 36 | 5039 | 46.08 | 649 | narrator=3859, world_simulator=1180 |
| 37 | 0 | 0.02 | 0 |  |
| 38 | 0 | 0.02 | 0 |  |
| 39 | 4983 | 67.6 | 926 | narrator=3912, world_simulator=1071 |
| 40 | 4067 | 34.68 | 0 | showrunner=2673, novelty_critic=1394 |
| 41 | 0 | 0.02 | 0 |  |
| 42 | 5166 | 55.81 | 988 | narrator=4056, world_simulator=1110 |
| 43 | 9845 | 75.73 | 611 | narrator=4292, event_injector=3250, character_agent:char_yanhua=2303 |
| 44 | 5192 | 52.66 | 819 | narrator=3845, world_simulator=1347 |
| 45 | 2556 | 17.48 | 0 | showrunner=2556 |
| 46 | 0 | 0.02 | 0 |  |
| 47 | 5397 | 61.04 | 1205 | narrator=4236, world_simulator=1161 |
| 48 | 0 | 0.03 | 0 |  |
| 49 | 0 | 0.03 | 0 |  |
| 50 | 7909 | 73.58 | 1169 | narrator=4180, showrunner=2554, world_simulator=1175 |
| 51 | 0 | 0.03 | 0 |  |
| 52 | 0 | 0.02 | 0 |  |
| 53 | 5147 | 50.01 | 919 | narrator=4051, world_simulator=1096 |
| 54 | 16594 | 108.03 | 1734 | narrator=5988, event_injector=3204, character_agent:char_sumo=2502 |
| 55 | 8045 | 66.17 | 810 | narrator=4020, showrunner=2562, world_simulator=1463 |
| 56 | 0 | 0.02 | 0 |  |
| 57 | 0 | 0.02 | 0 |  |
| 58 | 5750 | 62.8 | 938 | narrator=4261, world_simulator=1489 |
| 59 | 0 | 0.03 | 0 |  |
| 60 | 7528 | 51.03 | 0 | character_arc_tracker=3679, showrunner=2687, novelty_critic=1162 |
| 61 | 5260 | 49.69 | 665 | narrator=3949, world_simulator=1311 |
| 62 | 0 | 0.02 | 0 |  |
| 63 | 0 | 0.02 | 0 |  |
| 64 | 5230 | 53.19 | 813 | narrator=3942, world_simulator=1288 |
| 65 | 26072 | 189.51 | 575 | narrator=6135, narrative_critic:critique=4267, event_injector=3453 |
| 66 | 5732 | 60.96 | 1018 | narrator=4113, world_simulator=1619 |
| 67 | 0 | 0.02 | 0 |  |
| 68 | 0 | 0.02 | 0 |  |
| 69 | 5529 | 55.79 | 1043 | narrator=4240, world_simulator=1289 |
| 70 | 2756 | 20.06 | 0 | showrunner=2756 |
| 71 | 0 | 0.02 | 0 |  |
| 72 | 5263 | 49.63 | 779 | narrator=3970, world_simulator=1293 |
| 73 | 0 | 0.02 | 0 |  |
| 74 | 0 | 0.03 | 0 |  |
| 75 | 7799 | 62.6 | 688 | narrator=3908, showrunner=2548, world_simulator=1343 |
| 76 | 23199 | 176.6 | 1377 | narrator=5901, narrative_critic:critique=3478, event_injector=3314 |
| 77 | 14472 | 97.62 | 1462 | narrator=5788, character_agent:char_sumo=2399, character_agent:char_linchen=2265 |
| 78 | 0 | 0.02 | 0 |  |
| 79 | 0 | 0.02 | 0 |  |
| 80 | 9506 | 72.44 | 837 | narrator=4123, showrunner=2681, world_simulator=1426 |
| 81 | 0 | 0.03 | 0 |  |
| 82 | 0 | 0.04 | 0 |  |
| 83 | 5434 | 50.04 | 795 | narrator=4057, world_simulator=1377 |
| 84 | 0 | 0.04 | 0 |  |
| 85 | 2594 | 16.6 | 0 | showrunner=2594 |
| 86 | 5456 | 48.57 | 602 | narrator=3925, world_simulator=1531 |
| 87 | 11488 | 95.13 | 560 | narrator=3856, event_injector=2977, narrative_critic:critique=2828 |
| 88 | 5604 | 61.79 | 950 | narrator=4067, world_simulator=1537 |
| 89 | 0 | 0.04 | 0 |  |
| 90 | 6743 | 47.15 | 0 | character_arc_tracker=4071, showrunner=2672 |
| 91 | 5768 | 61.42 | 1017 | narrator=4277, world_simulator=1491 |
| 92 | 0 | 0.03 | 0 |  |
| 93 | 0 | 0.02 | 0 |  |
| 94 | 5486 | 51.22 | 770 | narrator=4017, world_simulator=1469 |
| 95 | 2677 | 18.59 | 0 | showrunner=2677 |
| 96 | 0 | 0.05 | 0 |  |
| 97 | 5330 | 48.63 | 756 | narrator=3991, world_simulator=1339 |
| 98 | 16741 | 108.99 | 1613 | narrator=5887, event_injector=3609, character_agent:char_sumo=2596 |
| 99 | 5767 | 54.14 | 907 | narrator=4104, world_simulator=1663 |
| 100 | 7381 | 76.29 | 0 | memory_compressor:l0_l1=3244, showrunner=2699, novelty_critic=1438 |

## First narrative sample

```
冰柱断裂的声音很脆。

像玻璃杯磕在铁皮上。碎冰溅上石阶，又滑下去，在第三级台阶上停住。铅灰色穹顶的接缝处还有两根冰棱挂着，风穿过时它们微微颤动，但没掉。

档案馆前的广场空无一人。

检查站那边传来铁丝网的低频嗡鸣。一段松脱的铁丝反复抽打水泥桩，节奏不规则——三下快，停顿，一下慢。铁锈粉末随着每次撞击簌簌落下，在桩基上积成暗红色的细线。

风变了方向。冰粒从斜打转为直落，敲在穹顶铅皮上，沙沙声密了一层。

栈桥方向有渡鸦在叫。不是鸣叫，是啄食的叩击——喙尖敲在系缆桩的铁箍上，单调，重复，每隔两秒一次。黑水在桥桩间缓慢翻涌，油膜裂开又合拢，映不出任何东西。

渡鸦歪头，啄起一粒冰，仰脖吞下。

然后它飞走了。

系缆桩上留下一道湿痕，很快被新落的冰粒覆盖。栈桥尽头，港区的轮廓在铅云下只剩灰影。起重机吊臂静止，船坞空置，废品女王号的船壳半沉在水里，露出水面的部分锈成赭红色。

广场上，那根断裂的冰棱已经完全融化。

石阶上只剩一摊水迹。
```
