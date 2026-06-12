# Phase 3 PLAN — 待用户决策

> Phase 2 (iter#76-112) 已完整 closure: deterministic + LLM-judge 双
> 验证, §4 N≥30 × 3-seed promote ×3. iter#113+ 转入 Phase 3.
> Phase 3 方向开放, 此文档列候选 + 估成本/收益让用户回来选.

## 当前状态 snapshot

* tests: 707/707 PASS
* code review cycles: 14 (cycle 1-14 全 HIGH/MEDIUM 修)
* Phase 1 总 cost: -77% tokens / -83% latency
* Phase 2 quality: drift 1→0 (seed3), avg_urg +9.3% avg, pairwise win 73.3%
* git: clean, iter/cost-quality-loop 分支
* 无 background bench 在跑

## Phase 3 候选方向

### 候选 A — narrator prompt 优化 (cost compression)

**Why:** narrator 占 50.5% total tokens (Phase 2 close-fix bench 数据).
最大单 agent 优化面.

**实现 candidates:**
* user_prompt summaries[-5:] 削到 [-3:] (prose_tail 已覆盖最近 ~2000 字符)
* recent_chapter_summaries 长度上限收紧
* render_narrator_discipline_block 进一步紧凑化
* SYSTEM_PROMPT 拆静态/动态以利 DeepSeek auto-cache 命中

**预期收益:** -5% ~ -15% narrator 调用 tokens. 跨 50 tick 节省 ~15-50k tokens.

**风险:** prose quality 可能受影响, 需要 quality bench gate.
跟 Phase 2 流程一致: 每次改动后跑 3-seed pairwise 验证.

**成本估计:** 1-3 iter (code) + 1 iter (bench validation) + 1 iter (3-seed pairwise).
共 ~250k judge tokens.

---

### 候选 B — Cast-confound 控制 (Phase 2 P2 carryover)

**Why:** iter#102 verdict 发现 seed3 cost 2.6x 主要因 bootstrap 生成 3 vs 2 character
(LLM 非确定性). 跨 seed 比较有 cast-size noise.

**实现 candidates:**
* 给 bootstrap 加 `--cast-size N` 强制参数, 让 cross-seed 比较 controlled
* showrunner 主动 cap active cast (推荐 sideline 多余 cast)
* character_agent 拆 active/inactive tier — inactive 不调 LLM

**预期收益:** cross-seed 实验 noise -90%, 是 Phase 3+ 所有 bench 的实验
clean ground. 同时 cast cap 直接减 character_agent 调用.

**风险:** cast cap 太严会限制 narrative 复杂度.

**成本估计:** 2-4 iter (含设计 + 实现 + 验证).

---

### 候选 C — prose diversity dim (Phase 2 §3 carryover)

**Why:** iter#107 matrix 显示 distinct char-2 跨 3 seed 在 [0.855, 0.909]
范围. seed3 最低 (-1.5% vs seed2). 是否高密度题材 prose 在退化, 还是
genre-specific noise — 当前无定量信号.

**实现 candidates:**
* 加 prose distinctiveness dimension 到 quality_metrics
* mimo judge 加 "diversity" rubric 维度 (现是 correctness/coherence/voice)
* longrange analysis 加 prose drift signal (除现有 plot drift)

**预期收益:** 多一维质量监控. 如发现真退化 → 触发针对性修.

**成本估计:** 2 iter (实现) + 1 iter (3-seed validation).

---

### 候选 D — Memory fidelity probe (Stage 3 carryover)

**Why:** iter#86 已 ship MemoryCompressor + L3 传说 reducer + 测试, 但
没集成到 bench. Phase 2 verdict-stage3 列为 "follow-up 候选", 一直没动.

**实现 candidates:**
* bench_tick.py 加 --memory-fidelity flag
* longrange.py 用 MemoryCompressor 输出加 fidelity 度量
* 跨 100/200/500 tick 长程 bench 看 L3 传说一致性是否衰减

**预期收益:** 揭露长程一致性 + 角色记忆漂移, 是迈向 200+ tick 自主连载
的前置 dim.

**成本估计:** 3-5 iter (含 200 tick bench, 单次 ~3-4 hr 各 ~2M tokens).
高成本 high signal.

---

## 推荐排序

按 (实际可执行度) × (Phase 3 上游度) × (cost):

1. **候选 A (narrator prompt)** — 最直接, 跟 Phase 1/2 流程一致, 改动可控
2. **候选 B (cast-confound)** — 上游度高, 为后续所有 Phase 3 实验扫雷
3. **候选 D (memory fidelity)** — 信号最强, 但成本高、bench 耗时长
4. **候选 C (prose diversity)** — 微调度量层, 不开新方向

## Notes for next session

* 全部 4 候选都不互斥 — A+B 是天然组合 (cost + experimental cleanness),
  B+D 是天然组合 (controlled long-range)
* 无候选需要 iter#103 close-fix 之外的 production code 改动撤销
* 707 tests 是 Phase 3 起点 ground truth

## Sources

- Phase 2 final: `verdict-iter112-phase2-close-fix-final.md`
- Phase 2 trail: CHANGELOG v2.39 iter#100-112
- Phase 1 trail: CHANGELOG v2.38 iter#3-72
