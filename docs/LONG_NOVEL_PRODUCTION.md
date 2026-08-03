# 长篇小说生产模式

本项目的默认产品路径是作者生产模式。九 Agent Tick 世界模拟继续保留在
“实验室”中，但不会参与默认建书、整书大纲或长篇生产。

架构不变量见 [最终产品架构](./FINAL_ARCHITECTURE.md)；本文聚焦日常操作。字段级接口见
[API 参考](./API.md)。

## 权威顺序

每一次正式生成都遵守以下权威顺序，后位数据不得覆盖前位数据：

1. `NarrativeContract`
2. `StoryBible`
3. `CanonicalState`
4. `StoryThreadRepository`
5. `MemoryRepository`
6. `StyleProfile`

`StoryBible` 是整书创作契约，`CanonicalState` 是唯一当前事实源。
`MemoryRepository` 只参与检索，不能把未经验证的回忆直接提升为事实。
`StyleProfile` 只控制表达方式，不能改变人物、事实、事件、终态、故事线状态或
长度门槛。

正式稿只读取 `committed` transaction。`prepared`、`validated`、`committing`、
`rejected` 和 `failed` transaction 中的候选正文都不会进入章节阅读或导出。

## 整书对象

每部作者模式作品在自己的数据目录中维护以下版本化对象：

- `production_spec.json`：书名、题材、主题、核心问题、篇幅、卷章数量、章/节长度、
  结局方向、语言和活动风格。
- `book_outline.json`：整书弧线、卷目标、章节目标、必需事件、必需终态、故事线和
  人物弧调度。
- `style_profiles.json`：只读内置 preset 与用户自定义风格档案。
- `active_style.json`：下一未生成章节使用的风格版本。
- `production_migration.json`：幂等整书域迁移收据。
- `generation_jobs/`：持久化整书生产任务。
- `production_attempts/`：每次分节尝试的持久化 journal。
- `production_events/`：可重放的生产事件。
- `production_chapters/`：章节工作/提交记录；API 只公开完整 committed 章节。

所有 schema 都带版本号。revision 更新使用乐观并发控制；客户端使用旧 revision
保存时返回 HTTP 409，不会覆盖更新后的权威文件。

“字数”统一指正文中的非空白字符数。前端进度、章节长度校验和导出统计使用同一口径。

## 大纲生成

整书大纲首次生成最多调用一次结构化 Provider。输出必须通过严格 schema、卷章编号、
卷归属、目标字数预算和目标闭合校验。第一次输出不合法时最多允许一次结构化修复。

章节生产循环不会再次调用大纲 Planner。用户可以在未提交章节上编辑大纲；已提交章节
的顺序和权威目标不会被静默改写。

## 章节生产

同一本作品只允许一个活动生产任务，章节和分节严格串行：

```text
冻结 ProductionSpec / Outline / StyleProfile revision
  → 冻结 StoryBible / Canon / Thread / Memory revision
  → 构建 NarrativeContract 和确定性执行计划
  → 单次 Writer 初稿
  → Narrative / State / Length / Style Validators
  → 至多一次受限局部 Patch Repair
  → 完整重新验证
  → RevisionGuard
  → Journaled Atomic Commit
  → 更新章节、任务和检索记忆
```

每节最多一次初稿 Writer、一次局部 Repair，默认没有全文 Writer retry，也没有章节
Planner。Patch anchor 不存在、revision 漂移或完整重验失败时拒绝候选，不进行模糊插入。

初稿 Provider 契约精确使用十个非空白连续正文微块：`opening_1/2`、
`development_1/2/3`、`conflict_1/2/3`、`resolution_1/2`。各块配额是软目标；服务端仅按
固定顺序连接，聚合后的非空白字符总数必须硬性落在 900–1100，落盘模型仍是原有
`WriterCandidate`。

长度缺口较大时，一次局部 Repair 可返回多个冻结 ID、anchor 和 placement 的微扩写块。
每块必须非空、不得超过绝对上限并通过 authority/safety 审计，单块目标是软引导；整组补文
的冻结总下限/上限和应用后 900–1100 的最终正文才是硬长度权限。任何块或聚合结果失败都会
使整组原子拒绝并保持原候选不变，不会通过复制、填充、截断、重分配或第三次调用制造通过。

每个 transaction 冻结完整风格 snapshot、prompt hash、StoryBible/Canon/Outline
revision 和本节 NarrativeContract。修改活动风格只影响下一未生成章节；已提交章节的
正文和证据保持不变。

## 暂停、恢复、取消与重试

- 暂停不会中断正在进行的原子提交。当前安全边界完成后任务进入 `paused`，且不启动
  下一节。
- 恢复重新检查 StoryBible、Canon、Outline、ProductionSpec 和 StyleProfile
  revision；陈旧任务 fail closed。
- `validated` 或 `committing` journal 可以恢复。恢复不会重复 section ID、
  transaction ID、Canon revision、Thread 推进或 Memory 写入。
- 取消在安全边界生效，保留此前已提交章节。
- 重试失败章节创建新的 request attempt ID 和 transaction，不覆盖旧失败证据。
- 服务重启后，持久化任务和 journal 可重新装载；缺少有效 Provider 配置时任务保持
  可恢复状态，不会提交半成品。

## 自定义风格

用户可以复制内置 preset 或新建 `StyleProfile`，设置叙述声音、视角、时态、句长、
段落密度、对话/描写比例、节奏、情绪、幽默、意象、词汇、开头/结尾偏好以及必须遵守/
避免规则。

可选样文只用于提取风格特征，不作为可复制句库。保存时会生成稳定 prompt hash。
预览不会修改 Canon、Thread、Memory 或正式章节。应用动作明确指向“下一未生成章节”。

字段、复制、revision、样文派生和激活规则见
[自定义风格档案](./CUSTOM_STYLE_PROFILES.md)。

## API

作者模式整书接口都要求应用登录：

| 接口 | 作用 |
| --- | --- |
| `GET/PUT /api/novels/{novel_id}/production-spec` | 读取或按 revision 更新整书规格 |
| `POST /api/novels/{novel_id}/outline/generate` | 一次性生成并校验整书大纲 |
| `GET/PUT /api/novels/{novel_id}/outline` | 读取或按 revision 更新大纲 |
| `GET/POST /api/novels/{novel_id}/style-profiles` | 列出或创建/复制版本化风格 |
| `PUT/DELETE /api/novels/{novel_id}/style-profiles/{style_id}` | 按 revision 更新或删除用户风格 |
| `POST /api/novels/{novel_id}/style-profiles/{style_id}/activate` | 从下一未开始章节激活风格 snapshot |
| `POST /api/novels/{novel_id}/style-profiles/{style_id}/preview` | 生成不提交的风格预览 |
| `POST /api/novels/{novel_id}/production/start` | 创建唯一活动生产任务 |
| `POST /api/novels/{novel_id}/production/pause` | 在安全边界暂停 |
| `POST /api/novels/{novel_id}/production/resume` | 幂等恢复 |
| `POST /api/novels/{novel_id}/production/cancel` | 在安全边界取消 |
| `POST /api/novels/{novel_id}/production/retry-failed` | 以新 attempt 重试失败章节 |
| `GET /api/novels/{novel_id}/production/status` | 获取任务、进度和脱敏 failure 状态 |
| `GET /api/novels/{novel_id}/production/events` | 订阅/读取生产事件 |
| `GET /api/novels/{novel_id}/chapters` | 列出正式提交章节 |
| `GET /api/novels/{novel_id}/chapters/{chapter_id}` | 阅读单个正式提交章节 |
| `GET /api/novels/{novel_id}/exports/manuscript` | 下载 committed-only Markdown |
| `GET /api/novels/{novel_id}/exports/evidence` | 下载 allowlisted JSON 证据 |

生产事件至少覆盖 job/chapter/section start、validation、repair、section/chapter
commit、paused、failed 和 completed。

## 旧作品迁移

旧作品第一次访问作者生产接口时执行幂等迁移：

1. 保留原 `story_bible.json`、Canon、Thread、Memory、transaction 和
   `tick_sections.jsonl` 正式正文。
2. 创建默认 `NovelProductionSpec`、draft `BookOutline` 和只读基础风格档案。
3. simulation 数据继续只读兼容，不自动升级为 Canon。
4. 临时文件经 flush、fsync 后原子 replace；关键文件保留 last-good。
5. 损坏文件隔离后 fail closed，不用默认内容直接覆盖损坏证据。

回滚只切换应用版本，不删除新作者域文件或 journal。旧运行时可以忽略不认识的新
schema；需要写入时应先复制完整作品目录并完成 committed-only 导出比对。

## 操作流程

1. 在五步向导中填写故事、篇幅、风格和 Provider，并测试连接。
2. 创建作者模式作品并生成整书大纲。
3. 检查/编辑未提交章节目标，保存最新 revision。
4. 在生产中心开始任务。
5. 需要时暂停、恢复、取消或重试失败章节。
6. 在章节页面阅读 committed 内容，在导出页生成 committed-only manuscript。

Provider 认证失败不会退出应用登录。修复 Provider 配置并重新 probe 后，可直接恢复
暂停的整书任务。

Provider 配置来源、浏览器会话/设备模式和真实验收用只读文件规则见
[Provider 生命周期](./PROVIDER_RUNTIME_LIFECYCLE.md)。迁移和部署回滚见
[迁移与回滚](./FINAL_MIGRATION_ROLLBACK.md)。
