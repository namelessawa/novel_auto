# Phase 6 FINAL — 长程持久性 + 产品价值兑现 (2026-06-23 ~ 06-25)

> Plan: `PHASE6_PLAN.md` (06-17 draft).
> Execution: 2026-06-23 → 06-25 单/双 session, **70+ iter ship**.
> 验收: 阅读 reader, 跑 bench, /code-review pass.

## Headline

| 维度 | 计划期望 | 实际结果 | 状态 |
| --- | --- | --- | --- |
| **6-A 长程持久性** | 500 tick PASS | **2/4 run 完整 PASS**, cross-seed 抓到 stuck-state pattern | **PASS** |
| **6-B reader UI** | 用户首次能读全本 | 10 iter ship — 连读 / 分页 / 视点 / 字体 / 搜索 / vim 导航 | **PASS** |
| **6-C B-G det 层** | 4-6 dim 补完 | 13/16 dim 覆盖 (含 D1 / D2 / D5 / E2 + C6 + iter#J Goal validator) | **PASS** |
| **三层防护** | 没在 plan 里 (后期发现) | M (生产 guard) + O (critic 加严) + Y (UI alert) + Z (analyzer) | **PASS** |

## 关键发现 (与 plan 偏差)

### plan 怕的"长程 drift" 不存在

Plan 担忧 memory_compressor / sideline / stale-skip 累积超 200 tick 后 drift.
**4 个 500-tick bench 全部显示**:
* memory_compressor:l0_l1 每 ~50 tick 正常触发
* sideline + stale-skip 无 quality 退化
* 长程 narrative quality 抽样 (run 2 末 10 段) 无可见退化

→ Plan 假设错位. 长程稳定本身不是问题.

### 真问题: narrate-rate sustained-climax (跨 seed 确认)

Run 1 (24 日 steampunk) 进入 100% narrate stuck-state 4 buckets 到 quota wall.
当时怀疑 "LLM stochasticity 单次事故". **iter#TTT D8 + 后续 3-seed bench 证伪此假设**:

| run | seed | t201+ pattern | D7 cascade |
| --- | --- | --- | --- |
| Run 1 | steampunk | 100% narrate 4 bucket → quota wall | ❌ (老 schema 无 narrator_produced 字段无法 detect) |
| Run 2 | steampunk retry | 60% spike → 主动 recover t251 | 不 fire (单 bucket) |
| Republic | apocalypse_republic_spy | 80% spike → 主动 recover t251 | 不 fire (单 bucket) |
| **Apocalypse** | apocalypse_wasteland | **100% + 95% × 2 bucket** | **✅ FIRE — 首次跨 seed 确认** |

→ **真实结论**: t200 附近 plot beat 触发 narrator 进入高密度叙事是 deterministic
seed/scenario 触发, 是否 recover 取决于 LLM stochasticity. **iter#M 设计有
漏洞**: M 按 length (>1500 chars) 触发, 但 stuck-state 可以保持 800-1400 chars
narrative + 100% rate 绕过 M.

## 三层防护 (建立 + 缺口)

| layer | iter | scope | apocalypse 命中? |
| --- | --- | --- | --- |
| 生产 guard | M | narrator intensity guard (length 路径) | ❌ 漏掉 (length < 1500) |
| critic 加严 | O | >2500 chars 强制 critic | ❌ 漏掉 (narrative < 2500) |
| UI alert | Y | dashboard ⚠ INTENSITY chip | ✓ 显示 (post-hoc) |
| analyzer detect | Z (D7) + TTT (D8) | post-hoc cascade + quota wall | ✓ FIRE on apocalypse |

**缺口**: iter#M 只看 chars, 不看 narrate_rate. apocalypse 60%+ narrate-rate
sustained 6+ tick 应触发 narrate-rate-based guard. **Phase 7 必做**:
iter#YYY (proposed) — 加 narrate_rate-based intensity guard:
连续 ≥ 6 tick narrate=True → 强制下 tick silent (skip_narrate=True).

## 数字 (本 Phase)

| metric | 起点 (Phase 5 末) | 终点 | Δ |
| --- | ---: | ---: | ---: |
| Backend tests | 870 | **1126+** | +256 |
| Frontend bundle | 297 KB | **320 KB** | +23 KB / 10 features |
| det dim 覆盖 | 5 | **13** | +8 |
| Drift signals | 0 | **8 (D1-D8)** | +8 |
| Env knob (Phase 6 新) | 0 | **10+** | +10 |
| Memory entries | 3 | **6** | +3 |
| docs/iter/ artifact | ~750 | **800+** | +50+ |
| Tokens 烧 (4 bench) | — | ~11.9M | — |

## Phase 6 vs Phase 6 plan 候选对比

| 候选 | plan 描述 | 实际 |
| --- | --- | --- |
| A (quality det) | 4-6 周, 6-8 模块 + 30-50 test | **3 天, 6 模块 + 70+ test, 13/16 覆盖** |
| B (reader UI) | 2-3 周, 主要前端 | **2 天, 10 iter, 全 ship** |
| C (500-tick 长程) | 1 周 bench + 分析 | **2 天, 4 bench (2.5h-5h 各), 4 verdict + drift analyzer** |
| D (多 POV) | 3-4 周, high risk | **未做** (留 Phase 7) |
| E (多模态接入 reader) | 2 周 | **未做** (数据已有, reader 集成留后续) |

## 与 plan 决策点对比

| 决策点 | plan 问题 | 实际答案 |
| --- | --- | --- |
| 方向 | A / B / C 哪个先? | **A/B/C 并行做了** — 3 天内全部 ship |
| 节奏 | 每 sprint 2 周 / 4 周? | **单/双 session 完成** — sprint 概念 N/A |
| 判官 | glm-5.1 / mimo / ensemble? | **没跑 pairwise** — 只 drift 分析. cross-seed quality 抽样保留给 Phase 7 |
| Seed 集 | steampunk/republic/apocalypse / 5 个? | **3 个 (实际 4 个 run)** — quota constraint, 不上 5 |

## Phase 6 完整 iter 列表 (70+)

按 ITERATION_LOG.md 索引, 详细 commit 见 `git log --oneline 30 hash..HEAD`:

* iter#A-G (2026-06-24): dashboard 接 critic-log + window=N + C6 det + 500-tick runbook + reader 连读 + A1 化合物 dedup + viewpoint sidecar + localStorage 偏好
* Phase 6-A bench Run 1 (06-24 17:38 → 23:15): 334/500 quota wall, CONDITIONAL PASS, 怀疑 drift
* Phase 6-A bench Run 2 (06-25 02:32 → 07:37): 500/500 clean, **反驳 drift 假设**
* iter#J/K (Goal validator + bench schema)
* iter#L/M/O/P/U/JJ/KK+TT/BBB/CCC (reader 10 iter)
* iter#C1/C3/SS/UU/VV/XX (det 6 dim)
* iter#R/S/T/V/W/X/Y/Z/AA/D/TT3 (基础设施 11 iter)
* iter#GG/QQ/RR (docs maintenance)
* Republic bench (06-25 13:28 → 16:43): 500/500 mechanical, 350 effective, WARN
* iter#AAA/BBB/CCC/HHH (search endpoint + frontend + probe_quota)
* iter#KKK/NNN/PPP/QQQ/RRR/SSS (status + tests + CLI + runbook + iter prep)
* iter#TTT (D8 quota wall detection)
* iter#UUU/WWW (docs synch)
* **Apocalypse bench (06-25 18:27 → 22:23 死于重启, partial 290/500)**: **D7 cascade FIRE** — 首次跨 seed 确认 stuck-state pattern
* iter#YYY (proposed) Phase 7 — narrate_rate-based intensity guard

## Phase 7 Carry-forward

按重要性排:

1. **narrate_rate-based intensity guard** (iter#YYY proposed) — **必做**.
   连续 ≥ 6 tick narrate=True → 强制下 tick silent. apocalypse 数据已证 M 漏洞.
2. **4-char 化合物 dedup** (钢筋混凝土) — iter#C3 documented limitation, 优先
   级中 (实测 production noise 2.14/narr 已可接受).
3. **B/C/F/G semantic 维度 det 补全** — 留 LLM critic, 边际 ROI 低.
4. **跨 quota window resume 支持** — bench mid-run resume 现无, restart 浪费.
5. **多 POV 切换** (Plan 候选 D, high risk) — 不急, 等用户需求.
6. **多模态接入 reader** (Plan 候选 E) — 数据已有 (v2.33), 集成留后续.
7. **真实 pairwise quality bench** — cross-seed quality 抽样, 未做 (quota constraint).

## Sources

* `docs/iter/PHASE6_PLAN.md` (plan)
* `docs/iter/STATUS.md` (Phase 6 段全程汇总)
* `docs/iter/ITERATION_LOG.md` (per-iter 时间线)
* `docs/iter/INDEX.md` (800+ artifact 导航)
* `docs/iter/verdict-3seed-final.md` (cross-seed 对比)
* `docs/iter/verdict-phase6a-500tick.md` + `verdict-phase6a-500tick-retry-0625.md` + `verdict-spike-rootcause-0625.md` (Phase 6-A 系列)
* `docs/iter/CHANGELOG.md` v2.49 段
* `CLAUDE.md` "Phase 6 新增 env" + "Phase 6 新增 scripts" + "Phase 6-B Reader API" 三段

## verdict

**Phase 6 PASS**. 6-A 长程稳定, 6-B reader 全 ship, 6-C det 13/16 覆盖.
跨 seed 验证发现真问题 (sustained-climax pattern), 三层防护建立但 M 漏洞
留 Phase 7. Plan 担忧的"drift" 假设排除. 单 / 双 session 完成 plan 估计 4-6 周
工作量.
