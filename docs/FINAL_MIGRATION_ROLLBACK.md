# 迁移与回滚

本文适用于从旧作品数据或旧应用版本迁移到当前整书 Author production。迁移是幂等、
非破坏性的；回滚是部署级切换，不删除新格式权威文件。本文不保存任何历史验收 verdict。

## 迁移原则

- 默认生产模式是 Author；simulation 必须由用户显式选择。
- `StoryBible` 与 `CanonicalState` 的权威等级不会因迁移而降低。
- 旧 Tick、fact ledger、summary、knowledge graph 和旧 memory 只作为低权威兼容输入，
  不会自动升级为 Canon。
- 新对象全部带 schema/revision；更新必须使用乐观并发控制。
- 迁移可重入。已经存在且有效的文件只校验，不被默认数据覆盖。
- 损坏文件先隔离并 fail closed；不允许“修复”为静默丢失旧证据。
- Provider 凭据不属于作品数据迁移范围。

## 新增的作品数据

| 路径 | 用途 | 回滚时处理 |
| --- | --- | --- |
| `production_spec.json` | 整书规模和创作规格 | 保留 |
| `book_outline.json` | 卷章结构、目标和进度 | 保留 |
| `style_profiles.json` | 内置与用户风格档案 | 保留 |
| `active_style.json` | 活动风格及生效章节 | 保留 |
| `production_migration.json` | 幂等迁移收据 | 保留 |
| `generation_jobs/` | 持久化整书任务 | 保留，停止旧进程写入 |
| `production_attempts/` | 分节尝试 journal | 保留 |
| `production_events/` | 可重放 Job 事件 | 保留 |
| `production_chapters/` | 章节工作/提交记录；公开面只读 committed | 保留 |

原有 `story_bible.json`、`canonical_state.json`、`story_threads.json`、
`memory_records.json`、`generation_transactions/` 和正式 section 存储继续作为 Author
权威链的一部分。

## 迁移前准备

1. 停止该作品的新 Writer 调用，等待正在进行的原子提交结束。
2. 记录部署版本、Git HEAD、数据根目录和作品 ID。
3. 对完整作品目录做只读快照或副本，并记录文件 SHA-256。
4. 生成一次旧版本可读的 manuscript/evidence 导出，记录 committed section 数与 hash。
5. 检查磁盘空间、目录写权限和原子 rename 能力。
6. 先在当前源码上完成 [最终验收](./FINAL_ACCEPTANCE.md) 的完整离线 Gate；迁移验证本身
   不需要真实 Provider 调用。

不要把浏览器、设备或验收用 Provider 凭据复制进作品目录、`config.json`、迁移包或报告。
服务端运行时凭据由部署环境或秘密管理系统注入；真实验收的原始 `coding.txt` 仅通过显式
只读 `--provider-file` 在进程内解析。

## 迁移流程

1. 部署当前应用，但保持对目标作品的生产任务关闭。
2. 以作品所有者身份读取任一整书 Author endpoint。`ensure_production_domain` 会在作品锁内
   创建或校验整书域。
3. 若整书规格不存在，迁移器从作品标题和现有 `StoryBible` 构造可编辑的默认
   `NovelProductionSpec`。
4. 若大纲不存在，创建空的 `draft BookOutline`；它不会伪造已提交进度。
5. 创建只读内置风格 preset 与活动风格绑定；已有合法用户风格和绑定保持不变。
6. 首次加载生产 runtime 时校验现有 Job、attempt、event、chapter 与 Author transaction
   journal。有效对象不重写；需要补齐的目录和文件按各自 store 的原子规则创建。
7. 读取规格、大纲、风格列表、Canon、Thread、Memory 和 committed chapters，确认 API
   revision 与磁盘对象一致。
8. 运行 [长篇生产手册](./LONG_NOVEL_PRODUCTION.md) 中的无 Provider 操作检查和 recorded
   smoke；不要用迁移验证去覆盖正式作品数据。

## 迁移后核对

迁移只有在以下检查全部满足时才可开放生产：

- 同一作品第二次触发迁移不再创建不同内容，且 migration 状态可重复读取；
- `StoryBible`、Canon、Thread、Memory 的 revision 与迁移前相符；
- 旧 committed sections 数量、顺序、正文 hash 与迁移前导出一致；
- 新 `BookOutline` 没有伪造 `committed_section_ids`；
- 内置 StyleProfile 为 `read_only=true`，活动绑定引用存在的 profile；
- 章节列表只显示 committed 章节，列表 DTO 不含正文，详情 DTO 含完整正文；
- manuscript 不含 rejected、failed、prepared、validated 或 committing 候选；
- evidence 不含 API key、Authorization、完整 Base URL、Provider 原始响应或拒绝正文；
- 重启应用后没有重复 section、transaction、Canon revision、Thread 推进或 Memory 写入。

## 在线升级与并发

推荐先停止 Writer，再升级。若必须滚动部署：

- 一次只允许一个版本持有某作品的生产租约；
- 数据目录必须共享原子 replace 语义，不能在两个不协调的副本中并发写；
- 所有规格、大纲、风格和 Job 控制都携带 `expected_revision`；HTTP 409 后客户端必须刷新，
  不能盲目重放旧 payload；
- 旧进程退出前不得启动新进程的 Writer；`validated`/`committing` journal 交由一个新进程
  恢复；
- schema 不兼容、权限错误或损坏文件都应暂停任务并 fail closed。

## 回滚触发条件

以下任一情况都应停止新写入并评估回滚：

- 权威文件无法校验或原子写持续失败；
- revision 不连续、重复 transaction/section 或 committed 顺序异常；
- manuscript 与 committed-only 规则不一致；
- 新版本无法在启动时幂等恢复 pending journal；
- Provider 错误被误映射为应用 401，或诊断/产物出现秘密；
- 当前新 evidence 中任一硬 Gate 失败。

验收失败本身不授权重复真实调用；是否开启新周期必须由新的源码 hash、全新 evidence 目录
和完整离线 Gate 重新决定。

## 部署级回滚

1. 请求 pause/cancel，并停止所有新 Writer 调度；等待当前原子边界结束。
2. 复制完整作品目录与当前 evidence，记录 hash；不要删除失败或 pending journal。
3. 在隔离部署中启动已知可用的旧版本。不要让新旧版本同时写同一目录。
4. 若旧版本能忽略新 schema，则让它只读检查；不要用旧版本改写不认识的文件。
5. 若旧版本无法读取迁移后的作品，把迁移前快照恢复到一个新的目录，再把旧部署指向该
   副本。不要覆盖唯一的新格式原件。
6. 比对迁移前导出、回滚副本导出和 committed section hash。
7. 旧版本健康检查、应用登录、读取和 committed-only 导出全部通过后，才重新开放写入。

## 前滚恢复

修复后重新采用当前版本时：

1. 从保留的新格式目录开始，不从 manuscript 反向重建 Canon。
2. 完成完整离线 Gate，并建立新的独占 evidence 周期。
3. 启动应用，让启动恢复扫描 Job/attempt/transaction journal。
4. 检查 `recovery/resume` 结果和 production events，再恢复 paused Job。
5. 对同一组 committed chapters 重新导出并核对 hash。
6. 只有新 evidence 报告满足全部硬 Gate，才能给出发布结论。

架构与恢复不变量见 [最终产品架构](./FINAL_ARCHITECTURE.md)，接口见
[API 参考](./API.md)。
