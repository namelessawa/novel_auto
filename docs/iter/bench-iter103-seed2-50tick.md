# Bench: iter103-seed2-50tick

- novel_id: `bench_iter103-seed2-50tick_1781225778`
- ticks: 50
- bootstrap_sec: 377.52
- tick_durations_sec: [81.59, 116.22, 108.63, 101.67, 155.6, 105.22, 76.88, 113.82, 107.93, 291.71, 95.3, 113.16, 110.06, 108.89, 159.1, 105.83, 112.36, 105.2, 111.19, 187.43, 310.96, 127.38, 82.99, 107.06, 201.33, 99.39, 144.1, 156.82, 154.85, 242.49, 144.5, 339.83, 130.7, 144.1, 174.26, 99.48, 135.93, 143.51, 134.81, 230.4, 133.24, 114.58, 266.95, 334.61, 198.81, 89.5, 127.18, 135.2, 144.35, 251.87]
- total_tokens: 527769
- call_count: 130
- narrative_chars_total: 29128
- tokens_per_char: 18.12

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 240593 | 45.6% |
| world_simulator | 151006 | 28.6% |
| showrunner | 46145 | 8.7% |
| event_injector | 26685 | 5.1% |
| character_agent:char_linxue | 16866 | 3.2% |
| character_agent:char_sumo | 13575 | 2.6% |
| character_agent:char_chenwanqing | 9086 | 1.7% |
| novelty_critic | 7062 | 1.3% |
| character_agent:char_zhaotiezhu | 6730 | 1.3% |
| character_arc_tracker | 6136 | 1.2% |
| character_agent:char_shilei | 3885 | 0.7% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 239652 |
| critical | 274919 |
| optional | 13198 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 5702 | 81.59 | 600 | narrator=3510, world_simulator=2192 |
| 2 | 7997 | 116.22 | 342 | narrator=4882, world_simulator=3115 |
| 3 | 7679 | 108.63 | 330 | narrator=4757, world_simulator=2922 |
| 4 | 7253 | 101.67 | 789 | narrator=3974, world_simulator=3279 |
| 5 | 11409 | 155.6 | 691 | showrunner=4361, narrator=4258, world_simulator=2790 |
| 6 | 7959 | 105.22 | 433 | narrator=5146, world_simulator=2813 |
| 7 | 6323 | 76.88 | 786 | narrator=4257, world_simulator=2066 |
| 8 | 8720 | 113.82 | 0 | narrator=5326, world_simulator=3394 |
| 9 | 7975 | 107.93 | 970 | narrator=4650, world_simulator=3325 |
| 10 | 30964 | 291.71 | 0 | narrator=7372, character_agent:char_sumo=4519, character_agent:char_linxue=4379 |
| 11 | 8078 | 95.3 | 840 | narrator=4732, world_simulator=3346 |
| 12 | 8087 | 113.16 | 626 | narrator=5542, world_simulator=2545 |
| 13 | 8341 | 110.06 | 589 | narrator=4681, world_simulator=3660 |
| 14 | 8298 | 108.89 | 470 | narrator=4905, world_simulator=3393 |
| 15 | 11666 | 159.1 | 517 | showrunner=5203, narrator=4059, world_simulator=2404 |
| 16 | 7527 | 105.83 | 101 | narrator=4967, world_simulator=2560 |
| 17 | 7548 | 112.36 | 164 | narrator=4532, world_simulator=3016 |
| 18 | 7166 | 105.2 | 99 | narrator=4675, world_simulator=2491 |
| 19 | 7733 | 111.19 | 360 | narrator=4656, world_simulator=3077 |
| 20 | 16305 | 187.43 | 382 | showrunner=5054, narrator=4884, novelty_critic=3710 |
| 21 | 27365 | 310.96 | 1700 | narrator=6875, event_injector=5476, character_agent:char_chenwanqing=4692 |
| 22 | 8592 | 127.38 | 762 | narrator=5213, world_simulator=3379 |
| 23 | 6300 | 82.99 | 891 | narrator=4468, world_simulator=1832 |
| 24 | 7061 | 107.06 | 1705 | narrator=5255, world_simulator=1806 |
| 25 | 13173 | 201.33 | 4 | narrator=5292, showrunner=4368, world_simulator=3513 |
| 26 | 6644 | 99.39 | 50 | world_simulator=3392, narrator=3252 |
| 27 | 7330 | 144.1 | 1344 | narrator=4297, world_simulator=3033 |
| 28 | 8473 | 156.82 | 1061 | narrator=4649, world_simulator=3824 |
| 29 | 8625 | 154.85 | 1154 | narrator=4700, world_simulator=3925 |
| 30 | 18494 | 242.49 | 533 | character_arc_tracker=6136, narrator=5126, showrunner=4611 |
| 31 | 7565 | 144.5 | 732 | narrator=4273, world_simulator=3292 |
| 32 | 28119 | 339.83 | 883 | narrator=5907, event_injector=5824, character_agent:char_sumo=5303 |
| 33 | 8282 | 130.7 | 794 | narrator=4610, world_simulator=3672 |
| 34 | 8429 | 144.1 | 679 | narrator=4811, world_simulator=3618 |
| 35 | 10930 | 174.26 | 0 | narrator=4296, showrunner=4228, world_simulator=2406 |
| 36 | 6601 | 99.48 | 644 | narrator=4261, world_simulator=2340 |
| 37 | 7608 | 135.93 | 939 | narrator=4332, world_simulator=3276 |
| 38 | 8315 | 143.51 | 966 | narrator=4654, world_simulator=3661 |
| 39 | 7977 | 134.81 | 755 | narrator=4297, world_simulator=3680 |
| 40 | 16544 | 230.4 | 1071 | narrator=5145, showrunner=4720, novelty_critic=3352 |
| 41 | 7887 | 133.24 | 526 | narrator=5118, world_simulator=2769 |
| 42 | 7186 | 114.58 | 0 | narrator=5025, world_simulator=2161 |
| 43 | 14569 | 266.95 | 25 | event_injector=6621, narrator=5040, world_simulator=2908 |
| 44 | 27681 | 334.61 | 333 | narrator=7215, event_injector=5237, character_agent:char_chenwanqing=4394 |
| 45 | 11886 | 198.81 | 673 | showrunner=4914, narrator=3818, world_simulator=3154 |
| 46 | 6434 | 89.5 | 568 | narrator=4747, world_simulator=1687 |
| 47 | 8033 | 127.18 | 491 | narrator=5052, world_simulator=2981 |
| 48 | 7796 | 135.2 | 302 | narrator=4497, world_simulator=3299 |
| 49 | 7849 | 144.35 | 454 | world_simulator=4005, narrator=3844 |
| 50 | 13291 | 251.87 | 0 | narrator=4759, showrunner=4642, world_simulator=3890 |

## First narrative sample

```
雾把路灯削成一团昏黄的湿气。街石反着光，踩上去要打滑。苏默竖起领口，绕过一摊积水，加快脚步往码头方向去。

快入冬了。空气里有鱼腥和柏油的味道，船坞那边传来沉闷的汽笛声，一声接一声，被雾吃得只剩轮廓。附近摊贩正往板车上码最后一筐带鱼，木框碰木框，蹾得地面都在响。苏默没停。他左手插在外套口袋里，护着一叠纸——今早档案馆复印室里抄出来的，关于码头仓库转让的批文副本，五张纸，用油纸包了两层，还是觉得潮气在往里渗。

这种天气法租界的巡捕不爱出巡。苏默从电报局拐进永安街，街面上除了他只有一个收夜壶的老头，推着车从巷子那头慢慢过来。苏默让了让，没抬头。

石板路尽头能看见海关大楼的灯，再往前就是码头栈桥了。汽笛又响了一下，这次近了些，带着煤烟的苦味扑过来。苏默走得太快，皮鞋底在湿石上打了个趔趄，右手撑了一下墙才稳住。墙皮是潮的，蹭了一掌白灰。

他抹了抹手，继续走。口袋里的纸包硌着肋骨。

栈桥上有人在卸货，汽灯被雾裹着，光散不开，照出码头工人弓着背扛麻袋的剪影。苏默没有上栈桥。他拐进仓库之间的夹道，从铁门的缝隙钻过去。铁锈蹭在袖口上，他低头看了一眼，没管。

穿过这段夹道，再过一道矮墙，就是沉默档案馆设在码头区的联络点——一间改过的旧仓库，门口挂着"恒记米行"的木牌，字都发了霉。

苏默到了门口，没急着敲。他先站定，听了一会儿。里头没有灯。但他闻到了烟味——纸烧过的烟味，从门缝底下漏出来。
```
