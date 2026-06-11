# Bench: stage4-50tick

- novel_id: `bench_stage4-50tick_1781165647`
- ticks: 50
- bootstrap_sec: 475.28
- tick_durations_sec: [114.29, 94.37, 122.73, 131.71, 174.04, 139.47, 142.09, 136.86, 100.73, 389.33, 121.14, 169.91, 164.34, 107.35, 163.78, 114.9, 141.25, 145.57, 147.15, 210.57, 394.88, 99.15, 108.33, 97.37, 228.41, 128.85, 131.84, 145.76, 130.39, 234.83, 141.95, 379.0, 111.79, 114.83, 172.77, 117.96, 58.36, 97.87, 105.34, 208.52, 141.45, 110.41, 337.82, 108.17, 170.38, 117.95, 91.66, 67.7, 110.71, 183.21]
- total_tokens: 540474
- call_count: 128
- narrative_chars_total: 27185
- tokens_per_char: 19.88

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 266708 | 49.3% |
| world_simulator | 142438 | 26.4% |
| showrunner | 44383 | 8.2% |
| event_injector | 19424 | 3.6% |
| character_agent:char_chengmo | 13994 | 2.6% |
| character_agent:char_linxue | 13551 | 2.5% |
| character_agent:char_sumo | 9977 | 1.8% |
| narrative_critic:critique | 8430 | 1.6% |
| novelty_critic | 7449 | 1.4% |
| character_arc_tracker | 5564 | 1.0% |
| narrative_critic:rewrite | 5490 | 1.0% |
| character_agent:char_ya_ling | 3066 | 0.6% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 209311 |
| critical | 318150 |
| optional | 13013 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6646 | 114.29 | 523 | narrator=4131, world_simulator=2515 |
| 2 | 6684 | 94.37 | 0 | narrator=3960, world_simulator=2724 |
| 3 | 8153 | 122.73 | 98 | narrator=5593, world_simulator=2560 |
| 4 | 7650 | 131.71 | 881 | narrator=4789, world_simulator=2861 |
| 5 | 10890 | 174.04 | 1073 | narrator=5282, showrunner=3197, world_simulator=2411 |
| 6 | 8648 | 139.47 | 149 | narrator=5932, world_simulator=2716 |
| 7 | 8327 | 142.09 | 638 | narrator=5223, world_simulator=3104 |
| 8 | 8555 | 136.86 | 846 | narrator=5459, world_simulator=3096 |
| 9 | 7275 | 100.73 | 684 | narrator=5048, world_simulator=2227 |
| 10 | 28122 | 389.33 | 1192 | narrator=6056, narrative_critic:critique=4142, showrunner=4105 |
| 11 | 8204 | 121.14 | 807 | narrator=4991, world_simulator=3213 |
| 12 | 9581 | 169.91 | 285 | narrator=5859, world_simulator=3722 |
| 13 | 9064 | 164.34 | 67 | narrator=5525, world_simulator=3539 |
| 14 | 7029 | 107.35 | 629 | narrator=4238, world_simulator=2791 |
| 15 | 11136 | 163.78 | 0 | narrator=4464, showrunner=3888, world_simulator=2784 |
| 16 | 7879 | 114.9 | 911 | narrator=5884, world_simulator=1995 |
| 17 | 8811 | 141.25 | 400 | narrator=5308, world_simulator=3503 |
| 18 | 8522 | 145.57 | 137 | narrator=5659, world_simulator=2863 |
| 19 | 8477 | 147.15 | 560 | narrator=5476, world_simulator=3001 |
| 20 | 15635 | 210.57 | 864 | narrator=5007, showrunner=4392, novelty_critic=3506 |
| 21 | 23072 | 394.88 | 743 | narrator=6307, narrative_critic:rewrite=5490, event_injector=5052 |
| 22 | 7587 | 99.15 | 0 | narrator=4544, world_simulator=3043 |
| 23 | 7451 | 108.33 | 872 | narrator=5567, world_simulator=1884 |
| 24 | 7756 | 97.37 | 0 | narrator=4532, world_simulator=3224 |
| 25 | 14178 | 228.41 | 522 | narrator=6095, showrunner=5038, world_simulator=3045 |
| 26 | 8317 | 128.85 | 538 | narrator=5074, world_simulator=3243 |
| 27 | 8193 | 131.84 | 773 | narrator=5224, world_simulator=2969 |
| 28 | 8717 | 145.76 | 1309 | narrator=5397, world_simulator=3320 |
| 29 | 8330 | 130.39 | 1174 | narrator=5232, world_simulator=3098 |
| 30 | 17910 | 234.83 | 874 | character_arc_tracker=5564, narrator=5162, showrunner=4487 |
| 31 | 8782 | 141.95 | 1545 | narrator=5343, world_simulator=3439 |
| 32 | 32086 | 379.0 | 0 | narrator=8351, event_injector=5778, character_agent:char_sumo=4955 |
| 33 | 8577 | 111.79 | 731 | narrator=5231, world_simulator=3346 |
| 34 | 8481 | 114.83 | 875 | narrator=5982, world_simulator=2499 |
| 35 | 12688 | 172.77 | 1079 | narrator=5281, showrunner=4752, world_simulator=2655 |
| 36 | 8615 | 117.96 | 1081 | narrator=6077, world_simulator=2538 |
| 37 | 2897 | 58.36 | 0 | world_simulator=2897 |
| 38 | 8183 | 97.87 | 337 | narrator=5910, world_simulator=2273 |
| 39 | 7403 | 105.34 | 0 | narrator=5641, world_simulator=1762 |
| 40 | 17438 | 208.52 | 0 | narrator=5745, showrunner=5169, novelty_critic=3943 |
| 41 | 9417 | 141.45 | 0 | narrator=5806, world_simulator=3611 |
| 42 | 8718 | 110.41 | 4 | narrator=5887, world_simulator=2831 |
| 43 | 34269 | 337.82 | 1369 | narrator=6962, character_agent:char_chengmo=5574, event_injector=5062 |
| 44 | 8551 | 108.17 | 1049 | narrator=5414, world_simulator=3137 |
| 45 | 12721 | 170.38 | 603 | narrator=4918, showrunner=4882, world_simulator=2921 |
| 46 | 8693 | 117.95 | 49 | narrator=5770, world_simulator=2923 |
| 47 | 7241 | 91.66 | 457 | narrator=5315, world_simulator=1926 |
| 48 | 6460 | 67.7 | 0 | narrator=4576, world_simulator=1884 |
| 49 | 8684 | 110.71 | 453 | narrator=5741, world_simulator=2943 |
| 50 | 13771 | 183.21 | 4 | narrator=5740, showrunner=4473, world_simulator=3558 |

## First narrative sample

```
雨点砸在石板上，细密，持续，像无数只手在敲打铁雾城的脊背。石板被水浸得发黑，缝隙里渗出湿漉漉的泥浆，行人的靴子踩上去，发出吸吮般的闷响，脚步自然就慢了。

木棚下，商贩们正急着收拾摊子。湿气粘在油布和干货上，摸一把，满手凉腻的潮。零星的叫卖声从棚子深处飘出来，带着一股子不甘不愿的黏糊劲儿，被雨声压得断断续续。一个卖劣质怀表的老头把木箱“砰”地合上，锁扣咔嗒一声脆响，他缩着脖子钻出棚子，很快被灰白的雨幕吞没，只剩一个模糊的背影和渐远的跛脚声。

更远处，靠近沼泽的街区，雾就不是雾了，是粘稠的、流动的墙。水面上偶尔鼓起一个气泡，“波”地破裂，吐出一小团更浓的白汽，随即被更大的雾吞没。雨滴落进沼泽，连涟漪都看不见。只有低沉的、来自地底或沼泽深处机械运作的嗡嗡声，透过厚重的水汽和石板路传上来，震得脚底发麻，不知是雨打的，还是那声音。

一个黑影贴着墙根的阴影快速移动，靴底几乎擦着石板，没有多余声响。他在一个巷口停了半秒，抬手抹了一把脸上的雨水，目光扫过雾气弥漫的街道尽头。那里，沼泽的雾与城市的雨幕连成一片，什么都看不清。只有那持续不断的机械嗡鸣，像一颗巨大心脏在湿冷的雨夜里沉闷搏动。

他低下头，裹紧了湿透的外套领口，身影没入更深的雨巷。
```
