# Iteration 06 — style validation cost telemetry

- iteration_id: `20260721-06-style-cost-telemetry`
- date: `2026-07-21`
- base_git_sha: `7d2cef49bb4a397f5dc288d7fa66895640561959`
- candidate_git_sha: `5949949a4c04ca32872306cefb6cea7d16d5b06b`
- provider: `custom`
- model: `glm-5.2`
- themes: smoke 由动态注册表选择
- styles: smoke 由 `list_style_keys()` 对应 key 选择
- seeds: 主题注册表 seed
- tick_counts: `1`

## Hypothesis

观察：Iteration 05 的 `validate_styles.py` 只留下总墙钟，未记录生成、anchors、
semantic judge、修订或编辑的 token；无法计算风格改动的真实成本 delta。

根因假设：脚本虽复用已接入 `TokenBudgetTracker` 的 LLMClient，却从未在 benchmark
边界拍快照，也未将 tracker 的 provider usage 写入样本和汇总。

准备修改的最小范围：仅在验证脚本建立独立 tracker，在共享 bootstrap 与每个样本
前后拍不可变快照，输出 prompt/completion/cache/calls/by_agent/墙钟；不修改任何 LLM
调用、Prompt、温度、模型或生产路径。

预期改善的指标：真实 smoke 产物 `samples_with_cost=1`，总量等于各 agent 求和，
bootstrap 与样本成本分离；provider 缺 usage 时显式 `MISSING/PARTIAL`。

可能退化的指标：resume 时旧样本没有成本字段；重复统计共享 bootstrap；全局 tracker
污染测试；Markdown 把未知显示成零。

验证方法：delta/aggregate 单测、相关测试、全后端测试；一个动态注册表风格的真实
1-Tick smoke，并核对 JSON 等式及敏感信息。

回滚条件：改变生成正文/判定逻辑；total 与 agent 汇总不一致；resume 把旧样本伪装成
已测；缺 usage 被报告为零成本；或测试回归。

## Result

- files_changed:
  - `scripts/validate_styles.py`: 独立 tracker、bootstrap/sample 快照、按 agent
    token/调用/缓存/墙钟、覆盖率与缺失 usage 状态、Markdown 汇总
  - `backend/tests/test_validate_styles_script.py`: delta、agent 归因及
    missing-usage fail-closed 回归
- tests_added: `backend/tests/test_validate_styles_script.py`
- baseline_metrics: style validation token coverage `0%`
- candidate_metrics:
  - real smoke: compatible / `apocalypse_wasteland` /
    `rough_grit_realism`, `1/1 PASS`, 1659 chars
  - cost coverage `1/1`; `usage_status=REPORTED`
  - bootstrap: `10,121` tokens, 4 calls, `96.672s`
  - sample: `13,288` tokens, 4 calls, `64.503s`
  - total: `23,409` tokens, 8 calls, measured `161.175s`
  - agent sum equals total in both blocks; `unattributed_tokens=0`
  - `missing_usage_blocks=0`
  - sample agents: style-anchor regeneration `2,175`, Narrator `5,790`,
    State Verifier `3,802`, semantic judge `1,521` tokens
- failure_samples: none in smoke；resume 的历史结果若无 cost 会计入
  `samples_without_cost`，不会伪装为已测
- cost_delta: telemetry-only；未增加 LLM 调用，只有进程内快照与 JSON 字段
- verdict: `ACCEPT`
- rollback_status: `not required`; 生产路径和 Prompt 未修改
- next_recommendation: 所有后续 style baseline/candidate 都使用该字段；优先研究
  State Verifier 高占比，但必须先保留误报/放弃的候选证据，不能直接降低验证强度。

## Evidence artifacts

- `docs/iter/style-cost-telemetry-smoke-glm-20260721.json`
- `docs/iter/style-cost-telemetry-smoke-glm-20260721.md`

provider metadata 只含模型、URL 和凭据是否存在，不含凭据值。

## Verification

```powershell
python -m pytest backend/tests/test_validate_styles_script.py `
  backend/tests/test_token_budget_safety.py `
  backend/tests/test_llm_observability.py -q
python -m pytest backend/tests/ -q
python scripts/validate_styles.py `
  --provider-file coding.txt `
  --mode compatible `
  --styles rough_grit_realism `
  --ticks 1 `
  --max-revisions 0 `
  --out docs/iter/style-cost-telemetry-smoke-glm-20260721.json
```

Gate A：相关 `31 passed`；全量 `1224 passed, 1 warning`。warning 是既有
`StarletteDeprecationWarning`。
