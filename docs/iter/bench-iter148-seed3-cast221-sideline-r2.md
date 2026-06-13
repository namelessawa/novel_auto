# Bench: iter148-seed3-cast221-sideline-r2

- novel_id: `bench_iter148-seed3-cast221-sideline-r2_1781341794`
- ticks: 50
- bootstrap_sec: 348.83
- tick_durations_sec: [102.99, 120.51, 106.36, 83.4, 199.22, 146.45, 95.31, 123.28, 109.55, 351.07, 135.51, 121.19, 129.04, 107.69, 227.28, 119.67, 125.66, 125.16, 132.25, 214.8, 292.63, 101.63, 117.3, 107.86, 168.71, 121.04, 99.27, 116.63, 116.85, 204.66, 70.49, 324.25, 148.24, 104.73, 175.88, 117.0, 110.26, 149.35, 108.88, 192.89, 117.63, 110.16, 251.27, 126.65, 179.16, 126.09, 132.19, 109.86, 135.08, 156.46]
- total_tokens: 528018
- call_count: 121
- narrative_chars_total: 30910
- tokens_per_char: 17.08

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 269335 | 51.0% |
| world_simulator | 155144 | 29.4% |
| showrunner | 55125 | 10.4% |
| event_injector | 22744 | 4.3% |
| novelty_critic | 7050 | 1.3% |
| narrative_critic:rewrite | 4949 | 0.9% |
| character_arc_tracker | 4462 | 0.8% |
| character_agent:char_sumo | 3440 | 0.7% |
| character_agent:char_liwan | 2946 | 0.6% |
| character_agent:char_linxue | 2823 | 0.5% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 235959 |
| critical | 280547 |
| optional | 11512 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 7117 | 102.99 | 873 | narrator=4272, world_simulator=2845 |
| 2 | 8589 | 120.51 | 0 | narrator=5631, world_simulator=2958 |
| 3 | 8083 | 106.36 | 835 | narrator=5058, world_simulator=3025 |
| 4 | 7481 | 83.4 | 763 | narrator=4645, world_simulator=2836 |
| 5 | 14063 | 199.22 | 364 | narrator=5766, showrunner=5159, world_simulator=3138 |
| 6 | 9417 | 146.45 | 722 | narrator=5544, world_simulator=3873 |
| 7 | 7617 | 95.31 | 699 | narrator=4966, world_simulator=2651 |
| 8 | 8397 | 123.28 | 812 | narrator=5446, world_simulator=2951 |
| 9 | 8105 | 109.55 | 997 | narrator=5123, world_simulator=2982 |
| 10 | 25892 | 351.07 | 0 | narrator=6985, showrunner=5310, event_injector=4523 |
| 11 | 9743 | 135.51 | 882 | narrator=5113, world_simulator=4630 |
| 12 | 8651 | 121.19 | 525 | narrator=5281, world_simulator=3370 |
| 13 | 8562 | 129.04 | 771 | narrator=5476, world_simulator=3086 |
| 14 | 8179 | 107.69 | 1194 | narrator=5407, world_simulator=2772 |
| 15 | 14855 | 227.28 | 1126 | narrator=5933, showrunner=5476, world_simulator=3446 |
| 16 | 9066 | 119.67 | 450 | narrator=5809, world_simulator=3257 |
| 17 | 8398 | 125.66 | 554 | narrator=5099, world_simulator=3299 |
| 18 | 8441 | 125.16 | 750 | narrator=4849, world_simulator=3592 |
| 19 | 9116 | 132.25 | 794 | narrator=5537, world_simulator=3579 |
| 20 | 17712 | 214.8 | 289 | narrator=5828, showrunner=5548, novelty_critic=3432 |
| 21 | 18400 | 292.63 | 619 | narrator=6295, event_injector=5819, character_agent:char_sumo=3440 |
| 22 | 7666 | 101.63 | 1075 | narrator=4775, world_simulator=2891 |
| 23 | 8497 | 117.3 | 677 | narrator=5484, world_simulator=3013 |
| 24 | 7930 | 107.86 | 1031 | narrator=5003, world_simulator=2927 |
| 25 | 12803 | 168.71 | 674 | showrunner=5578, narrator=5231, world_simulator=1994 |
| 26 | 8342 | 121.04 | 1206 | narrator=5187, world_simulator=3155 |
| 27 | 7988 | 99.27 | 119 | narrator=5131, world_simulator=2857 |
| 28 | 8150 | 116.63 | 625 | narrator=4786, world_simulator=3364 |
| 29 | 8479 | 116.85 | 918 | narrator=5232, world_simulator=3247 |
| 30 | 18034 | 204.66 | 1093 | showrunner=5518, narrator=5154, character_arc_tracker=4462 |
| 31 | 7006 | 70.49 | 0 | narrator=4360, world_simulator=2646 |
| 32 | 20896 | 324.25 | 759 | event_injector=6511, narrator=6163, narrative_critic:rewrite=4949 |
| 33 | 10024 | 148.24 | 0 | narrator=5950, world_simulator=4074 |
| 34 | 8342 | 104.73 | 0 | narrator=5285, world_simulator=3057 |
| 35 | 13999 | 175.88 | 715 | showrunner=5753, narrator=5116, world_simulator=3130 |
| 36 | 8699 | 117.0 | 1061 | narrator=5622, world_simulator=3077 |
| 37 | 8693 | 110.26 | 826 | narrator=5232, world_simulator=3461 |
| 38 | 9482 | 149.35 | 585 | narrator=5995, world_simulator=3487 |
| 39 | 8703 | 108.88 | 4 | narrator=5718, world_simulator=2985 |
| 40 | 17318 | 192.89 | 0 | showrunner=5707, narrator=5243, novelty_critic=3618 |
| 41 | 7978 | 117.63 | 652 | narrator=4716, world_simulator=3262 |
| 42 | 8067 | 110.16 | 845 | narrator=5321, world_simulator=2746 |
| 43 | 15873 | 251.27 | 50 | narrator=7283, event_injector=5891, world_simulator=2699 |
| 44 | 8029 | 126.65 | 110 | narrator=5226, world_simulator=2803 |
| 45 | 12746 | 179.16 | 880 | showrunner=5484, narrator=4591, world_simulator=2671 |
| 46 | 8851 | 126.09 | 1247 | narrator=5381, world_simulator=3470 |
| 47 | 9192 | 132.19 | 0 | narrator=5781, world_simulator=3411 |
| 48 | 8302 | 109.86 | 910 | narrator=5201, world_simulator=3101 |
| 49 | 9436 | 135.08 | 0 | narrator=5898, world_simulator=3538 |
| 50 | 12609 | 156.46 | 829 | showrunner=5592, narrator=5207, world_simulator=1810 |

## First narrative sample

```
酸雾涌进车厢时，苏墨捏紧了手中的记忆提取器。器身冰凉，金属外壳上细密的刻痕硌着掌心。车窗外，灰黄色的雾气里漂浮着星星点点的光，淡蓝色，像垂死的萤火。那是记忆碎片，撞在玻璃上，发出很轻的叮咚声，一声，又一声，间隔不等。

列车正驶向边界。他能感觉到金属轮毂碾过铁轨接缝的震动，从脚底传上来。更远处，栅栏的嘎吱声穿过雾气，断续，顽强，像某种生物临终的喘息。那声音提醒他，界限还在，但正在被腐蚀。锈迹每天都会多蔓延一点。

车厢内只有他一个人。座位是硬的，蒙着一层灰。他低头看提取器侧面的微型示数屏，幽绿的光映亮他半张脸。数字稳定，指向本次任务的坐标。神殿外围观测点。一个记录酸露滴落频率、记忆碎片漂浮轨迹的例行差事。委员会称之为“环境记忆基线采集”。

他的拇指无意识地摩挲着提取器侧面一个不起眼的凹槽。那里原本贴着标签，现在只剩下一点残胶。标签被他撕掉了。上面写着“实验性修复协议：第七样本”。那是他的秘密。用职务之便，偷偷截流一小部分即将被焚毁的碎片，尝试拼凑。不是为自己。

他想起那双眼睛。最后一次见她时，她坐在记忆清除室的金属椅上，眼神空荡荡的，像雨后的巷子。他们取走了她关于童年的全部光谱，关于母亲声音的频率，关于某个夏日午后蝉鸣的波形。为了“减轻负荷”。

列车猛地顿了一下。窗外的碎片光晕乱成一团。苏墨抬头，看向车厢尽头。那里，一块电子屏亮着，滚动播出今日记忆捐献者名单。名字一行行向上滚去，像墓碑。

他移开视线，目光落在自己的手背。皮肤下，血管微微凸起。他想，如果此刻有一台提取器对准他，屏幕上会显示什么？怀疑的色谱？背叛的振幅？

雾更浓了。叮咚声密集起来，敲打着玻璃，也敲打着车厢内壁。某个瞬间，他觉得那些光点试图告诉他什么。关于神殿石壁，关于那个被称为“零号”的幽禁之地，关于老陈总在深夜擦拭的某块旧记忆铜牌。

他深吸一口气。空气里有铁锈和旧纸灰的味道。提取器的示数屏闪烁了一下，一个提示符跳出：接近目标区域。建议启动被动接收模式。

苏墨的手指悬在启动键上，没有按下。他看着窗外那片混沌的、漂浮着无数人一生的灰黄色雾海。
```
