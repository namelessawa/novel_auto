# Bench: phase5j-longrange-200tick

- novel_id: `bench_phase5j-longrange-200tick_1781672606`
- ticks: 200
- bootstrap_sec: 452.49
- tick_durations_sec: [52.29, 0.02, 0.03, 73.39, 59.98, 0.02, 63.78, 0.03, 0.02, 232.96, 86.23, 0.02, 0.02, 67.91, 50.41, 0.03, 63.61, 0.02, 0.03, 121.22, 128.54, 62.36, 0.02, 0.02, 150.91, 0.02, 0.02, 69.22, 0.02, 127.09, 82.23, 172.44, 95.15, 0.03, 55.58, 63.73, 0.02, 0.02, 66.92, 109.37, 0.02, 105.5, 18.1, 222.28, 117.16, 0.03, 0.02, 72.5, 0.02, 54.17, 73.08, 0.03, 0.03, 42.92, 207.41, 69.46, 0.03, 0.02, 94.54, 114.55, 0.02, 95.13, 0.03, 0.03, 130.24, 179.2, 0.03, 98.67, 0.02, 29.37, 77.12, 0.03, 0.02, 111.74, 62.38, 0.02, 335.58, 181.27, 0.02, 97.96, 68.83, 0.02, 0.02, 71.73, 48.08, 0.02, 68.03, 152.01, 82.85, 170.06, 0.02, 79.74, 0.02, 0.02, 140.66, 0.1, 0.1, 87.7, 150.29, 268.82, 0.04, 0.06, 90.22, 0.04, 57.15, 118.76, 0.04, 0.04, 87.75, 148.6, 187.74, 0.04, 0.05, 96.35, 62.46, 0.03, 87.93, 0.03, 0.03, 169.65, 230.03, 101.38, 0.02, 0.02, 144.59, 0.04, 0.04, 88.3, 0.04, 53.49, 90.14, 189.6, 100.97, 0.03, 69.47, 90.03, 0.03, 0.04, 78.47, 126.74, 0.03, 85.35, 144.5, 133.24, 161.04, 0.03, 0.03, 87.24, 0.03, 273.63, 80.33, 0.04, 0.04, 265.15, 151.42, 0.04, 0.03, 79.41, 0.03, 106.94, 78.37, 0.05, 0.05, 72.74, 309.27, 84.95, 0.03, 0.03, 89.25, 63.02, 0.04, 82.15, 0.04, 0.04, 117.91, 144.64, 91.9, 0.04, 0.04, 219.6, 0.04, 0.03, 91.43, 0.03, 51.33, 69.25, 16.98, 122.9, 122.79, 58.56, 0.03, 99.5, 0.05, 0.03, 112.71, 0.04, 0.04, 66.38, 185.6, 368.41]
- total_tokens: 1062459
- call_count: 313
- narrative_chars_total: 84238
- tokens_per_char: 12.61

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 429286 | 40.4% |
| showrunner | 155207 | 14.6% |
| world_simulator | 131970 | 12.4% |
| event_injector | 73577 | 6.9% |
| character_agent:char_linxue | 53080 | 5.0% |
| character_arc_tracker | 42795 | 4.0% |
| character_agent:char_zhongli | 41139 | 3.9% |
| character_agent:char_lengfeng | 33449 | 3.1% |
| character_agent:char_sumo | 32976 | 3.1% |
| novelty_critic | 20830 | 2.0% |
| memory_compressor:l0_l1 | 20227 | 1.9% |
| character_agent:char_luyan | 12923 | 1.2% |
| character_agent:char_qianyin | 5352 | 0.5% |
| narrative_critic:critique | 5038 | 0.5% |
| narrative_critic:rewrite | 4610 | 0.4% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 412478 |
| critical | 566129 |
| optional | 83852 |

## Cache hit rate (Phase 5-A)

- total prompt_tokens: 637092
- total cached_tokens: 0
- overall hit rate: 0.0%

| agent | prompt | cached | hit% |
| --- | ---: | ---: | ---: |
| narrator | 299775 | 0 | 0.0% |
| showrunner | 81293 | 0 | 0.0% |
| world_simulator | 54093 | 0 | 0.0% |
| event_injector | 45086 | 0 | 0.0% |
| character_agent:char_linxue | 28760 | 0 | 0.0% |
| character_agent:char_zhongli | 26661 | 0 | 0.0% |
| character_agent:char_lengfeng | 23554 | 0 | 0.0% |
| character_arc_tracker | 23352 | 0 | 0.0% |
| character_agent:char_sumo | 21437 | 0 | 0.0% |
| novelty_critic | 9699 | 0 | 0.0% |
| memory_compressor:l0_l1 | 8042 | 0 | 0.0% |
| character_agent:char_luyan | 7433 | 0 | 0.0% |
| character_agent:char_qianyin | 2824 | 0 | 0.0% |
| narrative_critic:critique | 2682 | 0 | 0.0% |
| narrative_critic:rewrite | 2401 | 0 | 0.0% |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 4872 | 52.29 | 644 | narrator=3860, world_simulator=1012 |
| 2 | 0 | 0.02 | 0 |  |
| 3 | 0 | 0.03 | 0 |  |
| 4 | 6060 | 73.39 | 888 | narrator=4653, world_simulator=1407 |
| 5 | 4138 | 59.98 | 0 | showrunner=4138 |
| 6 | 0 | 0.02 | 0 |  |
| 7 | 5722 | 63.78 | 973 | narrator=4673, world_simulator=1049 |
| 8 | 0 | 0.03 | 0 |  |
| 9 | 0 | 0.02 | 0 |  |
| 10 | 26847 | 232.96 | 1742 | narrator=6923, showrunner=4264, event_injector=3350 |
| 11 | 6844 | 86.23 | 919 | narrator=4586, world_simulator=2258 |
| 12 | 0 | 0.02 | 0 |  |
| 13 | 0 | 0.02 | 0 |  |
| 14 | 5959 | 67.91 | 928 | narrator=4555, world_simulator=1404 |
| 15 | 3738 | 50.41 | 0 | showrunner=3738 |
| 16 | 0 | 0.03 | 0 |  |
| 17 | 5635 | 63.61 | 836 | narrator=4422, world_simulator=1213 |
| 18 | 0 | 0.02 | 0 |  |
| 19 | 0 | 0.03 | 0 |  |
| 20 | 11774 | 121.22 | 572 | narrator=4411, showrunner=3922, novelty_critic=2173 |
| 21 | 15694 | 128.54 | 821 | narrator=5167, event_injector=3580, character_agent:char_linxue=2683 |
| 22 | 5990 | 62.36 | 577 | narrator=4359, world_simulator=1631 |
| 23 | 0 | 0.02 | 0 |  |
| 24 | 0 | 0.02 | 0 |  |
| 25 | 10443 | 150.91 | 840 | showrunner=4548, narrator=4248, world_simulator=1647 |
| 26 | 0 | 0.02 | 0 |  |
| 27 | 0 | 0.02 | 0 |  |
| 28 | 5825 | 69.22 | 848 | narrator=4726, world_simulator=1099 |
| 29 | 0 | 0.02 | 0 |  |
| 30 | 8978 | 127.09 | 0 | character_arc_tracker=6029, showrunner=2949 |
| 31 | 6176 | 82.23 | 747 | narrator=4620, world_simulator=1556 |
| 32 | 17775 | 172.44 | 997 | narrator=5708, event_injector=3955, character_agent:char_zhongli=3643 |
| 33 | 13885 | 95.15 | 906 | narrator=5469, character_agent:char_zhongli=2376, character_agent:char_linxue=2323 |
| 34 | 0 | 0.03 | 0 |  |
| 35 | 3847 | 55.58 | 0 | showrunner=3847 |
| 36 | 5717 | 63.73 | 584 | narrator=4430, world_simulator=1287 |
| 37 | 0 | 0.02 | 0 |  |
| 38 | 0 | 0.02 | 0 |  |
| 39 | 5599 | 66.92 | 609 | narrator=4380, world_simulator=1219 |
| 40 | 6507 | 109.37 | 0 | showrunner=3917, novelty_critic=2590 |
| 41 | 0 | 0.02 | 0 |  |
| 42 | 5683 | 105.5 | 577 | narrator=4494, world_simulator=1189 |
| 43 | 2822 | 18.1 | 0 | event_injector=2822 |
| 44 | 22706 | 222.28 | 2211 | narrator=6746, event_injector=4324, character_agent:char_linxue=3978 |
| 45 | 9774 | 117.16 | 470 | narrator=4192, showrunner=3897, world_simulator=1685 |
| 46 | 0 | 0.03 | 0 |  |
| 47 | 0 | 0.02 | 0 |  |
| 48 | 5442 | 72.5 | 592 | narrator=3987, world_simulator=1455 |
| 49 | 0 | 0.02 | 0 |  |
| 50 | 3731 | 54.17 | 0 | showrunner=3731 |
| 51 | 5861 | 73.08 | 838 | narrator=4567, world_simulator=1294 |
| 52 | 0 | 0.03 | 0 |  |
| 53 | 0 | 0.03 | 0 |  |
| 54 | 4951 | 42.92 | 0 | narrator=3670, world_simulator=1281 |
| 55 | 16323 | 207.41 | 632 | narrator=4858, event_injector=4463, showrunner=3756 |
| 56 | 6106 | 69.46 | 717 | narrator=4357, world_simulator=1749 |
| 57 | 0 | 0.03 | 0 |  |
| 58 | 0 | 0.02 | 0 |  |
| 59 | 6670 | 94.54 | 1134 | narrator=4881, world_simulator=1789 |
| 60 | 11332 | 114.55 | 0 | character_arc_tracker=5263, showrunner=3832, novelty_critic=2237 |
| 61 | 0 | 0.02 | 0 |  |
| 62 | 6786 | 95.13 | 853 | narrator=4556, world_simulator=2230 |
| 63 | 0 | 0.03 | 0 |  |
| 64 | 0 | 0.03 | 0 |  |
| 65 | 10035 | 130.24 | 721 | narrator=4360, showrunner=3694, world_simulator=1981 |
| 66 | 18349 | 179.2 | 2070 | narrator=6562, event_injector=4159, character_agent:char_zhongli=2926 |
| 67 | 0 | 0.03 | 0 |  |
| 68 | 7066 | 98.67 | 982 | narrator=4905, world_simulator=2161 |
| 69 | 0 | 0.02 | 0 |  |
| 70 | 3015 | 29.37 | 0 | showrunner=3015 |
| 71 | 6498 | 77.12 | 613 | narrator=4457, world_simulator=2041 |
| 72 | 0 | 0.03 | 0 |  |
| 73 | 0 | 0.02 | 0 |  |
| 74 | 7645 | 111.74 | 605 | narrator=4233, world_simulator=3412 |
| 75 | 4157 | 62.38 | 0 | showrunner=4157 |
| 76 | 0 | 0.02 | 0 |  |
| 77 | 32670 | 335.58 | 1964 | narrator=7693, narrative_critic:rewrite=4610, event_injector=4403 |
| 78 | 20147 | 181.27 | 1957 | narrator=6882, character_agent:char_linxue=3060, world_simulator=2990 |
| 79 | 0 | 0.02 | 0 |  |
| 80 | 6001 | 97.96 | 0 | showrunner=3934, novelty_critic=2067 |
| 81 | 5902 | 68.83 | 529 | narrator=4316, world_simulator=1586 |
| 82 | 0 | 0.02 | 0 |  |
| 83 | 0 | 0.02 | 0 |  |
| 84 | 6062 | 71.73 | 352 | narrator=3805, world_simulator=2257 |
| 85 | 3596 | 48.08 | 0 | showrunner=3596 |
| 86 | 0 | 0.02 | 0 |  |
| 87 | 5626 | 68.03 | 420 | narrator=3980, world_simulator=1646 |
| 88 | 14279 | 152.01 | 802 | narrator=5511, event_injector=3885, character_agent:char_qianyin=2446 |
| 89 | 6520 | 82.85 | 605 | narrator=4599, world_simulator=1921 |
| 90 | 11850 | 170.06 | 0 | character_arc_tracker=8364, showrunner=3486 |
| 91 | 0 | 0.02 | 0 |  |
| 92 | 6178 | 79.74 | 634 | narrator=4573, world_simulator=1605 |
| 93 | 0 | 0.02 | 0 |  |
| 94 | 0 | 0.02 | 0 |  |
| 95 | 10230 | 140.66 | 896 | narrator=4767, showrunner=3902, world_simulator=1561 |
| 96 | 0 | 0.1 | 0 |  |
| 97 | 0 | 0.1 | 0 |  |
| 98 | 6734 | 87.7 | 568 | narrator=4549, world_simulator=2185 |
| 99 | 14357 | 150.29 | 945 | narrator=5075, event_injector=3940, character_agent:char_qianyin=2906 |
| 100 | 18032 | 268.82 | 905 | narrator=4871, memory_compressor:l0_l1=4779, showrunner=3321 |
| 101 | 0 | 0.04 | 0 |  |
| 102 | 0 | 0.06 | 0 |  |
| 103 | 6775 | 90.22 | 962 | narrator=4640, world_simulator=2135 |
| 104 | 0 | 0.04 | 0 |  |
| 105 | 3736 | 57.15 | 0 | showrunner=3736 |
| 106 | 7641 | 118.76 | 1291 | narrator=4931, world_simulator=2710 |
| 107 | 0 | 0.04 | 0 |  |
| 108 | 0 | 0.04 | 0 |  |
| 109 | 6924 | 87.75 | 636 | narrator=4579, world_simulator=2345 |
| 110 | 10442 | 148.6 | 0 | showrunner=4204, event_injector=3728, character_agent:char_linxue=2510 |
| 111 | 10017 | 187.74 | 1667 | narrator=5436, world_simulator=4581 |
| 112 | 0 | 0.04 | 0 |  |
| 113 | 0 | 0.05 | 0 |  |
| 114 | 7337 | 96.35 | 1034 | narrator=4909, world_simulator=2428 |
| 115 | 4094 | 62.46 | 0 | showrunner=4094 |
| 116 | 0 | 0.03 | 0 |  |
| 117 | 6726 | 87.93 | 834 | narrator=4884, world_simulator=1842 |
| 118 | 0 | 0.03 | 0 |  |
| 119 | 0 | 0.03 | 0 |  |
| 120 | 18898 | 169.65 | 890 | character_arc_tracker=6693, narrator=4687, showrunner=4340 |
| 121 | 22835 | 230.03 | 1746 | narrator=6743, character_agent:char_linxue=4257, event_injector=4076 |
| 122 | 7204 | 101.38 | 1031 | narrator=4642, world_simulator=2562 |
| 123 | 0 | 0.02 | 0 |  |
| 124 | 0 | 0.02 | 0 |  |
| 125 | 10350 | 144.59 | 934 | narrator=4586, showrunner=3968, world_simulator=1796 |
| 126 | 0 | 0.04 | 0 |  |
| 127 | 0 | 0.04 | 0 |  |
| 128 | 6418 | 88.3 | 1058 | narrator=4521, world_simulator=1897 |
| 129 | 0 | 0.04 | 0 |  |
| 130 | 3694 | 53.49 | 0 | showrunner=3694 |
| 131 | 6459 | 90.14 | 1048 | narrator=4520, world_simulator=1939 |
| 132 | 18654 | 189.6 | 1465 | narrator=6393, character_agent:char_linxue=4049, event_injector=3341 |
| 133 | 6866 | 100.97 | 864 | narrator=4682, world_simulator=2184 |
| 134 | 0 | 0.03 | 0 |  |
| 135 | 4200 | 69.47 | 0 | showrunner=4200 |
| 136 | 6275 | 90.03 | 797 | narrator=4989, world_simulator=1286 |
| 137 | 0 | 0.03 | 0 |  |
| 138 | 0 | 0.04 | 0 |  |
| 139 | 6135 | 78.47 | 509 | narrator=4733, world_simulator=1402 |
| 140 | 6992 | 126.74 | 0 | showrunner=4391, novelty_critic=2601 |
| 141 | 0 | 0.03 | 0 |  |
| 142 | 6080 | 85.35 | 643 | narrator=4091, world_simulator=1989 |
| 143 | 11960 | 144.5 | 1152 | narrator=5183, event_injector=3596, character_agent:char_sumo=3181 |
| 144 | 10061 | 133.24 | 681 | narrator=5011, character_agent:char_sumo=3253, world_simulator=1797 |
| 145 | 12957 | 161.04 | 925 | narrator=4808, showrunner=4062, character_agent:char_sumo=2701 |
| 146 | 0 | 0.03 | 0 |  |
| 147 | 0 | 0.03 | 0 |  |
| 148 | 6116 | 87.24 | 969 | narrator=4714, world_simulator=1402 |
| 149 | 0 | 0.03 | 0 |  |
| 150 | 18437 | 273.63 | 0 | character_arc_tracker=7368, memory_compressor:l0_l1=7142, showrunner=3927 |
| 151 | 6001 | 80.33 | 846 | narrator=4473, world_simulator=1528 |
| 152 | 0 | 0.04 | 0 |  |
| 153 | 0 | 0.04 | 0 |  |
| 154 | 27185 | 265.15 | 2923 | narrator=7844, event_injector=3829, character_agent:char_sumo=3145 |
| 155 | 10692 | 151.42 | 920 | narrator=4454, showrunner=4149, world_simulator=2089 |
| 156 | 0 | 0.04 | 0 |  |
| 157 | 0 | 0.03 | 0 |  |
| 158 | 5943 | 79.41 | 843 | narrator=4547, world_simulator=1396 |
| 159 | 0 | 0.03 | 0 |  |
| 160 | 6143 | 106.94 | 0 | showrunner=4483, novelty_critic=1660 |
| 161 | 5971 | 78.37 | 1034 | narrator=4683, world_simulator=1288 |
| 162 | 0 | 0.05 | 0 |  |
| 163 | 0 | 0.05 | 0 |  |
| 164 | 5821 | 72.74 | 609 | narrator=4160, world_simulator=1661 |
| 165 | 26483 | 309.27 | 1484 | narrator=5610, narrative_critic:critique=5038, showrunner=4100 |
| 166 | 6362 | 84.95 | 635 | narrator=4385, world_simulator=1977 |
| 167 | 0 | 0.03 | 0 |  |
| 168 | 0 | 0.03 | 0 |  |
| 169 | 6159 | 89.25 | 1661 | narrator=4886, world_simulator=1273 |
| 170 | 3981 | 63.02 | 0 | showrunner=3981 |
| 171 | 0 | 0.04 | 0 |  |
| 172 | 6089 | 82.15 | 852 | narrator=4410, world_simulator=1679 |
| 173 | 0 | 0.04 | 0 |  |
| 174 | 0 | 0.04 | 0 |  |
| 175 | 9206 | 117.91 | 774 | narrator=4325, showrunner=3629, world_simulator=1252 |
| 176 | 19966 | 144.64 | 1589 | narrator=6644, event_injector=3306, character_agent:char_zhongli=2834 |
| 177 | 6684 | 91.9 | 986 | narrator=4629, world_simulator=2055 |
| 178 | 0 | 0.04 | 0 |  |
| 179 | 0 | 0.04 | 0 |  |
| 180 | 20594 | 219.6 | 1078 | character_arc_tracker=9078, narrator=4394, showrunner=3688 |
| 181 | 0 | 0.04 | 0 |  |
| 182 | 0 | 0.03 | 0 |  |
| 183 | 6169 | 91.43 | 1020 | narrator=4575, world_simulator=1594 |
| 184 | 0 | 0.03 | 0 |  |
| 185 | 3610 | 51.33 | 0 | showrunner=3610 |
| 186 | 5675 | 69.25 | 669 | narrator=4558, world_simulator=1117 |
| 187 | 2695 | 16.98 | 0 | event_injector=2695 |
| 188 | 11067 | 122.9 | 1051 | narrator=4793, event_injector=3531, character_agent:char_sumo=2743 |
| 189 | 10028 | 122.79 | 1010 | narrator=4870, character_agent:char_sumo=2878, world_simulator=2280 |
| 190 | 3795 | 58.56 | 0 | showrunner=3795 |
| 191 | 0 | 0.03 | 0 |  |
| 192 | 6571 | 99.5 | 1063 | narrator=4572, world_simulator=1999 |
| 193 | 0 | 0.05 | 0 |  |
| 194 | 0 | 0.03 | 0 |  |
| 195 | 8941 | 112.71 | 821 | narrator=4203, showrunner=3509, world_simulator=1229 |
| 196 | 0 | 0.04 | 0 |  |
| 197 | 0 | 0.04 | 0 |  |
| 198 | 5579 | 66.38 | 677 | narrator=4207, world_simulator=1372 |
| 199 | 18357 | 185.6 | 1670 | narrator=6351, character_agent:char_linxue=3466, event_injector=3309 |
| 200 | 31248 | 368.41 | 864 | memory_compressor:l0_l1=8306, narrator=5395, showrunner=4003 |

## First narrative sample

```
铁锈雨落在棚顶，沙沙声像无数只虫在啃铁皮。

苏摩把领口收紧。雨水顺着帽檐滴进脖子，凉而涩，带一股金属的腥。他站在集市东角的告示牌前，看那张新贴的纸。纸边已经卷起，墨迹被雨洇开，只剩“招募”两个字还勉强可辨。下面一行小字完全糊成蓝灰色的水渍。

有人碰了碰他的胳膊肘。

“让让。”

一个推板车的女人。车上堆着齿轮胚件，锈斑从帆布下露出来。车轮卡进石板缝，她骂了一声，使劲一抬，过去了。积水溅上苏摩的靴子。他没动。

告示牌上还贴着别的纸。一张三个月前的失踪通报，照片上的人脸被酸雨蚀成空洞。一张齿轮议会的政令，红印还鲜亮，但正文已经读不连贯。他扫过那些字，目光停在右下角一行小字上——老城区封锁令，落款是三天前。

灰雾深处传来汽笛。

低沉，绵长，像某种巨大的喉咙在水下呻吟。苏摩抬起头。集市里其他人也抬起头。卖齿轮胚件的女人停住板车。一个正在收摊的布商把手按在货箱上。

汽笛持续了五秒。然后断了。

紧接着是金属摩擦的尖啸。声音从雾里来，方向辨不清。不是工厂的噪音——工厂的机器不会这样叫。这声音像什么东西在撕铁板，一层一层地撕，撕到骨头。

有人开始跑。

板车撞翻了货架。齿轮胚件滚了一地，在积水里砸出暗红色的水花。布商把货箱扛上肩，往巷子里钻。苏摩没跑。他听那个声音。

尖啸停了。

雾里什么也没有。只有铁锈雨还在下，沙沙地啃着铁皮屋顶。

苏摩把告示牌上那张被雨淋透的招募告示揭下来。纸在他手里烂掉一半。他把剩下半张叠好，塞进内袋。然后转身，逆着人流往老城区的方向走。
```
