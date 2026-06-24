# Phase 6-A · 500-tick stress · verdict

> 2026-06-24 23:15. seed1 = steampunk_archive, style=literary, cast221.
> Branch HEAD: 44b6cca (analyzer FP fix). Bench artifact:
> `docs/iter/bench-phase6a-500tick-seed1.{json,md}`.

## Headline · **CONDITIONAL PASS / 长程 quota 受限**

| 指标 | 值 |
| --- | ---: |
| 完成 tick | 500 / 500 (机械计数) |
| **有效 tick** (LLM 真跑) | **334 / 500 (67%)** |
| Bench 总时长 | 5h 37min (17:38 → 23:15) |
| 有效时长 (前 334) | 5h 31min (19,878s) |
| 总 tokens | 4,448,383 (~4.45M) — 低于 runbook 估算 5M |
| 总 LLM call | 1,085 |
| narratives 写盘 | 222 (前 334 tick 内, 实际 tick 1-334 全覆盖) |

## 终止原因 · DeepSeek 5h 配额触顶

23:14:54 起 LLM 调用全部 `AccountQuotaExceeded` / `AccountRateLimitExceeded`:
```
You have exceeded the 5-hour usage quota.
It will reset at 2026-06-25 01:53:31 +0800 CST.
```

Bench 没崩 — orchestrator 把 429 当 LLM no-op 吞掉, 后 166 tick 仍走完 7 阶段
循环但每 tick 0.7s (vs 健康 25-60s), 显示**配额耗尽下系统优雅降级**, 这是一个
正向信号.

## 6 维 drift 信号

| code | bucket | 测量 | 状态 |
| --- | --- | --- | --- |
| D1 avg_dur drift | t1-50 baseline 25.0s | — | baseline |
| D1 | t51-100 27.5s | 1.10× | ✓ healthy |
| D1 | t101-150 24.5s | 0.98× | ✓ healthy |
| D1 | t151-200 27.8s | 1.11× | ✓ healthy |
| D1 | **t201-250 105.1s** | **4.20×** | ❌ slow drift |
| D1 | **t251-300 118.5s** | **4.74×** | ❌ slow drift |
| D1 | **t301-350 70.8s (含 quota 边界)** | 2.83× | ❌ slow drift |
| D1 | t351-500 0.2s | (quota-exhausted, 非真信号) | — |
| D2 clean_rate drop | 全程 100% (per_tick 没记 surviving_codes) | — | 数据不可读 |
| D3 open_loop cap | 全程 null (per_tick 没记) | — | 数据不可读 |
| D4 memcompress | by_agent_cum L0→L1 触发 | ✓ healthy | |
| D5 contradictions | 全程 null | — | 数据不可读 |
| D6 token cascade | 50-bucket 间增长非超线性 | ✓ healthy | |

## 真实问题分析 · 为什么 t201+ 慢了 4×

抽样 narrative 数据:

| bucket | narrate 率 | avg_dur | 备注 |
| --- | ---: | ---: | --- |
| t1-200 | 22/50 = 44% | 25-28s | 正常 (Narrator silent_bias 触发) |
| **t201-250** | **50/50 = 100%** | 105s | 每 tick 都叙述 + 4× 慢速 |
| **t251-300** | **50/50 = 100%** | 118s | 同上, 进一步累积 |
| t301-334 | 34/34 = 100% | ~71s | 同上 (然后 quota) |

**核心发现**: t201 起 Narrator silent_bias 失效, **每 tick 全产 narrative**.
combined effect (100% narrate × 长 context × CharacterAgent goal validation 重试)
=> 4-5× per-tick 慢速 + 配额加速燃烧.

可能驱动:
1. seed scenario 在 t200 触发 climax sequence, 每 tick narrative_value ≥ 5 阈值
2. open_loops 累计 ≥ cap → EventInjector 原则 #6 优先关旧 → 每关旧 loop 产生
   "高价值" event → Narrator 觉得每 tick 都该写
3. CharacterAgent goal JSON 严格 schema (Goal.id=str / priority≤10 / progress≤1)
   被 LLM 不停违反 (id=int, priority='critical', progress='0%') → LLM 重试
   增加延迟 (但不 fatal, agent 仅 skip)

## 6-A 结论

| 维度 | 结论 |
| --- | --- |
| 长程稳定性 | **PARTIAL** — 前 200 tick 稳定, 200+ 出现 narrate 失控 |
| Memory pipeline | **HEALTHY** — memory_compressor:l0_l1 全程触发 |
| 优雅降级 | **HEALTHY** — quota 触顶后无 crash, 仅 LLM no-op |
| Token 效率 | **GOOD** — 4.45M / 334 effective tick = 13.3k tokens/tick avg |
| Cost 估算精度 | runbook 5M 估算偏高, 实测前 334 tick = 4.45M, 完整 500 tick 估算 6.7M |

## 6-B carry-forward · 真实问题

1. **t200+ narrate-rate 失控 → 长程 cost 主要风险**:
   * 这才是 Phase 6-A 真正抓到的 drift, 比"慢速本身"更深的原因.
   * 需要 narrator silent-bias 长程退化机制 (随累计 narratives 数 / climax 段过去
     后, bias 应回升).
   * 可能 fix: `narrator_silent_bias` 在连续 ≥10 tick all-narrate 后强制 +0.2.
2. **CharacterAgent Goal schema 过严**:
   * LLM 频繁出 priority='critical' / progress='0%' 等, 全程 skip 浪费 token.
   * 应在 Goal schema 加 validator 强转: 'critical'→10, 'high'→8, '0%'→0.0.
3. **DeepSeek 5-hour 配额作为 hard ceiling**:
   * 单 seed 500 tick 跑不完 1 个配额周期内. 长程 bench 需:
     - 升 plan (推荐), 或
     - cross-quota-window 续跑 (bench_tick 已支持 checkpoint, 但 mid-run resume 没做)
     - 改 provider (deepseek → mimo / ark, 看看配额拓扑)

## 不在此刀

- t200 narrate 失控的根因深挖 (开 narrative_critic_log 看 critic 是否每 tick 都 ACCEPT)
- Goal schema validator 改 (留 iter#J)
- 跨 quota window resume 支持 (留 iter#K)
- 跨 seed 复现 (留 6-B, 单 seed → 3-seed 升级)

## Sources

- Bench JSON: `docs/iter/bench-phase6a-500tick-seed1.json` (~540 KB)
- Bench MD: `docs/iter/bench-phase6a-500tick-seed1.md`
- Drift analyzer: `scripts/analyze_longrange_drift.py`
- Process log: `tasks/byk47udnj.output` (429 lines, 17:38→23:15)
- 分析 commit: 44b6cca (D4 FP fix)
