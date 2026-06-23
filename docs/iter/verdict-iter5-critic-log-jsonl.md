# iter#5 · agent code · critic decision JSONL log 持久化

## Scope

NarrativeCritic 的 surviving_triggers / decision_trail / action 此前
只 in-memory (落在 `NarratorOutput.critique_trace`, orchestrator 持有
`_last_narrator_output` 单例). 任何长程分析 / reader UI marker / iter
trial 比较都没有数据基础.

本刀加 `{data_dir}/critic_log.jsonl` 持久化 — 每 tick 1 行 lightweight
record. 500-tick novel 累积 ~100KB, IO 可忽略.

## 改动

- `backend/agents/orchestrator.py`:
  - `import json` 加入
  - 新 module-level helper `_append_critic_log(data_dir, tick, narrator_out)`
    — schema: `{tick, action, surviving_codes, decision_trail,
    new_opening_signature}`. final_text 不持久化 (已在
    `narratives/tick_NNNNNN.txt`). 空 critique_trace 直接 no-op.
  - tick 路径在 `_last_narrator_output = narrator_out` 之后调用 helper, 包
    在 `try/except` (IO 错误不破 tick).
- `backend/tests/test_critic_log.py` (新): **6 测试**
  - empty trace → no-op (jsonl 不创建)
  - 非空 trace → 1 行 + schema 字段齐
  - 多 tick → append 不覆盖, 顺序保留
  - surviving_codes 排序 + 去重
  - invalid trigger entries (非 dict / 缺 code / None) 跳过
  - 中文 evidence + ensure_ascii=False 安全

## 验证

```
backend/tests/test_critic_log.py ........ 6/6 PASS
```

全量 backend tests: **927 PASS** (iter#4 921 + 6 critic_log, 零回归).

## verdict = PASS

- coverage∆: +6 test, critic decision metadata 持久化路径锁定
- 数据基础∆: 每 tick 1 行 jsonl, 长程 500-tick ~100KB 容量
- 风险: 1★ — IO 操作包 try/except 兜底, fail-fast 不破 tick. helper
  抽离便于单测.

后续可建 reader API `/api/tick/critic-log` 把 jsonl stream 给 frontend,
段落级 surviving codes marker 可显示.

## 不在此刀

- Reader API endpoint 暴露 critic_log.jsonl — 留 iter#6+
- frontend 视觉 marker — frontend 仍 uncommitted v2.48 状态
- critic_log 长期 rotation (假设 500-tick 后无 rotate) — 100KB 长期累积
  无问题

## Sources

- 接入: `backend/agents/orchestrator.py::_append_critic_log` (module-level
  helper) + tick path 调用
- 测试: `backend/tests/test_critic_log.py`
- 数据 schema: 与 `NarratorOutput.critique_trace` 字段对齐 (CritiqueOutput.to_dict)
