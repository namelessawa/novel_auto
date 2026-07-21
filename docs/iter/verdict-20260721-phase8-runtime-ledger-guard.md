# Phase 8 最终报告：端到端运行时、类型化连续性账本与 StateGuard 校准

日期：2026-07-21

分支：`codex/longtext-style-iteration-20260721`

Phase 8 起点：`7f8f7e3141a3ffaf0106d8867a4bc271ef1c8220`

最终证据 HEAD（本报告提交前）：`be7ef77b167e148a48df93bbb43b941537bcf0fd`

行为基线：`6477f61b3ade9f3e984f66f457521976106edac9`

Phase 7 measured candidate：`040ad05`（结论 `INCONCLUSIVE`）

## 1. Executive summary

Phase 8 按顺序完成 Iteration 10–15，并在校准门禁失败后停止，没有越过前置
条件进入 Iteration 16 或 17。

- **Infrastructure**：通过。新增隔离的 full-runtime replay，deterministic mock
  与 recorded response 均经实际 `TickRuntime`/`Orchestrator` 组件图运行；新增
  `TypedContinuityState` v1、legacy fail-safe、raw audit、CanonicalFact 保守投影
  和四视图 reconciliation 证据。
- **Measurement**：通过。56 个 Phase 7 决策可无模型调用重放，73 个案例形成
  loss-aware 校准集，指标对缺失分母返回 null，不把 recorded outcome 当成
  ground truth。
- **Behavior**：仅接受 Iteration 13 的类型化 schema/持久化边界。没有修改
  StateGuard 阈值、接受规则或 repair 轮次；没有启用 CanonicalFact 消费者；
  没有修改 StylePreset 或接入 SummaryTree。
- **Quality**：未证明提升。Phase 8 没有真实模型生成、独立 judge 或人工标注，
  因而不能声称连续性、风格或正文质量改善。

停止原因是 `BLOCK_BEHAVIOR_CANDIDATE`：只有 34 个 decisive label，且有
recorded signal 的 20 个 decisive case 全是 expected accept；hard contradiction
recall 无法计算。39/73 案例仍为 ambiguous，0 个标签经过独立人工审查，typed
candidate decision coverage 为 0。继续调整 StateGuard 会把证据缺失误当成行为
优化。

此外，当前 replay CLI 只实现 `mock` 和 `recorded`；附件要求的 `real` 模式及
Gate B2 没有实现或运行。短 fixture 未配置 Critic。这些缺口均保留，不以 mock
结果代替。

## 2. Baseline 与最终状态

| 项目 | Phase 8 baseline | Phase 8 最终状态 |
| --- | --- | --- |
| 生产路径 replay | 无独立 fixture/schema/checkpoint/reconciliation 产物 | mock 与 recorded 可重放；真实模型模式未实现 |
| Phase 7 guard 证据 | 56 个 outcome，缺少完整 rejected draft/repair prose | 56/56 决策重现，缺失负载显式记录 |
| continuity ledger | 任意 dict，自然语言可污染地点/持有/伤势 | typed v1 + 引用目录校验 + raw audit + legacy fail-safe |
| StateGuard 校准 | recorded decision 未与 ground truth 分离 | 73 案例、34 decisive、39 ambiguous；行为门禁阻断 |
| StateGuard 行为 | Phase 7 既有逻辑 | 未改阈值、正则、接受逻辑或 repair 上限 |
| CanonicalFact | sidecar 与 reconciliation 基础设施 | 继续投影/审计；未成为 Narrator/StateGuard 新消费者 |
| 真实模型质量 | Phase 7 `INCONCLUSIVE` | 未重新测量，不作提升声明 |
| 后端测试 | 无 Phase 8 回归 | `1294 passed`，1 个既有 warning |
| 前端生产构建 | 待最终复验 | Vite 构建通过，55 modules transformed |

环境证据只记录变量名与存在性，不读取 `.env` 或任何值：Python 3.11.15、
Node v24.11.0、npm 11.14.1；当前进程的 `LLM_PROVIDER`、`DEEPSEEK_API_KEY`、
`MIMO_API_KEY`、`ARK_API_KEY`、`OPENAI_API_KEY`、`CUSTOM_API_KEY`、
`JUDGE_MODEL`、`LLM_TIMEOUT`、`CRITIC_ENABLE_LLM`、
`NARRATOR_ENABLE_CRITIC` 均为 absent。Phase 8 没有读取 `coding.txt`。

## 3. Iteration 记录

| Iteration | 单一假设/最小改动 | 主要证据 | 决策 |
| --- | --- | --- | --- |
| 10 | fixture transport 可通过真实组件图建立可重复 full-runtime replay | 1 accepted Tick；6 fixture calls；13 CanonicalFact additions；15 reconciliation checks、0 finding；全后端 1258 | `ACCEPT_INFRASTRUCTURE` |
| 11 | 明确 recorded provenance 与 loss-aware 转换可复用 Phase 7 证据 | 56/56 decision reproduced；20 accept/36 reject；rejected draft 0/36；repair full prose 0/56；全后端 1263 | `ACCEPT_MEASUREMENT` |
| 12 | 严格 typed contract 可把含糊字段变成可验证数据而不激活消费者 | 12 个 contract 回归；unknown/自然语言不成为权威事实；全后端 1275 | `ACCEPT_INFRASTRUCTURE` |
| 13 | Narrator 可输出 typed v1，并以 compatibility view 保持旧 Guard/投影边界 | recorded typed 1/1 valid；raw audit 1/1；稳定 hash；全后端 1285 | `ACCEPT_BEHAVIOR`（仅 schema/持久化） |
| 14 | loss-aware 数据集可区分缺失证据、标签与 recorded signal | 73 案例；27 accept、7 reject、39 ambiguous；11 类错误覆盖；全后端 1290 | `ACCEPT_MEASUREMENT` |
| 15 | coverage-aware 指标可防止在无 hard-negative signal 时误改 Guard | recall 明确 unavailable；行为门禁阻断；全后端 1294 | `ACCEPT_MEASUREMENT` |

没有行为候选被拒绝后回滚；原因是门禁在候选实现前即阻止 Iteration 16。
Iteration 17 因此传递性阻断。

## 4. Runtime execution coverage

这里的“执行”指生产类与生产控制流被调用；LLM transport 使用 fixture，不表示
真实 provider 调用。

| 组件 | 是否执行 | 证据边界 |
| --- | --- | --- |
| Orchestrator | 是 | 实际 `Orchestrator.run_tick()` 完成 |
| ActionResolver | 是 | production resolver 调用 1 次并应用 accepted action |
| Narrator | 是 | production Narrator 被调用，响应来自 agent-id-routed fixture |
| Critic | 否 | 短 deterministic fixture 未配置 Critic；报告标记 false |
| StateGuard | 是 | accepted 与 bounded-repair-then-reject 路径均有回归 |
| Persistence | 是 | TickState、TickDB、narrative、sidecar 均检查 |
| CanonicalFact | 是 | accepted fixture 新增 13 项；rejected prose 不投影 guarded facts |
| Reconciliation | 是 | 15 项检查，0 finding |

Replay 固定初态、事件和按 agent ID 路由的响应，使用只允许
`user_id="__replay__"` 的私有隔离目录。mock artifact 的 full-runtime evidence
hash 可复现；recorded artifact 的稳定 evidence SHA-256 为
`616e89687d4d164434f1e399500433cff0a796fd999a2fafc94c8ea49c599fa2`。
typed recorded artifact 的稳定 evidence SHA-256 为
`65bc64b8f3c9210a9797373ac0f7ae85459d44e2f7a7d2fa05074b76c79ce2c1`。

完成 checkpoint 可用 `--resume` 复验。部分多 Tick resume、真实 provider 模式、
真实模型预算/令牌上限与 checkpoint 尚未实现，因此 Replay Harness 不是附件中
三模式验收的完整 PASS。

## 5. Typed continuity ledger

核心 contract 是 Pydantic `TypedContinuityState` v1。关键结构如下（省略可选
字段）：

```json
{
  "schema_version": "1",
  "time_marker": "",
  "characters": {
    "char_wounded": {
      "location_id": "city_gate_inner",
      "movement_status": "arrived",
      "destination_location_id": null,
      "supporting_character_ids": ["char_linxue"],
      "carried_by_character_id": null,
      "injuries": [],
      "knowledge_fact_ids": []
    }
  },
  "items": {},
  "newly_known_fact_ids": {},
  "active_open_loop_ids": []
}
```

### 保证与兼容

- `location_id`、character/item/fact/open-loop/source-event ID 先做稳定 ID 语法
  校验，再与本次 Narrator 已拥有的引用目录核对。
- movement 仅允许 `stationary/departing/in_transit/arrived/unknown`；
  `in_transit` 不投影成 arrived。
- 支撑与搬运独立于地点；`由林雪架着` 不再能作为 typed location。
- injury 有稳定 ID、body part、severity、lifecycle status 和 source event。
- item 支持多 holder、location、非负 quantity、condition 与 container；unknown
  或 ambiguous multi-holder 不转成单一 objective field。
- legacy raw state 始终可读，并保留 raw payload、source schema、issues、
  references checked 与 authoritative eligibility。无法安全解析时不猜测、不
  抛出整个 Tick、也不生成权威 CanonicalFact。
- 老 TickState 无 audit 时加载为 non-authoritative legacy audit，无数据迁移。
- Guard 采纳 legacy repair 时明确降级为 legacy audit，不能冒充 typed authority。

第一次 recorded typed replay 暴露了旧 depth-4 compactor 将 `InjuryState` 变成
字符串的问题；深度上限调整到 6，其他容器/字符串大小限制不变并有回归测试。

### 有效性与 Prompt 成本

recorded fixture 为 1/1 typed valid、1/1 reference-authoritative-eligible、1/1 raw
audit retained。它只证明控制流，不代表真实模型 schema 合规率。附件要求的
“试验输出 schema 合法 ≥90%”没有真实模型分母，不能视为满足。

静态 system prompt 为 2,891 字符，相比 Iteration 12 增加 33 字符（+1.2%）；
最小 fixture 的动态 ID/schema block 为 419 字符。没有可解释的真实 token 或
latency delta。

## 6. Calibration dataset

- 总数：73。
- 来源：56 个 Phase 7 recorded trace + 17 个 minimal synthetic counterexample。
- provisional labels：accept 27、reject 7、ambiguous 39；decisive 34。
- 人工审查：0。每例有两次 Codex-assisted rubric pass，73/73 一致，但明确不是
  独立人工 ground truth。
- Phase 7 的 20 个 accepted case 有 pinned source full text，暂标 accept。
- Phase 7 的 36 个 rejected case 因完整 rejected draft 和 repair body 缺失，全部
  保持 ambiguous，没有合成缺失正文。
- 11 类 taxonomy 均覆盖：endpoint、location、item holder/condition、knowledge
  leak、ledger missing/wrong type、evidence extraction、reasonable omission、
  ungrounded fact、repair fact change。
- Dataset SHA-256：
  `573b2d822b8ecc3d4caf2609781d1fa2c26cd3ced46e8b25eba4f8dcc5b43441`。

已知 mojibake 只在 derived review view 中、且仅在 CJK score 提升时修复；raw
source 与 source hash 不变。

## 7. StateGuard calibration

正类定义为 reject；ambiguous 排除。34 个 decisive case 中只有 20 个带 recorded
signals，且 20 个全为 expected accept。

| Signal | Coverage | TP | FP | TN | FN | Precision | Recall | FPR | FNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| verifier reported safe | 20/34 | 0 | 1 | 19 | 0 | 0.000 | 不可用 | 5% | 不可用 |
| deterministic evidence gate | 20/34 | 0 | 4 | 16 | 0 | 0.000 | 不可用 | 20% | 不可用 |
| combined final decision | 20/34 | 0 | 0 | 20 | 0 | 不可用 | 不可用 | 0% | 不可用 |
| typed ledger candidate | 0 | — | — | — | — | — | — | — | — |

不存在带 recorded signals 的 labeled reject，所以 TP/FN 与 hard-error recall 没有
有效分母。报告保留 null，不将其强制写成 0 或 1。

- Ambiguous rate：39/73 = 53.4%。
- Repair attempts：40。
- Repair adopted/success：4/40 = 10%。
- Recorded fact preservation：32/40 = 80%；其余 8 次为 fact change 或 unknown。
- 31 个 `verifier safe + deterministic reject + final reject` case 是 probable
  evidence failure 候选，不是已确认 false positive。
- Operational reproduction 仅比较已有运行结果：verifier precision 83.3%、
  recall 13.9%；deterministic precision 90%、recall 100%。combined 与自身 recorded
  final outcome 完全一致是同义重放，不是质量准确率。

校准报告 SHA-256：
`b4d6f86a0c1b9c12c14ab5d82903317b4763185afd7fde549606c5c0c636dddc`。

最终门禁为 `BLOCK_BEHAVIOR_CANDIDATE`：decisive 少于行为门禁要求的 40；没有
signal-backed reject；没有独立人工审查；typed candidate coverage 为 0。因此
没有执行降低阈值、扩展中文正则或改变 fail-closed 行为的实验。

## 8. CanonicalFact consumer experiment

未运行。StateGuard behavior candidate 未获准，hard contradiction recall 不可测，
真实 Gate B2 也未运行，因而不满足附件第九节的全部前置条件。

CanonicalFact 继续作为 sidecar、投影与 reconciliation 审计基础设施；没有通过
feature flag 或默认路径注入 StateGuard，更没有注入 Narrator。SummaryTree 和
新的 NarrativeContextBundle 也没有接入生产。

## 9. Cost

| 模式 | Provider calls | Model tokens | 说明 |
| --- | ---: | ---: | --- |
| deterministic mock full runtime | 0 | 0 | 6 次 fixture transport call |
| recorded full runtime | 0 | 0 | 6 次 fixture transport call；稳定 evidence hash |
| Phase 7 decision replay/calibration | 0 | 0 | 56 traces，73-case dataset，纯本地指标 |
| real LLM | 0 | 0 | 因行为门禁阻断，未使用 `coding.txt`/provider/model |

Verifier token share、repair token share、accepted prose chars 与每 1000 字 token
成本均不可用；fixture response 不是 provider token。把这些字段写成 0% 会造成
误导，因此报告为 N/A。Critic 在短 fixture 中未运行。

## 10. Worst cases

以下保留失败与证据不足，不只展示成功 fixture。

1. **确定的 endpoint failure（minimal case）**：要求
   `char_hero enters city_interior`，正文明确“在外堡门洞下停住；内城门还紧闭”，
   ledger 为 `outer_fortification`。预期 reject；外堡不能被当作城内。但该案例
   没有 recorded Guard signals，所以只能证明标签/回归语义，不能贡献 recall。
2. **Probable evidence false negative**：Phase 7 literary tick 003 中，两人落到
   城墙外、地图被灰雪浸湿并由林尘收回、主角背伤员南行；verifier safe，
   deterministic gate 却以“雨水作用/损坏缺少逐字证据”拒绝。完整 rejected
   draft 缺失，最终标签只能 ambiguous，不能宣称已修复假拒绝。
3. **Ledger type failure**：`char_wounded.location = "由林雪架着"` 把支撑动作写
   成地点；正文也未给出可归一化终点。legacy normalizer 保留 raw 并标 unknown/
   non-authoritative；typed schema 要求 `supporting_character_ids` 或
   `carried_by_character_id`，不猜测位置。
4. **知识越权**：主角在无来源事件、无合法已知事实时说出“密道就在钟楼第三块
   砖后”，并把 `fact_secret_route` 写入自己的 known facts。预期 reject；该
   minimal case 同样缺少 recorded signals，暴露了 hard-negative coverage 缺口。
5. **物品状态冲突**：正文中买家接图封入铁匣、主角空手离开，declared ledger
   却仍把地图 holder 写成主角。预期 reject；它覆盖物品归属回退，但尚未形成
   有真实 Guard trace 的 ground-truth negative。

## 11. Modified files

相对 Phase 8 起点没有删除文件，也没有修改 `old/`。

### Final net changes

- `backend/narrative/typed_continuity.py`：typed v1 contract、引用校验、legacy
  normalization/audit 与 conservative legacy view。
- `backend/agents/narrator_agent.py`：请求/解析 typed ledger，建立 ID catalogs，
  保留 audit，并向既有 Guard 提供兼容视图。
- `backend/agents/orchestrator.py`、`backend/memory/tick_state.py`：原子持久化 typed
  state/audit，旧文件合成 non-authoritative audit。
- `backend/narrative/canonical_projection.py`、
  `backend/narrative/canonical_reconciliation.py`：只消费可安全映射的 legacy
  view；未知 typed reference 不投影。
- `backend/tick_runtime.py`：只允许 `__replay__` 使用隔离 replay data dir。
- `scripts/validate_styles.py`：直接 Narrator 测试路径同步持久化 continuity audit，
  但仍不冒充 full runtime。
- `scripts/replay_runtime_sequence.py`：mock/recorded full-runtime harness、稳定
  evidence hash 与 completed-checkpoint resume。
- `scripts/convert_phase7_guard_replays.py`：Phase 7 loss-aware trace converter。
- `scripts/build_state_guard_calibration.py`：可复现校准集构建。
- `scripts/calibrate_state_guard.py`：coverage-aware confusion/repair/behavior gate。
- `backend/tests/test_runtime_replay.py`、
  `backend/tests/test_phase7_guard_replay_conversion.py`、
  `backend/tests/test_typed_continuity.py`、
  `backend/tests/test_typed_continuity_generation.py`、
  `backend/tests/test_state_guard_calibration_dataset.py`、
  `backend/tests/test_state_guard_calibration_metrics.py`：Phase 8 新回归。
- `backend/tests/test_canonical_projection.py`：typed/unknown projection 安全回归。
- `backend/tests/fixtures/runtime_replay/mock_full_runtime_v1.json`、
  `backend/tests/fixtures/runtime_replay/typed_continuity_overlay_v1.json`、
  `backend/tests/fixtures/state_guard_calibration/manual_cases_v1.json`：最小、脱敏、
  版本化 fixtures。

### Rejected/reverted experiments

- 无已实现后回滚的行为实验。
- Iteration 16 StateGuard 候选在实现前被 calibration gate 拒绝。
- Iteration 17 CanonicalFact consumer 与 real Gate B2 传递性阻断。

### Generated artifacts and records

- `docs/iter/PHASE8_PLAN.md`、`docs/iter/PHASE8_STATUS.md`。
- `docs/iter/iteration-10-runtime-replay-20260721.md` 至
  `docs/iter/iteration-15-failure-taxonomy-20260721.md`。
- `docs/iter/phase8-runtime-replay-mock-20260721.json`。
- `docs/iter/phase8-runtime-replay-recorded-20260721.json`。
- `docs/iter/phase8-runtime-replay-typed-recorded-20260721.json`。
- `docs/iter/phase8-phase7-guard-recorded-v1.json`。
- `docs/iter/state_guard_calibration/phase8-state-guard-calibration-v1.json`。
- `docs/iter/state_guard_calibration/phase8-state-guard-calibration-report-v1.json`。
- `docs/iter/state_guard_calibration/phase8-state-guard-calibration-report-v1.md`。
- 本报告。

不相关的 untracked `scripts/openai_compatible_chat.py` 未读取、未修改、未提交。

## 12. Reproduction（PowerShell）

```powershell
Set-Location E:\pythonproject\novel_auto

# Gate A
python -m pytest backend/tests/test_runtime_replay.py `
  backend/tests/test_phase7_guard_replay_conversion.py `
  backend/tests/test_typed_continuity.py `
  backend/tests/test_typed_continuity_generation.py `
  backend/tests/test_state_guard_calibration_dataset.py `
  backend/tests/test_state_guard_calibration_metrics.py `
  backend/tests/test_canonical_projection.py -q
python -m pytest backend/tests/ -q

# Deterministic full-runtime replay；请使用新的空 work-dir
python scripts/replay_runtime_sequence.py `
  backend/tests/fixtures/runtime_replay/mock_full_runtime_v1.json `
  --mode mock `
  --work-dir .tmp/phase8-replay-mock `
  --out .tmp/phase8-replay-mock.json `
  --max-calls 20

# Recorded replay
python scripts/replay_runtime_sequence.py `
  backend/tests/fixtures/runtime_replay/mock_full_runtime_v1.json `
  --mode recorded `
  --work-dir .tmp/phase8-replay-recorded `
  --out .tmp/phase8-replay-recorded.json `
  --max-calls 20
python scripts/replay_runtime_sequence.py `
  backend/tests/fixtures/runtime_replay/mock_full_runtime_v1.json `
  --mode recorded `
  --work-dir .tmp/phase8-replay-recorded `
  --out .tmp/phase8-replay-recorded.json `
  --max-calls 20 --resume

# 用 pinned Phase 7 输入重新生成转换时，把两个原始 JSON 路径放在 --out 前
python scripts/convert_phase7_guard_replays.py `
  <phase7-run1.json> <phase7-run2.json> `
  --out .tmp/phase8-phase7-guard-recorded-v1.json

# 校准集与指标
python scripts/build_state_guard_calibration.py `
  docs/iter/phase8-phase7-guard-recorded-v1.json `
  backend/tests/fixtures/state_guard_calibration/manual_cases_v1.json `
  --out .tmp/phase8-state-guard-calibration-v1.json
python scripts/calibrate_state_guard.py `
  .tmp/phase8-state-guard-calibration-v1.json `
  --out-json .tmp/phase8-state-guard-calibration-report-v1.json `
  --out-md .tmp/phase8-state-guard-calibration-report-v1.md

# Frontend acceptance
Set-Location frontend
npm run build
Set-Location ..
```

`replay_runtime_sequence.py --help` 当前明确只列出 `{mock,recorded}`。不要把上面
命令改写成 `real` 并假定已支持；真实模式需要一个后续、重新授权且先补足校准
证据的迭代。

## 13. Risks and next recommendation

- **过拟合/证据偏差**：7 个 reject 都是 minimal synthetic，signal-backed decisive
  case 全为 accept；据此调阈值会严重偏向保留正文。
- **Reviewer 偏差**：两次 pass 都是 Codex-assisted，独立人工审查为 0。
- **缺失负载**：36 个 Phase 7 reject 缺完整 draft，40 次 repair 缺完整 repair
  prose，39 个 case 无法可靠裁决。
- **模型泛化**：typed valid 只有 1 个 recorded fixture；真实 provider、不同模型、
  题材、风格、seed 与压力场景均未测。
- **Replay 覆盖**：Critic、real mode、partial multi-Tick resume 未覆盖。
- **成本/性能**：Prompt 增量有字符级数据，但无真实 token/latency 数据；不能判断
  verifier/repair 占比或每千字成本。
- **兼容与迁移**：旧小说读取通过 fail-safe，但未执行生产数据迁移；任何显式
  migration 仍需单独审计、回滚设计与授权。
- **CanonicalFact 风险**：projection/reconciliation 存在不等于消费有效；在 hard
  contradiction recall 可测前不得成为默认上下文。

下一步不是立即改 StateGuard，而是补齐至少 6 个 decisive case 使总数达到 40，
并优先取得带完整 draft、Guard signals 和独立人工裁决的 hard-negative。只有
typed candidate 在同一批案例上获得决策覆盖、真正 endpoint failure 继续被拒绝、
hard contradiction recall 不下降后，才可重新考虑 Iteration 16；随后才是默认关闭
的 StateGuard read-only CanonicalFact 对照实验。

## 14. Final conclusion

**CONDITIONAL PASS：基础设施与测量有效，但 StateGuard 行为或 CanonicalFact 消费仍不足以进入生产默认。**
