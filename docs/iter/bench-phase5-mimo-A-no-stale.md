# Bench: phase5-mimo-A-no-stale

- novel_id: `bench_phase5-mimo-A-no-stale_1781588893`
- ticks: 20
- bootstrap_sec: 386.73
- tick_durations_sec: [93.68, 99.3, 126.29, 100.35, 203.61, 99.51, 115.42, 84.89, 122.81, 292.13, 140.23, 120.89, 116.23, 94.6, 174.06, 101.42, 127.18, 119.93, 145.54, 216.06]
- total_tokens: 178621
- call_count: 47
- narrative_chars_total: 7223
- tokens_per_char: 24.73

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 93121 | 52.1% |
| world_simulator | 54455 | 30.5% |
| showrunner | 20031 | 11.2% |
| event_injector | 3956 | 2.2% |
| novelty_critic | 3622 | 2.0% |
| character_agent:char_linxue | 3436 | 1.9% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 78442 |
| critical | 96557 |
| optional | 3622 |

## Cache hit rate (Phase 5-A)

- total prompt_tokens: 84782
- total cached_tokens: 24576
- overall hit rate: 29.0%

| agent | prompt | cached | hit% |
| --- | ---: | ---: | ---: |
| narrator | 55851 | 20480 | 36.7% |
| world_simulator | 14575 | 0 | 0.0% |
| showrunner | 9366 | 4096 | 43.7% |
| event_injector | 2061 | 0 | 0.0% |
| novelty_critic | 1574 | 0 | 0.0% |
| character_agent:char_linxue | 1355 | 0 | 0.0% |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 5999 | 93.68 | 511 | narrator=3535, world_simulator=2464 |
| 2 | 7387 | 99.3 | 165 | narrator=4853, world_simulator=2534 |
| 3 | 6862 | 126.29 | 658 | narrator=3842, world_simulator=3020 |
| 4 | 7212 | 100.35 | 223 | narrator=5084, world_simulator=2128 |
| 5 | 12874 | 203.61 | 38 | showrunner=4948, narrator=4746, world_simulator=3180 |
| 6 | 6448 | 99.51 | 804 | narrator=4070, world_simulator=2378 |
| 7 | 8239 | 115.42 | 0 | narrator=5203, world_simulator=3036 |
| 8 | 6629 | 84.89 | 653 | narrator=4938, world_simulator=1691 |
| 9 | 8095 | 122.81 | 0 | narrator=5037, world_simulator=3058 |
| 10 | 19611 | 292.13 | 0 | narrator=5016, showrunner=4477, event_injector=3956 |
| 11 | 8276 | 140.23 | 379 | narrator=5226, world_simulator=3050 |
| 12 | 7968 | 120.89 | 0 | narrator=5020, world_simulator=2948 |
| 13 | 7541 | 116.23 | 595 | narrator=4965, world_simulator=2576 |
| 14 | 7012 | 94.6 | 652 | narrator=4366, world_simulator=2646 |
| 15 | 12291 | 174.06 | 674 | showrunner=5392, narrator=4224, world_simulator=2675 |
| 16 | 6822 | 101.42 | 776 | narrator=3960, world_simulator=2862 |
| 17 | 7813 | 127.18 | 0 | narrator=5064, world_simulator=2749 |
| 18 | 7180 | 119.93 | 712 | narrator=4297, world_simulator=2883 |
| 19 | 7917 | 145.54 | 6 | narrator=5061, world_simulator=2856 |
| 20 | 16445 | 216.06 | 377 | showrunner=5214, narrator=4614, novelty_critic=3622 |

## First narrative sample

```
雨水在锈蚀的铁皮檐槽里积满，溢出来，顺着墙根往下淌，汇入街道上浑浊的泥水。苏默把领子又竖高了一些，雨水还是从脖颈后渗进去，凉意顺着脊椎往下爬。远处，齿轮港中央的钢铁烟囱群吐出低沉的汽笛，一声接一声，沉闷地压过雨幕，那是夜班轮换的信号。他加快脚步，靴子踩进泥泞，每拔一次都带起黏腻的声响。

雾薄了些，但空气里的煤烟味反而更呛人，混着铁锈和水汽，堵在胸口。他沿着背街走，尽量贴着墙根的阴影。主街的光太亮，也太招眼。提灯的光晕在巷口一晃，他立刻停住，背贴上冰凉潮湿的砖墙。灯光摇曳着，被雨丝切割，逐渐移近——两个穿着油布雨衣的身影，肩上挎着长棍，是齿轮集团的巡逻队。靴子踏过水洼的声音清晰可闻。苏默屏住呼吸，手按在怀里硬邦邦的铁皮筒上，那东西冰凉，但比此刻的雨更让人安心。

灯光晃过巷口，并没有照进来。脚步声渐渐远了，融进持续的雨声里。他吐出一口气，呼吸压在喉底。不能耽搁了。安全屋就在三个街区外，一间废弃的铆钉厂地下室。他需要在下一轮巡逻间隙赶到。苏默重新迈步，这次走得更急，泥水溅上裤腿。街角那盏唯一的煤气路灯在雨中晕开一团模糊的黄光，像一只疲倦的眼睛。他看见那光晕之下，安全屋所在的铆钉厂那扇锈蚀的侧门，虚掩着一条缝。
```
