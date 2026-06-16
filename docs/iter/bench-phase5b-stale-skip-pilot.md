# Bench: phase5b-stale-skip-pilot

- novel_id: `bench_phase5b-stale-skip-pilot_1781585844`
- ticks: 5
- bootstrap_sec: 314.94
- tick_durations_sec: [78.63, 0.05, 0.05, 71.26, 62.54]
- total_tokens: 17967
- call_count: 5
- narrative_chars_total: 791
- tokens_per_char: 22.71

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 8833 | 49.2% |
| showrunner | 4801 | 26.7% |
| world_simulator | 4333 | 24.1% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 9134 |
| critical | 8833 |

## Cache hit rate (Phase 5-A)

- total prompt_tokens: 8960
- total cached_tokens: 4096
- overall hit rate: 45.7%

| agent | prompt | cached | hit% |
| --- | ---: | ---: | ---: |
| narrator | 5683 | 3072 | 54.1% |
| showrunner | 2015 | 1024 | 50.8% |
| world_simulator | 1262 | 0 | 0.0% |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6722 | 78.63 | 321 | narrator=4704, world_simulator=2018 |
| 2 | 0 | 0.05 | 0 |  |
| 3 | 0 | 0.05 | 0 |  |
| 4 | 6444 | 71.26 | 470 | narrator=4129, world_simulator=2315 |
| 5 | 4801 | 62.54 | 0 | showrunner=4801 |

## First narrative sample

```
酸雨打在铁皮屋檐上，滴答声密得像缝纫机。苏默拉低帽檐，靴子踩进街面的积水，油花溅到裤脚，散开一圈虹彩。他侧身避开一辆陷在泥里的板车，车辙深得能没过脚踝，远处山道传来金属摩擦的吱呀——生锈的货运缆车又卡住了。港口方向，蒸汽阀门自动泄压，白雾喷涌而出，裹着煤灰扑在他脸上，他用手背抹了把眼睛。档案袋捂在怀里，牛皮纸边缘已经潮软。安全屋在三条街外的面包店地下室，得快些。转过拐角时，他停住脚。巷子深处，有人蜷在漏水的檐下，膝盖抵着胸口，头发黏在额头上，滴水的发梢指向一张苍白的脸。苏默右手滑进外套口袋，指尖碰触折叠刀的金属鞘。那女人抬起头，嘴唇冻得发紫，眼睛在灰蒙蒙的光线里显得异常清醒。她张了张嘴，喉咙里没发出声音，只是伸出一只手，掌心向上摊开。
```
