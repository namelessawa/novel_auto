# Bench: v7-character-trim

- novel_id: `bench_v7-character-trim_1781121656`
- ticks: 3
- bootstrap_sec: 323.71
- tick_durations_sec: [75.84, 87.98, 112.63]
- total_tokens: 31152
- call_count: 8

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 15759 | 50.6% |
| narrative_critic:critique | 8555 | 27.5% |
| world_simulator | 6838 | 22.0% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 6838 |
| critical | 24314 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 7167 | 75.84 | 0 | narrator=5071, world_simulator=2096 |
| 2 | 11274 | 87.98 | 296 | narrator=5219, narrative_critic:critique=4288, world_simulator=1767 |
| 3 | 12711 | 112.63 | 281 | narrator=5469, narrative_critic:critique=4267, world_simulator=2975 |

## First narrative sample

```
汽笛声又响了，比刚才更哑，拖着断续的尾音沉进雾里。陈守默停在道旁，靴子陷进泥泞。山道被雨水冲出几道深沟，泥浆稠得发亮，裹住脚踝时发出黏腻的声响。他低头看一眼，没拔腿，反而从怀里摸出半截蜡烛，划亮火折子。火苗在雾气中跳了两下，照出前方十来步的路面——那里塌了半边，露出底下生锈的管道，雨水正从裂缝里渗出来，汇成小股泥流冲向山沟。

火光移向左侧。齿轮集市边缘那块金属告示板还在，但刻在上面的线路图已经糊成一片锈红的水渍。雨水顺着板面往下淌，带走最后几道清晰的刻痕，只剩金属接缝处还留着些凹凸的纹路，像被虫子啃过的骨头。他吹熄蜡烛，塞回内袋。火折子的余温还烫着手指。

远处的灯火在雾里洇开，一团
```
