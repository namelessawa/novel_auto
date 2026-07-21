# 默认作者模式架构

## 目标与边界

默认运行路径围绕长期记忆、主题稳定和背景一致性设计。它不是旧 v1.x 单体章节生成器的回归，也不把九 Agent 模拟删除；它把“谁有权定义事实、哪些上下文可以进入 Writer、何时允许落盘”收束为一条可验证的主链。

作品首次打开时使用 `author` 模式，且不会导入或实例化 `TickRuntime`。只有用户显式切换为 `simulation` 时才延迟创建模拟运行时。模拟产生的正文和状态候选同样进入统一校验与事务网关，不能直接改写作者权威状态。

## 权威层级

1. `StoryBible` 是最高创作契约：主题、故事前提、世界不可变规则、禁区、主角契约、主冲突、结局方向和风格契约。
2. `CanonicalState` 是唯一当前可变事实：时间、角色、位置、物品、关系、读者/角色知识、情节位置和最近场景。
3. `StoryThread` 管理谜团、冲突、承诺、威胁和目标的生命周期；推进或解决必须附带正文证据。
4. `MemoryRecord` 用于检索历史，不覆盖 CanonicalState。每条记忆都有类型、规范状态、实体、来源引用、证据、重要度和创建修订号。
5. 知识图谱、旧事实账本、摘要树和模拟状态均为派生或迁移来源，不拥有最终写权。

StoryBible 的 PUT 使用 `expected_revision` 乐观并发控制；保存后标记为用户确认。Writer 的状态增量若指向 StoryBible、违反不可变世界规则或禁区，会被拒绝。

## 生成与提交主链

```mermaid
sequenceDiagram
    participant UI as Author Studio
    participant CB as ContextBuilder
    participant W as Writer
    participant V as Validator
    participant TX as Transaction Journal
    participant C as Canonical Stores
    UI->>CB: SectionGoal
    CB->>W: 10 个固定预算槽
    W->>V: 正文 + StateDelta + Thread/Memory
    alt 可修复且首次失败
        V->>W: 仅包含违规与修复提示的定向请求
        W->>V: 修复后的正文补丁
    end
    V->>TX: 写入 validated/committing 目标快照
    TX->>C: 幂等提交正文、CanonicalState、Threads、Memory
    C->>TX: 标记 committed
```

每次生成默认一次 Writer 调用，校验失败时最多追加一次修复调用。修复模型只能改变正文；状态增量始终采用第一次校验得到的 `validated_delta`，避免修复响应重新注入高风险状态。第二次仍失败则事务进入 `rejected`，不产生正式章节或权威状态变化。

十个上下文槽有独立字符预算：

1. `story_bible`（受保护，不因总预算丢失）
2. `canonical_state`
3. `section_goal`
4. `active_story_threads`
5. `reader_knowledge`
6. `character_knowledge`
7. `previous_prose_tail`（保留尾部）
8. `recent_section_summaries`
9. `relevant_long_term_memories`
10. `style_contract`

`context_manifest.json` 只记录各槽字符数、token 估算、预算、是否截断、引用 ID、选择/省略数量和重复率；API 不返回 prompt、候选正文或事务目标快照。

## 确定性校验

Validator 在任何权威写入前检查：

- StoryBible 越界、禁区和主题偏离；
- 不存在的角色、死亡角色复活及世界规则中的禁止复活；
- 位置跳跃、物品归属与转移；
- 角色知识来源、读者已知信息的重复揭示；
- 故事线证据、重复开启和非法解决；
- StateDelta 路径和操作合法性。

模拟模式可携带 `simulation_projection:` 类型化来源，作为位置迁移或故事线证据，但仍不能绕过 Bible、身份、路径和其他安全检查。

## 持久化、恢复与迁移

作者域文件位于每部作品的既有数据目录：

| 文件 | 含义 |
| --- | --- |
| `story_bible.json` | 最高创作契约 |
| `canonical_state.json` | 唯一当前事实 |
| `story_threads.json` | 故事线仓库 |
| `memory_records.json` | 类型化长期记忆 |
| `generation_mode.json` | per-novel 模式和修订号 |
| `context_manifest.json` | 最近一次内容无关的上下文清单 |
| `generation_transactions/{id}.json` | 生成和提交 journal |
| `story_migration.json` | 迁移结果与警告 |

单文件保存使用同目录临时文件、flush、`fsync` 和 `os.replace`，覆盖前验证现有文件并保留 `.bak`。损坏文件复制到 `quarantine/`；无法验证时拒绝覆盖。事务先记录完整目标快照，再以可重复操作依次提交 CanonicalState、Threads、Memory 和正式章节，最后标记 `committed`。进程在中途退出时，下一次服务启动会重放 `validated/committing` 事务；章节用事务 ID 幂等追加，因此不会重复发布。

迁移器只读取旧 `tick_state.json`、`fact_ledger.json`、`memory_store.json` 和 `summary_tree.json`，不改写原文件。L3 传说只能成为 `uncertain` 历史记忆，不能成为 CanonicalState。占位 Bible/State 可被 bootstrap 丰富；任何用户确认的数据优先且不会被后续迁移覆盖。

## API 与运行模式

所有作者 API 需要当前用户身份并通过 `(user_id, novel_id, real data_dir)` 隔离：

- `GET/PUT /api/novels/{novel_id}/story-bible`
- `GET /api/novels/{novel_id}/canonical-state`
- `GET /api/novels/{novel_id}/story-threads`
- `GET/PUT /api/novels/{novel_id}/generation-mode`
- `POST /api/novels/{novel_id}/sections/generate`
- `GET /api/novels/{novel_id}/sections/{task_or_section_id}/status`
- `GET /api/novels/{novel_id}/context-manifest`

模式切换失败会回滚原 `generation_mode.json` 并清除不完整 runtime。作者模式中的 Tick、Agent 及旧 `/api/section/generate` 不会隐式创建模拟器，而是返回模式错误。删除作品前同时释放作者与模拟 runtime，避免 Windows 文件句柄阻止删除。

默认值可用 `GENERATION_MODE=author` 配置，但一旦作品生成了 `generation_mode.json`，以作品内配置为准。

## 运维与回滚

- 回滚单次生成：未提交或被拒绝的事务不影响正式章节；检查对应 journal 的 `validation_report`。
- 崩溃恢复：重新启动服务并加载该作品，服务会重放待提交事务。
- 数据损坏：先查看 `quarantine/` 和同名 `.bak`，不要直接覆盖损坏权威文件。
- 回到模拟实验：通过 generation-mode API 或前端显式切换；若初始化失败，模式自动回滚。
- 回到作者模式：切换后模拟 runtime 缓存立即释放，后续页面不轮询 Tick。

实现入口位于 `backend/story/`，HTTP 边界位于 `backend/api/story_routes.py`，模拟发布边界位于 `backend/story/simulation_gateway.py`。
