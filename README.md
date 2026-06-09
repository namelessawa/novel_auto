# 无限小说生成系统 (Infinite Novel Generator)

> **当前版本: v2.34** (2026-06-09) — FastAPI + React/Vite 单栈,
> 10 Agent + 7 阶段 Tick 调度的多智能体模拟系统 (故事驱动),
> 节级管线已任务化, 自带邮箱 OTP 多租户认证、Tick 驱动节、多模态视频生成、
> 知识图谱 tick 同步。
> 设计哲学来自 [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md):
> **故事是模拟的副产品, Narrator 选择性讲述**。

> v1.x 章节驱动单体生成器已整体归档到 [`old/`](./old/),
> 不再参与运行时, 但可作为历史参考。

> **状态**: 全部 tick 架构用例 GREEN (541 用例 collect 通过, 全套 ~6s),
> 真实 LLM smoke (mimo-v2.5-pro / DeepSeek) 端到端通过。
> 完整版本历史见 [`CHANGELOG.md`](./CHANGELOG.md)。

> ⚠️ **安全提示 (deployment)**: v2.26 起已落地邮箱 OTP / JWT 鉴权与多租户
> 数据隔离 (`backend/auth/`), 业务端点全部经 `Depends(get_current_user)`
> 校验, 数据按 `data/users/{uid}/novels/{nid}/` 隔离。但 **管理面 API** —
> `/api/config/llm` 、`/api/tick/*` 、`/api/agents/*` 等 — 仍**默认无鉴权**;
> 默认 `cors_origins` 也是 `["*"]`。公网部署需自行加 reverse proxy 鉴权
> (basic auth / OAuth) 或收紧 `cors_origins` 与网络绑定。生产推荐 v2.28
> 后的「服务端 LLM 改读用户 key」模式: `config.json.llm.api_key` 留空,
> 前端请求带 `X-User-LLM-*` header 一次性传递, 服务端用完即丢。

---

## 设计哲学

1. **故事是模拟的副产品**:不让 agent 去"写下一章",而是让一群有目标的角色在
   有规则的世界里活动,Narrator 选择性叙述
2. **Narrator 的品味是质量瓶颈**:Narrator 决定 tick 里哪些事件值得讲述,沉默是合法选项
3. **角色只能用自己知道的信息**:CharacterAgent 严格按 `known_facts` + 可见事件决策
4. **主动遗忘是 feature**:L0→L1→L2→L3 分层压缩,远古事件传说化失真
5. **冲突保留池不能为零**:Showrunner 维护 ≥3 个开放伏笔,EventInjector 自动补充

---

## 架构总览

```
                       Orchestrator (纯 Python,无 LLM)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   WorldSimulator       CharacterAgent×N        Narrator
        │                     │                     │
        │            ActionResolver               (品味决定是否产出)
        │                     │                     │
        └──→ Event Stream ←───┘                     ▼
                  ▲                            [章节文本]
                  │
        ┌─────────┴──────────┐
        │                    │
   EventInjector        Showrunner
   (3 类事件注入)       (节奏 + 冲突保留)
        │                    │
        └─────┬──────────────┘
              │
              ▼
        TickState 持久化(JSON 原子写)
        TickDB 日志(SQLite WAL)
              │
        ┌─────┴──────────────────────┐
        ▼                            ▼
  MemoryCompressor          ConsistencyGuardian
  (L0→L1→L2→L3 压缩)        (5 类矛盾扫描)
        ▲                            ▲
        │                            │
        └─────────  NoveltyCritic ───┘
                 (重复模式检测)
```

### 10 个 Agent + 7 阶段 Tick 循环

| # | Agent | 频率 | LLM | 职责 |
|---|-------|------|-----|------|
| 0 | **Orchestrator** | 每 tick | ❌ 纯调度 | 协调 7 阶段流程, 末尾 KG 同步 + 持久化 |
| 1 | **WorldSimulator** | 每 tick | ✅ small | 推进时间/天气/社会演化 (稳态字段反清空保护) |
| 2 | **EventInjector** | 3-5 tick | ✅ medium | 内生/外生/戏剧事件 + `state_patches` 外部权威补丁 |
| 3 | **CharacterAgent×N** | 每 tick | ✅ A=strong / B=medium | 基于 `known_facts` 决策, cooldown + `model_tier_override` |
| 4 | **ActionResolver** | 每 tick | ❌ 纯逻辑 | 解析独占行动冲突, 落 state 转移字段 |
| 5 | **Narrator** | 每 tick | ✅ strongest→medium | 选材 + 写作, 可主动沉默, 反 reasoning 泄漏, 标题锚定 |
| 6 | **Showrunner** | 每 5 tick | ✅ medium | 节奏曲线 + 冷线索 + 弧线监控 |
| 7 | **MemoryCompressor** | 每 50 tick | ✅ small | L0→L1→L2→L3 压缩 + 传说化 |
| 8 | **ConsistencyGuardian** | 每 30 tick | ✅ continuity_v2 | 5 类矛盾扫描 + 幻觉率统计 |
| 9 | **NoveltyCritic** | 每 20 tick | ✅ small | 重复模式检测, 反馈 Narrator |
| 10 | **SectionCloser** *(v2.24)* | tick 后 | ✅ medium | 判定切节; `words >= upper` 不调 LLM 直接切 |

> 知识图谱 (`backend/graph/`): tick 末尾纯 Python 同步 (无 LLM),
> `CharacterProfile / WorldState.locations / factions /
> CharacterState.{current_location, relationships}` → `Entity + Relation`,
> 与 `agents_called` 一起诊断 (`kg_sync(+Ne/+Nr/~Ne)`).

### v2.20 – v2.34 增量概览

| 版本 | 主线 | 关键落地点 |
|------|------|-----------|
| v2.20 | 前后端缺口对齐 | LLM provider 切换 / `inject-event` 字段补 / OpenLoop CRUD UI / Tick 诊断面板 (6 端点) / Graph 删除按钮 + entity attributes / legacy ControlPanel 挂「节级管线」Tab |
| **v2.21** | P0–P3 隐患清扫 | `CharacterAgent` `all_in_location` 校验 / `_resolve_llm_block` 优先级翻转 (config.json 用户态优先) / TickState/SummaryTree 损坏 quarantine / TickDB `INSERT OR IGNORE` / `switch_novel` 两阶段 / `OpenLoop.origin_event_ids` 字段 / 前端写端点 `assertOk` / Vite proxy 强制 IPv4 |
| **Deploy** | 多目标生产部署 | Linux+systemd+CF Tunnel+Vercel 三段式 / Windows+Docker Desktop / 默认国内镜像源 (daocloud+清华) / `core/config` provider fallback / 前端 `base` 默认根路径 |
| v2.22 | P1-P3 收敛 | `provider 落盘原子化` / 图端点校验 / API 4xx 收敛 / UI 字段对齐 / Orchestrator 注入事件 try/finally |
| v2.23 | 节级管线最终修 | 题材锚定透传 (`seed/title/positioning` → `OutlineAgent`) / 节标题独立 LLM 产出 / UI 集中化 |
| **v2.24** | **SectionCloser + 任务队列 + per-novel TickRuntime** | `SectionCloser` agent / `backend/tasks/` (`TaskManager` + `task_routes` SSE) / `backend/sections/` / `POST /api/section/generate` / 节级管线降级 `/api/legacy/*` 别名 / 前端常驻 `TaskListPanel` |
| v2.25 | `bootstrap_world` 任务化 | 创建空壳 / 4 阶段冷启动 / 链式触发首节 分两步; `TaskKind=bootstrap_world` / `POST /api/novels/{id}/bootstrap-world` / 前端「世界种子」必填 |
| **v2.26** | **邮箱 OTP 认证 + 多租户隔离 + 随机种子/标题** | `backend/auth/` 包 (9 端点) / sha256 OTP + 5 min TTL + per-IP rate limit / `data/users/{uid}/novels/{nid}/` 隔离 / `POST /api/llm/random-{seed,title}` / 前端 `AuthContext` + `LoginGate` + `SettingsModal` |
| v2.27 | HTML 邮件 + 图片 provider + 本地 LLM 配置 | multipart text+HTML OTP 模板 / `ConfigView` 重写 schema 驱动多 provider / LLM 配置改 `localStorage` / Toast 精简 |
| **v2.28** | **多模态文生图 (讯飞) + 服务端 LLM 改读用户 key** | `xfyun_image.py` HMAC-SHA256 / `/api/image/generate` / `UserLLMConfig` `ContextVar` + LRU 32 缓存 `AsyncOpenAI` / `UserLLMHeadersMiddleware` 透传 `X-User-LLM-*` |
| v2.29 / v2.30 | 中间件 + 轮询治理 | `UserLLMHeadersMiddleware` 改纯 ASGI 修 502 CORS 头丢 / 彻底删除所有 `setInterval`, 事件驱动 (`visibilitychange` + 用户操作触发) |
| v2.31 / v2.32 | 讯飞图片生成对齐 | `modelid` (domain) 切换 / `wss → https POST` / 业务错误码中文 hint / MaaS host+body+分辨率约束 / `patch_id` 永远 set / Docker bridge MTU 1380 |
| **v2.33** | **多模态视频生成** | `text_segmenter`(中文按句切, 15-60 字) + `edge_tts_client`(WordBoundary 时长) + `video_composer`(`imageio-ffmpeg` 单条 filter_complex, `Semaphore(2)`) + `multimedia/asset_store` + `MultimodalView` 前端 + 6 REST 端点 + 36 安全/性能用例 |
| **v2.34** | **KG tick 同步 + LLM JSON 兜底 + 4 类用户 bug 治根** | `backend/graph/tick_kg_sync.py` 自动喂图 + `KnowledgeGraph.save/load_to_disk` / `parse_llm_json` 11 agent + bootstrap 统一 + `json_repair` 兜底 / `WorldSimulator` 稳态字段反清空 / `SectionCloser` 接共享 reasoning 反泄漏 / `bootstrap` 空世界完整性闸 / `TickState.novel_title` 主题锚点 / 终态任务保留 60s → 30 min |

### Guardian 幻觉率诊断 (v2.18 Phase 9)

```bash
# 生产观察 - shadow 期: 看真阳率
curl http://127.0.0.1:8762/api/tick/diagnostic/hallucination
# {
#   "auto_degrade_active": false,
#   "stats": {
#     "character_agent:elara": {
#       "hallucination_hits": 12,
#       "degrade_recommendations": 2,
#       "last_degrade_recommended_tick": 87,
#       "model_tier_override_active": false
#     }
#   }
# }

# 实战切 active 期 — Guardian 超阈值自动写 model_tier_override='haiku'
export HALLUCINATION_AUTO_DEGRADE=1
```

### `model_tier_override` 闭环路径 (v2.18 Phase 5–6)

```
Guardian.scan_hallucination_rate (阈值 >0.3)
  → GuardianConflict(priority='B', type='character',
                     resolution_specifics='haiku')
  → Orchestrator._ingest_guardian_conflicts
  → AgentRuntimeState.degrade_recommendations++ / hallucination_hits++
  → (HALLUCINATION_AUTO_DEGRADE=1) AgentRuntimeState.model_tier_override = 'haiku'
  → Orchestrator._collect_model_overrides (阶段 3)
  → CharacterAgent.batch_decide(model_overrides={cid: 'haiku'})
  → LLMClient.chat(model_override='haiku')
  → token budget 记账到降级 model
```

### TokenBudget 硬拦截 (v2.17)

```python
# 调用前 can_afford() 拦截 — critical 永不拒绝, medium/optional 超额抛
# BudgetExceeded; 调用方既有 try/except 自动落回降级输出。
try:
    resp = await llm_client.chat(
        system_prompt=..., user_prompt=...,
        agent_id="character_agent:elara",
        priority="medium",
    )
except BudgetExceeded:
    return self._fallback_action()
```

环境变量: `LLM_BUDGET_MAX_TOTAL` / `LLM_BUDGET_MAX_PER_TICK`,
持久化到 `data_dir/token_budget.json`。

### `chat_stream` 流式记账 (v2.19)

`writer_agent.write_stream` → `llm_client.chat_stream` 此前完全不入 tracker。
v2.19 让 streaming 与非 streaming 同源:

* 调用前 `can_afford()` 拦截 (`stream_options.include_usage=True` 透传)
* 从最后含 usage 的 chunk 抽 prompt/completion token, 进 tracker
* tick 默认 -1 时 fallback 到 `_current_tick_var` ContextVar
* v2.19.5: `async for` 包 `try/finally`, 异常路径也 record 一次 (call_count
  反映尝试次数), 防止失败的大段写作让生产监控的失败率虚低

### 读者互动分支管理 (v2.9 新增)

> 平行宇宙模型 — fork 即拷贝整个 data_dir, 各分支互不污染。

`backend/narrative/branch_manager.py` 提供 `BranchManager`:

```python
bm = BranchManager(root_data_dir="/path/to/novels/my_novel")
bm.load()

# tick 50 时给读者两个选择
meta = bm.fork(
    from_branch_id="main",
    new_branch_id="branch_追查",
    forked_at_tick=50,
    choice_description="alice 在十字路口",
    choice_options=["回家", "追查"],
    selected_option="追查",
)
# 之后 Orchestrator 用 bm.data_dir_for("branch_追查") 实例化
```

**操作**: `fork` / `archive` / `unarchive` / `set_canonical` / `annotate` /
`build_tree` / `list_branches(include_archived)`

**树结构** (BranchTreeNode) 供前端展示分支演化。

### 创造力评分器 (v2.8 新增)

> 不让系统渐进套路化 — 滑窗追踪词汇/结构/情感三维多样性, 退化时主动 alert。

`backend/narrative/creativity_scorer.py` 提供 `CreativityScorer`:

| 维度 | 指标 | 退化警报 |
|------|------|---------|
| 词汇 | TTR (type-token ratio) | `CRX_LEX` (>20% drop) |
| 结构 | sentence_len_std/mean | `CRX_STRUCT` (>20% drop) |
| 情感 | 情感类别数 (8 类词典) | `CRX_EMO` (>20% drop, 单类时 high) |

**工作流**:
1. 每段叙述后 `ingest_paragraph(text, tick)` 计算指标
2. 前 `baseline_size` (默认 20) 段锁定为基线
3. 之后每段对比最近 `window_size` (默认 10) 与基线的差
4. 退化 > 20% → alert 入报告
5. Orchestrator 把 alert 翻译为 `[创造力警报 CRX_LEX]` 注入下 tick Narrator

每条 alert 自带 `advice`, 可直接作为下段写作方向提示。

### Token 预算 + 安全过滤 (v2.7 新增)

> 不让成本失控 — 三层视图记账 + 退化决策 + Narrator 落盘前安全检查。

**TokenBudgetTracker** (`backend/nf_core/token_budget.py`):

| 优先级 | 退化阈值 |
|--------|---------|
| `critical` (Narrator, Critic) | 永不拒绝 |
| `medium` (Showrunner, Director) | 总预算 ≥90% 拒绝 |
| `optional` (NoveltyCritic, Tracker LLM) | 总 ≥70% 或 tick ≥80% 拒绝 |

环境变量: `LLM_BUDGET_MAX_TOTAL` / `LLM_BUDGET_MAX_PER_TICK`,
持久化到 `data_dir/token_budget.json` 累计 token 跨进程恢复。
`LLMClient.chat` 三参数 `agent_id` / `priority` / `tick` 自动入账。

**SafetyFilter** (`backend/narrative/safety_filter.py`):

| 类别 | 规则 | severity |
|------|------|----------|
| PII | 身份证号 (18 位 + X) | block |
| PII | 中国大陆手机号 | block |
| PII | 邮箱 | warn (mask) |
| PII | 银行卡号 16-19 位 | warn |
| harm | 自伤操作指南 (具体方法 + 自杀手段共现) | block |
| illegal | 违禁品制作 (炸弹/毒品合成) | block |

故意不阻塞: 文学暴力 / 灰色道德 / 悲剧 / 创伤描写。
block 时 Narrator 输出跳过落盘 + 状态更新, warn 时占位符替换继续。

### 事实账本 + 时间线 (v2.6 新增)

> 不让错误悄悄演化 — append-only ledger, 矛盾留下 disputed 痕迹而非默认覆盖。

`backend/narrative/fact_ledger.py` 提供 `FactLedger`:

**Fact** 字段: `id` / `kind` / `subject` / `predicate` / `object` /
`established_tick` / `source_event_id` / `status`

**FactKind**: location / possession / relation / rule / death / skill /
promise / fact

**矛盾检测** (`contradict_check` 不修改账本):

| 场景 | severity |
|------|----------|
| 同 subject 同 kind 但 predicate/object 不同 | high |
| 死者再次出现 location/skill/promise/possession | high |
| possession 同 object 跨 subject | medium |

**冲突动作** (`assert_fact(contradict_action=...)`):

* `"dispute"` (默认) — 旧 fact 降为 `disputed`, 新 fact 接管 `active`
* `"supersede"` — 旧 fact 标记 `superseded`, 写入 `superseded_by`
* `"keep_old"` — 新 fact 直接进 `disputed`, 旧保持

**时间线**: `location_at_tick(subject, tick)` 反查任意 tick 所在地;
乱序 assert 仍按 tick 升序维护。

Orchestrator 阶段 5b' 调用, 冲突翻译为 `[事实冲突 high]` 前缀注入 Narrator
recent_chapter_summaries, 强制不复述错误事实。持久化到
`data_dir/fact_ledger.json` 原子写。

### 人物弧光跟踪 (v2.5 新增)

> 不让角色长期 OOC — 7 阶段 ArcStage + 漂移检测 + B 级配角独立议程守护。

`backend/agents/character_arc_tracker.py` 提供 `CharacterArcTracker`:

**ArcStage 7 阶段** (`起点 → 觉醒 → 抗拒 → 挫折 → 转变 → 抉择 → 结局`)
对应 arc_progress 期待区间:

| Stage | arc_progress 区间 |
|-------|-------------------|
| 起点 | 0.00 – 0.15 |
| 觉醒 | 0.10 – 0.30 |
| 抗拒 | 0.25 – 0.50 |
| 挫折 | 0.40 – 0.65 |
| 转变 | 0.55 – 0.80 |
| 抉择 | 0.70 – 0.95 |
| 结局 | 0.85 – 1.00 |

**检测触发**:

| 触发码 | 条件 |
|--------|------|
| stalled | 同 stage 停留 ≥ 80 tick (结局态除外) → 自动升阶 |
| progress_mismatch | progress 不在 stage 期待区间 |
| B3 | B 级角色 `independent_agenda` 为空 |
| B1/B2/B4/B5/B6 | LLM 评估 (开启时), 引用 recent_actions 给证据 |

Orchestrator 阶段 7 调用 (CHARACTER_ARC_TRACKER_CADENCE 默认 30), 报告
通过 `_build_character_arc_hints()` 翻译为前缀提示 `[人物弧光]` /
`[漂移警告 alice]` / `[阶段推进 bob]` 注入 Narrator。

### 叙事大纲层 (v2.4 新增)

> 不让叙事漂流 — StoryArc 锚定主题, KeyBeat 锚定剧情骨架, PacingPoint 锚定节奏曲线。

`backend/agents/story_arc_director.py` 提供 `StoryArcDirector`:

| 输入 | 输出 (`StoryArcDirective`) |
|------|----------------------------|
| `StoryArc` (theme / beats / pacing_history) | `intensity_recommendation` (期望强度) |
| `current_tick` + `target_climax_tick` | `needs_escalation` / `needs_breather` |
| `recent_narrator_value_sum` | `active_beat_id` / `overdue_beats` |
| | `theme_reminder` / `narrator_hint` (≤30字) |
| | `suspense_pool_health` (4 档) |

**期待节奏曲线** (三幕剧 + 收尾抬升):

| progress | 期望强度 |
|----------|----------|
| 0%-10% | low (引子) |
| 10%-50% | medium (第一/二幕展开) |
| 50%-65% | high (危机) |
| 65%-80% | medium (黎明前的平静) |
| 80%-95% | high (高潮前奏) |
| 95%-100% | climax |

**异常触发**:
* 连续 ≥8 tick low → `needs_escalation=True` (EventInjector 兜底)
* 连续 ≥6 tick high → `needs_breather=True` (Showrunner 降温)
* `pending` beat 超过 window_end → `overdue_beats` 强制干预

Orchestrator 阶段 5c 调用, directive 注入 Narrator `recent_chapter_summaries`
作为前缀提示 (`[叙事大纲]` / `[本段提示]` / `[节奏建议]` / `[逾期节拍]`)。

### 优先级分层长期记忆 (v2.3 新增)

> 反 RAG 退化 — 不依赖朴素余弦相似, 多因子打分 + 防退化策略。

`backend/memory/memory_store.py` 提供 `PriorityMemoryStore`:

| 维度 | 公式 | 作用 |
|------|------|------|
| importance_eff | `importance × decay(ticks_since_access) + ref_bonus` | 重要性随时间衰减, 但高引用补偿 |
| recency | `5 / (1 + ticks_since / 100)` | 偏好近期, 但不抹掉远古 |
| char_overlap | `× 4.0` | 角色重叠加成 |
| tag_overlap | `× 3.0` | 情感/主题标签 |
| tier_proximity | L0=+1.0 / L1=+0.5 / L3=-0.5 | 分层近程 |
| protected | `+2.0 if is_protected` | open_loop / trauma / ref≥3 保护 |

防退化:
* `min_l0_or_l1` 强制保留近期层, 避免"全是 L3 传说"
* 同 involved + 邻近 tick 去重 (桶宽 20 tick)
* `replace_with_compressed` 升级时引用计数继承

Orchestrator 集成: 阶段 5 后自动 L0 入库, 阶段 6 后 `events_consumed`
触发 `touch()`, 阶段 7 整池压缩。Narrator 通过 `_build_long_term_memory_excerpts`
拿到 top-5 高优先级历史条目, 跨章节看见保护事件。

### 质量规范层 (v2.2 新增)

> 故事不是"生成",而是 **生成 → 批判 → 修订**。Narrator 每段产出后自动跑
> CRITIQUE → REVISE / REWRITE 循环,直到通过规范或触达上限。

| 模块 | 角色 |
|------|------|
| `backend/agents/quality_spec.py` | 单一真理源 — A-G 7 类 50+ 触发条件、AI 套话黑名单、陈词滥调黑名单、展示-非告诉对照表、决策矩阵 |
| `backend/agents/quality_checks.py` | 确定性 (无 LLM) 检测 — A1/A4/A6/A7/D2/D3/E1 |
| `backend/agents/narrative_critic.py` | CRITIQUE → REVISE / REWRITE 循环, 按 §2.1 决策矩阵迭代 |

**决策矩阵**:

| 触发情况 | 决策 |
|----------|------|
| ≥1 项高严重度 | **REWRITE** — 完全丢稿, 在节奏 / 感官 / 内外比例 / 句长 / 信息密度 至少一维度上切换 |
| 0 高 + ≥3 中 | **REVISE** — 外科手术式修订, 输出 diffs |
| 0 高 + ≤2 中 | **POLISH & ACCEPT** — 微调接受, 黑名单更新 |
| 全部通过 | **RED_TEAM** — 红队复查 (Showrunner/NoveltyCritic 层兜底) |

**环境开关**:

```bash
NARRATOR_ENABLE_CRITIC=1          # 显式开启 (留空时 pytest 关 / 生产开)
CRITIC_MAX_REVISE_ROUNDS=2        # 修订上限
CRITIC_MAX_REWRITE_ROUNDS=2       # 重写上限
CRITIC_ENABLE_LLM=1               # 0 时仅跑确定性检查
```

---

## 快速开始

### 1. 安装依赖

```bash
# Python(运行 + 测试)
pip install -r requirements-dev.txt

# 前端
cd frontend && npm install && cd ..
```

### 2. 配置 LLM 密钥

复制 `.env.example` → `.env`,填入 active provider 的密钥:

```bash
LLM_PROVIDER=deepseek          # deepseek | mimo | custom
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

(也可写到 `config.json` 兜底,但 `.env` 优先。)

### 3. 一键启动前后端

```bash
# Windows
start.bat

# macOS / Linux
./start.sh
```

或分别启动:

```bash
# 后端 (FastAPI, http://127.0.0.1:8762)
python run.py --reload

# 前端 (Vite, http://127.0.0.1:3143/)
cd frontend && npm run dev
```

> Vite dev server 自带 `/api` 代理到 8762;前端访问 backend 的 SSE 与 REST 无需配置 CORS。
> 端口可通过 `config.json` `server.backend_port` / `server.frontend_port` 修改。

### 4. 冷启动一个新世界

**推荐路径 (v2.25+ 任务化)**: 直接在前端 `HomeView` 创建小说, 填「世界种子」
(必填) 与折叠的「作品定位 / 参考作家」高级配置, 一次提交触发
`bootstrap_world → bootstrap_section` 两段任务, 在左下 `TaskListPanel` 看
4 阶段进度 + 后续字数进度。

**CLI 替代** (单租户开发模式, 跳过认证):

```bash
python -m backend.bootstrap_prompts \
    --novel-id mountain \
    --title "山阵" \
    --seed "宋代仿古,边境与中央的张力,存在低调方术传统" \
    --positioning "古典含蓄、心理白描、节奏舒缓" \
    --references "Le Guin / 古龙"
```

bootstrap 完成后:

```bash
curl -X POST http://127.0.0.1:8762/api/tick/run
curl http://127.0.0.1:8762/api/tick/status
curl http://127.0.0.1:8762/api/tick/history?last_n=20
```

或在前端 Tick 控制面板里手动推进、注入事件、查看 OpenLoop / 幻觉率诊断。

### 5. 生产部署 (SPA + API 同源)

```bash
cd frontend && npm run build && cd ..    # 产物在 frontend/dist/
python run.py                            # FastAPI 把 frontend/dist 挂到根 /
```

访问 `http://<host>:8762/` 即可 (v2.21 起 base 默认根路径)。三种部署方案:

* **Linux + systemd + Cloudflare Tunnel + Vercel** — `deploy/{backend,
  cloudflared,frontend}/README.md`
* **Windows + Docker Desktop + CF Tunnel (token 模式)** — `deploy/docker/README.md`
* 默认国内镜像源 (daocloud + 清华 PyPI/apt), 可通过 `.env` 切回官方

---

## API 速查

业务端点都经 `Depends(get_current_user)` 校验 JWT (v2.26+), 数据按
`(user_id, novel_id)` 隔离。管理 API (`/api/config/*` / `/api/tick/*` /
`/api/agents/*`) 默认无鉴权 — 仅适合本机/内网部署。

### 认证 (`/api/auth/*` — v2.26)
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/register/send-otp` | 注册前发邮箱 OTP (204, 一次性, 5 min TTL) |
| POST | `/register/verify` | 验证 OTP → JWT |
| POST | `/login/send-otp` | 登录发 OTP (枚举防御静默 204) |
| POST | `/login/verify-otp` | OTP 登录 → JWT |
| POST | `/login/password` | 密码登录 → JWT |
| POST | `/me/set-password` | 设置/更换密码 (bcrypt) |
| GET | `/me` | 当前用户信息 |
| PUT | `/me/settings` | `save_my_works` 等用户设置 |
| POST | `/logout` | 客户端清 JWT (服务端无 session) |

### 小说生命周期 (`/api/novels` — v2.25/v2.26)
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/novels` | 当前用户小说列表 |
| POST | `/api/novels` | 创建空壳 (默认 `auto_bootstrap=false`) |
| PUT | `/api/novels/{id}` | 改名 / 描述 (同步活跃 runtime title) |
| DELETE | `/api/novels/{id}` | 删除 |
| POST | `/api/novels/{id}/switch` | 切换活跃小说 (两阶段, tick 失败 503) |
| POST | `/api/novels/{id}/bootstrap-world` | 4 阶段冷启动 (`seed` 必填, 可链式触发首节) |

### 节驱动 (`/api/section` — v2.24)
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/section/generate` | 续写下一节, 入队任务 (返回 task_id) |
| GET | `/api/section/list` | tick 驱动节列表 |
| GET | `/api/section/list/{novel_id}` | 指定小说节列表 |

### Tick 控制 (`/api/tick/*`)
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/status` | 当前 tick / 暂停态 / OpenLoop 数 |
| POST | `/run` | 推进 1 个 tick (返回 TickSummary) |
| POST | `/pause` / `/resume` | 暂停 / 恢复后续自动循环 |
| POST | `/inject-event` | 手动注入 Event (422 校验 / 409 防 dup-id) |
| GET / POST / DELETE | `/open-loops{,/:id}` | 开放伏笔 CRUD (POST 防 dup-id 409) |
| GET | `/history?last_n=20` | 最近 N 个 TickSummary |
| GET | `/event-stats?last_n_ticks=50` | 事件统计 |
| GET | `/action-patterns?last_n_ticks=100` | 重复模式 |
| GET | `/style-anchors?top_k=20` | 风格锚点列表 |
| GET | `/character-states` | 全部 CharacterState |
| GET | `/novelty-warnings` | NoveltyCritic 输出 |
| GET | `/diagnostic/hallucination` | Guardian 幻觉率统计 + auto_degrade 状态 (v2.18 Phase 9) |

### 任务队列 (`/api/tasks/*` — v2.24)
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/tasks?novel_id=` | 全量任务集 |
| GET | `/api/tasks/{id}` | 单个任务快照 |
| POST | `/api/tasks/{id}/cancel` | 取消任务 |
| GET | `/api/tasks/{id}/stream` | SSE 实时进度 |

任务类型 (`TaskKind`): `section` / `bootstrap_section` / `bootstrap_world` /
`multimodal_generation`。

### 图像生成 (`/api/image` — v2.28)
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/image/generate` | 文生图 (header 带 `X-Image-AppID/APIKey/APISecret`, 后端用完即丢) |

### 多模态视频 (`/api/multimodal/*` — v2.33)
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/voices` | 中文 voice 白名单 |
| POST | `/segment-preview` | 分段预览 (不落盘) |
| POST | `/generate` | 入队多模态任务 (节文本 → 图 + TTS → 字幕视频) |
| GET | `/{novel_id}/list` | 已生成段列表 |
| GET | `/{novel_id}/{ch}/{s}/manifest` | 段 manifest |
| GET | `/{novel_id}/{ch}/{s}/asset/{filename}` | 段资产 (img/audio/srt/mp4) |

### LLM 辅助 (`/api/llm/*` — v2.26)
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/random-seed` | 随机世界种子 (X-User-LLM-* 一次性传 key) |
| POST | `/random-title` | 随机标题 (与 seed 联动客制化) |

### 配置 & 其他
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/stats` | 全局统计 |
| GET | `/api/config/llm` / PUT | LLM 配置查询/热更新 (原子写) |
| GET | `/api/graph` / `/api/graph/entities` / `/api/graph/relations` | KG 查询 (v2.34 优先读 tick KG) |
| GET / POST | `/api/snapshots` | KG 快照 |
| GET | `/api/agents{,/:id}` | Agent 上下文 (v2.20 诊断面板用) |
| POST | `/api/legacy/{generate,chapter/advance,rollback,reset,snapshots}` | 节级管线 (v2.24 别名) |

---

## 持久化分层

v2.26 起按用户隔离, 根路径 `backend/data/users/{uid}/novels/{nid}/` (被 `.gitignore`):

| 层 | 存储 | 内容 |
|----|------|------|
| 1 | SQLite WAL `ticks.db` | tick_log + events 两表, 按 tick_id 主键; `check_same_thread=False` + `threading.Lock` 串行化 (v2.26) |
| 2 | JSON `tick_state.json` | WorldState / CharacterProfile×N / OpenLoop / StyleAnchor / `novel_title` (v2.34) / AgentRuntimeState |
| 3 | JSON `summary_tree.json` | 分层摘要 + L3 传说 |
| 4 | NetworkX JSON `knowledge_graph.json` + `snapshots/` | 实体/关系图; tick 末尾从 char_states + world_state 自动同步 (v2.34); 每 50 tick 快照 |
| 5 | ChromaDB `chroma_db/` | 向量索引 (L0 事件 / L1 摘要) |
| 6 | 文本文件 `narratives/tick_NNNNNN.txt` | Narrator 产出 |
| 7 | JSON `sections/section_NNNN.json` | Tick 驱动节内容 (`TickSection`, v2.24) |
| 8 | `multimedia/sec_{ch}_{s}/` | `manifest.json` + `img_NN.png` + `audio_NN.mp3` + `subtitles.srt` + `output.mp4` (v2.33) |
| 9 | JSON `token_budget.json` / `fact_ledger.json` / `memory_store.json` | 全局账本 |

用户态认证数据落 `backend/auth.db` (SQLite); 默认无效会话 24h cleanup
后台 task 按 `save_my_works=False && last_accessed > 24h` 删除小说数据。

---

## 项目结构

```
novel_auto/
├── .env                              ← LLM 凭据 (优先来源)
├── config.json                       ← memory/vector/server/auth/smtp 配置 + LLM 兜底
├── config.example.json
├── run.py                            ← 根级启动入口 (uvicorn backend.main:app)
├── start.bat / start.sh              ← 一键启动后端 + 前端
├── requirements.txt / requirements-dev.txt
├── infinite-novel-multiagent-prompts.md ← 9 agent 设计 prompt 集
├── core/config.py                    ← 多 provider 路由, backend 通过 importlib 加载
├── memory_system/models.py           ← Pydantic v2 tick 契约
├── evaluation/continuity_v2.py       ← ConsistencyGuardian 复用
├── backend/                          ← FastAPI + 10 Agent + Tick 引擎
│   ├── main.py                       ← FastAPI 入口 + middleware + 静态资源 mount
│   ├── tick_runtime.py               ← Orchestrator + KG + 多租户注册表
│   ├── bootstrap_prompts.py          ← 4 阶段冷启动 (世界/角色/伏笔/风格)
│   ├── novel_manager.py              ← 多租户路径管理 + 路径安全 sanitizer
│   ├── cleanup_task.py               ← 24h 删除非保留小说的后台任务
│   ├── config/settings.py            ← 桥接 .env + config.json
│   ├── nf_core/                      ← LLM client + 行动解析 + Prompt 构建 +
│   │                                   reasoning_filter + json_utils +
│   │                                   text_segmenter + edge_tts_client +
│   │                                   video_composer + xfyun_image
│   ├── agents/                       ← Orchestrator / 10 个 Agent + 节级管线 5 个
│   │                                   (含 v2.24 SectionCloser)
│   ├── memory/                       ← TickState / SummaryTree / WorkingMemory /
│   │                                   PriorityMemoryStore
│   ├── persistence/                  ← TickDB (SQLite WAL, 跨线程互斥锁 v2.26)
│   ├── graph/                        ← KnowledgeGraph (NetworkX) + tick_kg_sync (v2.34)
│   ├── vector/                       ← VectorStore (ChromaDB)
│   ├── pipeline/                     ← 节级管线 (legacy, /api/legacy/*)
│   ├── auth/                         ← v2.26 邮箱 OTP + JWT + bcrypt + rate_limit
│   ├── tasks/                        ← v2.24 任务队列 (TaskManager + SSE)
│   ├── sections/                     ← v2.24 TickSection 存储
│   ├── multimedia/                   ← v2.33 多模态资产仓 (asset_store)
│   ├── middleware/                   ← v2.28 UserLLMHeadersMiddleware (纯 ASGI)
│   ├── narrative/                    ← branch_manager / safety_filter / fact_ledger /
│   │                                   creativity_scorer
│   ├── api/                          ← routes.py (核心 REST + 节级管线) +
│   │                                   tick_routes / section_routes /
│   │                                   bootstrap_routes / multimodal_routes /
│   │                                   image_routes / llm_routes / agent_routes
│   ├── data/users/{uid}/novels/{nid}/ ← 运行时数据 (gitignored, v2.26 起按用户隔离)
│   └── tests/                        ← 63 个测试文件, 541 用例
├── frontend/                         ← React + Vite 6
│   ├── vite.config.js                ← base=/, /api → 127.0.0.1:8762 proxy (强制 IPv4)
│   ├── src/
│   │   ├── App.jsx / main.jsx
│   │   ├── auth/                     ← AuthContext / LoginGate (v2.26)
│   │   ├── views/                    ← HomeView / NovelView / ConfigView /
│   │   │                                MultimodalView / AgentContextView
│   │   ├── components/               ← TaskListPanel / TickControlPanel /
│   │   │                                TickDiagnosticsPanel / GraphView /
│   │   │                                ControlPanel (legacy) / GeneratePanel /
│   │   │                                MemoryView / SectionsList
│   │   └── services/api.js           ← authedFetch + 6 多模态 + 任务 SSE
│   └── package.json
├── deploy/
│   ├── docker/                       ← Windows + Docker Desktop + CF Tunnel (token 模式)
│   ├── backend/                      ← Linux + systemd + nginx
│   ├── cloudflared/                  ← CF Tunnel (named tunnel + credentials.json)
│   └── frontend/                     ← Vercel (SPA rewrites + 安全头)
└── old/                              ← v1.x 归档 (不参与运行)
```

---

## 测试

541 用例 (v2.34) 全过, 全套 ~6 秒:

```bash
python -m pytest backend/tests/ -q
```

核心覆盖 (摘录 v2.20+ 新增, 完整 63 个文件见 `backend/tests/`):

| 测试文件 | 覆盖 |
|----------|------|
| `test_character_visibility.py` | `all_in_location` 矩阵 (v2.21) |
| `test_open_loop_origin_events.py` | OpenLoop 字段 + Narrator 解析 (v2.21) |
| `test_llm_config_fallback.py` | provider fallback 三优先级分支 (v2.21+Deploy) |
| `test_state_quarantine.py` | TickState / SummaryTree 损坏 quarantine (v2.21) |
| `test_tick_db_insert_ignore.py` | 重复 event_id / tick_id 不覆盖 (v2.21) |
| `test_switch_novel_two_phase.py` | tick 失败 503 路径 (v2.21) |
| `test_v2_22_p1_regressions.py` / `test_v2_22_p2_regressions.py` | provider 落盘 / UI 字段对齐 (v2.22) |
| `test_section_closer.py` | 切节判定 + 上限保护优先 LLM (v2.24) |
| `test_section_routes.py` / `test_section_store.py` | `POST /api/section/generate` + `TickSection` (v2.24) |
| `test_task_manager.py` | TaskManager 单例 + SSE 推送 (v2.24) |
| `test_main_wiring_v224.py` / `test_tick_runtime_registry.py` | per-novel/per-user runtime 装配 (v2.24) |
| `test_create_novel_bootstrap.py` / `test_bootstrap_routes.py` | `auto_bootstrap=False` 默认 + bootstrap-world 链式 (v2.25) |
| `test_auth_jwt.py` / `test_auth_otp.py` / `test_auth_password.py` / `test_auth_rate_limit.py` | 认证全栈 (v2.26) |
| `test_multi_tenant_isolation.py` | A 用户看不到 B 用户 novel (v2.26) |
| `test_llm_random_routes.py` | header key 流转 + 联动 prompt 客制化 (v2.26) |
| `test_text_segmenter.py` | 中文按句切, 段长 15-60 字 (v2.33) |
| `test_video_composer.py` | SRT 时间戳 / ffmpeg args / 字体样式 (v2.33) |
| `test_multimodal_security.py` | SSRF 白名单 / voice / 线程池并发 / 路径穿越 (v2.33) |
| `test_extract_message_text.py` | reasoning_content fallback 边界 (v2.34) |

(以及 v2.0–v2.19 时期的 40+ 个测试, 含 KG / Memory / Quality / TokenBudget /
StateOp / Hallucination / Chat-stream observability / inject-event validation /
open_loops admin / narrative_writer nonblocking / json_utils fence helper.)

> 真实 LLM smoke harness 不在单元测试里, 见
> [`scripts/smoke_v218.py`](./scripts/smoke_v218.py) 与
> [`scripts/smoke_v219.py`](./scripts/smoke_v219.py)。

---

## 配置参考

### LLM 提供商(`.env`)

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_PROVIDER` | `deepseek` | deepseek / mimo / custom |
| `LLM_MAX_TOKENS` | 8192 | 共享 max_tokens |
| `LLM_TEMPERATURE` | 0.7 | 共享 temperature |
| `LLM_TIMEOUT` | 120 | API 超时(秒) |
| `DEEPSEEK_*` | — | DeepSeek 配置 |
| `MIMO_*` | — | MiMo(小米)配置 |
| `CUSTOM_*` | — | 任意 OpenAI 兼容端点 |

### tick 行为

| 变量 | 默认 | 说明 |
|------|------|------|
| `ACTIVE_NOVEL_ID` | `default` | 当前小说 id (决定数据目录) |
| `ACTIVE_NOVEL_DATA_DIR` | — | 显式数据目录路径 (覆盖 ACTIVE_NOVEL_ID) |
| `MAIN_TRACKING_CHARACTER_ID` | — | Narrator 默认跟随的视角角色 |
| `NARRATOR_STRONG_MODEL_TICKS` | 100 | 前 N tick 用最强模型 |
| `CHARACTER_AGENT_CONCURRENCY` | 6 | Semaphore 并发上限 (v2.18 Phase 7) |
| `HALLUCINATION_AUTO_DEGRADE` | `0` | `1` 时 Guardian 超阈值自动写 `model_tier_override='haiku'` (v2.18 Phase 5) |
| `NARRATOR_ENABLE_CRITIC` | — | 显式开启 NarrativeCritic (留空时 pytest 关 / 生产开) |
| `LLM_BUDGET_MAX_TOTAL` / `LLM_BUDGET_MAX_PER_TICK` | — | token 预算上限, 持久化 `data_dir/token_budget.json` |
| `DISABLE_TICK_RUNTIME` | `0` | `1` 时禁用 tick runtime |
| `AGENT_HOST` / `AGENT_PORT` / `AGENT_RELOAD` / `AGENT_LOG_LEVEL` | — | uvicorn 配置 |

### 认证 & 多租户 (`config.json`, v2.26)

| 字段 | 说明 |
|------|------|
| `auth.enabled` | 启用 JWT + 多租户; 关闭后退回单租户 legacy 路径 |
| `auth.jwt_secret` | 建议 ≥ 64 字符随机串, 留空时启动期注入但每次重启 token 失效 |
| `auth.access_token_ttl_minutes` | JWT 有效期, 默认 60×24×7 |
| `auth.allow_registration` | 关掉可锁住新用户注册 (留邀请制 stub) |
| `smtp.host` / `port` / `username` / `password` / `from_addr` | OTP 邮件发送 (推荐腾讯企业邮箱 465 SSL) |

### 多模态 / 图像生成

| 变量 / 字段 | 说明 |
|------|------|
| `X-Image-Endpoint` / `X-Image-AppID` / `X-Image-APIKey` / `X-Image-APISecret` (header) | `POST /api/image/generate` 的一次性凭据, hostname 白名单校验 (v2.33) |
| `X-User-LLM-Key` / `X-User-LLM-Base-Url` / `X-User-LLM-Model` (header) | v2.28 起服务端 LLM 改读用户 key |
| `MULTIMODAL_VIDEO_CONCURRENCY` | `video_composer` 全局 `Semaphore`, 默认 2 |
| `TTS_VOICE` / `TTS_RATE` / `TTS_VOLUME` | edge-tts 默认参数 (在 `.env`) |

---

## 文档

* [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md)
  — 9 agent 完整 prompt 集 + 设计哲学 (必读)
* [`CHANGELOG.md`](./CHANGELOG.md) — 完整版本历史
* [`CLAUDE.md`](./CLAUDE.md) — Claude Code 工作指南
* [`backend/tests/`](./backend/tests/) — 63 个测试文件 / 541 用例, 即文档
* [`deploy/README.md`](./deploy/README.md) — Linux+systemd / Docker / Vercel
  三段式部署
* [`old/docs/`](./old/docs/) — v1.x 历史规划文档 (MIGRATION / IMPLEMENTATION_PLAN / ...)

---

## 故障排除

### `/api/tick/*` 返回 503

后端未启动或未 bootstrap:

```bash
curl http://127.0.0.1:8762/api/health     # 1. 检查后端是否在跑
python run.py --reload                    # 2. 启动后端
python -m backend.bootstrap_prompts --novel-id test --seed "..."   # 3. bootstrap 一个世界
```

### Narrator 总是沉默 (`narrator_produced_text=false`)

设计如此 — 事件总价值 <5 时 Narrator 跳过。若长期沉默:

* 通过 `/api/tick/inject-event` 注入高 `narrative_value` 事件
* 检查 `/api/tick/open-loops` 是否 ≥3
* 在前端 Tick 控制面板的"手动注入事件"表单输入戏剧事件

### 后端启动失败

确认 `config.json` 存在:

```bash
cp config.example.json config.json
```

`backend/config/settings.py` 优先桥接 `.env` 的 active provider,config.json 只在 .env 不可用时兜底。

### 终端乱码 (Windows)

```bash
chcp 65001
```

---

## 许可证

仅供学习与研究使用。
