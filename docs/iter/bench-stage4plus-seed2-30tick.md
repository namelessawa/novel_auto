# Bench: stage4plus-seed2-30tick

- novel_id: `bench_stage4plus-seed2-30tick_1781178658`
- ticks: 30
- bootstrap_sec: 403.14
- tick_durations_sec: [94.71, 93.68, 127.13, 109.17, 118.23, 102.51, 103.89, 95.29, 99.15, 386.4, 84.85, 96.54, 109.31, 108.42, 126.99, 35.71, 93.64, 121.96, 114.38, 156.25, 270.7, 102.69, 122.99, 107.66, 169.91, 116.57, 77.49, 88.81, 77.79, 226.35]
- total_tokens: 292673
- call_count: 76
- narrative_chars_total: 11612
- tokens_per_char: 25.20

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 136211 | 46.5% |
| world_simulator | 87102 | 29.8% |
| showrunner | 24665 | 8.4% |
| event_injector | 9305 | 3.2% |
| narrative_critic:critique | 7846 | 2.7% |
| character_arc_tracker | 6103 | 2.1% |
| character_agent:char_si_mo | 4144 | 1.4% |
| character_agent:char_lin_xue | 3799 | 1.3% |
| novelty_critic | 3669 | 1.3% |
| character_agent:char_zhao_gui_zhen | 3351 | 1.1% |
| character_agent:char_su_mu | 3287 | 1.1% |
| character_agent:char_shen_mo | 3191 | 1.1% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 127710 |
| critical | 155191 |
| optional | 9772 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6699 | 94.71 | 0 | narrator=4339, world_simulator=2360 |
| 2 | 6480 | 93.68 | 464 | narrator=3527, world_simulator=2953 |
| 3 | 7440 | 127.13 | 343 | narrator=4818, world_simulator=2622 |
| 4 | 7775 | 109.17 | 270 | narrator=4810, world_simulator=2965 |
| 5 | 9359 | 118.23 | 0 | showrunner=3149, world_simulator=3114, narrator=3096 |
| 6 | 7385 | 102.51 | 706 | narrator=4516, world_simulator=2869 |
| 7 | 7899 | 103.89 | 387 | narrator=4585, world_simulator=3314 |
| 8 | 6932 | 95.29 | 758 | narrator=3755, world_simulator=3177 |
| 9 | 7313 | 99.15 | 1011 | narrator=4218, world_simulator=3095 |
| 10 | 35669 | 386.4 | 999 | narrator=7458, event_injector=5679, showrunner=4471 |
| 11 | 7301 | 84.85 | 684 | narrator=4289, world_simulator=3012 |
| 12 | 7351 | 96.54 | 717 | narrator=4097, world_simulator=3254 |
| 13 | 8154 | 109.31 | 24 | narrator=5148, world_simulator=3006 |
| 14 | 7083 | 108.42 | 638 | narrator=4578, world_simulator=2505 |
| 15 | 10497 | 126.99 | 0 | narrator=4180, showrunner=3440, world_simulator=2877 |
| 16 | 2293 | 35.71 | 0 | world_simulator=2293 |
| 17 | 7472 | 93.64 | 221 | narrator=5177, world_simulator=2295 |
| 18 | 8047 | 121.96 | 0 | narrator=4864, world_simulator=3183 |
| 19 | 7905 | 114.38 | 565 | narrator=4025, world_simulator=3880 |
| 20 | 15090 | 156.25 | 0 | narrator=5239, showrunner=4276, novelty_critic=3669 |
| 21 | 25293 | 270.7 | 645 | narrator=6855, character_agent:char_si_mo=4144, narrative_critic:critique=3782 |
| 22 | 7844 | 102.69 | 0 | narrator=5200, world_simulator=2644 |
| 23 | 8312 | 122.99 | 0 | narrator=5251, world_simulator=3061 |
| 24 | 8334 | 107.66 | 404 | narrator=5278, world_simulator=3056 |
| 25 | 12287 | 169.91 | 881 | showrunner=4831, narrator=4658, world_simulator=2798 |
| 26 | 8493 | 116.57 | 4 | narrator=5296, world_simulator=3197 |
| 27 | 6143 | 77.49 | 395 | narrator=4057, world_simulator=2086 |
| 28 | 6768 | 88.81 | 382 | narrator=4113, world_simulator=2655 |
| 29 | 6143 | 77.79 | 515 | narrator=3882, world_simulator=2261 |
| 30 | 18912 | 226.35 | 599 | character_arc_tracker=6103, narrator=4902, showrunner=4498 |

## First narrative sample

```
石板路上的水渍干了大半，鞋底踩上去不再打滑。苏默把帆布挎包带子往肩上提了提，侧耳听了一阵。雾号声不知何时歇了，江面上传来沉闷的汽笛，一下，又一下，接着是引擎开始吃力的轰鸣——有船在启航。

他走到芦苇荡边缘的土坡上。晨光从东边漫过来，把叶片上的露水照得成了碎银。风很小，空气里有水汽和淤泥的味道。他蹲下，从挎包里掏出那台自己组装的接收器，铜线圈上还沾着昨夜的潮气。手指在调频旋钮上慢慢捻动，耳机里先是一片空茫的沙沙声，像远处雨落。

然后杂音里浮出一个极细微的、规律性的断续。不是莫尔斯码，是别的什么。频率正好在loop_4里记录过的那个共振点上。他屏住呼吸，把音量拧到最大。那断续声清晰了一点，像手指在铁皮上极轻地叩击，没节奏，没内容，就只是存在。

林雪的诗句。那句“失语之春”。它成了密钥，而密钥在空气里响。

苏默摘下一边耳机。鸟鸣从芦苇深处传来，一声接一声，活的。江上汽笛又响了，这次远了些。他低头看那台接收器，旋钮上的刻度盘，细小的数字因为受潮有点洇。

他听见自己的心跳。和耳机里那断续的、无意义的叩击，叠在一起。
```
