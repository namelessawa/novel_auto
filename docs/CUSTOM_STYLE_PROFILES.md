# 自定义风格档案

`StyleProfile` 是版本化、只控制表达的写作契约。它不能改变 `NarrativeContract`、
`StoryBible`、`CanonicalState`、长度门槛、章节目标或故事线状态；发生冲突时，上述权威
始终优先。

## 档案类型

| source | read_only | 说明 |
| --- | --- | --- |
| `preset` | `true` | 随作品迁移创建的内置 snapshot；不能更新或删除 |
| `user` | `false` | 用户新建或复制出的档案；可按 revision 更新/删除 |
| `legacy` | 视迁移结果 | 从旧作品风格锚点构造的兼容 snapshot |

内置 preset 来自后端 catalog，常见 key 包括 `literary`、`noir_cold`、
`warm_healing`、`hot_blooded` 和 `classical_chapter`。完整列表以
`GET /api/novels/{novel_id}/style-profiles` 为准。不要依赖前端硬编码列表。

## 字段

### 标识与版本

| 字段 | 说明 |
| --- | --- |
| `id` | 服务端生成的稳定 ID；用户档案形如 `style_<id>` |
| `revision` | 从 1 开始；每次成功更新递增 |
| `name` | 用户可见名称 |
| `base_preset_key` | 可选的 preset 语义来源，不赋予 preset 写权限 |
| `description` | 简短的表达目标 |
| `source` / `read_only` | 所有权与可编辑性 |
| `created_at` / `updated_at` | 版本时间戳 |

### 叙述与节奏

| 字段 | 类型/范围 | 说明 |
| --- | --- | --- |
| `narrative_voice` | string | 叙述声音与距离 |
| `viewpoint` | string | 第一/第三人称、限知等表达要求 |
| `tense` | string | 时态偏好 |
| `sentence_length_tendency` | string | 短句、交错、中长句等 |
| `paragraph_density` | string | 段落留白与信息密度 |
| `dialogue_ratio` | 0–1 | 对话比例目标 |
| `description_ratio` | 0–1 | 描写比例目标 |
| `pacing` | string | 推进与停顿方式 |
| `rhythm_instructions` | string | 句法、标点、段落节奏要求 |

比例是表达目标，不授权补写大纲中不存在的对白、人物或事件。

### 情绪、意象与收束

| 字段 | 类型/范围 | 说明 |
| --- | --- | --- |
| `emotional_intensity` | 0–10 | 情绪外显强度 |
| `humor_level` | 0–10 | 幽默强度 |
| `imagery_preference` | string | 感官与意象偏好 |
| `vocabulary_preference` | string | 词汇 register |
| `chapter_opening_preference` | string | 章节开头表达偏好 |
| `chapter_ending_preference` | string | 章节收尾表达偏好 |

### 规则与样文

| 字段 | 说明 |
| --- | --- |
| `must_do_rules` | 必须做到的表达规则 |
| `forbidden_rules` | 禁止的表达方式 |
| `avoided_phrases` | 应避免的短语或口癖 |
| `optional_user_sample` | 用户原始样文；保留为用户数据，不直接进入 Writer prompt |
| `derived_style_anchors` | 从样文计算的聚合特征，不包含原句片段 |
| `deterministic_rules` | 服务端可识别的确定性表达校验规则 |
| `prompt_hash` | expression-safe prompt contract 的稳定 SHA-256 |

## 样文处理与 prompt hash

样文作为用户拥有的 StyleProfile 数据保留，并在本地/服务端确定性分析中计算：非空白
字符数、句数、平均句长、段落数、平均段落长度、引号内对话占比和分句标点密度。输出是
“短句倾向”“中等对话占比”等聚合 anchor，不会截取或复制样文句子。

`prompt_hash` 由排序、紧凑 JSON 的 `prompt_contract` 计算。contract 包含表达字段、派生
anchors、deterministic rules 和“风格不得覆盖权威”的边界；不包含：

- `optional_user_sample` 原文；
- `id`、`name`、revision、时间戳；
- Provider 凭据或运行参数；
- StoryBible、Canon、章节正文或用户秘密。

因此只改档案名称不会改变实际 Writer 表达契约；修改表达字段或派生 anchors 会产生新的
revision 和新的 hash。传入与计算值不符的 `prompt_hash` 会被拒绝。

## 创建与复制

新建用户档案：

```http
POST /api/novels/{novel_id}/style-profiles
Content-Type: application/json
```

```json
{
  "name": "低饱和悬疑",
  "narrative_voice": "克制、贴近视点角色",
  "viewpoint": "第三人称限知",
  "sentence_length_tendency": "短句与中句交错",
  "paragraph_density": "中等留白",
  "dialogue_ratio": 0.25,
  "description_ratio": 0.4,
  "pacing": "线索推进快，解释延后",
  "emotional_intensity": 4,
  "humor_level": 0,
  "must_do_rules": ["情绪落到动作或物件"],
  "forbidden_rules": ["跨视点心理"],
  "avoided_phrases": ["命运的齿轮"],
  "optional_user_sample": "<user-owned sample>"
}
```

复制现有 preset 或用户档案只需名称与来源：

```json
{
  "name": "我的冷峻版本",
  "copy_from_profile_id": "preset_noir_cold"
}
```

兼容字段 `source_profile_id` 与 `copy_from_profile_id` 二选一；同时指定不同来源返回 422。
复制结果始终是新的 `source=user`、`read_only=false` 档案，revision 从 1 开始。

## 编辑、删除与冲突

更新路径为 `PUT /api/novels/{novel_id}/style-profiles/{style_id}`，payload 至少包含当前
`expected_revision`，其余字段是 patch：

```json
{
  "expected_revision": 1,
  "pacing": "前快后缓，结尾停在未回答的行动选择",
  "emotional_intensity": 5
}
```

- 旧 revision 返回 409；客户端刷新后让用户决定是否重新应用修改。
- 内置 preset 更新/删除返回 403 `STYLE_PROFILE_READ_ONLY`。
- 活动档案不能删除，返回 409 `STYLE_PROFILE_ACTIVE`。
- 删除请求把 revision 放在 query：
  `DELETE .../style-profiles/{style_id}?expected_revision=2`。

已开始 Job、chapter 和 section 持有完整 StyleProfile snapshot；编辑源档案不会回写这些
snapshot，也不会改变已提交正文或证据。

## 非 Canon 预览

```http
POST /api/novels/{novel_id}/style-profiles/{style_id}/preview
```

```json
{
  "expected_revision": 2,
  "sample_goal": "用夜班车站里的一次短暂对峙展示这个风格"
}
```

预览只向 Provider 发送 expression-safe `prompt_text` 和 `sample_goal`，不发送完整
StyleProfile 或用户样文。响应包含 `text`、style ID/revision、`prompt_hash` 和 token usage。
预览是非 Canon：不创建正式 transaction，不推进 StoryBible、Canon、Thread、Memory、
Outline 或 Production Job，也不进入 manuscript/evidence 导出。

Provider 输出为空或疑似包含 secret/traceback 时返回 502 `PROVIDER_OUTPUT_INVALID`。

## 激活与“下一章生效”

```http
POST /api/novels/{novel_id}/style-profiles/{style_id}/activate
```

```json
{
  "expected_revision": 3,
  "expected_spec_revision": 5,
  "applies_from_chapter_ordinal": 12
}
```

`expected_revision` 是 `active_style.json` 当前 revision，不是目标 profile revision。省略
`applies_from_chapter_ordinal` 时，服务端确定下一未生成章节。显式 ordinal 不能小于该值，
因此风格不能追溯覆盖已开始或已提交章节。

激活在作品生产边界锁内完成：先把目标 profile 的完整 snapshot、revision 和 prompt hash
写入 `active_style.json`，再同步 `ProductionSpec.active_style_profile_id`。如果进程恰好在两次
原子写之间退出，下次 API 读取以 active binding 为权威，幂等修复 Spec 派生字段。

章节开始时再冻结一次实际 snapshot。之后即使用户更新/激活其他风格：

- 当前章节继续用原 snapshot；
- 已提交章节的 style ID/revision/hash 与正文不变；
- 下一未开始章节按新的 active binding 选择 snapshot。

## 验证与审计

每个正式 section attempt 和 chapter 在作品私有持久化中冻结完整 style snapshot；公开收据
至少记录 style ID、revision 和 prompt hash。拥有该作品的 Style/chapter API 可能返回其
自有 snapshot，但诊断与公共导出只使用 allowlist。验收至少检查：

- 同一章节内所有 sections 使用同一冻结风格；
- 激活前的章节不发生回写；
- 激活只在下一未开始章节出现；
- optional sample 原句不出现在 Writer prompt、预览 prompt、manuscript、公开 evidence
  导出、日志或最终报告；
- style 变化不改变 required events、end states、Canon delta 或长度门槛；
- prompt hash 可从 expression-safe contract 重算。

完整 endpoint 表见 [API 参考](./API.md)，生产冻结顺序见
[最终产品架构](./FINAL_ARCHITECTURE.md)。
