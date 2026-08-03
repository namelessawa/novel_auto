# 无限小说生成系统

这是一个 FastAPI + React/Vite 的长篇小说生产系统。默认产品路径是可恢复的整书
Author production：先建立整书规格与大纲，再由单一 Writer 按章、按节串行生成，经过
确定性校验和事务提交后才成为正式稿。

九 Agent / 七阶段 Tick 世界模拟仍保留在“实验室”中，但不参与默认建书、整书大纲或
长篇生产，也不能绕过 Author 的校验与 Canon 提交边界。

## 产品原则

- `StoryBible` 约束全书不可越界的设定、人物与创作方向。
- `CanonicalState` 是唯一当前事实源。
- 每节 `NarrativeContract` 冻结必须发生的事件、终态、禁区和长度范围。
- `StoryThreadRepository` 管理有证据的叙事义务；`MemoryRepository` 只提供检索，
  都不是第二套事实源。
- `StyleProfile` 只控制表达。它不能改变事实、人物、事件、终态、长度门槛或故事线状态。
- 正式阅读和导出只包含 `committed` 章节；失败、拒绝或提交中的候选正文不会进入正式稿。

完整架构见 [最终架构](./docs/FINAL_ARCHITECTURE.md)。

## 快速开始

### 环境

- Python 3.11+
- Node.js 18+
- npm

### 安装与启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
npm --prefix frontend install

# 终端一：后端
python run.py --reload

# 终端二：前端
npm --prefix frontend run dev
```

- 前端：<http://127.0.0.1:3143/>
- 后端：<http://127.0.0.1:8762/>
- OpenAPI：<http://127.0.0.1:8762/docs>

Provider 凭据不需要写入仓库文件。用户可以在界面中选择：

- 仅保存在当前浏览器会话；
- 保存在当前设备的浏览器存储；
- 不发送浏览器凭据，使用运维方已注入的服务端运行时。

完整 key、Authorization 和完整 Provider Base URL 不会由服务端回显，也不会进入报告、
日志、证据产物或 Git。服务端运行时的部署方式由运维环境或秘密管理系统决定。
真实验收例外地要求显式传入原始 `coding.txt` 的只读路径；该文件只在进程内解析，普通
浏览器产品流不会读取它。
[Provider 生命周期](./docs/PROVIDER_RUNTIME_LIFECYCLE.md) 说明了配置优先级和安全边界。

## 五步建书

新建作品向导固定为五步，默认创建 Author production 项目：

1. **故事**：标题、原始 seed、题材、主题、核心问题和结局方向。
2. **篇幅**：总字数、卷数、章数、章节允许范围和分节目标。
3. **风格**：选择内置 preset，或建立自定义 `StyleProfile`。
4. **模型**：从后端 catalog 选择 Provider；可测试浏览器配置或服务端 fallback。
5. **确认**：保存 `StoryBible`、`NovelProductionSpec` 与风格绑定，再生成整书大纲。

大纲达到 `ready` 或 `locked` 后，生产中心才允许启动整书任务。

## 生产操作

- **开始**：同一本作品只创建一个活动 Job，章节和分节严格串行。
- **暂停**：当前安全边界完成后进入 `paused`，不启动下一节。
- **恢复**：重新检查冻结的 Bible、Canon、Outline、Spec 和 Style revision。
- **取消**：在安全边界停止，保留此前已经提交的章节。
- **重试失败章节**：只对 `failed` Job 开放，创建新的 attempt 和 transaction，保留旧证据。
- **事件流**：SSE 按 Job ID 推送章节、分节、校验、修复、提交和终态事件。
- **导出**：manuscript 只含正式正文；evidence 只含允许公开的 revision、hash 和收据。

崩溃后，启动钩子会从 Job、attempt 与 Author transaction journal 恢复。恢复是幂等的，
不会重复创建 section、推进 Canon/Thread revision 或写入 Memory。操作细节见
[长篇生产手册](./docs/LONG_NOVEL_PRODUCTION.md)。

## 自定义风格

内置 preset 为只读。用户可以复制 preset 或创建自定义风格，并通过 revision guard 更新。
可选样文只用于派生风格特征，原句不会进入 Writer prompt；稳定 `prompt_hash` 绑定实际的
表达契约。激活风格只影响下一未开始章节，已开始或已提交章节继续使用冻结 snapshot。

详见 [自定义风格档案](./docs/CUSTOM_STYLE_PROFILES.md)。

## 权威数据

每部作品的数据目录包含：

- `story_bible.json`
- `canonical_state.json`
- `story_threads.json`
- `memory_records.json`
- `generation_mode.json`
- `context_manifest.json`
- `tick_sections.jsonl`
- `production_spec.json`
- `book_outline.json`
- `style_profiles.json`
- `active_style.json`
- `production_migration.json`
- `generation_transactions/`
- `generation_jobs/`
- `production_attempts/`
- `production_events/`
- `production_chapters/`

关键 JSON 使用临时文件、flush、`fsync` 和原子替换，并保留 last-good 备份；无法安全解析的
文件会被隔离且 fail closed。旧 Tick、fact ledger、summary 与 memory 文件保留为低权威
迁移输入，不会自动升级为 Canon。参见
[迁移与回滚](./docs/FINAL_MIGRATION_ROLLBACK.md)。

## API

主要接口包括：

- 整书规格与大纲 CRUD / 生成；
- StyleProfile CRUD、复制、预览与激活；
- Job 启动、暂停、恢复、取消、失败章节重试、状态和 SSE；
- committed-only 章节读取；
- manuscript / evidence 导出；
- Provider catalog、runtime 与最小 probe；
- StoryBible、Canon、Threads、Memory 与恢复诊断。

完整路径、请求字段和错误码见 [API 参考](./docs/API.md)。运行时 schema 以 FastAPI
`/docs` 为准。

## 离线验证

任何真实 Provider 调用前，都必须对当前源码完整执行：

```powershell
python -m pytest backend/tests/ -q -W error
python -m ruff check backend scripts core
python -m compileall -q backend scripts core
npm --prefix frontend run test:author
npm --prefix frontend run build
npm --prefix frontend audit --omit=dev
git diff --check
python scripts/smoke_author_mode_recorded.py
$RecordedOutput = ".tmp\recorded-long-preflight-" + (Get-Date -Format "yyyyMMdd-HHmmss")
python scripts/smoke_long_novel_recorded.py `
  --output-dir $RecordedOutput `
  --chapters 30 `
  --sections-per-chapter 2
```

随后还必须完成 exact secret scan、generic secret scan 和未跟踪敏感文件检查。任一项失败
都要修复后从完整离线 Gate 重新开始，不能进入真实调用。

这些单独命令适合开发预检；正式周期由
`scripts/run_final_long_novel_acceptance.py` 在独占 staging 中重新执行并落 receipt，不能把
手工输出当作最终 PASS。

## 最终验收状态

README 不缓存某次历史运行的 PASS/FAIL。当前候选是否完成，只由全新、独占 evidence
目录中的 `report.json`、`report.md`、`manifest.json`、`artifact-sha256.json` 与
`recovery.md` 决定。没有这组新报告，或任一硬 Gate 非绿色，都不能宣称最终通过。

严格顺序是：完整离线 Gate（含 recorded 30×2 长程验收）→ 新最小 probe → 新 G1 →
新 G2 → 真实 Provider 产品 smoke → final。统一 runner、命令、阈值和判定规则见
[最终验收](./docs/FINAL_ACCEPTANCE.md)。

## 项目导航

| 路径 | 内容 |
| --- | --- |
| `backend/story/` | Author 权威模型、事务、整书编排、持久化与恢复 |
| `backend/nf_core/` | Provider runtime、LLM 客户端和通用核心 |
| `backend/api/` | FastAPI 路由 |
| `backend/agents/` | 实验性多 Agent simulation |
| `frontend/src/` | React 产品界面 |
| `scripts/` | 离线 smoke、真实 Gate 与诊断工具 |
| `docs/` | 架构、API、运行手册和验收说明 |
| `docs/iter/` | 历史实验记录；不代表当前最终 verdict |
| `old/` | 只读归档，不参与运行时 |

Docker 部署另见 [部署说明](./deploy/docker/README.md)。
