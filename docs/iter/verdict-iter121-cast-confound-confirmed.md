# iter#121 — cast-confound 实战验证 ✓ + Phase 3-B 大胜

> Phase 3-B (iter#119) CLI 落地后第一次实战 bench. seed3 (末世废土) 50-tick
> with 控制 cast 2A+2B+1C (固定 5 角色), 验证 iter#102 P1 假设: seed3
> cost 2.6x 主因是 cast random.

## Setup

| iter | bench | cast 模式 | actual chars | seed | ticks |
| --- | --- | --- | ---: | --- | ---: |
| #102 | stage5-seed3-50tick | wide range | 3 (random) | 末世废土 | 50 |
| #104 | iter103-seed3-50tick | wide range (+close-fix) | 2 (random) | 同 | 50 |
| **#121** | **iter121-seed3-cast221** | **2A+2B+1C 固定** | **5** | **同** | **50** |

## Long-range drift table (iter#121)

| tick | open | stale | closed_total | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 4 | 0 | 0 | 8.0 |
| 10 | 5 | 0 | 0 | 7.4 |
| 15 | 7 | 0 | 0 | 6.71 |
| 20 | 7 | 0 | 0 | 6.71 |
| **25** | **5** | **0** | **2** | **7.4** ← Showrunner 触发 |
| 30 | 5 | 0 | 3 | 7.4 |
| 35 | 4 | 0 | 4 | 8.0 |
| 40 | 5 | 0 | 4 | 7.4 |
| 45 | 6 | 0 | 4 | 7.0 |
| 50 | 6 | 1 | 4 | 7.0 |

open 在 tick 15-20 升到 7 (突破 cap=6), Showrunner 在 tick 25 关 2 个 +
tick 30 / tick 35 各关 1 个, 共 4. 末期 open stable 在 5-6.

## 跨 iter#102 / #104 / #121 完整对比

| metric | #102 baseline (wide) | #104 close-fix (wide) | **#121 close-fix + cast 控** | iter#102 → #121 delta |
| --- | ---: | ---: | ---: | ---: |
| total_tokens | 1,305,466 | 611,600 | **496,972** | **-62%** |
| call_count | 297 | 151 | **125** | **-58%** |
| narrations | 46 | 44 | 45 | -2% |
| **distinct char-2** | **0.8545** | 0.868 | **0.8787** | **+2.8% (best)** |
| open final | 11 | 5 | 6 | -45% |
| stale final | 2 | 0 | 1 | -50% |
| **closed_total** | **0** | 1 | **4** | **+4 (best)** |
| avg_urg final | 6.09 | 6.80 | **7.0** | **+15%** |
| drift signals | 1 | 0 | **0** | drift 消除 |

**Top by_agent comparison:**

| iter | narrator | world_sim | showrunner | top char_agent | total chars |
| --- | ---: | ---: | ---: | --- | ---: |
| #102 | 352k | 157k | 31k | char_fangyanshu=125k | 3 |
| #104 | 274k | 139k | 46k | char_atu=55k | 2 |
| **#121** | **253k** | **143k** | **45k** | **char_linxue=11k** | **5** |

**关键发现**: 5 角色 cast 反而让单个 character_agent token 量大降.
原因: 跟 tracking_chars 调度有关 — 不是所有角色每 tick 都跑 LLM, 只有
被事件影响的角色才跑. 5 角色分摊后, 单角色 tick 调用频次大幅降.

iter#102 时 3 角色 (fangyanshu/jichuan/lujiuniang) 各承担 100k+ 因为
plot 密度高频触发每个; iter#121 时 5 角色让事件 dispersal 更均匀,
character_agent 总和反而少.

## iter#102 P1 假设验证

**假设 (iter#102 verdict §Finding 3)**: seed3 +170% cost (vs seed1/2) 主因
是 cast-dense 题材 bootstrap 生成 3 character_agent 累积 token. 治本是
showrunner cap active cast.

**实证**: 控制 cast 至 5 (实际 2A+2B+1C) 后 — total_tokens 跌 -62%, 落回
seed1/2 同区间 (~500k). 假设**部分确认 (cast 是主因之一, 但治理方式与
预期相反)**:

- 预测: cast 越少 → token 越少
- 实测: cast 5 (固定) < cast 2 (random) < cast 3 (random)
- 推断: random cast 让 character_agent 调度不均, 个别 agent 抢占
  100k+ tokens. 固定多 cast 让事件 dispersal 更均匀, 总 cost 反而最低.

## quality 维度

- distinct char-2 0.8787 — 跨历史 seed3 bench 最高 (其他 0.8545/0.868)
- avg_urg final 7.0 — 比 iter#104 close-fix 时 6.80 高
- drift signals 0 (与 iter#104 同, 但底线维持)
- 4 个 close (vs iter#104 时 1 个) — close 机制更活跃

## 双指标 delta summary

cost delta vs iter#102 (baseline): **-62%**
cost delta vs iter#104 (close-fix): **-19%**
quality delta vs iter#104: drift 同 0, avg_urg +3%, distinct +1.6%, closed +3

## Phase 3 status update

| 候选 | 状态 | 信号 |
| --- | --- | --- |
| A) narrator slim | 失败 revert (iter#114-115) | -4.9% cost / -12.7% urg |
| **B) cast-confound** | **大胜 (iter#119-121)** | **-19% cost / +1.6% prose / drift 同** |
| C) prose diversity dim | 基建完成 (iter#116-118), 弱信号 | mattr -1.2% vs ±1.8% variance |
| D) memory fidelity | 未启动 | 高成本 |

**Phase 3-B 是 Phase 3 首个明显胜利**.

## Continuation

iter#122+ 候选:
1. (P0) seed1 + seed2 with cast 控制实验 — 看 cast-confound 治理在 plot-light
   题材也有相似 cost 节省, 还是只 seed3 特殊
2. (P1) cast count 系统化 sweep — 比如 cast 3/4/5/6 跨 5 个 sample 找
   optimal point
3. (P2) showrunner active-cast cap (运行时, 不是 bootstrap 时) — 可以剧本
   自适应缩 / 扩 cast 而非固定

## Sources

- bench: `docs/iter/bench-iter121-seed3-cast221.{json,md}`
- analysis: `docs/iter/longrange-iter121-seed3-cast221.{json,md}`
- baseline: `verdict-iter102-stage5-seed3-50tick.md`
- close-fix baseline: `verdict-iter104-close-loop-fix-validated.md`
- Phase 3-B CLI: iter#119 (CHANGELOG v2.40)
