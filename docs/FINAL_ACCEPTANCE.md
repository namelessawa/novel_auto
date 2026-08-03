# 最终验收

本文定义当前整书候选的规范性验收顺序和阈值，不是执行结果。仓库中的历史 evidence、
历史 PASS/FAIL、旧分支或旧基线都不能作为当前 verdict。没有与当前源码 hash 绑定的全新
报告，结论就是“尚未验收”，而不是 PASS。

统一入口是 `scripts/run_final_long_novel_acceptance.py`。一次调用只推进一个 phase，固定顺序
为 `offline → probe → g1 → g2 → product → final`。它没有 resume/force；某 phase 失败、
中断或源码发生变化后，必须保留旧目录并换全新 evidence 根目录从 offline 重来。

## Fail-closed 规则

1. evidence 根目录在 offline 前必须不存在；runner 独占创建，绝不覆盖。
2. 周期开始记录当前分支、HEAD、完整非忽略源码树 SHA-256、受保护文件 hash 和旧 evidence
   树 hash。
3. 真实调用前完整执行离线 Gate。任一检查失败，修复后从新周期的完整离线 Gate 重来。
4. probe 通过前禁止 G1；G1 通过前禁止 G2；G2 通过前禁止 product。
5. 每个 phase 只能运行一次，失败或成功 receipt 都不能复制到另一周期。
6. 不降低 Validator、长度门槛、revision guard、风格边界或安全扫描来换取通过。
7. 原始 `coding.txt` 仅通过显式只读路径在进程内解析；不复制、不修改、不提交、不回显，
   不把路径、内容或 secret 写入日志、报告或 manifest。
8. 真实调用必须断言 `provider=custom`、`model=glm-5.2`、thinking disabled、SDK retries 0。
9. 真实调用日志只保存元数据；Provider 原始响应和正文不能进入 evidence JSON。

Runner 会拒绝错误 branch/merge-base。如果源码中的周期常量仍指向另一个候选，立即停止，
不能通过改 evidence 或跳 phase 绕过。

## 周期变量

下面的占位符只在当前 PowerShell 会话中替换，不写回仓库：

```powershell
$AcceptanceCycle = "long-novel-<UTC-or-local-timestamp>"
$EvidenceRoot = Join-Path ".tmp" $AcceptanceCycle
$UserRoot = "<absolute-user-root>"
$ProviderFile = Join-Path $UserRoot "coding.txt"
$PreviousEvidence = "<absolute-read-only-previous-evidence-directory>"
$AcceptanceArgs = @(
  "--provider-file", $ProviderFile,
  "--user-root", $UserRoot,
  "--previous-evidence-root", $PreviousEvidence,
  "--evidence-root", $EvidenceRoot
)
```

`$ProviderFile` 必须正好是 `$UserRoot\coding.txt`。Runner 还对 `$UserRoot\.env` 和
`$UserRoot\config.json` 做 hash 保护；它们可以不含 Provider key，也不是本周期的凭据来源。
`$PreviousEvidence` 必须存在且全程只读，只用于证明旧 evidence 未被修改，不能提供当前
Gate 的 PASS 收据。`$EvidenceRoot` 不能位于上述两个受保护目录内。

## Phase 1：offline

```powershell
python scripts/run_final_long_novel_acceptance.py `
  --phase offline `
  @AcceptanceArgs
```

此 phase 不调用真实 Provider；`npm audit` 可能访问依赖 registry，但不会接触小说 Provider
凭据或生成正文。Runner 在私有临时目录中按固定顺序执行：

```text
python -m pytest backend/tests/ -q -W error
python -m ruff check backend scripts core
python -m compileall -q backend scripts core
npm --prefix frontend run test:author
npm --prefix frontend run build
npm --prefix frontend audit --omit=dev
git diff --check
python scripts/smoke_author_mode_recorded.py --data-dir <fresh-temp-dir>
python scripts/smoke_long_novel_recorded.py --output-dir <fresh-temp-dir> --chapters 30 --sections-per-chapter 2
```

随后对当前源码与新 artifact 完成：

- API key exact scan；
- Provider Base URL exact scan；
- generic secret scan；
- untracked sensitive file 检查；
- recorded artifact 的 metadata-only 复制与 SHA-256 清单。

扫描器在内存中读取 `coding.txt` 的 exact 值，但不得把值或命中上下文写入产物。命中只
记录分类、数量和脱敏位置；任何命中都使 offline 失败。Runner 若没有实际执行完整固定
清单，或源码/受保护文件在执行中变化，也不能生成绿色收据。

### Recorded 30×2 门槛

本阶段的长程 smoke 不评价文学质量，验证持久化、控制、恢复和风格边界。必须满足：

- 完整提交 30 chapters，每章至少 2 sections，章/节顺序连续；
- service restart 至少 3 次，pause/resume 至少 2 次；
- 一次确定性 crash recovery 和一次 failed-section 新 attempt/transaction 重试成功；
- 只激活一次自定义风格，且只从下一未开始章节生效；
- duplicate section/transaction、revision discontinuity、recovery duplicate 均为 0；
- hard fact/state conflict、illegal ThreadChange、evidenceless StateDelta 均为 0；
- rejected prose leak、thread liveness violation、style snapshot mismatch 均为 0；
- 总长度相对规划偏差 ≤ 10%；长度在章节允许范围内的章节 ≥ 95%；
- manuscript/evidence 生成成功，失败 sentinel 和候选正文均不泄漏。

只有 smoke 自身全部 gates 为真且退出码为 0，offline 才能通过。

## Phase 2：probe

```powershell
python scripts/run_final_long_novel_acceptance.py `
  --phase probe `
  @AcceptanceArgs
```

Runner 只在 branch、HEAD、source-tree SHA-256、受保护文件和旧 evidence hash 与绿色 offline
收据完全一致时，内部调用：

```text
python scripts/probe_quota.py --provider-file <original-coding.txt> --provider custom --expect-model glm-5.2 --expect-thinking-mode disabled --expect-max-retries 0
```

Probe 只验证配置解析、认证、最小响应与脱敏诊断。失败时不启动 Writer，当前周期不能重用。

## Phase 3：G1

```powershell
python scripts/run_final_long_novel_acceptance.py `
  --phase g1 `
  @AcceptanceArgs
```

G1 使用 `action_conflict × literary × 1 section`、目标 900 非空白字符、固定 seed，并创建
全新的 transaction。所有条件都是硬门槛：

| 指标 | 门槛 |
| --- | ---: |
| attempted / committed / contract pass | 1 / 1 / 1 |
| narrative 非空白字符 | 900–1100 |
| required events / required end states | 全部完成且各至少 1 个 |
| Provider errors | 0 |
| Planner calls / full Writer retries | 0 / 0 |
| Provider calls | ≤ 2 |
| bad commits / transaction anomaly | 0 / 0 |
| missing patch anchors / post-resolution expansion | 0 / 0 |

任一项不满足即冻结失败 receipt，禁止进入 G2。

G1/G2 即使在首个 section 提交前失败，也必须留下 metadata-only 失败行。该行的调用总数
必须严格等于 `planner_calls + writer_calls + structured_output_repair_count`，且完整运行时
回执必须与本周期 `coding.txt` 解析结果一致。原始异常消息、Provider 响应和候选正文不会
进入 evidence。失败行、计数不一致或回执漂移本身就是硬失败，不能通过“attempted=0”隐藏。
矩阵 CLI 对这个 1×1 模式使用独立的 `G1_SINGLE_PASS` 退出门；不能套用 45 节 Stage 1 的
`committed_at_least_43_of_45` 退出条件。最终结论仍由上表全部 G1 checks 独立重算。
Writer 的提示 JSON Schema 精确要求 `narrative_cells` 中 52 个非空白句级正文单元：
十块依次含 `[4,4,6,6,6,6,6,6,4,4]` 个单元，按
`o1u1 … r2u4` 的冻结键序覆盖原有十个逻辑块。全部 52 个值都是精确非空白字符串，
每个值承载一个完整展开的句级 prose beat，不接受嵌套对象或数组。标准 900–1100 section
使用 1090 字单一 Provider 写作目标并保留 10 字硬上限余量；前两个单元各使用 20 字软目标，
其余 50 个单元各使用 21 字软目标，52 个实际 prose cell 目标相加恰好为 1090。十个逻辑块
只表达归属、不另设数值配额，也没有任何单元级独立长度硬门。服务端按
`cell → block` 冻结顺序原样连接，再按十块顺序加入段落分隔，
以非空白字符总数 900–1100
作为硬边界。缺键、多键、空值、退回旧 `narrative_text` / `narrative_blocks` 形态、空白
填充或聚合长度越界都不能计入 `Writer first pass`，且服务端不会自动复制、补齐、加标点或
截断正文。连接结果仍进入既有完整 Validator 和至多一次局部 Repair。每个单元必须是一个
完整展开的句级 prose beat；“软”只表示服务端不按单元字数独立拒绝，不表示 Provider 可以
用片语、摘要、提纲、标签或占位替代正文。receipt 只记录十块/52 单元的非空白长度和句界
计数，不记录单元正文或原始响应。若首个响应仅序列化无效，唯一一次格式修复仍复用本次
动态 52-key 纯字符串 schema；修复结果必须再次经过相同冻结连接和 900–1100 聚合契约，不能
回落到旧 `narrative_text` schema。Primary 或格式修复结果只要形状不符，或格式修复结果
聚合越界，就 fail-closed 为安全的 `PROVIDER_OUTPUT_INVALID`，不能进入提交路径。

局部 Repair 可在一次调用中返回多个冻结 ID/anchor/placement 的微补丁，Provider 调用计数
仍只增加一次。每个 patch 的 wire `patch_text` 必须是 `beat_1`、`beat_2`、`beat_3` 三个
非空白单元；服务端按冻结顺序原样连接成内部字符串，再执行既有数字、anchor、authority 与
安全审计。单元目标和 focus 是软引导，但每个连接后 patch 的最小/最大值都是硬边界。
服务端按真实长度缺口平衡分配逐 patch 最小值，使其总和覆盖最终下限；同时平衡分配绝对
上限，且上限总和不超过最终正文剩余空间。因此任一逐 patch 合法响应必然可达到 900 下限，
也不可能越过 1100 上限。缺失、重复、越权、不安全、逐 patch 越界或聚合越界会使整组原子
拒绝，原候选保持不变。

## Phase 4：G2

```powershell
python scripts/run_final_long_novel_acceptance.py `
  --phase g2 `
  @AcceptanceArgs
```

G2 使用五个固定风格 `literary`、`noir_cold`、`warm_healing`、`hot_blooded`、
`classical_chapter`，每个 3 sections，共 15 个：

| 指标 | 最低门槛 |
| --- | ---: |
| 完整尝试 | 15 / 15 |
| committed | 至少 14 / 15；目标 15 / 15 |
| 长度 900–1100 | 至少 14 / 15 |
| Writer 首次通过 | 至少 9 / 15 |
| 使用 Repair | 至多 6 / 15 |
| Repair 成功率 | ≥ 90% |
| Provider errors | 0 |
| Planner calls / full Writer retries | 0 / 0 |
| bad commits / transaction anomaly | 0 / 0 |
| missing patch anchors / post-resolution expansion | 0 / 0 |

当前 runner 复用严格 G2 assessment，可要求 committed=15、contract=15 和每节 Provider
calls≤2；以更严格规则为准，不能降低到表格以下。

## Phase 5：真实产品 smoke

```powershell
python scripts/run_final_long_novel_acceptance.py `
  --phase product `
  @AcceptanceArgs
```

Runner 在新的 staging 目录内部调用：

```text
python scripts/smoke_long_novel_provider.py --provider-file <original-coding.txt> --output-dir <fresh-exclusive-dir>
```

Smoke 必须走真实产品对象与控制面，并证明：

1. 使用 preset 建立整书规格并生成有效大纲；
2. 通过真实 Job 提交至少 2 个 preset 章节；
3. 创建并激活自定义风格到下一未开始章节；
4. 再提交至少 1 个使用新风格 snapshot 的章节；
5. 至少一次 pause/resume；
6. Planner calls 和全文 Writer retries 均为 0；
7. 每节 Provider 调用严格分解为 Planner、初稿/局部 Repair 和 format-only repair；局部
   Repair 必须计为第二次 Writer 调用，产品总数还必须包含大纲调用；
8. duplicate section/transaction 和 rejected prose published 均为 0；
9. manuscript 导出只含 committed 章节；
10. Provider、StyleProfile、transaction、报告和导出中没有 secret。

Provider 认证错误必须保留应用 JWT；该不变量同时由离线 API/UI 测试覆盖。任何产品 gate、
exit code、source/protected hash 或秘密扫描失败都使本 phase 失败。

## Phase 6：final

```powershell
python scripts/run_final_long_novel_acceptance.py `
  --phase final `
  @AcceptanceArgs
```

Final 只在前五个 phase 全部为绿色且仍对应相同 source/protected hashes 时运行。它重新扫描
源码和所有 evidence，验证 JSON 只含 metadata，生成最终产物，再对发布后的产物执行一次
exact/generic scan。它不会启动新的 Provider 调用，也不会读取历史 receipt 替代本周期数据。

## 必需产物

`$EvidenceRoot` 顶层至少包含：

- `report.json`：机器可读 phase、阈值、状态和最终 verdict；
- `report.md`：同一结果的人类可读摘要；
- `manifest.json`：artifact 清单、大小、SHA-256 和 product manuscript 位置；
- `artifact-sha256.json`：关键产物 hash；
- `recovery.md`：失败/中断后的新周期说明；
- `cycle-state.json` 与各 phase 的不可变 receipt。

报告记录当前 branch、HEAD、source-tree SHA-256、脱敏 Provider metadata、命令与退出码；不得
记录 `coding.txt` 路径/内容、API key、Authorization、完整 Base URL、Provider 原始响应或
用户正文。唯一允许的 prose artifact 是 product 的 committed-only manuscript。

## Verdict

最终 verdict 只从本周期新 `report.json` 读取。所有 phase、最终扫描和受保护不变量均为真
时，runner 才能发布 `FINAL_LONG_NOVEL_PASS`。任一 phase 未运行、缺 receipt、hash 不匹配、
阈值失败或扫描失败都不能宣称 PASS。README、本文、历史日志和聊天文字都不是 verdict
来源。

产品架构见 [最终产品架构](./FINAL_ARCHITECTURE.md)，真实 Provider 生命周期见
[Provider 生命周期](./PROVIDER_RUNTIME_LIFECYCLE.md)。
