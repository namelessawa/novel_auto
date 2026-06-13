# Bench: iter140-seed1-sideline-active

- novel_id: `bench_iter140-seed1-sideline-active_1781307363`
- ticks: 50
- bootstrap_sec: 311.07
- tick_durations_sec: [67.29, 55.04, 86.56, 62.52, 131.81, 94.75, 84.28, 105.5, 88.7, 237.8, 65.29, 65.09, 123.29, 79.03, 187.57, 77.37, 83.96, 74.62, 92.93, 141.77, 159.02, 97.78, 91.9, 100.71, 128.75, 76.37, 81.45, 89.99, 65.09, 172.16, 77.24, 159.63, 213.55, 76.97, 144.81, 113.63, 95.31, 87.89, 73.07, 149.87, 51.92, 99.06, 100.33, 230.38, 196.91, 101.31, 108.06, 101.3, 117.76, 150.54]
- total_tokens: 540109
- call_count: 126
- narrative_chars_total: 36956
- tokens_per_char: 14.61

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 277356 | 51.4% |
| world_simulator | 140586 | 26.0% |
| showrunner | 53409 | 9.9% |
| event_injector | 24182 | 4.5% |
| character_agent:char_chenafu | 11207 | 2.1% |
| character_agent:char_linxue | 8505 | 1.6% |
| character_agent:char_sumo | 7908 | 1.5% |
| novelty_critic | 7224 | 1.3% |
| character_arc_tracker | 5491 | 1.0% |
| character_agent:char_qitieshan | 4241 | 0.8% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 233625 |
| critical | 293769 |
| optional | 12715 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6967 | 67.29 | 0 | narrator=5376, world_simulator=1591 |
| 2 | 6908 | 55.04 | 0 | narrator=3877, world_simulator=3031 |
| 3 | 8566 | 86.56 | 68 | narrator=5560, world_simulator=3006 |
| 4 | 7281 | 62.52 | 510 | narrator=4669, world_simulator=2612 |
| 5 | 13702 | 131.81 | 886 | narrator=5345, showrunner=5286, world_simulator=3071 |
| 6 | 9539 | 94.75 | 1069 | narrator=5966, world_simulator=3573 |
| 7 | 8700 | 84.28 | 790 | narrator=5442, world_simulator=3258 |
| 8 | 8924 | 105.5 | 3373 | narrator=6019, world_simulator=2905 |
| 9 | 8610 | 88.7 | 457 | narrator=5777, world_simulator=2833 |
| 10 | 22885 | 237.8 | 992 | narrator=6461, showrunner=5533, event_injector=4433 |
| 11 | 7848 | 65.29 | 4 | narrator=6019, world_simulator=1829 |
| 12 | 7054 | 65.09 | 639 | narrator=4266, world_simulator=2788 |
| 13 | 8948 | 123.29 | 0 | narrator=5878, world_simulator=3070 |
| 14 | 7702 | 79.03 | 923 | narrator=5117, world_simulator=2585 |
| 15 | 15384 | 187.57 | 679 | narrator=6038, showrunner=5047, world_simulator=4299 |
| 16 | 7914 | 77.37 | 863 | narrator=4954, world_simulator=2960 |
| 17 | 8441 | 83.96 | 1137 | narrator=5490, world_simulator=2951 |
| 18 | 8202 | 74.62 | 611 | narrator=5805, world_simulator=2397 |
| 19 | 8901 | 92.93 | 1010 | narrator=5752, world_simulator=3149 |
| 20 | 17082 | 141.77 | 1395 | narrator=5448, showrunner=4978, novelty_critic=3599 |
| 21 | 16016 | 159.02 | 806 | narrator=5404, event_injector=4436, character_agent:char_chenafu=3186 |
| 22 | 8908 | 97.78 | 1114 | narrator=5342, world_simulator=3566 |
| 23 | 8583 | 91.9 | 1080 | narrator=5857, world_simulator=2726 |
| 24 | 9254 | 100.71 | 723 | narrator=5901, world_simulator=3353 |
| 25 | 12492 | 128.75 | 1269 | narrator=5338, showrunner=5224, world_simulator=1930 |
| 26 | 8008 | 76.37 | 694 | narrator=5395, world_simulator=2613 |
| 27 | 8366 | 81.45 | 0 | narrator=5852, world_simulator=2514 |
| 28 | 8530 | 89.99 | 890 | narrator=5953, world_simulator=2577 |
| 29 | 7573 | 65.09 | 796 | narrator=5655, world_simulator=1918 |
| 30 | 19160 | 172.16 | 0 | narrator=6018, character_arc_tracker=5491, showrunner=5344 |
| 31 | 8049 | 77.24 | 988 | narrator=5248, world_simulator=2801 |
| 32 | 14037 | 159.63 | 728 | event_injector=6496, narrator=5330, world_simulator=2211 |
| 33 | 26019 | 213.55 | 2306 | narrator=8009, event_injector=4971, character_agent:char_qitieshan=4241 |
| 34 | 8227 | 76.97 | 872 | narrator=5324, world_simulator=2903 |
| 35 | 13587 | 144.81 | 833 | showrunner=5446, narrator=5213, world_simulator=2928 |
| 36 | 9774 | 113.63 | 523 | narrator=5969, world_simulator=3805 |
| 37 | 8474 | 95.31 | 0 | narrator=5806, world_simulator=2668 |
| 38 | 8527 | 87.89 | 276 | narrator=5846, world_simulator=2681 |
| 39 | 7583 | 73.07 | 569 | narrator=4522, world_simulator=3061 |
| 40 | 16986 | 149.87 | 467 | showrunner=5507, narrator=5293, novelty_critic=3625 |
| 41 | 6558 | 51.92 | 0 | narrator=4181, world_simulator=2377 |
| 42 | 8704 | 99.06 | 910 | narrator=5699, world_simulator=3005 |
| 43 | 8708 | 100.33 | 1103 | narrator=5979, world_simulator=2729 |
| 44 | 27657 | 230.38 | 1285 | narrator=6711, character_agent:char_chenafu=5665, character_agent:char_linxue=4377 |
| 45 | 13512 | 196.91 | 763 | showrunner=5525, narrator=4889, world_simulator=3098 |
| 46 | 8289 | 101.31 | 0 | narrator=5196, world_simulator=3093 |
| 47 | 8187 | 108.06 | 839 | narrator=5198, world_simulator=2989 |
| 48 | 8290 | 101.3 | 744 | narrator=5935, world_simulator=2355 |
| 49 | 9057 | 117.76 | 0 | narrator=5945, world_simulator=3112 |
| 50 | 13436 | 150.54 | 972 | showrunner=5519, narrator=5089, world_simulator=2828 |

## First narrative sample

```
蒸汽管道接头的嘶嘶声在雾里撕开，比昨夜更尖利。苏默停在巷口，仰头。铜绿接头处，水珠挤出来，一颗接一颗砸向金属地板，叮叮咚咚。水洼已经漫开
```
