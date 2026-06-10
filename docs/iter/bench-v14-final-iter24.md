# Bench: v14-final-iter24

- novel_id: `bench_v14-final-iter24_1781131585`
- ticks: 3
- bootstrap_sec: 294.06
- tick_durations_sec: [144.24, 92.35, 78.22]
- total_tokens: 31926
- call_count: 10

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 11438 | 35.8% |
| narrative_critic:rewrite | 8488 | 26.6% |
| world_simulator | 6635 | 20.8% |
| narrative_critic:revise | 5365 | 16.8% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 6635 |
| critical | 25291 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 13672 | 144.24 | 434 | narrative_critic:revise=5365, narrator=3676, narrative_critic:rewrite=2876 |
| 2 | 9705 | 92.35 | 172 | narrator=3872, world_simulator=3001, narrative_critic:rewrite=2832 |
| 3 | 8549 | 78.22 | 288 | narrator=3890, narrative_critic:rewrite=2780, world_simulator=1879 |

## First narrative sample

```
雨滴砸在铜檐上，声音沉闷。林雪关上铁木窗栓，指尖沾满湿冷的铁锈粉，粗糙感扎着皮肤。档案馆里更静，蒸汽管道偶尔嘶鸣，深处传来金属摩擦，整座建筑仿佛在喘息。空气粘稠，吸进肺里沉重。她摸向工作台，铜制台灯投下昏黄光，照亮羊皮卷宗。纸张边缘潮软，微微卷曲。她的工作是整理：软刷扫去积灰，手指熟练动作，但不用盯视。目光偶尔飘向窗外灰雾，那里滴水声更多，锈蚀悄发生。台灯边缘，一份卷宗封皮泛着不自然的光，水渍般微亮。她停顿，将软刷轻放木托盘。指尖碰卷宗，触感更凉更润，像摸到冰露。小心翻开，内部是蒸汽管道记录，字迹枯燥。翻到中间空白处，多出几行字，纤细如针尖蘸淡铁水写。角度倾斜时才显。她认得这笔迹。是自己的。一串日期，从明天起连续七天，后跟地点：第七档案库外回廊、第二蒸汽阀门室、中央塔底层……最后指向废弃神殿遗址。末行字迹凌乱：‘他们在听。别出声。’手指按纸页，指节发白。窗外雨声忽大，冲刷屋顶，管道嘶鸣尖锐。她合上纸页，纸张摩擦声极轻。卷宗从手中滑落，砸在地板上，溅起细尘。
```
