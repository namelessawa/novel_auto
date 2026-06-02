# 项目结构 (structure.md)

> 本文档描述项目具体结构分布,随每轮迭代同步更新。
> 版本: v2.2 · 2026-06-03

---

## 顶层目录

```
novel_auto/
├── backend/                  # FastAPI + 9 Agent + 7 阶段 Tick 调度
├── frontend/                 # React 18 + Vite (base=/nw/)
├── core/                     # 多 provider LLM 路由 (.env → active provider)
├── memory_system/            # Pydantic v2 tick 契约 + 遗留 dataclass
├── evaluation/               # ConsistencyGuardian 复用的 continuity_v2 评估器
├── deploy/                   # nginx + systemd 单机部署模板
├── old/                      # v1.x 章节驱动单体生成器归档 (只读)
├── tools/                    # 辅助 CLI / 一次性脚本
├── results/                  # 生成结果留档目录
├── temp/                     # 临时文件
├── infinite-novel-multiagent-prompts.md   # 9-agent 架构设计源
├── infinite_novel_iteration_prompt.md     # 自我迭代 Prompt v1
├── novel_quality_critique_and_iteration.md  # 质量评估 & 迭代规范 v1.1
├── CHANGELOG.md
├── CLAUDE.md                 # Claude Code 项目指令
├── README.md
├── structure.md              # 本文件
├── config.json               # LLM 兜底配置 (.env 优先)
├── config.example.json
├── requirements.txt          # 运行时依赖
├── requirements-dev.txt      # 测试依赖
├── run.py                    # 后端入口 (uvicorn backend.main:app)
├── start.bat / start.sh      # 一键启动前后端
└── bash.exe.stackdump        # (无关, MSYS 临时)
```

---

## `backend/` 关键模块

```
backend/
├── main.py                   # FastAPI 入口 + 静态资源 mount + lifecycle
├── tick_runtime.py           # Orchestrator + TickState + TickDB 单例容器
├── bootstrap_prompts.py      # 5 prompt 冷启动 CLI (世界/角色/伏笔/风格锚点)
├── api/
│   ├── routes.py             # 节级管线 REST + SSE (legacy 节级管线)
│   ├── tick_routes.py        # 14 条 tick 控制 REST
│   └── agent_routes.py       # (P2 占位) agent 配置 / 诊断 REST
├── agents/                   # 9 + 4 Agent 实现
│   ├── orchestrator.py       # 7 阶段调度器, 纯 Python
│   ├── world_simulator.py    # ① 推进时间/天气/社会
│   ├── event_injector.py     # ② 内生/外生/戏剧事件注入
│   ├── character_agent.py    # ③ 单角色基于 known_facts 决策, 并行 batch
│   ├── narrator_agent.py     # ⑤ 选材 + 写作 + critic 循环 (v2.2)
│   ├── showrunner.py         # ⑥ 节奏曲线 + 冷线索 + 弧线监控
│   ├── memory_compressor.py  # ⑦ L0→L1→L2→L3 压缩 + 传说化
│   ├── consistency_guardian.py # ⑧ 5 类矛盾扫描
│   ├── novelty_critic.py     # ⑨ 重复模式检测
│   ├── writer_agent.py       # legacy 节级 writer, v2.2 注入质量规范
│   ├── outline_agent.py      # legacy 节级 planner
│   ├── retrieval_agent.py    # legacy 节级 retrieval
│   ├── update_agent.py       # legacy 节级 知识图更新
│   ├── validation_agent.py   # legacy 节级 validation
│   ├── quality_spec.py       # ★ v2.2 质量规范单一真理源
│   ├── quality_checks.py     # ★ v2.2 确定性触发检测
│   └── narrative_critic.py   # ★ v2.2 CRITIQUE → REVISE/REWRITE 循环
├── config/
│   └── settings.py           # .env + config.json 双源配置
├── memory/
│   ├── tick_state.py         # TickState — Pydantic v2 dump 原子写
│   └── summary_tree.py       # 分层摘要树 (L0-L3) + 持久化
├── nf_core/
│   ├── llm_client.py         # OpenAI SDK 包装, streaming + JSON mode
│   ├── action_resolver.py    # 纯 Python 行动冲突解析
│   └── prompt_builder.py     # Token 自适应裁剪
├── persistence/
│   └── tick_db.py            # SQLite WAL (tick_log + events 两表)
├── data/
│   └── novels/<novel_id>/    # tick_state.json + summary_tree.json
│                             # + ticks.db + narratives/tick_NNNNNN.txt
│                             # + knowledge_graph.json + chroma_db/
└── tests/                    # 69 用例, ~2.3s 全过
    ├── conftest.py           # mock_llm fixture + sys.path 注入
    ├── test_action_resolver.py
    ├── test_knowledge_graph.py
    ├── test_orchestrator_p0.py
    ├── test_orchestrator_p1.py
    ├── test_prompt_builder.py
    ├── test_quality_spec.py  # ★ v2.2 19 用例
    ├── test_summary_tree_persistence.py
    ├── test_tick_state.py
    └── test_working_memory.py
```

---

## v2.2 质量规范层 (本轮新增)

```
backend/agents/
├── quality_spec.py           # 静态规范 (50+ 触发 + 黑名单 + prompt 片段)
│   ├── TRIGGER_RULES         # A-G 7 类全量
│   ├── HIGH_SEVERITY_CODES
│   ├── AI_CLICHE_BLACKLIST   # 28 条 A4 自动触发
│   ├── CLICHE_BLACKLIST      # 28 条 D3 自动触发
│   ├── SHOW_DONT_TELL_EXAMPLES
│   ├── decide_action()       # 决策矩阵
│   └── render_*_block()      # prompt 片段渲染
├── quality_checks.py         # 确定性 (无 LLM) 触发检测
│   ├── check_ai_cliche_blacklist  # A4
│   ├── check_cliche_blacklist     # D3
│   ├── check_word_repetition      # A1
│   ├── check_adjective_runs       # D2
│   ├── check_summary_ending       # A6 (高)
│   ├── check_opening_repetition   # A5/A7
│   ├── check_sentence_rhythm      # E1
│   └── run_deterministic_checks   # 一次性入口
└── narrative_critic.py       # LLM-driven CRITIQUE → REVISE/REWRITE 循环
    ├── NarrativeCritic
    │   ├── critique_and_iterate    # 主入口, 至多 2+2 轮
    │   ├── _llm_critique           # LLM 语义判定 (B/C/F/G 多数项)
    │   ├── _llm_revise             # 外科手术式修订, 输出 diffs
    │   └── _llm_rewrite            # 完全丢稿重写 + 维度切换
    ├── CritiqueOutput              # final_text / rounds / triggers / trail
    └── CRITIC_SYSTEM_PROMPT / REVISE_SYSTEM_PROMPT / REWRITE_SYSTEM_PROMPT
```

集成路径:

```
Narrator.narrate()
  ├─ 1. _effective_value() 评估事件总分
  ├─ 2. 决定篇幅 (short/medium/long)
  ├─ 3. LLM 写作 (NARRATOR_SYSTEM_PROMPT 内嵌质量规范)
  ├─ 4. _parse_output() 解析 JSON
  └─ 5. _run_critique()             ← v2.2 新增
        └─ NarrativeCritic.critique_and_iterate()
              ├─ run_deterministic_checks()   # A1/A4/A6/A7/D2/D3/E1
              ├─ _llm_critique()              # LLM 语义判定
              ├─ decide_action()              # 决策矩阵
              ├─ _llm_revise() or _llm_rewrite()
              └─ 循环直到 ACCEPT / 触达上限
```

---

## 数据流 (一次 tick)

```
TickState  ── 阶段 1 ──→  WorldSimulator           → 新 WorldState + natural events
   ▲                              │
   │            阶段 2:   EventInjector + Showrunner  → 注入事件
   │                              │
   │            阶段 3:   CharacterAgent × N (并行)   → CharacterAction
   │                              │
   │            阶段 4:   ActionResolver              → 解冲突
   │                              │
   │            阶段 5:   _apply_actions              → CharacterState 更新 + action events
   │                              │
   │            阶段 6:   Narrator                    → narrative text
   │                            └─ NarativeCritic (v2.2 CRITIQUE → REVISE/REWRITE)
   │                              │
   └────────── 阶段 7:   MemoryCompressor / ConsistencyGuardian / NoveltyCritic (周期性)
                                  │
                          TickDB (SQLite WAL)
                                  │
                          narratives/tick_NNNNNN.txt 落盘
```

---

## 路径常量约定

* backend 内大多数模块通过 `sys.path.insert` 把 `backend/` 和项目根加入路径,
  然后用裸 import: `from agents.X`, `from memory.tick_state`,
  `from memory_system.models`
* 入口脚本 (`run.py` / `bootstrap_prompts.py` / `tests/conftest.py`) 负责设置
  sys.path
* 不要在 backend 子模块里写 `from backend.X` — 保持原有的裸 import 风格

## 配置优先级

```
.env  ──→  core/config.py:get_active_llm_config()  ──→  backend/config/settings.py
                                                              ▲
                                                              │ 兜底
                                                       config.json (根级)
```

## 持久化

| 数据 | 位置 | 格式 |
|------|------|------|
| TickState | `backend/data/novels/<id>/tick_state.json` | Pydantic v2 dump (原子写) |
| SummaryTree | `backend/data/novels/<id>/summary_tree.json` | 层级 JSON (原子写) |
| Tick 日志 | `backend/data/novels/<id>/ticks.db` | SQLite WAL (tick_log + events) |
| 知识图 | `backend/data/novels/<id>/knowledge_graph.json` | NetworkX node-link |
| 向量索引 | `backend/data/novels/<id>/chroma_db/` | ChromaDB 持久化 |
| 叙述文本 | `backend/data/novels/<id>/narratives/tick_NNNNNN.txt` | 纯文本 |

---

## 迭代历史 (高层)

| 版本 | 日期 | 主题 |
|------|------|------|
| v2.0 | 2026-04 | 9 Agent + 7 阶段 Tick 架构落地 |
| v2.1 | 2026-06-02 | 双栈融合为单进程, v1.x → `old/` |
| **v2.2** | **2026-06-03** | **质量规范层 — CRITIQUE → REVISE / REWRITE 循环嵌入 Narrator** |

后续路线 (`TaskList` 跟踪):

* 阶段 6: 长期记忆与一致性强化 (分层记忆 + 优先级机制)
* 阶段 7: 叙事大纲与节奏控制 (全局大纲 + 主题锚点 + 悬念蓄水池)
* 阶段 8: 人物弧光与配角独立性 (动机栈 + 弧光阶段 + 说话风格指纹)
* 阶段 9: 事实/时间线/世界设定一致性 (事实账本 + 时间线索引 + 矛盾检测器)
* 阶段 10: 性能与体验 (token 预算调度 + 流式输出)
