# Bench: phase5a-cache-vis-pilot

- novel_id: `bench_phase5a-cache-vis-pilot_1781583227`
- ticks: 5
- bootstrap_sec: 377.3
- tick_durations_sec: [69.96, 52.71, 59.42, 58.02, 123.33]
- total_tokens: 39143
- call_count: 11
- narrative_chars_total: 3272
- tokens_per_char: 11.96

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 22427 | 57.3% |
| world_simulator | 11551 | 29.5% |
| showrunner | 5165 | 13.2% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 16716 |
| critical | 22427 |

## Cache hit rate (Phase 5-A)

- total prompt_tokens: 22036
- total cached_tokens: 10240
- overall hit rate: 46.5%

| agent | prompt | cached | hit% |
| --- | ---: | ---: | ---: |
| narrator | 16205 | 9216 | 56.9% |
| world_simulator | 3738 | 0 | 0.0% |
| showrunner | 2093 | 1024 | 48.9% |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 6354 | 69.96 | 480 | narrator=3794, world_simulator=2560 |
| 2 | 6235 | 52.71 | 608 | narrator=4432, world_simulator=1803 |
| 3 | 7129 | 59.42 | 720 | narrator=4443, world_simulator=2686 |
| 4 | 6864 | 58.02 | 665 | narrator=4980, world_simulator=1884 |
| 5 | 12561 | 123.33 | 799 | showrunner=5165, narrator=4778, world_simulator=2618 |

## First narrative sample

```
码头上没有人。雨砸在木板上，溅起浑浊的泥点，和蒸汽管口泄露的白汽搅在一起，呛得人喉头发紧。陆沉把油布外套的领子又拽高了些，湿透的布料黏在脖颈后。他得穿过这片泥泞，去东区的旧仓库。

脚下打滑，他扶住一排竖在岸边的货箱。箱子上糊着的标签早已被雨水泡烂，只剩下几片纸角在风里哆嗦。远处，黑乎乎的船影在浪里剧烈地摇晃，缆绳绷得发出呻吟。更远的地方，城市轮廓被雨和蒸汽切割得支离破碎，只有零星几扇窗户透出昏黄的光，像漂浮的病眼。

他抹了把脸，雨水混着汗水，冰凉一片。街角那块褪色的告示栏前，不知何时多了块崭新的木板，白底黑字扎眼——蒸汽纪元展览会，盛大开幕。雨顺着光滑的板面流下来，字迹模糊扭曲，仿佛正在融化。

一声汽笛穿透雨幕，悠长，沉闷，从城市腹地传来。陆沉停下动作，侧耳。不是码头的吊装机，是更远处，铁轨的方向。他盯着雨水在告示牌边缘汇成细流，滴落，砸进脚边的泥坑。该动了。他挪动脚步，靴子从泥里拔出，发出令人牙酸的咕唧声。

又一声汽笛，比刚才近，也更尖锐。这次他听清了，是往北去的列车。北区，断裂峡谷的方向。他加快了步子，油布衣摆拍打着小腿，沉重而潮湿。
```
