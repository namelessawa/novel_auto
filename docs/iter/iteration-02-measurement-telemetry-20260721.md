# Iteration 02 — long-range measurement telemetry

- iteration_id: `20260721-02-measurement-telemetry`
- date: `2026-07-21`
- base_git_sha: `0d91d575dccceb71e8258cb94b822a6e55a4307c`
- candidate_git_sha: `1df04117e16e625c4a80e9ff5f48ac2fe90ab915`
- provider: `custom`
- model: `glm-5.2`
- themes: `republic_spy,gourmet_culinary,apocalypse_wasteland`
- styles: `literary`
- seeds: project registry seeds
- tick_counts: `3,3,3`

## Hypothesis

观察：三份真实 3-Tick baseline 都被 analyzer 报为 100% critic clean，同时报
MemoryCompressor silent；但 baseline 没有逐 Tick critic 字段，且 3 Tick 不应触发
50-Tick compressor。报告也丢失已有 OpenLoop snapshot 与 Tick Token 增量。

根因假设：`bench_tick.py` 的观测 schema 与 `analyze_longrange_drift.py` 的缺失值
语义不一致；analyzer 把“没有观测”当成“无问题”，并把不完整 bucket 当成完整周期。

准备修改的最小范围：只增加 benchmark 只读字段、暴露最近一次 Guardian 输出，
并让 analyzer 向后兼容地重建累计 Token、读取 OpenLoop snapshots、区分 unknown，
以及仅在到达 50-Tick 边界时检查 per-bucket compressor。

预期改善的指标：D2 不再显示伪 100%；D3/D5/D6 在有数据时可计算；不足
50 Tick 不再误报 D4。正文、Narrator 产出率和 Token 消耗不应改变。

可能退化的指标：benchmark JSON 体积轻微增加；若 Guardian 最近输出没有按扫描
Tick 清空，可能把旧矛盾重复计数。

验证方法：新增 synthetic regression，重跑相关测试，并用三份未修改的真实 baseline
JSON 重新分析；随后运行全部后端测试。无需真实 LLM 才能验证本轮测量修复。

回滚条件：任何 Tick 调度/正文变化；旧 schema 无数据时仍显示健康；不足 50 Tick
仍报 D4；或 Guardian 冲突被跨 Tick 重复计数。

## Result

- files_changed:
  - `backend/agents/orchestrator.py`: 暴露并逐扫描清空最近 Guardian 输出。
  - `scripts/bench_tick.py`: 写入累计 Token、OpenLoop、critic、Narrator skip、
    Guardian 当前/累计冲突字段。
  - `scripts/analyze_longrange_drift.py`: unknown 语义、旧 schema 回填、短 bucket
    D4/D8 保护。
  - `backend/tests/test_analyzer_measurement_coverage.py`: 5 个测量回归。
  - `backend/tests/test_bench_script_smoke.py`: critic/skip 观测契约。
  - `backend/tests/test_tick_throughput.py`: Guardian 输出观测契约。
- tests_added: 7 个新断言/用例；最终全量 `1216 passed, 1 warning`。
- baseline_metrics:
  - 原 analyzer 对三份 3-Tick JSON 均显示 `clean_rate_pct=100.0`、
    `cumulative_tokens_at_end=null`、`open_loop_avg=null`，并误报 D4。
  - 原始真实 tokens：谍战 `15102`，治愈 `8425`，末日 `20950`。
  - 原始 OpenLoop snapshots 平均：谍战 `5.0`，治愈 `4.0`，末日 `5.0`。
- candidate_metrics:
  - 同三份原始 JSON 重分析：累计 Token 全部恢复，OpenLoop 平均全部恢复，
    critic 显示 `null / 0 evaluated`，不足 50 Tick 的 D4/D8 均不再误报。
  - 新 3-Tick GLM candidate 的 9 个观测字段每 Tick 齐全；三个正文空缺被明确
    解释为事件价值 `4/1/1 < 5` 的合法沉默，而非 quota wall 或状态误杀。
- failure_samples:
  - baseline analyzer 把无 critic 字段解释为 100% clean。
  - baseline analyzer 在 3-Tick run 中报告 MemoryCompressor silent。
  - 首版 candidate analyzer 把三个合法低价值快速 Tick 报为 D8 quota wall；已由
    新回归捕获并在同轮修复。
- cost_delta: 生产 LLM 调用数 `+0`；仅 benchmark JSON 每 Tick 增加少量字段。
  candidate 的 `991 tokens` 不与 baseline `15102 tokens` 宣称成本改善，因为本次
  随机事件价值不同且三个 Tick 均合法沉默。
- verdict: `ACCEPT`
- rollback_status: `not required`
- next_recommendation: 用新 telemetry 复验 NarrativeStateGuard 的高价值正文误杀；
  不降低状态安全阈值，先修可复现的因果/多人过门证据假阴性。
