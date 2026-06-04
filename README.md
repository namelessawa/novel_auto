# 无限小说生成系统 (Infinite Novel Generator)

> **当前版本: v2.19.6** (2026-06-04) — FastAPI + React/Vite 单栈,
> 9 Agent + 7 阶段 Tick 调度的多智能体模拟系统(故事驱动)。
> 设计哲学来自 [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md):
> **故事是模拟的副产品,Narrator 选择性讲述**。

> v1.x 章节驱动单体生成器已整体归档到 [`old/`](./old/),
> 不再参与运行时,但可作为历史参考。

> **状态**: 343 用例 GREEN, 真实 LLM smoke (mimo-v2.5-pro / DeepSeek) 端到端
> 通过。完整版本历史见 [`CHANGELOG.md`](./CHANGELOG.md)。

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

### 9 个 Agent + 7 阶段 Tick 循环

| # | Agent | 频率 | LLM | 职责 |
|---|-------|------|-----|------|
| 0 | **Orchestrator** | 每 tick | ❌ 纯调度 | 协调 7 阶段流程 |
| 1 | **WorldSimulator** | 每 tick | ✅ small | 推进时间/天气/社会演化 |
| 2 | **EventInjector** | 3-5 tick | ✅ medium | 内生/外生/戏剧事件注入 |
| 3 | **CharacterAgent×N** | 每 tick | ✅ A=strong / B=medium | 单角色基于 known_facts 决策 |
| 4 | **ActionResolver** | 每 tick | ❌ 纯逻辑 | 解析独占行动冲突 |
| 5 | **Narrator** | 每 tick | ✅ strongest→medium | 选材 + 写作,可主动沉默 |
| 6 | **Showrunner** | 每 5 tick | ✅ medium | 节奏曲线 + 冷线索 + 弧线监控 |
| 7 | **MemoryCompressor** | 每 50 tick | ✅ small | L0→L1→L2→L3 压缩 + 传说化 |
| 8 | **ConsistencyGuardian** | 每 30 tick | ✅ continuity_v2 | 5 类矛盾扫描 |
| 9 | **NoveltyCritic** | 每 20 tick | ✅ small | 重复模式检测,反馈 Narrator |

### v2.10 – v2.19 增量概览

下表为后续 10 个版本的功能落地索引, 详情见 [`CHANGELOG.md`](./CHANGELOG.md):

| 版本 | 主线 | 关键落地点 |
|------|------|-----------|
| v2.10 | TickRuntime 全装配 | 把 v2.3-v2.9 全部增强层显式注入 `tick_runtime.py`, FastAPI 启动即享受全部能力 |
| v2.11 / v2.12 / v2.13 / v2.14 | 质量层实测迭代 | 基于真实 MIMO 输出修正 A1 误报、A4/A6/A7 黑名单、句长 E1 与段末升华禁忌 |
| v2.15 | P0 sweep | 并发统一入口 / 路径安全 sanitizer / 记忆 touch 闭环 / runtime 注册表显式校验 |
| v2.16 | 硬状态转移 + 可观测性 | `CharacterAction` 落 location/inventory/status/relationship 字段; 18 个 LLM 调用点标注 `agent_id+priority`; 中文输出约束; 多地点冷启动 |
| v2.17 | runtime coherency sweep | LLM 配置热更新 (`PUT /api/config/llm` + `LLMClient.reload`); TokenBudget 调用前硬拦截; Tick 控制台前端; CodeQL path-injection / clear-text-logging 全部切断 |
| **v2.18** | **状态硬转移 + Guardian 闭环 + tick 并行化** | 9 个 Phase: money_delta / `AgentRuntimeState` cooldown / `StateOp+StatePatch` / `scan_hallucination_rate` / Guardian shadow mode / `model_tier_override` / concurrency 3→6 + Narrator 并行 / EventInjector 产 patch / `GET /api/tick/diagnostic/hallucination` |
| **v2.19** | **流式闭环 + 输入校验 + IO 优化** | `chat_stream` 接入 budget+observability+model_override; `inject-event` 加 422/409 边界; `POST /api/tick/open-loops` 防 dup-id 覆盖; `_default_narrative_writer` 卸 IO 到 worker 线程; `chat_stream` 异常路径也记账; LLM JSON fence helper 集中到 `nf_core.json_utils` |

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

# 前端 (Vite, http://127.0.0.1:3143/nw/)
cd frontend && npm run dev
```

> Vite dev server 自带 `/api` 代理到 8762;前端访问 backend 的 SSE 与 REST 无需配置 CORS。
> 端口可通过 `config.json` `server.backend_port` / `server.frontend_port` 修改。

### 4. 冷启动一个新世界

```bash
python -m backend.bootstrap_prompts \
    --novel-id mountain \
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

也可在前端 Tick 控制面板里手动推进、注入事件、查看 OpenLoop。

### 5. 生产部署(SPA + API 同源)

```bash
cd frontend && npm run build && cd ..    # 产物在 frontend/dist/
python run.py                            # FastAPI 自动 mount frontend/dist 到 /nw/
```

访问 `http://<host>:8762/nw/` 即可。`deploy/` 下提供了 nginx 与 systemd 样例。

---

## tick API 速查

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/tick/status` | 当前 tick / 暂停态 / OpenLoop 数 |
| POST | `/api/tick/run` | 推进 1 个 tick (返回 TickSummary) |
| POST | `/api/tick/pause` | 暂停后续自动循环 |
| POST | `/api/tick/resume` | 恢复 |
| POST | `/api/tick/inject-event` | 手动注入 Event |
| GET | `/api/tick/open-loops` | 开放伏笔列表(按 urgency 降序) |
| POST | `/api/tick/open-loops` | 管理员手动新增 OpenLoop |
| DELETE | `/api/tick/open-loops/:id` | 关闭 OpenLoop |
| GET | `/api/tick/history?last_n=20` | 最近 N 个 TickSummary |
| GET | `/api/tick/event-stats?last_n_ticks=50` | 事件统计 |
| GET | `/api/tick/action-patterns?last_n_ticks=100` | 重复模式 |
| GET | `/api/tick/style-anchors?top_k=20` | 风格锚点列表 |
| GET | `/api/tick/character-states` | 全部 CharacterState |
| GET | `/api/tick/novelty-warnings` | NoveltyCritic 输出 |

---

## 持久化分层

| 层 | 存储 | 内容 |
|----|------|------|
| 1 | SQLite WAL `ticks.db` | tick_log + events 两表,按 tick_id 主键 |
| 2 | JSON `tick_state.json` | WorldState / CharacterProfile×N / OpenLoop / StyleAnchor / novelty_warnings |
| 3 | JSON `summary_tree.json` | 分层摘要 + L3 传说 |
| 4 | NetworkX JSON `knowledge_graph.json` + `snapshots/` | 实体/关系图 + 每 50 tick 快照 |
| 5 | ChromaDB | 向量索引(L0 事件 / L1 摘要) |
| 6 | 文本文件 `narratives/tick_NNNNNN.txt` | Narrator 产出 |

所有数据存放在 `backend/data/novels/{novel_id}/`(被 `.gitignore`)。

---

## 项目结构

```
novel_auto/
├── .env                              ← LLM 凭据(优先来源)
├── config.json                       ← memory/vector/server 配置 + LLM 兜底
├── config.example.json
├── run.py                            ← 根级启动入口 (uvicorn backend.main:app)
├── start.bat / start.sh              ← 一键启动后端 + 前端
├── requirements.txt / requirements-dev.txt
├── infinite-novel-multiagent-prompts.md ← 9 agent 设计 prompt 集
├── core/
│   ├── __init__.py
│   └── config.py                     ← 多 provider 路由,backend 通过 importlib 加载
├── memory_system/
│   ├── __init__.py
│   └── models.py                     ← Pydantic v2 tick 契约 + 遗留 dataclass
├── evaluation/
│   ├── __init__.py
│   └── continuity_v2.py              ← ConsistencyGuardian 复用
├── backend/                          ← FastAPI + 9 Agent + Tick 引擎
│   ├── main.py                       ← FastAPI 入口 + 静态资源 mount
│   ├── tick_runtime.py               ← Orchestrator 单例
│   ├── bootstrap_prompts.py          ← 5 prompt 冷启动
│   ├── novel_manager.py
│   ├── config/settings.py            ← 桥接 .env + config.json
│   ├── nf_core/                      ← LLM client + ActionResolver + PromptBuilder
│   ├── agents/                       ← Orchestrator / 9 个 Agent + 节级管线 5 个
│   ├── memory/                       ← TickState / SummaryTree / WorkingMemory
│   ├── persistence/                  ← TickDB (SQLite WAL)
│   ├── graph/                        ← KnowledgeGraph (NetworkX)
│   ├── vector/                       ← VectorStore (ChromaDB)
│   ├── pipeline/                     ← 节级管线
│   ├── api/                          ← routes.py (节级 REST+SSE) + tick_routes.py
│   ├── data/novels/{id}/             ← 运行时数据(gitignored)
│   └── tests/                        ← 50 个测试
├── frontend/                         ← React + Vite 6
│   ├── index.html
│   ├── vite.config.js                ← base=/nw/, /api → 8762 proxy
│   ├── src/
│   │   ├── App.jsx / main.jsx
│   │   ├── pages/ components/ services/ styles/
│   └── package.json
├── deploy/                           ← nginx / systemd 样例
└── old/                              ← v1.x 归档(不参与运行)
    ├── docs/                         ← IMPLEMENTATION_PLAN / MIGRATION / ...
    ├── core/ memory_system/          ← v1 生成器与记忆模块
    ├── experimental/ utils/ tests/   ← 实验性 / 工具 / 旧测试
    ├── multimedia/ results/ vercel/ public/ views/ temp/
    ├── frontend_express/             ← v1 Express+ejs 前端
    ├── agent_backend/                ← v2 subprocess 启动器(已被 run.py 替代)
    └── create_novel.py / continue_novel.py / main.py / validate_system.py
```

---

## 测试

343 用例 (v2.19.6) 全过,全套 ~6 秒:

```bash
python -m pytest backend/tests/ -q
```

核心覆盖 (摘录, 完整列表见 `backend/tests/`):

| 测试文件 | 覆盖 |
|----------|------|
| `test_knowledge_graph.py` | KnowledgeGraph CRUD + 快照 + 回滚 |
| `test_working_memory.py` | WorkingMemory ring buffer + eviction |
| `test_summary_tree_persistence.py` | 持久化 + 原子写 + legendize 兜底 |
| `test_tick_state.py` | TickState + OpenLoop reap + arc_status |
| `test_action_resolver.py` | 冲突解析 (tier / goal priority) + 败者状态清零 |
| `test_orchestrator_p0.py` / `test_orchestrator_p1.py` | 全链路 + EventInjector / Showrunner cadence / NoveltyCritic |
| `test_prompt_builder.py` | Token 预算 + 优先级裁剪 |
| `test_quality_spec.py` | A-G 触发条件 + 决策矩阵 + NarrativeCritic 4 路径 |
| `test_memory_store.py` | PriorityMemoryStore CRUD / 多因子打分 / 防退化 / 保护机制 |
| `test_story_arc_director.py` / `test_character_arc_tracker.py` | StoryArc + CharacterArc 检测与建议 |
| `test_fact_ledger.py` | 事实账本 / 矛盾检测 / 时间线索引 |
| `test_token_budget_safety.py` | TokenBudgetTracker 决策矩阵 + SafetyFilter PII/harm 规则 |
| `test_creativity_scorer.py` | 词汇/结构/情感滑窗 + 退化警报 |
| `test_branch_manager.py` | 分支 fork/archive/tree/canonical 切换 |
| `test_v217_coherency_sweep.py` | LLM 热更新 / TokenBudget 拦截 / tick 默认 novel 对齐 |
| `test_agent_runtime_state.py` | AgentRuntimeState 模型 + 持久化 (v2.18 Phase 2) |
| `test_state_patch.py` | StateOp / StatePatch 校验 + Orchestrator 应用 (v2.18 Phase 3) |
| `test_consistency_guardian_hallucination.py` | scan_hallucination_rate 边界 (v2.18 Phase 4) |
| `test_hallucination_observation.py` | Guardian → AgentRuntimeState shadow 与 active (v2.18 Phase 5) |
| `test_model_tier_override.py` | LLMClient/CharacterAgent/Orchestrator 闭环 (v2.18 Phase 6) |
| `test_concurrency_phase7.py` | concurrency 3→6 + Narrator/只读 agent 并行 (v2.18 Phase 7) |
| `test_event_injector_state_patches.py` | EventInjector 产 StatePatch (v2.18 Phase 8) |
| `test_hallucination_diagnostic_api.py` | `GET /api/tick/diagnostic/hallucination` (v2.18 Phase 9) |
| `test_chat_stream_observability.py` | chat_stream budget + observability + 异常记账 (v2.19 / v2.19.5) |
| `test_inject_event_validation.py` | inject-event 422/409 边界 (v2.19.1) |
| `test_open_loops_admin_api.py` | POST /api/tick/open-loops dup-id 防护 (v2.19.3) |
| `test_narrative_writer_nonblocking.py` | `_default_narrative_writer` 卸 IO (v2.19.4) |
| `test_json_utils.py` | LLM fence helper 边界 (v2.19.6) |

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
| `ACTIVE_NOVEL_ID` | `default` | 当前小说 id(决定数据目录) |
| `ACTIVE_NOVEL_DATA_DIR` | — | 显式数据目录路径(覆盖 ACTIVE_NOVEL_ID) |
| `MAIN_TRACKING_CHARACTER_ID` | — | Narrator 默认跟随的视角角色 |
| `NARRATOR_STRONG_MODEL_TICKS` | 100 | 前 N tick 用最强模型 |
| `CHARACTER_AGENT_CONCURRENCY` | 3 | Semaphore 并发上限 |
| `DISABLE_TICK_RUNTIME` | `0` | `1` 时禁用 tick runtime |
| `AGENT_HOST` / `AGENT_PORT` / `AGENT_RELOAD` / `AGENT_LOG_LEVEL` | — | uvicorn 配置 |

---

## 文档

* [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md)
  — 9 agent 完整 prompt 集 + 设计哲学(必读)
* [`CHANGELOG.md`](./CHANGELOG.md) — 完整版本历史
* [`CLAUDE.md`](./CLAUDE.md) — Claude Code 工作指南
* [`backend/tests/`](./backend/tests/) — 50 个测试,即文档
* [`old/docs/`](./old/docs/) — v1.x 历史规划文档(MIGRATION / IMPLEMENTATION_PLAN / ...)

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
