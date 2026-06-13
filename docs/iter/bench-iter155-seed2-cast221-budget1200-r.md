# Bench: iter155-seed2-cast221-budget1200-r

- novel_id: `bench_iter155-seed2-cast221-budget1200-r_1781364633`
- ticks: 50
- bootstrap_sec: 357.03
- tick_durations_sec: [80.6, 62.83, 86.63, 94.62, 150.21, 78.2, 95.37, 99.9, 104.87, 351.75, 98.06, 93.97, 127.24, 117.3, 181.99, 85.36, 74.23, 72.3, 97.08, 174.83, 223.82, 92.72, 98.97, 97.53, 132.87, 92.18, 87.83, 82.46, 114.64, 169.21, 74.13, 211.7, 117.2, 106.5, 161.27, 79.56, 75.83, 89.64, 94.38, 177.42, 79.28, 75.84, 207.34, 81.02, 125.62, 78.86, 92.02, 104.51, 103.14, 158.49]
- total_tokens: 522773
- call_count: 123
- narrative_chars_total: 29402
- tokens_per_char: 17.78

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 266836 | 51.0% |
| world_simulator | 147239 | 28.2% |
| showrunner | 53134 | 10.2% |
| event_injector | 19242 | 3.7% |
| character_agent:char_satojian | 11713 | 2.2% |
| character_agent:char_linxue | 8448 | 1.6% |
| novelty_critic | 7013 | 1.3% |
| character_arc_tracker | 4746 | 0.9% |
| narrative_critic:critique | 4402 | 0.8% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 231328 |
| critical | 279686 |
| optional | 11759 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 7124 | 80.6 | 0 | narrator=5061, world_simulator=2063 |
| 2 | 6178 | 62.83 | 463 | narrator=4380, world_simulator=1798 |
| 3 | 7710 | 86.63 | 776 | narrator=4652, world_simulator=3058 |
| 4 | 8513 | 94.62 | 574 | narrator=5366, world_simulator=3147 |
| 5 | 13192 | 150.21 | 580 | showrunner=5122, narrator=5059, world_simulator=3011 |
| 6 | 7447 | 78.2 | 665 | narrator=5447, world_simulator=2000 |
| 7 | 8514 | 95.37 | 819 | narrator=5445, world_simulator=3069 |
| 8 | 8262 | 99.9 | 1131 | narrator=4965, world_simulator=3297 |
| 9 | 8895 | 104.87 | 9 | narrator=5815, world_simulator=3080 |
| 10 | 32018 | 351.75 | 1998 | narrator=6822, event_injector=5390, showrunner=4624 |
| 11 | 8547 | 98.06 | 0 | narrator=5764, world_simulator=2783 |
| 12 | 8295 | 93.97 | 0 | narrator=4679, world_simulator=3616 |
| 13 | 9565 | 127.24 | 1036 | narrator=5497, world_simulator=4068 |
| 14 | 9353 | 117.3 | 0 | narrator=5945, world_simulator=3408 |
| 15 | 14866 | 181.99 | 359 | narrator=5994, showrunner=5293, world_simulator=3579 |
| 16 | 7832 | 85.36 | 708 | narrator=4860, world_simulator=2972 |
| 17 | 7559 | 74.23 | 672 | narrator=4926, world_simulator=2633 |
| 18 | 7248 | 72.3 | 940 | narrator=5079, world_simulator=2169 |
| 19 | 8424 | 97.08 | 915 | narrator=5685, world_simulator=2739 |
| 20 | 17471 | 174.83 | 982 | narrator=5713, showrunner=5484, novelty_critic=3343 |
| 21 | 17956 | 223.82 | 1399 | narrator=6128, event_injector=4853, character_agent:char_satojian=3835 |
| 22 | 8215 | 92.72 | 696 | narrator=4694, world_simulator=3521 |
| 23 | 8051 | 98.97 | 892 | narrator=4931, world_simulator=3120 |
| 24 | 8699 | 97.53 | 162 | narrator=5564, world_simulator=3135 |
| 25 | 11573 | 132.87 | 0 | showrunner=5322, narrator=4505, world_simulator=1746 |
| 26 | 7774 | 92.18 | 591 | narrator=4576, world_simulator=3198 |
| 27 | 8216 | 87.83 | 867 | narrator=5120, world_simulator=3096 |
| 28 | 7843 | 82.46 | 0 | narrator=6059, world_simulator=1784 |
| 29 | 9101 | 114.64 | 1052 | narrator=5356, world_simulator=3745 |
| 30 | 19136 | 169.21 | 166 | narrator=6115, showrunner=5610, character_arc_tracker=4746 |
| 31 | 6989 | 74.13 | 0 | narrator=4340, world_simulator=2649 |
| 32 | 17438 | 211.7 | 1238 | narrator=6191, character_agent:char_satojian=4847, event_injector=4019 |
| 33 | 9293 | 117.2 | 898 | narrator=5964, world_simulator=3329 |
| 34 | 8913 | 106.5 | 503 | narrator=6006, world_simulator=2907 |
| 35 | 13620 | 161.27 | 593 | showrunner=5686, narrator=5140, world_simulator=2794 |
| 36 | 7555 | 79.56 | 1251 | narrator=5471, world_simulator=2084 |
| 37 | 7856 | 75.83 | 525 | narrator=4659, world_simulator=3197 |
| 38 | 8078 | 89.64 | 806 | narrator=5041, world_simulator=3037 |
| 39 | 8904 | 94.38 | 0 | narrator=5879, world_simulator=3025 |
| 40 | 18332 | 177.42 | 463 | narrator=5973, showrunner=5524, novelty_critic=3670 |
| 41 | 7630 | 79.28 | 567 | narrator=4874, world_simulator=2756 |
| 42 | 7847 | 75.84 | 0 | narrator=4298, world_simulator=3549 |
| 43 | 18066 | 207.34 | 1017 | narrator=5809, event_injector=4980, character_agent:char_linxue=4380 |
| 44 | 7666 | 81.02 | 531 | narrator=5376, world_simulator=2290 |
| 45 | 12596 | 125.62 | 731 | narrator=5299, showrunner=4963, world_simulator=2334 |
| 46 | 8144 | 78.86 | 654 | narrator=4885, world_simulator=3259 |
| 47 | 8453 | 92.02 | 0 | narrator=5246, world_simulator=3207 |
| 48 | 9337 | 104.51 | 78 | narrator=5809, world_simulator=3528 |
| 49 | 8777 | 103.14 | 259 | narrator=5359, world_simulator=3418 |
| 50 | 13702 | 158.49 | 836 | showrunner=5506, narrator=5015, world_simulator=3181 |

## First narrative sample

```
雨还在下，但雾已经散尽了。

苏默把灰布长衫的领子竖起来，雨水顺着布料边缘渗进脖颈，激起一阵凉意。他沿着江边石板路走，靴底踩在湿滑的路面上，发出短促而清晰的摩擦声。昨天还能没到小腿的浓雾，此刻只剩江心一缕薄纱，底下青灰色的水波纹路一根根数得清。空气里那股子潮湿的霉烂气更重了，混着江水特有的腥，钻进鼻腔，像某种陈年档案打开时的味道。

他在码头第三根铁桩旁停下。视线越过几排低矮的货栈屋顶，落在远处泊位上。一艘深灰色的货船正在靠岸，船舷上沾着锈迹和油污，甲板上有两个穿短打的苦力正弯腰移动一个木箱。缆绳绷紧时发出的吱嘎声，木箱底板刮过甲板的钝响，都清清楚楚地传过来。比昨天靠岸的那艘大，吃水也深。

他抬手抹了把脸上的雨水，手指触到眼尾一道旧疤的凹凸。老王说今天会有新船。但他没说过是这艘。

雨珠从帽檐滚落，在他脚边溅开细小的水花。石板路上的反光更亮了，把远处货船的轮廓、码头吊臂的钢索、甚至更远处法租界那几栋灰蒙蒙的洋楼顶，都映照得刀切一般分明。界限太清楚了。清楚得让他喉咙发紧。

他松开握着领口的手，掌心潮湿。该动了。
```
