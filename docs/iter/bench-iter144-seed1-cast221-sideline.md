# Bench: iter144-seed1-cast221-sideline

- novel_id: `bench_iter144-seed1-cast221-sideline_1781321931`
- ticks: 50
- bootstrap_sec: 464.12
- tick_durations_sec: [97.37, 117.55, 133.2, 113.74, 160.67, 108.91, 103.15, 142.34, 144.69, 428.19, 93.14, 147.57, 119.43, 74.91, 151.41, 125.96, 114.54, 97.87, 124.77, 186.53, 343.51, 101.99, 105.11, 94.82, 179.76, 122.99, 102.95, 105.45, 102.95, 194.77, 110.6, 223.32, 153.3, 117.29, 177.19, 108.69, 100.63, 99.78, 127.04, 143.8, 79.06, 101.64, 279.2, 92.28, 189.92, 96.99, 132.66, 111.27, 93.2, 206.09]
- total_tokens: 495119
- call_count: 123
- narrative_chars_total: 41167
- tokens_per_char: 12.03

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 248255 | 50.1% |
| world_simulator | 140412 | 28.4% |
| showrunner | 51567 | 10.4% |
| event_injector | 19900 | 4.0% |
| character_agent:char_linxue | 8150 | 1.6% |
| novelty_critic | 6799 | 1.4% |
| character_arc_tracker | 5084 | 1.0% |
| character_agent:char_yanhong | 4235 | 0.9% |
| narrative_critic:critique | 4150 | 0.8% |
| character_agent:char_sumo | 3563 | 0.7% |
| character_agent:char_zhaotieshan | 3004 | 0.6% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 219118 |
| critical | 264118 |
| optional | 11883 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6261 | 97.37 | 562 | narrator=3609, world_simulator=2652 |
| 2 | 7433 | 117.55 | 590 | narrator=4765, world_simulator=2668 |
| 3 | 8338 | 133.2 | 449 | narrator=5128, world_simulator=3210 |
| 4 | 7314 | 113.74 | 381 | narrator=4146, world_simulator=3168 |
| 5 | 10526 | 160.67 | 879 | narrator=4606, showrunner=4493, world_simulator=1427 |
| 6 | 7469 | 108.91 | 708 | narrator=4163, world_simulator=3306 |
| 7 | 6875 | 103.15 | 0 | narrator=4439, world_simulator=2436 |
| 8 | 8020 | 142.34 | 496 | narrator=5285, world_simulator=2735 |
| 9 | 8205 | 144.69 | 767 | narrator=4841, world_simulator=3364 |
| 10 | 28898 | 428.19 | 1034 | narrator=6617, showrunner=5171, character_agent:char_linxue=4810 |
| 11 | 7277 | 93.14 | 0 | narrator=4053, world_simulator=3224 |
| 12 | 8791 | 147.57 | 379 | narrator=5464, world_simulator=3327 |
| 13 | 7573 | 119.43 | 312 | narrator=5111, world_simulator=2462 |
| 14 | 5891 | 74.91 | 772 | narrator=4255, world_simulator=1636 |
| 15 | 11961 | 151.41 | 789 | showrunner=5012, narrator=4263, world_simulator=2686 |
| 16 | 8433 | 125.96 | 346 | narrator=5207, world_simulator=3226 |
| 17 | 7635 | 114.54 | 479 | narrator=4528, world_simulator=3107 |
| 18 | 6765 | 97.87 | 830 | narrator=4252, world_simulator=2513 |
| 19 | 7833 | 124.77 | 902 | narrator=4555, world_simulator=3278 |
| 20 | 15672 | 186.53 | 913 | showrunner=5340, narrator=4774, novelty_critic=3375 |
| 21 | 23640 | 343.51 | 1166 | narrator=7392, event_injector=5881, narrative_critic:critique=4150 |
| 22 | 7553 | 101.99 | 1890 | narrator=5310, world_simulator=2243 |
| 23 | 8254 | 105.11 | 793 | narrator=5435, world_simulator=2819 |
| 24 | 7848 | 94.82 | 733 | narrator=5057, world_simulator=2791 |
| 25 | 13572 | 179.76 | 640 | showrunner=5409, narrator=4595, world_simulator=3568 |
| 26 | 8149 | 122.99 | 782 | narrator=5098, world_simulator=3051 |
| 27 | 7900 | 102.95 | 1171 | narrator=5307, world_simulator=2593 |
| 28 | 7878 | 105.45 | 858 | narrator=5253, world_simulator=2625 |
| 29 | 7859 | 102.95 | 684 | narrator=4227, world_simulator=3632 |
| 30 | 17218 | 194.77 | 1111 | showrunner=5107, character_arc_tracker=5084, narrator=4268 |
| 31 | 8055 | 110.6 | 0 | narrator=5323, world_simulator=2732 |
| 32 | 15596 | 223.32 | 2085 | narrator=5915, event_injector=4645, character_agent:char_zhaotieshan=3004 |
| 33 | 9504 | 153.3 | 3160 | narrator=5361, world_simulator=4143 |
| 34 | 8218 | 117.29 | 77 | narrator=5426, world_simulator=2792 |
| 35 | 12720 | 177.19 | 1558 | showrunner=5345, narrator=4904, world_simulator=2471 |
| 36 | 7769 | 108.69 | 1304 | narrator=4966, world_simulator=2803 |
| 37 | 7642 | 100.63 | 784 | narrator=4839, world_simulator=2803 |
| 38 | 7591 | 99.78 | 806 | narrator=4804, world_simulator=2787 |
| 39 | 8456 | 127.04 | 2031 | narrator=5333, world_simulator=3123 |
| 40 | 15362 | 143.8 | 273 | narrator=5340, showrunner=4890, novelty_critic=3424 |
| 41 | 6607 | 79.06 | 480 | narrator=4299, world_simulator=2308 |
| 42 | 7683 | 101.64 | 464 | narrator=5024, world_simulator=2659 |
| 43 | 17728 | 279.2 | 0 | narrator=6778, event_injector=4627, character_agent:char_linxue=3340 |
| 44 | 7655 | 92.28 | 402 | narrator=4382, world_simulator=3273 |
| 45 | 13073 | 189.92 | 738 | showrunner=5402, narrator=4430, world_simulator=3241 |
| 46 | 7527 | 96.99 | 812 | narrator=4652, world_simulator=2875 |
| 47 | 8663 | 132.66 | 353 | narrator=5487, world_simulator=3176 |
| 48 | 7638 | 111.27 | 1993 | narrator=5105, world_simulator=2533 |
| 49 | 7212 | 93.2 | 1180 | narrator=5087, world_simulator=2125 |
| 50 | 13379 | 206.09 | 1251 | showrunner=5398, narrator=4797, world_simulator=3184 |

## First narrative sample

```
嘶嘶声是从街角的接缝处逃出来的。灰白的蒸汽裹着铁锈味，贴地蔓延，和铅灰色的薄雾搅在一起，把巷子两头的轮廓都吞掉了。苏墨压低帽檐，手插在旧大衣口袋里，指尖摸到那枚冰冷的铜齿轮钥匙。远处，齿轮工厂的轰鸣穿过雾气传来，一下，又一下，沉闷得像这座城市的心跳。他得穿过三条街，去旧档案馆。

风忽然转了向，卷起地上混着煤灰的碎屑，打着旋儿升起来，形成一个矮小的尘卷，挡在他前面的路上。他停下脚步，眯起眼。尘卷里似乎有什么东西一闪——不是垃圾，是某种规整的金属反光，很小，瞬间就被灰烬遮住了。工厂的轰鸣节奏没变，但苏墨耳朵里，那声音好像和刚才漏气的嘶嘶声叠在了一起，合成一种新的、让人牙酸的频率。

他绕过尘卷，靴子踩在湿漉漉的卵石上，发出空洞的回响。雾更浓了。下一个路口，原本该亮着的煤气路灯灭了，黑黢黢的灯柱下，堆着一些看不清原貌的废弃零件。苏墨没停，脚步反而快了些。钥匙在口袋里硌着掌心。

旧档案馆的铁门出现在雾中，像一头蹲伏的巨兽剪影。门没关严，留着一道缝。苏墨推门，铰链发出刺耳的呻吟。门内比外面更暗，弥漫着纸张、尘土和另一种淡淡霉味的气息。寂静突然压下来，把外面工厂的轰鸣隔成了遥远的背景音。

“我到了。”他对着黑暗的门厅说，声音不大。没有人应答。只有他自己的呼吸声，和远处某个房间传来的、极其轻微的、纸张翻动的沙沙声。
```
