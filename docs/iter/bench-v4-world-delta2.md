# Bench: v4-world-delta2

- novel_id: `bench_v4-world-delta2_1781118689`
- ticks: 3
- bootstrap_sec: 372.24
- tick_durations_sec: [100.45, 168.29, 101.15]
- total_tokens: 41292
- call_count: 10

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 13833 | 33.5% |
| narrative_critic:critique | 13598 | 32.9% |
| world_simulator | 8149 | 19.7% |
| narrative_critic:rewrite | 5712 | 13.8% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 8149 |
| critical | 33143 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 11654 | 100.45 | 525 | narrator=4712, narrative_critic:critique=4474, world_simulator=2468 |
| 2 | 17350 | 168.29 | 478 | narrative_critic:rewrite=5712, narrative_critic:critique=4433, narrator=4359 |
| 3 | 12288 | 101.15 | 818 | narrator=4762, narrative_critic:critique=4691, world_simulator=2835 |

## First narrative sample

```
雾气从档案馆的通风口涌进来，灰白色的，带着铁锈和湿土的气味。能见度压到十米以内，最远那排书架只剩个轮廓。林雪把提灯挂在肘弯，灯焰在潮湿里跳了跳，投下抖动的影子。她今天的目的是找到“卷宗预言”关于机械丛林的那部分——张野提过，就在这片区域。

脚下的石板地泛着水光，岩壁接缝处渗出细密的水珠，汇成一道，滑进墙角的铜槽。滴答声在雾里闷闷地响，混着头顶蒸汽管道规律的嘶鸣。齿轮机构在墙内转动，声音透过雾气变得迟钝，像沉在水底。她伸手摸过一排档案册的脊背，皮革潮冷，有些已经起了霉斑。

“这里。”她低声自语，指尖停在一本深褐色册子上。标签字迹被水汽晕开，只能勉强辨出“丛林-古代-休眠”的字样。她抽出来，纸张的重量不对，太轻了。翻开，内页被撕去了大半，残留的边角蜷曲发黄。正中央粘着一张铜版拓片，刻着交错的齿轮与藤蔓，藤蔓的纹路里嵌着极小的字，像虫爬的轨迹。

她凑近提灯，拓片边缘的湿气让指尖发滑。远处忽然传来一声金属刮擦——像铁柜门被推开，又很快合上。林雪合上册子，侧耳。雾气吞掉了后续的声响，只有管道嘶嘶，和水滴敲打铜槽的节奏。她把拓片小心夹进内袋，贴着胸口。纸张的凉意透过衣料渗进来。

书架间还是灰白一片，但那刮擦声的方向，隐约有蒸汽溢出的淡光。
```
