# A1 阈值校准 — Phase 6-C iter#C2

> 池: 2368 narratives 跨 bench novels. 抽样 50 条 (seed=42).

## Headline

| 配置 | avg A1/narr | clean% | 相对 base=3 |
| --- | ---: | ---: | ---: |
| **base=3, no exempt** (script baseline) | 4.58 | 12.0% | — |
| **base=3 + exempt** (production-like) | 2.14 | 22.0% | -53% noise |
| **base=4, no exempt** (+1 阈值, 假设场景) | 2.26 | 32.0% | -51% noise |

> 重要 ▸ 校准脚本的 baseline (no exempt) **过严**: 它把所有 2-gram 都算上, 包括角色/地点名. 生产 ``run_deterministic_checks`` 由 orchestrator 把 ``char.name + location.name`` 作为 ``exempt_words`` 传入. 真实生产噪声接近 **base=3 + exempt** 行.

## Per-bucket

| bucket | n | avg_len | base=3 | base=3+exempt | base=4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| M (501-1500) | 43 | 832 | 5.07 | 2.35 | 2.49 |
| S (≤500) | 7 | 313 | 1.57 | 0.86 | 0.86 |

## Top offenders — base=3 (no exempt)

```
  不是  ×10 narratives
  金属  ×9 narratives
  苏默  ×7 narratives
  苏墨  ×6 narratives
  卷宗  ×3 narratives
  通道  ×3 narratives
  头顶  ×3 narratives
  林雪  ×3 narratives
  方向  ×3 narratives
  档案  ×3 narratives
  照片  ×3 narratives
  格栅  ×2 narratives
  手指  ×2 narratives
  冰面  ×2 narratives
  壮汉  ×2 narratives
```

## Top offenders — base=3 + exempt (production-like)

Should now be free of character / location proper nouns. Anything surviving here is either a TRUE repetition (sthg LLM should fix) or a FALSE positive worth adding to STOP_NOMINALS.

```
  宗筒  ×2 narratives
  料堆  ×1 narratives
  混凝  ×1 narratives
  凝土  ×1 narratives
  结晶  ×1 narratives
  煤气  ×1 narratives
  气灯  ×1 narratives
  钥匙  ×1 narratives
  少年  ×1 narratives
  船夫  ×1 narratives
  木槌  ×1 narratives
  黑渣  ×1 narratives
  碎屑  ×1 narratives
  刻痕  ×1 narratives
  灰钢  ×1 narratives
```

## Sample drill-down (top 10 by base=3 triggers)

| label | len | base=3 | base=3+ex | base=4 | top words (base=3) |
| --- | ---: | ---: | ---: | ---: | --- |
| `…2-longrange-500tick_1781696585/tick_000021.txt` | 1491 | 20 | 11 | 12 | 灰袍×13, 袍人×13, 管道×8 |
| `…2-longrange-500tick_1781696585/tick_000355.txt` | 901 | 14 | 7 | 9 | 石板×8, 字符×7, 表面×7 |
| `…ange-seed2-republic_1781689578/tick_000025.txt` | 1099 | 11 | 9 | 6 | 顾明×9, 明远×9, 老周×6 |
| `…2-longrange-500tick_1781696585/tick_000014.txt` | 1005 | 10 | 3 | 8 | 灰钢×7, 手指×6, 不是×6 |
| `…aseline-seed5-scifi_1781696583/tick_000091.txt` | 1054 | 10 | 3 | 4 | 冰面×7, 苏墨×5, 通道×5 |
| `…2-longrange-500tick_1781696585/tick_000261.txt` | 983 | 9 | 4 | 4 | 苏墨×9, 铁片×8, 镜面×7 |
| `…ter103-seed3-50tick_1781213180/tick_000040.txt` | 881 | 8 | 5 | 4 | 苏默×5, 紫色×5, 冰柱×5 |
| `…stage5-seed3-50tick_1781203198/tick_000032.txt` | 966 | 8 | 2 | 4 | 金属×5, 九娘×5, 通道×5 |
| `…k_archive_noir_cold_1781626894/tick_000003.txt` | 998 | 8 | 3 | 5 | 栈桥×7, 墨青×5, 一下×5 |
| `…ter103-seed3-50tick_1781213180/tick_000016.txt` | 950 | 7 | 3 | 4 | 金属×5, 混凝×5, 凝土×5 |

## Verdict

* **production-like avg = 2.14 A1/narr** — 中等. base=3 raw 噪声 4.58, exempt 后 2.14 (-53%).

* **首选优化方向**: STOP_NOMINALS 而非阈值. 看 production-like top offenders 区分 TP/FP.


## Reproducer

```
python scripts/calibrate_a1.py --sample 50 --seed 42
```


## 不在此刀

* 改 threshold — 本 iter 只校准.

* 改 STOP_NOMINALS — 留 iter#C3 (若 verdict 推荐).

* cross-seed bench — 只有需要动阈值时才上.

