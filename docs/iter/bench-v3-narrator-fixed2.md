# Bench: v3-narrator-fixed2

- novel_id: `bench_v3-narrator-fixed2_1781115760`
- ticks: 3
- bootstrap_sec: 395.89
- tick_durations_sec: [223.13, 214.45, 150.31]
- total_tokens: 116482
- call_count: 24

## By agent (cumulative, bootstrap + ticks)

| agent | tokens | % |
| --- | ---: | ---: |
| narrator | 25258 | 21.7% |
| world_simulator | 17738 | 15.2% |
| character_agent:char_lirui | 13479 | 11.6% |
| character_agent:char_liusan | 12453 | 10.7% |
| character_agent:char_zhangwei | 11678 | 10.0% |
| character_agent:char_wangtie | 11343 | 9.7% |
| character_agent:char_chenbo | 10899 | 9.4% |
| character_agent:char_zhaoxue | 4843 | 4.2% |
| narrative_critic:critique | 4677 | 4.0% |
| character_agent:char_linmo | 4114 | 3.5% |

## By priority

| priority | tokens |
| --- | ---: |
| medium | 58055 |
| critical | 58427 |

## Per tick

| tick | tokens | sec | narr_chars | top agents |
| ---: | ---: | ---: | ---: | --- |
| 1 | 34504 | 223.13 | 0 | narrator=8732, world_simulator=5986, character_agent:char_chenbo=4359 |
| 2 | 43947 | 214.45 | 800 | narrator=7963, world_simulator=6204, character_agent:char_lirui=5279 |
| 3 | 38031 | 150.31 | 0 | narrator=8563, world_simulator=5548, character_agent:char_lirui=4759 |

## First narrative sample

```
张卫的机械传感在浓雾中发出低沉的蜂鸣，频率不稳。雨滴从护目镜边缘滑落，模糊了战术显示屏上闪烁的定位光点。边境墙的轮廓若隐若现，像被墨水浸透的旧照片。

光点跳了一下。张卫停下脚步。风裹着雨水灌进领口，金属扣冰凉地贴在锁骨上。异常读数。不是雾气干扰——频率波形太规则，像是某种有目的的信号。他用义肢指尖触碰显示屏，放大标记区域。位置在废弃矿道入口以南两百步，岩壁下方。

走私通道？张卫眯起眼。或者更深处的东西。机械传感再次蜂鸣，这次声音更低，像某种警告。他没动，调整了传感灵敏度，等待下一次读数。

齿轮港的雨小了些。黑市在潮水退去的泥泞中重新立起——木板架在没过脚踝的积水上，摊位像踩高跷的瘦子，摇摇晃晃。鱼腥味混着机油味，蒸汽从破损的管道里钻出来，把叫卖声切成碎片。

刘三缩在油布棚下，帽檐压得很低。他没在看摊位，眼睛跟着人群里一个穿旧军装的男人走。李锐。那家伙手里攥着一叠先知团的传单，纸角被雨水打湿卷起，字迹晕开。李锐爬上一个翻倒的货箱，鞋底踩在浸透的木头上发出闷响。

"潮水退了——可船坞烂了！"李锐举起传单，声音在潮湿的空气里撞出回响，"帝国说这是天灾！卷宗里写得清清楚楚，三十年前就有人预见这一切！他们藏着掖着，怕你们知道真相！"

几个码头工人停下脚步，叉着胳膊听。卖腌鱼的老妇人把一张宣传页塞进她的货箱底下，没抬头。有人在笑，但笑声被蒸汽管道的嘶鸣吞掉一半。

刘三的手指摸进挎包。联络器的旋钮粗糙，冰冷。他拧了一下，又拧了一下。指示灯灭着。他往油布棚里退了半步，躲开李锐扫过来的目光，手指继续拧动旋钮，指甲抠进刻度槽里。

绿灯亮了。微弱，像将死的萤火虫。

信号回来了。

刘三没动。他的眼睛从联络器移向人群，又移向齿轮港的方向——那里，损坏的船坞骨架在雾中露出扭曲的轮廓，像某种巨兽的肋骨。李锐还在喊。传单从他手里飘出去，一张，两张，被风吹进积水里，墨字在水面上慢慢散开。
```
