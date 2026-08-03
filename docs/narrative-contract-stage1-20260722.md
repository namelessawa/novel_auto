# Narrative Contract Stage 1 真实矩阵复跑（2026-07-22）

> 历史真实矩阵记录，不授权当前 Provider 调用，也不代表当前 G1/G2。当前候选必须使用
> [最终验收](./FINAL_ACCEPTANCE.md) 的全新独占 evidence 周期。

## 结论

`STAGE1_FAIL`

本轮已实际完成完整 Stage 1 调用矩阵：3 个主题 × 5 个风格 × 每组合 3 次连续生成，共 15 个独立连续状态链、45 次 GLM-5.2 真实生成。矩阵执行完整，但门禁未通过：45 次输出中只有 21 次通过正文与状态双层校验并正式提交，24 次被事务硬拒绝。因此不能进入 Stage 2，也不能把“45 次真实输出完成”表述成“45 节正式章节提交完成”。

每个组合只初始化一次 StoryBible，并在同一 runtime / CanonicalState 上串行生成。拒绝事务不推进 CanonicalState，所以下一次尝试仍生成该状态链的下一正式节；这正是事务设计要求，也是本轮部分组合的 `section_id` 在尝试记录中重复、但已提交 `section_id` 与 revision 均不重复的原因。

## 执行配置

```powershell
python scripts/run_author_stage1_matrix.py `
  --provider-file coding.txt `
  --themes reality_mystery,action_conflict,warm_relationship `
  --styles literary,noir_cold,warm_healing,hot_blooded,classical_chapter `
  --sections-per-combo 3 `
  --checkpoint-every 1 `
  --combo-retries 1 `
  --desired-length 400 `
  --seed 20260722 `
  --output-dir .tmp/narrative-contract-stage1-20260722-final
```

- Provider / model：`custom` / `glm-5.2`，凭据只注入进程环境。
- 执行时间：2026-07-22 18:14:08—18:36:53（Asia/Shanghai），约 22 分 45 秒。
- 运行方式：不同小说串行；同一本小说内绝不并发写状态。
- checkpoint：每次尝试完成后落盘；15 个组合各自独立运行目录。
- 价格：未配置 token 单价，因此不伪造成本数字。

## Gate 与总指标

| 指标 | 实际 | Gate | 结果 |
| --- | ---: | ---: | --- |
| 组合完成 | 15 / 15 | 15 / 15 | 通过 |
| 真实生成尝试 | 45 / 45 | 45 / 45 | 通过 |
| 正式提交 | 21 / 45 | 本轮强校验要求 45 / 45 | 失败 |
| 硬事实错误提交 | 0 | 0 | 通过 |
| 事务数据损坏 | 0 | 0 | 通过 |
| Narrative Contract accepted | 23 / 45（51.11%） | ≥ 95% | 失败 |
| Repair 后 accepted | 6 / 30（20.00%） | ≥ 98% | 失败 |
| Repair 率 | 30 / 45（66.67%） | 观测项 | — |
| 硬拒绝 | 24 | 观测项 | — |
| Provider error / retry | 0 / 0 | 观测项 | — |

Token：prompt `191,213`，completion `64,415`，总计 `255,628`；其中 repair completion `40,773`（为 completion 子集，不能重复相加）。单次尝试平均耗时 `30.1629s`。

## 15 个组合

| 主题 | 风格 | 尝试 | 提交 | Contract pass | Repair | 拒绝 | Token |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| reality_mystery | literary | 3 | 2 | 2 | 2 | 1 | 18,117 |
| reality_mystery | noir_cold | 3 | 2 | 2 | 1 | 1 | 16,722 |
| reality_mystery | warm_healing | 3 | 0 | 1 | 3 | 3 | 17,979 |
| reality_mystery | hot_blooded | 3 | 3 | 3 | 2 | 0 | 19,616 |
| reality_mystery | classical_chapter | 3 | 1 | 1 | 2 | 2 | 15,659 |
| action_conflict | literary | 3 | 2 | 2 | 1 | 1 | 14,558 |
| action_conflict | noir_cold | 3 | 1 | 1 | 3 | 2 | 16,126 |
| action_conflict | warm_healing | 3 | 2 | 2 | 1 | 1 | 17,616 |
| action_conflict | hot_blooded | 3 | 1 | 1 | 3 | 2 | 18,800 |
| action_conflict | classical_chapter | 3 | 1 | 1 | 2 | 2 | 14,915 |
| warm_relationship | literary | 3 | 1 | 1 | 2 | 2 | 16,224 |
| warm_relationship | noir_cold | 3 | 1 | 1 | 2 | 2 | 15,774 |
| warm_relationship | warm_healing | 3 | 1 | 1 | 2 | 2 | 18,535 |
| warm_relationship | hot_blooded | 3 | 2 | 3 | 2 | 1 | 17,436 |
| warm_relationship | classical_chapter | 3 | 1 | 1 | 2 | 2 | 17,551 |

唯一 3/3 正式提交的组合是 `reality_mystery × hot_blooded`。按风格统计，hot_blooded 的提交率最高（6/9），warm_healing 与 classical_chapter 最低（均为 3/9）；这轮失败不是强风格单向恶化，五个风格都没有达到 Gate。

## 失败分布

最终仍存活的正文违规码：

| 违规码 | 次数 |
| --- | ---: |
| `REQUIRED_EVENT_MISSING` | 15 |
| `END_STATE_NOT_REACHED` | 10 |
| `NARRATIVE_TOO_LONG` | 1 |

修复前还捕获并成功清除过 `UNSUPPORTED_BACKSTORY_ADDED`、`UNSUPPORTED_NUMBER_ADDED`、`UNSUPPORTED_DATE_ADDED`、`UNSUPPORTED_INJURY_ADDED` 和 `NARRATIVE_TOO_SHORT`。这说明新增事实防线有效，但 Repair 对“事件必须实际发生”和“结局必须实际到达”的完成能力不足。

最终状态层违规码：

| 违规码 | 次数 |
| --- | ---: |
| `THREAD_FIELD_OVERRIDE_FORBIDDEN` | 5 |
| `DELTA_NARRATIVE_MISMATCH` | 5 |
| `THREAD_ADVANCE_UNKNOWN` | 2 |
| `THREAD_ADVANCE_NO_EVIDENCE` | 1 |

全矩阵记录 13 个 state conflict、64 个已验证 delta、5 个被拒 delta；任何带冲突的候选都没有进入 CanonicalState。主要修复方向应是：让 Repair 严格补齐缺失事件/终态，同时禁止修复响应擅自重写已验证的线程字段或提交与修复后正文不一致的 delta。不能通过放宽确定性 Gate 提高表面通过率。

## 连续性、记忆、风格与重复

- 15 个组合的已提交 `section_id`、事务 ID 均唯一，Canonical revision 全部连续，无跳号、重复或半提交。
- 共执行 30 次 runtime rebuild；未注入 staged crash，本轮没有 recovery 事件。
- 最大 active StoryThread 为 2，最大 memory records 为 11；Stage 1 只有三次尝试，不能据此证明长期记忆质量。
- style contract 通过 28/45，17 次 drift warning；事实失败的文本即使风格清晰也不计整体通过。
- 平均 opening overlap `0.0205`，平均连续 n-gram overlap `0.0373`；短链结果只能作为退化预警，不能替代长程分析。
- 平均 contract coverage `0.8611`，required-event coverage `0.6667`，required-end-state coverage `0.7778`。

## 证据与安全边界

- deterministic：正文合同、状态事务、连续 revision、拒绝不提交和矩阵 Gate。
- recorded：本轮未使用录制响应。
- real provider：45 次 GLM-5.2 真实生成，含 30 次 Repair。
- human review：未执行。
- LLM judge：未执行；Writer 没有自评，确定性 Gate 没有被模型评分覆盖。
- 凭据扫描：扫描输出目录 464 个文件，`coding.txt` 的 API key 命中 0 个文件。

本地原始证据入口：

- `.tmp/narrative-contract-stage1-20260722-final/stage1-matrix.json`：逐组合、逐尝试完整机器指标。
- `.tmp/narrative-contract-stage1-20260722-final/stage1-matrix.md`：矩阵摘要。
- `.tmp/narrative-contract-stage1-20260722-final/runs/<theme>__<style>/report.json`：每条连续链报告。
- 同目录 `samples/section_*.txt`：45 份完整正文，以及执行 Repair 的 before / after 文本。

这些原始生成物保留在受控 `.tmp` 目录，不纳入 Git；正式结论与可复现命令由本文档记录。

## 验收

- 后端：`1433 passed, 1 warning`。
- Ruff：新增/修改的 runner 与测试全部通过。
- 前端：作者工作区 `14 passed`。
- Vite production build：通过。
- Stage 2：`NOT_RUN`，因为 Stage 1 Gate 未通过。
