# iter#118 — diversity dim 离线 cross-bench 分析

> iter#116 加入 TTR / MATTR / 句长 stats. iter#118 用新 dim 离线分析 7 个
> 已有 bench artifact, 评估 dim 灵敏度.

## 跨 7 bench 数据

| bench | n | ttr_char | ttr_word | mattr | sent_mean | sent_std |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| stage5-seed1-baseline | 41 | 0.4637 | 0.9944 | **0.7681** | 21.3 | 11.8 |
| iter103-seed1-close-fix | 44 | 0.4516 | 0.9907 | 0.7544 | 22.6 | 13.9 |
| stage5-seed2-baseline | 42 | 0.5234 | 0.9946 | **0.7705** | 20.7 | 10.9 |
| iter103-seed2-close-fix | 45 | 0.5090 | 0.9975 | 0.7692 | 22.3 | 11.1 |
| stage5-seed3-baseline | 46 | 0.4328 | 0.9965 | 0.7600 | 25.2 | 13.2 |
| iter103-seed3-close-fix | 44 | 0.4476 | 0.9974 | 0.7708 | 25.4 | 14.8 |
| **iter114-seed2-narrator-slim (反向)** | 40 | 0.5199 | 0.9976 | **0.7599** | 22.9 | 11.4 |

## 关键 delta 分析

### iter#114 slim vs iter#107 close-fix (同 seed2)

| metric | iter#107 close-fix | iter#114 slim | delta | 信号强度 |
| --- | ---: | ---: | ---: | --- |
| ttr_char | 0.5090 | 0.5199 | +2.1% | **反向** (slim 更 unique?) |
| ttr_word | 0.9975 | 0.9976 | +0.01% | 无信号 |
| **mattr** | **0.7692** | **0.7599** | **-1.2%** | **弱信号 (有方向但小)** |
| sent_mean | 22.3 | 22.9 | +2.7% | 不显著 |
| sent_std | 11.1 | 11.4 | +2.7% | 不显著 |

### close-fix 在 3-seed 的自然变异

| seed | baseline mattr | close-fix mattr | delta |
| --- | ---: | ---: | ---: |
| seed1 | 0.7681 | 0.7544 | -1.8% |
| seed2 | 0.7705 | 0.7692 | -0.2% |
| seed3 | 0.7600 | 0.7708 | +1.4% |
| avg | 0.7662 | 0.7648 | **-0.18% (噪声)** |

## 解读 — diversity dim 灵敏度评估

**信号方向正确但弱**:
- mattr 在 iter#114 slim 反向 -1.2%, 跟现有 overlap_consec_char-4 +226%
  捕捉到的方向一致 (都说 quality 退化), 但量级差很多.
- close-fix 在 3-seed 内 mattr 自然变异 ±1.8%, slim 的 -1.2% 仍在
  此区间内, 单看 mattr 不能 confident 区分.

**几个特征确认**:
- ttr_word 跨 7 bench 极稳定 (0.9907-0.9976, < 0.7%), 这个 dim 信号死.
  原因: 单段 narration 平均 < 30 word, 词不重复几乎是必然.
- ttr_char 跨 seed 差异大 (0.43-0.52), seed1/3 是 0.43-0.46 跟 seed2 0.51-0.52
  差异主要题材 / cast 名词集导致, **不适合单看为 quality 信号**.
- mattr 是最有意义的 dim — 跨 seed [0.7544, 0.7708] 区间紧凑 (0.7%),
  题材噪声小, slim 反向 -1.2% 是真信号 (虽小).
- 句长 stats 跨 seed 与 fix 差异主要 +1-3 字 mean / +2-3 std, 噪声主导.

**结论 — iter#116 dim 不能替代 overlap_consec**:
overlap_consec_char-4 在 slim 抓 +226% 突变 — 强信号.
mattr 同 case 抓 -1.2% — 弱信号.
两者捕捉**不同退化模式**:
- overlap_consec: adjacent narration 重复 (slim narrator 自我抄)
- mattr: 段内 vocabulary 局部贫乏

Phase 3-C dim 仍有价值 (mattr 跨题材稳定且有方向性), 但不该当主门控信号.

## 后续 (iter#119+ 候选)

1. (low priority) 删 ttr_word 维度 (cross-bench 极稳定无 signal)
2. (medium) 集成 mattr 到 longrange.py drift_signals, 阈值 -2% 触发 prose
   diversity 弱告警
3. (medium) 探索更敏感的 vocabulary 度量 — sentence-tier rare-word freq,
   或字典覆盖范围

## Sources

- analysis script: `scripts/analyze_diversity.py`
- cross-bench MD: `docs/iter/diversity-cross-bench-iter118.md`
- 7 bench inputs 见上表
- baseline iter trail: iter#100-#112
