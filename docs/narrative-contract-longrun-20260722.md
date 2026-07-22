# Narrative Contract Hardening + Long-Run Validation（2026-07-22）

## 结论

`LONG_RUN_CONDITIONAL_PASS`

正文契约、双层校验、一次 Repair、事务拒绝、恢复和 20 节零 Provider 回放均通过；GLM-5.2 只完成了单组合的多轮 3 节 pilot，完整 Stage 1（45 节）及 Stage 2—4 未执行，因此不能报告 `LONG_RUN_PASS`。真实 pilot 的门禁结果按实际运行保留为未通过；最终别名修正只获得确定性离线重放证据，没有被提升为真实 Provider 通过证据。

## 权威链与实现

本节权威顺序为：

```text
NarrativeContract > StoryBible / CanonicalState > StyleContract
```

`NarrativeContractBuilder` 只使用 StoryBible、CanonicalState、SectionGoal、目标 StoryThread 和结构化用户约束，生成稳定 hash；Writer 看见语义契约，不看服务端正则。`NarrativeContractValidator` 先验证正文，`StoryValidator` 再验证 StateDelta/Thread；任一层失败都只允许一次最小正文 Repair，随后两层全部重跑。Repair 仍失败时事务进入 `rejected`，不能 stage 或 commit。

## 修改文件

- 后端领域与事务：`backend/story/narrative_contract.py`、`narrative_validator.py`、`models.py`、`context_builder.py`、`service.py`、`validator.py`、`writer.py`、`persistence.py`、`simulation_gateway.py`。
- API：`backend/api/story_routes.py`，新增契约预览、脱敏事务层和长程状态聚合。
- 后端测试：`narrative_contract_fixtures.py`、`test_narrative_contract.py`、`test_narrative_contract_validator.py`、`test_narrative_contract_generation.py`、`test_author_longrange_recorded.py`，并扩展 `test_author_generation_service.py`、`test_simulation_gateway.py`、`test_story_api.py`。
- 前端：`frontend/src/dashboard/views/AuthorStudioView.jsx`、`styles/author.css`、`services/api.js`、`frontend/tests/author-ui.test.mjs`。
- 验证脚本：`scripts/run_author_longrange.py`、`analyze_author_longrange.py`、`compare_author_longrange.py`，并同步 `smoke_author_mode.py` 的 11 槽断言。
- 文档：`README.md`、`CHANGELOG.md`、`docs/author-mode-architecture.md` 与本报告。

## 里程碑记录

| 里程碑 | 修改/发现 | 验证与 token | 进入下一阶段 |
| --- | --- | --- | --- |
| M0 | 基线与 author 主链审计；基线 SHA `00cc9256c16ab5b705d32ba1c46f28a37152812e` | 基线后端 43 passed；前端 11 passed；0 token | 是 |
| M1 | NarrativeContract 模型、确定性 builder、11 槽上下文 | 模型/builder 单测；0 token | 是 |
| M2 | 独立正文 Validator、统一长度、实体/事实/事件/结局/时间/新增事实码 | 人工正负例与不可变样本；0 token | 是 |
| M3 | 双层校验、一次 Repair、两层重跑、stage 防绕过、候选历史与 repair token | 事务/拒绝/恢复测试；0 token | 是 |
| M4 | 契约预览、正文/权威状态/风格分层、预算与长程状态 | 前端测试与 build；0 token | 是 |
| M5 | 五份真实正文按 SHA-256 冻结为 fixture | 五份全部准确拦截；0 token | 是 |
| M6 | 20 节 Recorded Writer、checkpoint、resume、重启恢复、stale recovery、分析/对比 | `STAGE0_PASS`；0 provider token | 是 |
| M7 | GLM-5.2 单组合 4 轮 × 3 节诊断 pilot | 63,146 total tokens；未达到 Stage 1 gate | 否 |
| M8—M10 | Stage 2/3 与第二轮长程修正 | 未执行；0 token | 否 |
| M11 | 静态检查、全量测试、前端构建与证据分级 | Ruff passed；后端 1429 passed；前端 14 passed；Vite build passed | 条件通过 |

## 五份真实样本回归

原文从 `docs/iter/style-generation-samples-glm52-20260722.json` 原样读取，并用固定 SHA-256 防止测试中被改写。

| 风格 | 预期问题 | Validator 实际违规码 | 拦截 | Repair / 风格影响 |
| --- | --- | --- | --- | --- |
| literary | 错误持信者、未实际交信 | `REQUIRED_FACT_MISSING`、`REQUIRED_EVENT_MISSING`、`END_STATE_WRONG_HOLDER`、`UNSUPPORTED_KINSHIP_ADDED`、`NARRATIVE_RELATION_ADDED`、`UNSUPPORTED_DATE_ADDED` | 是 | fixture 只做不可变回放，未调用 Repair；未改原文，故无风格损伤结论 |
| noir_cold | 天亮前改为下周、因果削弱 | `TIME_CONSTRAINT_MUTATED`、`CAUSAL_LINK_WEAKENED`、`NARRATIVE_TOO_SHORT` | 是 | 同上 |
| hot_blooded | 伤亡、亲属、背景、伤势、关系 | `UNSUPPORTED_CASUALTY_ADDED`、`UNSUPPORTED_KINSHIP_ADDED`、`UNSUPPORTED_BACKSTORY_ADDED`、`UNSUPPORTED_INJURY_ADDED`、`NARRATIVE_RELATION_ADDED`，另有 number/date | 是 | 同上 |
| warm_healing | 门外新增第二人 | `NARRATIVE_CHARACTER_ADDED`，另有必要事实遗漏 | 是 | 同上 |
| classical_chapter | 亲属、日期、组织、烧信选项、未交信、过短 | `UNSUPPORTED_KINSHIP_ADDED`、`UNSUPPORTED_DATE_ADDED`、`UNSUPPORTED_ORGANIZATION_ADDED`、`NARRATIVE_ORGANIZATION_ADDED`、`FORBIDDEN_OUTCOME_MENTIONED`、`REQUIRED_EVENT_INCOMPLETE/MISSING`、`END_STATE_NOT_REACHED`、`NARRATIVE_TOO_SHORT` | 是 | 同上 |

## Stage 结果

| Stage | 状态 | 实际证据 |
| --- | --- | --- |
| Stage 0 | `PASS` | 20/20 committed；contract 100%；Repair 5/5 成功；3 次 runtime rebuild；clean recovery 与 stale rejection 均通过；五份真实样本全部拒绝 |
| Stage 1 | `NOT_COMPLETED / GATE NOT MET` | 仅 literary × reality_mystery × 3 节 pilot；没有执行 3×5×3=45 节矩阵。四轮诊断真实运行分别提交 0/3、1/3、2/3、2/3 |
| Stage 2 | `NOT_RUN` | Stage 1 未通过，未启动 120 节 |
| Stage 3 | `NOT_RUN` | 前置 gate 未通过，未启动 300 节 |
| Stage 4 | `NOT_RUN` | 前置 gate 未通过，未启动 200—300 节 |

真实 pilot 暴露并修复了三个测试契约问题：证据误要求逐字出现“完成第 N 次交接”；连续章节重复要求已完成的交接；`旧信` 未声明 `信纸/信封/封套/油纸封` 别名。最终代码对 v4 三篇原文的离线重放为 3/3 accepted，但这只是 deterministic recorded evidence，不是新的 real-provider run。

## 长程指标

| 指标 | Stage 0（最终） | 最新真实 pilot v4 |
| --- | ---: | ---: |
| attempted / committed | 20 / 20 | 3 / 2 |
| contract pass | 100% | 66.67% |
| Repair rate / success | 25% / 100% | 33.33% / 0%（该次 Repair 仍拒绝） |
| hard reject / state conflict | 0 / 0 | 1 / 0 |
| Canonical revision | 1 → 21，连续 | 正式提交后到 3，连续 |
| max active StoryThread | 0 | 0 |
| final memory records | 20 | 4 |
| style contract | Fake Writer 不代表风格；检测为 false | 3/3 检测为 true，但事实失败不能算整体通过 |
| mean consecutive 4-gram overlap | 0.9117（Fake Writer 故意高度重复） | 0.0263 |
| token | 0 | 14,555（prompt 11,811；completion 2,744；其中 repair 1,094） |
| mean latency | 0.1636s | 23.181s |
| Provider errors | 0 | 0 |
| runtime rebuild / recovery | 3；staged recovery 1/1；stale 1/1 | 2 rebuild；无 staged crash 注入 |

四轮真实诊断合计 12 次尝试、5 次提交、7 次硬拒绝、63,146 tokens（prompt 50,818；completion 12,328；可独立归因的 repair 5,315；v1 在字段加入前未单列 repair token）。未配置价格费率，因此不伪造成本数字。

## 样本

录制开头：

> 暴雨后的旧灯塔仍带着潮湿盐味。沈砚先核对旧信上的既有记录……沈砚把旧信交给林秋，林秋接过旧信，并把它放进桌上的防潮袋。

录制中段/后段分别明确“林秋核对旧信第 10 处记录并继续保管”和“第 20 处记录并继续保管”；Canonical revision 同步为 11 和 21。

Repair 前：

> 沈砚仍把旧信藏在怀里，并说父亲会替他们处理。

命中 `UNSUPPORTED_KINSHIP_ADDED`、`NARRATIVE_RELATION_ADDED`、`NARRATIVE_TOO_SHORT`。Repair 后删除亲属与错误持信事实，补足既定核对事件和长度；正文/状态两层均通过。

最严重真实失败（v4 第一节）实质完成了交接，但把物品称为“油纸封/封套”，最终又明确“那封旧信”。运行时被旧别名表误拒；最终代码已将该 299 字原文及 SHA-256 `ecb082e8…e65945` 固化为回归，确定性重放通过。没有把该离线结果冒充真实重跑。

## 证据边界与限制

- deterministic：模型、Validator、事务、API、前端、runner/analyzer 单测与静态检查。
- recorded：20 节 Fake/Recorded Writer、五份历史真实原文、v4 失败原文离线回放。
- real provider：GLM-5.2 四轮 3 节诊断 pilot；最后一轮实际 gate 未通过。
- human review：未执行。
- LLM judge：未执行；Writer 没有自评，确定性结果没有被 Judge 覆盖。

已知限制：命名人物检测只覆盖显式引介等保守模式；中文开放域实体识别仍不等价于 NER。完整 Stage 1—4、50/100/200 节记忆召回抽样、两名盲审和独立 Judge 均待后续有明确预算时执行。受此限制，本轮只能是 `LONG_RUN_CONDITIONAL_PASS`。

## 复现

```powershell
python scripts/run_author_longrange.py --mode recorded --max-sections 20 --checkpoint-every 5 --desired-length 400 --seed 20260722 --theme reality_mystery --style literary --output-dir .tmp/narrative-contract-stage0
python scripts/analyze_author_longrange.py .tmp/narrative-contract-stage0/report.json
python scripts/compare_author_longrange.py first/analysis.json second/analysis.json --out-md comparison.md
```

真实模式额外要求 `--provider-file`，凭据只进入进程环境，不写报告。runner 支持 `--resume --checkpoint-every --max-sections --max-total-tokens --max-cost --provider --model --theme --style --seed --output-dir`。
