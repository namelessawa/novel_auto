# Phase 4 PLAN (updated iter#149) — E landed, F/G/D pending

> **更新 iter#149**: Phase 4-E (#139-149) 完整 closure, **跨 3-seed pairwise
> 69.3% mimo win, production landed**. F/G/D 仍 pending.

> Phase 3 完整 closure (iter#113-137). 重要教训: iter#128 cast=3 default
> 基于 det 指标改 default, iter#133-135 mimo pairwise 反向 → iter#136
> REVERT. Phase 4 候选必须满足新 quality gate process.

## Phase 4 quality gate process (mandatory)

每个 architecture / config 改动:

1. **det gate**: cost/distinct/drift 维度 (pass = no obvious regression)
2. **mimo pairwise gate**: 跨 ≥ 1 seed pairwise judge (pass = ≥ 45% win)
3. **3-seed expand**: 跨 plot-light / plot-medium / plot-dense seed 验证

iter#128 漏 mimo gate 直接改 default → iter#136 revert. 不再重蹈.

## Phase 4 候选方向 (按优先级)

### 候选 D — memory fidelity probe (Phase 3 carryover)

**Why**: Phase 2 §6 listed; 200 tick 长程一致性是 production 高价值维度.

**Implementation**:
* `scripts/bench_tick.py --memory-fidelity` flag
* 跨 tick 50/100/150/200 跑 L3 传说 reducer (MemoryCompressor 已 ship)
* `quality_metrics/longrange.MemoryProbe` 集成
* 单 seed 200 tick bench ≈ 3-4 hr / ~2M tokens

**Cost**: 高 (但一次性, 信号强)
**Quality gate**: pairwise 200 tick narrative 内一致性可量化

### 候选 E — Showrunner runtime active-cast cap (Phase 3-B 延伸) — ✅ **LANDED iter#149**

**实施 + 验证完成**:
* iter#139: infrastructure (ShowrunnerOutput.sidelined_characters,
  TickState API, orchestrator wire, 16 tests)
* iter#141: SYSTEM_PROMPT 强制阈值触发 (≥ 4 chars 必须 sideline 1)
* iter#143: 首次 positive (66.67% mimo win, confounded)
* iter#145: clean A/B seed1 80% win, cost -2.9%
* iter#147: cross-genre seed2 50% tied
* iter#149: cross-genre seed3 77.78% win → **3-seed avg 69.3% promote**

**Net result**: Phase 4-E **default ON**, cost 中性 (+1.2% avg), quality
+38.6pp mimo pairwise. drift 0 跨 3 seed. **No opt-in flag** (跨题材 decisive).

**Key insight**: 与 iter#133-135 静态 cast=3 反例对比, **关键不是 "少 char",
而是 "灵活调度"**. 动态 sideline 让 character 池子保留 + Showrunner 选择性
退场, 静态 cast=3 character interaction 永远缺.

### 候选 F — Critic prompt cache / max_tokens 进一步压

**Why**: Phase 1 iter#12 把 critic budget 砍到 1500/4096. 但 cumul 仍是
narrator 后的 #2 token spender. 进一步 prompt cache (DeepSeek auto-cache
stable prefix) 可能 -10% cost.

**Implementation**:
* `backend/agents/narrative_critic.py` SYSTEM_PROMPT 拆静态 / 动态
* 静态部分大块前 (LLM cache 友好)
* 动态部分 (tick context) 后

**Cost**: 低 (prompt 改). Quality gate 必须 (critic 影响 narrator critique).

### 候选 G — Memory compressor budget 进一步压

**Why**: MemoryCompressor 每 50 tick 跑一次, 但 budget 较宽. iter#7-12
当年压过 cost, 现在跨 200 tick bench 也许还有空间.

**Implementation**:
* 测当前 compressor token spend
* 如 > 10% 总 budget, 改 prompt 紧凑化
* Quality gate: 200 tick fidelity probe pairwise (与 D 重合)

**Cost**: 中. 与 D 天然组合.

## 推荐排序 (updated iter#149)

按 (信号强度) × (实现成本) × (Phase 4 上游度):

1. ~~E (runtime sideline)~~ — **LANDED iter#149, 69.3% mimo win, cost 中性**
2. **F (critic prompt cache)** — 低成本 next 候选, DeepSeek auto-cache
3. **G (compressor budget)** — 与 D 组合, 探 prompt slim
4. **D (memory fidelity probe)** — 长程一致性, 200-tick bench 高成本

## Phase 3 完整 status (iter#113-137)

| 候选 | 状态 | 净结果 |
| --- | --- | --- |
| A) narrator slim | 失败 revert (#114-115) | 教训: prose_tail ≠ summaries |
| **B) cast-confound** | **CLI 保留 opt-in, default revert (#119-136)** | 教训: det 不够测 prose dynamics |
| C) prose diversity dim | 弱信号 (#116-118) | 工具沉淀 |
| D) memory fidelity | 未启动 | 留 Phase 4 候选 D |

## Phase 1/2/3 累积净改动 (revised iter#136)

| Phase | 净 production 改动 |
| --- | --- |
| Phase 1 | -77% tokens (代码 + prompt 压缩, 验证充分) |
| Phase 2 | close-loop fix (#103) + add_open_loop dedup (#108), 73% pairwise promote |
| Phase 3-B | --cast-{a,b,c}-count CLI (opt-in), all-or-nothing 校验, compliance warning |
| Phase 3 总 | 工具沉淀, default behavior 不变 |

## Notes for next session

* Phase 1 + 2 是核心 production gain
* Phase 3 是工具与教训沉淀, default 净 0
* Phase 4 应**先 mimo pairwise gate 设计** 再实施
* 不可重复 iter#128 "det-only validation" 错误

## Sources

- Phase 3 revert: `verdict-iter136-revert-iter128-pairwise-evidence.md`
- Phase 3 final (revised): `PHASE3_FINAL.md`
- Phase 2 final: `verdict-iter112-phase2-close-fix-final.md`
- Phase 1 trail: CHANGELOG v2.38
- iter#133-135 pairwise: `verdict-iter{133,134,135}-*.{json,md}`
