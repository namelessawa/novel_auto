# Phase 6 PLAN — quality + 长程持久性 + 产品价值兑现 (草稿)

> 2026-06-17 draft. 待用户 confirm 方向后细化。
> 状态: **proposal**, 不是 commitment.

## Phase 1-5 复盘 (Phase 6 起点)

| Phase | 主线 | cost 增益 | quality 增益 | 结论 |
| --- | --- | --- | --- | --- |
| 1 (#3-72) | cost 优化主线 | **-77% tokens** | 持平 | 饱和 |
| 2 (#76-112) | quality-first loop + critic gating | -22% | +73.3% pairwise | LANDED |
| 3-B (#119-136) | cast confound (CLI opt-in) | 0 | +73% mimo (单 seed) | CLI 收档 |
| 4-E (#139-151) | sideline default ON | 0 | **+38.6pp mimo cross-seed** | LANDED |
| 5-A (#197) | narrator prompt cache 重排 | input -45.5% (ARK 端可观测前) | 持平 | LANDED |
| 5-B (#198) | world_simulator stale-skip 架构 | 总 cost -54% (5-tick) → 200-tick 持平 | 不 drift | LANDED |
| 5-C/D/E | 21 主题 × 16 风格 preset | 0 | 173/208 ≥ 4.0 | LANDED |
| 5-D follow-up | UI 推荐配对 + 3-seed gate | 0 | 3-seed cross-theme PASS | LANDED |

**当前 cost baseline** (seed1 200-tick 长程):

| agent | tokens | % | 状态 |
| --- | ---: | ---: | --- |
| narrator | 429,286 | **40.4%** | Phase 5-A 已重排, ARK metadata 暂不可观测 |
| showrunner | 155,207 | **14.6%** | Phase 4-E sideline 已榨干 |
| world_simulator | 131,970 | 12.4% | Phase 5-B stale-skip 已 47% 跳过 |
| event_injector | 73,577 | 6.9% | iter#10 budget 已紧 |
| character_agent×N | ~178k | 16.8% | 6 角色场景下 batch_decide 并发 |
| character_arc_tracker | 42,795 | 4.0% | v2.18 arc 追踪 |
| novelty_critic / memory_compressor / 其他 | ~50k | <5% | 都已 iter#15-30 调过 |

**Cost 压缩 ROI 已到边际**:
- narrator 是最大头但已 Phase 5-A 重排, 进一步压会动 quality
- showrunner / world_simulator 在 Phase 4/5 已经动过, 再压有 revert 风险
- 余下小项 (event_injector / novelty_critic / arc_tracker) 单项 < 10% 总, 优化空间 < 5%

**Phase 6 不应继续以 cost 为主线**. 已经触底.

## Phase 6 候选方向

### 候选 A — quality 完整 det 层 (B-G 维度) ⭐

**Why**:
- `docs/design/novel_quality_critique_and_iteration.md` 定义 A-G 7 维 rubric
- 现状 `quality_metrics/` 只覆盖 repetition (A) / consistency / compliance
- B 角色失真 / C 情节 / D 描写 / E 语言 / F 结构 / G AI 模式 大部分靠 LLM critic 做
- LLM critic 每 tick ~10k tokens, 全靠 critic 兜底 cost 高 + 假阴/假阳率
- det 层补全 → critic 只做语义类, LLM 调用频次 ↓, 触发精度 ↑

**Scope**:
- D4/D6/D2 — 中文 NLP 描写检测 (动词/形容词比例, 抽象 vs 具象 metric)
- E1/E2/E7 — 句长方差 + 翻译腔 pattern + 对仗句式
- B4 — 内心独白字数 / 行动+对话字数 ratio
- G3/G4/G5 — 旁白解释密度 + 末尾升华 + 留白行数
- 与 narrative_critic 集成: det 触发 → 优先 REVISE, 减少 LLM 调用

**Cost**: 高 (4-6 周, 6-8 模块 + 30-50 新 test)
**Risk**: 中 (中文 NLP 评判难做 ground truth, 容易过/欠 trigger)
**Quality gate**: cross-seed pairwise (3-seed ≥ 60% PASS) + 触发率精度抽样 (≥ 80% 命中 design rubric)
**ROI**: 高 (cost ↓ + quality ↑ 双向)

### 候选 B — 长程小说 reader + 弧线 UI

**Why**:
- 已有 character_arc_tracker (v2.18) 全程记录弧线但前端无展示
- 已有 multimedia (v2.33 TTS + 图 + 视频) 但单 section 不连贯
- 用户看的是连续小说, 当前 UI 只暴露 tick 控制台 + 单 narrative 调试视图
- 200-tick 长程已确认稳定, 但 reader 体验不到

**Scope**:
- 长程小说阅读视图 (按 tick 串 narrative, 支持滚动 / 时间轴 / 视点切换)
- 角色弧线时间轴 (character_arc_tracker 数据 → 时间线 UI)
- 开放伏笔与回收追踪 (open_loops + closed_loops UI)
- 推荐: 把 multimedia 接入 reader (段落 → 图 + TTS, 用户选)

**Cost**: 中 (2-3 周, 主要前端)
**Risk**: 低 (UI 工作, 后端数据已就绪)
**Quality gate**: UI 自动 e2e (playwright) 覆盖 3 个核心流程
**ROI**: 高 (产品价值兑现, 用户首次能"读"自动生成的小说)

### 候选 C — 500/1000 tick 超长程持久性

**Why**:
- 现已 PASS: 200 tick (seed1) + 100 tick × 3 seed (Phase 5-D follow-up)
- 真小说级别 ≥ 500 tick (~50 章 × ~10 tick/章)
- memory_compressor L0→L1→L2 长程 L3 传说一致性未验证
- summary_tree 查询命中率长程未跟踪
- 风险: stale-skip + sideline 累积超 200 tick 有未知 drift

**Scope**:
- 单 seed 500 tick stress (~10h bench, ~5M tokens)
- 单 seed 1000 tick stress (~20h bench, ~10M tokens, 可选)
- 长程 memory fidelity probe (L3 传说 vs 实际事件抽样校验)
- 长程 reader-perceptible 质量评估 (取每 100 tick 头尾段 pairwise)

**Cost**: 低 (1 周 bench + 分析, 不动代码)
**Risk**: 低 (验证型工作)
**Quality gate**: 500 tick 完成率 100% + 长程 pairwise vs 短程 baseline ≥ 50% (中性以上)
**ROI**: 中 (验证产品长篇能力, 给后续 phase 信号)

### 候选 D — 多 POV 切换 + 弧线驱动叙事

**Why**:
- 当前 narrator 每 tick 选一个 viewpoint_character, 全程单视点单线
- 真小说常 multi-POV (主线 A + 主线 B + 主线 C 交错)
- character_arc_tracker 已有数据但 narrator 不主动用
- Showrunner 已有"cold_thread 提示" 但仅暗示, 没机制切 POV

**Scope**:
- Showrunner 加 POV 切换决策 (基于 arc heat / loop urgency)
- narrator 加跨 tick POV 连续性约束 (避免 E3 violation)
- TickState 加 active_pov + last_pov_switch_tick 字段
- pairwise gate: 单 POV vs 多 POV 模式 cross-seed ≥ 60%

**Cost**: 高 (3-4 周, 架构改动)
**Risk**: **高** (E3 POV 切换违例风险, Phase 4-E 教训"架构改动 mandatory cross-seed")
**Quality gate**: 3-seed pairwise + 200-tick 长程
**ROI**: 高但风险高 (突破单视点天花板, 但可能引入 confusion)

### 候选 E — 多模态接入完善 (v2.33 → v2.45)

**Why**:
- v2.33 引入分段 + 图 + TTS + 视频 (`backend/api/multimodal_routes.py`)
- 当前: 单 section 一次性产, 没接入 reader / 没批量化
- 长程小说自动产 TTS 全集 + 章节图 + 关键场景视频

**Scope**:
- 长程 batch_multimodal: per 100 tick → 1 章节图 + 完整 TTS + 关键场景视频
- 资产 manifest 接入 reader UI (候选 B 联动)
- 视频 ffmpeg 性能优化 (现 imageio-ffmpeg + libx264, 600 帧 ~10s)

**Cost**: 中 (2 周)
**Risk**: 低 (现有路径扩展)
**Quality gate**: e2e: 100 tick → 完整 multimedia 包 (TTS 长度 / 图清晰度 / 视频时长)
**ROI**: 中 (产品深化但不破天花板)

## 推荐 sprint plan

```
Phase 6-A: C (500-tick 长程)         -- 1 周 (低成本验证)
   ↓ 如果长程 PASS
Phase 6-B: B (reader UI)             -- 2-3 周 (产品价值)
   ↓ 用户实际看到自动小说后
Phase 6-C: A (B-G det 层)            -- 4-6 周 (quality 深化)
   ↓ optional
Phase 6-D: D (多 POV) 或 E (多模态)   -- 等用户信号
```

**串行而非并行** — 每个阶段产 verdict + cross-seed gate, 不重复 Phase 4-F
budget 教训 (一次改一变量).

## Phase 6 quality gate (沿用 Phase 5)

每个 candidate 必须:

1. **det gate**: cost/distinct/drift 无明显回归
2. **mimo pairwise gate**: ≥ 1 seed ≥ 45% win → 进 3-seed
3. **3-seed expand**: steampunk / republic / apocalypse ≥ 60% avg → ship
4. 单 seed 50% borderline = noise: revert, not promote
5. 一次只动一变量 (反 iter#128 教训)
6. 架构改动 > 配置压缩 (Phase 4-E vs F 教训)

## Phase 6 不做 (intentional)

- ❌ 继续以 cost 为主线 — 已饱和, 边际 ROI < 5%
- ❌ 重新引入章节式生成 — 已归档 (`old/core/`)
- ❌ 切回 mimo 为生成模型 — 已 ARK 跨家族判断
- ❌ 提前实现 narrator critic LLM 多轮 self-revise — 已 v2.38 iter#33 max_total_rounds=1 定档

## 风险清单

1. **ARK 配额 / TPM cap**: Phase 6-C 500 tick × seed3 需 ~5M tokens
2. **judge endpoint 跨家族对齐**: glm-5.1 在 D/E 维度精度待 calibrate
3. **测试基础设施衰减**: 长程 bench 跑完后 unit test 仍 30s 内, 但 e2e 没有 — 候选 B 加 playwright e2e 后会有维护成本
4. **product value vs eng work**: 候选 A 工作量最大但用户体验改善间接; 候选 B 工作量中但用户首次能"读"

## 决策点 (待用户 confirm)

1. **方向**: 优先 quality (A) 还是产品 (B) 还是先验证长程 (C)?
2. **节奏**: 每个 sprint 2 周 ship 还是 4 周 ship?
3. **判官**: 继续 glm-5.1 / 切回 mimo / 双判官 ensemble?
4. **bench seed 集**: 维持 steampunk/republic/apocalypse 还是扩到 5 个 (加 xianxia + scifi)?

## Sources

- 数据基线: `docs/iter/bench-phase5j-longrange-200tick.json`, `verdict-phase5j-3seed-longrange.md`
- 教训: `PHASE4_FINAL.md`, `PHASE5_FINAL.md`
- 设计 rubric: `docs/design/novel_quality_critique_and_iteration.md`
- 工具栈: `PAIRWISE_JUDGE_RUNBOOK.md`, `RECOMMENDED_PAIRS.md`
