# Bench: v1-critic-trim

- novel_id: `bench_v1-critic-trim_1781111365`
- ticks: 3
- bootstrap_sec: 370.58
- tick_durations_sec: [411.8, 361.77, 212.94]
- total_tokens: 120588
- call_count: 22

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 29218 | 24.2% |
| world_simulator | 19837 | 16.5% |
| narrative_critic:critique | 14652 | 12.2% |
| event_injector | 11806 | 9.8% |
| character_agent:char_lintie | 10361 | 8.6% |
| character_agent:char_suxiu | 8547 | 7.1% |
| character_agent:char_zhaotieshan | 7791 | 6.5% |
| character_agent:char_ahuang | 7767 | 6.4% |
| character_agent:char_cenji | 6863 | 5.7% |
| character_agent:char_guweiqian | 3746 | 3.1% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 54064 |
| critical | 66524 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 42900 | 411.8 | 522 | narrator=13545, character_agent:char_lintie=5368, event_injector=4798 |
| 2 | 55029 | 361.77 | 1854 | narrator=9281, world_simulator=7931, event_injector=7008 |
| 3 | 22659 | 212.94 | 840 | world_simulator=7551, narrator=6392, narrative_critic:critique=4725 |

## First narrative sample

```
齿轮停了。

不是某一根、某一组——是核心卷宗存储器里每一座精密时钟同步器，在同一个呼吸的间隙，全部陷入沉默。苏绣手里翻开的卷宗合拢了半页，纸边割过拇指，她没在意。那声"咔哒"太响了，在档案馆的寂静里像骨节断裂。

紧接着是第二声"咔哒"。

存储器第七排底层，一卷新弹出的卷宗正从增殖槽里缓缓滑出，封皮上的字迹尚未完全凝固：疫源追溯。

阿黄比她先到。

他用袖子擦了把掌心的油，嘴里"嘶嘶"抽着冷气，蹲下身先去看底座的联锁机构。手指沾着黑色油污，绕过卷宗边缘，摸索释放杆的位置，目光刻意避开那几个字。"哎呦……"他嘟囔着，声音压得比平时更低，"这动静不对，太不对了。齿轮停摆是常有的，但卷宗自己'咔哒'一声蹦出来……"

他没往下说。头顶的蒸汽管嗤嗤漏气，冰雾从天顶的裂缝渗入，在瓦斯灯光里折射出一层幽蓝。

苏绣绕到他身侧，蹲下。膝盖碰到冰冷的铸铁底座，寒意穿过裙摆。她的指尖先碰封皮——磨损程度极低，几乎没有人翻阅过的痕迹，却被封存在存储器里不知多少年。她把卷宗展开三寸，低头去看。

符号从卷轴表面浮现出来，墨色深得发黑，边缘有一种不自然的扩散，像水渍渗入旧布。她认得这种笔法。不是档案馆标准的复写墨——太新了，新得像昨天才写上去的。
```
