# Bench: iter103-seed3-50tick

- novel_id: `bench_iter103-seed3-50tick_1781213180`
- ticks: 50
- bootstrap_sec: 284.08
- tick_durations_sec: [57.18, 112.16, 82.22, 49.9, 115.9, 74.36, 80.81, 89.49, 76.14, 259.84, 73.72, 77.75, 71.18, 76.13, 127.26, 97.26, 72.85, 88.1, 94.23, 164.39, 178.2, 63.92, 118.56, 127.37, 211.27, 124.76, 119.96, 105.63, 137.28, 178.39, 146.19, 198.11, 133.8, 129.98, 182.11, 87.12, 80.64, 88.04, 82.44, 157.01, 116.92, 75.56, 225.64, 84.82, 144.26, 78.03, 83.26, 89.75, 85.96, 142.48]
- total_tokens: 611600
- call_count: 151
- narrative_chars_total: 37985
- tokens_per_char: 16.10

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 273547 | 44.7% |
| world_simulator | 139395 | 22.8% |
| character_agent:char_atu | 55234 | 9.0% |
| character_agent:char_leien | 51555 | 8.4% |
| showrunner | 45765 | 7.5% |
| event_injector | 17801 | 2.9% |
| character_agent:char_linxue | 6456 | 1.1% |
| novelty_critic | 6122 | 1.0% |
| character_arc_tracker | 4804 | 0.8% |
| narrative_critic:critique | 4486 | 0.7% |
| character_agent:char_zhaotie | 4198 | 0.7% |
| character_agent:char_sumo | 2237 | 0.4% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 262393 |
| critical | 338281 |
| optional | 10926 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 5780 | 57.18 | 581 | narrator=3885, world_simulator=1895 |
| 2 | 9301 | 112.16 | 0 | narrator=5282, world_simulator=4019 |
| 3 | 8028 | 82.22 | 864 | narrator=5299, world_simulator=2729 |
| 4 | 6209 | 49.9 | 723 | narrator=4614, world_simulator=1595 |
| 5 | 11456 | 115.9 | 856 | narrator=4920, showrunner=3933, world_simulator=2603 |
| 6 | 7618 | 74.36 | 858 | narrator=4769, world_simulator=2849 |
| 7 | 8262 | 80.81 | 0 | narrator=5668, world_simulator=2594 |
| 8 | 8594 | 89.49 | 527 | narrator=5696, world_simulator=2898 |
| 9 | 8012 | 76.14 | 588 | narrator=5344, world_simulator=2668 |
| 10 | 29088 | 259.84 | 1720 | narrator=7047, event_injector=4636, showrunner=4536 |
| 11 | 8040 | 73.72 | 1047 | narrator=5061, world_simulator=2979 |
| 12 | 7716 | 77.75 | 1293 | narrator=5643, world_simulator=2073 |
| 13 | 7227 | 71.18 | 1340 | narrator=5334, world_simulator=1893 |
| 14 | 7759 | 76.13 | 974 | narrator=4779, world_simulator=2980 |
| 15 | 12356 | 127.26 | 1355 | narrator=5156, showrunner=4726, world_simulator=2474 |
| 16 | 8850 | 97.26 | 950 | narrator=5625, world_simulator=3225 |
| 17 | 7706 | 72.85 | 916 | narrator=5192, world_simulator=2514 |
| 18 | 8435 | 88.1 | 0 | narrator=5651, world_simulator=2784 |
| 19 | 8592 | 94.23 | 692 | narrator=4913, world_simulator=3679 |
| 20 | 16711 | 164.39 | 319 | narrator=5598, showrunner=4822, novelty_critic=3467 |
| 21 | 18899 | 178.2 | 1157 | narrator=5851, event_injector=4373, character_agent:char_atu=3536 |
| 22 | 7195 | 63.92 | 696 | narrator=5181, world_simulator=2014 |
| 23 | 15869 | 118.56 | 597 | narrator=6211, character_agent:char_leien=3896, character_agent:char_atu=3359 |
| 24 | 15154 | 127.37 | 510 | narrator=5037, character_agent:char_atu=3850, world_simulator=3198 |
| 25 | 21525 | 211.27 | 913 | narrator=5546, showrunner=4765, character_agent:char_leien=4378 |
| 26 | 15416 | 124.76 | 1296 | narrator=5903, character_agent:char_atu=3498, character_agent:char_leien=3460 |
| 27 | 15674 | 119.96 | 498 | narrator=6218, character_agent:char_leien=3525, character_agent:char_atu=3339 |
| 28 | 14378 | 105.63 | 1317 | narrator=5740, character_agent:char_leien=3508, character_agent:char_atu=3465 |
| 29 | 16134 | 137.28 | 1040 | narrator=5806, character_agent:char_atu=3606, world_simulator=3415 |
| 30 | 25403 | 178.39 | 0 | narrator=6303, character_arc_tracker=4804, showrunner=4027 |
| 31 | 17332 | 146.19 | 925 | narrator=7564, character_agent:char_leien=3846, character_agent:char_atu=3157 |
| 32 | 22845 | 198.11 | 941 | narrator=7370, character_agent:char_atu=4452, event_injector=4259 |
| 33 | 16604 | 133.8 | 705 | narrator=5835, character_agent:char_leien=5235, character_agent:char_atu=3645 |
| 34 | 16407 | 129.98 | 963 | narrator=5421, character_agent:char_atu=4233, character_agent:char_leien=4013 |
| 35 | 20518 | 182.11 | 0 | narrator=6452, showrunner=4837, character_agent:char_leien=3329 |
| 36 | 8715 | 87.12 | 547 | narrator=5362, world_simulator=3353 |
| 37 | 7998 | 80.64 | 0 | narrator=5571, world_simulator=2427 |
| 38 | 7933 | 88.04 | 798 | narrator=4519, world_simulator=3414 |
| 39 | 8066 | 82.44 | 710 | narrator=5383, world_simulator=2683 |
| 40 | 16422 | 157.01 | 881 | narrator=5783, showrunner=5185, world_simulator=2799 |
| 41 | 9586 | 116.92 | 623 | narrator=5330, world_simulator=4256 |
| 42 | 7597 | 75.56 | 617 | narrator=5290, world_simulator=2307 |
| 43 | 26195 | 225.64 | 1444 | narrator=6247, character_agent:char_atu=4837, event_injector=4533 |
| 44 | 8229 | 84.82 | 986 | narrator=4667, world_simulator=3562 |
| 45 | 13289 | 144.26 | 558 | narrator=5451, showrunner=4552, world_simulator=3286 |
| 46 | 7422 | 78.03 | 897 | narrator=4771, world_simulator=2651 |
| 47 | 7490 | 83.26 | 52 | narrator=4738, world_simulator=2752 |
| 48 | 7268 | 89.75 | 690 | narrator=3933, world_simulator=3335 |
| 49 | 7778 | 85.96 | 1206 | narrator=5411, world_simulator=2367 |
| 50 | 12519 | 142.48 | 815 | narrator=5177, showrunner=4382, world_simulator=2960 |

## First narrative sample

```
沙尘钻进鼻腔时，苏默正在给皮革穿孔。骨针刺透鞣制过的驼兽皮，发出干涩的撕裂声。他停下动作，眯眼望向摊位外。尘风卷着赭红色的沙粒，掠过集市歪斜的棚顶，铁皮发出类似呜咽的震颤。远处，靠近城墙根的地方，空气扭曲了一瞬——又一个幻影。这次是个推着独轮车的人形，透明得能看见后面的泥砖墙，维持了三四次呼吸的时间才散掉。

“今天的幻影比昨天近了。”摊主老德蹲在隔壁，正往麻布袋里塞着晒干的沙鼠肉干，声音被风吹得断续，“再刮下去，记忆管理局该派人清街了。”

苏默没应声，低头继续手上的活。他眼前的案板上摊着十来张待修的皮料，都是商队送来的磨损货。他需要这笔工钱，或者说，他需要工钱能换到的、每周三份的“标准记忆补给”。那罐装在铅盒里的淡蓝色粉末，是他对抗脑袋里那片不断扩大的空白的唯一办法。

但上周的补给明显淡了。冲开时颜色寡淡，喝下去之后，童年的片段没有像往常那样浮起来，只是后脑勺传来一阵针扎似的麻。他知道这意味着什么。

骨针差点扎进指节。苏默稳住手，把穿好的皮条拉紧。风小了些，集市里的人声重新冒出来——吆喝、讨价还价、金属碰撞。一切都裹在一层挥之不去的尘土味里。他拿起案板角落的沙漏，细沙已经漏下去大半。再有一个时辰，记忆管理局的巡逻队就会经过这片外缘集市。

他必须在那之前收摊，去东区第三个巷口的暗门。那里有人在等他，带着一份模糊的承诺，和一份明确的危险。
```
