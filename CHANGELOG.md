# Changelog

本项目采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格,
版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

---

## [2.38] — 2026-06-11 — iter#12: EventInjector prompt compression

`backend/agents/event_injector.py`:

* SYSTEM_PROMPT 1700 → 1290 chars (-24%). 三类事件 / 原则 / 禁区合并精简
  描述, state_patches 段紧凑化, 输出格式占位符具体化 (与 narrator
  iter#4 同思路, 用具体 char_id / location_id 替换 `<int>` 之类占位符).

### Tests

5/5 event_injector + world_sim tests pass, 574/574 全测试.

### Benchmark

event_injector 在 3-tick bench 没触发, 所以效果要在生产长跑里看. 直观
节省: 每次 inject 输入 prompt 节省 ~400 chars = ~200 tokens.

---

## [2.38] — 2026-06-11 — iter#11: Bootstrap max_tokens slim

`backend/bootstrap_prompts.py`:

| stage       | before  | after   |
| ----------- | ------: | ------: |
| world       | 24,576  | 4,096   |
| characters  | 32,768  | 6,144   |
| open_loops  | 12,288  | 5,120 (3072 太紧截断, 已 bump 到 5120 安全) |
| style       | 16,384  | 4,096   |
| **总额**    | **85,016** | **19,456** (-77%) |

实测: bootstrap_sec 361 → 299 (-17%), 总 token 28,318 (vs iter#10
31,286). 累计 vs baseline: total -79.5%, bootstrap -40%.

12/12 bootstrap tests pass.

---

## [2.38] — 2026-06-11 — iter#10: Critic length-gated

`backend/agents/narrator_agent.py`:

* **narrative_text < 400 字时跳过 critic 整段** (`_CRITIC_MIN_NARRATIVE_LEN`).
  一次 critique+rewrite ~4500 tokens 比短段落本身还多, 收益不成比例. 短段
  落的语感由 Narrator 自身的 system prompt + 反 reasoning filter 已经管住,
  critic 主要价值在长段落的结构性纠错.

### Benchmark — iter#10 vs iter#9-baseline

| 指标                       | iter#9-baseline | iter#10 (length-gate) |
| -------------------------- | --------------: | --------------------: |
| total tokens               |          34,806 |                31,286 |
| narrative_critic:critique  |          13,564 |                 4,719 |
| narrator                   |          13,216 |                18,041 |
| world_simulator            |           8,026 |                 8,526 |

> critic -65% (length gate 在 tick 2/3 短段落生效).  narrator 自然增长是
> tick 1 产了 896 字长段落. 总 -10% / 累计 vs baseline -77%.

### Quality — 抽样

样本 (tick 1, 896 字): "齿轮的嗡鸣声突然拔高了半个音阶..." 苏默乘汽轮抵达
锈幕城, 沼泽里蓝绿色光点 / 背包里像心跳的震颤 / 老头抱编织袋打盹 — 长段
落充分调动悬疑与世界感, 完全保留 baseline 的质量基线.

10/10 narrator+critic tests pass.

---

## [2.38] — 2026-06-11 — iter#19-29 收尾 + review fixes (累计 -77% tokens / -83% latency)

### iter#19 — Narrator material_block 紧凑

description 截 120 字; internal/intent 80→60 字; 保留 [e.id] (events_consumed
需引用). 每 narrator 调用省 ~600 chars input.

### iter#20 — character_agent user_prompt

多 header 合并到单行 (当前状态/位置/情绪/身体/物品/钱); 关系/事件/目标 desc
截 50-100; recent_actions 取后 3 (从 4). per-call 省 ~300-500 chars.

### iter#21 — Showrunner user_prompt indent strip

json indent 去掉; 最近章节 20→10; loop desc 80→60.

### iter#22 — EventInjector user_prompt indent strip

6 个 json.dumps indent → 紧凑; 去 ```json 围栏. 每次调用省 600-1200 tokens.

### iter#23 — MemoryCompressor user_prompt indent strip

batch=10 entries 紧凑化, 节省 50%.

### iter#24 — character_arc_tracker user_prompt indent strip

json indent + fence + 检测要求合并.

### iter#25 — Critic length-gate 400→600 字

阈值通过 _critic_min_narrative_len() lazy 读 CRITIC_MIN_NARRATIVE_LEN env.
400-600 字段落 critic 触发 REVISE+REWRITE 时 14k tokens 与产出本身同级,
600+ 字才值得反复打磨.

### iter#26 — continuity_v2 evaluator slim

8 维度详细子项 (每项 3 行) 压到单行 ~80 chars/dim; memory_section json
indent 去掉.

### iter#27 — NoveltyCritic user_prompt indent strip

json indent + fence; 章节 30→20.

### iter#28 — story_arc_director user_prompt 合并

三段 header 合并到单段紧凑视图.

### iter#29 — bootstrap stage JSON indent strip

PROMPT_CHARACTERS / PROMPT_LOOPS 的 world_state JSON 不再 indent.

### Review fixes (iter#19-29)

* MEDIUM iter#20 — character_agent facts/secrets 按 item 截断 (此前 ";"
  join 后 [:200] 中间砍字, 静默丢 tail)
* MEDIUM iter#22 — event_injector stray "+" 字符清理
* HIGH iter#25 — 双重 `import os` 别名清理
* HIGH iter#25 — module-level env 冻结改成 lazy 函数 read (monkeypatch
  能正确生效)

### Benchmark — v15 final vs baseline (3 tick + bootstrap, custom MaaS qwen)

| 指标                       | v0-baseline | v15-final | Δ      |
| -------------------------- | ----------: | --------: | -----: |
| total tokens               |     137,890 |    31,214 |  -77%  |
| narrative_critic (all)     |      65,174 |     7,878 |  -88%  |
| narrator                   |      19,904 |    16,184 |  -19%  |
| world_simulator            |      19,427 |     7,152 |  -63%  |
| bootstrap_sec              |         501 |       306 |  -39%  |
| avg tick duration (sec)    |         556 |        91 |  -83%  |

### Quality samples preserved at iter#29

> 酸雨落了整夜。天亮时没停。
> 铁影城的屋顶在雾中只露出轮廓, 像一排生锈的锯齿... 玄烛低头走过赤铜巷.
> 外套领子竖着, 还是挡不住那股味道 — 煤烟混铁锈, 呛嗓子. 他把布袋换到
> 另一边肩上, 里面的东西硌着肋骨. 三份卷宗, 封蜡完好, 是昨夜从外城守备
> 处领回来的. 编号 6-17、6-18、6-19. 守备官递过来的时候手心出汗, 说了句
> "尽快", 多余的话一个字没有.

577/577 tests pass (incl. integration test for critic length-gate added at
iter#15 review fix).

---

## [2.38] — 2026-06-11 — iter#16-18 三轮 + review fix

### iter#16 — NoveltyCritic prompt 减重

`backend/agents/novelty_critic.py` SYSTEM_PROMPT 1200→636 chars (-47%).
5 类检测模式合并到 numbered list, JSON 输出 schema 用具体值, severity
枚举与 examples 真实化.

### iter#17 — Bootstrap PROMPT_WORLD / PROMPT_CHARACTERS slim

`backend/bootstrap_prompts.py`:
* PROMPT_WORLD 1636→1465 chars (-10%)
* PROMPT_CHARACTERS 1519→1437 chars (-5%)

review fix HIGH: 实测 schema 示例用具体值 "锈幕城"/"林雪"/"char_linxue"
会让 instruction-tuned 模型把这些当 soft default 直接 copy. 改用明显占
位符 "<...>" + 显式禁止 copy 指令.

### iter#18 — render_critique_block_semantic — A 类不进 LLM prompt

`backend/agents/quality_spec.py` 新增 `render_critique_block_semantic()`
只列 B-G 6 类 (38 条规则), 跳过 A 类 (7 条, det 检查器已覆盖). 节省
~600 input tokens 每次 critique 调用.

CRITIC_SYSTEM_PROMPT 3278→2675 chars (-18%). render_full_critique_block
标记 LEGACY. 累计 CRITIC prompt vs baseline: 3887→2675 (-31%).

### Review fix CRITICAL — revise/rewrite schema placeholder leak

实测 tick 1 narrative_text 变成 "完整修订后的段落正文" 10 字 — REVISE
JSON schema 示例占位符被 LLM 直接 copy 进 revised_text 写盘. 三路修复:
1. REVISE/REWRITE schema 占位符改成自描述性 "(此处放真正修订后的...)"
2. _parse_text_field 新增 _REVISE_REWRITE_PLACEHOLDERS 检测
3. 最小长度护栏 (≥ 40 字) — 短于此几乎肯定是损坏输出

577/577 tests pass.

---

## [2.38] — 2026-06-11 — iter#9: 全仓 max_tokens 减重 + iter#6-8 review fix

### Changed — iter#9 max_tokens repo-wide slim

防 reasoning 模型 "把 budget 全填满写思考" 浪费。所有 LLM 调用按实际输出
体积重新估算上限:

| 调用点                          |   before |    after |
| ------------------------------- | -------: | -------: |
| showrunner                      |   30,720 |    3,072 |
| event_injector                  |   40,960 |    4,096 |
| memory_compressor L0→L1         |   40,960 |    4,096 |
| memory_compressor L1→L2         |   20,480 |    4,096 |
| novelty_critic                  |   20,480 |    2,048 |
| evaluation/continuity_v2        |   40,960 |    4,096 |

> 这些 agent 不每 tick 跑 (showrunner 每 5 tick / event_injector 每 3-5 tick
> / memory_compressor 每 50 tick / novelty_critic 每 20 tick), 但每次"被 LLM
> 填满 budget" 是 10-40k token 损失. 累计长跑 100+ tick 节省可观.

574/574 tests pass.

### Fixed — iter#6-8 code-review

| 严重度    | 文件                          | 修复                                                   |
| --------- | ----------------------------- | ------------------------------------------------------ |
| HIGH      | narrative_critic.py           | det-substantive (medium+high) gate 误判: 改成 `det_high >= 1` 才跳 LLM (REWRITE 已确定). det 仅 medium 时 LLM 仍需找语义触发 (B/C/F/G — show-don't-tell / 视角漂移 / 对话潜台词). 配套修测试 mock 序列. |
| HIGH      | character_agent.py            | max_tokens=2048 对 reasoning 模型太紧, chain-of-thought 与 message.content 共享 budget. 改 A 级 8192 / B 级 4096. |
| MEDIUM    | narrator_agent.py             | open_loops 排序 `getattr(l, "urgency", 0)` 防御默认 — OpenLoop.urgency 非 nullable, 改用 `l.urgency` 直接访问. |

---

## [2.38] — 2026-06-11 — iter#8: CharacterAgent prompt + 输出预算紧缩

`backend/agents/character_agent.py`:

* **`SYSTEM_PROMPT_TEMPLATE` 2000 → 1700 chars** (-15%). 决策原则 6→3 条
  合并; 语言约束精简掉重复举例; 输出格式注释化繁就简; 信息密度提高但
  保留所有关键字段说明.
* **`max_tokens` 30720 → 2048**. CharacterAction JSON 典型 500-800 tokens
  完成; 30720 是给推理模型留出"把 budget 全填满写思考"的空间, 实测白烧.
  此变更同时缩短延迟 (大 max_tokens 让 stream connection 更慢释放).

### Tests

31/31 character_agent tests pass.

### Benchmark — iter#8 单步对照 iter#7

此次 bench 期间 character_agents 没有被事件波及 (3-tick 短跑特有现象,
长跑 1 个 A 级角色 fire 1 次省 ~28k tokens max_tokens budget). 总 token
基本持平 (31,152 vs 30,434). 节约要在生产长跑里体现.

---

## [2.38] — 2026-06-11 — iter#7: Narrator user_prompt slim

`backend/agents/narrator_agent.py`:

* `_PROSE_TAIL_MAX_CHARS` 1200 → 800. 实测最后 800 字足以维持文风/视角
  延续, 多出来的 400 字主要是上一段已讲完的素材.
* `_MAX_BRIEF_CHARS_COUNT` 8 → 5, `_MAX_BRIEF_EVENTS` 24 → 16. 单 tick
  范围内 8 个角色 / 24 个事件是噪声, 反而稀释 Narrator 注意力.
* `open_loops` 渲染从 8 条 → 5 条 (按 urgency 降序取前 5), description
  截断 100 → 80 字. 让 Narrator 集中处理最紧迫的伏笔.
* `recent_chapter_summaries` 8 → 5. 最近 5 段已足够保持连贯.

### Benchmark — iter#7 单步对照 iter#6

| 指标                       |   iter#6 |   iter#7 |
| -------------------------- | -------: | -------: |
| total tokens               |   29,801 |   30,434 |
| narrator                   |   14,852 |   13,467 |
| world_simulator            |   10,033 |    7,993 |
| narrative chars (3 tick)   |    1,753 |    1,948 |
| avg tick sec               |       94 |       79 |

> 总 token 持平 (差异在 critic 因为 narrator 多写一次), 但 per-char cost
> 进一步下降 (narrator tokens / chars: 8.5 → 6.9). 质量样本非常好.

### Quality — 抽样

样本 (tick 1, 815 字): "铁在锈。雨从铅灰色的天幕里落下来, 不是水, 是
稀薄的、带着铁腥味的酸浆..." 苏默工务局巡查员的工作场景里嵌入黑影
搬运、酸蚀黄铜纹章、引向旧档案馆 — 整段是高水准类型小说. 4 字开篇,
长短句交替, 物件因果链 (排水口→骨头→纹章→档案馆) 完整.

### Tests

10/10 narrator/critic tests pass.

---

## [2.38] — 2026-06-11 — iter#6: Critic 条件 LLM gating

> 自我迭代第 4 轮. critic 再砍一刀 — det 已发现 ≥2 个 medium/high 触发时
> 直接进入修订, 跳过 LLM critique. LLM 主要价值在 det 静默时检语义类问
> 题; det 非静默时 LLM 找的多半是同类问题换皮版本.

### Changed — NarrativeCritic 条件 LLM gating

`backend/agents/narrative_critic.py`:

* **`det_substantive >= 2` 时跳过 LLM critique** — 直接拿 det 触发清单
  进入 REVISE/REWRITE. 仍然记 `llm_critique_done=True` 保证后续 round
  也不再 retry LLM.
* **`CRITIC_FORCE_LLM=1` env 强制开关** — 调试或严格模式可以恢复总跑.

### Benchmark — 累计 vs baseline

| 指标                       | v0-baseline | iter#5 | iter#6 | Δ vs baseline |
| -------------------------- | ----------: | -----: | -----: | ------------: |
| total tokens               |     137,890 | 41,292 | 29,801 |         -78%  |
| narrative_critic (all)     |      65,174 | 19,310 |  4,916 |         -92%  |
| world_simulator            |      19,427 |  8,149 | 10,033 |         -48%  |
| narrator                   |      19,904 | 13,833 | 14,852 |         -25%  |
| avg tick duration (sec)    |         556 |    123 |     94 |         -83%  |
| narrative chars (3 tick)   |       2,105 |  1,821 |  1,753 |         -17%  |

### Quality — 抽样

样本 (tick 1, 590 chars): "苏默指尖划过书脊。羊皮粗糙, 湿气黏手...
卷宗不在原位。标签新, 墨未干: 「预言存录·第三类·锈钉城变故」". 短句节奏
（苏默冷峻人设）、具体物（羊皮 / 铅框窗 / 帝国蓝章 / 黄纸地图）、双重
钩子（5 年前预言今日归档 + 红笔圈"白鸦, 第二夜"）齐全, 远超 baseline.

### Tests

9/9 critic 测试通过, 574/574 全测试通过.

---

## [2.38] — 2026-06-11 — fix(iter-review): CRITICAL world_time=0 + HIGH ellipsis

code-review 在 iter#3-5 diff 上发现:

* [CRITICAL] `world_simulator.py`: `not delta_raw.get("world_time")` 对值 0
  falsy-test 误判为缺失, bootstrap tick 时会双倍推进时间. 改 `is None`.
  非空过滤同步重写 — 只跳过 None / 空字符串 / 空集合, 保留合法零值.
* [HIGH] `narrator_agent.py`: ellipsis 占位符阈值过低 (3) 误杀中文
  "她停下……他也停下……灯灭了……" 这类 3 省略号悬念段. 改成按 "……" / "..."
  整组算, 阈值 6 组 (cjk+ascii) / 4 组 (纯 ascii).
* [HIGH] `narrative_critic.py`: 文档化 "首次 LLM critique 失败 → 整个
  draft 走 det-only" 是有意权衡, 而非副作用.

574/574 tests pass.

---

## [2.38] — 2026-06-11 — iter#5: WorldSimulator delta-output + 紧凑输入

> 自我迭代第 3 轮. 目标: WorldSimulator (v3 后排名 #1 31%) 减重. 改成
> delta-output + 紧凑输入视图, 砍 max_tokens 81920→4096.

### Changed — WorldSimulator delta-output

`backend/agents/world_simulator.py`:

* **输出从 `new_world_state` (整段 WorldState 回灌) 改成 `world_state_delta`**
  (只列实际变更字段). WorldState 90% 字段每 tick 不变, 回灌等于把
  locations/factions/world_rules 重写一遍, 占 6-10k tokens/tick.
* **解析器同时支持两种 schema** — `world_state_delta` 优先, fallback 到
  `new_world_state`. 与 prior 合并时只接受非空字段, 防 LLM 把 era="" 之类
  覆盖掉 (沿用 v2.35 反清空保护).
* **max_tokens 81920 → 4096** — delta 模式下 4096 远够 (实测 ~800-1500
  tokens 出齐).
* **input prompt 紧凑视图** — 不再 dump 整个 WorldState; 只送
  world_time / era / season / weather / 地点名 + 事件描述 (truncated 80 字).
* **强制 1-3 条 natural_events** — 第一版砍得太狠, 模型干脆 0 events, 下游
  CharacterAgent/Narrator 链路全静默 (无事件→无角色波及→无叙述). 加硬性
  要求即便世界变化轻微也要产出可感知的环境事件 (脚下泥泞/雾里人影/告示
  牌新换), 保住下游驱动.

### Benchmark — 3 tick + bootstrap, custom provider

| 指标                       | v0-baseline | v3 (iter#4) | v4 (iter#5) | Δ vs baseline |
| -------------------------- | ----------: | ----------: | ----------: | ------------: |
| total tokens               |     137,890 |      60,316 |      41,292 |         -70%  |
| world_simulator            |      19,427 |      18,909 |       8,149 |         -58%  |
| narrator                   |      19,904 |      17,191 |      13,833 |         -31%  |
| narrative_critic (all)     |      65,174 |       9,556 |      19,310 |         -70%  |
| avg tick duration (sec)    |         556 |         190 |         123 |         -78%  |
| narrative chars (3 tick)   |       2,105 |       1,953 |       1,821 |         -13%  |

### Quality — 抽样

样本 (tick 1, 525 chars): "雾气从档案馆的通风口涌进来 / 灰白色的, 带着铁锈和
湿土的气味...提灯挂在肘弯, 灯焰在潮湿里跳了跳, 投下抖动的影子...". 林雪持灯
探档案, 发现 卷宗预言 残卷 + 铜版拓片 (齿轮与藤蔓), 远处铁柜门刮擦声埋下
钩子. 具体物 + 嗓音 + 神秘弯钩齐全, 完全没有回退.

### Tests

20/20 orchestrator + WorldSimulator-related tests pass (parser 双 schema
兼容).

---

## [2.38] — 2026-06-11 — iter#4: Narrator prompt + output bound + 反 reasoning 加固

> 自我迭代第 2 轮. 目标: Narrator 链路减重 (slim prompt + 输出预算). 中途
> 发现 Custom MaaS qwen36v35b 对精简提示脆弱, 输出多种 reasoning / 占位
> 符 / JSON-schema-as-prose 泄漏. 强化 strip_reasoning_leak 多语言多变种
> 检测, 加 schema 占位符识别, 退化为跳过避免污染正文.

### Changed — Narrator prompt + 输出预算

* **NARRATOR_SYSTEM_PROMPT 2862 → 2195 chars (-23%)** (`backend/agents/
  narrator_agent.py`). 写作方法从 6 条合并到 4 条 (场景三要素 / 对白承载
  冲突 / 具体物优先+内心要薄 / 节奏与衔接). 信息纪律去重复. 反 reasoning
  禁区保留并加强 (含英文 marker).
* **max_tokens 16384 → 按 estimated_length 分档** (long=5500 / medium=3500 /
  short=2200). baseline 实测 medium tick 产出 1854 字 vs 目标 1200 字, 注水
  54%; 预算硬上限后强制贴 target.

### Changed — 反 reasoning 泄漏多层加固

`backend/nf_core/reasoning_filter.py`:

* **新增中文 reasoning marker** — qwen36v35b 实测新变种 (`"首先,任务"` /
  `"首先,本段"` / `"首先,这部"` / `"首先,我看"` / `"首先,我注意"` 等)
* **新增英文 reasoning marker** — `"Let me analyze"` / `"Let me write"` /
  `"I'll write"` / `"I need to write"` / `"First, let me"` ...
* **高置信度泄漏 markers** (`_HIGH_CONFIDENCE_LEAK_MARKERS`) — JSON schema
  字段名 (`narrative_text` / `estimated_length` / `viewpoint_characters` ...)
  / 写作方法标题出现在文本任意位置即视为完整泄漏, 直接返回空字符串.
  真正的小说正文绝不会含这些 token.

`backend/agents/narrator_agent.py`:

* **JSON 解析失败兜底前先扫 reasoning** — 此前 raw 直接当 narrative_text
  写盘, 导致 "Let me analyze..." 之类直接写进小说. 现在扫到 leak 退化跳过,
  保留 tick_summary 供 MemoryCompressor 记账.
* **JSON schema 示例改用安全具体值** — 此前占位符 `"...实际的中文小说正文..."`
  被 MaaS 模型直接 copy 进输出. 改为具体示例 `"苏默冒雨向安全屋移动"`,
  附加占位符检测 (`is_placeholder`): `...` ≥ 3 次 / `"实际的中文小说正文"` /
  `"char_id_1"` / `"loop_id_1"` 出现即跳过.

### Benchmark — 3 tick + bootstrap, custom provider

| 指标                       | v0-baseline | v3-narrator-fixed3 |        Δ |
| -------------------------- | ----------: | -----------------: | -------: |
| total tokens               |     137,890 |             60,316 |    -56%  |
| narrator                   |      19,904 |             17,191 |    -14%  |
| narrative_critic:critique  |      51,450 |              9,556 |    -81%  |
| narrative_critic:rewrite   |      13,724 |                  0 |   -100%  |
| avg tick duration (sec)    |         556 |                190 |    -66%  |
| narrative chars (3 tick)   |       2,105 |              1,953 |     -7%  |

> Narrator 跳过 1/3 ticks 是 MaaS 模型 reasoning fragility 的代价 — 过滤层
> 把"Let me analyze..."、JSON schema copy-paste 这类输出拦下来, 比让它们
> 污染正文更可取. 产出的 2 段质量很高 (压力表归零检校 / 工业雾色 / Lin Xue
> 失语症复发的具体感官), 与 baseline 同等或更好.

### Tests

6/6 narrator + reasoning 测试通过. strip_reasoning_leak 新增 6 个
高置信度信号路径全部 PASS.

---

## [2.38] — 2026-06-11 — iter#3: NarrativeCritic 减重

> 自我迭代循环第 1 轮 (cost-quality-loop branch). 目标: 降低单 tick 生成
> token 开支, 不损质量. 实测 critic 链路占 baseline 47% 的总 token 开支,
> 本轮专攻该路径.

### Changed — NarrativeCritic 减重

* **LLM critique 只在第一轮跑** (`backend/agents/narrative_critic.py`) —
  此前 critique → revise → critique → revise 每轮都跑 LLM critique 重新评估
  修订后的全段, 占 critic 开支 60-70%. 改为: 第一轮 det+LLM 合并判定,
  后续轮只跑 deterministic 检查验证结构性触发是否清掉. 语义触发在第一轮
  已识别, revise 阶段已带 `avoid_codes`, 不需要二次确认
* **MAX_TOTAL_ROUNDS 4 → 2** (env `CRITIC_MAX_TOTAL_ROUNDS` 可恢复). 实测两
  轮以上的修订质量收益已饱和, token 是线性 ×2-3 增长
* **critique max_tokens 8192 → 1500** (env `CRITIC_CRITIQUE_MAX_TOKENS`).
  triggers JSON 极紧凑, 1500 足够列 10+ 触发; 之前的 8192 给推理模型留了
  把 budget 全填满的空间
* **revise/rewrite max_tokens 32768 → 4096** (env `CRITIC_REVISE_MAX_TOKENS`).
  narrative_text 上限 ~2200 字 (≈3300 tokens), 给 4096 留余量
* **推理前缀拦截** — MaaS Qwen / DeepSeek-R1 偶发把 JSON 提示当开放问答,
  输出 `Let me analyze...` / `好的, 让我...` 前缀, 整次调用 JSON 解析必失败.
  baseline 实测 2 次此类失败, ~10k tokens 白烧. 新增前缀检测, 命中即退回
  det-only, 不重试

### Benchmark — 3 tick + bootstrap, custom provider (讯飞 MaaS qwen36v35b)

| 指标                       | v0-baseline | v1-critic-trim |       Δ |
| -------------------------- | ----------: | -------------: | ------: |
| total tokens               |     137,890 |        120,588 |  -12.5% |
| narrative_critic:critique  |      51,450 |         14,652 |  -71.5% |
| narrative_critic:rewrite   |      13,724 |              0 |   -100% |
| avg tick duration (sec)    |         556 |            329 |   -41%  |
| narrative chars produced   |       2,105 |          3,216 |   +53%  |

> narrator 自身 token 增长 (19k → 29k) 是因为产出文本长度 +53%, 不是回归.
> per-character cost 下降幅度远大于 12.5%.

### Quality — 抽样保持

样本 (tick 1, 522 chars): 具象意象 (齿轮停摆/油污/疫源追溯/复写墨) 到位,
角色嗓音区分明显 (苏绣的细致 vs 阿黄的"哎呦"嘟囔), 神秘钩子自然.
风格未退化至 baseline 那种"安全感官碎片" 老问题.

### Tests

15/15 critic 相关测试通过, 无需修改既有测试.

### Infra

* `scripts/bench_tick.py` — bootstrap + N tick + 按 agent 拆解 token 开支
  的基线测量脚本. 输出 `docs/iter/bench-<label>.{json,md}`
* 提交时 working tree 工作分支: `iter/cost-quality-loop`

---

## [2.37] — 2026-06-10

> 三线大修: 叙事质量架构重写 + 全项目 4 路并行 code review (10 CRITICAL /
> 12 HIGH / 15 MEDIUM 全数处置) + 前端「墨砚」设计系统重构。
> (含 v2.35 WorldState 反清空、v2.36 summary_tree/branch per-tick 持久化两个
> 未单独记账的代码层增量。)

### Changed — 叙事质量架构 (生成质量根因修复)

实测问题: 产出是"与标题脱节的无人物无对话意境碎片"。诊断出 6 个架构级根因,
全部修复:

* **台词管道打通 (根因 #1)** — `CharacterAction.dialogue_spoken / intent /
  internal_monologue` 此前在 action→Event 转换时被丢弃, Narrator 从看不到
  任何角色说了什么, 又被禁止编造 → 结构性写不出对话。Orchestrator 现在缓存
  本 tick `resolved_actions` 原样传给 Narrator, 素材简报按事件渲染台词原文
  (`台词 (对X): "…"`) 与 △ 标记的私密动机线 (内心/意图, 仅供理解不可写成旁白)
* **前文衔接 (根因 #2)** — Narrator 每次拿到上一段实际正文的结尾
  (`prose_tail`, ≤1200 字), 指令"第一句必须能直接接着读"; 进程重启时从
  `narratives/` 最新文件恢复, 跨重启保持衔接。此前每 tick 是孤立小品
* **角色名片 (根因 #3)** — `CharacterProfile` (名字/性格/说话风格/关系+信任)
  首次传入 Narrator; 此前它只拿到 `char_xxx` id, 连角色叫什么都不知道
* **世界落地 (根因 #4)** — `WorldState` (era/季节/天气 + 涉事地点名与现状)
  渲染进场景块, 场景不再悬空
* **Narrator system prompt 重写 (根因 #5)** — 从"55 条禁令 + 56 个黑名单词
  逐行列出"改为正向写作方法论 (场景引擎: 目标/阻力/转折; 对白承载冲突 +
  动作节拍; 具体物优先; 因果显形; 内心要薄; 句长节奏) + 紧凑风格纪律
  (`quality_spec.render_narrator_discipline_block`, 完整清单仍由
  NarrativeCritic 确定性检测兜底)。负面约束压倒正向指导正是模型退缩到
  "安全感官碎片"的成因
* **篇幅指标重校 (根因 #6)** — 单 tick 目标 2000-5000 字必然注水;
  改为 300-700 / 600-1200 / 1200-2200 三档, "宁短勿水", 节级体量由
  SectionCloser 跨 tick 累积保证; `max_tokens` 163840 → 16384 (诚实值)
* **CharacterAgent** — 注入"你最近几步的行动"(防同一动作机械连刷) +
  台词要求段 (声纹一致/口语不规则/有目的/可不说话)
* **bootstrap 升级** — 角色 `speech_style` 强制含 2 句示例台词 (声纹),
  personality 写行为倾向而非标签, A/B 角欲望强制互斥; 风格锚点对话场
  强制 ≥4 句你来我往真实对白 (无对白示范的锚点集会把全书带成独白流)
* Narrator 语感锚点注入降为 top-3, 措辞改为"示例内容与本作无关, 不要模仿
  其内容"

### Fixed — 核心引擎 (并行审查 #1)

* **CRITICAL** `run_tick` 的 `asyncio.gather` 内 Narrator 异常直接传播,
  跳过全部持久化 (tick 已 advance 但永不 save, 重跑被 TickDB
  INSERT OR IGNORE 静默吞) — `_narrate_safe` 包装降级为沉默 tick
* **CRITICAL** 多租户 token 记账错乱 — `_GLOBAL_TRACKER` 模块单例被最后
  构造的 runtime 接管, 用户 A 的调用记到 B 的账上; 改 ContextVar per-task
  绑定 + 每 tick 开始时 `set_global_tracker`
* **HIGH** CharacterArcTracker 在与 Narrator 并行的"只读"窗口里 upsert
  角色状态 (Narrator 可能读到半新半旧快照) — 改两段式: 并行窗口只收集,
  串行阶段统一应用
* **HIGH** StoryArc 就地 mutate → `model_copy`; TokenBudget 内存记录
  无限增长 → 2000 条触顶裁剪

### Fixed — 周期 agent / 存储层 (并行审查 #2, 19 项)

* **CRITICAL** MemoryCompressor 把 open_loop 源事件 (protected id) 送 LLM
  压缩 — 伏笔因果根可被永久删除; 候选过滤补 `id not in protected`
* **CRITICAL** ConsistencyGuardian → continuity_v2 传 JSON 字符串而非 dict,
  每次扫描必抛 TypeError 被吞、**一致性检查自部署起从未真正工作过**
  (永远 degraded=True); 修通后 world_state/角色状态真正进评估 prompt
* **CRITICAL** StoryArcDirector 就地 mutate 共享 arc.pacing_history —
  改不可变重建 + 单次赋值
* **HIGH** tick_kg_sync 角色移动后旧 LOCATED_AT 边永不删除 (角色"同时位于
  两地"且随 tick 膨胀); ArcTracker 吞 LLM 幻觉 drift_codes/stage (加白名单);
  narrative_critic 加总轮次上限 4 + `use_llm=False` 时不再调 LLM 修订;
  continuity_v2 评估缓存加 128 条 FIFO 上限
* **MEDIUM** fact_ledger bisect 插入 + load 时排序; branch_manager
  save 失败回滚内存; showrunner `max(None, int)` 兜底 (两处);
  safety_filter warn 打码改 pattern.sub (原 evidence.replace 会误伤/漏替);
  knowledge_graph rollback 改临时图原子替换; creativity_scorer 总段数
  计数器; summary_tree `_merge_up` 被 cancel 时恢复 pending 索引 +
  load 失败用快照阈值重建; tick_db ROLLBACK 判空 + Row 不逃逸锁;
  prompt_builder 截断零进展守卫

### Fixed — API / 认证层 (并行审查 #3, 11 项)

* **CRITICAL** 任务越权 — `task.user_id == ""` 时任何登录用户可读/取消/
  订阅该任务 (`if task.user_id and ...` 短路); 改严格比对
* **CRITICAL** CORS `allow_origins=["*"]` + `allow_credentials=True` 违反
  规范, 生产跨域下浏览器直接拒绝带 Authorization 的请求 (前端无法登录);
  默认 origins 改 localhost 白名单, 含 `*` 时自动关 credentials
* **CRITICAL** 限流可被伪造 `X-Forwarded-For` 绕过 — 新增 `trusted_proxy`
  配置 (默认 False 只信 socket 对端; 反代部署示例已配 true)
* **HIGH** `GET /api/agents` 无认证暴露注册表与模块路径 (补 auth);
  cleanup_loop 同步 rmtree/SQLite 阻塞 event loop (入 executor);
  `_clear_for_tests` 不 cancel 孤儿任务; 标题生成 fire-and-forget task
  无引用持有; switch_novel 双 `_active_by_user` 更新无原子性 (统一锁内
  回调); `get_runtime` 锁外读活跃表 TOCTOU (并发可造出双 runtime 泄漏
  SQLite 句柄)
* **MEDIUM** tick 路由 query 参数加 `ge/le` 上限; auth config 加 mtime
  缓存 (此前每请求重读 config.json)
* 审查声称的"tick/agent 端点可跨用户越权"经验证**不成立** (per-user
  manifest + realpath 沙箱链路闭合), 未为不存在的洞加代码

### Changed — 前端「墨砚」设计系统重构

* `global.css` 全量重写: 暖墨四层 surface + 朱砂主色 + 青瓷/缃黄/黛蓝/胭脂
  语义辅色, Noto Serif SC 衬线标题与正文, 类名 API 与旧版兼容 (视图零改动
  换肤), 旧 token 全部别名映射
* **阅读视图重写** (产品核心面): 正文按段渲染 (首行缩进 2em / 行高 2.05 /
  40em 行宽 / 纸面底色), 章节元信息行, 上一节/下一节导航
* App 壳: 墨砚 wordmark, 朱砂活跃指示条, 新空态/进度条/徽标体系
* 视图层 17 项行为 bug 修复 (竞态/泄漏/空指针/localStorage provider 回跳,
  详见审查 #4 清单)

### Tests

* 新增 `test_task_routes.py` / `test_auth_config_cache.py` /
  `test_agent_routes_auth.py`; 适配 6 个测试文件到新契约
* 全量回归通过 (见各审查批次通过记录)

## [2.34] — 2026-06-09

### Added
* **`feat(kg)`** 知识图谱接入 tick 架构 — 新增 `backend/graph/tick_kg_sync.py`
  纯 Python 同步 (无 LLM), 自动从 `CharacterProfile` /
  `WorldState.{locations,factions}` / `CharacterState.{current_location,
  relationships}` / `Faction.{leader,allied,hostile}_*` 喂图。中文关系类型
  (`恋人/盟友/敌人/师徒/...`) → `RelationType` 映射, 兜底 `KNOWS+label`
* `KnowledgeGraph` 加 single-file 持久化 `save_to_disk` / `load_from_disk`,
  与 snapshot 历史回滚目录解耦; 原子写 + 损坏文件静默跳过
* `TickRuntime.__init__` 装载 KG (per-novel `data_dir/knowledge_graph.json`),
  并立即跑一次 seed sync; `Orchestrator` 加 `knowledge_graph` +
  `knowledge_graph_path` 参数, `_run_tick_unlocked` 末尾持久化前同步 + 落盘,
  累积到 `agents_called` 以 `kg_sync(+Ne/+Nr/~Ne)` 形式诊断
* `/api/graph*` 路由优先读 tick KG, fallback 到 legacy GenerationPipeline,
  POST/DELETE 后同步落盘。修前端 KG tab 永远 0 实体 0 关系的存量问题
* **`feat(tasks)`** 任务面板独立分段 + 15s 兜底刷新 (`TaskListPanel.jsx`) —
  内嵌标题 + ⟳ 刷新按钮, 15s `setInterval` 仅在 tab 可见时跑, 防 SSE 漏推;
  终态任务保留窗口 60s → **30 分钟** (实测一节生成 ~30 分钟, 60s 太短)

### Fixed
* **bug 1 (标题穿通根因)** — `WorldSimulator._parse_output` 把 LLM 输出的
  `new_world_state` 整个替换 `prior_world_state`; MiMo 偷工只给
  `{era, weather}` 时, `model_validate` 用 `default_factory=list` 兜底,
  bootstrap 写入的 5 locations / 3 factions / 6 world_rules 被空 list
  整个擦掉。修法: 稳态字段反清空保护, `locations/factions/world_rules`
  为空但 prior 非空 → 保留 prior + warning, 真要删走 events
* **bug 2 (supplement 元话语泄漏)** — `SectionCloser._draft_closure_supplement`
  漏掉 v2.34 早期给 NarratorAgent 加的 `_strip_reasoning_leak`, 补叙段
  末尾出现 "首先, 用户提供了..." 一整段 reasoning 复述落盘。抽 reasoning
  反泄漏到共享模块 `nf_core/reasoning_filter.py`, marker 35 → 47
  (补"我的任务是" / "用户提供了" / "需要快速带过" / "要求包括"),
  `NarratorAgent` / `SectionCloser` 同接一道闸
* **bug 3 (bootstrap 空世界)** — 4 阶段 LLM 都返回 `{}` 时, 角色 / 地点 /
  伏笔 / 风格锚点全为空但 task 仍标 `completed`, 续写时 Narrator 完全失锚。
  新增完整性闸: 4 集合任一为 0 直接 raise, task 变 `failed`,
  用户可见可重跑
* **bug 4 (4 类用户报 bug — 数据兜底 + Narrator 反泄漏 + 标题穿通)**:
  * `secrets_kept` / `active_global_events` 等 `list[str]` 字段被 reject —
    `models._coerce_llm_payload` 加元素级兜底, dict 项抽
    `content/description/text/value/summary/name/title/label/id`,
    仅在 `typing.get_args` 判定目标元素类型为 `str` 时介入
  * `WorldSimulator` 自然事件 `evt_001/evt_002` 跨 tick 重复 + 缺 type —
    `_parse_output setdefault type=exogenous` + 强制重写 id 为
    `evt_nat_{world_time}_{idx}_{6 位 hex}`, 不依赖 LLM 给 unique id
  * `Narrator narrative_text` 末尾接 reasoning prologue —
    `_strip_reasoning_leak` 段落起点扫 35 个 CoT 标记
    (`首先,理解任务` / `从 tick 摘要看` / `关键点包括` / `好的, 以下是` / ...)
    命中即砍; prompt 加「输出禁区」段, leak 后 <40 字才退化为不叙述
  * 标题"被遗忘的神明..."跑成现实村庄 — `TickState` 加 `novel_title`
    字段 + `bootstrap_world(title=...)` + `NarratorAgent.narrate(novel_title=...)`
    渲染到 user_prompt 顶部「作品标题 (主题锚点 — 必须呼应)」块;
    `PUT /api/novels` 改名时同步活跃 runtime
* **`fix(llm-json)`** `json_repair` 兜底 (`requirements.txt` +
  `json-repair>=0.45.0`) — `parse_llm_json` 加 fast path (`json.loads`)
  + 降级 (`json_repair`, 修复未转义引号 / 字面换行 / 单引号 /
  尾随逗号), 顶层不是 dict 时仍 raise 避免误吃空对象, 包未安装时
  降级到 stdlib (向后兼容旧 Docker 镜像)
* **`fix(llm-json)`** 11 个 agent + `bootstrap` 统一走 `parse_llm_json` —
  新增 `nf_core/json_utils.py:extract_json_object + parse_llm_json` 深度
  平衡扫描第一个 `{...}` (字符串内 brace / 转义引号正确处理), 12 处调用
  全切; 失败日志改用 `raw[:300]`, 直接看 MiMo 原始返回排障
* **`fix(bootstrap)`** 鲁棒 JSON 提取 + 失败时打印原文 —
  `_extract_json_object` 深度平衡扫描第一个 `{...}` 子串, `_llm_json` 解析
  失败时记 `stage + 错误位置 + raw[:500] + extracted[:500]`
* **`fix(bootstrap)`** `max_tokens` 砍到 16K-32K, 修 MiMo reasoning 5 分钟
  服务端超时 — `mimo-v2.5-pro` reasoning chain 在 61K-122K 下展开过长,
  MiMo 平台 5 分钟硬超时 → `APITimeoutError`。降到 reasoning + JSON 都能
  塞下、5 分钟算得完的折中: `world 24576 / characters 32768 /
  open_loops 12288 / style 16384`
* **`fix(llm)`** reasoning 模型 (MiMo) `content` 空导致 502, fallback 到
  `reasoning_content` — `random-title max_tokens=32` / `random-seed=300`
  对推理模型严重不够, 思维链吃光 budget 让 `content` 返空字符串,
  `if not text` 抛 502 但答案其实在 `reasoning_content` 里。新增
  `extract_message_text`, `content` 空时退到 `reasoning_content`
  (attribute 或 `model_extra`); `random-seed` 默认 2048,
  `random-title` 1024; 502 错误信息带 `finish_reason`, 让用户区分
  "上游 length 截断" vs "上游审核拦截"; title 清理改为取最后一段非空行
* **`fix(llm_client)`** `AsyncOpenAI max_retries: 1 → 0` (3 处: 主 client /
  reload / 用户态 client) — MiMo 单次 5 分钟服务端超时, 重试又一次
  5 分钟没意义, fail fast 让上层 (bootstrap / writer / ...) 直接拿到
  `APITimeoutError` 处理

### Tests
* `test_extract_message_text.py` (9) — `content` 正常/空/None/全空白 分别
  fallback, `reasoning_content` 在 attribute 与 `model_extra` 两种位置
* `parse_llm_json` 6 edge case (干净/markdown/前后散文/嵌套/字符串内 brace/
  纯 reasoning) 本地全过, 14 个 modified 模块 importlib 全 OK
* 全套 541 个测试可被收集 (`pytest --collect-only`); 32 个
  orchestrator/narrator/tick_state/graph 测试在 KG 接入后仍全过

---

## [2.33] — 2026-06-08

### Added — 多模态生成: 节文本 → 分段图 + TTS → 字幕视频

后端
* `backend/nf_core/text_segmenter.py` — 中文按句/逗号切, 段长 15-60 字, 纯 Python
* `backend/nf_core/edge_tts_client.py` — `edge-tts` + `WordBoundary` 拿时长,
  voice 白名单
* `backend/nf_core/video_composer.py` — `imageio-ffmpeg` + libx264 单条
  `filter_complex` 合成, `compose_video_async` + 全局 `Semaphore(2)` 限并发
* `backend/multimedia/asset_store.py` — per-novel-per-section 资产
  (`manifest.json` + `img_NN.png` + `audio_NN.mp3` + `subtitles.srt` +
  `output.mp4`), `update_segment_status` read-modify-write 在锁内
* `backend/api/multimodal_routes.py` — 6 REST 端点 (`/api/multimodal/voices`,
  `/segment-preview`, `/generate`, `/{novel}/list`,
  `/{novel}/{ch}/{s}/manifest`, `/{novel}/{ch}/{s}/asset/{filename}`),
  复用 `task_manager` SSE
* `backend/tasks/task_models.py` `TaskKind` 加 `multimodal_generation`

前端
* `frontend/src/views/MultimodalView.jsx` — 完整新视图: 节列表 + 分段预览 +
  配置 + SSE 进度 + 视频播放器 + 段缩略图
* `frontend/src/services/api.js` — 6 个多模态 API + 401-aware blob URL helper

依赖: `edge-tts` (MIT) + `imageio-ffmpeg` (静态二进制) + `mutagen`
(mp3 时长兜底)

### Security & Fixed (3 reviewer 并行 + 手动)
* **CRITICAL** SSRF — `X-Image-Endpoint` 接受任意 URL 把讯飞凭据签发到
  攻击者主机, `xfyun_image` 加 hostname 白名单 + 强制 https
* **CRITICAL** `progress_state` 每个 task 各创独立 dict, 进度永远 `1/N`,
  改为 `_run_executor` 共享 + `asyncio.Lock` 保护
* **HIGH** voice 参数无校验 → `GenerateRequest field_validator` 白名单
* **HIGH** `image_creds` 在 task 闭包里长期持有 `APISecret` → finally 清零
* **HIGH** SSE controller unmount 不 abort → `useEffect cleanup` 显式 abort
* **HIGH** `assetUrls cleanup` 闭包捕获初始空对象 → ref 同步, unmount 时
  revoke 真实 blob URL
* **HIGH** `handleGenerate` 双击 race → `generatingRef` 同步锁
* **MEDIUM** `get_asset endswith` 多扩展名绕过 → `Path(filename).suffix`
* **MEDIUM** `datetime.utcnow()` 3.12+ 弃用 → `datetime.now(timezone.utc)`
* **MEDIUM** `fetchMultimodalAssetBlobUrl 401` 不刷登录态 → 复刻 `_emit401`

### Tests
* `test_text_segmenter.py` (11) — 空/单/多句/超长/碎片/末段兜底
* `test_video_composer.py` (13) — SRT 时间戳/ffmpeg args/字体样式
* `test_multimodal_security.py` (12) — SSRF 白名单/voice/线程池并发不丢更新/
  路径穿越

### Data Layout
```
data/users/{uid}/novels/{nid}/multimedia/sec_{ch}_{s}/
  manifest.json + img_NN.png + audio_NN.mp3 + subtitles.srt + output.mp4
```

---

## [2.32] — 2026-06-08

### Fixed — 讯飞图片生成对齐 MaaS 平台文档
* `host` + body 必填字段 + 分辨率约束 (`512/640/768/1024/1280/1536/2048`)
  对齐讯飞 [Spark v2.1/tti] 文档
* `patch_id` 永远 set, 空数组兜底 — 实测 schema validator 报
  `'$.header.patch_id' field is required`, 全量模型 (`xopqwentti20b` 等)
  不需要 LoRA 也得给空数组

### Fixed — Docker bridge MTU 降到 1380, 修讯飞 TLS 握手超时
* DNS / TCP 443 都通, TLS Client Hello 第一帧丢, 根因是 Docker 默认 bridge
  MTU 1500 > 讯飞 GFW 路径 MTU
* `docker-compose.yml` 加 `driver_opts: com.docker.network.driver.mtu: 1380`

---

## [2.31] — 2026-06-08

### Added — 讯飞图片生成支持 `modelid` (domain) 切换
* `xfyun_image` 接受 `modelid` 参数 (默认 `xopqwentti20b`), 透传到请求体
  `header.domain`
* 业务错误码加中文 hint 映射 (`10004 → "缺字段, 看 detail"`,
  `10013 → "审核拦截, 改 prompt"`, …), 用户一眼看出怎么修

### Fixed — 讯飞协议与域名解析
* 端点协议从 `wss://` 改为 `https:// POST`, 修 `ConnectionResetError`
  (讯飞星辰 MaaS 平台已切到 REST, WebSocket 端点稳定性差)
* 兼容 `websockets 11+` `InvalidStatus` 改名, 异常 `detail` 永不为空
* `backend + cloudflared` 显式 DNS (`8.8.8.8` / `1.1.1.1`), 修讯飞域名
  解析失败 (Cloudflare Tunnel 容器默认走 DNS-over-HTTPS, 国内 GFW 偶发拦截)

---

## [2.30] — 2026-06-08

### Refactored — 彻底去掉所有保活轮询, 事件驱动

之前每秒 ~1 个请求 (`App.jsx /api/stats` 30s + `HomeView.jsx /api/tick/status`
15s + `TaskListPanel.jsx /api/tasks` 3s + `TickControlPanel.jsx
/api/tick/status` 3s), idle 也在拉, devtools 网络面板刷屏。

现在
* 全部 `setInterval` 删除, 死常量 `POLL_INTERVAL_MS` 清掉
* 触发时机:
  1. 组件挂载时拉一次
  2. tab 从后台切回前台时拉一次 (`visibilitychange → visible`)
  3. 用户操作完成后由现有 `onAfterGenerated` / `refreshKey` / `handleX` 触发
* 进行中任务的实时进度仍走 `TaskListPanel` 的 SSE 流 (事件驱动, 不算轮询)

idle 时网络面板完全静音。

---

## [2.29] — 2026-06-08

### Fixed — 502 缺 CORS 头
* `UserLLMHeadersMiddleware` 从 `BaseHTTPMiddleware` 改成**纯 ASGI middleware** —
  `BaseHTTPMiddleware` 在错误响应路径有已知边缘案例: CORS 头偶尔丢失, 浏览器
  读不到 502 body, 用户看不到讯飞具体错误。纯 ASGI 直接走 `scope/receive/send`,
  不破坏中间件链
* `image_routes` 缺凭据时直接 400 (避免浪费一次讯飞握手往返);
  `XfyunImageError` 分支显式 `logger.warning` 让具体错落到 docker logs

### Tuned — 后台保活轮询过密 (此后 v2.30 完全删除)
* `/api/stats` 5s → 30s, `/api/tick/status` 3s → 15s
* `document.visibilitychange` 监听, tab 切到后台暂停轮询, 后台 tab 网络
  噪音降 ~80%

---

## [2.28] — 2026-06-08

### Added — 多模态文生图 (科大讯飞) + 服务端 LLM 改读用户 key

**多模态生成 tab**
* `backend/nf_core/xfyun_image.py` — 科大讯飞 Spark v2.1/tti 客户端,
  HMAC-SHA256 鉴权 + 流式收 base64 切片 + 错误码透传
* `backend/api/image_routes.py:POST /api/image/generate` —
  header 一次性带 `AppID/APIKey/APISecret`, 后端用完即丢
* `frontend/src/views/MultimodalView.jsx` — 文本框 → 尺寸选择 → 生成 →
  图片预览 + 下载 (v2.28 占位让用户先跑通凭据, v2.33 接小说内容)
* `App.jsx` 主导航加「多模态生成」tab

**服务端 LLM 改用用户 key (彻底去掉项目内 api key 兜底)**
* `nf_core/llm_client` 加 `UserLLMConfig` `ContextVar` +
  `set_user_llm_config` / `get_user_llm_config` helper + 按
  `(api_key, base_url)` 缓存 `AsyncOpenAI` (LRU 32 上限防内存膨胀);
  `chat()` / `chat_stream()` 优先用 `ContextVar` 凭据, 没值才退回
  `self._client`
* `backend/middleware/user_llm.py` ASGI middleware — 请求入口读
  `X-User-LLM-Key/Base-Url/Model` 写入 `ContextVar`,
  `asyncio.create_task` 默认拷贝 context, 后台 tick/section 任务自动继承
* `main.py` 注册 `UserLLMHeadersMiddleware` (CORS 之后, 先 CORS 后 user-llm)
* `frontend/src/services/api.js` `authedFetch` 所有非公开请求都带
  `X-User-LLM-*` header

兼容性: 用户没配 key 时仍走 `config.json` 兜底 (legacy/dev); 生产强制模式
→ `config.json` 留空 `api_key` 即可

---

## [2.27] — 2026-06-08

### Added — HTML 邮件 + 图片生成多 provider + LLM 配置改本地存储 + toast 精简

**邮件**
* `smtp_client` multipart text + HTML, 紫青渐变品牌色 + 大字号 OTP
* 显式 `Message-ID` 提升 Gmail 反垃圾打分

**系统设置 (`ConfigView` 重写)**
* 文本 LLM: provider (`deepseek/mimo/custom`) + key/url/model, 全 `localStorage`
* 图片生成: 新增, 默认科大讯飞 (`AppID + APISecret + APIKey` 三段式)
* schema 驱动多 provider 字段; 预留 OpenAI DALL·E / Stability / 自定义
* 服务端不再有 LLM 兜底 key; 未配置时相关功能直接报错

**SettingsModal 精简** — 移除「个人 LLM API 配置」段 (迁到 ConfigView),
仅保留: 保存我的作品 / 设置密码 / 退出登录

**Toast 精简** — 删除可被 UI 自然感知的 success/info; 保留全部错误 +
验证码已发送 + 密码设置成功 + 已保存

---

## [2.26] — 2026-06-08

### Added — 邮箱 OTP 认证 + 多租户数据隔离 + 随机种子/标题按钮

5 phase 一次性实现:

**后端 — 认证**
* `backend/auth/` 包: `models` / `store` (SQLite) / `jwt_utils` / `otp` /
  `password` (bcrypt) / `smtp_client` (aiosmtplib) / `rate_limit`
  (per-IP+per-email) / `dependencies` / `routes`
* 9 个端点: `register/send-otp` & `verify` / `login/send-otp` &
  `verify-otp` & `password` / `me` / `me/set-password` / `me/settings` /
  `logout`
* 邮箱枚举防御: `login/send-otp` 静默 204, `login/verify` 错误文案统一
* 一次性 OTP, 5 分钟 TTL, 5 次尝试上限, sha256 + 常数时间比较

**后端 — 多租户**
* `novel_manager` 全 API 加 `user_id` 参数, 路径
  `data/users/{uid}/novels/{nid}/`
* `tick_runtime` 注册表 key `(user_id, novel_id)`, active 状态 per-user
* 启动时一次性迁移 `data/novels/` → `data/users/_legacy/novels/`
* 所有路由经 `Depends(get_current_user)`, task 加 `user_id` 字段 + ownership
  检查
* 24h cleanup 后台 task: `save_my_works=False` 且 `last_accessed` 超期 → 删

**后端 — 随机生成**
* `POST /api/llm/random-seed` + `POST /api/llm/random-title` —
  `X-User-LLM-Key/Base-Url/Model` header 一次性传递, 后端用完即丢
* 联动: 一侧已填 → 另一侧客制化生成

**前端 — 认证 UI**
* `AuthContext` — `localStorage JWT` + 401 自动 logout
* `LoginGate` 全屏遮罩: OTP / 密码 / 注册 三 tab
* `SettingsModal` — API key (localStorage) + `save_my_works` 开关 + 设置密码
* `TopBar` — 右上角邮箱徽章 + 设置齿轮
* `App.jsx` 包 `AuthProvider`, 未登录全屏拦截

**前端 — 随机按钮**
* `HomeView` 标题/种子输入框右侧 🎲 按钮, 联动客制化
* `services/api.js` 全部走 `authedFetch` (自动注入 `Bearer` + 401 处理)

依赖
* `requirements.txt`: `passlib` + `bcrypt<5` + `python-jose` +
  `aiosmtplib` + `email-validator`
* `config.example.json` + deploy 模板: 新增 `auth` + `smtp` 段
* 腾讯企业邮箱 SMTP: `smtp.exmail.qq.com:465` SSL

### Fixed — TickDB 跨线程 `ProgrammingError`

多租户改造后 FastAPI `Depends` 解析 runtime 并把 `runtime.tick_db.X(...)`
在 sync handler 的 thread executor 里执行, 同一 `TickDB._conn` 被不同 worker
线程触达 → sqlite3 默认 `check_same_thread=True` 抛 `ProgrammingError`,
`/api/tick/{history,event-stats,action-patterns}` 全 500。

* `sqlite3.connect(check_same_thread=False)` 关掉守卫
* `threading.Lock` 串行所有 `_conn` 操作 (autocommit 模式下并发 BEGIN 也会
  transaction within transaction)
* 验证: 8 线程 × 20 op 跨线程压测无报错

### Tests
* 45 用例新增 — `test_auth_password / jwt / rate_limit / otp /
  multi_tenant_isolation / llm_random_routes`
* `416 → 461` 用例; 60+ legacy 测试因 API 签名变化需后续迁移
* 兼容 shim 保留 `_container` / `_assert_path_within_novels_root` 让旧测试
  collection 通过

---

## [2.25] — 2026-06-06

### Added — `bootstrap_world` 任务化 + 链式触发首节

v2.24 默认 `auto_bootstrap=True` 把"创建空壳"与"种子化首节"并成一步,
冷启动一个 fresh novel (zero CharacterAgent / OpenLoop / StyleAnchor)
立刻入 `bootstrap_section`, executor 推 30 tick 全沉默到硬上限切节,
首节几乎空 — 烟测真实复现了这个失败模式。

v2.25 把两步拆开:
1. `POST /api/novels` (默认 `auto_bootstrap=False`) — 仅创建空壳
2. `POST /api/novels/{id}/bootstrap-world` — 4 阶段冷启动后链式入队首节

### v2.25-a (后端)
* `TaskKind` 加 `bootstrap_world`, `max_ticks=4` 借用为阶段总数
* `backend/api/bootstrap_routes.py` 新增
  `POST /api/novels/{id}/bootstrap-world` — `seed` 必填,
  `positioning/references/also_generate_first_section` 可选, 后三者默认值
  与 `bootstrap_prompts.py main()` 对齐
* `_reload_runtime` — bootstrap 改了 `tick_state.json`, 注册表里那个内存空
  state 的 runtime 实例必须丢掉, 下次 `get_runtime` 重读盘
* `_spawn_chained_first_section` — bootstrap 完成后入队
  `kind=bootstrap_section` 任务, 复用 `section_routes._make_section_executor`
* `routes.create_novel` 默认改 `auto_bootstrap=False`, 保留显式 True
  路径供测试 / 节级管线对照实验

### v2.25-b (前端)
* `HomeView` 创建表单加「世界种子」必填 textarea + 折叠的「作品定位 /
  参考作家」高级配置, 一次提交触发 `bootstrap_world → bootstrap_section`
  两段任务
* `TaskListPanel` 对 `bootstrap_world` 任务用 `tick_count/max_ticks` (4 阶段)
  代替字数进度条, 显示「阶段 N/4」
* `bootstrapWorld(novelId, {seed, positioning?, references?,
  also_generate_first_section?})` API 封装

### Tests
* `test_bootstrap_routes.py` (8) — 404/409/失败态/端到端/链式触发/字段透传/
  字段默认/router 已注册
* `test_create_novel_bootstrap.py` — `default_skips_bootstrap_task_v225` /
  `with_auto_bootstrap_true_still_spawns_task`
* 全套 **451** 通过

---

## [2.24] — 2026-06-05

### Added — SectionCloser Agent + 任务队列 + per-novel TickRuntime

**P1 — 后端铺底**
* `backend/agents/section_closer.py` — 新增 SectionCloser, 判定 tick 流是否
  应当切节: `lower <= words < upper` 调 LLM judge,
  `words >= upper` 不调 LLM 直接切 (上限保护优先于 LLM); `words < lower`
  强制继续
* `backend/tasks/` 模块 — `TaskManager` 单例 (内存) + `task_models.py`
  (`TaskKind`) + `task_routes.py`:
  * `GET /api/tasks{?novel_id}` — 全量任务集
  * `GET /api/tasks/{id}` — 单个任务
  * `POST /api/tasks/{id}/cancel`
  * SSE `GET /api/tasks/{id}/stream`
* `backend/sections/section_store.py` — `TickSection` (Pydantic):
  `chapter/section/title/content/word_count/...`, JSON 持久化
* `Orchestrator.last_narrator_output` 公开 — `SectionTask` executor 在每
  tick 后区分 `narrate` / `silent`
* access log 过滤 — `/api/tasks` 与 `/api/tick/status` 高频轮询不上日志

**P2 — API 改造**
* `POST /api/section/generate` — 续写下一节, 走任务队列 + 自动首节
* 节级管线端点加 `/api/legacy/` 别名 (原 `/api/generate` /
  `/api/generate/stream` / `/api/chapter/advance` / `/api/rollback` /
  `/api/snapshots` / `/api/reset` 同时保留), 让前端测试栏使用
* `TickRuntime` 注册表 key 由 `novel_id` 升级到 `(user_id, novel_id)`

**P3 — 前端**
* `frontend/src/components/TaskListPanel.jsx` (新) — 轮询 `/api/tasks` 3s +
  per-task SSE 替换轮询; 终态保留 60s (v2.34 改 30 分钟); 进度条 +
  cancel 按钮
* `App.jsx` 工具栏「测试」分类挂「节级管线 (legacy)」, 主路径常驻
  `TaskListPanel`
* `HomeView.handleCreate` / `handleContinue` 改任务流, 不再就地 SSE;
  toast「已加入任务队列, 见左下面板」
* `NovelView` 同时拉 `/api/section/list` 与 `/api/sections`, 按
  `(chapter, section)` 合并, tick 驱动优先, legacy 退让

### Tests
* `test_section_closer.py` / `test_section_routes.py` /
  `test_section_store.py` / `test_task_manager.py` /
  `test_main_wiring_v224.py` / `test_tick_runtime_registry.py`
* **443/443** 通过, 无 v2.24 之前用例回归

---

## [2.23] — 2026-06-05

### Fixed — 节级管线最终修

* **题材锚定** — 节级管线生成时透传 `seed / title / positioning` 给
  `OutlineAgent`, 防止节级管线脱离主题漂走
* **节标题生成** — 每节调 LLM 单独产 `title` 字段 (而非沿用 chapter 标题)
* **UI 集中化** — 节级管线 (legacy) 与 tick 驱动节统一在 `NovelView`
  展示 (v2.24 P3 进一步合并视图)

---

## [2.22] — 2026-06-04

### Fixed (P1)
* `provider 落盘 + 原子化` — `PUT /api/config/llm` 写 `config.json` 改
  `tempfile + os.replace` 原子写, 防止崩溃留下半截文件
* 图端点校验 — `/api/graph/entities POST` 加 entity_id 唯一性 + attributes
  类型校验; `/api/graph/relations POST` 校验 from/to 实体存在
* API 4xx 收敛 — 多个端点把内部 `KeyError` / `ValueError` 包成 404/422,
  不再裸 500

### Fixed (P2)
* 前端 UI 字段对齐 — `EventInjector` 注入事件表单字段名与后端
  `InjectEventRequest` 对齐 (`type / visible_to / narrative_value / ...`)
* Orchestrator 注入事件不丢失 — `_injected_pending` 在 tick 入口被 drain,
  `_run_tick_unlocked` 异常时改为 try/finally 保护

### Refactored (P3)
* `tools/drive_ticks.py` 归档到 `old/tools/` — 历史 smoke 工具, 已被
  pytest harness 取代

### Fixed (v2.21.1)
* `CharacterState` 字段名是 `current_location` 不是 `location` — v2.18 落
  state 转移字段时混了, 修齐

### Tests
* `test_v2_22_p1_regressions.py` / `test_v2_22_p2_regressions.py`

---

## [Deploy] — 2026-06-07 to 2026-06-08

### Added — 多目标生产部署

**Linux + systemd + Cloudflare Tunnel + Vercel** (`deploy/{backend,
cloudflared,frontend}/`)
* `backend/install.sh` 一键装系统依赖 + venv + pip + 用户 + systemd, 留空
  API Key 等手动填
* `backend/update.sh` git pull + 条件 pip + 重启 + 健康检查
* `backend/backup.sh` zstd/gz 备份 `data/` + 滚动清理
* `novel-agent.service` 沙箱加固 (`ProtectSystem=strict` +
  `ReadWritePaths`)
* `cloudflared/install.sh` 装 cloudflared + tunnel create + 凭据落地 + systemd
* `cloudflared/config.yml.example` SSE 友好 (`connectTimeout 30s`,
  `keepAliveTimeout 90s`, `disableChunkedEncoding=false`)
* `frontend/vercel.json` SPA rewrites + 长缓存 + 安全头
* `frontend/env.production.example` `VITE_API_BASE` + `VITE_BASE_PATH`

**Windows + Docker Desktop (token 模式 CF Tunnel)** (`deploy/docker/`)
* `Dockerfile` python:3.11-slim, 非 root (uid 1001), tini PID1,
  healthcheck 用 urllib (slim 没 curl), HF cache 走环境变量到
  `/home/app/.cache`
* `docker-compose.yml` backend + cloudflared 两容器编排, token 模式无需
  本地 `config.yml`, backend 只 bind `127.0.0.1:8762`, cloudflared
  `depends_on healthy`, 业务数据全部走 bind mount
  (`../../data/{backend,storage,hf_cache}`), `config.json :ro` mount 支持
  热改
* `.dockerignore` 排除 `.git / .venv / node_modules / data/ / old/`
* Windows 详细步骤 README (CF 网页拿 token → 填 `.env` → `up -d` →
  网页配 hostname), 含资源占用 / 备份 / 升级 / 排错 9 节

### Refactored — 前端 `base` 默认根路径
* `frontend/vite.config.js` `base = process.env.VITE_BASE_PATH || '/'`
  (此前 `/nw/`)
* `backend/main.py` `app.mount('/', StaticFiles(..., html=True))`, 删多余
  root redirect
* `frontend/vercel.json` SPA rewrites 改根路径 (`/(.*) → /index.html`)
* 同源部署直接 `http://host:8762/` 即可, Vercel 部署不再需要
  `VITE_BASE_PATH=/`

### Fixed
* `deploy(docker)` 默认走国内镜像源 (daocloud + 清华 PyPI/apt) — docker.io
  在国内频繁超时, 基础镜像 / cloudflared / PyPI / debian apt 四处都切到
  国内, 全部参数化 (`REGISTRY` / `PIP_INDEX_URL` / `APT_MIRROR` /
  `CLOUDFLARED_IMAGE`)
* `fix(core/config)` active provider 缺凭据时按顺序 fallback 到完整 provider —
  `_complete(c) = api_key + base_url + model 三者全齐`, 按 `_FALLBACK_ORDER`
  (`deepseek → mimo → custom`) 找第一个完整的; 全员不完整时保留请求的
  provider, 让上游 "Missing credentials" 错误清晰
* `fix(deploy/docker)` `chown /app` + 预建 `results/temp` — `USER app
  (uid 1001)` 在 `/app` 下 mkdir 子目录 `EACCES`, 导致 `core/config.py`
  模块级 `RESULTS_DIR.mkdir()` 抛 PermissionError, 被
  `backend/config/settings.py` 裸 except 静默吞掉, LLM 凭据解析回兜底
  (`api_key=""`), 启动期 openai SDK 报 Missing credentials, 容器无限 restart

---

## [2.21] — 2026-06-04

### Fixed — 一次性清掉 10 个 P0–P3 隐患

P0:
* **`CharacterAgent._filter_visible_events`** — 此前 `visible_to=['all_in_location']`
  的事件被无条件下发给所有被唤醒角色, 直接违反 prompts.md 第 0 节"角色只能用
  自己知道的信息"。修复: 接收 `cur_location` 参数, 仅当 `e.location == cur_location`
  才可见。`'all'` 保留为真·全局广播
* **`_resolve_llm_block` 优先级翻转** — `core/config.py` 给 `DEEPSEEK_BASE_URL/MODEL`
  设了 `os.getenv` 默认值, main_env 分支任何场景都命中,
  `config.json.llm.api_key` 实际从未被读到 → PUT `/api/config/llm`
  写入的 key 静默无效。新规则: config.json.llm.api_key 非空 → config.json
  整段为权威 (UI 写入路径唯一能生效的入口); 否则回退到 main_env

P1:
* **TickState / SummaryTree 损坏 quarantine** — 此前 load 失败只 log + return
  False, 下次 `save()` 用 fresh 状态原子覆盖原路径, 真实数据永久丢失。
  修复: 损坏文件 rename 到 `{path}.corrupt.{ts}`, 可人工恢复
* **TickDB INSERT OR IGNORE** — events / tick_log 此前用 `INSERT OR REPLACE`,
  LLM 复用 `event_id` 时旧记录被静默擦掉, 污染 Showrunner / NoveltyCritic 的
  窗口聚合。改为 `INSERT OR IGNORE` + warning
* **`switch_novel` 两阶段** — tick 切换失败仅 warning 然后 return 200, UI 看到
  "成功"但 `/api/tick/*` 仍指向旧 novel。改为先切 tick, 失败显式 503,
  legacy 仍停在旧 novel; tick 成功后再切 legacy

P2:
* **OpenLoop.origin_event_ids** — orchestrator.py:543 已经在每条新 loop 上
  `mark_protected(origin_event_ids)`, 但模型没有此字段, `_TickModelConfig.extra="ignore"`
  静默吃掉 LLM 输出 → 保护分支永远是空 list。加字段 + 更新 Narrator
  system prompt 的输出 JSON 模板
* **前端写端点统一 `assertOk`** — `runOneTick` / `switchNovel` / `pauseTick` /
  `resumeTick` / `fetchTickHistory` / 各 novel CRUD 此前裸 `return res.json()`,
  后端 4xx/5xx 时 toast 显示假成功 ("Tick undefined 完成")。抽公共
  `assertOk(res)` helper 处理 string detail 与 FastAPI 422 list 两种错误体
* **`generateSectionStream` 加 `onError`** — SSE 流失败时也走 `onDone()`,
  UI 看不出区别。新增可选 `onError` 回调 + `response.ok` 校验; NovelView /
  HomeView 已 wire `onError → reject`, GeneratePanel 不传 onError 保持兼容
* **test_llm_config_provider_switch 不再改真实 config.json** — autouse
  fixture monkeypatch `_load_config` / `_save_config` 重定向到 tmp_path

P3:
* **Vite proxy 强制 IPv4** — `localhost` 在 Windows/Node 某些环境下解析为
  IPv6 (`::1`), 后端 uvicorn 默认只绑 IPv4 → 前端开发时 `/api/*` 全 ECONNREFUSED。
  CLAUDE.md 早已约定 host=127.0.0.1, 此前实现遗漏

### Security
* README 顶部加 ⚠️ 警告: 管理 API 默认无鉴权, 仅适合本机 / 内网部署。
  公网需自行加 reverse proxy 鉴权。token 鉴权开关排入后续版本路线

### Tests
* 新增 5 个测试文件, +26 用例覆盖本轮修复:
  * `test_character_visibility.py` (8) — 可见性矩阵
  * `test_open_loop_origin_events.py` (4) — OpenLoop 字段 + Narrator 解析
  * `test_llm_config_fallback.py` (5) — 三优先级分支
  * `test_state_quarantine.py` (6) — TickState / SummaryTree quarantine
  * `test_tick_db_insert_ignore.py` (4) — 重复 event_id / tick_id
  * `test_switch_novel_two_phase.py` (3) — tick 失败 503 路径

---

## [2.19.6] — 2026-06-04

### Refactored — 抽 LLM JSON fence helper 到 `nf_core.json_utils`

10 个 v2 agent (`character_agent` / `narrator_agent` / `novelty_critic` /
`event_injector` / `memory_compressor` / `character_arc_tracker` / `showrunner` /
`story_arc_director` / `world_simulator` / `narrative_critic`) 此前各自内联同
一段 ~5 行 markdown fence stripping, 行为漂移风险。每次 LLM 输出格式变化要
追 10 处, v2.16 加严输出约束时已经在两个 agent 之间出现细节差。

* **新增** `backend/nf_core/json_utils.py:strip_code_fence(text) -> str` —
  保持原 7 处实现行为不变, 不引入新语义, 避免跨 agent 回归
* **替换** 9 个 v2 tick agent 的内联 fence 块为 `strip_code_fence(raw)`, 每文件
  净 -5 行
* **`narrative_critic._strip_code_fence`** 改为转调公共 helper, 保留私有别名
  给模块内多个调用方 (向后兼容)
* **`update_agent.py`** (legacy v1 节级管线) 保留原内联实现, 行为略不同
  (`==` 而非 `startswith`), 不在 v2 tick 主路径暂不动

### Tests

* `backend/tests/test_json_utils.py` 新增 9 用例覆盖 helper 全部边界
  (plain JSON / fenced / fenced+lang / 前后空白 / 内联反引号不剥 /
  空字符串 / 仅空白 / 开但不闭 / 多行 JSON)
* 全套 343 用例通过 (此前 334, +9, 0 回归); 净 -51 行

---

## [2.19.5] — 2026-06-04

### Fixed — `chat_stream` 异常路径也记账

v2.19 让 `chat_stream` 走 tracker 记账, 但 `record` 在 `async for` 循环之后才
调用。若 stream 中途抛错 (provider 502 / 网络断 / safety filter mid-stream),
异常正常传播给调用方, 但 `tracker.record` 永远不跑 — 失败的大段写作完全不进
monitoring, 生产侧的失败率和 cost 数据全是虚低数据。

`async for stream` 包进 `try/finally`, finally 路径无论成功/失败都尝试
`tracker.record`。usage 缺失时记 0 token, 但 `snapshot.call_count` 和
`by_agent` 仍能反映这次尝试。

### Tests

* `test_chat_stream_observability::exception_still_records_attempt` 新增 —
  `_ExplodingStream` 在 partial 输出后抛 RuntimeError, 断言异常被传播 AND
  `tracker.call_count == 1`
* 全套 334 用例通过 (此前 333, +1, 0 回归)

---

## [2.19.4] — 2026-06-04

### Perf — `_default_narrative_writer` 卸 IO 到 worker 线程

Narrator 每 tick 产 1.5k-3k 字 narrative 后调 `_default_narrative_writer`
落盘, 原实现是 `async def` + 内部裸 `os.makedirs` / `with open()` 同步 IO,
await 时整个 event loop 被磁盘 IO 阻塞 5-50ms。

v2.18 Phase 7 把 Narrator 与只读三件套 (Guardian / Critic / ArcTracker)
`asyncio.gather` 起来, 预期重叠 LLM 等待时间。但 Narrator 写盘阶段仍在 event
loop 上, 只读 agent 的 LLM 回调被推迟, 并发收益打折。

把 `mkdir + open + write` 包进内部 `_sync_write` 闭包, `asyncio.to_thread`
卸到 worker 线程。Python 3.9+ 的 `to_thread` 会自动 `copy_context()` 到 worker,
ContextVar (含 `_current_tick_var`) 透传不变。

### Tests

* `backend/tests/test_narrative_writer_nonblocking.py` — 新增 3 用例
  * `writes_file_correctly` — 黑盒回归 (文件 + 内容 + 编码)
  * `runs_off_main_thread` — 白盒钉死 (`open` 调用所在 `thread.id != event loop tid`)
  * `does_not_block_loop` — 端到端: monkeypatch 80ms 慢盘 + 并发 80ms
    `asyncio.sleep`, 断言总耗时 < 130ms; patch 前实测 172ms (串行),
    patch 后 ≤ 90ms (并行)
* 全套 333 用例通过 (此前 330, +3, 0 回归)

---

## [2.19.3] — 2026-06-04

### Added — `POST /api/tick/open-loops` 防 dup-id 静默覆盖

`TickState.add_open_loop` 是 `_open_loops[loop.id] = loop`, 同 id 直接覆盖。
路由从未做 id 检查, 管理员二次提交同 id 会丢失原 loop 的运行时累积:
`last_referenced_tick` (Narrator 引用过的时点) / `opened_tick` / 累积的
`max_age_ticks`。一旦覆盖, 冷线索检测会把其实很新的伏笔判为被遗忘,
urgency 漂走。

* `TickState.has_open_loop(loop_id)` — 新增轻量查询 API
* `POST /api/tick/open-loops` 在 id 已存在时返回 **409**, 并提示 RESTful 替换
  路径: 先 DELETE 再 POST

### Tests

* `backend/tests/test_open_loops_admin_api.py` — 新增 4 用例
  * `first_time_ok` (happy path 回归)
  * `duplicate_id_returns_409` — 模拟 Narrator `touch_open_loop` 后再 POST 同 id,
    断言 409 且 `last_referenced_tick` 不被回零
  * `delete_then_repost_ok` — RESTful 替换路径仍能工作
  * `distinct_ids_independent` — 不同 id 不冲突
* 全套 330 用例通过 (此前 326, +4, 0 回归)

---

## [2.19.2] — 2026-06-04

### Fixed — `injectTickEvent` 错误响应翻译为 Error

v2.19.1 在后端给 `/api/tick/inject-event` 加了 422/409 边界, 但前端 wrapper
`res.json()` 不会因为非 2xx 抛错, 调用方拿到 `{detail: ...}` 然后访问
`res?.event?.tick → undefined`, 上游 `TickControlPanel` 仍 toast
"事件已注入 (tick undefined)"。等于服务端校验生效, 用户却完全感知不到。

* 显式 `res.ok` 检查, 非 2xx 抛 `Error(detail)`
* 兼容两种 FastAPI detail 形态:
  * `HTTPException` → `detail: string` (我们自己抛的 422/409 走这条)
  * Pydantic 422 → `detail: [{loc, msg, type, ...}]`, 拼接 `loc + msg`
* `TickControlPanel.handleInject` 既有 catch 分支自动起作用, toast `error`
  显示后端返回的真实原因

### Verified

* `npm run build` 通过 (1066 modules, 3.7s)
* 后端 inject-event 错误响应结构已与前端 parser 对齐 (live curl 验证)
* 后端测试套件无变化, 326 passed

---

## [2.19.1] — 2026-06-04

### Added — `/api/tick/inject-event` 输入校验加固

修补 3 个静默陷阱:

1. **type 非法值返回 500** (而非 422) — `InjectEventRequest.type` 是 plain
   `str`, 任何非 `EventKind` Literal 值都通过 FastAPI 边界, 直到
   `Event(type=...)` 内部 Pydantic 校验时才抛 ValidationError, 被 FastAPI
   包成 500 + 暴露内部模型路径
2. **`visible_to=all_in_location` 配空 location → 静默丢弃** — `visible_to`
   不传时 fallback 成 `['all_in_location']`; 若 location 也为空,
   `Orchestrator._collect_affected_characters` 会因 location 不匹配跳过所有
   角色, 事件最终对谁都不可见。调用方拿 200 而事件被悄悄吞掉
3. **显式 id 与 `_injected_pending` 已有项冲突 → 静默覆盖** — 同 id 的两个
   Event 同时进队列, 下游消费不可预知

变更 (`backend/api/tick_routes.py`):

* `InjectEventRequest.type` 改为 `EventKind` Literal → FastAPI 自动 422
* 计算最终 `visible_to` 后, 若含 `all_in_location` 但 location 空 → 422
* 显式 `req.id` 与 `_injected_pending` 中 id 重复 → 409
* 自动生成 id 路径 (`req.id=None`) 沿用 `evt_user_{tick}_{len(pending)}`, 不变

### Tests

* `backend/tests/test_inject_event_validation.py` — 新增 8 用例覆盖
  unknown_type_422 / valid_type / all_in_location_requires_location /
  default_visible_to_empty_location / explicit_visible_to_no_location /
  duplicate_id_409 / auto_generated_ids_no_collide /
  narrative_value_out_of_range
* 全套 326 用例通过 (此前 318, +8, 0 回归)

---

## [2.19.0] — 2026-06-04

### Added — `chat_stream` 接入 budget / observability 闭环

`chat()` 已有 budget pre-check + ContextVar tick + tracker 记账 +
`model_override`, 但 `chat_stream()` 此前完全脱离: 不做 `can_afford`, 不
`record`, 不读 ContextVar, 不支持 override。节级 SSE
(`writer_agent.write_stream` → `llm_client.chat_stream`) 仍是活路径,
每段 1.5k-3k 字写作的 prompt/completion token 完全不入 tracker — 生产成本
不可见, 预算上限对 streaming 无效。

变更:

* `llm_client.chat_stream()` 新增 `agent_id` / `priority` / `tick` /
  `model_override` 参数
* 调用前 `tracker.can_afford()` 拦截; 非 critical 超额时抛 `BudgetExceeded`,
  底层 `_client.chat.completions.create` 不被调
* 透传 `stream_options={'include_usage': True}`, 从最后含 usage 的 chunk 提取
  prompt/completion token 调用 `tracker.record()`; 提供商不返回 usage 时记 0
* `tick` 默认 -1 时 fallback 到 `_current_tick_var` (与 `chat()` 同源)
* `writer_agent.write_stream()` 标注 `agent_id='writer_agent'`
  `priority='critical'`

### Tests

* `backend/tests/test_chat_stream_observability.py` — 新增 7 用例覆盖
  records_usage_from_final_chunk / tick_falls_back_to_contextvar /
  rejected_by_budget_does_not_call_create / critical_bypasses_budget /
  handles_missing_usage / model_override_passed_to_create /
  requests_usage_via_stream_options
* 全套 318 用例通过 (此前 311, +7, 0 回归)

---

## [2.18.0] — 2026-06-03

v2.18 是 9 个 Phase 的连续推进, 围绕 **"状态硬转移 + Guardian 闭环 + tick
并行化"** 三条主线, 全程保持单进程 / 单仓库 / 不引入新依赖。

### Phase 1 — `CharacterState.money` + `CharacterAction.money_delta`

* `CharacterState` 加 `money: int` (clamp ≥ 0); `CharacterAction` 加
  `money_delta: int` 表达角色意志中的金钱变动 (买/卖/赌/送)
* `Orchestrator._apply_actions` 落 `money_delta`, 越界 clamp 并打
  `money_overdraft` flag

### Phase 2 — `AgentRuntimeState` + Orchestrator cooldown

* 新增 `AgentRuntimeState(agent_id, last_invoked_tick, failure_count,
  cooldown_until_tick, model_tier_override, summary_cache)`
* `TickState` 新增 `upsert_agent_runtime_state` / `record_agent_invocation` /
  `is_agent_in_cooldown`; `FAILURE_THRESHOLD=3`, `COOLDOWN_TICKS=5`
* Orchestrator 阶段 3 调度前过滤 in-cooldown 的 character_agent, 进程重建后
  从 `tick_state.json` 恢复 `failure_count`

### Phase 3 — `StateOp` / `StatePatch` 外部权威补丁层

* `StateOpKind = Literal['set','add','append','remove']`,
  `StatePatchTarget = Literal['character','world','location','faction']`
* `Orchestrator._apply_state_patches` 在阶段 5d 应用; `current_location` 设值
  校验 `valid_location_ids`, `money` clamp 0+ 并打 `money_overdraft`
* 设计原则: 角色意志 (`CharacterAction`) 与外部权威 (`StatePatch`) 分通路,
  顺序"意志 → 权威", 让权威能"补一刀"

### Phase 4 — `ConsistencyGuardian.scan_hallucination_rate`

* `_HALLUCINATION_FLAGS = (inventory_without_action, location_without_move,
  money_without_action)` — 与 `Orchestrator._consistency_flags` 输出对齐
* `scan_hallucination_rate(events, threshold=0.3)` 纯计数, 100% 确定性, 按
  `participants[0]` 归账; 严格 `>` 阈值才报, 防边界震荡
* `async scan()` 总是先跑幻觉率扫描 (即使 LLM 评估器不可用),
  结果合并进 `GuardianOutput.conflicts`

### Phase 5 — Guardian → `AgentRuntimeState` 闭环观测 (默认 shadow mode)

* `AgentRuntimeState` 增 `hallucination_hits` / `degrade_recommendations` /
  `last_degrade_recommended_tick`; 旧持久化文件 load 时自动取默认 0
* `TickState.record_degrade_recommendation(agent_id, tick, hits,
  set_override=None)` — `set_override=None` 时仅写统计, shadow mode
* `TickState.get_hallucination_stats()` — 仅返回曾被建议过降级的 agent, 含
  `model_tier_override_active` 布尔
* `Orchestrator._ingest_guardian_conflicts` 读 `HALLUCINATION_AUTO_DEGRADE`
  env, shadow / active 双路径

### Phase 6 — `model_tier_override` 激活路径

* `LLMClient.chat` 加 `model_override: str | None`,
  `effective_model = model_override or self._model`; token budget record 用
  `effective_model` 让降级的 token 消费正确归账到 fallback model
* `CharacterAgent.decide(... model_override=...)`,
  `batch_decide(... model_overrides: dict[cid, tier]=None)`
* `Orchestrator._collect_model_overrides` 阶段 3 一次性收集,
  `batch_decide` 前注入
* 生产路径: shadow 观察 N 天 (Phase 5) → `HALLUCINATION_AUTO_DEGRADE=1` 切
  active → 实际生效仍需 provider 层 `fallback_model` 路由 (config.json)

### Phase 7 — tick 提速 (concurrency 3→6 + Narrator 与只读 agent 并行)

* `_default_concurrency` 3 → 6, 6 个 A/B 级角色一次并发 `batch_decide`
* `_phase7_readonly_agents` — Guardian / NoveltyCritic / ArcTracker 用
  `asyncio.gather(return_exceptions=True)` 并发, 单个失败不阻塞其他
* `run_tick` 主流程: `asyncio.gather(_narrate, _phase7_readonly_agents)`,
  Narrator LLM 等待与 Guardian 等 LLM 等待重叠
* `MemoryCompressor` 仍串行 (写 memory_store, 防 race);
  `Showrunner` / `EventInjector` / `StoryArcDirector` 仍串行 (数据依赖)
* 预期: tick=60 (三件套全触发) 节省 ~3 个 LLM 等待

### Phase 8 — `EventInjector` 产 `StatePatch`

* `EventInjectorOutput.state_patches: list[StatePatch]` — P3 引入的补丁层
  终于有 LLM 产源
* SYSTEM_PROMPT 加 `state_patches` 字段说明 + 严格 JSON 示例, 明确"仅对强
  因果、必须立即生效的事件添加 patches; 一般事件不需要"
* 适用场景: 爆炸波及房间所有人 / 瘟疫扩散 / NPC 当场死亡; 不借道
  CharacterAction (那是角色意志)
* `Orchestrator` 阶段 5d 在 `_apply_actions` (角色意志) 之后调
  `_apply_state_patches` (外部权威), `TickSummary.agents_called` 加
  `state_patches(applied=X,rejected=Y)` 诊断
* 单条 Pydantic validation 失败跳过, 其他保留 (与 events 解析容错策略一致)

### Phase 9 — `GET /api/tick/diagnostic/hallucination` Guardian 闭环外露

* 返回 `ts.get_hallucination_stats()` (按 agent_id 索引)
* 字段: `degrade_recommendations` / `hallucination_hits` /
  `last_degrade_recommended_tick` / `model_tier_override_active`
* 顶层加 `auto_degrade_active: bool` — 反映 `HALLUCINATION_AUTO_DEGRADE` env
* `tick_state` 未注入时返回 503 (与现有 endpoint 一致, 不崩)
* 生产消费模式: shadow 期监控真阳率, active 期看 `model_tier_override` 命中分布

### Tests (累计 v2.18 全程)

* 263 (Phase 2) → 276 (Phase 3) → 282 (Phase 4) → 291 (Phase 5) →
  295 (Phase 6) → 303 (Phase 7) → 307 (Phase 8) → 311 (Phase 9), 全程 GREEN

### Tooling

* `scripts/smoke_v218.py` — 真实 LLM smoke harness, 15 tick 实测发现 money 端到端
  路径与 shadow mode 正确; 6 agent failure_count=0, override=""

---

## [2.17.0] — 2026-06-03

### Runtime coherency sweep — 6 项修复 + CodeQL 切断

1. **启动默认 novel 对齐** (`main.py` + `api/routes.py` + `novel_manager.py`)
   * `novel_manager.resolve_default_novel_id()` 作为单一权威入口
   * `main.py` startup 同时把 active id 注入 legacy pipeline 与 tick runtime
   * `/api/stats` 与 `/api/tick/*` 首屏指向同一本小说
2. **LLM 配置热更新** (`config/settings.py` + `nf_core/llm_client.py` +
   `api/routes.py`)
   * `resolve_llm_block_now()` + `LLMClient.reload()` — 不重启进程切 provider
   * `PUT /api/config/llm` 调用 `reload()` 重建 `AsyncOpenAI` 实例
   * 响应中新增 `applied` 字段, 调用方可见实际生效值
3. **TokenBudget 调用前硬拦截** (`nf_core/llm_client.py` +
   `nf_core/token_budget.py`)
   * 新增 `BudgetExceeded` 异常类型
   * `LLMClient.chat()` 在 OpenAI 调用前查询 `can_afford()`
   * critical 始终放行; medium / optional 超额时抛 `BudgetExceeded`, 调用方
     既有 try/except 自动降级
4. **前端 Tick 控制台** (`frontend/src/components/TickControlPanel.jsx`)
   * 接入 `runOneTick` / `pause` / `resume` / `inject-event` / `history` /
     `open-loops`
   * 每 3 秒轮询 status, 注入事件表单, 历史 15 tick 表格
   * `App.jsx` 把"Tick 控制台"入口指向新组件
5. **`agent_routes` tick 字段对齐** (`persistence/tick_db.py`)
   * `TickDB._row_to_dict` 同时暴露 `tick_id` / `tick` /
     `narrator_produced` / `narrator_produced_text` / `narrator_chars` /
     `narrator_output_chars` 双键
   * `agent_routes._scan_last_invoked` 不再返回 `tick=None`
6. **legacy pipeline 持久化补全** (`pipeline/engine.py`)
   * `save_state` 写 `summary_tree_legacy.json` + 触发 KG snapshot
   * `load_state` 恢复 `SummaryTree` + 回滚 KG 到最新快照
   * 与 tick runtime 的 `summary_tree.json` 用独立文件名, 不冲突

### Security — CodeQL high severity 全部切断

* **path-injection (3 处)**: `tick_state.py` / `tick_runtime.py` /
  `tick_db.py` 的 `os.makedirs` 接受 `_resolve_novel_data_dir` 返回值,
  CodeQL 视为受 `ACTIVE_NOVEL_ID` / `ACTIVE_NOVEL_DATA_DIR` 环境污染。
  在 `_resolve_novel_data_dir` 入口增 `_sanitize_within_novels_root`
  (realpath + commonpath 强制 candidate 落在 `backend/data/novels/` 下),
  复用 `novel_manager._validate_novel_id` 正则白名单
  (字母/数字/下划线/中文/-) 拒绝 `../etc` 之类越界 id
* **clear-text-logging (3 处)**: `LLMClient.reload` 日志去掉 `base_url` /
  `model` / `source` 字符串, 仅记长度 (整数, 非敏感); 它们都从含
  `api_key` 的 dict 派生, 同一 dict 中其它字段也被 CodeQL 标污
* `agent_routes` stack-trace-exposure (PR #6) + `_safe_summary`
  clear-text-logging (PR #4) 同期修复

### Tests

* `backend/tests/test_v217_coherency_sweep.py` 新增 14 单元测试
* 全套 245 用例通过 (231 现有 + 14 新增)
* `npm run build` 通过 (vite 6.4, 6.5s)
* 真实 LLM (mimo-v2.5-pro) bootstrap + 1 tick + 6 endpoint 端到端验证通过

---

## [2.16.0] — 2026-06-03

### P0 — 硬状态转移落字段

`CharacterAction` 加 `new_location` / `inventory_added` / `inventory_removed`
/ `status_added` / `status_removed` / `relationship_deltas`,
`Orchestrator._apply_actions` 落到对应 `CharacterState` 字段并同步
`WorldState.locations.present_characters`。

之前角色"去了安全屋"但 state 仍是原 location, 长期连贯性靠 Narrator 圆场不
可持续; v2.18 Phase 4 的 hallucination flags
(`location_without_move` / `inventory_without_action`) 就建立在本字段之上。

### P0 — LLM 可观测性

`nf_core.llm_client` 加 `ContextVar` 承载当前 tick, **18 个 LLM 调用点**全部
标注 `agent_id` + `priority`。`TokenBudgetTracker` 不再全是
`unknown/medium/tick=-1`, 能识别哪条 agent 最贵, 也为 v2.19 的 chat_stream
观测打地基。

### P1 — 中文输出约束

* `CharacterAgent` system prompt 加显式语言要求
* `_parse_action` 检测连续英文词污染时打 `lang_contamination` flag
* 防止事件日志再出现 `Diana uses sword` 类英文动作句

### P1 — 多地点冷启动

`bootstrap_prompts.py` 的 `PROMPT_WORLD` 要求 ≥5 地点并按 城市 / 边境 / 秘所
/ 旷野 / 聚会点 分类, 防止角色都挤在 `loc_1` 单一地点导致舞台感重复。

### Tests

* 4 个新测试文件 + `test_orchestrator_p0` 加 2 个端到端用例
* 全套 231 用例通过 (此前 ~217 / 0 回归)

---

## [2.15.0] — 2026-06-03

### P0 sweep — 并发/路径安全/记忆闭环/runtime 注册表

针对实测发现的 4 类生产隐患, 不引入新依赖、不破契约, 全部低破坏面修复。

* **并发**: `CharacterAgent.batch_decide` 用 `asyncio.Semaphore` 限并发已存
  在, 但 `_default_concurrency` 来源不统一; 集中到环境变量
  `CHARACTER_AGENT_CONCURRENCY`, 单一入口便于 v2.18 Phase 7 提到 6
* **路径安全**: `novel_manager._assert_path_within_novels_root` 与
  `_validate_novel_id` 联合校验, 拒绝 `../` / 绝对路径 / 非法字符 novel_id;
  v2.17 path-injection 修复在此基础上扩展 (CodeQL 也认这条 sanitizer)
* **记忆闭环**: `PriorityMemoryStore.touch()` / `mark_protected()` 调用点
  对齐 Orchestrator 阶段 6, 防止 `events_consumed` 漏 touch 让保护事件被
  压缩误删
* **runtime 注册表**: `TickRuntime` 装配的 8 个可选层 (memory_store /
  story_arc_director / character_arc_tracker / fact_ledger / safety_filter
  / token_budget / creativity_scorer / branch_manager) 显式校验,
  缺失参数立即抛, 不靠默认构造静默退化

### Security

* `agent_routes` stack-trace-exposure (CodeQL py/stack-trace-exposure) 修复 —
  异常不再透传原始 traceback 到 HTTP 响应
* `_safe_summary` 重构切断 CodeQL clear-text-logging taint flow

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
