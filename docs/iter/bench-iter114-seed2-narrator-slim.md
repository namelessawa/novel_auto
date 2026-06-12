# Bench: iter114-seed2-narrator-slim

- novel_id: `bench_iter114-seed2-narrator-slim_1781235759`
- ticks: 50
- bootstrap_sec: 454.85
- tick_durations_sec: [106.89, 96.18, 101.36, 88.11, 156.73, 107.49, 98.04, 103.25, 106.67, 335.46, 140.39, 169.69, 154.29, 110.05, 163.74, 104.52, 96.43, 99.26, 84.17, 163.04, 222.63, 208.6, 164.28, 167.19, 276.14, 187.72, 141.39, 137.66, 110.68, 161.1, 114.88, 284.21, 95.46, 104.9, 173.62, 93.32, 64.15, 112.8, 104.76, 166.93, 123.87, 101.25, 239.25, 102.37, 162.92, 96.65, 95.67, 101.68, 116.29, 179.93]
- total_tokens: 553809
- call_count: 140
- narrative_chars_total: 23286
- tokens_per_char: 23.78

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 238995 | 43.2% |
| world_simulator | 149692 | 27.0% |
| showrunner | 46308 | 8.4% |
| character_agent:char_susu | 44771 | 8.1% |
| character_agent:char_satuoluo | 30674 | 5.5% |
| event_injector | 19419 | 3.5% |
| character_agent:char_linxue | 8386 | 1.5% |
| novelty_critic | 7618 | 1.4% |
| character_arc_tracker | 4393 | 0.8% |
| character_agent:char_sumo | 3553 | 0.6% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 246093 |
| critical | 295705 |
| optional | 12011 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6442 | 106.89 | 519 | narrator=3682, world_simulator=2760 |
| 2 | 7087 | 96.18 | 393 | narrator=4371, world_simulator=2716 |
| 3 | 7158 | 101.36 | 0 | narrator=4784, world_simulator=2374 |
| 4 | 6523 | 88.11 | 98 | narrator=3721, world_simulator=2802 |
| 5 | 10755 | 156.73 | 375 | showrunner=4051, narrator=3534, world_simulator=3170 |
| 6 | 7341 | 107.49 | 372 | narrator=4877, world_simulator=2464 |
| 7 | 6901 | 98.04 | 0 | world_simulator=3515, narrator=3386 |
| 8 | 7102 | 103.25 | 752 | narrator=4501, world_simulator=2601 |
| 9 | 7937 | 106.67 | 636 | narrator=4821, world_simulator=3116 |
| 10 | 22631 | 335.46 | 1136 | narrator=6416, event_injector=4824, showrunner=4399 |
| 11 | 11810 | 140.39 | 0 | narrator=5457, world_simulator=3714, character_agent:char_susu=2639 |
| 12 | 12779 | 169.69 | 0 | narrator=5567, character_agent:char_susu=3769, world_simulator=3443 |
| 13 | 12673 | 154.29 | 0 | narrator=5689, world_simulator=3647, character_agent:char_susu=3337 |
| 14 | 8777 | 110.05 | 313 | narrator=4949, world_simulator=3828 |
| 15 | 12876 | 163.74 | 191 | showrunner=5199, narrator=4591, world_simulator=3086 |
| 16 | 7764 | 104.52 | 309 | narrator=4166, world_simulator=3598 |
| 17 | 7384 | 96.43 | 182 | narrator=4730, world_simulator=2654 |
| 18 | 7108 | 99.26 | 786 | narrator=3868, world_simulator=3240 |
| 19 | 7426 | 84.17 | 80 | narrator=5358, world_simulator=2068 |
| 20 | 16552 | 163.04 | 189 | showrunner=5271, narrator=4541, novelty_critic=3835 |
| 21 | 20909 | 222.63 | 1326 | narrator=5297, event_injector=4885, character_agent:char_susu=3904 |
| 22 | 18883 | 208.6 | 1045 | narrator=5308, world_simulator=4909, character_agent:char_satuoluo=4372 |
| 23 | 15895 | 164.28 | 823 | narrator=5405, character_agent:char_satuoluo=4508, character_agent:char_susu=3624 |
| 24 | 15758 | 167.19 | 0 | narrator=7302, character_agent:char_satuoluo=3648, character_agent:char_susu=2895 |
| 25 | 23638 | 276.14 | 294 | narrator=6043, showrunner=5104, character_agent:char_susu=4285 |
| 26 | 17459 | 187.72 | 1774 | narrator=5614, character_agent:char_susu=4569, character_agent:char_satuoluo=4039 |
| 27 | 16027 | 141.39 | 513 | narrator=5489, character_agent:char_susu=4360, character_agent:char_satuoluo=3653 |
| 28 | 14110 | 137.66 | 870 | narrator=4980, character_agent:char_susu=3247, world_simulator=3236 |
| 29 | 8207 | 110.68 | 0 | narrator=4679, world_simulator=3528 |
| 30 | 16401 | 161.1 | 760 | narrator=4931, showrunner=4635, character_arc_tracker=4393 |
| 31 | 7501 | 114.88 | 889 | narrator=4253, world_simulator=3248 |
| 32 | 18475 | 284.21 | 463 | narrator=6044, event_injector=4887, character_agent:char_linxue=4178 |
| 33 | 6809 | 95.46 | 597 | narrator=3797, world_simulator=3012 |
| 34 | 6830 | 104.9 | 846 | narrator=4036, world_simulator=2794 |
| 35 | 12020 | 173.62 | 445 | narrator=4828, showrunner=3988, world_simulator=3204 |
| 36 | 6585 | 93.32 | 147 | narrator=4779, world_simulator=1806 |
| 37 | 5478 | 64.15 | 0 | narrator=3281, world_simulator=2197 |
| 38 | 7781 | 112.8 | 2 | narrator=4654, world_simulator=3127 |
| 39 | 7334 | 104.76 | 0 | narrator=4516, world_simulator=2818 |
| 40 | 15690 | 166.93 | 592 | showrunner=4868, narrator=4310, novelty_critic=3783 |
| 41 | 8070 | 123.87 | 77 | narrator=4891, world_simulator=3179 |
| 42 | 7334 | 101.25 | 0 | narrator=4544, world_simulator=2790 |
| 43 | 20250 | 239.25 | 1079 | narrator=4937, event_injector=4823, character_agent:char_linxue=4208 |
| 44 | 7838 | 102.37 | 593 | narrator=3952, world_simulator=3886 |
| 45 | 11736 | 162.92 | 760 | narrator=4944, showrunner=4448, world_simulator=2344 |
| 46 | 7381 | 96.65 | 807 | narrator=4127, world_simulator=3254 |
| 47 | 7122 | 95.67 | 778 | narrator=5015, world_simulator=2107 |
| 48 | 7812 | 101.68 | 378 | narrator=4998, world_simulator=2814 |
| 49 | 7762 | 116.29 | 269 | narrator=4507, world_simulator=3255 |
| 50 | 11688 | 179.93 | 828 | narrator=4525, showrunner=4345, world_simulator=2818 |

## First narrative sample

```
雨从子夜下起，到凌晨变成了雾。街灯在潮气里化成一团团昏黄，照不出三步远的石板路。苏默竖起衣领，低头辨认着脚下被水浸得发亮的缝隙。路面的反光模糊了边界，仿佛整个上海都泡在一块走不出去的湿绸布里。

他往旧中央档案馆的方向走。自从上个月那场无名大火把半边楼烧塌了，巡捕房在废墟外围拉了铁丝网，说是等勘查，但谁都知道，里头早被人翻过不止一遍。可有些东西，翻得越干净，留下的痕迹反而越可疑。比如那本该在火场里烧成灰的密码本。

脚步停了。

侧前方传来碎石滑落的细响，很轻，不是野猫。苏默退进一处门洞的阴影里，看着一个裹紧短褂的身影从浓雾中钻出，迅速闪进另一条岔巷。那人手里提着个油纸包，不大，但形状规整。

雾更浓了。苏默继续往前，棚户区的轮廓在远处显露出来。几扇窗户透出灯光，隔着雨幕变成毛茸茸的光团。低语声和木箱挪动的闷响混在雨声里，听不清内容，只觉出一种刻意压低的忙碌。

他停在巷口，没再靠近。棚户深处，一个女人压低的嗓音突然拔高了一瞬：“……表要修，就快点！”随即被另一个人的喝止打断，声音又沉回雾里。

表。苏默把手里捏着的那枚怀表残骸攥紧，冰凉的金属棱角硌着掌心。他看了看棚户透出的光，又回头望了望档案馆废墟的方向，步子拐了方向。
```
