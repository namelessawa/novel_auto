# Bench: iter127-seed3-cast120

- novel_id: `bench_iter127-seed3-cast120_1781285705`
- ticks: 50
- bootstrap_sec: 294.81
- tick_durations_sec: [84.76, 75.71, 83.45, 101.98, 133.26, 76.75, 65.17, 90.05, 95.61, 555.11, 111.8, 76.94, 87.91, 89.65, 168.86, 115.85, 70.17, 110.17, 92.59, 171.6, 463.11, 105.47, 99.26, 79.7, 144.36, 73.26, 91.29, 78.89, 92.82, 147.42, 95.31, 443.22, 62.73, 97.34, 151.1, 75.66, 116.7, 94.06, 109.22, 139.21, 102.21, 93.87, 490.64, 92.83, 127.34, 110.09, 83.48, 84.07, 62.01, 130.25]
- total_tokens: 502482
- call_count: 123
- narrative_chars_total: 28976
- tokens_per_char: 17.34

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 268565 | 53.4% |
| world_simulator | 139228 | 27.7% |
| showrunner | 46315 | 9.2% |
| event_injector | 18011 | 3.6% |
| character_agent:char_sumo | 12083 | 2.4% |
| character_agent:char_linxue | 9138 | 1.8% |
| novelty_critic | 6067 | 1.2% |
| character_arc_tracker | 3075 | 0.6% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 215637 |
| critical | 277703 |
| optional | 9142 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6687 | 84.76 | 490 | narrator=4236, world_simulator=2451 |
| 2 | 6992 | 75.71 | 0 | narrator=4429, world_simulator=2563 |
| 3 | 7391 | 83.45 | 358 | narrator=5451, world_simulator=1940 |
| 4 | 7865 | 101.98 | 1491 | narrator=5077, world_simulator=2788 |
| 5 | 11340 | 133.26 | 783 | narrator=4944, showrunner=3839, world_simulator=2557 |
| 6 | 7200 | 76.75 | 878 | narrator=5141, world_simulator=2059 |
| 7 | 6681 | 65.17 | 562 | narrator=4800, world_simulator=1881 |
| 8 | 7681 | 90.05 | 938 | narrator=4911, world_simulator=2770 |
| 9 | 8318 | 95.61 | 0 | narrator=5670, world_simulator=2648 |
| 10 | 21090 | 555.11 | 1031 | narrator=7456, showrunner=4551, event_injector=3658 |
| 11 | 8737 | 111.8 | 1345 | narrator=5378, world_simulator=3359 |
| 12 | 7238 | 76.94 | 648 | narrator=4935, world_simulator=2303 |
| 13 | 8038 | 87.91 | 469 | narrator=5634, world_simulator=2404 |
| 14 | 7663 | 89.65 | 1045 | narrator=4896, world_simulator=2767 |
| 15 | 13759 | 168.86 | 703 | narrator=5632, showrunner=4964, world_simulator=3163 |
| 16 | 9175 | 115.85 | 0 | narrator=5729, world_simulator=3446 |
| 17 | 7227 | 70.17 | 0 | narrator=4699, world_simulator=2528 |
| 18 | 9123 | 110.17 | 1239 | narrator=5603, world_simulator=3520 |
| 19 | 8571 | 92.59 | 983 | narrator=5031, world_simulator=3540 |
| 20 | 17709 | 171.6 | 181 | narrator=5861, showrunner=4476, world_simulator=3855 |
| 21 | 21870 | 463.11 | 0 | narrator=7701, event_injector=4641, character_agent:char_sumo=3630 |
| 22 | 9193 | 105.47 | 597 | narrator=5573, world_simulator=3620 |
| 23 | 9295 | 99.26 | 0 | narrator=5848, world_simulator=3447 |
| 24 | 7912 | 79.7 | 740 | narrator=5165, world_simulator=2747 |
| 25 | 13218 | 144.36 | 946 | narrator=5517, showrunner=5388, world_simulator=2313 |
| 26 | 7605 | 73.26 | 922 | narrator=5030, world_simulator=2575 |
| 27 | 8531 | 91.29 | 149 | narrator=5825, world_simulator=2706 |
| 28 | 7255 | 78.89 | 520 | narrator=4446, world_simulator=2809 |
| 29 | 8162 | 92.82 | 454 | narrator=5514, world_simulator=2648 |
| 30 | 15635 | 147.42 | 0 | showrunner=5390, narrator=4319, character_arc_tracker=3075 |
| 31 | 8486 | 95.31 | 0 | narrator=5509, world_simulator=2977 |
| 32 | 16744 | 443.22 | 538 | narrator=6931, event_injector=4528, character_agent:char_sumo=3724 |
| 33 | 6720 | 62.73 | 684 | narrator=4818, world_simulator=1902 |
| 34 | 8717 | 97.34 | 380 | narrator=5787, world_simulator=2930 |
| 35 | 12756 | 151.1 | 825 | narrator=4957, showrunner=4612, world_simulator=3187 |
| 36 | 7506 | 75.66 | 992 | narrator=4934, world_simulator=2572 |
| 37 | 8619 | 116.7 | 999 | narrator=5672, world_simulator=2947 |
| 38 | 8373 | 94.06 | 8 | narrator=5833, world_simulator=2540 |
| 39 | 8125 | 109.22 | 859 | narrator=4384, world_simulator=3741 |
| 40 | 14755 | 139.21 | 6 | narrator=5765, showrunner=4437, novelty_critic=2550 |
| 41 | 8519 | 102.21 | 0 | narrator=5096, world_simulator=3423 |
| 42 | 8261 | 93.87 | 0 | narrator=5186, world_simulator=3075 |
| 43 | 22950 | 490.64 | 1669 | narrator=6383, event_injector=5184, character_agent:char_sumo=4729 |
| 44 | 8756 | 92.83 | 940 | narrator=5137, world_simulator=3619 |
| 45 | 12091 | 127.34 | 698 | narrator=5130, showrunner=4155, world_simulator=2806 |
| 46 | 8981 | 110.09 | 158 | narrator=5723, world_simulator=3258 |
| 47 | 7711 | 83.48 | 539 | narrator=4698, world_simulator=3013 |
| 48 | 7899 | 84.07 | 1040 | narrator=5049, world_simulator=2850 |
| 49 | 7082 | 62.01 | 587 | narrator=5588, world_simulator=1494 |
| 50 | 12270 | 130.25 | 582 | narrator=5534, showrunner=4503, world_simulator=2233 |

## First narrative sample

```
沙尘暴的尖啸又高了半个音阶。苏默把呼吸压进喉咙，侧身穿过港口的铁栅栏。薄冰在脚下碎裂，发出脆响。远处的船桅杆在风里拧出干涩的嘎吱声，像骨头在断裂。他拉紧领口，粗粝的沙粒打进眼角。街道上的废弃告示牌被风掀动，铁皮刮着水泥地，一下，又一下。建筑缝隙里灌出低沉的呼啸，像什么东西在喘。

档案管理会大楼的轮廓在黄雾里晃。苏默低头走，靴子陷进积沙。他绕过一处新堆起的沙丘，靴底踩到硬物——是半截塑封的档案袋，边角磨损，字迹被沙粒磨花了。他弯腰捡起来，指尖拂过封面：“燃料配给记录，霜降季，第三批。”日期是七天前的。

风把他往前推。大楼的灯光在百米外跳了一下，暗了，又亮，像接触不良。他加快脚步。门口的登记处空着，玻璃窗上蒙着厚厚一层灰。他推门进去，风沙被隔在门外，耳朵里嗡嗡响。大厅的照明灯管只剩两根亮着，光线昏黄，照出空气中悬浮的微尘。

值班台后面的空椅子还在转，吱呀作响。苏默把档案袋放在台面上，手指敲了敲。没人应。他听见走廊深处传来争吵声，隔着门，听不清词句，只有一高一低的音调撞在一起。灯又闪了一下。这次暗了更久，再亮起来时，光线暗了一档。他盯着灯管，里面的钨丝在细微地颤抖。
```
