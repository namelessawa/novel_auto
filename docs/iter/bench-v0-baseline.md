# Bench: v0-baseline

- novel_id: `bench_v0-baseline_1781108894`
- ticks: 3
- bootstrap_sec: 500.76
- tick_durations_sec: [477.28, 613.66, 579.4]
- total_tokens: 137890
- call_count: 23

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrative_critic:critique | 51450 | 37.3% |
| narrator | 19904 | 14.4% |
| world_simulator | 19427 | 14.1% |
| narrative_critic:rewrite | 13724 | 10.0% |
| character_agent:char_lin_xue | 8801 | 6.4% |
| character_agent:char_lao_zhou | 8408 | 6.1% |
| character_agent:char_chen_gang | 7736 | 5.6% |
| character_agent:char_su_mo | 4246 | 3.1% |
| character_agent:char_ma_sha | 4194 | 3.0% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 36275 |
| critical | 101615 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 33494 | 477.28 | 482 | narrative_critic:critique=13628, world_simulator=5337, narrative_critic:rewrite=5292 |
| 2 | 55884 | 613.66 | 940 | narrative_critic:critique=18936, world_simulator=8093, narrator=7430 |
| 3 | 48512 | 579.4 | 683 | narrative_critic:critique=18886, narrator=7483, world_simulator=5997 |

## First narrative sample

```
雨砸下来。每滴带铁锈味，砸进泥里，炸开浑浊点。泥深过踝，拔脚时吸吮声黏连。远处金属梁骨半淹，像腐烂肋骨露出水面。
苏默伏在铁蒺藜丛后。雨水顺发梢钻进眼角，涩。他用手背蹭眼，左手无名指齿轮戒指冰得刺骨。拇指来回拨那圈齿痕，零件早已无用。内袋掏地图，牛皮透湿，墨团化开。指尖摁在某处，字迹勉强可读。安全屋，东北，直线短。但暴雨抹平地标，每步可能踩空。
身子压得更低，蹭着泥面挪。残骸影子斜拉，枯草被雨打趴。左脚突然陷进暗坑，泥水瞬间没膝，寒意钻骨。他僵住，屏住呼吸。耳里只有雨轰响，心跳捶打胸腔。没其他声音。雨幕厚得吞光，也吞掉视线。情报闪过：齿轮兄弟会最近活跃。他们那身行头，这种天气，反而更招摇。
地图标工棚作避风处。他摸到时，只剩锈架和破板。风斜扯雨泼进，板缝漏得厉害。没法待。挪步继续。约两百米外，一具锅炉残壳，背风侧。底部塌出个凹洞，里面塞干草和破布。他钻进去，蜷起身子。空间窄，膝盖顶着锈铁。
外头雨泼如注，灰雾茫茫。里头，他听见自己喘气声，靴底滴水嗒嗒。背靠冰金属，手按内袋地图，目光穿透雨雾望向东北——旧神殿方向。戒指在指间转，无意识地，金属慢慢温了。
```
