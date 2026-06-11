# Bench: stage1-v16-15tick

- novel_id: `bench_stage1-v16-15tick_1781147938`
- ticks: 15
- bootstrap_sec: 458.72
- tick_durations_sec: [147.27, 139.52, 180.46, 145.82, 287.17, 131.67, 116.95, 195.3, 139.3, 492.01, 167.38, 143.18, 104.64, 115.03, 151.44]
- total_tokens: 149839
- call_count: 35
- narrative_chars_total: 10284
- tokens_per_char: 14.57

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 81498 | 54.4% |
| world_simulator | 45500 | 30.4% |
| showrunner | 13136 | 8.8% |
| event_injector | 5561 | 3.7% |
| character_agent:char_heisha | 4144 | 2.8% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 68341 |
| critical | 81498 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 7672 | 147.27 | 0 | narrator=4926, world_simulator=2746 |
| 2 | 7016 | 139.52 | 567 | narrator=4527, world_simulator=2489 |
| 3 | 8787 | 180.46 | 817 | narrator=4909, world_simulator=3878 |
| 4 | 7847 | 145.82 | 948 | narrator=4917, world_simulator=2930 |
| 5 | 13627 | 287.17 | 0 | narrator=5683, showrunner=4301, world_simulator=3643 |
| 6 | 7679 | 131.67 | 745 | narrator=5119, world_simulator=2560 |
| 7 | 7761 | 116.95 | 614 | narrator=5092, world_simulator=2669 |
| 8 | 9748 | 195.3 | 814 | narrator=5536, world_simulator=4212 |
| 9 | 7586 | 139.3 | 821 | narrator=5777, world_simulator=1809 |
| 10 | 25121 | 492.01 | 0 | narrator=7759, event_injector=5561, showrunner=4582 |
| 11 | 9597 | 167.38 | 876 | narrator=5842, world_simulator=3755 |
| 12 | 8853 | 143.18 | 926 | narrator=5419, world_simulator=3434 |
| 13 | 7633 | 104.64 | 897 | narrator=5133, world_simulator=2500 |
| 14 | 8650 | 115.03 | 1219 | narrator=5722, world_simulator=2928 |
| 15 | 12262 | 151.44 | 1040 | narrator=5137, showrunner=4253, world_simulator=2872 |

## First narrative sample

```
雾散了一半，港口方向的吊臂终于能看清轮廓，锈铁城的脊线在铅灰色天空下露出牙齿。苏墨把油布裹紧，从屋檐下迈出来。积水没过脚踝，每一步都踩出铁锈色的涟漪。

排水沟早就满了。浑水沿着街面朝低处涌，灌进半掩的铺门里。一间五金铺的老板蹲在门槛上拿木板挡水，嘴里骂着什么，雨水从他帽檐淌下来，打在膝盖上的毛巾印出深色斑点。苏墨从他身边经过时低头看了一眼——街面的积水是红褐色的，不是泥，是铁。整条路的铆钉和接缝都在往外渗锈水，像这座城市在流一种很慢的血。

她走到十字路口停下来。一辆废弃的蒸汽拖车横在路中央，半个轮子陷在路面塌陷的坑里，车身上所有的铁件都起了泡。酸雨打在它的锅炉外壳上，发出细密的嘶嘶声。苏墨盯着那些铁锈泡看了两秒——它们在肉眼可见地胀大，像什么东西正从金属内部往外顶。

远处钟塔的影子从雾尾里浮现出来。铜皮表面已经花得不成样子，绿锈一道道挂下来，像垂死的藤蔓。她想起昨晚在祭坛石板上用指甲描下来的那几个符号——不是任何她见过的文字，但她的小指划过刻痕时，手腕里的骨头跟着嗡了一下。纸条叠在内袋里，贴着肋骨，湿气还没渗进去。

风向变了，带着一股铜腥味从港口涌上来。她抬起下巴，看见钟塔顶部的蒸汽阀门在雨里喷出一团白雾，阀门的节拍比昨天快了半拍。

她把油布的边角塞得更紧，朝街的另一头走去。积水在她身后合拢，没有留下脚印。
```
