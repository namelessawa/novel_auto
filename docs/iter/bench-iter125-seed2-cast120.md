# Bench: iter125-seed2-cast120

- novel_id: `bench_iter125-seed2-cast120_1781271372`
- ticks: 50
- bootstrap_sec: 295.32
- tick_durations_sec: [30.53, 97.07, 56.2, 75.64, 150.99, 61.55, 74.67, 101.14, 91.67, 255.95, 74.0, 85.94, 92.09, 98.08, 103.03, 75.35, 80.37, 117.8, 92.28, 136.73, 249.68, 113.65, 85.28, 89.77, 151.13, 92.13, 101.71, 86.94, 72.74, 180.69, 136.36, 264.6, 168.72, 129.07, 144.35, 99.22, 114.6, 120.74, 129.47, 202.46, 125.63, 169.0, 313.26, 113.47, 197.76, 157.48, 111.34, 85.86, 163.35, 211.07]
- total_tokens: 484134
- call_count: 121
- narrative_chars_total: 22176
- tokens_per_char: 21.83

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 253339 | 52.3% |
| world_simulator | 142469 | 29.4% |
| showrunner | 40537 | 8.4% |
| event_injector | 19944 | 4.1% |
| character_agent:char_chenkang | 7835 | 1.6% |
| novelty_critic | 7028 | 1.5% |
| character_agent:char_linxue | 6411 | 1.3% |
| character_arc_tracker | 4106 | 0.8% |
| character_agent:char_sumo | 2465 | 0.5% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 213250 |
| critical | 259750 |
| optional | 11134 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 2022 | 30.53 | 0 | world_simulator=2022 |
| 2 | 7832 | 97.07 | 0 | narrator=4499, world_simulator=3333 |
| 3 | 5767 | 56.2 | 487 | narrator=4215, world_simulator=1552 |
| 4 | 7252 | 75.64 | 253 | narrator=4983, world_simulator=2269 |
| 5 | 11933 | 150.99 | 993 | showrunner=4557, narrator=4476, world_simulator=2900 |
| 6 | 7073 | 61.55 | 0 | narrator=4443, world_simulator=2630 |
| 7 | 7589 | 74.67 | 56 | narrator=5843, world_simulator=1746 |
| 8 | 8340 | 101.14 | 377 | narrator=4899, world_simulator=3441 |
| 9 | 7914 | 91.67 | 748 | narrator=4703, world_simulator=3211 |
| 10 | 21137 | 255.95 | 328 | narrator=6376, event_injector=4545, showrunner=4241 |
| 11 | 7419 | 74.0 | 466 | narrator=5041, world_simulator=2378 |
| 12 | 7790 | 85.94 | 0 | narrator=5438, world_simulator=2352 |
| 13 | 6979 | 92.09 | 846 | narrator=4659, world_simulator=2320 |
| 14 | 8348 | 98.08 | 816 | narrator=5001, world_simulator=3347 |
| 15 | 10063 | 103.03 | 482 | narrator=4831, showrunner=3227, world_simulator=2005 |
| 16 | 7232 | 75.35 | 0 | narrator=5402, world_simulator=1830 |
| 17 | 7699 | 80.37 | 0 | narrator=5588, world_simulator=2111 |
| 18 | 9453 | 117.8 | 705 | narrator=5631, world_simulator=3822 |
| 19 | 8322 | 92.28 | 510 | narrator=5814, world_simulator=2508 |
| 20 | 15121 | 136.73 | 0 | narrator=4662, showrunner=3681, novelty_critic=3576 |
| 21 | 18714 | 249.68 | 1702 | narrator=6322, event_injector=4745, character_agent:char_chenkang=4460 |
| 22 | 9497 | 113.65 | 917 | narrator=5008, world_simulator=4489 |
| 23 | 8049 | 85.28 | 4 | narrator=5727, world_simulator=2322 |
| 24 | 7623 | 89.77 | 333 | narrator=5110, world_simulator=2513 |
| 25 | 12927 | 151.13 | 331 | narrator=5452, showrunner=4335, world_simulator=3140 |
| 26 | 8036 | 92.13 | 328 | narrator=5407, world_simulator=2629 |
| 27 | 7926 | 101.71 | 1431 | narrator=5199, world_simulator=2727 |
| 28 | 8080 | 86.94 | 944 | narrator=4814, world_simulator=3266 |
| 29 | 7258 | 72.74 | 704 | narrator=4729, world_simulator=2529 |
| 30 | 16342 | 180.69 | 67 | narrator=4865, showrunner=4156, character_arc_tracker=4106 |
| 31 | 8502 | 136.36 | 531 | narrator=5125, world_simulator=3377 |
| 32 | 17259 | 264.6 | 1020 | event_injector=5644, narrator=5356, world_simulator=3221 |
| 33 | 10516 | 168.72 | 291 | narrator=5627, world_simulator=4889 |
| 34 | 8262 | 129.07 | 0 | narrator=5260, world_simulator=3002 |
| 35 | 10276 | 144.35 | 516 | narrator=4772, showrunner=3941, world_simulator=1563 |
| 36 | 7305 | 99.22 | 635 | narrator=4457, world_simulator=2848 |
| 37 | 7664 | 114.6 | 560 | narrator=4867, world_simulator=2797 |
| 38 | 7904 | 120.74 | 480 | narrator=4490, world_simulator=3414 |
| 39 | 8432 | 129.47 | 0 | narrator=5394, world_simulator=3038 |
| 40 | 15450 | 202.46 | 0 | showrunner=4769, narrator=4277, novelty_critic=3452 |
| 41 | 7602 | 125.63 | 735 | narrator=4975, world_simulator=2627 |
| 42 | 9073 | 169.0 | 0 | narrator=5728, world_simulator=3345 |
| 43 | 20533 | 313.26 | 1565 | narrator=6726, event_injector=5010, character_agent:char_linxue=3373 |
| 44 | 8184 | 113.47 | 866 | narrator=5284, world_simulator=2900 |
| 45 | 12570 | 197.76 | 0 | narrator=5880, showrunner=3868, world_simulator=2822 |
| 46 | 9083 | 157.48 | 0 | narrator=5858, world_simulator=3225 |
| 47 | 7475 | 111.34 | 767 | narrator=4882, world_simulator=2593 |
| 48 | 6887 | 85.86 | 0 | narrator=4165, world_simulator=2722 |
| 49 | 9213 | 163.35 | 6 | narrator=5897, world_simulator=3316 |
| 50 | 12207 | 211.07 | 376 | narrator=5182, showrunner=3762, world_simulator=3263 |

## First narrative sample

```
雨声敲打在铁皮上，密集得让人听不出间隙。苏墨将档案馆侧门推开一道缝，潮气扑面而来。

码头方向传来汽笛，一声接一声，沉闷地撞进浓雾里，比昨日更急。他低头看了看积水，没过鞋底已经冰凉。沼泽的泥腥气混在雨水里，漫过石板路。

“苏警探。”

声音来自廊下阴影。陈抗靠在立柱旁，半边身子被雨水打湿。“你这里也不安全。”他没抬头，视线落在苏墨手中的牛皮纸袋上。

“你更不安全。”苏墨把纸袋塞进内袋，压紧。“特高课的人在码头换了班次。汽笛不是报时，是信号。”

陈抗的指尖在柱子上敲了两下。“童谣里唱了。‘钟声停，船笛起，沼泽吞没黑衣人。’”

“林雪呢？”

“在安全屋。记忆又碎了一些。”陈抗终于转过脸，眼下有青黑。“她今早一直在哼调子，但填词变了。说档案馆的地板下面，有东西在腐烂。”

苏默握了握拳。纸张受潮的细微声响从内袋传来，像是档案在呼吸。屋顶的雨滴声忽然变调，从急促转为沉闷的鼓点。

“巡捕房的线断了。”苏墨说，“特高课知道有人在查哨所。他们先处理档案，再处理人。”

陈抗从柱子边走开，靴子踩进积水，溅起水花。“那我们就先到沼泽里去。黑衣人总得找个地方沉下去。”
```
