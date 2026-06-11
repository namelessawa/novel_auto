# Bench: stage3-longrange-50tick

- novel_id: `bench_stage3-longrange-50tick_1781155934`
- ticks: 50
- bootstrap_sec: 304.15
- tick_durations_sec: [75.02, 74.92, 83.87, 90.63, 160.84, 91.24, 73.45, 69.68, 92.77, 245.45, 124.24, 132.1, 76.64, 89.92, 193.63, 101.7, 120.24, 118.97, 120.13, 153.0, 346.96, 99.08, 128.4, 121.2, 226.52, 117.41, 122.16, 118.48, 135.79, 173.1, 100.17, 284.46, 121.34, 133.52, 223.19, 150.56, 113.12, 102.81, 120.77, 174.52, 131.55, 111.03, 405.24, 128.23, 203.4, 117.2, 129.78, 124.85, 111.67, 184.63]
- total_tokens: 509417
- call_count: 124
- narrative_chars_total: 29991
- tokens_per_char: 16.99

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 272498 | 53.5% |
| world_simulator | 134657 | 26.4% |
| showrunner | 44039 | 8.6% |
| event_injector | 18993 | 3.7% |
| character_agent:char_linxue | 13432 | 2.6% |
| narrative_critic:critique | 8592 | 1.7% |
| character_agent:char_sumo | 6848 | 1.3% |
| novelty_critic | 6844 | 1.3% |
| character_arc_tracker | 3514 | 0.7% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 197689 |
| critical | 301370 |
| optional | 10358 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6526 | 75.02 | 839 | narrator=4306, world_simulator=2220 |
| 2 | 7424 | 74.92 | 0 | narrator=5905, world_simulator=1519 |
| 3 | 7749 | 83.87 | 610 | narrator=5299, world_simulator=2450 |
| 4 | 7710 | 90.63 | 749 | narrator=4866, world_simulator=2844 |
| 5 | 11826 | 160.84 | 0 | narrator=6006, showrunner=3592, world_simulator=2228 |
| 6 | 8545 | 91.24 | 427 | narrator=6093, world_simulator=2452 |
| 7 | 6920 | 73.45 | 917 | narrator=5297, world_simulator=1623 |
| 8 | 7428 | 69.68 | 230 | narrator=5703, world_simulator=1725 |
| 9 | 7782 | 92.77 | 712 | narrator=4662, world_simulator=3120 |
| 10 | 19453 | 245.45 | 298 | narrator=6075, event_injector=4090, showrunner=4048 |
| 11 | 9206 | 124.24 | 514 | narrator=4783, world_simulator=4423 |
| 12 | 9459 | 132.1 | 0 | narrator=5761, world_simulator=3698 |
| 13 | 3683 | 76.64 | 0 | world_simulator=3683 |
| 14 | 7381 | 89.92 | 740 | narrator=5156, world_simulator=2225 |
| 15 | 13077 | 193.63 | 779 | narrator=5787, showrunner=4582, world_simulator=2708 |
| 16 | 8188 | 101.7 | 796 | narrator=5196, world_simulator=2992 |
| 17 | 8715 | 120.24 | 843 | narrator=5488, world_simulator=3227 |
| 18 | 8356 | 118.97 | 15 | narrator=6013, world_simulator=2343 |
| 19 | 8124 | 120.13 | 433 | narrator=5115, world_simulator=3009 |
| 20 | 13990 | 153.0 | 712 | narrator=4625, showrunner=3827, novelty_critic=3434 |
| 21 | 22375 | 346.96 | 919 | narrator=7038, event_injector=5081, narrative_critic:critique=3992 |
| 22 | 7969 | 99.08 | 732 | narrator=5206, world_simulator=2763 |
| 23 | 8690 | 128.4 | 721 | narrator=5561, world_simulator=3129 |
| 24 | 8357 | 121.2 | 769 | narrator=5310, world_simulator=3047 |
| 25 | 14111 | 226.52 | 180 | narrator=5986, showrunner=4808, world_simulator=3317 |
| 26 | 7701 | 117.41 | 1092 | narrator=4871, world_simulator=2830 |
| 27 | 8529 | 122.16 | 662 | narrator=5722, world_simulator=2807 |
| 28 | 8087 | 118.48 | 909 | narrator=5351, world_simulator=2736 |
| 29 | 8851 | 135.79 | 848 | narrator=5288, world_simulator=3563 |
| 30 | 14603 | 173.1 | 880 | narrator=5240, showrunner=4163, character_arc_tracker=3514 |
| 31 | 7567 | 100.17 | 775 | narrator=5218, world_simulator=2349 |
| 32 | 20617 | 284.46 | 392 | narrator=7991, event_injector=4558, character_agent:char_linxue=3091 |
| 33 | 8480 | 121.34 | 0 | narrator=5711, world_simulator=2769 |
| 34 | 8323 | 133.52 | 403 | narrator=5728, world_simulator=2595 |
| 35 | 13609 | 223.19 | 4 | narrator=5792, showrunner=4895, world_simulator=2922 |
| 36 | 8919 | 150.56 | 0 | narrator=5464, world_simulator=3455 |
| 37 | 7478 | 113.12 | 617 | narrator=4775, world_simulator=2703 |
| 38 | 7323 | 102.81 | 825 | narrator=4972, world_simulator=2351 |
| 39 | 8004 | 120.77 | 679 | narrator=5286, world_simulator=2718 |
| 40 | 14953 | 174.52 | 797 | narrator=5141, showrunner=4566, novelty_critic=3410 |
| 41 | 9208 | 131.55 | 0 | narrator=6069, world_simulator=3139 |
| 42 | 7525 | 111.03 | 817 | narrator=5476, world_simulator=2049 |
| 43 | 28390 | 405.24 | 1807 | narrator=6971, event_injector=5264, narrative_critic:critique=4600 |
| 44 | 8578 | 128.23 | 1105 | narrator=5553, world_simulator=3025 |
| 45 | 13476 | 203.4 | 0 | narrator=5881, showrunner=4996, world_simulator=2599 |
| 46 | 8532 | 117.2 | 749 | narrator=5596, world_simulator=2936 |
| 47 | 8565 | 129.78 | 807 | narrator=6044, world_simulator=2521 |
| 48 | 8646 | 124.85 | 781 | narrator=5198, world_simulator=3448 |
| 49 | 7705 | 111.67 | 1355 | narrator=5715, world_simulator=1990 |
| 50 | 12704 | 184.63 | 752 | narrator=6208, showrunner=4562, world_simulator=1934 |

## First narrative sample

```
汽笛声从雾里钻出来的时候，苏默正踩进一个泥坑。

靴子陷下去三指深。他拔脚，鞋底带出一团黑泥，啪地落回地面，溅在裤腿上。雨不大，但已经下了整夜，泥路变成一条浑浊的浅沟，雨水在低洼处聚成不规则的黄褐色水洼。蒸汽船的汽笛又响了一声，比刚才闷，像是被雾吞掉了一半，只剩一个湿漉漉的尾音拖在空气里，很久不散。

远处的工业烟囱看不到顶。烟柱灰白，和雾搅在一起，分不清哪里是天，哪里是烟囱吐出来的东西。偶尔有火星从烟柱里迸出来，红点一闪，噼啪一声就灭了，像谁在很高的地方划了一根火柴。空气里有一股焦糊味，混着铁锈和湿土，沉在鼻腔里不肯走。

苏默把帽檐往下压了压，沿着泥路往东走。

东边是蒸汽机房的后墙，墙根底下有个检修通道，铁门生了锈，推开的时候会发出很尖的声响。他不想弄出声音，所以绕到北侧，从堆着煤渣的空地穿过去。煤渣被雨泡软了，踩上去是黏的，鞋底黏着碎屑，走一步响一步。他放慢速度，尽量让脚步落在煤渣堆边缘那些还没泡烂的硬块上。

棉布外套已经被雨浸透，贴在后背上，重了一倍。他没有伞。这年头在艾瑟堡街头打伞的人不多——蒸汽管道的排气口分布在街巷各处，喷出来的热气会把伞布烫出洞。人们习惯戴帽，或者什么也不戴，淋着。

路过第七号蒸汽枢纽站的铁栅栏时，他停了一下。栅栏里面没有人，值班室的窗户黑着，气压表的铜针指向低区，管道里的蒸汽流动声很轻，像远处有人在叹气。枢纽站对面的墙上贴着布告，纸已经被雨泡烂了半张，剩下的部分能看到"档案馆"三个印刷体大字和一行模糊的小字，像是某种通告。他没凑过去看。

又走了大概两百步，泥路拐了个弯。雾在这里更浓，十步之外的东西全变成灰色的轮廓。苏默放慢脚步，右手伸进外套内侧，指尖碰到了那叠纸的边缘。纸还是干的，硬壳封面隔着棉布传来一点凉意。

他没有拿出来。

拐弯处有一盏瓦斯路灯，灯罩上凝着水珠，火苗在里面跳，橘黄色的光在雾里散开，像一团模糊的伤疤。他低头走过灯下，影子拉得很长，歪歪斜斜地铺在泥水里，被雨水打散。

再往前就是安全屋了。
```
