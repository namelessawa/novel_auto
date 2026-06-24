# A1 阈值校准 — Phase 6-C iter#C2

> 池: 2368 narratives 跨 bench novels. 抽样 50 条 (seed=42).

## Headline

| 配置 | avg A1/narr | clean% | 相对 base=3 |
| --- | ---: | ---: | ---: |
| **base=3, no exempt** (script baseline) | 2.98 | 16.0% | — |
| **base=3 + exempt** (production-like) | 1.42 | 40.0% | -52% noise |
| **base=4, no exempt** (+1 阈值, 假设场景) | 1.5 | 38.0% | -50% noise |

> 重要 ▸ 校准脚本的 baseline (no exempt) **过严**: 它把所有 2-gram 都算上, 包括角色/地点名. 生产 ``run_deterministic_checks`` 由 orchestrator 把 ``char.name + location.name`` 作为 ``exempt_words`` 传入. 真实生产噪声接近 **base=3 + exempt** 行.

## Per-bucket

| bucket | n | avg_len | base=3 | base=3+exempt | base=4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| M (501-1500) | 43 | 832 | 3.28 | 1.6 | 1.63 |
| S (≤500) | 7 | 313 | 1.14 | 0.29 | 0.71 |

## Top offenders — base=3 (no exempt)

```
  不是  ×9 narratives
  金属  ×7 narratives
  苏默  ×7 narratives
  苏墨  ×4 narratives
  林雪  ×3 narratives
  照片  ×3 narratives
  格栅  ×2 narratives
  壮汉  ×2 narratives
  裂缝  ×2 narratives
  光束  ×2 narratives
  灰袍人  ×2 narratives
  卷宗筒  ×2 narratives
  头顶  ×2 narratives
  她说  ×2 narratives
  出一  ×2 narratives
```

## Top offenders — base=3 + exempt (production-like)

Should now be free of character / location proper nouns. Anything surviving here is either a TRUE repetition (sthg LLM should fix) or a FALSE positive worth adding to STOP_NOMINALS.

```
  灰袍人  ×2 narratives
  卷宗筒  ×2 narratives
  陈阿福  ×1 narratives
  废料堆  ×1 narratives
  混凝土  ×1 narratives
  煤气灯  ×1 narratives
  留下  ×1 narratives
  灰钢  ×1 narratives
  冰层  ×1 narratives
  紫色光  ×1 narratives
  板房  ×1 narratives
  弄堂  ×1 narratives
  晶体  ×1 narratives
  藤蔓  ×1 narratives
  阿土  ×1 narratives
```

## Sample drill-down (top 10 by base=3 triggers)

| label | len | base=3 | base=3+ex | base=4 | top words (base=3) |
| --- | ---: | ---: | ---: | ---: | --- |
| `…2-longrange-500tick_1781696585/tick_000021.txt` | 1491 | 13 | 9 | 7 | 灰袍人×13, 林雪×8, 她说×7 |
| `…2-longrange-500tick_1781696585/tick_000355.txt` | 901 | 10 | 7 | 7 | 石板×8, 中心×5, 字符×5 |
| `…2-longrange-500tick_1781696585/tick_000014.txt` | 1005 | 7 | 4 | 5 | 手指×6, 不是×6, 留下×6 |
| `…aseline-seed5-scifi_1781696583/tick_000091.txt` | 1054 | 7 | 2 | 2 | 苏墨×5, 频率×5, 管道×4 |
| `…ange-seed2-republic_1781689578/tick_000025.txt` | 1099 | 7 | 6 | 4 | 顾明远×9, 老周×6, 布鞋×5 |
| `…k_archive_noir_cold_1781626894/tick_000003.txt` | 998 | 6 | 2 | 4 | 墨青×5, 栈桥×5, 一下×5 |
| `…ter103-seed3-50tick_1781213180/tick_000040.txt` | 881 | 5 | 2 | 2 | 苏默×5, 记忆×5, 金属×4 |
| `…2-longrange-500tick_1781696585/tick_000261.txt` | 983 | 5 | 3 | 1 | 苏墨×7, 照片×4, 铁片脸×4 |
| `…punk_archive_somber_1781626913/tick_000001.txt` | 834 | 5 | 3 | 3 | 不是×6, 码头×5, 下来×5 |
| `…ter103-seed3-50tick_1781213180/tick_000016.txt` | 950 | 4 | 1 | 3 | 金属×5, 格栅×5, 混凝土×5 |

## Verdict

* **production-like avg = 1.42 A1/narr** — 已经低. iter#7 carry-forward 的 "12+ A1/narr" 已被 iter#4 exempt_words + 助词头/尾改进 + length-aware threshold 联合缓解.

* **不建议动 base threshold** — 当前 4.58 noise 主要来自缺 exempt, 而生产已注入 exempt. 改 threshold 会让真实问题段也漏掉.

* **可选改进 (低风险)**: 看上面 production-like top offenders 表, 若有不算专有名词的反复词 (如 `不是` / `一下`), 可加 STOP_NOMINALS, 进一步降本但不改 threshold.


## Reproducer

```
python scripts/calibrate_a1.py --sample 50 --seed 42
```


## 不在此刀

* 改 threshold — 本 iter 只校准.

* 改 STOP_NOMINALS — 留 iter#C3 (若 verdict 推荐).

* cross-seed bench — 只有需要动阈值时才上.

