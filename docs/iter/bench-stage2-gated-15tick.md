# Bench: stage2-gated-15tick

- novel_id: `bench_stage2-gated-15tick_1781151790`
- ticks: 15
- bootstrap_sec: 421.58
- tick_durations_sec: [92.87, 93.4, 110.68, 127.75, 184.92, 90.61, 135.11, 77.69, 99.83, 440.53, 83.14, 77.63, 87.39, 115.33, 184.2]
- total_tokens: 146819
- call_count: 38
- narrative_chars_total: 7442
- tokens_per_char: 19.73

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 67880 | 46.2% |
| world_simulator | 43809 | 29.8% |
| showrunner | 13258 | 9.0% |
| narrative_critic:rewrite | 5404 | 3.7% |
| event_injector | 4864 | 3.3% |
| character_agent:char_xuming | 4318 | 2.9% |
| character_agent:char_liuboshi | 3899 | 2.7% |
| character_agent:char_afen | 3387 | 2.3% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 69217 |
| critical | 77602 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 5747 | 92.87 | 662 | narrator=3263, world_simulator=2484 |
| 2 | 6442 | 93.4 | 679 | narrator=4027, world_simulator=2415 |
| 3 | 7231 | 110.68 | 1106 | narrator=4387, world_simulator=2844 |
| 4 | 8402 | 127.75 | 159 | narrator=5091, world_simulator=3311 |
| 5 | 11283 | 184.92 | 0 | narrator=4648, showrunner=3627, world_simulator=3008 |
| 6 | 6913 | 90.61 | 0 | world_simulator=3694, narrator=3219 |
| 7 | 8685 | 135.11 | 246 | narrator=4801, world_simulator=3884 |
| 8 | 6491 | 77.69 | 269 | narrator=4891, world_simulator=1600 |
| 9 | 6994 | 99.83 | 815 | narrator=4342, world_simulator=2652 |
| 10 | 37419 | 440.53 | 723 | narrator=7447, narrative_critic:rewrite=5404, event_injector=4864 |
| 11 | 7480 | 83.14 | 791 | narrator=4262, world_simulator=3218 |
| 12 | 6524 | 77.63 | 788 | narrator=4182, world_simulator=2342 |
| 13 | 7051 | 87.39 | 768 | narrator=4592, world_simulator=2459 |
| 14 | 8166 | 115.33 | 70 | narrator=5222, world_simulator=2944 |
| 15 | 11991 | 184.2 | 366 | showrunner=4842, world_simulator=3643, narrator=3506 |

## First narrative sample

```
雾刚吞掉码头最后一盏灯，雨就大了。苏默把伞往左倾，避开低洼处倒涌上来的脏水。井盖缝隙里钻出的白汽被雨水打散，混进更浓的雾里，裹住半条街。远处，货船的汽笛又响了一声，闷，拖得长，像叹气。

他走得急。档案馆的安全屋在三条街外，穿过这片旧蒸汽站台区就到。怀里揣着的东西硬邦邦的，顶着肋骨——是今早刚从密库调出来的卷宗附录，关于“静默矿”采掘点的几页零散记录。守密会那几个老家伙让他务必在入夜前送到，原话是“不能再拖了”。

雨砸在伞面上，又从边缘浇下来，裤脚已经湿透，冷意顺着腿往上爬。苏默没停。蒸汽管道从两侧废墟的墙体里探出来，有的在滴水，有的嘶嘶漏着气，把原本就模糊的轮廓搅得更碎。他绕过一摊积水，水里映着头顶一盏将灭未灭的瓦斯路灯，晃荡着，像只浑浊的眼。

就在这时，他眼角余光里有什么动了一下。

很近，大概二十步外，一截断裂的承重墙后面。雾气浓得发白，但那东西的颜色更深，而且太快了——像个人影，侧着身，猛地缩回墙后的黑暗里。几乎同时，一片被雨水泡胀的锈铁皮从那堵墙上方松脱，哐啷一声砸进水塘，溅起老高的泥水。

苏默的脚步钉在原地。

伞沿淌下的水线在他眼前拉成一道帘。他没去摸腰间，只是更紧地攥住了伞柄，指节发白。那后面是什么？帝国的探子？还是“预言猎人”那帮疯狗跟到了这里？怀里那几页纸忽然变得滚烫。

雨声里，货船的汽笛第三次响起，比前两次更远，更模糊。雾墙之后，再没有任何动静，只有水从高处滴落的单调声响，嗒，嗒，嗒。

他重新迈步，速度比刚才更快了些，鞋底碾过碎砾和积水，走向安全屋的方向，一次也没有回头。
```
