# Bench: phase5-mimo-B-stale-on-retry

- novel_id: `bench_phase5-mimo-B-stale-on-retry_1781592558`
- ticks: 20
- bootstrap_sec: 465.5
- tick_durations_sec: [77.78, 0.02, 0.02, 93.65, 75.63, 0.02, 129.65, 0.02, 0.02, 326.49, 174.06, 0.02, 0.02, 62.73, 114.99, 0.02, 106.39, 0.02, 0.02, 191.57]
- total_tokens: 82105
- call_count: 22
- narrative_chars_total: 2300
- tokens_per_char: 35.70

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 35532 | 43.3% |
| showrunner | 19195 | 23.4% |
| world_simulator | 17438 | 21.2% |
| event_injector | 4499 | 5.5% |
| novelty_critic | 3025 | 3.7% |
| character_agent:char_linxue | 2416 | 2.9% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 41132 |
| critical | 37948 |
| optional | 3025 |

## Cache hit rate (Phase 5-A)

- total prompt_tokens: 40160
- total cached_tokens: 18432
- overall hit rate: 45.9%

| agent | prompt | cached | hit% |
| --- | ---: | ---: | ---: |
| narrator | 21616 | 13312 | 61.6% |
| showrunner | 8466 | 4096 | 48.4% |
| world_simulator | 5353 | 0 | 0.0% |
| event_injector | 2166 | 1024 | 47.3% |
| character_agent:char_linxue | 1554 | 0 | 0.0% |
| novelty_critic | 1005 | 0 | 0.0% |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 5565 | 77.78 | 530 | narrator=3818, world_simulator=1747 |
| 2 | 0 | 0.02 | 0 |  |
| 3 | 0 | 0.02 | 0 |  |
| 4 | 6888 | 93.65 | 469 | narrator=5342, world_simulator=1546 |
| 5 | 4409 | 75.63 | 0 | showrunner=4409 |
| 6 | 0 | 0.02 | 0 |  |
| 7 | 7554 | 129.65 | 0 | narrator=5331, world_simulator=2223 |
| 8 | 0 | 0.02 | 0 |  |
| 9 | 0 | 0.02 | 0 |  |
| 10 | 19662 | 326.49 | 611 | narrator=6765, event_injector=4499, showrunner=4394 |
| 11 | 9328 | 174.06 | 144 | narrator=5524, world_simulator=3804 |
| 12 | 0 | 0.02 | 0 |  |
| 13 | 0 | 0.02 | 0 |  |
| 14 | 2672 | 62.73 | 0 | world_simulator=2672 |
| 15 | 5172 | 114.99 | 0 | showrunner=5172 |
| 16 | 0 | 0.02 | 0 |  |
| 17 | 6778 | 106.39 | 15 | narrator=5095, world_simulator=1683 |
| 18 | 0 | 0.02 | 0 |  |
| 19 | 0 | 0.02 | 0 |  |
| 20 | 14077 | 191.57 | 531 | showrunner=5220, narrator=3657, novelty_critic=3025 |

## First narrative sample

```
钟声从雾深处落下来，沉闷，被潮湿的空气吃掉了大半。苏默停住脚步，数了三下。不是报时。钟声又响，间隔不规则，像某个齿轮咬合出了毛病。

锤击声从左侧传来，节奏缓慢，一下接一下。蒸汽锤。她辨认出方向——铸铁厂的方向，隔着三条街。声音穿过雾层变得含混，仿佛整座城都在敲打自己。风裹着铁锈和机油的味道扑过来，她用袖口捂了一下鼻子，继续走。

石板路上积水很深，靴子踩下去，水没过脚踝。墙壁渗出锈色的水痕，一道一道，像陈年的伤。她贴着墙根走，手扶着砖面，指尖冰凉，蹭到一层黏腻的油膜。雾浓得看不见下一个转角的路灯杆，只能靠脚底板记住路——左脚踩到松动的那块砖，再走七步，右拐。

转过弯，雾里浮出建筑的轮廓。无声神殿的钟塔尖顶戳进灰白色的天空，像一根生锈的针。第二声钟鸣这时候落下来，比刚才近，比刚才重。苏默加快脚步，靴底在石板上打出急促的水声。

铁门还没开。她摸到门环，指节叩上去，铜环冰得刺骨。门缝里透出微弱的光，有人在里面点灯了。她又叩了三下，节奏刻意放慢。暗号。

门轴发出低哑的呻吟，露出一道窄缝。一双浑浊的眼睛从缝隙里看出来，盯了她两秒，没有说话。她侧身挤进去，靴子在门槛上刮出一道水痕。

身后，雾气吞没了街道。锤击声还在，一下，一下，比钟声更慢，更沉。
```
