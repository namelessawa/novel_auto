# WRITER_FIRST_PASS_FAIL

## 结论

Writer Preflight、单次整章 Retry 和 Transaction Revision Guard 已完成实现，自动化、离线回归与真实 Provider Mini Matrix 均已执行。真实 Mini 的提交数从上一阶段 8/15 提升到 11/15，`warm_healing` 从 0/3 提升到 3/3，Provider error 和 revision 完整性异常均降为 0；但真正不经过 Retry/Repair 的初稿直接通过仅 3/15，Repair dependency 仍为 73.33%，未达到本阶段 Gate。

因此结论为 `WRITER_FIRST_PASS_FAIL`，不具备运行 45 节 Stage 1 Full Matrix 的资格。15 节结果只代表本次小样本，不证明长篇稳定性。

## 修改文件

核心实现：

- `backend/story/writer_preflight.py`
- `backend/story/revision_guard.py`
- `backend/story/writer.py`
- `backend/story/service.py`
- `backend/story/models.py`
- `backend/story/context_builder.py`
- `backend/story/writing_plan.py`
- `backend/story/section_budget.py`
- `backend/api/story_routes.py`

测试与度量：

- `backend/tests/test_writer_preflight.py`
- `backend/tests/test_writer_retry.py`
- `backend/tests/test_revision_guard.py`
- `backend/tests/test_author_stage1_matrix.py`
- `scripts/run_author_longrange.py`
- `scripts/run_author_stage1_matrix.py`
- `docs/iter/INDEX.md`
- `docs/iter/writer-first-pass-optimization-20260727.md`

## WriterPreflight 设计

流程调整为：

```text
Writer initial
  -> deterministic WriterPreflight
  -> 最多一次 Writer Retry
  -> 完整 Narrative/State/Length/Ending Validator
  -> 最多一次局部 Repair Patch
  -> Commit 或 Reject
```

Preflight 只决定是否值得重写一次，不替代完整 Validator。检查项：

1. 非空白字符数以及 target/min/max。
2. opening/development/conflict/resolution 四段内容比例。
3. EventExecutionPlan 必要事件覆盖，阈值固定为 100%。
4. RequiredEndState 可达率，阈值固定为 100%。

结构检查不读取标题。它把实质句子按其在正文累计字符中的位置分配到服务端四段预算区间，检查每段是否有正文以及最低比例；阈值只用于识别缺失内容段，不作为文学质量评分。

Preflight 产生的主要错误码：

- `PREFLIGHT_TOO_SHORT`
- `PREFLIGHT_TOO_LONG`
- `PREFLIGHT_STRUCTURE_INCOMPLETE`
- `PREFLIGHT_EVENT_COVERAGE_LOW`
- `PREFLIGHT_END_STATE_UNREACHABLE`

Transaction 同时保存 initial/final Preflight report。`writer_first_pass_pass` 的定义比 Preflight 更严格：初稿必须通过 Preflight、完整 NarrativeContract 和权威状态校验，并且不使用 Retry 或 Repair。

## Writer Retry

Writer Retry 是独立的整章生成调用，不是 Patch：

- 输入完整 Context、SectionWritingPlan、SectionBudgetPlan、EventExecutionPlan 和 Preflight 失败原因。
- 不把失败正文作为可编辑文本交给模型，只提供长度、标题和摘要审计信息。
- 明确要求重新生成完整 `WriterCandidate` JSON。
- 风格只控制表达，不控制事件数量和章节长度。
- 禁止新增人物、背景、历史、关系、伤亡、伤势、数字、日期和世界规则。
- Retry 结果仍必须经过完整事实、状态、事件、终态、长度和 Ending Gate。
- Retry 本身不能直接写 CanonicalState。

调用硬上限：

```text
Writer initial = 1
Writer retry   = 1
Repair Patch   = 1
total          <= 3
```

Repair 的 INSERT/REPLACE/DELETE/EXPAND/COMPACT 安全边界没有放宽，也没有新增 Critic、第二 Writer、多 Agent 或 LLM Judge。

## Style Contract 调整

- `warm_healing`：温暖来自动作，不来自更多段落；连续情绪描写最多两段。
- `literary`：细节必须服务既有人物、必要事件或现有环境；禁止无事件功能的长描写。
- `noir_cold`：冷峻不等于短或省略，必须完整呈现行动、决定和结果。
- `classical_chapter`：古典感来自句式、节奏和叙述方式，不得增加历史背景。
- 全局原则：Style controls expression, not event count and not chapter length。

## Transaction Revision Guard

Transaction 新增 `journal_canonical_revision`。正常提交前要求：

```text
transaction.canonical_state_revision
==
journal_canonical_revision
==
current CanonicalState revision
```

并要求 `target_revision == expected_revision + 1`。

进入 committing 后，CanonicalState 成功写入即原子更新 journal revision。恢复时只允许：

```text
journal_canonical_revision == current CanonicalState revision
```

且该值必须是 transaction base 或 target revision。任何不一致都停止恢复，将事务持久化为 rejected，并记录：

```text
REVISION_CHAIN_BROKEN
```

真实 Mini 中 `canonical_revision_jump`、`canonical_revision_chain_broken`、重复 section/transaction 均为 0。

## 自动化与离线结果

| 验证 | 结果 |
| --- | --- |
| WriterPreflight 新增测试 | 4/4 |
| Writer Retry 新增测试 | 4/4 |
| Revision Guard 新增测试 | 3/3 |
| 后端全量测试 | 1534 passed；1 条既有 Starlette deprecation warning |
| Author UI | 14/14 |
| 前端生产构建 | passed |
| Python compile / `git diff --check` | passed |
| 24 个历史失败案例 | 24/24；Repair 17/17；regression 0；bad commit 0 |
| Stage 1 六个失败案例 | 6/6；patch failure 0；validator failure 0；regression 0 |
| Recorded 流程 | 6/6 commit；first pass 5/6；Repair 1/6；5 次 runtime rebuild |

离线证据：

| Artifact | SHA-256 |
| --- | --- |
| `.tmp/writer-first-pass-optimization/offline-24.json` | `b2f77be1d37c5fd52f860e5ef4678df807bd2c3d50a96d81276f928ca2e38159` |
| `.tmp/writer-first-pass-optimization/offline-six.json` | `871dc3f50003f8938c8f1726c8afe437f4246237c04fb94fc6992aa0291ec81b` |
| `.tmp/writer-first-pass-optimization/recorded-smoke/report.json` | `3e1b0217c916d3cfc456d27f3585d5336f810dba17a605f78eb85070a178068f` |

`.tmp` 证据保留在本地，不纳入 Git 提交。

## 真实 Mini Matrix

配置：

```text
theme=action_conflict
styles=literary,noir_cold,warm_healing,hot_blooded,classical_chapter
sections_per_style=3
model=glm-5.2
desired_length=900
seed=20260726
provider=custom（coding.txt）
```

最终矩阵完成 5/5 组合、15/15 attempts，执行时间为 2026-07-27 10:07:50–10:25:58（Asia/Shanghai）。

| 风格 | 提交 | 初稿直通 | Retry | Repair | 900–1100 | 平均长度 | Token | 平均延迟 | Provider error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| literary | 3/3 | 1/3 | 2/3 | 2/3 | 3/3 | 1017.33 | 51,118 | 75.07s | 0 |
| noir_cold | 2/3 | 0/3 | 3/3 | 3/3 | 2/3 | 1034.33 | 69,367 | 92.42s | 0 |
| warm_healing | 3/3 | 2/3 | 1/3 | 0/3 | 3/3 | 977.00 | 36,527 | 54.36s | 0 |
| hot_blooded | 2/3 | 0/3 | 1/3 | 3/3 | 2/3 | 929.67 | 43,340 | 50.75s | 0 |
| classical_chapter | 1/3 | 0/3 | 3/3 | 3/3 | 1/3 | 752.00 | 65,082 | 89.05s | 0 |
| **合计** | **11/15** | **3/15** | **10/15** | **11/15** | **11/15** | **942.07** | **265,434** | **72.33s** | **0** |

初稿与 Retry 分层：

- 5/15 初稿通过轻量 Preflight。
- 其中 2 节在完整 Validator 中发现新增伤势或日期，因此真正初稿直接通过为 3/15。
- 初稿 Preflight 问题：过短 7、过长 3、事件覆盖不足 4、终态不可达 2。
- 10 节执行 Writer Retry，只有 1/10 在 Retry 后直接达到完整交付，其余仍需要 Repair。
- Retry 后 Preflight 问题仍以过短为主：过短 7、过长 1、事件覆盖不足 2、终态不可达 2。
- 11 节使用 Repair，7 节 Repair 成功，Repair success 为 63.64%。

真实安全结果：

- 必要事件完成 15/15。
- 最终状态达到 14/15；未达到的一节被拒绝。
- 硬事实错误提交 0。
- 状态冲突提交 0。
- 非法 StoryThread change commit 0。
- 无证据 StateDelta commit 0。
- Transaction integrity violation 0。

与 Section Balance Mini 对比：

| 指标 | 上一阶段 | 本阶段 |
| --- | ---: | ---: |
| 提交 | 8/15 | 11/15 |
| Contract | 53.33% | 73.33% |
| 长度 900–1100 | 53.33% | 73.33% |
| Repair dependency | 100% | 73.33% |
| Provider error | 4 | 0 |
| Revision integrity anomaly | 2 | 0 |
| warm_healing | 0/3 | 3/3 |

结果有改善，但仍未达到“Repair 只处理少量异常”的阶段目标。

## Token、Latency 与 Provider 调用

Token：

- Prompt：220,306
- Completion：45,128
- Total：265,434
- Retry token：97,156（Total 的子集）
- Repair token：52,845（Total 的子集）

Provider：

- 记录调用 36 次 = 15 initial + 10 retry + 11 repair。
- Provider error：0。
- 平均每节端到端延迟：72.3295 秒。

## Gate

| Gate | 要求 | 实际 | 结果 |
| --- | ---: | ---: | --- |
| 正式提交 | ≥14/15 | 11/15 | FAIL |
| 初稿直接通过 | ≥8/15 | 3/15 | FAIL |
| Contract | ≥93% | 73.33% | FAIL |
| Repair success | ≥90% | 63.64% | FAIL |
| Repair dependency | ≤40% | 73.33% | FAIL |
| 长度 900–1100 | ≥93% | 73.33% | FAIL |
| 硬事实错误提交 | 0 | 0 | PASS |
| 状态冲突提交 | 0 | 0 | PASS |
| 事务损坏 | 0 | 0 | PASS |
| Provider error | 0 | 0 | PASS |

最终矩阵 Gate：`MINI_MATRIX_FAIL`。不运行、不授权 3 themes × 5 styles × 3 sections 的 45 节 Stage 1 Full Matrix。

真实证据：

| Artifact | SHA-256 |
| --- | --- |
| `.tmp/writer-first-pass-optimization/real-mini/stage1-matrix.json` | `744ff9936674f8fdddac2b76d090ce3ab64d8373fd2c13dd59d2474fcdd5177b` |
| `.tmp/writer-first-pass-optimization/real-mini/stage1-matrix.md` | `d6f12e761ee18d4d7a78b90abcb348ef25430175bd3adc7134047ae58654867d` |

## 证据边界

| 边界 | 本阶段含义 |
| --- | --- |
| deterministic | Preflight、Narrative/Event/EndState/Length/Ending/State validators、Revision Guard、Gate 和自动化测试 |
| recorded | 24/24、6/6 frozen fixture 与 6 节 Recorded 流程；不是本次 Provider 文学样本 |
| real provider | 上述 15 节由 `glm-5.2` 真实执行；token、latency、调用和错误来自持久化矩阵 |
| human review | 未执行；不声明人工文学质量验收 |
| LLM judge | 未执行；所有 PASS/FAIL 均来自确定性规则和数值 Gate |

本报告不把 Preflight 通过等同于完整 Contract 通过，也不把 Retry 成功或 15 节 Mini 外推为长篇稳定。
