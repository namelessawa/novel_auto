# Bench: stage1-v15-15tick

- novel_id: `bench_stage1-v15-15tick_1781144461`
- ticks: 15
- bootstrap_sec: 506.87
- tick_durations_sec: [186.27, 106.63, 168.66, 193.81, 231.74, 148.68, 142.98, 168.27, 110.1, 464.31, 171.25, 178.52, 144.12, 238.19, 254.27]
- total_tokens: 188873
- call_count: 46
- narrative_chars_total: 8826
- tokens_per_char: 21.40

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 80001 | 42.4% |
| world_simulator | 44128 | 23.4% |
| narrative_critic:critique | 31206 | 16.5% |
| showrunner | 12523 | 6.6% |
| narrative_critic:rewrite | 6947 | 3.7% |
| event_injector | 6046 | 3.2% |
| character_agent:char_zhangbu | 4039 | 2.1% |
| character_agent:char_xuanya | 3983 | 2.1% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 70719 |
| critical | 118154 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 11151 | 186.27 | 616 | narrator=4583, narrative_critic:critique=3761, world_simulator=2807 |
| 2 | 6603 | 106.63 | 395 | narrator=4750, world_simulator=1853 |
| 3 | 11136 | 168.66 | 610 | narrator=4282, narrative_critic:critique=3748, world_simulator=3106 |
| 4 | 11127 | 193.81 | 447 | narrator=5044, world_simulator=3112, narrative_critic:rewrite=2971 |
| 5 | 11930 | 231.74 | 0 | narrator=5243, showrunner=3677, world_simulator=3010 |
| 6 | 9393 | 148.68 | 318 | narrator=5724, world_simulator=3669 |
| 7 | 11164 | 142.98 | 862 | narrator=4546, narrative_critic:critique=3917, world_simulator=2701 |
| 8 | 12056 | 168.27 | 710 | narrator=5083, narrative_critic:critique=3815, world_simulator=3158 |
| 9 | 8491 | 110.1 | 497 | narrator=5721, world_simulator=2770 |
| 10 | 29490 | 464.31 | 0 | narrator=7749, event_injector=6046, showrunner=4427 |
| 11 | 11752 | 171.25 | 671 | narrator=5485, narrative_critic:critique=3791, world_simulator=2476 |
| 12 | 12786 | 178.52 | 1180 | narrator=5553, narrative_critic:critique=4168, world_simulator=3065 |
| 13 | 11479 | 144.12 | 735 | narrator=4963, narrative_critic:critique=3814, world_simulator=2702 |
| 14 | 13420 | 238.19 | 547 | narrator=5993, narrative_critic:rewrite=3976, world_simulator=3451 |
| 15 | 16895 | 254.27 | 1238 | narrator=5282, showrunner=4419, narrative_critic:critique=4192 |

## First narrative sample

```
苏默的靴子陷进泥里，拔出来时发出黏腻的声响。他低头看了看，鞋面上的泥点在煤油灯的光晕里泛着黑。雨水顺着破旧的油布伞边沿淌下来，在脚边砸出一个个小坑。街道两侧的蒸汽管道嘶嘶作响，吐出带着铁锈味的白雾，和雨搅在一起，把视野搅得模模糊糊。
远处传来蒸汽机规律的轰隆声，像一颗巨大心脏在雾里跳动。偶尔有金属零件松脱或撞击的“哐当”声夹杂其中，听着让人心头发紧。他握紧了伞柄，骨节发白。目的地是三条街外的安全屋。管理局的林雪半小时前用老线路发了急电，没说什么事，只让他立刻过去。
巷口的阴影里有动静。苏默没停步，伞面微微倾斜，挡住半边视线。脚步加快，靴底碾过碎石。汽笛声穿透雨雾，短促，尖锐，是港口方向。船只进出的信号。这个点，不该有船。
他拐进另一条更窄的巷子，这里没有路灯，只有住户窗缝里漏出的零星光点。泥水没到了脚踝。墙壁潮湿，长满暗绿色的苔藓。他贴着墙根走，呼吸放得很轻。
安全屋的后门就在前面。门牌被雨水冲刷得看不清字。苏默收起伞，甩了甩水，伸手去推门。门没锁，虚掩着，露出一条缝。他顿了顿，从腰后摸出那把老式的转轮手枪。枪身冰凉，沾着雨水。
他侧身挤进门里。屋内更暗，弥漫着陈旧纸张和煤灰混合的气味。他没开灯，借着窗外微弱的光，看见桌上放着一个打开的铁皮盒子。盒子里是空的。林雪不在。
桌角压着一张纸条，纸被水汽浸得有些发皱。他拿起纸条，就着光看。上面只有一行字，笔迹急促，墨迹有些化开了：
“卷宗被调包了。她在哭。别来管理局。”
```
