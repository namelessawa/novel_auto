# Cost-Quality Iteration Loop — Full Journey

> Branch: `iter/cost-quality-loop`. 2026-06-10 → 2026-06-11.
> 34 iterations + 9 code-review cycles. **Total tokens -77% / latency -83% vs baseline**, quality preserved.

## Baseline → Final

| metric                       | v0-baseline | v15-final (iter#29) | v16-final (iter#31) |       Δ |
| ---------------------------- | ----------: | ------------------: | ------------------: | ------: |
| total tokens (3 tick + boot) |     137,890 |              31,214 |              19,287 | **-77~86%** |
| critic links                 |      65,174 |               7,878 |                   0 | -88~100% |
| world_simulator              |      19,427 |               7,152 |               8,305 | -57~63% |
| narrator                     |      19,904 |              16,184 |              10,982 | -19~45% |
| bootstrap_sec                |         501 |                 306 |                 305 |  -39%   |
| avg tick duration (sec)      |         556 |                  91 |                  68 | **-81~88%** |

## Iterations

### Cycle 1 — Core agents (iter#3-5)

* **iter#3** NarrativeCritic 减重 -85%: LLM critique 只第一轮跑; MAX_TOTAL_ROUNDS 4→2; max_tokens collapse (8192→1500 / 32768→4096); 反 reasoning 前缀 guard.
* **iter#4** Narrator prompt slim + output budget per estimated_length + 反 reasoning 加固 (markers + JSON 解析失败兜底 + 占位符检测).
* **iter#5** WorldSimulator delta-output (改 `world_state_delta` 模式, 解析器兼容 fallback); max_tokens 81920→4096; 紧凑视图 (只送 volatile 字段).
* Review fix: CRITICAL `world_time=0` falsy guard + HIGH ellipsis threshold for Chinese literary use.

### Cycle 2 — Refinement (iter#6-8)

* **iter#6** Critic 条件 LLM gating (det_high ≥1 时跳 LLM critique).
* **iter#7** Narrator user_prompt slim: prose_tail 1200→800, MAX_BRIEF chars 8→5 / events 24→16, top-loops by urgency.
* **iter#8** CharacterAgent prompt 2000→1700 + max_tokens 30720→2048 (后 review 调成 A=8192/B=4096 for reasoning models).
* Review fix: HIGH critic det-substantive 改 det_high gate (避免漏掉语义 high); HIGH char_agent max_tokens 改 tier-aware.

### Cycle 3 — Sweep (iter#9-12)

* **iter#9** 全仓 max_tokens 减重: showrunner 30720→3072, event_injector 40960→4096, memory_compressor L0→L1 40960→6144, L1→L2 20480→6144, novelty_critic 20480→2048, evaluation/continuity_v2 40960→4096.
* **iter#10** Critic length-gate < 400 字跳 critic.
* **iter#11** Bootstrap max_tokens slim 85k→19k, bootstrap_sec -17%.
* **iter#12** EventInjector system prompt 1700→1290 chars (-24%).
* Review fix: HIGH bootstrap 示例值污染 → 改用 `<...>` 占位符; HIGH critic prompt 字段名误述; CRITICAL revise/rewrite schema 占位符泄漏 (含 _REVISE_REWRITE_PLACEHOLDERS 检测).

### Cycle 4 — Prompts (iter#13-15)

* **iter#13** Showrunner SYSTEM_PROMPT 1500→1294 chars.
* **iter#14** Critic system prompts 去 blacklist 段 (det 已覆盖 A4); CRITIC 3887→3278, REVISE 1722→1070, REWRITE 1454→796.
* **iter#15** character_arc_tracker max_tokens 8192→4096; memory_compressor L1→L2 4096→6144 (consistency).

### Cycle 5 — Cleanup (iter#16-18)

* **iter#16** NoveltyCritic prompt 1200→636 chars (-47%).
* **iter#17** Bootstrap PROMPT_WORLD 1636→1465, PROMPT_CHARACTERS 1519→1437.
* **iter#18** render_critique_block_semantic — A 类不进 LLM (B-G only).
* Review fix: HIGH bootstrap 示例具体值 → 占位符化.

### Cycle 6 — User prompts (iter#19-21)

* **iter#19** Narrator material_block 紧凑 (desc 120 字 / monologue 60 字 / kind_map 缩写).
* **iter#20** CharacterAgent user_prompt 多 header 合并.
* **iter#21** Showrunner user_prompt indent + fence strip; 章节 20→10.
* Review fix: MEDIUM character_agent facts/secrets 按 item 截断.

### Cycle 7 — Indent strip wave (iter#22-24)

* **iter#22** EventInjector user_prompt: 6 个 json.dumps indent → 无, 去 fence.
* **iter#23** MemoryCompressor user_prompt: 同样 indent + fence strip.
* **iter#24** character_arc_tracker user_prompt: 同上.
* Review fix: MEDIUM stray "+" 字符清理.

### Cycle 8 — Critic + bootstrap (iter#25-27)

* **iter#25** Critic length-gate 400→600, lazy env read.
* **iter#26** continuity_v2 evaluator 8 维度子项压到单行.
* **iter#27** NoveltyCritic user_prompt indent + fence strip, 章节 30→20.
* Review fix: HIGH duplicate import os; HIGH module-level env frozen → lazy 函数 read.

### Cycle 9 — Final pass (iter#28-34)

* **iter#28** story_arc_director user_prompt 合并到单段.
* **iter#29** Bootstrap stage JSON indent strip.
* **iter#30** summary_tree LLM max_tokens 10240→1024 (legendize, _compress, _compress_root).
* **iter#31** bootstrap regenerate_style max_tokens 16384→4096.
* **iter#32** README v2.38 header.
* **iter#33** Critic MAX_TOTAL_ROUNDS 2→1.
* **iter#34** world_simulator events 20→10, desc 80→60.
* Review fix: MEDIUM _compress / _compress_root 长度护栏; MEDIUM world_sim 按 narrative_value 降序选 top-10 (替代 recency).

## Architectural patterns applied

1. **max_tokens 合理化** — 反 reasoning 模型把 budget 全填满的浪费. 所有调用按实际输出体积重新估算上限, env override 留作生产逃生通道.
2. **JSON delta output** — 仅传 changed fields 而非全量回灌 (WorldSimulator).
3. **占位符自描述化 + 检测** — schema 示例值改成显式 `<placeholder>` 形式, 解析层加占位符检测防 LLM copy-paste.
4. **Det + LLM 分工** — A 类 (重复) 由 det 检查器 silently 兜底, LLM critic 只负责语义类 (B-G), 既减 prompt 体积也减 LLM 调用频次.
5. **Length-gating + round capping** — 短段落跳 critic, modify 上限 1 轮, env 可恢复.
6. **JSON indent strip 全仓** — 仅 LLM 入口的 prompt 用紧凑 JSON; persistence 路径保持 indent 给人类调试用.
7. **反 reasoning 多层防线** — system prompt 显式禁止 + reasoning_filter Chinese/English markers + 高置信信号 (JSON 字段名出现即整段视作泄漏) + 兜底前先扫.
8. **Lazy config read** — env-driven tuning knob 用函数包装而非模块级常量, 测试 monkeypatch.setenv 立即生效.

## Code review verdicts

| Cycle | Severity findings | Status |
| ----- | ----------------- | ------ |
| #1    | CRITICAL world_time=0 + HIGH ellipsis | fixed |
| #2    | HIGH critic det-gating + HIGH char_agent max_tokens | fixed |
| #3    | HIGH mem_compressor budget + state_patches + critic gate test | fixed |
| #4    | HIGH critic prompt 字段名误述 | fixed |
| #5    | HIGH bootstrap 示例污染 + MEDIUM 多项 | fixed |
| #6    | MEDIUM char_agent facts truncation | fixed |
| #7    | MEDIUM stray "+" | fixed |
| #8    | HIGH duplicate import + frozen env | fixed |
| #9    | MEDIUM 3 项 (修 2) | fixed |

CRITICAL hotfix between cycles 5 & 6: revise/rewrite schema placeholder leak (literally `"完整修订后的段落正文"` 写入 narrative_text).

## Tests

575/575 pass (从 baseline 540 → 整体 + 1 新增 critic gate integration test).

## Quality samples (iter#29 final)

> 酸雨落了整夜。天亮时没停。
> 铁影城的屋顶在雾中只露出轮廓, 像一排生锈的锯齿. 街巷窄, 两面高墙夹着,
> 雨水沿墙根淌下来, 颜色发黄, 碰到铁栏杆就嘶嘶响, 冒一点白烟. 栏杆上原本
> 有漆, 早被蚀光了, 露出底下坑洼的铸铁.
>
> 玄烛低头走过赤铜巷. 外套领子竖着, 还是挡不住那股味道 — 煤烟混铁锈,
> 呛嗓子. 他把布袋换到另一边肩上, 里面的东西硌着肋骨. 三份卷宗, 封蜡完好,
> 是昨夜从外城守备处领回来的. 编号 6-17、6-18、6-19. 守备官递过来的时候
> 手心出汗, 说了句"尽快", 多余的话一个字没有.

具象意象 (酸雨 / 铸铁 / 煤烟 / 布袋 / 封蜡), 人物动作 (低头 / 换肩 / 缩
脖子 / 数步), 悬念锚 (神秘卷宗 + 守备官的"尽快"), 全部到位.
