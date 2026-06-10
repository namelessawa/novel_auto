# Bench: v11-injector-trim

- novel_id: `bench_v11-injector-trim_1781125886`
- ticks: 3
- bootstrap_sec: 277.91
- tick_durations_sec: [81.08, 182.01, 95.25]
- total_tokens: 40816
- call_count: 10

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 13189 | 32.3% |
| narrative_critic:critique | 13069 | 32.0% |
| world_simulator | 8519 | 20.9% |
| narrative_critic:revise | 6039 | 14.8% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 8519 |
| critical | 32297 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 10716 | 81.08 | 474 | narrative_critic:critique=4436, narrator=3779, world_simulator=2501 |
| 2 | 18371 | 182.01 | 728 | narrative_critic:revise=6039, narrator=4993, narrative_critic:critique=4147 |
| 3 | 11729 | 95.25 | 542 | narrative_critic:critique=4486, narrator=4417, world_simulator=2826 |

## First narrative sample

```
酸雨打在生锈的黄铜报亭顶棚上，声音密而涩。陈默把帽檐压低，手指摸到外套内袋里硬邦邦的怀表壳。齿轮市的空气裹着铁锈和硫磺的湿气，每吸一口都像在舔舐旧管道。远处的齿轮咬合声沉闷下去，被雨幕捂住了嘴。

他穿过第七区的废弃轨道，鞋底碾过腐蚀的枕木碎屑。雾浓得化不开，只看得见脚下三步锈迹斑斑的铁轨，向黑暗里延伸。风卷过来，带着酸雨的微刺和远处蒸汽汽笛的呜咽，像谁在雾里拖拽生锈的锁链。

怀表在胸口跳了一下。他掏出来，黄铜表壳已被酸蚀出细密的斑点。玻璃表面蒙着水汽，指针在模糊的刻度上爬行。三天。卷宗上烧焦的字迹和林砚空洞的眼神叠在一起，压在齿轮深处。他必须去档案馆，陆铮守着的那些故纸堆里，或许还藏着爆炸前能拧动的阀门。

脚下一滑。他扶住身旁废弃的蒸汽管道，金属冰凉刺骨，掌心传来细微的震颤——不是风，是管道深处残存的压力在嘶鸣。雾气更浓了，前方隐约有建筑的轮廓，像一头蹲伏的巨兽。但另一个方向，隔着雨幕和迷雾，传来规律的、钢铁碾压碎石的闷响。不是齿轮市应有的节奏。

陈默的手指攥紧了怀表。表壳的棱角硌进掌心。他站在轨道中央，雨水顺着帽檐流进衣领。
```
