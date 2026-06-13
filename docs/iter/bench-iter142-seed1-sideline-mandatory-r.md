# Bench: iter142-seed1-sideline-mandatory-r

- novel_id: `bench_iter142-seed1-sideline-mandatory-r_1781313784`
- ticks: 50
- bootstrap_sec: 317.2
- tick_durations_sec: [102.0, 130.36, 83.94, 103.55, 174.5, 94.75, 116.66, 70.34, 114.88, 336.68, 108.6, 115.89, 112.96, 58.48, 152.72, 127.95, 125.68, 87.42, 116.07, 184.98, 294.84, 90.31, 96.31, 108.21, 170.04, 94.54, 90.61, 109.24, 127.81, 223.15, 116.92, 410.37, 136.43, 121.59, 212.15, 130.35, 119.61, 136.46, 126.71, 232.29, 156.23, 151.78, 335.07, 130.71, 203.32, 123.46, 109.35, 139.43, 97.47, 206.4]
- total_tokens: 566526
- call_count: 126
- narrative_chars_total: 29469
- tokens_per_char: 19.22

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 293487 | 51.8% |
| world_simulator | 151693 | 26.8% |
| showrunner | 52353 | 9.2% |
| event_injector | 22431 | 4.0% |
| character_agent:char_linxue | 11023 | 1.9% |
| character_agent:char_sumo | 7821 | 1.4% |
| novelty_critic | 7354 | 1.3% |
| character_agent:char_zhaotie | 7278 | 1.3% |
| character_arc_tracker | 5720 | 1.0% |
| narrative_critic:critique | 4413 | 0.8% |
| character_agent:char_tiechui | 2953 | 0.5% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 236708 |
| critical | 316744 |
| optional | 13074 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 7988 | 102.0 | 0 | narrator=5384, world_simulator=2604 |
| 2 | 8476 | 130.36 | 0 | narrator=5475, world_simulator=3001 |
| 3 | 7313 | 83.94 | 0 | narrator=4094, world_simulator=3219 |
| 4 | 8231 | 103.55 | 786 | narrator=5267, world_simulator=2964 |
| 5 | 14061 | 174.5 | 864 | narrator=5725, showrunner=5095, world_simulator=3241 |
| 6 | 8531 | 94.75 | 997 | narrator=5572, world_simulator=2959 |
| 7 | 9164 | 116.66 | 1428 | narrator=5826, world_simulator=3338 |
| 8 | 7265 | 70.34 | 0 | narrator=5502, world_simulator=1763 |
| 9 | 9342 | 114.88 | 795 | narrator=5817, world_simulator=3525 |
| 10 | 27520 | 336.68 | 1529 | narrator=7109, showrunner=4982, event_injector=4871 |
| 11 | 8731 | 108.6 | 1077 | narrator=5639, world_simulator=3092 |
| 12 | 9075 | 115.89 | 786 | narrator=6251, world_simulator=2824 |
| 13 | 8874 | 112.96 | 1176 | narrator=6192, world_simulator=2682 |
| 14 | 6929 | 58.48 | 0 | narrator=4498, world_simulator=2431 |
| 15 | 13692 | 152.72 | 4 | narrator=6182, showrunner=4952, world_simulator=2558 |
| 16 | 8460 | 127.95 | 762 | narrator=5161, world_simulator=3299 |
| 17 | 8738 | 125.68 | 933 | narrator=5660, world_simulator=3078 |
| 18 | 7760 | 87.42 | 0 | narrator=5372, world_simulator=2388 |
| 19 | 8846 | 116.07 | 1194 | narrator=5954, world_simulator=2892 |
| 20 | 17970 | 184.98 | 458 | narrator=5893, showrunner=5299, novelty_critic=3698 |
| 21 | 27457 | 294.84 | 343 | narrator=8808, event_injector=5668, character_agent:char_zhaotie=3858 |
| 22 | 8006 | 90.31 | 724 | narrator=4875, world_simulator=3131 |
| 23 | 8419 | 96.31 | 882 | narrator=5600, world_simulator=2819 |
| 24 | 9205 | 108.21 | 213 | narrator=6185, world_simulator=3020 |
| 25 | 13682 | 170.04 | 643 | showrunner=5371, narrator=4462, world_simulator=3849 |
| 26 | 8215 | 94.54 | 868 | narrator=5148, world_simulator=3067 |
| 27 | 8209 | 90.61 | 121 | narrator=6287, world_simulator=1922 |
| 28 | 8550 | 109.24 | 625 | narrator=4590, world_simulator=3960 |
| 29 | 9952 | 127.81 | 313 | narrator=6127, world_simulator=3825 |
| 30 | 20072 | 223.15 | 675 | narrator=5793, character_arc_tracker=5720, showrunner=5397 |
| 31 | 9208 | 116.92 | 592 | narrator=5804, world_simulator=3404 |
| 32 | 32000 | 410.37 | 781 | narrator=10441, event_injector=6126, character_agent:char_sumo=4237 |
| 33 | 10073 | 136.43 | 844 | narrator=6048, world_simulator=4025 |
| 34 | 9065 | 121.59 | 0 | narrator=6158, world_simulator=2907 |
| 35 | 14075 | 212.15 | 1128 | narrator=6214, showrunner=5425, world_simulator=2436 |
| 36 | 9526 | 130.35 | 0 | narrator=6225, world_simulator=3301 |
| 37 | 8287 | 119.61 | 0 | narrator=6341, world_simulator=1946 |
| 38 | 9240 | 136.46 | 1162 | narrator=6391, world_simulator=2849 |
| 39 | 8689 | 126.71 | 907 | narrator=5716, world_simulator=2973 |
| 40 | 18424 | 232.29 | 687 | showrunner=5582, narrator=5531, novelty_critic=3656 |
| 41 | 10023 | 156.23 | 798 | narrator=6304, world_simulator=3719 |
| 42 | 9653 | 151.78 | 37 | narrator=6370, world_simulator=3283 |
| 43 | 19616 | 335.07 | 208 | narrator=6684, event_injector=5766, character_agent:char_linxue=3984 |
| 44 | 8947 | 130.71 | 525 | narrator=5818, world_simulator=3129 |
| 45 | 13731 | 203.32 | 775 | showrunner=5479, narrator=5316, world_simulator=2936 |
| 46 | 8661 | 123.46 | 886 | narrator=5722, world_simulator=2939 |
| 47 | 8370 | 109.35 | 975 | narrator=5257, world_simulator=3113 |
| 48 | 9046 | 139.43 | 815 | narrator=6015, world_simulator=3031 |
| 49 | 7926 | 97.47 | 149 | narrator=5128, world_simulator=2798 |
| 50 | 13233 | 206.4 | 4 | narrator=5556, showrunner=4771, world_simulator=2906 |

## First narrative sample

```
冻雾的质感变了。不再是弥漫的水汽，而是细小的冰晶，撞在脸上像针扎。林雪呼出的白气瞬间凝结，挂在眉睫上，视野里只剩下一片浑浊的灰白。脚下的石板路泛着一层湿黑的光，那是冰壳，薄得几乎看不见，却让每一步都变成赌注。

左侧传来金属扭曲的脆响。一个机械仆从——那种负责清扫街道的六足型号——正试图保持平衡，一条支撑腿却朝奇怪的角度滑开。它关节处的蒸汽喷射了几下，徒劳地想稳住，最终还是重重侧翻在地。外壳撞击地面，发出空洞的闷响。它挣扎着，几条腿徒劳地在冰面上划动，刮擦声刺耳，最终只剩一盏维修灯在浓雾里徒劳地闪烁，光晕被冰晶切割得支离破碎。

林雪停下脚步。不是为了那个仆从。是声音。远处的嗡鸣声变了调，不再是低沉的背景音，而是拔高、尖锐，像无数片薄铁皮在高速震颤。金属撞击声夹杂其中，清脆而密集，越来越近。她退到街边一个废弃的报亭阴影里，背抵着冰冷的木板。冰晶在她的衣料上积了薄薄一层。

雾气翻涌。阴影确实在动，不是错觉。隔着一条街的废弃摊位区，帆布棚子在无风的状态下轻微鼓动，下方积尘的地面出现了模糊的、非人的足迹——不是脚印，更像是沉重的、带棱角的东西拖拽而过留下的压痕，断断续续，消失在更深的雾里。她蹲下身，指尖拂过最近的一处压痕边缘。冰凉。压痕的深度显示那东西不轻。

追查陈缄传来的那些破碎机械信号时，她曾在齿轮议会的加密档案里见过类似的描述。不是动物。是某种…更固定的东西，在不该移动的时候移动了。档案里提到了钟楼。她甩甩头，驱散这个念头。眼前压痕的走向，似乎正朝着雾气中齿轮钟楼那模糊的、巨大的黑影轮廓方向延伸过去。

更近了。尖锐的嗡鸣声已经裹挟着气流，吹得她面前的雾气形成涡旋。伴随着声音，是沉重、不规则的落地声，咚，咚，咚，正在逼近这条街。

林雪的手按在腰间短棍的握柄上，指节收紧。她看着机械仆从那盏还在闪烁的维修灯，光一下，一下，映亮了地面蔓延的冰纹。
```
