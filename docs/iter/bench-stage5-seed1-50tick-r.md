# Bench: stage5-seed1-50tick-r

- novel_id: `bench_stage5-seed1-50tick-r_1781188010`
- ticks: 50
- bootstrap_sec: 362.77
- tick_durations_sec: [102.27, 120.85, 127.5, 147.11, 186.16, 160.95, 119.23, 140.22, 115.71, 402.18, 176.59, 114.76, 103.04, 73.02, 151.88, 67.39, 125.45, 137.46, 122.44, 224.42, 365.99, 142.52, 131.67, 134.37, 179.03, 120.3, 141.43, 133.05, 170.63, 199.86, 142.88, 353.2, 117.18, 119.22, 218.87, 152.55, 131.97, 130.18, 123.13, 207.41, 127.58, 134.12, 318.34, 143.62, 214.83, 126.19, 105.1, 125.15, 110.71, 189.1]
- total_tokens: 521767
- call_count: 123
- narrative_chars_total: 31532
- tokens_per_char: 16.55

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 263742 | 50.5% |
| world_simulator | 152399 | 29.2% |
| showrunner | 40964 | 7.9% |
| event_injector | 18144 | 3.5% |
| character_agent:char_sumo | 12994 | 2.5% |
| character_agent:char_linxue | 12498 | 2.4% |
| narrative_critic:critique | 12164 | 2.3% |
| novelty_critic | 6946 | 1.3% |
| character_arc_tracker | 1916 | 0.4% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 211507 |
| critical | 301398 |
| optional | 8862 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6760 | 102.27 | 267 | narrator=4490, world_simulator=2270 |
| 2 | 7652 | 120.85 | 812 | narrator=4449, world_simulator=3203 |
| 3 | 8483 | 127.5 | 761 | narrator=5617, world_simulator=2866 |
| 4 | 8868 | 147.11 | 874 | narrator=5689, world_simulator=3179 |
| 5 | 11641 | 186.16 | 900 | narrator=5906, showrunner=3660, world_simulator=2075 |
| 6 | 9015 | 160.95 | 1621 | narrator=5965, world_simulator=3050 |
| 7 | 7852 | 119.23 | 812 | narrator=5117, world_simulator=2735 |
| 8 | 8910 | 140.22 | 456 | narrator=5938, world_simulator=2972 |
| 9 | 7881 | 115.71 | 496 | narrator=4738, world_simulator=3143 |
| 10 | 26512 | 402.18 | 1238 | narrator=5985, showrunner=4435, event_injector=4202 |
| 11 | 9238 | 176.59 | 736 | narrator=5581, world_simulator=3657 |
| 12 | 7499 | 114.76 | 178 | narrator=5877, world_simulator=1622 |
| 13 | 6603 | 103.04 | 602 | narrator=4595, world_simulator=2008 |
| 14 | 2840 | 73.02 | 0 | world_simulator=2840 |
| 15 | 6747 | 151.88 | 0 | showrunner=4143, world_simulator=2604 |
| 16 | 2935 | 67.39 | 0 | world_simulator=2935 |
| 17 | 8133 | 125.45 | 735 | narrator=5562, world_simulator=2571 |
| 18 | 8833 | 137.46 | 787 | narrator=5626, world_simulator=3207 |
| 19 | 8564 | 122.44 | 899 | narrator=5485, world_simulator=3079 |
| 20 | 16844 | 224.42 | 623 | narrator=5740, showrunner=4306, world_simulator=3410 |
| 21 | 27296 | 365.99 | 1239 | narrator=6805, event_injector=4929, character_agent:char_sumo=4375 |
| 22 | 9649 | 142.52 | 837 | narrator=5530, world_simulator=4119 |
| 23 | 8768 | 131.67 | 406 | narrator=5977, world_simulator=2791 |
| 24 | 8676 | 134.37 | 0 | narrator=5645, world_simulator=3031 |
| 25 | 11839 | 179.03 | 709 | narrator=5297, showrunner=3307, world_simulator=3235 |
| 26 | 8185 | 120.3 | 745 | narrator=5110, world_simulator=3075 |
| 27 | 9278 | 141.43 | 563 | narrator=5947, world_simulator=3331 |
| 28 | 8790 | 133.05 | 0 | narrator=5837, world_simulator=2953 |
| 29 | 9752 | 170.63 | 1073 | narrator=5385, world_simulator=4367 |
| 30 | 14551 | 199.86 | 724 | narrator=5257, showrunner=3963, world_simulator=3415 |
| 31 | 8894 | 142.88 | 1551 | narrator=5849, world_simulator=3045 |
| 32 | 23703 | 353.2 | 925 | narrator=7110, character_agent:char_sumo=4771, event_injector=4629 |
| 33 | 8559 | 117.18 | 768 | narrator=4993, world_simulator=3566 |
| 34 | 8321 | 119.22 | 730 | narrator=5670, world_simulator=2651 |
| 35 | 13368 | 218.87 | 285 | narrator=5923, showrunner=4594, world_simulator=2851 |
| 36 | 9255 | 152.55 | 0 | narrator=5612, world_simulator=3643 |
| 37 | 8356 | 131.97 | 919 | narrator=5138, world_simulator=3218 |
| 38 | 8678 | 130.18 | 1337 | narrator=5679, world_simulator=2999 |
| 39 | 8674 | 123.13 | 841 | narrator=5307, world_simulator=3367 |
| 40 | 16294 | 207.41 | 853 | narrator=5162, showrunner=4710, novelty_critic=3558 |
| 41 | 8647 | 127.58 | 893 | narrator=5813, world_simulator=2834 |
| 42 | 8935 | 134.12 | 610 | narrator=5153, world_simulator=3782 |
| 43 | 22178 | 318.34 | 906 | narrator=6283, character_agent:char_linxue=4577, event_injector=4384 |
| 44 | 9286 | 143.62 | 0 | narrator=6032, world_simulator=3254 |
| 45 | 13263 | 214.83 | 0 | narrator=6059, showrunner=3715, world_simulator=3489 |
| 46 | 8896 | 126.19 | 654 | narrator=5980, world_simulator=2916 |
| 47 | 7848 | 105.1 | 758 | narrator=5297, world_simulator=2551 |
| 48 | 8793 | 125.15 | 345 | narrator=6037, world_simulator=2756 |
| 49 | 8066 | 110.71 | 0 | narrator=5744, world_simulator=2322 |
| 50 | 13159 | 189.1 | 64 | narrator=5751, showrunner=4131, world_simulator=3277 |

## First narrative sample

```
苏默拉紧油布外套的领口，酸雨顺着帽檐滴落，在石砖上溅开铁锈色的水花。街道两旁，齿轮状建筑的排水管将雨水汇聚成溪流，冲刷着地面油污，发出持续的潺潺声。水流混入街角的积水，泛起一圈圈浑浊的涟漪。远处，汽笛声穿透铅灰色的酸雾，从码头方向传来。煤渣被雨水浸透，散发出刺鼻的硫磺味，随着风飘进巷子。苏默低头快步走着，靴子踩过水洼，溅湿了裤脚。他拐过一个街角，排水管的流水声突然变大，头顶的齿轮雕塑在雾中缓缓转动，锈蚀的关节发出吱呀声。他停下脚步，从外套内袋摸出一块怀表，表盘玻璃裂了一道纹。他按开表盖，秒针还在走。合上表，他继续朝巷子深处走去。
```
