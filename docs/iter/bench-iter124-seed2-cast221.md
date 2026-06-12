# Bench: iter124-seed2-cast221

- novel_id: `bench_iter124-seed2-cast221_1781265061`
- ticks: 50
- bootstrap_sec: 352.31
- tick_durations_sec: [60.43, 71.02, 100.29, 87.18, 149.93, 105.83, 97.47, 101.39, 89.12, 298.53, 39.41, 74.94, 76.79, 79.24, 155.17, 102.43, 99.77, 114.23, 108.76, 151.27, 206.13, 94.6, 105.96, 93.41, 140.81, 86.56, 103.27, 104.2, 91.2, 192.43, 71.85, 286.84, 78.72, 104.56, 169.79, 115.99, 79.85, 78.49, 96.78, 133.24, 100.58, 87.6, 276.6, 86.47, 137.32, 75.6, 75.31, 58.38, 95.39, 190.24]
- total_tokens: 533808
- call_count: 128
- narrative_chars_total: 31753
- tokens_per_char: 16.81

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 259209 | 48.6% |
| world_simulator | 144743 | 27.1% |
| showrunner | 46775 | 8.8% |
| event_injector | 18692 | 3.5% |
| character_agent:char_zhaotiezhu | 13930 | 2.6% |
| character_agent:char_sumo | 13219 | 2.5% |
| character_agent:char_guxiansheng | 12211 | 2.3% |
| character_agent:char_linxue | 12138 | 2.3% |
| novelty_critic | 7011 | 1.3% |
| character_arc_tracker | 5880 | 1.1% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 236351 |
| critical | 284566 |
| optional | 12891 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 5754 | 60.43 | 0 | narrator=4053, world_simulator=1701 |
| 2 | 6508 | 71.02 | 631 | narrator=3876, world_simulator=2632 |
| 3 | 8057 | 100.29 | 582 | narrator=4495, world_simulator=3562 |
| 4 | 7675 | 87.18 | 316 | narrator=5493, world_simulator=2182 |
| 5 | 12021 | 149.93 | 589 | narrator=5122, showrunner=4241, world_simulator=2658 |
| 6 | 8591 | 105.83 | 0 | narrator=5605, world_simulator=2986 |
| 7 | 8143 | 97.47 | 1190 | narrator=5040, world_simulator=3103 |
| 8 | 8659 | 101.39 | 650 | narrator=4804, world_simulator=3855 |
| 9 | 7665 | 89.12 | 636 | narrator=5097, world_simulator=2568 |
| 10 | 27793 | 298.53 | 840 | narrator=7229, event_injector=4541, showrunner=4383 |
| 11 | 2733 | 39.41 | 0 | world_simulator=2733 |
| 12 | 7370 | 74.94 | 873 | narrator=4898, world_simulator=2472 |
| 13 | 7524 | 76.79 | 820 | narrator=4604, world_simulator=2920 |
| 14 | 7555 | 79.24 | 571 | narrator=5756, world_simulator=1799 |
| 15 | 12808 | 155.17 | 603 | showrunner=4808, narrator=4780, world_simulator=3220 |
| 16 | 8546 | 102.43 | 0 | narrator=5488, world_simulator=3058 |
| 17 | 8628 | 99.77 | 428 | narrator=5538, world_simulator=3090 |
| 18 | 8637 | 114.23 | 974 | narrator=4903, world_simulator=3734 |
| 19 | 8713 | 108.76 | 0 | narrator=5422, world_simulator=3291 |
| 20 | 16284 | 151.27 | 1138 | narrator=5200, showrunner=4934, novelty_critic=3450 |
| 21 | 21621 | 206.13 | 2180 | narrator=6631, character_agent:char_zhaotiezhu=4457, character_agent:char_guxiansheng=4272 |
| 22 | 8303 | 94.6 | 377 | narrator=5672, world_simulator=2631 |
| 23 | 8349 | 105.96 | 1086 | narrator=5239, world_simulator=3110 |
| 24 | 8293 | 93.41 | 836 | narrator=5727, world_simulator=2566 |
| 25 | 12157 | 140.81 | 1088 | narrator=5514, showrunner=3930, world_simulator=2713 |
| 26 | 7973 | 86.56 | 697 | narrator=4747, world_simulator=3226 |
| 27 | 8923 | 103.27 | 641 | narrator=5311, world_simulator=3612 |
| 28 | 8613 | 104.2 | 256 | narrator=5566, world_simulator=3047 |
| 29 | 7639 | 91.2 | 691 | narrator=4298, world_simulator=3341 |
| 30 | 18767 | 192.43 | 992 | character_arc_tracker=5880, showrunner=5029, narrator=4920 |
| 31 | 7359 | 71.85 | 668 | narrator=5626, world_simulator=1733 |
| 32 | 33085 | 286.84 | 2469 | narrator=9552, event_injector=5188, character_agent:char_guxiansheng=4213 |
| 33 | 7845 | 78.72 | 642 | narrator=4964, world_simulator=2881 |
| 34 | 8473 | 104.56 | 4 | narrator=5601, world_simulator=2872 |
| 35 | 12873 | 169.79 | 0 | narrator=5038, showrunner=5027, world_simulator=2808 |
| 36 | 8737 | 115.99 | 0 | narrator=5089, world_simulator=3648 |
| 37 | 6987 | 79.85 | 938 | narrator=4342, world_simulator=2645 |
| 38 | 7804 | 78.49 | 806 | narrator=4882, world_simulator=2922 |
| 39 | 8516 | 96.78 | 746 | narrator=5509, world_simulator=3007 |
| 40 | 15344 | 133.24 | 763 | showrunner=5062, narrator=4989, novelty_critic=3561 |
| 41 | 8789 | 100.58 | 62 | narrator=5735, world_simulator=3054 |
| 42 | 7489 | 87.6 | 549 | narrator=4460, world_simulator=3029 |
| 43 | 36270 | 276.6 | 169 | narrator=8556, event_injector=5638, character_agent:char_zhaotiezhu=5439 |
| 44 | 7730 | 86.47 | 983 | narrator=4362, world_simulator=3368 |
| 45 | 12184 | 137.32 | 962 | narrator=4784, showrunner=4578, world_simulator=2822 |
| 46 | 7577 | 75.6 | 0 | narrator=4148, world_simulator=3429 |
| 47 | 7628 | 75.31 | 334 | narrator=5339, world_simulator=2289 |
| 48 | 6439 | 58.38 | 536 | narrator=4643, world_simulator=1796 |
| 49 | 7991 | 95.39 | 972 | narrator=4905, world_simulator=3086 |
| 50 | 14386 | 190.24 | 465 | narrator=5657, showrunner=4783, world_simulator=3946 |

## First narrative sample

```
雾里人影一晃，就没了。脚步声从栈道那头移过来，靴子踩在湿木板上，噗噗的闷响，节奏整齐。苏墨蹲在货箱后面，手指抠着木板边缘的霉斑，数着步数。十步，二十步……声音渐渐被雨声盖过。他等了足有一分钟，直到心跳从喉咙口落回胸腔。

雨更大了。水珠顺着仓库的瓦檐往下淌，连成一条抖动的线。他站起来，膝盖发麻，用手抹了把脸上的水汽。档案库的铁门就在二十步外，雾里显出暗沉沉的一块。他得过去。怀里揣着的那几页纸——从旧货栈捡来的、字迹模糊的航运记录残片——贴着皮肤，已经被体温焐得有些发软。

栈道上的积水没过了鞋底。他低头快走，鞋面拍打水面，溅起的水珠打在裤腿上。一艘乌篷船在旁边的雾里轻轻晃着，缆绳绷紧，发出“吱呀”的细响，像有人在磨牙。

钥匙插进锁孔，转动时很涩。他用力推，铁门发出沉重的“嘎”声，一股更浓重的潮气混着旧纸和霉味涌出来。里面的光很暗，只有高处几扇气窗透进灰蒙蒙的天光。他侧身挤进去，反手把门掩到只剩一条缝。

不是全黑。他适应了一下，能看见成排的档案架，金属的，高耸入天花板。湿气在这里凝成了可见的雾丝，缓慢浮动。滴答。很轻的一声。他循声看去，最靠近墙的一排架子顶部，有水珠正在凝聚，拉长，然后滴落。下面正对着几叠平放的档案，牛皮纸封面已经洇开深色的水渍。

他走过去，伸手碰了碰那叠纸。冰凉，潮湿。纸页边缘已经开始发皱卷曲。得挪开。他踮起脚，双手去抱最上面那几盒。手指刚碰到盒盖，又一滴水落下来，正砸在他的手背上，冰得他一缩。

外面，雨声密得像鼓点。
```
