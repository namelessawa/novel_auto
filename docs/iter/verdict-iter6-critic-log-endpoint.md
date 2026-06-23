# iter#6 · agent code · GET /api/tick/critic-log reader endpoint

## Scope

接 iter#5 critic decision JSONL log 持久化, 加 reader API 把 jsonl stream
给 frontend. Phase 6-B 后续 reader UI 可以从单 endpoint 拿 critic decision
per tick (surviving codes / decision_trail / action).

## 改动

- `backend/api/tick_routes.py`:
  - 加 `import json` 顶部
  - 新增 `GET /api/tick/critic-log` endpoint:
    - 参数: `start_tick` / `end_tick` / `limit` (与 `/narratives` 对齐)
    - 数据源: `{data_dir}/critic_log.jsonl` (iter#5 落定)
    - 行级解析: 逐行 `json.loads`, malformed 行 skip + warn (不 500)
    - 范围过滤 + limit 截断, 与 `/narratives` 端点合约一致
    - `run_in_threadpool` 包同步 IO, 防 event loop 卡
- `backend/tests/test_critic_log_endpoint.py` (新): **6 测试**
  - empty 文件 → 空 rows
  - 多行解析 + 字段保留
  - start_tick / end_tick 过滤
  - limit 截断 + `truncated=true`
  - malformed JSON 行 skip 不 500
  - 中文 evidence + ensure_ascii=False 安全

## 验证

```
backend/tests/test_critic_log_endpoint.py ........ 6/6 PASS
```

全量 backend tests: **933 PASS** (iter#5 927 + 6 endpoint, 零回归).

## verdict = PASS

- coverage∆: +6 test, reader endpoint 合约锁定
- 端点∆: `/api/tick/critic-log` 上线, 与 `/api/tick/narratives` 端点对偶
  (一给文本, 一给决策元数据, 同步 tick 字段对齐)
- 风险: 1★ — 纯 reader 端点 (无副作用), malformed 行 safe-skip + warn

Phase 6-B reader UI 数据基础完整: narratives (text + world_time) +
critic-log (surviving codes + decision_trail).

## 不在此刀

- frontend 视觉 marker (critic decision badge / surviving codes pill)
  — frontend uncommitted v2.48 状态, 留 iter
- aggregated stats endpoint (例: top-N 触发码, action 分布) — 留下个
  slice if 用户需要 dashboard analytics
- critic_log rotation / sharding — 500-tick ~100KB, 长期累积无 IO 问题

## Sources

- iter#5 数据基础: `backend/agents/orchestrator.py::_append_critic_log`,
  `docs/iter/verdict-iter5-critic-log-jsonl.md`
- 端点: `backend/api/tick_routes.py::list_critic_log`
- 测试: `backend/tests/test_critic_log_endpoint.py`
