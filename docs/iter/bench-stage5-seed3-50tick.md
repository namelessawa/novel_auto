# Bench: stage5-seed3-50tick

- novel_id: `bench_stage5-seed3-50tick_1781203198`
- ticks: 50
- bootstrap_sec: 349.27
- tick_durations_sec: [62.34, 98.86, 64.64, 121.73, 174.81, 94.48, 94.37, 63.08, 87.64, 431.18, 108.99, 86.57, 77.85, 80.14, 117.27, 109.12, 92.21, 88.89, 96.72, 151.34, 272.61, 226.84, 163.18, 164.66, 242.15, 178.0, 154.14, 191.9, 165.77, 238.82, 205.42, 307.32, 174.81, 239.33, 245.49, 207.42, 152.21, 189.28, 172.75, 272.58, 203.94, 93.51, 261.82, 215.91, 218.36, 140.47, 186.37, 158.28, 228.94, 203.89]
- total_tokens: 1305466
- call_count: 297
- narrative_chars_total: 44660
- tokens_per_char: 29.23

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 352030 | 27.0% |
| world_simulator | 157071 | 12.0% |
| character_agent:char_fangyanshu | 124986 | 9.6% |
| character_agent:char_jichuan | 119023 | 9.1% |
| character_agent:char_lujiuniang | 116598 | 8.9% |
| character_agent:char_linxue | 115502 | 8.8% |
| character_agent:char_sumo | 113264 | 8.7% |
| character_agent:char_ading | 112037 | 8.6% |
| showrunner | 41958 | 3.2% |
| event_injector | 24719 | 1.9% |
| narrative_critic:critique | 13445 | 1.0% |
| character_arc_tracker | 7472 | 0.6% |
| novelty_critic | 7361 | 0.6% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 577369 |
| critical | 713264 |
| optional | 14833 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 5893 | 62.34 | 356 | narrator=3823, world_simulator=2070 |
| 2 | 7937 | 98.86 | 632 | narrator=4745, world_simulator=3192 |
| 3 | 6796 | 64.64 | 0 | narrator=3907, world_simulator=2889 |
| 4 | 9258 | 121.73 | 458 | narrator=5552, world_simulator=3706 |
| 5 | 12760 | 174.81 | 850 | narrator=4918, world_simulator=4116, showrunner=3726 |
| 6 | 8161 | 94.48 | 751 | narrator=5168, world_simulator=2993 |
| 7 | 8586 | 94.37 | 448 | narrator=5832, world_simulator=2754 |
| 8 | 6496 | 63.08 | 1012 | narrator=4784, world_simulator=1712 |
| 9 | 7747 | 87.64 | 797 | narrator=5042, world_simulator=2705 |
| 10 | 47396 | 431.18 | 1909 | narrator=9465, event_injector=6274, narrative_critic:critique=4754 |
| 11 | 9085 | 108.99 | 496 | narrator=5504, world_simulator=3581 |
| 12 | 7701 | 86.57 | 0 | narrator=4056, world_simulator=3645 |
| 13 | 7150 | 77.85 | 812 | narrator=4691, world_simulator=2459 |
| 14 | 7767 | 80.14 | 641 | narrator=4856, world_simulator=2911 |
| 15 | 10878 | 117.27 | 792 | narrator=5377, showrunner=3350, world_simulator=2151 |
| 16 | 9173 | 109.12 | 352 | narrator=5764, world_simulator=3409 |
| 17 | 7898 | 92.21 | 447 | narrator=5186, world_simulator=2712 |
| 18 | 8026 | 88.89 | 149 | narrator=5465, world_simulator=2561 |
| 19 | 7987 | 96.72 | 397 | narrator=5249, world_simulator=2738 |
| 20 | 16040 | 151.34 | 154 | narrator=5421, showrunner=4430, novelty_critic=3352 |
| 21 | 31436 | 272.61 | 1905 | narrator=6849, event_injector=6118, narrative_critic:critique=4687 |
| 22 | 32607 | 226.84 | 479 | narrator=11088, character_agent:char_jichuan=4302, character_agent:char_linxue=3437 |
| 23 | 32833 | 163.18 | 737 | narrator=6740, character_agent:char_jichuan=4326, character_agent:char_lujiuniang=4290 |
| 24 | 34467 | 164.66 | 1722 | narrator=7160, character_agent:char_lujiuniang=4338, character_agent:char_linxue=4317 |
| 25 | 38024 | 242.15 | 1497 | narrator=7684, showrunner=4648, character_agent:char_fangyanshu=4068 |
| 26 | 37215 | 178.0 | 1649 | narrator=8218, character_agent:char_sumo=4758, character_agent:char_jichuan=4737 |
| 27 | 31981 | 154.14 | 1134 | narrator=7649, character_agent:char_fangyanshu=4635, character_agent:char_jichuan=4202 |
| 28 | 35514 | 191.9 | 509 | narrator=8912, character_agent:char_jichuan=4420, character_agent:char_sumo=4272 |
| 29 | 33523 | 165.77 | 0 | narrator=7769, character_agent:char_linxue=4071, character_agent:char_ading=4042 |
| 30 | 47195 | 238.82 | 1052 | narrator=7672, character_arc_tracker=7472, character_agent:char_fangyanshu=5436 |
| 31 | 36159 | 205.42 | 715 | narrator=9147, character_agent:char_fangyanshu=4460, character_agent:char_ading=4422 |
| 32 | 46757 | 307.32 | 966 | narrator=9943, event_injector=6373, character_agent:char_jichuan=4284 |
| 33 | 33120 | 174.81 | 2639 | narrator=9036, character_agent:char_fangyanshu=4107, character_agent:char_ading=4035 |
| 34 | 36379 | 239.33 | 1641 | narrator=8814, character_agent:char_lujiuniang=5411, character_agent:char_fangyanshu=4985 |
| 35 | 39968 | 245.49 | 1436 | narrator=7825, character_agent:char_ading=5349, character_agent:char_jichuan=5086 |
| 36 | 35226 | 207.42 | 2277 | narrator=8553, character_agent:char_jichuan=5427, character_agent:char_sumo=4516 |
| 37 | 32712 | 152.21 | 1442 | narrator=7903, character_agent:char_ading=4476, character_agent:char_linxue=4457 |
| 38 | 35048 | 189.28 | 1984 | narrator=8644, character_agent:char_jichuan=4437, character_agent:char_ading=4168 |
| 39 | 37380 | 172.75 | 754 | narrator=7649, character_agent:char_linxue=4795, character_agent:char_ading=4707 |
| 40 | 47266 | 272.58 | 290 | narrator=8707, character_agent:char_fangyanshu=6069, character_agent:char_ading=5219 |
| 41 | 38193 | 203.94 | 639 | narrator=8507, character_agent:char_ading=5216, character_agent:char_fangyanshu=4832 |
| 42 | 9363 | 93.51 | 628 | narrator=5867, world_simulator=3496 |
| 43 | 45221 | 261.82 | 0 | narrator=9309, event_injector=5954, character_agent:char_jichuan=5363 |
| 44 | 39853 | 215.91 | 676 | narrator=9088, character_agent:char_jichuan=5715, character_agent:char_linxue=4648 |
| 45 | 39758 | 218.36 | 1033 | narrator=8413, character_agent:char_lujiuniang=5979, character_agent:char_fangyanshu=4558 |
| 46 | 34225 | 140.47 | 699 | narrator=8437, character_agent:char_jichuan=4099, character_agent:char_fangyanshu=3980 |
| 47 | 38381 | 186.37 | 1503 | narrator=8111, character_agent:char_lujiuniang=5825, character_agent:char_fangyanshu=5208 |
| 48 | 35803 | 158.28 | 1093 | narrator=7370, character_agent:char_fangyanshu=5287, character_agent:char_ading=4603 |
| 49 | 37657 | 228.94 | 703 | narrator=8854, character_agent:char_linxue=6476, character_agent:char_sumo=4677 |
| 50 | 39467 | 203.89 | 1405 | narrator=7307, character_agent:char_linxue=5073, showrunner=4364 |

## First narrative sample

```
雨水顺着苏默的后脖颈流进衣领，他缩了缩脖子。街角的告示牌上，新贴的告示正在褪色，水渍从边缘向中心蔓延，吞噬着墨迹。他停下脚步，试图辨认那些正在消融的字。‘……记忆完整度抽检……第七区……未登记副本……’
几个词从潮湿的纸面上浮起，又被下一滴雨水砸碎。他移开视线，靴子踩进泥泞的市场地，拔出来时发出黏腻的声响，留下一个深凹的坑。周围的摊贩在灰蒙蒙的雾霭里蜷缩着，像一块块沉默的石头。远处，闷雷滚过天际，灰白的闪光在雾霭深处闷了一下，短暂地映出建筑物模糊的轮廓。
苏默低头看了看自己的靴子，皮面浸透了水，颜色深得发黑。他从怀里掏出一张折起来的硬纸片，边缘被体温捂得有些软。纸上是他抄录的一段编号，字迹很小，挤在角落。他把纸片又塞了回去，拍了拍胸口。
告示上的字又少了一些。他转身离开，靴子从泥里拔出，留下新鲜的水印。
```
