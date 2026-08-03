# API 参考

本文覆盖默认整书 Author 产品路径。运行时 schema、必填字段和枚举以登录后的 FastAPI
OpenAPI `/docs` 为准；本文说明资源关系、并发语义和不容易从 schema 看出的安全边界。

## 通用约定

- 基础地址：`http://127.0.0.1:8762`。
- 除公开的 `GET /api/presets` 外，下列接口都要求应用 Bearer JWT；作品接口只能访问当前
  用户拥有的作品。
- `{novel_id}` 是作品 ID；`{style_id}`、`{job_id}`、`{chapter_id}` 是对应资源 ID。
- 整书规格、大纲、风格绑定、风格档案和 Job 控制采用乐观并发。写请求携带当前
  `expected_revision`；不匹配返回 HTTP 409 `REVISION_CONFLICT`。
- “字数”统一为非空白字符数。
- 正式章节与导出只读取 `committed` 数据。
- 错误通常位于 `detail`：

```json
{
  "detail": {
    "code": "REVISION_CONFLICT",
    "message": "数据已被其他会话更新，请重新载入",
    "details": {"expected": 3, "actual": 4}
  }
}
```

## Provider 请求配置

浏览器可以为当前请求发送完整的一组用户 LLM headers：

```text
X-User-LLM-Key
X-User-LLM-Base-Url
X-User-LLM-Model
X-User-LLM-Provider
X-User-LLM-Thinking-Mode
X-User-LLM-Timeout
X-User-LLM-Max-Retries
```

如果浏览器没有本地 key，应省略整组用户 LLM headers，由服务端配置或环境 fallback 统一
解析；不要发送只有 provider/model、没有凭据的残缺覆盖。完整 key 和完整 Base URL 不会
从服务端回显。配置优先级、安全规则与真实验收的 `coding.txt` 用法见
[Provider 生命周期](./PROVIDER_RUNTIME_LIFECYCLE.md)。

## Provider API

| 方法与路径 | 请求 | 响应/用途 |
| --- | --- | --- |
| `GET /api/config/llm/providers` | 无 | 后端 catalog：provider、label、默认 model、默认 Base URL |
| `GET /api/config/llm/runtime` | 可带用户 LLM headers | 当前解析结果的 provider/model/source/thinking/timeout/retries、凭据存在性和短指纹 |
| `POST /api/config/llm/probe` | 可选 `{"max_tokens":16}` | 最小调用；返回状态、分类、tokens、延迟和配置指纹 |
| `GET /api/config/llm` | 无 | 兼容的服务端配置视图；不得依赖它读取完整 secret |
| `PUT /api/config/llm` | `api_key?`、`base_url?`、`model?`、`provider?` | 更新服务端持久配置并 reload 下一次调用；部署级操作 |

Provider 认证、限流、不可用和输出错误分别映射为：

| HTTP | code | 应用 JWT |
| ---: | --- | --- |
| 424 | `PROVIDER_AUTH_FAILED` | 保留 |
| 429 | `PROVIDER_RATE_LIMITED` | 保留 |
| 502 | `PROVIDER_UNAVAILABLE` | 保留 |
| 502 | `PROVIDER_OUTPUT_INVALID` | 保留 |

只有应用 JWT 自身无效/过期的 HTTP 401 `AUTH_*` 才触发重新登录。

## 作品 CRUD

| 方法与路径 | 请求/参数 | 作用 |
| --- | --- | --- |
| `GET /api/novels` | 无 | 列出当前用户作品和活动作品 ID |
| `POST /api/novels?auto_bootstrap=false` | `{"title":"...","generation_mode":"author"}` | 创建作品；默认 Author |
| `PUT /api/novels/{novel_id}` | `{"title":"..."}` | 修改标题 |
| `DELETE /api/novels/{novel_id}` | 无 | 删除非活动作品；这是破坏性操作 |
| `POST /api/novels/{novel_id}/switch` | 无 | 切换活动作品；Author 不构建 Tick runtime |

冷启动兼容接口包括 `GET /api/presets`、`POST .../bootstrap-world`、
`POST .../regenerate-style-anchors` 和 `POST .../style-preset`。默认整书向导应优先使用下述
ProductionSpec、BookOutline 与 StyleProfile API。

## 整书规格

### `GET /api/novels/{novel_id}/production-spec`

返回：

```json
{
  "production_spec": {
    "revision": 1,
    "title": "示例",
    "target_total_chars": 300000,
    "volume_count": 5,
    "chapter_count": 100,
    "target_chapter_chars": 3000,
    "accepted_chapter_min_chars": 2700,
    "accepted_chapter_max_chars": 3300,
    "section_target_chars": 1500,
    "active_style_profile_id": "preset_literary"
  },
  "migration": {}
}
```

实际对象还包括 premise、genre、theme、central_question、generation_language、
ending_direction、production_status 与时间戳。

### `PUT /api/novels/{novel_id}/production-spec`

发送 `NovelProductionSpecUpdate`，至少包含 `expected_revision`；其余字段是 patch：

```json
{
  "expected_revision": 1,
  "target_total_chars": 240000,
  "volume_count": 4,
  "chapter_count": 80,
  "target_chapter_chars": 3000,
  "accepted_chapter_min_chars": 2700,
  "accepted_chapter_max_chars": 3300,
  "section_target_chars": 1500
}
```

总字数必须落在 `chapter_count × [chapter_min, chapter_max]` 内，卷数不能大于章数，分节目标
不能大于章节上限。活动风格以 `active_style.json` 为权威，不能通过本接口绕过 activate。

## 整书大纲

| 方法与路径 | 请求 | 作用 |
| --- | --- | --- |
| `GET /api/novels/{novel_id}/outline` | 无 | 返回 `book_outline` 与 migration 收据 |
| `PUT /api/novels/{novel_id}/outline` | `BookOutlineUpdate`，含 `expected_revision` | 修改未提交章节的大纲内容 |
| `POST /api/novels/{novel_id}/outline/generate` | `expected_spec_revision`，可选 `expected_outline_revision` | 一次结构化生成；无效时至多一次结构化修复 |

生成请求示例：

```json
{
  "expected_spec_revision": 2,
  "expected_outline_revision": 1
}
```

响应包含 `book_outline`、`provider_calls`、`repair_performed` 和脱敏 usage。大纲必须满足卷章
连续编号、卷归属、各卷章节数/字符预算闭合及 Spec 总预算。已有 committed 章节时不能重新
生成全书大纲；用户也不能修改 committed 章节、`status` 或 `committed_section_ids`。

## StyleProfile CRUD

| 方法与路径 | 请求/参数 | 作用 |
| --- | --- | --- |
| `GET /api/novels/{novel_id}/style-profiles` | 无 | 返回 `profiles` 和 `active_style` |
| `POST /api/novels/{novel_id}/style-profiles` | `StyleProfileCreateRequest` | 新建用户档案，或复制现有档案 |
| `PUT /api/novels/{novel_id}/style-profiles/{style_id}` | `StyleProfileUpdate` + `expected_revision` | 更新用户档案 |
| `DELETE /api/novels/{novel_id}/style-profiles/{style_id}?expected_revision=N` | query revision | 删除非活动用户档案 |
| `POST /api/novels/{novel_id}/style-profiles/{style_id}/activate` | 激活请求 | 从下一未开始章节绑定该 snapshot |
| `POST /api/novels/{novel_id}/style-profiles/{style_id}/preview` | preview 请求 | 生成非 Canon 的风格预览 |

复制 preset 的最小请求：

```json
{
  "name": "我的冷峻叙事",
  "copy_from_profile_id": "preset_noir_cold"
}
```

激活请求：

```json
{
  "expected_revision": 2,
  "expected_spec_revision": 4,
  "applies_from_chapter_ordinal": 8
}
```

`expected_revision` 是当前 `active_style` revision。省略 `applies_from_chapter_ordinal` 时自动
使用下一未开始章节；不得指定更早章节。preview 请求为
`{"expected_revision":3,"sample_goal":"展示一小段追逐场景"}`，不修改 Canon、Thread、
Memory、Job 或章节。完整字段与 hash 规则见 [自定义风格档案](./CUSTOM_STYLE_PROFILES.md)。

## 整书生产控制

### 启动

`POST /api/novels/{novel_id}/production/start`

```json
{
  "expected_spec_revision": 4,
  "expected_outline_revision": 3
}
```

返回 `{"job":{...},"existing":false}`。相同活动 Job 可幂等返回 `existing=true`；同作品不能
并发运行多个活动 Job。启动前大纲、规格和风格绑定必须有效。

### 暂停、恢复、取消、失败重试

以下四个接口使用相同 body：

```json
{"job_id":"job_...","expected_revision":12}
```

| 方法与路径 | 语义 |
| --- | --- |
| `POST .../production/pause` | 请求在下一个安全边界进入 paused |
| `POST .../production/resume` | 重新校验 revision 并调度 paused Job；幂等恢复 |
| `POST .../production/cancel` | 在安全边界取消，保留已提交章节 |
| `POST .../production/retry-failed` | 为 failed 章节建立新 attempt/transaction |

每次成功响应都返回最新 `job` revision。客户端必须使用该 revision 发下一次控制请求。

### 状态

`GET /api/novels/{novel_id}/production/status?job_id={job_id}`。省略 `job_id` 时读取当前/最近
Job。公开 DTO 排除冻结的完整 Spec/Outline/Style snapshot，并补充：

- `completed_chars` / `committed_chars` / `progress_percent`；
- `completed_chapters`、`provider_call_count`、`latency_sample_count`；
- `last_committed_at`、`story_bible_revision`；
- Job 状态、当前位置、token/latency 汇总、failure code/message 与最新 revision。

Provider runtime 诊断通过 `/api/config/llm/runtime` 单独读取，不混入 Job DTO。

常见 409 为 `PRODUCTION_LEASE_CONFLICT` 或 `PRODUCTION_CONTRACT_STALE`；找不到 Job 返回
404 `PRODUCTION_JOB_NOT_FOUND`。

## SSE 生产事件

`GET /api/novels/{novel_id}/production/events?job_id={job_id}&after_sequence=0&follow=true`

- `after_sequence` 用于断线续传，只返回更大的 sequence；
- `follow=false` 读取当前快照后结束；
- 终态且没有新事件时流结束；长连接会发送注释 keepalive；
- 响应为 `text/event-stream`，禁止代理缓冲。

Wire contract：

```text
id: 17
event: section_committed
data: {"sequence":17,"job_id":"job_...","chapter_id":"ch_...","section_id":"sec_...","transaction_id":"tx_...","timestamp":"..."}

```

事件类型包括 `job_status`、`chapter_started`、`section_started`、`validation`、`repair`、
`section_committed`、`chapter_committed`、`paused`、`failed`、`completed`。取消状态通过
`job_status` 的 `cancelled` 表达。客户端应按 `id/sequence` 去重，不能用到达次数推断提交。

## Committed chapters

| 方法与路径 | 返回 |
| --- | --- |
| `GET /api/novels/{novel_id}/chapters` | committed 章节列表；section 元数据不含 `content` |
| `GET /api/novels/{novel_id}/chapters/{chapter_id}` | 单章详情；包含拼接 `content` 和 committed sections |

章节 DTO 包含 chapter/section transaction IDs、StoryBible revision 起止、Canon revision
起止、repair 总数、style profile ID/name/revision/prompt hash、长度和提交时间。尚未完整提交的
chapter 返回 404 `COMMITTED_CHAPTER_NOT_FOUND`，不会泄漏候选正文。

## Author 权威、审计与导出

| 方法与路径 | 作用 |
| --- | --- |
| `GET/PUT /api/novels/{novel_id}/story-bible` | 读取/按 revision 更新创作圣经 |
| `GET /api/novels/{novel_id}/canonical-state` | 读取唯一当前事实源 |
| `GET /api/novels/{novel_id}/story-threads` | 读取故事线状态与证据 |
| `GET /api/novels/{novel_id}/memories?limit=N` | 读取公开 memory 摘要和当前选中 IDs |
| `GET/PUT /api/novels/{novel_id}/generation-mode` | Author / 显式 simulation 切换 |
| `POST /api/novels/{novel_id}/sections/generate` | 兼容的单节 Author 任务入口 |
| `POST /api/novels/{novel_id}/sections/contract-preview` | 预览本节契约与确定性计划 |
| `GET /api/novels/{novel_id}/sections/{task_or_section_id}/status` | 读取公开 task/transaction/section 状态 |
| `GET /api/novels/{novel_id}/context-manifest` | 读取冻结上下文选择与预算收据 |
| `GET /api/novels/{novel_id}/transactions?limit=N` | 公开 transaction ledger |
| `POST /api/novels/{novel_id}/recovery/resume` | 幂等恢复 pending Author transactions |
| `GET /api/novels/{novel_id}/exports/manuscript` | 下载 committed-only Markdown |
| `GET /api/novels/{novel_id}/exports/evidence` | 下载 allowlisted JSON evidence |
| `GET /api/novels/{novel_id}/long-run/status` | 无正文/无 prompt 的长程诊断聚合 |

manuscript 响应提供 `X-Artifact-SHA256`、included/excluded section 数。evidence 包含 Bible/
Canon hash、ContextManifest、Thread/Memory 摘要、公开 transaction 收据、committed section
元数据和 manuscript hash；不含 Provider secret、完整 Base URL、原始响应或 rejected prose。

## 状态码摘要

| HTTP | 典型含义 |
| ---: | --- |
| 200/201 | 成功；创建 StyleProfile 返回 201 |
| 401 | 应用 JWT 无效/过期 |
| 403 | 内置 StyleProfile 只读 |
| 404 | 作品/Style/Job/committed chapter 不存在或不属于当前用户 |
| 409 | revision、活动 style、lease、任务或冻结契约冲突 |
| 422 | schema、规格、大纲、激活、生产状态或持久化请求无效 |
| 424/429/502 | Provider auth/rate/unavailable/output error；应用 JWT 保留 |

恢复和原子提交语义见 [最终产品架构](./FINAL_ARCHITECTURE.md)。
