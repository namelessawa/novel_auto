# Repair Patch Mode 验收报告

## 结论

`REPAIR_PATCH_PASS`

验收分支：`codex/repair-patch-mode-20260722`

基础提交：`d2e9ce0c0ab0ace25f3ca327bdab888e1052173b`

真实模型：`GLM-5.2`（`coding.txt`，报告与日志不保存凭据）

## 1. 修改文件

运行时与协议：

- `backend/story/repair_patch.py`
- `backend/story/repair_plan.py`
- `backend/story/writer.py`
- `backend/story/service.py`
- `backend/story/models.py`
- `backend/story/event_execution.py`
- `backend/api/story_routes.py`

测试与冻结回放：

- `backend/tests/test_repair_patch.py`
- `backend/tests/test_repair_patch_validator.py`
- `backend/tests/test_repair_patch_apply.py`
- `backend/tests/test_repair_patch_real_failure_replay.py`
- `backend/tests/test_stage1_failure_replay.py`
- `backend/tests/test_repair_plan.py`
- `backend/tests/test_event_completion_repair.py`
- `backend/tests/test_narrative_contract_generation.py`
- `backend/tests/test_author_generation_service.py`
- `backend/tests/test_author_context_validator.py`
- `backend/tests/fixtures/repair_patch_real_failures.json`

回放、长程验证与 UI：

- `scripts/extract_repair_patch_failures.py`
- `scripts/replay_repair_patch_failures.py`
- `scripts/replay_stage1_event_failures.py`
- `scripts/run_author_longrange.py`
- `scripts/smoke_author_mode_recorded.py`
- `frontend/src/dashboard/views/AuthorStudioView.jsx`
- `frontend/tests/author-ui.test.mjs`

## 2. Patch 架构

```text
原 WriterCandidate（正文 + 原结构化提案）
  ↓
现有 Narrative/Event/End Validator
  ↓
服务端生成 RepairPlan + relevant windows + exact patch templates
  ↓
单次 LLM Repair：只返回 INSERT / REPLACE / DELETE patches
  ↓
RepairPatchValidator
  ├─ anchor 存在且唯一
  ├─ 单 patch ≤ 300 字、禁止整章替换
  ├─ target 必须属于 RepairPlan
  ├─ 禁止新增人物、亲属、日期、数字、伤亡、伤势、背景、世界规则、支线
  └─ REPAIR_NO_CHANGE / REPAIR_REGRESSION
  ↓
服务端顺序应用局部 Patch
  ↓
原 Narrative / Event / End / State Validator 全量复验
  ↓
原子 Commit；任一步失败则拒绝，不允许第二次 Repair
```

Repair 响应中的 `narrative_text`、`state_delta`、threads、memory、summary、
title 等字段全部忽略，并记录 `REPAIR_EXTRA_FIELD_IGNORED`。Repair 后只替换
原候选的 `narrative_text`，原结构化提案仍由 StateValidator 重新验证。

旧 `DeterministicRepairEnforcer` 已从运行代码删除。事务模型中的
`repair_enforced_removals` 仅为读取旧持久化事务保留，当前运行链路不再使用。
现有 Narrative/Event/End/State Validator 与 Gate 均未放宽。

## 3. 离线 24 案例

历史 fixture 整文件 SHA-256 已冻结：

```text
8ec6567bc2c9cff0e96956a865e8a53e49c9e55961af9f91307a29d00646eae6
```

结果：

| 指标 | 结果 |
| --- | ---: |
| 历史案例 | 24 |
| 最终 accepted | 24/24 |
| 触发 Repair | 17 |
| Repair 成功 | 17/17 |
| Repair regression | 0 |
| Bad commit | 0 |

回放产物：
`.tmp/event-completion-repair/patch-offline-replay-r2.json`

SHA-256：
`95fcf8367d33ff20098dca69072b13c245bbbb55757b71d72cf88e6ab812b165`

## 4. 最终 6 个真实 reject 回放

从上一轮真实 15 节最终 reject 中脱敏冻结 6 例；原文和原 Provider Repair
输出均以 SHA-256 约束。新 fixture SHA-256：

```text
6bcf279b9ed1019102e5aec18ffd1c9c0580f30f6a0013a5dde2f46652666daf
```

结果：

| 指标 | 结果 |
| --- | ---: |
| 真实 reject | 6 |
| 正确局部 Patch | 6/6 |
| Patch Validator accepted | 6/6 |
| Narrative/Event/End/State 最终通过 | 6/6 |
| Repair regression | 0 |

回放产物：
`.tmp/event-completion-repair/real-rejects-patch-replay-r2.json`

SHA-256：
`dd0efdaed052150b859a327686b24cbe42106079f353e5b58cfa0e9b417bbd25`

## 5. 真实 15 节矩阵

验收参数与上一轮相同：

```text
theme = action_conflict
styles = literary,noir_cold,warm_healing,hot_blooded,classical_chapter
sections_per_style = 3
desired_length = 450
seed = 20260722
runtime_rebuild_every = 2
model = glm-5.2
```

最终矩阵：

| 风格 | 尝试 | 提交 | Repair | Token | 平均延迟 |
| --- | ---: | ---: | ---: | ---: | ---: |
| literary | 3 | 3 | 2 | 23,305 | 23.2377s |
| noir_cold | 3 | 3 | 1 | 21,272 | 20.4906s |
| warm_healing | 3 | 3 | 0 | 21,787 | 31.1300s |
| hot_blooded | 3 | 3 | 2 | 26,712 | 33.7921s |
| classical_chapter | 3 | 3 | 2 | 26,939 | 27.7349s |
| **合计** | **15** | **15** | **7** | **120,015** | **27.2771s** |

Gate：

| 验收项 | 阈值 | 结果 |
| --- | ---: | ---: |
| 正式提交 | ≥14/15 | **15/15** |
| Contract | ≥93% | **15/15，100%** |
| Repair success | ≥90% | **7/7，100%** |
| 硬事实错误提交 | 0 | **0** |
| 状态冲突提交 | 0 | **0** |
| 事务损坏 | 0 | **0** |
| Provider error | 0 | **0** |
| Event completed | 全部 | **15/15** |
| End state reached | 全部 | **15/15** |

最终 Gate：`MINI_MATRIX_PASS`。

验收矩阵产物：
`.tmp/event-completion-repair/patch-mini-matrix-r2-20260726/stage1-matrix.json`

SHA-256：
`effb28fed4f4b46a8d0322b19a5164018bf8a243a3d709ac159ed572394e26b8`

## 6. Repair、Token、Latency 与 Provider 次数

- Repair 率：`7/15 = 46.67%`
- Repair 成功率：`7/7 = 100%`
- 实际 Patch：8 个（INSERT 7、DELETE 1）
- Patch Validator 失败：0
- Prompt token：98,253
- Completion token：21,762
- Repair token 子集：24,312（已包含在总 token 中，不重复相加）
- 总 token：120,015
- 验收矩阵完成 Provider 调用：22 次（初稿 15 + Repair 7）
- 总延迟：409.1559s
- 平均：27.2771s
- 中位数：29.2902s
- P95：35.2648s
- 最小 / 最大：12.2277s / 35.8660s

验收前诊断预跑在首个组合发现模型把模板中的“林秋”改成“她”，被
`PATCH_EVENT_EVIDENCE_INCOMPLETE` 正确拒绝。该预跑在修复 Prompt 后主动终止，
原失败目录保留在
`.tmp/event-completion-repair/patch-mini-matrix-20260726/`，不计入最终验收矩阵。
预跑完成 5 次可审计 Provider 调用；终止时可能另有 1 个在途请求。

## 7. 验证

- 后端全量：`1491 passed`
- Patch/离线聚焦：`31 passed`
- 前端 Author UI：`14 passed`
- 前端生产构建：通过
- Ruff（改动核心文件）：通过
- `git diff --check`：通过
- recorded 长程：4/4 committed，Repair 1/1
- recorded authority/recovery smoke：10/10 步骤通过，Provider 调用 0

## 8. 未解决问题

- 本阶段 Gate 无阻塞项。
- 有 1 个无效 thread proposal 被原 StateValidator 正常丢弃；未进入正式状态，
  不属于状态冲突或硬事实错误提交。
- 按阶段约束，本次没有启动 Stage 1 的 45 节测试。真实 15 节已经通过，后续才具备
  进入 45 节测试的资格，但不在本阶段自动扩大范围。
