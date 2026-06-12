# iter#115 — Phase 3-A narrator slim 反向结果 + revert

> Phase 3-A 第一次实证 bench: narrator user_prompt summaries [-5:] →
> [-3:] (iter#114) 在 seed2 50-tick 跑出反向结果. revert.

## bench 对比 (相同 seed2, 唯一差别 = summaries 截窗)

| metric | iter#107 baseline (5 summaries) | iter#115 slim (3 summaries) | delta | 方向 |
| --- | ---: | ---: | ---: | --- |
| total_tokens | 527,769 | 553,809 | +4.9% | ❌ 反向 |
| call_count | 130 | 140 | +7.7% | ❌ 反向 |
| narrations | 45 | 40 | -11% | ❌ 反向 |
| distinct char-2 | 0.8974 | 0.9026 | +0.6% | ➖ 噪声 |
| distinct char-3 | 0.9772 | 0.9538 | -2.4% | ❌ 退化 |
| distinct char-4 | 0.9949 | 0.9701 | -2.5% | ❌ 退化 |
| overlap consec char-3 | 0.0266 | 0.0499 | **+88%** | ❌ 严重退化 |
| overlap consec char-4 | 0.0108 | 0.0352 | **+226%** | ❌ 严重退化 |
| open final | 4 | 3 | -25% | ➖ |
| closed_total | 2 | 4 | +100% | ✓ (但代价大) |
| avg_urg final | 7.25 | 6.33 | -12.7% | ❌ 退化 |
| drift signals | 0 | 0 | 0 | ✓ |

## 解读 — 为什么截短 summaries 反而 cost 上涨 + quality 下降

预期: 砍 2 行 summary → -150 tokens/tick → -7500 跨 50 tick → -1.5%.
实际: cost +4.9% (~+26k tokens), quality 多维下降.

**Hypothesis (待验证)**: summaries 提供 "前情张力 anchor" — narrator 知道前
几章在追什么 plot thread. 砍到 3 行后 LLM 失去远期上下文, 表现:
- 自我重复 increased (overlap consec char-4 +226%): narrator 重新引入
  themes 因为忘了已写过. 重复 prose = 更多 wasted token.
- avg_urg 下跌 (7.25 → 6.33): narrator 选 loop 时不知道整体 plot 强度,
  挑了 lower-urg loop.
- close 机制更活跃 (+100%): Showrunner 看 open pool 健康度时, 没有 summary
  历史参照, 默认更激进 close → 但实际伤了 narrative.
- narrations -11%: narrator 多次决定 skip narrate (无足够上下文判断价值).
- tokens +4.9%: 上面所有 quality 退化的 LLM 反应 (multi-round critic
  + character_agent 补救) 净增 cost.

## Conclusion

prose_tail + summaries 是 **不同抽象层**, 非 simple redundant:
- prose_tail (~1600 chars): 续写连贯锚 (语气 / 当前句子风格)
- summaries[-5:]: 前情张力锚 (plot trail / urgency context)

两者作用不能互替. iter#114 的简化假设错误.

## Revert action

- `backend/agents/narrator_agent.py`: `[-3:]` → `[-5:]` (回到 iter#113 状态)
- 保留 comment 标记教训: "prose_tail 与 summaries 并非简单 redundant"

## Phase 3-A 后续教训

* 候选 A 的 user_prompt 体积减少不是单纯字数游戏, **每个字段承载独立功能**.
  下一次尝试需要先 mock 量化每字段的边际贡献 (例如 ablation study), 不能
  靠 intuition.
* 真正能省 narrator token 的方向更可能在:
  - SYSTEM_PROMPT (一次性 + 服务端 prompt cache 友好)
  - 输出 max_tokens 收紧 (LLM 输出量 cap)
  - 而非 user_prompt 内容 trimming

## 测试

由于 conda 环境 pytest install 损坏 (无关 iter#114, site-packages 含 `.c~`
临时文件), 本 revert 暂未本地复跑全套. revert 是回到 iter#113 707/707
PASS 的精确状态 (单行 [-3:] → [-5:]), 不引入新代码路径.

## Sources

- baseline: `bench-iter103-seed2-50tick.{json,md}` (iter#107)
- slim run: `bench-iter114-seed2-narrator-slim.{json,md}` (iter#115)
- longrange: `longrange-iter114-seed2-narrator-slim.{json,md}`
- Phase 3 plan: `PHASE3_PLAN.md`
