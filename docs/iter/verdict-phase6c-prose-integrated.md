# Phase 6-C 第二刀 — prose_dynamics 接入 narrative_critic verdict

> Phase 6-C 第一刀 (commit e8363f2) 落了 `quality_metrics/prose_dynamics.py`
> 但留了一句 "接入 narrative_critic 的 PR 独立". 本刀合上闭环.

## 改动

- `backend/agents/quality_checks.py`:
  - 新增 `check_prose_dynamics(text)` wrapper, 内部 lazy import
    `quality_metrics.prose_dynamics.prose_dynamics_report`,把
    E1 / D6 触发转 `DeterministicTrigger(severity="medium")`,evidence
    前缀加 `[prose_dynamics]` 区分.
  - env knob `PROSE_DYNAMICS_ENABLE` 默认 True (0/false/no/off 关).
  - 接入点: `run_deterministic_checks` 末尾, 在 `check_sentence_rhythm`
    之后 — 双 E1 共存, 由 `NarrativeCritic._merge_triggers` 按 code 去重
    (同 medium 保留先入, 老 quality_checks 的 E1 evidence 优先).
- `backend/agents/narrative_critic.py`: **零侵入**.
- `backend/tests/test_quality_spec.py`: +5 测试 (healthy / E1 / D6 / env
  kill switch / run_deterministic_checks 集成).

## Offline replay — Phase 6-A.2 500-tick 271 narratives

实跑 narrative 全集上跑 `run_deterministic_checks`, 看接入后触发频次:

| 指标 | 数值 | 解读 |
|---|---:|---|
| narratives ≥ 100 chars | 271 | 校准基线 |
| 老 E1 (`std/mean<0.25`) | 0 (0.0%) | **完全没触发** |
| 新 E1 (`stddev<6.0`, prose_dynamics) | 2 (0.7%) | 跟 commit e8363f2 校准数一致 ✓ |
| E1 老新重叠 | 0 | 永不同时触发, 无 noise 重复 |
| 新 D6 (abstract:concrete) | 0 (0.0%) | healthy bench 无 FP, 符合校准目标 ✓ |

**接入后 critic REVISE 上限增量:0.7%** (2/271 narratives), cost 增量
可忽略. quality 闭环已合上 — det 层 E1/D6 触发会驱动 narrative_critic
进 REVISE 决策分支.

完整 det code 频谱 (Phase 6-A.2 271 narratives):

| code | 触发数 |
|---|---:|
| A1 | 3603 |
| D2 | 51 |
| A6 | 4 |
| A4 | 3 |
| E1 | 2 |
| D6 | 0 |

## 解读

1. **老 E1 (相对阈值) 在长程实跑中 0 触发** — 说明 `std/mean<0.25` 阈值
   在长程 healthy prose 上偏严, 实际生产里相当于"死代码"路径. 新 E1
   绝对阈值 `stddev<6.0` 补位, 覆盖 healthy 但句长扁平的边缘 case.
2. **D6 在 healthy 数据 0 命中** — 校准时已确认 (commit e8363f2),
   bench 数据是 Phase 5-D follow-up 长程稳态 prose, 不含"全宏伟古老
   神秘"的 AI 套路. 单测 19 条用 degenerate 样本覆盖 D6 触发路径
   (`test_prose_dynamics.py`).
3. **新 D6 触发对 critic LLM cost 的影响**: 若未来 LLM 产 narrative
   退化为抽象密集 prose (典型 AI 失败模式), D6 立刻把它送进 REVISE,
   不依赖 LLM critic 慢路径捕捉. 这是 Phase 6-C 设计意图 — det 层
   覆盖 mechanical 维度, LLM critic 聚焦 semantic.

## 测试

- 新增 5 个 unit test:
  - `test_check_prose_dynamics_healthy_no_trigger` (healthy 样本不触发)
  - `test_check_prose_dynamics_flat_rhythm_triggers_e1` (5 句 4 字触发 E1)
  - `test_check_prose_dynamics_abstract_triggers_d6` (全抽象形容词触发 D6)
  - `test_check_prose_dynamics_env_kill_switch` (env=0 时不触发)
  - `test_run_deterministic_checks_includes_d6` (主入口 D6 可达)
- 全量 backend tests: **835 PASS** (前 830 + 5 新增, 零回归).

## 不在此刀 (留给 Phase 6-C 后续 slice)

- B (角色失真) — 内心独白 vs 行动比 (B4)
- C (情节) — 转折前铺垫 (C1) / 章末无悬念 (C6)
- D 其他 — 形容词堆砌已有 D2 (老), D4 告诉 vs 展示需要 NLP
- E 其他 — E2 对仗 / E3 POV / E7 翻译腔
- F / G — 语义类, 留 LLM critic

## Status

**Phase 6-C 第二刀 LANDED**. E1 + D6 接入闭环, det → REVISE 决策路径打通.
后续 sprint 可继续加 D4 / B4 / C1 等 det 维度, 或转 Phase 6-B reader 扩展.

## Sources

- Phase 6-C 第一刀: commit e8363f2 + `quality_metrics/prose_dynamics.py`
- 校准基线: `bench-phase6a2-longrange-500tick.json` (271 narratives)
- 接入: `backend/agents/quality_checks.py::check_prose_dynamics`
- 测试: `backend/tests/test_quality_spec.py::test_check_prose_dynamics_*`
