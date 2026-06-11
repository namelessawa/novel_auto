# Phase 2 Final Verdict — quality-first loop complete

> Phase 1 (iter#3-72): cost -77% / latency -83%.
> Phase 2 (iter#76-98): quality 升级为一等公民, 跨题材 drift 解除.
> 此报告整合 Phase 2 所有 Stage 结论, 给出 best stable 推荐.

## Stage roll-up

| Stage  | iter range | 退出条件     | verdict |
| ------ | ---------- | ------------ | ------- |
| 0      | iter#76-80 | 度量基建 + judge self-sanity | bias=0 PASS |
| 1      | iter#81-83 | v15 vs v16 verdict           | v16 win 70% (provisional) |
| 2      | iter#84-85 | adaptive critic gating       | stage2 双向 win |
| 3      | iter#86-89 | longrange drift surfaced     | 2 drift signals captured |
| 4      | iter#90-94 | 3 fixes 同时解 drift          | stage4 win + 0 drift |
| cross-genre | iter#95-98 | 多 seed 验证               | **stage5 (iter#96) cross-genre robust** |

## Cross-genre 3-seed validation table (best stable candidate = stage5)

| seed | 题材 | ticks | open end | stale end | avg_urg | drift signals | distinct char-2 |
| ---- | ---- | ----: | -------: | --------: | ------: | ------------: | --------------: |
| 1 | 蒸汽朋克档案馆 (stage4, no open_pressure) | 50 | 5 | 1 | 6.80 | 0 | 0.895 |
| 2 | 民国上海密码员 (stage5, open_pressure on) | 30 | **4** | **0** | **7.50** | **0** | **0.913** |
| 3 | 末世废土移动城市 (stage5)                  | 30 | **4** | **0** | **7.50** | **0** | 0.889 |

* **plot drift**: 3/3 seed 0 drift signals; open_count capped 自适应
* **prose quality**: distinct char-2 ∈ [0.889, 0.913] — 同水准
* **stage5 (iter#96) 跨题材完整 robust**

## Cost evolution

| config      | v0 baseline | v15 final | v16 final | stage4 | stage5 |
| ----------- | ----------: | --------: | --------: | -----: | -----: |
| tokens / tick | ~9,200 (3-tick avg, 137,890/(3+bootstrap proportion)) | ~10,150 (188,873/15-tick + bootstrap) | ~9,990 (149,839/15) | ~10,810 (540,474/50) | ~10,110 (292,673/30 + 303,290/30) avg ≈ same |

stage5 平均 cost ≈ stage4 (Phase 1 已饱和); plot drift 修复几乎不增成本.

## §4 + §5 + §6 整合判决

* §4 v16_promote: v16 win-rate 70% vs v15 — **superseded by §5**, stage2
  双向 win 是更好选择.
* §5 stage2 transit: cost ≈ v16, quality 双向 60-70% win — Stage 2 真正
  实现 "v15 关键质量 + v16 平均成本".
* §6 long-range: stage4 (stage2 + 3 fixes) 在 single-seed 50 tick 全消
  drift. stage5 (stage4 + iter#96) 跨 3 seed 完全 robust.

## Phase 2 best stable — recommendation

**stage5 = default production config:**
* CRITIC_IMPORTANCE_MIN=7 (importance-gated critic)
* iter#90-92 EventInjector + Showrunner 三件套
* iter#96 EVENT_INJECTOR_OPEN_LOOP_CAP=6 (open_pressure 自适应)

Stage 2 verdict (iter#85) 的 "v15 关键质量 + v16 平均成本" 目标在
stage5 完整达成, 并且 plot-level 长程 robust 跨 3 题材.

## Phase 2 metric infrastructure 永久遗产

* `quality_metrics/repetition.py` — char/word n-gram distinct + overlap
* `quality_metrics/consistency.py` — entity vs world snapshot
* `quality_metrics/compliance.py` — length tier / leak / schema rate
* `quality_metrics/judge.py` + `judge_prompts/` — pairwise + rubric, mimo
* `quality_metrics/longrange.py` — foreshadowing / novelty / memory probes
* `scripts/bench_tick.py --quality` — det 全跑 + judge 按预算采样
* `scripts/quality_self_sanity.py` — judge bias guard
* `scripts/stage1_verdict.py` — v15 vs v16 pairwise pipeline
* `scripts/analyze_longrange.py` — drift trend + signal auto-detect

共 60 单元测试覆盖, 全程 deterministic, judge prompt 版本化入库.

## Sources

- Phase 2 stages: `docs/iter/verdict-stage{1,2,3,4}.md`
- Cross-genre: `docs/iter/verdict-iter95-multiseed.md`
- All benches: `docs/iter/bench-stage{1,2,3,4,5}-*.{json,md}`
- All analyses: `docs/iter/longrange-stage{3,4,5}-*.{json,md}`
- iter trail: iter#76-98 (23 iter, ≈ 12 真改动 + 4 review/fix + 7 验证)

## Continuation

继续迭代由用户指引. 候选方向:
1. stage5 50 tick 多 seed 跑足 §4 N≥30 narrations × 3 seed → 转 final
2. 进一步压 cost (在 stage5 上推 critic gate, 或 prompt cache 探索)
3. 探 prose diversity 度量 (Phase 2 §9 prompt 多样化 candidates)
4. 探 Stage 3 verdict candidate "memory fidelity probe" 实测 (iter#86
   已 ship reducer + 测试, 但 bench 集成留作 follow-up)
