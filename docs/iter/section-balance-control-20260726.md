# SECTION_BALANCE_FAIL

## 结论

Section Balance Control、Ending Gate 与受限 COMPACT 已完成实现，离线回归和代码回归通过；但真实 Mini Matrix 仅提交 8/15，长度命中率、Repair 成功率、Repair 依赖率、事务完整性和 Provider 稳定性均未达到 Gate。因此本阶段结论为 `SECTION_BALANCE_FAIL`，不具备重新运行 45 节 Stage 1 Full Matrix 的资格。

真实样本中必要事件与最终状态均为 15/15 完成，硬事实错误提交和状态冲突提交均为 0；当前失败集中在长度收敛、对 Repair 的过度依赖、Provider error，以及两条修订链完整性异常。15 节结果不能外推为长篇稳定性。

## 修改文件

核心实现：

- `backend/story/section_budget.py`
- `backend/story/ending_validator.py`
- `backend/story/context_builder.py`
- `backend/story/models.py`
- `backend/story/section_length_validator.py`
- `backend/story/repair_plan.py`
- `backend/story/repair_patch.py`
- `backend/story/service.py`
- `backend/story/writer.py`
- `backend/api/story_routes.py`

验证与可观测性：

- `backend/tests/test_section_balance.py`
- `backend/tests/test_compact_patch.py`
- `backend/tests/test_ending_gate.py`
- `backend/tests/test_author_generation_service.py`
- `backend/tests/test_author_stage1_matrix.py`
- `frontend/src/dashboard/views/AuthorStudioView.jsx`
- `frontend/tests/author-ui.test.mjs`
- `scripts/run_author_longrange.py`
- `scripts/run_author_stage1_matrix.py`
- `docs/iter/INDEX.md`
- `docs/iter/section-balance-control-20260726.md`

## SectionBudgetPlan 设计

服务端在原 `SectionWritingPlan` 之上生成受保护的 `SectionBudgetPlan`。当接受区间为 900–1100 字时，中心目标固定为 1000 字：

| 分段 | 建议预算 | 硬提示上限 |
| --- | ---: | ---: |
| opening | 180 | 230 |
| development | 300 | 350 |
| conflict | 300 | 350 |
| resolution | 220 | 270 |

四段预算总和必须等于中心目标。停止条件同时为：

1. `required_events_completed`
2. `end_state_reached`
3. `minimum_length_reached`

Writer prompt 明确要求三项同时满足后立即结束，禁止在此后增加人物、背景、冲突、历史、关系或解释。最终联合 Gate 是 `Event PASS AND EndState PASS AND Length PASS AND Ending PASS`；单独达到字数不再构成可提交条件。

五种风格拥有独立 `style_balance_contract`：

- `literary`：描写必须服务当前事件，不得为文学性开启新场景。
- `noir_cold`：冷峻不等于短篇，不得省略必要事件或低于长度下限。
- `warm_healing`：温暖必须落到照料行动，连续情绪描写最多两段。
- `hot_blooded`：不得用新敌人、战争、伤亡、受伤或新冲突增加强度。
- `classical_chapter`：不得用朝代、家族、官职、日期或新人物制造古典感。

## COMPACT 设计

Repair 顺序调整为：

1. 缺失事件
2. 错误终态
3. 非法事实
4. 长度 EXPAND/COMPACT
5. 极小风格调整

太短继续使用受限 `EXPAND`；太长或出现终态后扩张时使用 `COMPACT`。COMPACT 的删除范围由服务端从原文中选定，LLM 只能逐字段复制，不能自行决定删除内容。

安全限制：

- 单个 COMPACT 最多删除 200 个非空白字符。
- 删除锚点必须在原文唯一出现，并逐字段匹配服务端授权模板。
- `patch_text` 必须为空，不能借 COMPACT 添加任何事实。
- 不能携带事件或终态修改目标。
- 不能与已完成事件、最终状态、已验证 StateDelta、StoryThread resolution evidence 等保护区间重叠。
- PatchSet 总量仍受上限约束，不允许整篇重写或无限 Repair。
- Patch 应用后重新执行 Narrative、Length、Ending、State 和回归校验。

真实 Mini 共记录 46 个 COMPACT patch 和 7 个 EXPAND patch。COMPACT 路径已实际运行，但未把整体长度收敛率提升到 Gate 要求。

## Ending Gate

`EndingCompletionValidator` 以“全部必要事件和最终状态均已出现的最晚证据位置”为 resolution boundary。该位置之后若确定性模式检测到新事件、新人物或新冲突，产生：

```text
POST_RESOLUTION_EXPANSION
```

此错误可 Repair，并被路由到服务端授权的 COMPACT；安静收尾不被当作新剧情。最终 Ending report 和四项联合 Gate 均写入 transaction、API 响应和 Author Studio。

## 自动化与离线验证

| 验证 | 结果 |
| --- | --- |
| 后端全量测试 | 1522 passed，1 条既有 Starlette deprecation warning |
| Author UI | 14/14 passed |
| 前端生产构建 | Vite build passed |
| `git diff --check` | passed |
| 24 个历史失败案例 | 24/24 recovered；Repair 17/17；regression 0；bad commit 0 |
| Stage 1 六个失败案例 | 6/6；patch failure 0；validator failure 0；regression 0 |

离线证据：

| Artifact | SHA-256 |
| --- | --- |
| `.tmp/section-balance-control/offline-24.json` | `b2f77be1d37c5fd52f860e5ef4678df807bd2c3d50a96d81276f928ca2e38159` |
| `.tmp/section-balance-control/offline-six.json` | `871dc3f50003f8938c8f1726c8afe437f4246237c04fb94fc6992aa0291ec81b` |

上述 `.tmp` 产物保留在本地验证目录，不纳入 Git 提交。

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

最终原子矩阵覆盖 5/5 组合、15/15 attempts，执行时间为 2026-07-27 00:04:17–00:32:29（Asia/Shanghai）。

| 风格 | 提交 | 900–1100 | 平均长度 | Repair 成功 | COMPACT / EXPAND | Token | 平均延迟 | Provider error | 完整性 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| literary | 2/3 | 2/3 | 1059.00 | 2/3 | 13 / 1 | 41,365 | 266.41s | 0 | OK |
| noir_cold | 2/3 | 2/3 | 1038.33 | 2/3 | 14 / 1 | 45,305 | 107.48s | 2 | `canonical_revision_jump` |
| warm_healing | 0/3 | 0/3 | 1352.00 | 0/3 | 15 / 1 | 42,976 | 37.92s | 2 | `canonical_revision_chain_broken` |
| hot_blooded | 3/3 | 3/3 | 1043.33 | 3/3 | 4 / 1 | 38,846 | 45.85s | 0 | OK |
| classical_chapter | 1/3 | 1/3 | 723.67 | 1/3 | 0 / 3 | 34,801 | 41.61s | 0 | OK |
| **合计** | **8/15** | **8/15** | **1043.27** | **8/15** | **46 / 7** | **203,293** | **99.85s** | **4** | **2 条异常** |

Token 明细：

- Prompt token：163,234
- Completion token：40,059
- Total token：203,293
- 其中 Repair token：80,706（为 total 的子集，不重复相加）

Provider 调用：

- 矩阵记录的已形成 section transaction 的 Writer 调用：30 次，每节初稿与 Repair 各一次。
- 另有 4 次 provider failure；失败调用没有 section metrics，因此不把它们伪计入上述 30 次。
- 所有 15 节都依赖 Repair，Repair dependency 为 100%。

逐风格观察：

- `literary` 两节收敛，一节 Repair 后仍为 1128 字。
- `noir_cold` 两节收敛，一节为 1138 字；同时存在 Provider error 和 revision jump。
- `warm_healing` 仍为主要失败点：一节 744 字、两节分别 1548/1764 字，COMPACT 未形成可靠收敛。
- `hot_blooded` 是唯一 3/3 提交且 3/3 命中长度区间的风格。
- `classical_chapter` 两节 Repair 后仍只有 508/656 字，EXPAND 未达到下限。
- 15/15 必要事件与 15/15 最终状态均完成；被拒绝样本主要由长度、非法 Repair patch 或证据链 Gate 拦截。

真实证据：

| Artifact | SHA-256 |
| --- | --- |
| `.tmp/section-balance-control/real-mini/stage1-matrix.json` | `bc3bc4bd18bbf93e7032029caa79b0f2210da8bd3cb9bfc63b05a8c2626add03` |
| `.tmp/section-balance-control/real-mini/stage1-matrix.md` | `06aa728871a2496408e2e67aa376cb43763257ff3d105abcf140107aa850daae` |

## Gate

| Gate | 要求 | 实际 | 结果 |
| --- | ---: | ---: | --- |
| 提交 | ≥14/15 | 8/15 | FAIL |
| Contract | ≥93% | 53.33% | FAIL |
| Repair success | ≥90% | 53.33% | FAIL |
| Repair dependency | ≤40% | 100% | FAIL |
| 长度 900–1100 | ≥93% | 53.33% | FAIL |
| 硬事实错误提交 | 0 | 0 | PASS |
| 状态冲突提交 | 0 | 0 | PASS |
| 事务损坏 | 0 | 2 条完整性异常 | FAIL |
| Provider error | 0 | 4 | FAIL |

补充安全指标：非法 StoryThread change commit 为 0，无证据 StateDelta commit 为 0，重复 section/transaction 为 0，StoryBible revision 保持稳定。

结论：`MINI_MATRIX_FAIL`。不运行、不授权 3 themes × 5 styles × 3 sections 的 45 节 Stage 1 Full Matrix。

## 证据边界

| 边界 | 本阶段含义 |
| --- | --- |
| deterministic | Pydantic 契约、Budget/Length/Ending/Patch/State validators、单元测试和 Gate 聚合 |
| recorded | 24 个历史失败 fixture 与 Stage 1 六个 sanitized fixture 的离线重放；不代表本次 Provider 生成 |
| real provider | 上述 15 节由 `glm-5.2` 真实调用生成；矩阵中的 token、latency、调用和错误来自持久化记录 |
| human review | 未执行；本文是工程 Agent 审查，不声明人工文学质量验收 |
| LLM judge | 未执行；通过与否完全由确定性 Validator 和数值 Gate 决定 |

两条 revision 完整性异常按 Gate 原样计为失败；本报告不在缺少独立复现的情况下替它们断言根因。真实 Mini 只证明本次 15 节运行的表现，不证明长篇稳定，也不证明未运行的 45 节矩阵会通过。
