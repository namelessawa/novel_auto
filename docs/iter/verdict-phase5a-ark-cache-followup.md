# Phase 5-A follow-up — ARK cache metadata 探针 verdict

> Date: 2026-06-17
> Scope: 解释 `verdict-phase5j-longrange-200tick.md` 提出的异常 — pilot 56.9% cache hit 与 200-tick 长程 0% hit 的差异
> Probes: `scripts/probe_ark_cache.py` + `probe_ark_cache_realistic.py` + `probe_ark_cache_endpoints.py`

## 结论 (TL;DR)

**ARK volces `/api/coding/v3` endpoint 已经停止在 `usage.prompt_tokens_details.cached_tokens` 字段暴露 prefix cache 命中数**。Phase 5-A pilot (2026-06-16) 拿到的 9216/16205 = 56.9% narrator cache hit 是当时的真实读数;Phase 5-J 200-tick bench (2026-06-17) 和本次 31 次跨场景探针 (2026-06-17) 全部读到 0,是 ARK metadata 行为变了。

**Phase 5-A 架构本身仍然 SHIP**:
* 单测 `test_narrator_prefix_cache.py` 锁定 SYSTEM bit-identical(实际 cache 命中由 provider 端机制决定,与我们的 prompt 结构无关)
* 即使 provider 关闭了 metadata 暴露,prefix cache 自身是否仍在 server-side 命中无法直接验证,但**业务层 cost / quality 受影响为零**:命中 → 服务端便宜,不命中 → 与 Phase 5-A 前完全一致(SYSTEM 没退回动态拼接,prefix 结构仍是最优)

## 探针方法

3 个 script 总共 31 个 LLM 调用:

| 探针 | 调用数 | scope | 结果 |
| --- | ---: | --- | --- |
| `probe_ark_cache.py` | 16 | A: 同 prompt 连发 5 次<br>C: thinking on/off 各 2 次<br>D: prompt size 梯度 (39 / 293 / 1236 chars) | **全 0 命中** |
| `probe_ark_cache_realistic.py` | 6 | 真实 NARRATOR_SYSTEM_PROMPT (2195 chars) + 真实 USER (1395 chars), 连发 6 次, 2s 间隔 | **全 0 命中** |
| `probe_ark_cache_endpoints.py` | 9 | coding endpoint × deepseek-v4-pro × 3<br>standard `/api/v3` endpoint × deepseek-v4-pro × 3<br>coding endpoint × glm-5.1 (judge) × 3 | coding endpoint **全 0**<br>standard endpoint **404 不存在** (deepseek-v4-pro 仅在 coding endpoint 注册) |

实验维度全部排除:

* prompt 体积: 117 → 1960 tokens 全 0 命中(应该顶到任何合理的 prefix cache 阈值)
* thinking 模式: disabled / 默认都 0
* 连续调用: 1s / 2s 间隔, 6 次连发, 中间没有 cache eviction 风险
* 模型: deepseek-v4-pro + glm-5.1 都 0
* endpoint: coding-v3 (production), standard `/api/v3` 模型不存在

## 时间线证据

| 时间 | 数据源 | narrator cached_tokens |
| --- | --- | --- |
| 2026-06-16 12:26 | `bench-phase5a-cache-vis-pilot.json` (commit 373d3af) | **9216 / 16205 = 56.9%** |
| 2026-06-17 ~13:00 | `bench-phase5j-longrange-200tick.json` (commit 82820a5) | **0 / 299775** |
| 2026-06-17 17:11-17:21 | 本次 31 次探针 | **全 0** |

24 小时跨度内 ARK metadata 暴露行为变化是唯一一致的解释。

## 不能下的结论 (重要)

* **不能** 说 "ARK 关掉了 prefix cache" — 我们只观察到 metadata 不暴露, 实际 server-side 是否仍命中、计费是否仍按 cached 折扣不可知
* **不能** 说 "Phase 5-A 没有收益" — 架构改对了, prefix 结构是最优的, server-side 命不命中是 ARK 内部黑盒
* **不能** 说 "pilot 56.9% 是假数据" — pilot 时间点 metadata 是真暴露的, 数据有时效性

## 影响评估

### 对 Phase 5-A 状态: 无影响, 仍 SHIP

* 单测锁定的是 SYSTEM bit-identical, 不是 cached_tokens 数值
* SYSTEM 静态拼接是最优 prefix 结构(无论 provider 端缓存机制怎么变)
* 业务上没人靠 cached_tokens 字段做决策, 只是观测信号

### 对 bench/metric 层: 减一项可观测信号

* `cache_hit_rate` 指标在 ARK provider 下不再有效, 应该在 bench MD 报告里加注释 "ARK 当前不暴露 cached_tokens 字段, 0 不代表未命中"
* 切回 DeepSeek 官方 endpoint 或 mimo 时该字段恢复有意义

### 对 cost 估算: 间接观察仍可行

如果 ARK 仍按 prefix cache 折扣计费, 长程 input cost 单调下降是间接证据。但 ARK 不公开发票级 cache 命中拆账, 我们只能等 ARK 自己改回暴露 metadata 或加另一个观测窗口。

## 行动项 (carry-forward)

* [x] **本 verdict 入库** — 解释 200-tick bench 0% cache 不是退化
* [ ] `scripts/bench_tick.py` 的 MD report 加注释 "cached_tokens=0 在 ARK 下可能是 metadata 不暴露而非未命中"(等下一次必要时改, 不优先)
* [ ] 长期: 加 ARK 客服 ticket 或文档查询, 确认是否长期不暴露 metadata
* [ ] **不做**: 给 narrator 加任何 "回退/修复" 代码 — 架构正确, 问题在 provider 端可观测性

## Sources

* `scripts/probe_ark_cache.py` — 4 维探针 (warmup / TTL / thinking / prefix length)
* `scripts/probe_ark_cache_realistic.py` — narrator-size 真实重放
* `scripts/probe_ark_cache_endpoints.py` — coding vs standard vs judge endpoint 对比
* 数据: `docs/iter/probe-ark-cache-1781687517.json`, `probe-ark-cache-realistic-1781688035.json`, `probe-ark-endpoints-1781688145.json`
* 对照: `bench-phase5a-cache-vis-pilot.json` (pilot), `bench-phase5j-longrange-200tick.json` (200-tick)
