# Changelog

本文件记录面向使用者和部署者的发布级变化，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

逐轮实验、评测数据与回滚理由不再重复堆叠在根 Changelog；请查阅 [docs/iter/ITERATION_LOG.md](./docs/iter/ITERATION_LOG.md) 和 [docs/iter/INDEX.md](./docs/iter/INDEX.md)。历史全文仍可从 Git 历史获取。

## [Unreleased] — 2026-07-22

### Added

- 新增确定性 `NarrativeContract` 与独立正文校验层，覆盖允许实体、必要事实/事件/最终状态、时间与因果、禁止新增、关系保护和统一中文长度边界；Writer 风格明确服从事实契约。
- 新增可恢复长程验证 runner/analyzer/comparator、五份真实风格原文不可变回归、Repair 前后候选历史、独立 repair token 统计，以及 Author Studio 契约预览和分层验证诊断。
- 新增 author 权威链加固：bootstrap 前逐字持久化 seed 与字段 provenance、StateDelta 逐操作证据/类型闸、StoryBible stale-context 提交与恢复保护、故事线有限合并、Context 全局硬预算，以及 11 项前端真实交互测试。
- 新增 `scripts/smoke_author_mode_recorded.py`，以零 Provider 调用录制验证 seed、旧事务拦截、缺证据 delta、runtime 重建和长期记忆复用的十步链路。
- 新增默认作者模式：`StoryBible` 作为最高创作契约，`CanonicalState` 作为唯一当前事实，结合类型化长期记忆与故事线生命周期构建固定十槽上下文。
- 新增单 Writer → 确定性 Validator → 至多一次定向修复 → journaled commit 主链，并提供故障恢复、损坏隔离、last-good 备份和修订号冲突保护。
- 新增作者模式 REST API、编辑工作台、创作圣经/规范状态/故事线视图、上下文清单，以及旧 Tick/事实账本/记忆/摘要数据的幂等只读迁移。
- 新增 `scripts/smoke_author_mode.py`，用于以环境变量凭据验证真实 OpenAI 兼容 provider 的多节生成与重启恢复。
- 新增长篇 `NarrativeStateGuard`：在叙事落盘前检查事实、角色、位置、关系、物品和开放伏笔等状态变化。
- 新增风格契约快照、版本和 prompt hash，使长程生成可以持续验证 preset 是否发生漂移。
- 新增 `SectionEditor` 与确定性接缝指标，在节合并时去除事件重放、突兀跳切和段首重复，并对编辑稿再次执行事实复验。
- 新增 `scripts/validate_styles.py`，支持 compatible/pressure 双场景、确定性验收、可选 LLM judge、单次定向修订、原子 checkpoint 与 `--resume`。
- 新增 `quality_metrics/style_contract.py` 与 `quality_metrics/section_seams.py`。
- 新增根目录 `update-docker.bat`，用于 Windows 上重建现有 Docker Compose 部署并等待健康检查。

### Changed

- Author 模式风格 preset 统一写入 `StoryBible.style_contract` 并提升 revision；TickState style anchors 仅保留为 simulation 运行数据。
- Repair 仅修改正文，之后以修复正文重新验证原候选的每条 StateDelta；缺失或不可定位 evidence 的变化永不进入 CanonicalState。
- 作品默认不再实例化九 Agent Tick runtime；世界模拟改为显式开启、延迟加载的实验模式，其产出仍必须通过统一 Validator 与 CanonicalState 事务网关。
- 知识图谱在作者模式中降级为只读派生视图；旧章节生成、Tick 与 Agent API 不得隐式拉起模拟 runtime。
- 前端默认导航改为章节创作、创作圣经、规范状态和故事线，Tick、Agent 与知识图谱移入高级/实验入口。
- Narrator 增加稳定 prefix、风格严格 Tick、生成温度上限和长程上下文处理。
- 章节生成接入风格契约与角色声纹，风格 preset 支持运行时切换和锚点重生成。
- README 重组为架构、快速开始、配置、验证、Docker 更新和安全入口。
- 根 Changelog 从逐 iteration 流水账改为发布级摘要。

### Removed

- `CLAUDE.md` 与 `structure.md` 不再由 Git 跟踪；本地副本继续保留。

## [2.49] — 2026-06-25

### Added

- Phase 6-B Reader：连读模式、视点 sidecar、分页、键盘导航、状态栏、全文搜索、高亮与搜索历史。
- Phase 6-C 确定性质量层扩展到 13/16 个维度，包括章末悬念、重复短语、形容词堆砌、单感官、对仗工整和世界观倾倒。
- 新增长程漂移分析、跨 benchmark 对比、批量主题运行、配额探针和 narrative grep 工具。

### Changed

- 500 Tick 长程验证完成：完整运行达到 500/500，确认此前异常来自 provider 配额或随机性，而非系统性 drift。
- Narrator、critic 和 UI 增加持续高潮防护：滚动强度守卫、超长正文强制 critic、强度提示与 D7 cascade 检测。
- provider catalog 扩展为 23 个 OpenAI 兼容提供商。

### Fixed

- Goal schema 容错处理优先级、百分比、数字 ID 和字段别名，消除一批 LLM 输出导致的目标跳过。
- critic skip 决策、reader API、长程 analyzer schema 和 lazy ChromaDB 导入问题。

## [2.44] — 2026-06-17

### Added

- Phase 5-A：Narrator prompt cache 重排，动态风格锚点移到 user prompt，保持 system prompt 稳定。
- Phase 5-B：WorldSimulator 对低价值稳态 Tick 执行确定性短路。
- Phase 5-C/D/E：21 个题材、16 个风格 preset，矩阵 benchmark、按题材推荐与不推荐组合。
- 跨 seed 长程 verdict 聚合器、pairwise judge runbook 和前端 preset 推荐展示。

### Changed

- 三题材长程压力测试全部通过；跨 seed stale-skip 保持稳定。
- 补齐气氛类 preset 的最低人物存在度约束，消除矩阵中低于 3 分的组合。

## [2.43] — 2026-06-14

### Added

- Showrunner 动态 active-cast cap 与角色 sideline 生命周期，包含 TTL、立即释放和异常 payload 防护。

### Changed

- 跨题材验证确认动态 sideline 相比固定 cast 限制更稳，作为 Phase 4 正式方案落地。
- critic 输出预算实验在跨 seed 出现边缘退化后回滚到 1500，保持质量优先。

## [2.42] — 2026-06-13

- 收档 Phase 3 并同步 Phase 4 计划。
- 回滚固定 `cast=3` 默认值；该设置仅保留为 benchmark CLI opt-in，避免对群像题材造成质量回归。

## [2.41] — 2026-06-13

- 完成角色数量实验、smoke 和多轮 review。
- 验证固定少角色配置存在题材依赖，明确需要跨 seed、跨题材 gate 后才能修改生产默认值。

## [2.40] — 2026-06-12

- 新增 prose diversity 指标、cast sweep 参数与多 seed benchmark。
- 回滚 narrator 摘要窗口和固定 cast 等未能稳定泛化的实验性默认值。

## [2.39] — 2026-06-12

### Added

- Showrunner 自动关闭已解决的 open loop，并增加 open-loop 去重 gate。

### Changed

- 三 seed pairwise 验证平均胜率 73.3%，解决长期 `closed=0` 泄漏问题。

## [2.38] — 2026-06-11

### Changed

- 完成 cost-quality loop：相对基线总 token 降低约 77%，平均 Tick 时延降低约 83%，并保留质量 gate。
- 对 critic、WorldSimulator、Narrator、CharacterAgent、bootstrap、Showrunner 和记忆压缩器重新分配 prompt 与输出预算。
- 引入 delta output、短正文 gate、critic 轮次上限、紧凑 JSON 和按优先级选择上下文。

### Fixed

- 加固 reasoning 泄漏、schema 占位符污染、`world_time=0`、环境变量冻结和异常 LLM payload 等问题。

## [2.37] — 2026-06-10

- 重写 Narrator 场景简报：原始台词、私密动机、角色名片、世界状态和 `prose_tail` 连贯衔接。
- CharacterAgent 增加行动历史和台词声纹；bootstrap 增加对白锚点。
- 完成全项目审查并修复 ConsistencyGuardian 静默失效、伏笔压缩、任务越权、CORS 和多租户 token 记账等问题。
- 前端落地“墨砚”阅读设计系统。

## [2.34] — 2026-06-09

- 新增 Tick 末尾知识图谱同步与磁盘持久化。
- 统一 agent/bootstrap 的 LLM JSON 解析与 `json_repair` 兜底。
- 修复 WorldSimulator 稳态字段被清空、SectionCloser reasoning 泄漏和空世界启动等问题。

## [2.33] — 2026-06-08

- 新增中文文本分段、Edge TTS、图片/音频资产管理和 FFmpeg 视频合成。
- 前端加入多模态工作区，后端新增对应任务与 REST API。

## [2.28–2.32] — 2026-06-08

- 新增讯飞和 DashScope 图像生成、用户级 LLM Header 透传及客户端缓存。
- 中间件改为纯 ASGI，修复 502 时 CORS 响应头丢失。
- 前端移除固定轮询，改为可见性与用户操作驱动刷新。
- Docker 网络增加稳定 DNS 和 MTU 1380 配置。

## [2.24–2.27] — 2026-06-05 至 2026-06-08

- 引入 SectionCloser、后台任务队列、SSE、per-novel TickRuntime 和节存储。
- 世界冷启动任务化，并支持链式生成首节。
- 新增邮箱 OTP/JWT、可选密码、多租户目录隔离和随机种子/标题。
- 配置界面升级为多 provider schema，LLM 凭据改为用户侧配置。

## [2.20–2.23] — 2026-06-04 至 2026-06-05

- 补齐 Tick 诊断、事件注入、OpenLoop CRUD 和知识图谱编辑界面。
- 加固 TickState/SummaryTree 原子写与损坏隔离、TickDB 幂等写和小说切换流程。
- 完成节级管线的题材锚定、独立标题生成和 API 收敛。
- 增加 Windows Docker Desktop、Linux systemd、Cloudflare Tunnel 与独立前端部署方案。

## [2.1–2.19] — 2026-06-02 至 2026-06-04

- 完成多智能体 Tick 架构、角色视野约束、行动冲突解析、事件流和 Narrator 选择性叙述。
- 新增事实账本、角色弧线、创造力评分、读者分支、TokenBudget、安全过滤和模型降级闭环。
- 引入分层记忆、知识图谱、SQLite WAL、摘要树、ConsistencyGuardian 和 NoveltyCritic。
- v1.x 章节式单体生成器整体迁移到只读 `old/` 归档。

## [2.0.0] — 2026-06-02

- 建立 FastAPI + React/Vite 单栈应用和新版数据目录。
- 以 Tick 驱动的世界模拟取代章节驱动的单体生成链路。

## [1.x] — 2026 年以前

- 早期章节驱动生成器，现仅保留在 `old/` 供历史参考，不参与运行时。
