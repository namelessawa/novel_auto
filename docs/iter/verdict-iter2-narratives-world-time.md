# iter#2 · agent code · `/api/tick/narratives` 双 contract fix

## Scope

Phase 6-B reader endpoint `/api/tick/narratives` 在 HEAD 状态有两处 contract bug:

1. **AttributeError**: 调 `ts.get_current_tick()` 但 TickState 是 property
   `ts.current_tick` (line 131) — 任何请求触发 500. v2.48 dashboard
   uncommitted 工作已经修了属性名访问 (注释 `v2.48 — current_tick 是
   property 不是方法`), 本刀把该改动从 uncommitted 区里挑出来落定.
2. **world_time 字段遗漏**: docstring 承诺每行返回 `{tick, world_time, text,
   char_count}` 但实现没填 `world_time`. reader UI 因此只能按 tick_id 数字
   显示而非"故事时间". 本刀新加批量 SQL 查询 + 字段填充.

两处都属 ship 时漏修的 contract bug, 没 endpoint test 兜底, 一同 fix.

## 改动

- `backend/persistence/tick_db.py`:
  - 新增 `get_world_time_map(tick_ids: list[int]) -> dict[int, int]`. 单次
    IN-clause SQL 批量取 tick_log world_time, 比 N 次 single-row 查询省
    99% lock 周期. 缺失 tick_ids 不出现在结果 dict (caller 决定 None /
    default). 空输入 short-circuit 返回 `{}`.
- `backend/api/tick_routes.py::list_narratives`:
  - 拿到 narrative rows 后批量查 world_time, fill 到每行. 空 narratives
    short-circuit, 不发空 SQL.
- `backend/tests/test_tick_db_world_time_map.py`: +5 unit (empty / 多 tick /
  缺失 tick_id / 单 tick / 重复输入).
- `backend/tests/test_narratives_endpoint_world_time.py`: +4 integration
  (世界时间填充 / 缺失 tick_log → None / start_end 过滤 / 空目录).

## 验证

```
backend/tests/test_tick_db_world_time_map.py ........ 5/5 PASS
backend/tests/test_narratives_endpoint_world_time.py ........ 4/4 PASS
```

全量 backend tests: **879 PASS** (iter#1 870 + 5 unit + 4 integration =
879, 零回归).

## verdict = PASS

- coverage∆: +9 测试 (5 unit + 4 integration); 锁住 reader endpoint
  contract, 防 v2.48 类 ship 漏 regression
- contract∆: docstring 与 impl 一致 (world_time 实际返回)
- 风险: 1★ — TickDB 加新 method 不动既有路径, list_narratives 改动幂等

Phase 6-B reader API 合约第一道防线就位.

## 不在此刀

- frontend ReaderOverlay 接 world_time 渲染 — uncommitted v2.48 dashboard
  改动, 留下一刀; 或等 v2.48 frontend 整体 commit 之后再做适配
- TickDB row_factory 多线程 access patterns — sqlite3 max-host-param 999
  目前 reader limit 2000 但实际请求 <500, chunking 未发生; 留 carry-forward
  if 后续要支持 1000+ batch read

## Sources

- 错误诊断: `backend/api/tick_routes.py:335` docstring vs
  `backend/api/tick_routes.py:372` impl 不一致
- 接入: `backend/persistence/tick_db.py::get_world_time_map`
- 测试: `backend/tests/test_tick_db_world_time_map.py`,
  `backend/tests/test_narratives_endpoint_world_time.py`
