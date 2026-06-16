# Phase 5 PLAN — cost reclaim via narrator cache + world stale-skip

> Phase 4 完整 closure (iter#139-158). Phase 5 目标: 在 Phase 4-E 架构
> 增益基础上, 用 **架构改动 > 配置压缩** 的纪律继续拿 cost,
> 同时验证 Phase 4-E 长程持久性。

## Phase 4 carry-forward (mandatory lessons)

1. **det gate ≠ ship gate**: distinct / drift / cost 都不够测 prose dynamics
2. **配置改动也需 mimo gate**: 任何 budget / threshold 改动 → cross-seed pairwise
3. **单 seed 50% = noise**: 决策必须基于 cross-seed ≥60% decisive
4. **架构改动 > 配置压缩**: Phase 4-E (E) win 是新机制, Phase 4-F (F) revert 是 budget 压。Phase 5 候选优先架构

## 当前 cost 分布 (iter#148 seed3, 50-tick)

| agent | tokens | % | 上次动过 |
| --- | ---: | ---: | --- |
| narrator | 269335 | **51.0%** | iter#5/#9 budget tier (从未做 cache 重排) |
| world_simulator | 155144 | **29.4%** | iter#4 delta output (每 tick 必跑 LLM) |
| showrunner | 55125 | 10.4% | iter#139 sideline (Phase 4-E, 慎动) |
| event_injector | 22744 | 4.3% | iter#10 budget |
| novelty_critic | 7050 | 1.3% | 稳定 |
| narrative_critic | 4949 | 0.9% | iter#157 revert 后已 floor |
| character_agent | <2% / 个 | 总 <10% | Phase 4-E sideline 已省 |

**80% 总成本集中在 narrator + world_simulator.** Phase 5 唯一有 ROI 的方向。

## Phase 5 候选

### 候选 H — Narrator prompt cache 重排 ⭐ Phase 5-A

**Why**:
* narrator 51% 总占比, 单点最大杠杆
* 现状 `_build_system_prompt(style_anchors)` 把 **动态 style_anchors 追加到 SYSTEM 末尾** (narrator_agent.py:497-509), 打破 DeepSeek auto prefix cache
* DeepSeek cache hit rate 价: input miss `$0.07/M` vs hit `$0.014/M` = **5x 折扣**
* SYSTEM_PROMPT 主体 (~3-4 KB 静态文字) 跨 tick 完全一致, 是天然 cache prefix

**Implementation**:
1. `narrator_agent.py:_build_system_prompt`:
   * 删除 style_anchors 追加分支
   * 只返回 `NARRATOR_SYSTEM_PROMPT` (纯 static, 跨 tick bit-identical)
2. `narrator_agent.py:_build_user_prompt`:
   * 接受 `style_anchors` 参数
   * 把 anchor block 拼到 user_prompt 最前面 (动态部分都在 user, 不影响 cache)
3. 调用点 (`narrator_agent.py:346-365`) 把 style_anchors 从 system 改 pass 到 user
4. 加 2 个测试: cache prefix 稳定性 + 内容等价 (LLM 收到的字面信息不变)

**Cost**: 低 (纯 prompt 结构改, ~30 行)
**Risk**: 低 (LLM 输入语义完全等价, 只是结构位置变)
**Quality gate**:
* det gate: 1-seed bench, narrator tokens 应明显降 (期望 -15~25% input cost)
* mimo gate: 单 seed 50-tick pairwise (≥ 45% win)
* 通过 → 3-seed promote 走 Phase 4-E 流程

**预期净收益**: -10~15% 总 cost (取决 cache hit rate)

### 候选 I — World_simulator stale-skip 架构 ⭐ Phase 5-B

**Why**:
* world_simulator 29.4%, 第二大头
* 每 tick 必跑 LLM, 但 **很多 tick 世界真静态** (无场景切换, 无重大事件)
* prompt 已经在 iter#5 delta-output, budget 已紧 — 进一步 **配置压会重蹈 F revert 教训**
* 架构改动: det 层短路 stale tick → skip LLM

**Implementation**:
1. `nf_core/world_stale_detector.py` (新):
   * 输入: 上 tick events + 上 tick world_state + 当前 char_states
   * 触发条件 (全部满足才 skip LLM):
     * 上 tick 所有 events 的 `narrative_value < 5`
     * 上 tick 无 setting_change / location 切换
     * 距上次 LLM world_simulator 调用 < 3 tick (防止漂移累积)
   * 触发时 emit: 1 条 stale 自然事件 + world_state delta = `{}` (零变化)
2. `world_simulator.py:simulate`:
   * 入口先调 stale_detector
   * stale → 返回构造好的 delta, 跳过 LLM
   * 非 stale → 走原 LLM 路径
3. `tick_runtime` 记 stale_skip 计数到 metrics
4. 加 5 个测试 (触发条件 boundary)

**Cost**: 中 (det 层新模块 ~80 行 + 集成 ~30 行)
**Risk**: 中 (有 drift 风险, 必须 strict mimo gate)
**Quality gate**:
* det gate: skip 率应 30-50% (太低无收益, 太高有 drift 嫌疑)
* mimo gate: **mandatory cross-seed ×3** (这是架构改动)
* 长程 stress: 必须 ≥ 100 tick 验证 stale 累积无 drift

**预期净收益**: -15~25% world_simulator cost = -5~8% 总 cost

### 候选 J — Phase 4-E 长程持久性 + memory fidelity probe (combined)

**Why**:
* Phase 4-E LANDED 仅在 50-tick clean A/B 验证
* 200-tick 下 sideline TTL 累积是否仍优? memory_compressor 长程 L3 传说一致性?
* 一次 bench 解决两题, ROI 最高 (省 ~50% bench 成本)

**Implementation**:
1. `scripts/bench_tick.py --long-range` flag:
   * 200 tick, sideline ON vs OFF
   * 跑 3 seed
   * tick 50/100/150/200 各 snapshot
2. `quality_metrics/longrange.py` 新增:
   * memory fidelity probe (L3 传说 vs 实际 tick events)
   * sideline 累积效应 metric (character 池子利用率)
3. judge pairwise on tick 100/150/200 (而非全部, 节省 judge cost)

**Cost**: 高 (~2M tokens × 3 seed = ~6M tokens, ~6-8 hr bench)
**Risk**: 低 (不改代码, 仅验证 + 数据)
**Output**:
* 长程 quality 报告
* decision: 继续 E / 调整 TTL / 给 G 信号
* Phase 5 后期归档

### 候选 K — Pairwise judge 自动化 (infrastructure backlog)

**Why**:
* Phase 4-E 3-seed 手工流程太重 (~半天 / cycle)
* H/I/J 都受益
* 但不直接改 product cost/quality

**Implementation**:
* `scripts/judge_pairwise.py` (已有? 待 audit)
* GitHub Actions or local pre-commit hook
* 3-seed 标准化 (seed1/2/3 = 蒸汽朋克 / 民国 / 末世)

**Cost**: 中 (一次性工具)
**ROI**: 长期。Phase 5-D (sprint 4) 候选, 在 H/I 之后做

## Phase 5 sprint plan (推荐顺序)

```
Phase 5-A: H (narrator cache 重排)      -- 2-3 iter
  ├─ iter A1: code + det bench
  ├─ iter A2: 1-seed mimo gate
  └─ iter A3: 3-seed promote (or revert)

Phase 5-B: I (world stale-skip)         -- 4-6 iter
  ├─ iter B1: stale_detector + tests
  ├─ iter B2: 集成 + det bench
  ├─ iter B3-B5: 3-seed mimo gate (mandatory cross-seed)
  └─ iter B6: ship or revert

Phase 5-C: J (200-tick 长程)            -- 1-2 iter (但 bench 占 6-8 hr)
  ├─ iter C1: 长程 bench infrastructure
  └─ iter C2: 跑 + 报告

Phase 5-D: K (judge 自动化, backlog)    -- 时间允许时
```

## Phase 5 quality gate (mandatory, copy from Phase 4)

每个 candidate 必须:

1. **det gate**: cost/distinct/drift no obvious regression
2. **mimo pairwise gate**: ≥1 seed ≥ 45% win → 进 3-seed
3. **3-seed expand**: plot-light (蒸汽朋克) / medium (民国) / dense (末世) ≥ 60% avg → ship
4. **单 seed 50% borderline = noise**: revert, not promote
5. **一次只动一变量**: 反 iter#128 教训
6. **架构改动优先**: Phase 4-E vs F 教训

## Phase 5 成功标准

| 维度 | 起点 (iter#148) | Phase 5 target |
| --- | --- | --- |
| 总 cost / 50-tick | ~528k tokens | ≤ 450k (-15%) |
| narrator 占比 | 51% | ≤ 45% |
| world_simulator 占比 | 29% | ≤ 24% |
| pairwise mimo (vs current) | baseline | ≥ 45% 跨 3-seed (中性以上) |
| drift | 0 | 0 (保持) |
| 长程 (200-tick) 一致性 | 未测 | 已测, decisive 或 borderline 都给信号 |

## 风险清单

1. **DeepSeek cache 机制实测**: 假设 prefix cache 友好, 但需要实际 bench 验证 hit rate (查 response metadata 中的 `cached_tokens` 字段, 若 SDK 不暴露则按 input cost 反推)
2. **stale-skip drift 累积**: 长程 stress 必须做 (J 顺带验证)
3. **Phase 4-E TTL=10 假设**: 长程下 TTL 是否需要调? 等 J 信号
4. **测试覆盖**: H/I 都需新加 unit test, 不能只信 bench

## Sources

- Phase 4 final: `PHASE4_FINAL.md`
- Phase 4-E landing: `verdict-iter149-phase4e-3seed-final-promote.md`
- Phase 4-F revert lesson: CHANGELOG v2.43 iter#157
- 当前 cost 基线: `bench-iter148-seed3-cast221-sideline-r2.md`
- narrator code: `backend/agents/narrator_agent.py:497-509` (cache-unfriendly point)
- world code: `backend/agents/world_simulator.py:34-77`
