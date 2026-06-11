# Bench: stage4-seed2-30tick

- novel_id: `bench_stage4-seed2-30tick_1781174098`
- ticks: 30
- bootstrap_sec: 323.32
- tick_durations_sec: [121.34, 128.18, 93.35, 85.14, 173.52, 83.12, 69.57, 106.87, 104.6, 322.3, 113.83, 81.86, 112.5, 80.55, 160.1, 96.69, 110.49, 106.82, 95.38, 205.16, 292.03, 94.17, 132.43, 110.85, 100.71, 81.79, 81.9, 105.14, 109.39, 207.5]
- total_tokens: 307630
- call_count: 74
- narrative_chars_total: 17496
- tokens_per_char: 17.58

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 157038 | 51.0% |
| world_simulator | 90843 | 29.5% |
| showrunner | 24720 | 8.0% |
| event_injector | 9748 | 3.2% |
| character_agent:char_sumo | 6714 | 2.2% |
| character_agent:char_wenzhu | 6292 | 2.0% |
| character_arc_tracker | 5843 | 1.9% |
| novelty_critic | 3384 | 1.1% |
| character_agent:char_watanabe | 3048 | 1.0% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 131603 |
| critical | 166800 |
| optional | 9227 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 8302 | 121.34 | 0 | narrator=5169, world_simulator=3133 |
| 2 | 8731 | 128.18 | 1133 | narrator=5034, world_simulator=3697 |
| 3 | 7738 | 93.35 | 362 | narrator=5377, world_simulator=2361 |
| 4 | 7614 | 85.14 | 156 | narrator=4825, world_simulator=2789 |
| 5 | 12658 | 173.52 | 127 | narrator=5160, showrunner=4163, world_simulator=3335 |
| 6 | 7259 | 83.12 | 742 | narrator=4643, world_simulator=2616 |
| 7 | 6988 | 69.57 | 210 | narrator=5236, world_simulator=1752 |
| 8 | 8120 | 106.87 | 814 | narrator=4808, world_simulator=3312 |
| 9 | 8470 | 104.6 | 943 | narrator=5762, world_simulator=2708 |
| 10 | 28959 | 322.3 | 60 | narrator=7570, event_injector=4618, showrunner=4068 |
| 11 | 8582 | 113.83 | 71 | narrator=5412, world_simulator=3170 |
| 12 | 7299 | 81.86 | 742 | narrator=4335, world_simulator=2964 |
| 13 | 9207 | 112.5 | 4 | narrator=5967, world_simulator=3240 |
| 14 | 7051 | 80.55 | 547 | narrator=4188, world_simulator=2863 |
| 15 | 12409 | 160.1 | 120 | narrator=5783, showrunner=3569, world_simulator=3057 |
| 16 | 7958 | 96.69 | 334 | narrator=5504, world_simulator=2454 |
| 17 | 8890 | 110.49 | 310 | narrator=5688, world_simulator=3202 |
| 18 | 8488 | 106.82 | 808 | narrator=4922, world_simulator=3566 |
| 19 | 8368 | 95.38 | 737 | narrator=5078, world_simulator=3290 |
| 20 | 17434 | 205.16 | 553 | narrator=5325, showrunner=4567, world_simulator=4158 |
| 21 | 23443 | 292.03 | 1591 | narrator=7824, event_injector=5130, character_agent:char_sumo=4139 |
| 22 | 8462 | 94.17 | 1077 | narrator=5311, world_simulator=3151 |
| 23 | 9320 | 132.43 | 3138 | narrator=5992, world_simulator=3328 |
| 24 | 8643 | 110.85 | 342 | narrator=5371, world_simulator=3272 |
| 25 | 6217 | 100.71 | 0 | showrunner=3514, world_simulator=2703 |
| 26 | 7217 | 81.79 | 668 | narrator=4669, world_simulator=2548 |
| 27 | 7600 | 81.9 | 459 | narrator=4914, world_simulator=2686 |
| 28 | 8470 | 105.14 | 379 | narrator=5765, world_simulator=2705 |
| 29 | 8446 | 109.39 | 612 | narrator=5684, world_simulator=2762 |
| 30 | 19287 | 207.5 | 457 | character_arc_tracker=5843, narrator=5722, showrunner=4839 |

## First narrative sample

```
雨又下了一夜。

青石板路被泡得发亮，每一块石头的缝隙里都蓄满了水。苏默的布鞋踩上去，泥水便从边缘渗出来，迅速染黑了灰白的鞋面。他把伞柄上的水又甩了一下。伞骨是旧竹削的，伞面糊的油纸在雨里闷出一股桐油和霉烂混杂的气味。

街两边的店铺大多没开门，偶有一两扇板门半掩着，里面黑洞洞的，只有更深处飘出一点煤烟和稀粥的蒸汽。空气太重了，煤烟味沉在底下，跟泥土和腐烂叶子的腥气搅在一起，吸进肺里发腻。他没停，沿巷子往里走。目标是巷尾那栋灰砖小楼的二层，墨隐社在这片安全屋的窗户永远用厚布帘遮着，但今晚，他得去确认一样东西。

雨幕隔着巷子口，远处湖面的轮廓是一片更浓的灰。芦苇的影子在风里起伏，沙沙的声响隔着雨，闷闷的，像很多人在远处同时翻动书页。他想起圣嘉禄藏书阁那批碳化档案，林雪上周在老地方见面时提过，军统那边有人靠近文本后开始说梦话，内容全是没人见过的古文字，醒来却什么都不记得。渡边诚那边也没好多少，派去的梅机关技术人员，一个向上面提交了完全胡言乱语的破译报告，另一个据说夜里会对着墙壁鞠躬，用谁也听不懂的语言喃喃自语。

水珠从伞沿滴下来，落在他的手背上，冰凉。

安全屋的后门没锁。他推开门，一股更浓的霉味混着纸张受潮后特有的酸气涌出来。木楼梯踩上去吱呀作响，他数着步子，在第七级处稍停，侧耳听了听。楼上没有光，也没有声音。只有雨水顺着瓦檐流下，击打窗台外接水陶瓮的单调声响。他继续上楼，从怀里摸出钥匙，打开了二楼内侧房间那把黄铜锁。

屋内比走廊更黑。他没点灯，先把门在身后关严，湿透的外套脱下来，搭在门边的椅背上，水渍立刻在木头表面洇开一小片深色。然后他走到窗边，掀开厚布帘的一角。巷子里空无一人，只有雨。他放下帘子，这才划亮一根洋火。

火光跳了一下，照亮桌上摊开的一张地图，地图边缘已经受潮卷曲。火柴头快燃尽时，他点燃了桌角那盏小油灯。昏黄的光晕开来，照见地图上几个用红笔圈出的点：十六铺码头，圣嘉禄旧址，还有淀山湖芦荡深处的废弃哨塔。他的手指在码头那个圈上按了按。明天，那批档案残片就要在黑市上开拍。林雪会去，渡边诚的人也会去。

他从桌下拖出一个铁皮箱，打开锁，里面是几份用油布仔细包好的文件。最上面那份的封皮，墨迹已经有些化开，但还能勉强辨认出“梅机关精神诱导实验阶段性记录（摘抄）”的字样。这是陈大壮和文竹冒死从哨塔里带出来的。他用指尖轻轻碰了碰纸页边缘。纸已经软了，摸上去凉，像是还沾着湖水的潮气。

油灯的火苗突然抖了一下。苏默抬起头。

窗外，雨声里混进了一点别的动静。很轻，像是有人踩着湿透的落叶，停在了楼下。

他没动。右手慢慢垂下去，握住了椅腿边那根黑沉沉的包铁木棍。灯光把他握棍的影子投在对面墙上，放大，扭曲，像某种蓄势待发的兽。
```
