# Bench: baseline-glm-20260721-republic_spy

- novel_id: `bench_baseline-glm-20260721-republic_spy_1784572705`
- ticks: 3
- bootstrap_sec: 121.86
- tick_durations_sec: [67.08, 0.02, 0.02]
- total_tokens: 15102
- call_count: 5
- narrative_chars_total: 864
- tokens_per_char: 17.48

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrative_state_verifier | 6103 | 40.4% |
| narrator | 4742 | 31.4% |
| narrative_state_repair | 3292 | 21.8% |
| world_simulator | 965 | 6.4% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 965 |
| critical | 14137 |

## Cache hit rate (Phase 5-A)

- total prompt_tokens: 11305
- total cached_tokens: 0
- overall hit rate: 0.0%

| agent | prompt | cached | hit% |
| --- | ---: | ---: | ---: |
| narrative_state_verifier | 4962 | 0 | 0.0% |
| narrator | 3567 | 0 | 0.0% |
| narrative_state_repair | 2157 | 0 | 0.0% |
| world_simulator | 619 | 0 | 0.0% |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 15102 | 67.08 | 864 | narrative_state_verifier=6103, narrator=4742, narrative_state_repair=3292 |
| 2 | 0 | 0.02 | 0 |  |
| 3 | 0 | 0.02 | 0 |  |

## First narrative sample

```
雨丝斜着扎进黄浦江。

周小山蹲在芦苇丛里，左肩抵住渔棚的烂木板。水从棚顶的破洞漏下来，滴在他后颈，顺着脊椎往下淌。他没动。

三米外，潮水正在吞掉最后一片泥滩。芦苇根部的泡沫聚了又散，散开时露出半截麻绳。绳头系在棚柱上，另一头沉在水里。

他盯着那根绳子。

三天前他来的时候，这绳子还没有。渔棚里只有碎报纸和那张刮花照片的通行证。他把通行证揣进怀里，报纸碎片塞进裤袋。走的时候，棚柱上只有锈铁钉。

现在多了一根麻绳。

周小山把重心移到右脚。淤泥吸住鞋底，拔出来时发出闷响。他停住，听。

远处有爆炸声，闷在雨雾里，像隔着棉被敲鼓。闸北方向。水鸟从芦苇丛里蹿出来，翅膀拍打水面，低低掠过江心。

他伸手抓住麻绳，往上提。

绳子很沉。

一节一节往上拉。淤泥从绳股间挤出来，滴在他膝盖上。拉到第三把时，水面破开。

一只铁皮箱。

箱子不大，公文包大小，四角包着铜皮。锁扣上挂着一把铜锁，锁面生满绿锈。他拎起箱子，水从箱底哗哗往下浇。

棚子里有块干木板。他把箱子放上去，蹲下来看那把锁。锁孔里有泥，塞得严严实实。他掏出钥匙串，挑出一根细铁丝，捅进锁孔。

铁丝搅动泥浆。

锁舌弹开。

箱盖掀起来。里面没有水，垫着一层油纸。油纸下面，是一本账簿。

封皮上盖着青帮的印。

他翻开。第一页是码头货单，日期从今年九月开始。每一笔都标注了船名、货品、经手人。他翻到最后一页，停住。

十一月七日。安康丸。货品栏写着：医疗器械。

经手人签名：顾四。

周小山合上账簿。雨声忽然变密，砸在棚顶，像有人往木板上撒豆子。他把账簿塞进怀里，贴着那张通行证。铁皮箱重新锁好，拎到棚外，扔回水里。

泥水溅上他的脸。

他用袖子擦掉，转身往岸上走。芦苇叶子刮过他的肩膀，留下一道湿痕。走到土路时，他回头看了一眼江面。

灰黄色的雾幔把对岸裹得严严实实。

他沿着土路往法租界方向走。雨丝斜打在路边的法桐上，浸透的落叶铺了一地，踩上去软塌塌的，泛出一层油亮的水光。几个行人缩着脖子从他身边跑过，脚步急促而零碎，溅起的泥点打在他的裤腿上。
```
