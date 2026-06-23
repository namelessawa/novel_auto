# iter#7 · agent code · GET /api/tick/critic-log/stats aggregated dashboard

## Scope

接 iter#5/6 critic_log.jsonl 数据基础, 加一个 dashboard-friendly aggregate
endpoint. 长程 500-tick 一目了然的 critic 行为概览, 替代 reader UI 自己
做 client-side groupby.

## 改动

- `backend/api/tick_routes.py`:
  - 新增 `GET /api/tick/critic-log/stats` endpoint:
    - 扫 `{data_dir}/critic_log.jsonl` 全文件 (~10ms / 500-tick / 100KB)
    - 输出 `action_distribution` (ACCEPT/REVISE/REWRITE/RED_TEAM 计数)
    - `top_codes` 触发 code 频次 top-10
    - `ticks_scanned` 实际 tick 数
    - `empty_decision_ticks` clean output tick 数 (surviving=[]).
    - 参数 `start_tick` / `end_tick` 范围过滤
- `backend/tests/test_critic_log_stats.py` (新): **7 测试**
  - empty 文件 → 全零
  - action_distribution 计数
  - top_codes 按频次降序
  - empty_decision_ticks 计数
  - range 过滤
  - top_codes 截断 10
  - malformed safe-skip

## 验证

```
backend/tests/test_critic_log_stats.py ........ 7/7 PASS
```

全量 backend tests: **940 PASS** (iter#6 933 + 7 stats, 零回归).

## verdict = PASS

- coverage∆: +7 test, dashboard aggregation 合约锁定
- 端点∆: `/api/tick/critic-log/stats` — dashboard 直接 consume, 不再
  client-side groupby
- 风险: 1★ — pure reader endpoint, malformed 行 safe-skip

## Phase 6-C reader 数据栈完整 (iter#5/6/7 三件套):

1. **iter#5** orchestrator append critic_log.jsonl (per-tick raw)
2. **iter#6** GET /critic-log raw rows (per-tick text + decision_trail)
3. **iter#7** GET /critic-log/stats aggregated (dashboard summary)

frontend 直接消费 (3) 拿 summary, 想 drill-down 用 (2) 拿 raw rows.

## 不在此刀

- frontend dashboard 视觉 (v2.48 uncommitted)
- 跨 novel 全局 stats (现在 endpoint 是 per-novel 通过 runtime resolve)
- 时间窗口 sliding stats (例: 最近 100 tick 趋势) — 留 carry-forward

## Sources

- iter#5 数据基础: `backend/agents/orchestrator.py::_append_critic_log`
- iter#6 raw endpoint: `backend/api/tick_routes.py::list_critic_log`
- iter#7 stats: `backend/api/tick_routes.py::critic_log_stats`
- 测试: `backend/tests/test_critic_log_stats.py`
