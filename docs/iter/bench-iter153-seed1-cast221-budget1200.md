# Bench: iter153-seed1-cast221-budget1200

- novel_id: `bench_iter153-seed1-cast221-budget1200_1781352542`
- ticks: 50
- bootstrap_sec: 321.91
- tick_durations_sec: [97.62, 143.3, 116.83, 115.47, 189.74, 114.69, 125.02, 131.28, 148.87, 374.11, 104.62, 115.93, 120.03, 678.97, 349.95, 202.31, 600.06, 102.46, 171.68, 244.18, 212.3, 79.81, 87.91, 101.31, 148.06, 97.67, 96.65, 107.39, 76.93, 168.46, 84.54, 177.37, 95.25, 102.03, 147.76, 93.32, 84.48, 83.17, 120.77, 153.56, 87.96, 76.0, 187.25, 98.49, 146.33, 93.87, 72.97, 88.52, 91.7, 157.07]
- total_tokens: 499825
- call_count: 120
- narrative_chars_total: 31482
- tokens_per_char: 15.88

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 256242 | 51.3% |
| world_simulator | 140571 | 28.1% |
| showrunner | 52536 | 10.5% |
| event_injector | 19055 | 3.8% |
| novelty_critic | 7060 | 1.4% |
| character_agent:char_zhaotie | 6548 | 1.3% |
| narrative_critic:rewrite | 3913 | 0.8% |
| character_arc_tracker | 3838 | 0.8% |
| narrative_critic:critique | 3760 | 0.8% |
| character_agent:char_linxue | 3224 | 0.6% |
| character_agent:char_sumo | 3078 | 0.6% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 218710 |
| critical | 270217 |
| optional | 10898 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6681 | 97.62 | 652 | narrator=3942, world_simulator=2739 |
| 2 | 8864 | 143.3 | 1193 | narrator=5481, world_simulator=3383 |
| 3 | 8134 | 116.83 | 1148 | narrator=5042, world_simulator=3092 |
| 4 | 8129 | 115.47 | 0 | narrator=5731, world_simulator=2398 |
| 5 | 13661 | 189.74 | 1130 | narrator=5526, showrunner=5315, world_simulator=2820 |
| 6 | 8440 | 114.69 | 691 | narrator=5810, world_simulator=2630 |
| 7 | 8416 | 125.02 | 1283 | narrator=5585, world_simulator=2831 |
| 8 | 8635 | 131.28 | 0 | narrator=5758, world_simulator=2877 |
| 9 | 9299 | 148.87 | 944 | narrator=5922, world_simulator=3377 |
| 10 | 27439 | 374.11 | 2032 | narrator=6856, showrunner=5590, event_injector=5144 |
| 11 | 7918 | 104.62 | 668 | narrator=4694, world_simulator=3224 |
| 12 | 8318 | 115.93 | 847 | narrator=4947, world_simulator=3371 |
| 13 | 8694 | 120.03 | 823 | narrator=5569, world_simulator=3125 |
| 14 | 3551 | 678.97 | 0 | world_simulator=3551 |
| 15 | 13028 | 349.95 | 1087 | showrunner=5603, narrator=5151, world_simulator=2274 |
| 16 | 8164 | 202.31 | 589 | narrator=5869, world_simulator=2295 |
| 17 | 0 | 600.06 | 0 |  |
| 18 | 6689 | 102.46 | 679 | narrator=5277, world_simulator=1412 |
| 19 | 8834 | 171.68 | 0 | narrator=5795, world_simulator=3039 |
| 20 | 18090 | 244.18 | 246 | narrator=5784, showrunner=5484, novelty_critic=3618 |
| 21 | 19500 | 212.3 | 1072 | narrator=5229, event_injector=4953, narrative_critic:critique=3760 |
| 22 | 7672 | 79.81 | 880 | narrator=5089, world_simulator=2583 |
| 23 | 7874 | 87.91 | 923 | narrator=5057, world_simulator=2817 |
| 24 | 8887 | 101.31 | 0 | narrator=5917, world_simulator=2970 |
| 25 | 14224 | 148.06 | 130 | narrator=5847, showrunner=4957, world_simulator=3420 |
| 26 | 7923 | 97.67 | 758 | narrator=4812, world_simulator=3111 |
| 27 | 8350 | 96.65 | 755 | narrator=5755, world_simulator=2595 |
| 28 | 8811 | 107.39 | 987 | narrator=5645, world_simulator=3166 |
| 29 | 7489 | 76.93 | 747 | narrator=4767, world_simulator=2722 |
| 30 | 17976 | 168.46 | 0 | narrator=5648, showrunner=5153, character_arc_tracker=3838 |
| 31 | 7719 | 84.54 | 791 | narrator=4994, world_simulator=2725 |
| 32 | 15629 | 177.37 | 493 | narrator=5120, event_injector=4081, narrative_critic:rewrite=3913 |
| 33 | 8846 | 95.25 | 637 | narrator=5500, world_simulator=3346 |
| 34 | 8820 | 102.03 | 14 | narrator=5699, world_simulator=3121 |
| 35 | 12851 | 147.76 | 406 | showrunner=5341, narrator=4794, world_simulator=2716 |
| 36 | 8167 | 93.32 | 609 | narrator=4831, world_simulator=3336 |
| 37 | 8194 | 84.48 | 14 | narrator=5530, world_simulator=2664 |
| 38 | 7288 | 83.17 | 484 | narrator=3964, world_simulator=3324 |
| 39 | 9105 | 120.77 | 23 | narrator=5379, world_simulator=3726 |
| 40 | 15769 | 153.56 | 658 | narrator=5009, showrunner=4848, novelty_critic=3442 |
| 41 | 7645 | 87.96 | 775 | narrator=4797, world_simulator=2848 |
| 42 | 7467 | 76.0 | 349 | narrator=5670, world_simulator=1797 |
| 43 | 16162 | 187.25 | 978 | narrator=5464, event_injector=4877, character_agent:char_zhaotie=3611 |
| 44 | 8811 | 98.49 | 590 | narrator=5268, world_simulator=3543 |
| 45 | 12659 | 146.33 | 543 | showrunner=4948, narrator=4373, world_simulator=3338 |
| 46 | 8207 | 93.87 | 905 | narrator=5101, world_simulator=3106 |
| 47 | 7216 | 72.97 | 1121 | narrator=5419, world_simulator=1797 |
| 48 | 7952 | 88.52 | 966 | narrator=5213, world_simulator=2739 |
| 49 | 8154 | 91.7 | 858 | narrator=5724, world_simulator=2430 |
| 50 | 13474 | 157.07 | 4 | narrator=5888, showrunner=5297, world_simulator=2289 |

## First narrative sample

```
雨砸下来的时候，苏默正蹲在一块翻翘的铁板后面。

铁板原先是某个棚屋的顶盖，锈穿了，边缘卷起来像一片巨大的枯叶。雨水打在上面噼啪作响，顺着锈孔往下淌，淌进苏默后颈。他缩了缩，没挪地方——因为雾里有东西在动。

距离不好判断。浓雾把所有距离都吃掉了。能看见的只有轮廓：一团比雾色更深的黑影，在二十步外、也许三十步外的废墟间缓慢移动。不是风。风不会那样停顿。

苏默把手探进外套内侧，指尖碰到卷宗的硬纸壳边缘。还硬。还没被雨水泡软。他往里又按了按，确认封蜡没开，手才抽出来。

雾更浓了一层。黑影不见了。

他数了二十个心跳。没有第二下脚步声，没有兽类喘息。也许是野犬，也许是拾荒的游民，也许是帝国巡街的机械驮犬——白天锈蚀集市上有人提过，入秋以后南区的巡逻加密了。苏默当时没在意。现在他把每一句闲话都想了一遍。

积水已经没过鞋底。脚趾在湿袜子里发胀。他低头看那片铁板——上面有道旧刻痕，被人用尖锐的东西划过，笔画歪扭，像某个字的起笔又没有写完。他盯着看了两秒，辨认不出来。也许什么都不是。

雨更大了。棚屋残架发出吱嘎声，某根支撑杆在风里微微晃。苏默站起来，膝盖嘎巴响了一下。他把帽檐压低，侧耳又听。

除了雨声和金属被敲打的噼啪声，什么都没有。

他迈出铁板的遮蔽，朝集市方向走了三步，又停住。

地上多了一排印痕。不是他的鞋印。是某种更深、更窄的压痕，像沉重的机械足交替踩过积水留下的凹陷，已经被雨水填了大半。印痕从他左侧延伸向前方的雾幕，方向跟他要去的地方一样。

苏默把外套领子立起来，跟了上去。
```
