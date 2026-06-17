# Bench: phase5j-longrange-seed2-republic

- novel_id: `bench_phase5j-longrange-seed2-republic_1781689578`
- ticks: 100
- bootstrap_sec: 322.77
- tick_durations_sec: [51.37, 0.02, 0.02, 52.08, 17.32, 0.02, 45.73, 0.02, 0.02, 320.71, 56.4, 0.03, 0.03, 50.86, 16.99, 0.02, 52.69, 0.02, 0.03, 65.79, 110.46, 55.35, 0.02, 0.02, 74.91, 0.02, 0.02, 45.93, 0.02, 39.08, 50.76, 79.37, 51.81, 0.02, 14.43, 58.78, 0.02, 0.02, 51.24, 34.2, 0.02, 49.21, 204.58, 73.49, 15.93, 0.03, 44.41, 0.02, 0.03, 70.49, 0.02, 0.02, 51.74, 132.86, 66.8, 0.02, 0.02, 55.04, 0.02, 41.73, 54.84, 0.02, 0.02, 54.01, 205.65, 55.27, 0.02, 0.02, 63.98, 19.76, 0.02, 61.64, 0.05, 0.04, 67.72, 112.24, 74.8, 0.03, 0.03, 67.24, 0.03, 0.03, 59.5, 0.02, 16.8, 55.6, 182.9, 46.35, 0.02, 52.59, 44.83, 0.03, 0.03, 46.51, 17.3, 0.03, 44.27, 93.28, 51.38, 71.78]
- total_tokens: 423141
- call_count: 146
- narrative_chars_total: 50749
- tokens_per_char: 8.34

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 200876 | 47.5% |
| showrunner | 53014 | 12.5% |
| world_simulator | 44440 | 10.5% |
| event_injector | 29919 | 7.1% |
| character_agent:char_zhaotianyou | 22800 | 5.4% |
| narrative_critic:rewrite | 17535 | 4.1% |
| narrative_critic:critique | 15861 | 3.7% |
| character_arc_tracker | 9792 | 2.3% |
| character_agent:char_gumingyuan | 9538 | 2.3% |
| novelty_critic | 6657 | 1.6% |
| character_agent:char_liangchen | 4773 | 1.1% |
| character_agent:char_shenruyue | 4530 | 1.1% |
| memory_compressor:l0_l1 | 3406 | 0.8% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 136911 |
| critical | 266375 |
| optional | 19855 |

## Cache hit rate (Phase 5-A)

- total prompt_tokens: 314926
- total cached_tokens: 0
- overall hit rate: 0.0%

| agent | prompt | cached | hit% |
| --- | ---: | ---: | ---: |
| narrator | 152577 | 0 | 0.0% |
| showrunner | 43611 | 0 | 0.0% |
| world_simulator | 27007 | 0 | 0.0% |
| event_injector | 23393 | 0 | 0.0% |
| character_agent:char_zhaotianyou | 17355 | 0 | 0.0% |
| narrative_critic:critique | 12858 | 0 | 0.0% |
| narrative_critic:rewrite | 9730 | 0 | 0.0% |
| character_arc_tracker | 7325 | 0 | 0.0% |
| character_agent:char_gumingyuan | 7177 | 0 | 0.0% |
| novelty_critic | 4563 | 0 | 0.0% |
| character_agent:char_liangchen | 3596 | 0 | 0.0% |
| character_agent:char_shenruyue | 3438 | 0 | 0.0% |
| memory_compressor:l0_l1 | 2296 | 0 | 0.0% |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 4444 | 51.37 | 874 | narrator=3399, world_simulator=1045 |
| 2 | 0 | 0.02 | 0 |  |
| 3 | 0 | 0.02 | 0 |  |
| 4 | 5040 | 52.08 | 1067 | narrator=4063, world_simulator=977 |
| 5 | 2488 | 17.32 | 0 | showrunner=2488 |
| 6 | 0 | 0.02 | 0 |  |
| 7 | 4981 | 45.73 | 824 | narrator=3963, world_simulator=1018 |
| 8 | 0 | 0.02 | 0 |  |
| 9 | 0 | 0.02 | 0 |  |
| 10 | 29503 | 320.71 | 3834 | narrator=7125, narrative_critic:rewrite=6022, narrative_critic:critique=4598 |
| 11 | 5656 | 56.4 | 1054 | narrator=4177, world_simulator=1479 |
| 12 | 0 | 0.03 | 0 |  |
| 13 | 0 | 0.03 | 0 |  |
| 14 | 5038 | 50.86 | 878 | narrator=4000, world_simulator=1038 |
| 15 | 2610 | 16.99 | 0 | showrunner=2610 |
| 16 | 0 | 0.02 | 0 |  |
| 17 | 5114 | 52.69 | 880 | narrator=4024, world_simulator=1090 |
| 18 | 0 | 0.02 | 0 |  |
| 19 | 0 | 0.03 | 0 |  |
| 20 | 8775 | 65.79 | 830 | narrator=4011, showrunner=2709, novelty_critic=1029 |
| 21 | 11233 | 110.46 | 1799 | narrator=5500, event_injector=3358, character_agent:char_zhaotianyou=2375 |
| 22 | 5541 | 55.35 | 876 | narrator=4094, world_simulator=1447 |
| 23 | 0 | 0.02 | 0 |  |
| 24 | 0 | 0.02 | 0 |  |
| 25 | 7989 | 74.91 | 1099 | narrator=4271, showrunner=2637, world_simulator=1081 |
| 26 | 0 | 0.02 | 0 |  |
| 27 | 0 | 0.02 | 0 |  |
| 28 | 5016 | 45.93 | 721 | narrator=3936, world_simulator=1080 |
| 29 | 0 | 0.02 | 0 |  |
| 30 | 5209 | 39.08 | 0 | character_arc_tracker=2612, showrunner=2597 |
| 31 | 5088 | 50.76 | 813 | narrator=3933, world_simulator=1155 |
| 32 | 9991 | 79.37 | 835 | narrator=4601, event_injector=3188, character_agent:char_gumingyuan=2202 |
| 33 | 5385 | 51.81 | 788 | narrator=4003, world_simulator=1382 |
| 34 | 0 | 0.02 | 0 |  |
| 35 | 2577 | 14.43 | 0 | showrunner=2577 |
| 36 | 5380 | 58.78 | 1071 | narrator=4242, world_simulator=1138 |
| 37 | 0 | 0.02 | 0 |  |
| 38 | 0 | 0.02 | 0 |  |
| 39 | 5203 | 51.24 | 876 | narrator=4090, world_simulator=1113 |
| 40 | 4052 | 34.2 | 0 | showrunner=2644, novelty_critic=1408 |
| 41 | 0 | 0.02 | 0 |  |
| 42 | 5148 | 49.21 | 801 | narrator=4033, world_simulator=1115 |
| 43 | 22035 | 204.58 | 2178 | narrator=6053, narrative_critic:rewrite=4126, narrative_critic:critique=3760 |
| 44 | 8542 | 73.49 | 840 | narrator=4633, character_agent:char_zhaotianyou=2470, world_simulator=1439 |
| 45 | 2636 | 15.93 | 0 | showrunner=2636 |
| 46 | 0 | 0.03 | 0 |  |
| 47 | 5045 | 44.41 | 653 | narrator=3922, world_simulator=1123 |
| 48 | 0 | 0.02 | 0 |  |
| 49 | 0 | 0.03 | 0 |  |
| 50 | 7884 | 70.49 | 987 | narrator=4088, showrunner=2707, world_simulator=1089 |
| 51 | 0 | 0.02 | 0 |  |
| 52 | 0 | 0.02 | 0 |  |
| 53 | 5357 | 51.74 | 977 | narrator=4207, world_simulator=1150 |
| 54 | 14783 | 132.86 | 2911 | narrator=6561, event_injector=3195, character_agent:char_gumingyuan=2534 |
| 55 | 8202 | 66.8 | 909 | narrator=4155, showrunner=2650, world_simulator=1397 |
| 56 | 0 | 0.02 | 0 |  |
| 57 | 0 | 0.02 | 0 |  |
| 58 | 5398 | 55.04 | 930 | narrator=4217, world_simulator=1181 |
| 59 | 0 | 0.02 | 0 |  |
| 60 | 7365 | 41.73 | 0 | character_arc_tracker=3316, showrunner=2652, novelty_critic=1397 |
| 61 | 5399 | 54.84 | 933 | narrator=4155, world_simulator=1244 |
| 62 | 0 | 0.02 | 0 |  |
| 63 | 0 | 0.02 | 0 |  |
| 64 | 5359 | 54.01 | 978 | narrator=4164, world_simulator=1195 |
| 65 | 24697 | 205.65 | 1613 | narrator=5980, narrative_critic:critique=3776, narrative_critic:rewrite=3659 |
| 66 | 5744 | 55.27 | 850 | narrator=4149, world_simulator=1595 |
| 67 | 0 | 0.02 | 0 |  |
| 68 | 0 | 0.02 | 0 |  |
| 69 | 5828 | 63.98 | 1341 | narrator=4569, world_simulator=1259 |
| 70 | 2732 | 19.76 | 0 | showrunner=2732 |
| 71 | 0 | 0.02 | 0 |  |
| 72 | 5682 | 61.64 | 1204 | narrator=4394, world_simulator=1288 |
| 73 | 0 | 0.05 | 0 |  |
| 74 | 0 | 0.04 | 0 |  |
| 75 | 7976 | 67.72 | 806 | narrator=4092, showrunner=2690, world_simulator=1194 |
| 76 | 11679 | 112.24 | 1881 | narrator=5605, event_injector=3430, character_agent:char_zhaotianyou=2644 |
| 77 | 8723 | 74.8 | 1022 | narrator=4760, character_agent:char_zhaotianyou=2578, world_simulator=1385 |
| 78 | 0 | 0.03 | 0 |  |
| 79 | 0 | 0.03 | 0 |  |
| 80 | 9325 | 67.24 | 818 | narrator=4119, showrunner=2707, novelty_critic=1285 |
| 81 | 0 | 0.03 | 0 |  |
| 82 | 0 | 0.03 | 0 |  |
| 83 | 5404 | 59.5 | 1076 | narrator=4235, world_simulator=1169 |
| 84 | 0 | 0.02 | 0 |  |
| 85 | 2763 | 16.8 | 0 | showrunner=2763 |
| 86 | 5267 | 55.6 | 1073 | narrator=4206, world_simulator=1061 |
| 87 | 21277 | 182.9 | 1765 | narrator=5965, narrative_critic:rewrite=3728, narrative_critic:critique=3727 |
| 88 | 5381 | 46.35 | 685 | narrator=3963, world_simulator=1418 |
| 89 | 0 | 0.02 | 0 |  |
| 90 | 6542 | 52.59 | 0 | character_arc_tracker=3864, showrunner=2678 |
| 91 | 5020 | 44.83 | 723 | narrator=3920, world_simulator=1100 |
| 92 | 0 | 0.03 | 0 |  |
| 93 | 0 | 0.03 | 0 |  |
| 94 | 5067 | 46.51 | 794 | narrator=3974, world_simulator=1093 |
| 95 | 2684 | 17.3 | 0 | showrunner=2684 |
| 96 | 0 | 0.03 | 0 |  |
| 97 | 5017 | 44.27 | 695 | narrator=3895, world_simulator=1122 |
| 98 | 13678 | 93.28 | 1436 | narrator=5329, event_injector=3225, character_agent:char_zhaotianyou=2636 |
| 99 | 5630 | 51.38 | 751 | narrator=4101, world_simulator=1529 |
| 100 | 7559 | 71.78 | 0 | memory_compressor:l0_l1=3406, showrunner=2615, novelty_critic=1538 |

## First narrative sample

```
雨打在帆布篷上，声音像砂石筛过铁网。

苏默把咖啡杯推到桌边。瓷底刮过铁皮桌面，留下一道水痕。杯里的残液已经凉透，表面浮着一层油光。他没再碰。

沿街的排水管涌出铁锈色的水，在人行道边缘冲开一道浅沟。梧桐叶贴在地上，叶脉间积着泥。一辆黑色福特从街角拐过来，轮胎碾过水洼，泥点溅上咖啡馆的玻璃窗。

苏默看着那辆车。它没有加速，也没有减速。

车窗是黑色的，雨刷在挡风玻璃上刮出两道弧。车子经过咖啡馆门口时，后座窗帘动了一下——不是风，是手指拨开的缝隙。

他把手伸进外套内侧。锡盒的棱角隔着衬衫抵住肋骨，金属的温度还没被体温捂热。胶片在盒子里轻微晃动，发出极细的摩擦声。

福特车在街尾停下。尾灯在雨雾中晕成两团红。

没有人下车。

苏默站起身，把几张法币压在杯子底下。纸币边角卷起，他用指节敲了敲桌面，让侍应生看见。然后推开玻璃门。

雨立刻打湿了他的肩膀。冷意从领口灌进去，沿着脊椎往下走。他没有缩脖子，也没有加快脚步。

往南是码头。往北是租界。

他选了第三条路——穿过梧桐夹道的小巷，往河岸方向走。巷子里堆着鱼贩丢弃的木箱，雨水泡烂了箱底的稻草，散发出咸腥和朽木混合的气味。一只野猫蹲在箱子上，盯着他经过，瞳孔收成一条线。

身后传来车门打开又关上的声音。两声。间隔很短。

他没有回头。

巷子尽头是河。灰白色的水雾从水面升起，对岸货栈的轮廓像泡在显影液里的底片，模糊，但正在成形。铁皮屋顶的锈迹在雨水中蔓延，一滴锈水悬在屋檐边缘，拉长，坠落，砸在下方的麻袋上。

拖船的汽笛从远处传来，低沉，拖着尾音。

苏默在河岸边的石阶上停下。石阶长满青苔，缝隙里积着烟蒂和碎贝壳。他蹲下身，假装系鞋带，手指探进石阶下的暗槽。

空的。

他收回手，指尖沾了泥。

脚步声在巷子里停下了。不是走错路的停下——是看见目标后的停顿。

苏默站起来，转过身。

巷口站着两个人。雨衣帽檐压得很低，遮住了大半张脸。其中一个把手插在口袋里，口袋鼓起一块。

不是手枪的形状。

是警棍。

“苏先生。”左边那个开口，声音被雨声削得很薄，“梁警官想见你。”
```
