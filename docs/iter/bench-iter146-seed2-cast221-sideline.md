# Bench: iter146-seed2-cast221-sideline

- novel_id: `bench_iter146-seed2-cast221-sideline_1781329787`
- ticks: 50
- bootstrap_sec: 354.73
- tick_durations_sec: [106.14, 78.9, 62.13, 96.91, 189.39, 84.21, 94.97, 124.88, 122.28, 445.06, 93.61, 83.5, 110.57, 127.05, 224.78, 87.33, 110.24, 81.51, 65.63, 184.58, 235.16, 145.18, 153.55, 120.43, 153.43, 106.0, 132.97, 105.99, 121.01, 281.92, 112.39, 290.65, 83.59, 144.76, 212.45, 127.75, 132.87, 112.57, 120.12, 200.51, 112.97, 123.24, 330.28, 121.95, 219.02, 110.42, 123.94, 115.67, 123.87, 219.39]
- total_tokens: 536113
- call_count: 125
- narrative_chars_total: 28855
- tokens_per_char: 18.58

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 271258 | 50.6% |
| world_simulator | 146439 | 27.3% |
| showrunner | 51394 | 9.6% |
| event_injector | 23014 | 4.3% |
| character_agent:char_linxue | 15750 | 2.9% |
| character_agent:char_sumo | 12856 | 2.4% |
| novelty_critic | 6825 | 1.3% |
| character_arc_tracker | 5593 | 1.0% |
| character_agent:char_lutanzhang | 2984 | 0.6% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 223831 |
| critical | 299864 |
| optional | 12418 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 7499 | 106.14 | 455 | narrator=4800, world_simulator=2699 |
| 2 | 7010 | 78.9 | 803 | narrator=4739, world_simulator=2271 |
| 3 | 6765 | 62.13 | 539 | narrator=5076, world_simulator=1689 |
| 4 | 7421 | 96.91 | 759 | narrator=5484, world_simulator=1937 |
| 5 | 13402 | 189.39 | 656 | showrunner=5082, narrator=5067, world_simulator=3253 |
| 6 | 7301 | 84.21 | 745 | narrator=5693, world_simulator=1608 |
| 7 | 7678 | 94.97 | 1079 | narrator=5104, world_simulator=2574 |
| 8 | 8914 | 124.88 | 519 | narrator=5771, world_simulator=3143 |
| 9 | 8598 | 122.28 | 548 | narrator=5228, world_simulator=3370 |
| 10 | 32098 | 445.06 | 573 | narrator=7891, event_injector=5956, showrunner=5286 |
| 11 | 7812 | 93.61 | 664 | narrator=4855, world_simulator=2957 |
| 12 | 7228 | 83.5 | 543 | narrator=5370, world_simulator=1858 |
| 13 | 8376 | 110.57 | 448 | narrator=5424, world_simulator=2952 |
| 14 | 8661 | 127.05 | 309 | narrator=5503, world_simulator=3158 |
| 15 | 14696 | 224.78 | 0 | narrator=5464, showrunner=5404, world_simulator=3828 |
| 16 | 7124 | 87.33 | 389 | narrator=5384, world_simulator=1740 |
| 17 | 8225 | 110.24 | 4 | narrator=5583, world_simulator=2642 |
| 18 | 6582 | 81.51 | 554 | narrator=4489, world_simulator=2093 |
| 19 | 6363 | 65.63 | 620 | narrator=4767, world_simulator=1596 |
| 20 | 15982 | 184.58 | 649 | showrunner=5387, narrator=4551, novelty_critic=3278 |
| 21 | 16419 | 235.16 | 1301 | narrator=5740, event_injector=5385, character_agent:char_linxue=3687 |
| 22 | 9558 | 145.18 | 856 | narrator=5212, world_simulator=4346 |
| 23 | 9200 | 153.55 | 0 | narrator=5715, world_simulator=3485 |
| 24 | 8376 | 120.43 | 1259 | narrator=5180, world_simulator=3196 |
| 25 | 11888 | 153.43 | 831 | narrator=5754, showrunner=3449, world_simulator=2685 |
| 26 | 8052 | 106.0 | 605 | narrator=5446, world_simulator=2606 |
| 27 | 9133 | 132.97 | 0 | narrator=5692, world_simulator=3441 |
| 28 | 8078 | 105.99 | 601 | narrator=5781, world_simulator=2297 |
| 29 | 8653 | 121.01 | 0 | narrator=5737, world_simulator=2916 |
| 30 | 20510 | 281.92 | 550 | narrator=5775, character_arc_tracker=5593, showrunner=5514 |
| 31 | 8245 | 112.39 | 184 | narrator=5778, world_simulator=2467 |
| 32 | 25981 | 290.65 | 1413 | narrator=6636, event_injector=5258, character_agent:char_linxue=4179 |
| 33 | 7514 | 83.59 | 0 | narrator=4408, world_simulator=3106 |
| 34 | 9009 | 144.76 | 1996 | narrator=5934, world_simulator=3075 |
| 35 | 14097 | 212.45 | 180 | narrator=5874, showrunner=4881, world_simulator=3342 |
| 36 | 8769 | 127.75 | 1 | narrator=5452, world_simulator=3317 |
| 37 | 8517 | 132.87 | 4 | narrator=5262, world_simulator=3255 |
| 38 | 7417 | 112.57 | 590 | narrator=4389, world_simulator=3028 |
| 39 | 8262 | 120.12 | 466 | narrator=5466, world_simulator=2796 |
| 40 | 17161 | 200.51 | 828 | narrator=5242, showrunner=5229, novelty_critic=3547 |
| 41 | 7980 | 112.97 | 778 | narrator=4884, world_simulator=3096 |
| 42 | 8267 | 123.24 | 731 | narrator=4894, world_simulator=3373 |
| 43 | 24563 | 330.28 | 802 | narrator=6717, event_injector=6415, character_agent:char_sumo=3845 |
| 44 | 8865 | 121.95 | 634 | narrator=4949, world_simulator=3916 |
| 45 | 14838 | 219.02 | 0 | narrator=5737, showrunner=5444, world_simulator=3657 |
| 46 | 8033 | 110.42 | 744 | narrator=4969, world_simulator=3064 |
| 47 | 9067 | 123.94 | 404 | narrator=5899, world_simulator=3168 |
| 48 | 8201 | 115.67 | 0 | narrator=5029, world_simulator=3172 |
| 49 | 8457 | 123.87 | 826 | narrator=5718, world_simulator=2739 |
| 50 | 15268 | 219.39 | 1415 | narrator=5746, showrunner=5718, world_simulator=3804 |

## First narrative sample

```
路灯在雾里洇成一团黄，边缘毛糙，像褪色的水渍。石板路面泛着微光，苏默的鞋底踩上去，水声很轻。远处闸北方向有人在喊，声音被雾气吞掉一半，只剩调子拖长的尾巴。

他停在梧桐树下。树干粗壮，皮裂得厉害。叶子落得差不多了，剩几片枯黄的挂在枝头，被雨打得发黏。

霞飞路137号在街对面。法式建筑，三层，外墙是旧的米黄色灰泥，雨水冲刷出一道道深色水痕。二楼靠东的窗户亮着灯，窗帘拉得严实，只透出昏黄的光。这么晚了，档案馆不该有人。

苏默摸出怀里的纸条。纸角已经起毛，是被人反复折过又展开的痕迹。字迹潦草，墨水洇开几处："霞飞路，十三，子时。"他第三次确认地址，确认时辰。字条是三天前塞进他门缝的，没有署名，没有回信地址。只有一股旧纸箱的霉味。

十六铺方向传来汽笛声。沉闷的长音，穿过半个租界，拖到最后变成嗡嗡的低鸣，钻进耳朵里。

他把纸条塞回内袋，抬头看那扇窗。灯光还在。窗帘后面，有一个模糊的影子晃了一下，很快又静止。是人影，还是他自己眼花？

细雨变密。水珠顺着帽檐滑下来，滴在他手背上，凉。

然后，灯灭了。
```
