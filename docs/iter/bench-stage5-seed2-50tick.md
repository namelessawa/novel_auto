# Bench: stage5-seed2-50tick

- novel_id: `bench_stage5-seed2-50tick_1781196517`
- ticks: 50
- bootstrap_sec: 370.45
- tick_durations_sec: [111.86, 96.75, 89.43, 88.06, 166.23, 120.18, 78.07, 132.41, 115.14, 326.15, 105.05, 107.39, 95.7, 102.79, 137.89, 132.2, 103.39, 99.5, 92.37, 141.2, 232.79, 111.54, 98.81, 88.7, 134.51, 99.61, 103.63, 102.44, 118.98, 192.25, 93.1, 242.76, 137.04, 115.13, 175.49, 95.59, 62.95, 102.74, 76.83, 173.13, 111.36, 85.72, 227.77, 74.07, 158.4, 87.95, 76.67, 92.06, 105.59, 176.33]
- total_tokens: 483857
- call_count: 121
- narrative_chars_total: 25111
- tokens_per_char: 19.27

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 264025 | 54.6% |
| world_simulator | 140678 | 29.1% |
| showrunner | 36008 | 7.4% |
| event_injector | 19025 | 3.9% |
| character_agent:char_linxue | 12911 | 2.7% |
| novelty_critic | 7203 | 1.5% |
| character_arc_tracker | 4007 | 0.8% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 195711 |
| critical | 276936 |
| optional | 11210 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6944 | 111.86 | 145 | narrator=5025, world_simulator=1919 |
| 2 | 6987 | 96.75 | 464 | narrator=4707, world_simulator=2280 |
| 3 | 6957 | 89.43 | 680 | narrator=4452, world_simulator=2505 |
| 4 | 6999 | 88.06 | 799 | narrator=4827, world_simulator=2172 |
| 5 | 11409 | 166.23 | 997 | narrator=4917, showrunner=3257, world_simulator=3235 |
| 6 | 8309 | 120.18 | 763 | narrator=5432, world_simulator=2877 |
| 7 | 6983 | 78.07 | 580 | narrator=4625, world_simulator=2358 |
| 8 | 8620 | 132.41 | 90 | narrator=5579, world_simulator=3041 |
| 9 | 7607 | 115.14 | 0 | narrator=5238, world_simulator=2369 |
| 10 | 20812 | 326.15 | 0 | narrator=7059, event_injector=5542, showrunner=3498 |
| 11 | 8446 | 105.05 | 213 | narrator=5449, world_simulator=2997 |
| 12 | 7934 | 107.39 | 648 | narrator=5046, world_simulator=2888 |
| 13 | 7952 | 95.7 | 974 | narrator=5249, world_simulator=2703 |
| 14 | 8204 | 102.79 | 831 | narrator=5295, world_simulator=2909 |
| 15 | 11248 | 137.89 | 875 | narrator=5734, world_simulator=2786, showrunner=2728 |
| 16 | 9000 | 132.2 | 834 | narrator=5324, world_simulator=3676 |
| 17 | 8243 | 103.39 | 4 | narrator=5840, world_simulator=2403 |
| 18 | 6999 | 99.5 | 516 | narrator=3878, world_simulator=3121 |
| 19 | 7398 | 92.37 | 771 | narrator=4552, world_simulator=2846 |
| 20 | 14996 | 141.2 | 179 | narrator=5731, novelty_critic=3549, showrunner=3493 |
| 21 | 16014 | 232.79 | 788 | narrator=5018, event_injector=4507, character_agent:char_linxue=3738 |
| 22 | 8512 | 111.54 | 333 | narrator=5756, world_simulator=2756 |
| 23 | 7647 | 98.81 | 0 | narrator=5454, world_simulator=2193 |
| 24 | 7519 | 88.7 | 50 | narrator=5511, world_simulator=2008 |
| 25 | 10321 | 134.51 | 499 | narrator=4070, showrunner=3368, world_simulator=2883 |
| 26 | 7863 | 99.61 | 646 | narrator=4688, world_simulator=3175 |
| 27 | 8348 | 103.63 | 498 | narrator=5820, world_simulator=2528 |
| 28 | 7836 | 102.44 | 453 | narrator=4743, world_simulator=3093 |
| 29 | 8643 | 118.98 | 202 | narrator=5640, world_simulator=3003 |
| 30 | 15708 | 192.25 | 0 | narrator=4030, character_arc_tracker=4007, showrunner=3917 |
| 31 | 7839 | 93.1 | 600 | narrator=4607, world_simulator=3232 |
| 32 | 17344 | 242.76 | 869 | narrator=5824, event_injector=4825, character_agent:char_linxue=3888 |
| 33 | 9786 | 137.04 | 30 | narrator=5926, world_simulator=3860 |
| 34 | 8166 | 115.13 | 937 | narrator=4493, world_simulator=3673 |
| 35 | 12879 | 175.49 | 295 | narrator=5966, showrunner=3765, world_simulator=3148 |
| 36 | 7768 | 95.59 | 808 | narrator=4462, world_simulator=3306 |
| 37 | 7093 | 62.95 | 0 | narrator=4410, world_simulator=2683 |
| 38 | 8357 | 102.74 | 733 | narrator=5420, world_simulator=2937 |
| 39 | 7126 | 76.83 | 562 | narrator=4874, world_simulator=2252 |
| 40 | 16697 | 173.13 | 0 | narrator=5756, showrunner=4085, novelty_critic=3654 |
| 41 | 8566 | 111.36 | 730 | narrator=5810, world_simulator=2756 |
| 42 | 7776 | 85.72 | 653 | narrator=5127, world_simulator=2649 |
| 43 | 17904 | 227.77 | 775 | narrator=7545, event_injector=4151, character_agent:char_linxue=3424 |
| 44 | 7343 | 74.07 | 796 | narrator=5723, world_simulator=1620 |
| 45 | 12854 | 158.4 | 0 | narrator=5982, showrunner=3986, world_simulator=2886 |
| 46 | 8014 | 87.95 | 794 | narrator=5155, world_simulator=2859 |
| 47 | 7419 | 76.67 | 592 | narrator=5126, world_simulator=2293 |
| 48 | 8035 | 92.06 | 1044 | narrator=5766, world_simulator=2269 |
| 49 | 8884 | 105.59 | 1061 | narrator=5468, world_simulator=3416 |
| 50 | 13549 | 176.33 | 0 | narrator=5896, showrunner=3911, world_simulator=3742 |

## First narrative sample

```
雨水在档案馆石质外墙汇成细流，反着阴天的光。排水管口滴水不断，砸在水泥地上，声音空洞。林雪站在侧门的雨搭下，肩膀湿了一片。她今早从床上醒来时，掌心里就攥着那张纸——童谣的句子又变了。河面雾气浓重，汽笛声从雾中钻出来，短促的一响，辨不清方向。她掏出口袋里的纸片，墨迹被潮气洇开，'钟声敲十三'
```
