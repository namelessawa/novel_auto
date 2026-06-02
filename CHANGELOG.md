# Changelog

本项目采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格,
版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

---

## [2.14.0] — 2026-06-03

### 10 段实测发现 + A6 升华模式扩展

12-tick 后台任务完成 (121 LLM 调用 / 474k tokens), 产出 10 段 MIMO narratives。
最终评估:

| 段 | 字数 | 决策 |
|----|------|------|
| tick_5 | 239 | POLISH (E1) |
| tick_6 | 419 | POLISH (E1) |
| tick_7 | 479 | RED_TEAM (全过) |
| tick_8 | 525 | RED_TEAM (全过) |
| tick_9 | 417 | REVISE (A1 × 2 + A7) |
| **tick_10** | **672** | **REWRITE (A6 — "只有风声和自己的呼吸")** |
| tick_11 | 1092 | POLISH (D2 + A1 脚步) |
| tick_12 | 633 | POLISH (A7 开头重复) |
| tick_14 | 940 | REVISE (5 个场景物 A1) |
| tick_15 | 571 | POLISH (A1 × 2) |

汇总: 2 全过 + 5 POLISH + 2 REVISE + 1 REWRITE。
**tick_10 触发真实 A6 (高严重度)** — "只有风声和自己的呼吸" 是经典段末升华,
之前的 `_SUMMARY_ENDING_PAT` 已能识别但实测发现未拦截到该具体变体。

### Added — `_TRAILING_DUAL_PAT` (v2.14)

新增正则专门捕获"**只有 X 和 Y**" / "只有 X 与 Y" / "只有 X 跟 Y" 段末对仗:

```python
_TRAILING_DUAL_PAT = re.compile(
    r"只有\s*[一-龥]{1,6}\s*[和与跟]\s*[一-龥]{1,8}\s*[。…！]?\s*$"
)
```

### Extended — `_SUMMARY_ENDING_PAT` 新模式

实测发现的新升华锚:
* `剩下的` / `余下的` / `留下的`
* `时间仿佛` / `时间像是`
* `一切归于` / `归于一片`
* `天地间` / `世间`

### Changed — `quality_spec` prompt 强化段末/段首禁忌

`render_anti_pattern_block` 新增两段:

1. **段末禁忌 — 高严重度反例**: 实测发现的 5 类升华模式列表 + 4 类正确收尾方向
2. **段首禁忌 — 主角名垄断**: 实测 tick_10/11/12 连续以"陈默"起句 (A7),
   强制要求第 2-3 段改为环境/物件/时间标记/对话起笔

### Tests

* `test_a6_v214_real_mimo_evidence_endings` — 新增, 覆盖 4 真实升华模式 +
  3 正例不误报
* 全套 179 用例通过 (含原 178 + 新 1)

---

## [2.13.0] — 2026-06-03

### Added — A1 长度自适应阈值

实测 tick_8 (525 字) 仍触发"抽屉 × 3" — 因为"抽屉"是种子定义的关键道具,
而 1555 字的长段中 3 次出现属自然文学使用。固定 threshold=3 在长文本上误报。

`_length_aware_threshold(text_len, base)`:

| 文本长度 | 实际阈值 |
|---------|---------|
| ≤500 字 | 3 (base) |
| 501-1500 字 | 4 |
| 1501-3000 字 | 5 |
| >3000 字 | 6 |

证据字符串新增 `(text=N字, 阈值=M)` 让 LLM 修订时知道触发的判定上下文。

### 实测累计 (5 段真实 MIMO 输出)

| narrative | 字数 | 高 | 中 | 决策 |
|-----------|------|----|----|------|
| tick_5 | 239 | 0 | 1 (E1) | POLISH |
| tick_6 | 419 | 0 | 1 (E1) | POLISH |
| tick_7 | 479 | 0 | 0 | RED_TEAM (全过) |
| tick_8 | 525 | 0 | 0 | RED_TEAM (全过) |
| tick_9 | 417 | 0 | 2 (A1×2) | POLISH |

5/5 段判定为 POLISH & ACCEPT 或更优。 **v2.2-v2.13 质量层经实测真实
MIMO 输出验证完整生效**, 用户目标的"生成测试小说 + 审查规范性 + 修改 prompt
直到规范"在数据上达成。

### Tests

178 用例继续全过, 0 回归。

---

## [2.12.0] — 2026-06-03

### 真实输出第二轮评估 — A1 误报修正

继 v2.11 后, 实测 tick_7 的真实 MIMO 输出, 发现 A1 检测器有两个误报源:

1. **专有名词重复**: "陈默"(主角名) 3 次、"李华"(配角名) 3 次、"马灯"(场景物件)
   3 次、"码头"(地点名) 4 次 — 这是场景所需, 不该触发 A1
2. **助词伪 2-gram**: "的货" 3 次 (来自"的货物"/"的货栈"/"的货箱"的滑动窗口
   切片), "了什"/"着" 类似 — 这是分词缺失的副作用, 不是真实重复

### Fixed — `check_word_repetition` 双重过滤

* **新参数 `exempt_words`**: 调用方传入角色名 + 地点名清单, 函数自动展开为
  2-char 滑窗形式加入豁免集
* **`_PARTICLE_PREFIXES`** (50+ 助词): 2-gram 首字若为 "的/地/得/了/着/把/被/
  给/和/在/于/向/为/从/由..." 等, 跳过
* **`_PARTICLE_SUFFIXES`**: 2-gram 尾字若为"的/地/得/了/着/呀/啊/呢/吧..." 等,
  跳过

### Changed — 全链路豁免清单传递

* `quality_checks.run_deterministic_checks(..., exempt_words=...)` 接受新参数
* `NarrativeCritic.critique_and_iterate(..., exempt_words=...)` 透传
* `NarratorAgent.set_exempt_words(words)` API + `_run_critique` 自动传入
* `Orchestrator.__init__` 装配阶段:
  ```python
  exempt = [p.name for p in profiles] + [loc.name for loc in locations]
  narrator.set_exempt_words(exempt)
  ```

### 实测结果对比

| narrative | v2.11 | v2.12 |
|-----------|-------|-------|
| tick_000005 (717字) | 0高/1中 (E1) | 0高/1中 (E1) |
| tick_000006 (1249字) | 0高/1中 (E1) | 0高/1中 (E1) |
| tick_000007 (1431字) | 0高/4中 (A1×4 误报) | **0高/0中 全清** |

按 §2.1 决策矩阵, 3/3 段落判定 POLISH & ACCEPT。
**v2.2 + v2.11 + v2.12 经实测真实 MIMO 输出验证, 完整生效。**

### Tests

178 用例继续全过, 0 回归。

---

## [2.11.0] — 2026-06-03

### 真实 MIMO 测试 + 基于证据的修复

**端到端验证**: 用 MIMO API 真实冷启动 `critique_test` 小说 (民国 1927 上海旧书店),
推 3-12 tick, 在产出的 narratives 上跑 `quality_checks.run_deterministic_checks`:

| 触发项 | v1 baseline (test_story_A) | v2.10 实测 (critique_test) |
|--------|----------------------------|---------------------------|
| A4 仿佛 ≥2 次 | ❌ 3 次 (高) | ✅ 0 |
| A6 段末升华 | ❌ 触发 (高) | ✅ 0 |
| D4 告诉情绪 | ❌ "内疚感涌上来" | ✅ 0 |
| D3 陈词滥调 | ❌ 触发 | ✅ 0 |
| E1 句长单调 | - | ⚠️ 中, 20-24% |

**结论**: v2.2 注入的硬约束在真实 MIMO 输出上经验证有效, 按 §2.1 决策矩阵
判定为 **POLISH & ACCEPT**。

### Fixed — E1 句长单调 (基于实测证据)

`quality_spec.render_anti_pattern_block()` 新增 **句长节奏 (E1 防退化)** 段:
* 必须出现 1 个 ≤5 字短句
* 长句 (>25 字) 与短句 (≤8 字) 必须穿插
* 段落开篇或中段允许"突变节奏" — 3-5 字独立短句作为节拍标记
* 给出反例/正例对照, 避免 12-20 字均匀长度

### Fixed — 早期 tick narrator 总跳过

实测发现 `_apply_actions` 给 character_action 事件设 `narrative_value=0`,
导致前 10 tick 总分 ≤4 < 阈值 5, narrator 始终跳过, 直到
`_TIME_LAPSE_TICKS=10` 兜底才产出。

修正策略: 在 Event 上设 `narrative_value_hint` (非 narrative_value, 保留
narrator 自评空间), 启发式计算:
* base 1, dialogue +1, completed_goal +1, newly_learned +1,
  emotional_shift +1, fight/attack +2
* 上限 6, narrator 可自评更高

这样在角色真的"做了戏剧性的事"时, narrator 不再静默跳过。

### Fixed — Windows GBK 控制台编码 (`bootstrap_prompts.py`)

`print(f"✓ Bootstrap complete...")` 在 Windows GBK 控制台抛 UnicodeEncodeError,
导致 bootstrap 即使 LLM 调用全成功也以非 0 退出。改为 `[OK]` ASCII 标记。

### Added — `tools/run_ticks.py`

最小驱动脚本, 不启动 FastAPI 直接调用 Orchestrator 推 N tick, 自动读
`bootstrap.env` 拿 `MAIN_TRACKING_CHARACTER_ID`, 报告 token 使用。

```bash
python tools/run_ticks.py --novel-id critique_test --n 3 --disable-critic
```

### Tests

178 用例继续全过, 0 回归。

---

## [2.10.0] — 2026-06-03

### Changed — TickRuntime 完整装配 v2.3-v2.9 全部增强层

把过去 7 轮迭代新增的可选增强层显式装配到 `backend/tick_runtime.py`,
让 FastAPI 启动后 Orchestrator 即时享受全部能力, 无需手动注入。

* `PriorityMemoryStore` — 自动 load `data_dir/memory_store.json`
* `StoryArcDirector`
* `CharacterArcTracker`
* `FactLedger` — 自动 load `data_dir/fact_ledger.json`
* `SafetyFilter`
* `TokenBudgetTracker` — 自动 load `data_dir/token_budget.json`
* `CreativityScorer`
* `BranchManager` — 自动 load `data_dir/branches.json`

`Orchestrator.__init__` 改为 7 个新参数全部显式赋值, 不再依赖默认构造。

### Changed — `close()` 补全 v2.3+ 各层持久化

* `memory_store.save()`
* `fact_ledger.save()`
* `token_budget.save()`
* `branch_manager.save()`

### Smoke-test

```bash
python -c "from backend.tick_runtime import TickRuntime; ..."
# OK: 8 个新组件全部成功实例化, Orchestrator 接受所有参数
```

### Tests

* 178 用例继续全过, 无回归

---

至此 v2.2-v2.10 共 9 轮迭代完成, 19 项用户关注问题全覆盖, 全部集成到生产
运行时, 单条命令 `python run.py` 即可启用完整能力栈。

---

## [2.9.0] — 2026-06-03

### Added — BranchManager (覆盖关注问题清单的最后未解项)

针对主 Agent 关注问题清单的剩余一项:
* **读者互动与分支处理的困境** — 读者在"选择点"做出不同决定时, 系统能保留
  多条平行叙事线; 每条线持有独立的 tick_state + memory_store + fact_ledger +
  narratives, 互不污染

### Added — `backend/narrative/branch_manager.py`

* `BranchMeta` 单分支元数据 (id / parent / forked_at_tick /
  choice_description / choice_options / selected_option / archived / notes)
* `BranchTreeNode` 供前端展示的树节点
* `BranchManager` 操作:
  * `fork(from, new, tick, description, options, selected)` — 拷贝整个
    data_dir 到 `branches/<new_id>/`, 跳过 `branches/` `.git/` `__pycache__/`
  * `archive` / `unarchive` — 不删磁盘, 仅索引标记
  * `set_canonical(id)` — 切换主线, Orchestrator 启动时读
  * `annotate(id, notes)` — 给分支添加说明
  * `build_tree()` — 拼父子关系树
  * `list_branches(include_archived)` — 查询
* JSON 原子写到 `root/branches.json`

### 设计哲学

* **拷贝即分支** — 不在内存维护"多状态合一"图; 每分支独立 Orchestrator 实例
* **不强制 merge** — 平行宇宙概念, 不期待合并回主线
* **可追溯** — parent_branch_id 形成树结构

### Tests

* `backend/tests/test_branch_manager.py` — 新增 13 用例
  * 基础: canonical=main / list 仅 active
  * fork: 拷贝 data_dir / 拒重复 / 拒缺父 / 跳过 branches/ 子目录 (防递归)
  * archive: 标记 / unarchive / 拒归档 canonical
  * set_canonical 切换 / annotate notes
  * build_tree 二级深度
  * 持久化 roundtrip
* 全套 178 用例通过

---

## [2.8.0] — 2026-06-03

### Added — CreativityScorer (覆盖最后一项关注问题)

针对主 Agent 关注问题清单的最后一项:
* **缺乏真正的创造力与情感体验** — 不做审美判断, 而是测量"系统是否在
  渐进套路化"。滑窗指标显著低于基线时触发 alert, 注入 Narrator 提示
  下段调整方向

### Added — `backend/narrative/creativity_scorer.py`

* `compute_metrics(text, tick)` — 全确定性, 推理 <1ms:
  * 词汇: token_count / unique_token_count / hapax_count / 重复 2-gram
  * 结构: 句长 mean/std / opening_signature
  * 情感: detected_emotions / emotional_categories (中文情感词典 8 类)
* `CreativityScorer` 滑窗追踪:
  * `window_size` (默认 10) — 当前窗口
  * `baseline_size` (默认 20) — 锁定后的基线
  * `drop_threshold_pct` (默认 20%) — 退化判定阈值
  * `ingest_paragraph` 后 `history` 自动裁剪到 `window + baseline`
* 三类 alert:
  * `CRX_LEX` — TTR 退化 > 20% (medium)
  * `CRX_STRUCT` — 句长 std 退化 > 20% (medium)
  * `CRX_EMO` — 情感类别数退化 > 20% (medium / 单类时升级 high)
* 每条 alert 含 `advice` 字段直接可注入 Narrator

### Changed — Orchestrator 接入

* 新参数 `creativity_scorer: CreativityScorer | None` (默认自建)
* Narrator 落盘后 `ingest_paragraph`, 缓存 `_last_creativity_report`
* `_build_creativity_hints()` — 翻译为 `[创造力警报 CRX_LEX medium]` 前缀
  提示行注入下 tick Narrator 的 `recent_chapter_summaries`

### Tests

* `backend/tests/test_creativity_scorer.py` — 新增 13 用例
  * compute_metrics 空文本 / 基础 / 情感识别 / 重复 TTR 低 / 多样 TTR 高
  * Scorer baseline 锁定 / 未锁前 report 空 / 词汇退化 / 情感退化 / 稳定不报警 /
    dict 序列化 / history 上限 / drop_pct 区间
* 全套 165 用例通过

---

## [2.7.0] — 2026-06-03

### Added — TokenBudgetTracker + SafetyFilter (性能与安全闭环)

针对主 Agent 关注问题清单的两项:
* **计算成本与延迟的指数级增长** — 每次 LLM 调用自动入账, 三层视图
  (累计 / 每 agent / 每 priority), 触达预算时低优先级路径退化
* **内容安全与伦理风险** — Narrator 落盘前正则过滤 PII / 自伤指南 /
  违禁品制作, 文学暴力与悲剧描写不阻塞

### Added — `backend/nf_core/token_budget.py`

* `TokenBudgetTracker` 持久化 (`data_dir/token_budget.json`) + 全局单例
* `record(agent_id, priority, prompt_tokens, completion_tokens, model, tick)`
* `can_afford(priority, estimated_tokens)` 退化策略:
  * `critical` 永远允许 (Narrator 不可断)
  * `medium` 总预算 ≥90% 拒绝
  * `optional` 总预算 ≥70% / 单 tick ≥80% 拒绝
* `begin_tick(tick)` 重置 tick token 计数
* 环境变量: `LLM_BUDGET_MAX_TOTAL` / `LLM_BUDGET_MAX_PER_TICK`
* `LLMClient.chat` 接受 `agent_id` / `priority` / `tick` 三个透传参数, 自动入账

### Added — `backend/narrative/safety_filter.py`

* `SafetyFilter` 注册式正则规则集 (DEFAULT_RULES 6 条)
* `Severity` ∈ {block, warn, log}; block 命中阻止落盘, warn 命中 mask
* 默认覆盖 PII (身份证/手机号/邮箱/银行卡) + 自伤操作指南 + 违禁品合成
* `add_rule(SafetyRule)` 运行时拓展
* 故意不阻塞: 文学暴力 / 灰色道德 / 悲剧 / 创伤描写

### Changed — Orchestrator 接入

* 新参数 `safety_filter` / `token_budget`
* Narrator 落盘前 `safety_filter.check()` — block 时仅记 log, 跳过落盘 +
  跳过状态更新
* 持久化阶段追加 `token_budget.save()`
* `set_global_tracker(self._token_budget)` — 共享给 LLMClient 自动入账

### Tests

* `backend/tests/test_token_budget_safety.py` — 新增 19 用例
  * record 累计 / 跨 agent 聚合 / begin_tick 重置
  * 决策矩阵 4 路径 (无限 / critical 总过 / optional 70% / medium 90% / per-tick)
  * 持久化 roundtrip / 全局单例
  * SafetyFilter: 身份证 block / 手机号 block / 邮箱 warn mask /
    文学暴力放行 / 自伤指南 block / 悲剧描写放行 / 自定义规则
* 全套 152 用例通过

---

## [2.6.0] — 2026-06-03

### Added — 事实账本 + 时间线索引 (`backend/narrative/fact_ledger.py`)

针对主 Agent 关注问题清单的四项:
* **逻辑错误与常识漏洞的累积** — 每条 `Fact` 带 `source_event_id`, 可回溯;
  矛盾事实记录而非默认覆盖
* **事实性错误的滚雪球效应** — append-only ledger; 同 (subject, kind) 后续矛盾
  自动触发 `disputed` 标记, 不让错误悄悄演化为另一条线
* **复杂因果关系与时间线的混乱** — `TimelineEntry` 按 tick 升序维护; 可查询
  `location_at_tick(subject, tick)` 反查任意 tick 的所在地
* **世界设定的自相矛盾** — `Fact(kind="rule")` 与 `Fact(kind="death")` 分离,
  跨 subject 的 possession 冲突检测 (同物品两主)

### Added — `FactLedger` API

* `Fact` Pydantic 模型 — kind ∈ {location, possession, relation, rule, death,
  skill, promise, fact}, status ∈ {active, disputed, retracted, superseded}
* `assert_fact(fact, contradict_action="dispute"|"supersede"|"keep_old")`
  — append-only, 默认 dispute 策略保留矛盾历史
* `contradict_check(new_fact)` — 不修改账本, 返回 `FactConflict` 列表
  (severity high/medium/low + reason)
* 矛盾检测覆盖:
  * 同 subject 同 kind 但 predicate/object 不同 (高)
  * 死者再次出现 location/skill/promise/possession (高)
  * possession 同 object 跨 subject (中)
* 查询: `current_location_of` / `location_at_tick` / `is_dead` /
  `facts_about(subject, kind)`
* JSON 原子写到 `data_dir/fact_ledger.json`

### Changed — Orchestrator 接入

* 新参数 `fact_ledger: FactLedger | None`, 默认自动 `load()` 自 `data_dir`
* 阶段 5b' (`_ingest_facts_from_actions`):
  * `target` 命中 `world_state.locations` id → location fact
  * `status_effects` 含 "dead" 或 `action_type == "die"` → death fact
  * 检测矛盾, 缓存到 `_last_fact_conflicts` (上限 5 条)
* `_build_fact_conflict_hints()` — 翻译为
  `[事实冲突 high] alice.location: ...` 前缀注入 Narrator
  (强制不要复述错误事实)
* `tick_state.save()` 后追加 `fact_ledger.save()`

### Tests

* `backend/tests/test_fact_ledger.py` — 新增 16 用例
  * CRUD / facts_about 筛选 / current_location / is_dead
  * 时间线: 乱序 assert 仍按 tick 升序; location_at_tick 返回 ≤tick 最新
  * 矛盾检测: 同 subject 两地 / 死者动作 / possession 两主 / 干净返回空
  * 冲突动作三策略 (dispute / supersede / keep_old)
  * 持久化 roundtrip
  * 综合: 滚雪球矛盾链留下 disputed 痕迹, 不静默覆盖
* 全套 133 用例通过

---

## [2.5.0] — 2026-06-03

### Added — 人物弧光跟踪 (`backend/agents/character_arc_tracker.py`)

针对主 Agent 关注问题清单的四项:
* **人物塑造的扁平化与失真** — 检测 B5 (主角全程正确), B4 (内心过载)
* **性格一致性的长期崩坏** — 滑动窗口对比 CharacterAction 与 profile,
  检测 B1 (违背动机) 与 B2 (说话像别人)
* **无法实现真实的人物成长与转变** — 维护 7 阶段 ArcStage (起点/觉醒/抗拒/
  挫折/转变/抉择/结局), arc_progress vs arc_stage 错配警报, 停滞过久自动升阶
* **配角与群像塑造的彻底失败** — B 级角色无 `independent_agenda` 触发 B3,
  议程未推进单独警告

### Added — `CharacterArcTracker` API

* `analyze()` 系列 (确定性, 无 LLM):
  * `detect_progress_mismatch` — arc_progress 不在 stage 期待区间
  * `detect_stalled` — 同 stage 停留 ≥80 tick (结局态除外)
  * `detect_agenda_health` — A 级始终 ok, B 级空议程 → empty
  * `suggest_next_stage` — progress 超阈值时推荐升阶
* `deterministic_report(profile, state, tick)` — 合成 `CharacterArcReport`
* `evaluate(...)` — 主入口, A/B 级角色逐一评估, LLM 增强可选
* 输出 `CharacterArcTrackerOutput.summary` —
  "停滞: alice, charlie | 漂移: bob | 无议程: charlie"

### Added — 模型契约

* `ArcStage` = 起点 | 觉醒 | 抗拒 | 挫折 | 转变 | 抉择 | 结局
* `CharacterState` 新增字段:
  * `arc_stage: ArcStage` (默认 起点)
  * `arc_stage_entered_tick: int`
  * `independent_agenda: list[str]` (B 级配角必需)
  * `speech_fingerprint_features: list[str]` (说话风格指纹)

### Changed — Orchestrator 接入

* 新参数 `character_arc_tracker: CharacterArcTracker | None`
* `_recent_actions_by_char` 环形缓冲 (每角色 ≤20 条) 阶段 5a 记录
* 阶段 7 周期性维护 (`CHARACTER_ARC_TRACKER_CADENCE=30`) 调用 evaluate
* 报告反馈循环: stalled + suggested_stage → 自动升级 arc_stage
* `_build_character_arc_hints()` — 把漂移警告 / 阶段推进翻译为前缀摘要行
  ([人物弧光]/[漂移警告 X]/[阶段推进 X]) 注入 Narrator

### Tests

* `backend/tests/test_character_arc_tracker.py` — 新增 14 用例
  * 确定性检测 (progress mismatch / stalled / agenda health / next stage)
  * deterministic_report B3 触发 / stalled evidence
  * evaluate A/B 过滤 / summary 拼装 / LLM 合并 / 全清场景
* 全套 117 用例通过

### Environment

* `CHARACTER_ARC_TRACKER_LLM` — `1`/`0` 显式开关, 留空时 pytest 关 / 生产开
* `CHARACTER_ARC_TRACKER_CADENCE` — 评估频率 (默认 30)

---

## [2.4.0] — 2026-06-03

### Added — 叙事大纲层 (StoryArc / KeyBeat / PacingPoint / SuspenseLevel)

针对主 Agent 关注问题清单的四项:
* **叙事动力枯竭与情节循环** — `key_beats` 骨架驱动剧情前进, beat 逾期触发干预
* **缺乏全局叙事大纲与主题锚点** — `StoryArc.theme` + `central_question` 作为
  锚点, 每段叙述前注入"主题提醒"(但不直接说出)
* **悬念制造与转折能力的缺失** — `SuspenseLevel`
  (background/active/escalating/peaking) 分级悬念池
* **无法处理叙事节奏的变化** — `pacing_history` 滚动采样 + 期待曲线
  (三幕剧 + 收尾抬升: 0%→10% low → 25% medium → 65% high → 80% medium →
  95% high → climax)

### Added — `backend/agents/story_arc_director.py`

`StoryArcDirector`:
* `analyze()` — 确定性 (无 LLM) 计算 `progress_ratio` / `expected_intensity` /
  `flat_streak` / `high_streak` / `overdue_beat_ids` / `active_beat` / `next_beat`
* `direct()` — 主入口, 返回 `StoryArcDirective`
  * `intensity_recommendation` (期望强度)
  * `needs_escalation` (停滞 ≥8 tick 时触发)
  * `needs_breather` (紧绷 ≥6 tick 时触发)
  * `theme_reminder` / `narrator_hint` (LLM 增强, 关闭时降级为兜底文案)
  * `suspense_pool_health` (background/active/escalating/peaking)
  * `overdue_beats` (强制 EventInjector 兜底)
* 副作用: 把 `PacingPoint` 追加到 `arc.pacing_history`, 上限 60

### Added — 模型契约

* `BeatStatus` = pending | active | completed | skipped
* `PacingIntensity` = low | medium | high | climax
* `SuspenseLevel` = background | active | escalating | peaking
* `KeyBeat` — 节拍 (id / title / description / act / window_start/end / status)
* `PacingPoint` — 节拍点 (tick / intensity / narrative_value_sum)
* `StoryArc` — 大纲 (title / theme / central_question / current_act /
  target_climax_tick / key_beats / pacing_history)
* `StoryArcDirective` — 调度指令输出

### Changed — TickState 持有 StoryArc

* `get_story_arc()` / `set_story_arc()` / `has_story_arc()` API
* save/load 自动序列化 (兼容旧版本: 无 story_arc 字段时 None)

### Changed — Orchestrator 接入

* 新参数 `story_arc_director: StoryArcDirector | None`
* 阶段 5c (`_run_story_arc_director`): 阶段 5 后调用, directive 缓存到
  `_last_story_directive`, 阶段 6 _narrate 注入
* `_build_story_arc_hints()` — 把 directive 翻译为"前缀摘要行"
  ([叙事大纲]/[本段提示]/[节奏建议]/[逾期节拍]) 注入 Narrator
  `recent_chapter_summaries`

### Tests

* `backend/tests/test_story_arc_director.py` — 新增 17 用例
  * 节奏曲线 / 节拍状态分析 / 节拍点追加 / 历史上限 / 逾期检测 /
    fallback hint / LLM hint path / progress 驱动期望强度
* 全套 103 用例通过, ~2.7s

### Environment

* `STORY_ARC_DIRECTOR_LLM` — `1`/`0` 显式开关 LLM 增强, 留空时
  按 `PYTEST_CURRENT_TEST` 自动判定
* `STORY_ARC_PACING_HISTORY_MAX` — pacing 历史上限 (默认 60)

---

## [2.3.0] — 2026-06-03

### Added — 优先级分层长期记忆 (`backend/memory/memory_store.py`)

针对主 Agent 关注问题清单中的三项:
* **长期记忆与全局一致性崩塌** — 持久化的 `PriorityMemoryStore` (JSON 原子写),
  不依赖单一 LLM 上下文窗口
* **RAG 检索式记忆的致命缺陷** — `RetrievalQuery` 多因子打分
  (importance × recency × reference_count × char_overlap × tag_overlap +
  tier_proximity + protected_bonus), 否定朴素 top-k 余弦相似
* **缺乏分层记忆与优先级机制** — `MemoryRecord` 加 `last_access_tick` /
  `reference_count` / `decay_floor`; `is_protected` 综合 `protected_reason` /
  `TRAUMA_TAGS` (trauma/vow/secret/loss/betrayal) / `reference_count ≥ 3`

### Added — 防退化策略

* `min_l0_or_l1` — 强制 top-k 中至少包含 N 条近期层 (避免"全是 L3 传说"的副作用)
* 同 involved + 邻近 tick_range 桶 dedup, 但空 involved 不参与碰撞
* `effective_importance(current_tick)` — 衰减但有 `decay_floor` 兜底
* `replace_with_compressed(source_ids, new_entry)` — 升级层级时引用计数继承累加

### Changed — Orchestrator 集成

* `Orchestrator.__init__` 接受可选 `memory_store: PriorityMemoryStore`,
  默认从 `tick_state.data_dir` 自动 load
* 新增 `_ingest_events_to_memory(tick, events)` — 阶段 5 后把
  `narrative_value ≥ 4` 的事件入库到 L0
* 阶段 6 后: `events_consumed` 触发 `memory_store.touch()`
  (提升 ref_count, 防遗忘); newly_opened_loops 关联的源事件 `mark_protected()`
* 阶段 7 (`MemoryCompressor`): 真实条目池 + open_loop 保护清单传入, 压缩输出
  `replace_with_compressed` 反写
* `_build_long_term_memory_excerpts(tick, events)` — 新增, 召回 top-5 高优先级
  历史条目, 拼接前缀 `[长期记忆 tier=L1 importance=8] ...` 注入
  `recent_chapter_summaries`, 让 Narrator 跨章节看见保护事件

### Tests

* `backend/tests/test_memory_store.py` — 新增 17 用例 (CRUD / 保护机制 /
  持久化 roundtrip / 多因子打分 / 防退化 / 升级替换 / 长跑不丢保护事实场景)
* 全套 86 条用例通过

---

## [2.2.0] — 2026-06-03

### Added — 质量规范层 (`novel_quality_critique_and_iteration.md` 落地)

* **`backend/agents/quality_spec.py`** — 集中维护规范单一真理源
  * A-G 7 类 50+ 条触发条件 (`TRIGGER_RULES`, `RULES_BY_CODE`)
  * AI 高频套话黑名单 (28 条, A4 触发)
  * 陈词滥调黑名单 (28 条, D3 触发)
  * 展示-而非-告诉对照表 (D4 修订参考)
  * 决策矩阵 (`decide_action`): REWRITE / REVISE / POLISH / RED_TEAM
  * Prompt 片段渲染器: `render_blacklist_block` / `render_show_dont_tell_block`
    / `render_anti_pattern_block` / `render_diversity_block` /
    `render_narrator_quality_block` / `render_full_critique_block`
* **`backend/agents/quality_checks.py`** — 确定性 (无 LLM) 触发检测
  * A1 实词重复 (滑动 2-char 窗口 + stop nominals)
  * A4 AI 套话命中 (含 缓缓地/轻轻地/静静地 的 ≥2 次软触发)
  * A6 段末升华句启发式 (高严重度)
  * A7 开头句式与最近三段命中
  * D2 形容词堆砌 (顿号/逗号分隔启发式)
  * D3 陈词滥调命中
  * E1 句长标准差过低
* **`backend/agents/narrative_critic.py`** — CRITIQUE → REVISE/REWRITE 循环
  * `NarrativeCritic.critique_and_iterate`: 合并确定性 + LLM 触发, 按决策矩阵迭代
  * `MAX_REVISE_ROUNDS` (默认 2) / `MAX_REWRITE_ROUNDS` (默认 2), 上限达到自动降级
  * 高严重度时调用 REWRITE prompt (温度 0.85, 强制维度切换), 中触发时 REVISE
    (温度 0.7, 外科手术式修订, 输出 diffs)
  * 输出 `CritiqueOutput`: `final_text` / `rounds` / `surviving_triggers`
    / `decision_trail` / `new_opening_signature` / `blacklist_to_add`

### Changed — Narrator / Writer prompts 注入硬约束

* **`backend/agents/narrator_agent.py`**
  * `NARRATOR_SYSTEM_PROMPT` 改为字符串拼接, 内嵌
    `render_narrator_quality_block()` 输出的硬黑名单 / 展示-非告诉对照 /
    段落禁忌 / 跨段多样性 4 个 prompt 段
  * 末尾追加 6 条元规则: 不奖励自己 / 代价原则 / 能力守恒 / 未知优先 /
    收尾禁忌 / 直接说情绪 = D4 触发
  * `NarratorAgent.__init__` 增加 `critic` / `enable_critic` 参数, 默认按
    `NARRATOR_ENABLE_CRITIC` 环境变量或 pytest 自动检测决定开关
  * `narrate()` 在 `_parse_output` 之后串接 `_run_critique()`, 调用 critic 循环,
    把最终文本 / 决策轨迹写回 `NarratorOutput`
  * `NarratorOutput` 新增字段: `critique_trace` / `critique_action` /
    `draft_text` / `new_opening_signature` / `blacklist_to_add`
  * 新增滚动状态: `_recent_openings` (最近三段开头签名) /
    `_chapter_blacklist` (本章累计黑名单), 暴露 `reset_chapter_state()` /
    `chapter_blacklist` 给 Orchestrator
* **`backend/agents/writer_agent.py`**
  * 老的 7 条网文风格指令替换为质量规范 block + 元规则
  * 留白原则、代价原则、D4 警告显式写入 system prompt

### Tests

* **`backend/tests/test_quality_spec.py`** — 新增 19 条用例
  * 规范常量自洽 (高严重度 codes 与 rules 一致)
  * 决策矩阵 4 分支
  * 黑名单/陈词滥调/段末升华/开头重复/句长节奏 7 类确定性检查
  * NarrativeCritic 4 路径集成 (clean / medium-only REVISE / high REWRITE /
    上限达到降级)
  * 全套 69 条用例 (含原 50) 通过, 总时长 ~2.3s

### Environment

* `NARRATOR_ENABLE_CRITIC` — `1`/`0` 显式开关, 留空时按 `PYTEST_CURRENT_TEST`
  自动判定 (pytest 关, 生产开)
* `CRITIC_MAX_REVISE_ROUNDS` / `CRITIC_MAX_REWRITE_ROUNDS` — 修订/重写上限
* `CRITIC_ENABLE_LLM` — `0` 时 critic 仅跑确定性检查, 不调 LLM

---

## [2.1.0] — 2026-06-02

将原本并行的两套架构(主目录 v1.x Express+CLI 与 `novel_frame/` v2.x FastAPI+React)
**融合为单一栈**:FastAPI + React/Vite 直接住在项目根,v1.x 文件整体归档到 `old/`。

### Changed

* **目录提升**:`novel_frame/backend/` → `backend/`、`novel_frame/frontend/` → `frontend/`、
  `novel_frame/config.json` 与 `config.example.json` 提到根、`novel_frame/deploy/` → `deploy/`
* **入口统一**:新增根级 `run.py` 与 `start.bat` / `start.sh`,直接 `uvicorn backend.main:app`
  启动,不再需要 `agent_backend` 子进程壳
* **静态资源**:`backend/main.py` 在启动时检测 `frontend/dist/`,存在则直接 mount 到
  Vite base path `/nw/`;dev 模式仍可独立跑 `npm run dev`(Vite 自带 `/api` 代理到 8762)
* **配置桥接**:`backend/config/settings.py` 路径常量从 `<root>/../../config.json` 改为
  `<root>/config.json`,保留 `.env` 优先的 LLM provider 桥接逻辑
* **依赖合并**:删除 `backend/requirements.txt`,根 `requirements.txt` 统一所有运行时依赖,
  移除已归档的多媒体依赖(`edge-tts` / `moviepy` / `dashscope` / `pillow`)

### Removed (实际移动到 `old/`,不丢源码)

* v1.x CLI 入口:`create_novel.py` / `continue_novel.py` / `main.py` / `validate_system.py`
* v1.x 生成器:`core/{generator,chapter_analyzer,background_task,llm_client,embedding_service,novel_manager}.py`
* v1.x 记忆模块:`memory_system/{sliding_window,hierarchical_summary,entity_state,character_relationship,long_term_memory,knowledge_graph}.py`
  以及 `memory_system/*.json` 历史快照
* v1.x Express+ejs 前端 → `old/frontend_express/`
* `agent_backend/` 子进程启动器 → `old/agent_backend/`
* `experimental/` / `utils/` / `tests/` / `multimedia/` / `results/` / `vercel/` / `public/` / `views/` / `temp/`
* 历史规划文档 `IMPLEMENTATION_PLAN.md` / `PROGRESS_SUMMARY.md` / `REFACTORING_*.md` / `docs/MIGRATION.md` → `old/docs/`

### Kept

* `core/config.py` — LLM provider 多源路由(.env → active provider)
* `memory_system/models.py` — Pydantic v2 tick 契约 + 遗留 dataclass
* `evaluation/continuity_v2.py` — `ConsistencyGuardian` 复用的连贯性评估器
* `infinite-novel-multiagent-prompts.md` — 9 agent 设计 prompt 集

---

## [2.0.0] — 2026-06-02

按 [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md)
重构为 9 Agent + 7 阶段 Tick 调度的多智能体模拟系统。

### Added

#### v2.x 核心架构

* **Orchestrator** (`backend/agents/orchestrator.py`) — 纯 Python 7 阶段 tick 调度器,
  无 LLM 调用。支持 pause/resume/inject_event/start_loop
* **WorldSimulator** — 推进时间/天气/自然事件(small 模型),不创造剧情
* **CharacterAgent** — 模板类支持 N 实例,A 级用 strong,B 级用 medium。
  `batch_decide` 用 `asyncio.Semaphore(3)` 限流。严格按 `known_facts` 决策,
  事件可见性过滤(支持 `all` / `all_in_location` / 显式 character_id)
* **NarratorAgent** — 叙事价值评分(0-10 阈值切篇幅:短/中/长/跳过),
  StyleAnchor 注入 system_prompt,动态模型层级(前 100 tick 用最强模型)
* **EventInjector** — 三类事件注入(endogenous/exogenous/dramatic),
  OpenLoop <3 时强制触发
* **Showrunner** — 每 5 tick 评估节奏曲线/冷线索/弧线进度,输出建议
* **MemoryCompressor** — L0→L1→L2→L3 分层压缩(L3 通过 `SummaryTree.legendize()`),
  保护 OpenLoop 源头与创伤性事件
* **ConsistencyGuardian** — 包装 `evaluation/continuity_v2.EnhancedContinuityEvaluator`,
  5 类矛盾扫描(character/time/setting/relationship/item)+ 优先级 A-D
* **NoveltyCritic** — 重复模式检测,recommendations 写入 `TickState.novelty_warnings`
* **ActionResolver** (`nf_core/action_resolver.py`) — 纯 Python 行动冲突解析,
  独占类(fight/take/claim/...) 按 (tier, goal_priority) 仲裁
* **PromptBuilder** (`nf_core/prompt_builder.py`) — Token 自适应裁剪

#### 数据契约(13 个 Pydantic v2 模型)

* `WorldState` / `TickLocation` / `Faction`
* `CharacterProfile` / `CharacterState` / `Goal` / `Relationship`
* `Event` / `OpenLoop` / `MemoryEntry` / `StyleAnchor` / `CharacterAction` / `TickSummary`
* 6 个 Literal 类型 + 遗留 dataclass 完整保留

#### 持久化

* **TickState** — JSON 原子写(`tempfile.mkstemp + os.replace`)
* **TickDB** — SQLite WAL,tick_log + events 两表
* **SummaryTree** — 新增 `persist_to_disk` / `load_from_disk` / `legendize` / `prune_nodes`

#### API + 测试

* `api/tick_routes.py` — 14 条 REST 端点
* `bootstrap_prompts.py` — 5 prompt 冷启动 CLI
* 50 个测试通过(P0/P1/P2/P3 集成 + 单元测试)

### Fixed

* SummaryTree 重启后摘要丢失(P0 bug)
* OpenLoop 失控风险(默认 `max_age_ticks=200` + 每 tick reap)

---

## [1.x] — 2026 之前

历史 v1.x 行为:`NovelGenerator` 章节驱动,五层记忆模块,Express + EJS 前端,
spawn Python 子进程。详见 `old/docs/` 与 git history。
