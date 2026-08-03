# Author 权威链加固验收（2026-07-22）

> 历史单节 Author 验证记录，不是当前整书发布 verdict。当前候选只按
> [最终验收](./FINAL_ACCEPTANCE.md) 的全新六阶段 evidence 判定。

## 结论与范围

本轮只收口既有 Author Memory Refactor 的权威漏洞，不扩展 StateGuard 研究、provider、Critic、多 Agent、多媒体或知识图谱。修复后的后端、前端、恢复路径与录制式 smoke 均通过；结果来自本轮重新执行，不复用首次验收中“无高/中风险”的旧结论。

## 权威链

```text
StoryBible
>
CanonicalState
>
最终验证通过的 StateDelta
>
MemoryRepository
>
旧迁移数据 / simulation 候选
```

- 新 author bootstrap 在 LLM 任务入队前逐字保存 seed，并记录 title、theme key、positioning、references、style contract 的来源。
- Author 风格只读取并写入 StoryBible；simulation 的 TickState preset/anchors 不拥有反向写权。
- StateDelta 每项独立检查 evidence、正文定位、路径、目标类型和领域约束，只有最终 `validated_delta` 能改变 CanonicalState。
- Repair 只改正文，修复后重新验证原始结构化提案。
- commit 与 recover 都重新检查 StoryBible revision；旧上下文事务进入 `stale_context`，不会产生正式章节或部分权威写入。
- StoryThread 推进/解决保留来源字段并有限合并；Memory、摘要和知识图谱不覆盖当前事实。

## 基线

- HEAD：`a14aa3755c592975b3d6d2e8dc7d513b9f2ec002`。
- 相对 `main...HEAD`：257 files，193823 insertions，332 deletions；当时分支领先 main 56 commits。
- 关键 author 后端基线：31 passed，1 个既有 Starlette/httpx warning。
- 前端基线：3 个静态 SSR 测试通过；59 modules，CSS 110.86 kB（gzip 19.29），JS 352.25 kB（gzip 105.10）。
- 工作区原有未跟踪 `.tmp/` 和 `scripts/openai_compatible_chat.py`，本轮未读取、修改或暂存它们。

## 最终验证

| 命令 | 实际结果 |
| --- | --- |
| `python -m pytest backend/tests/test_author_context_validator.py -q` | 最终 22 passed；中间与 service/gateway 合跑 36 passed（20+14+2） |
| `python -m pytest backend/tests/test_author_generation_service.py -q` | 14 passed |
| `python -m pytest backend/tests/test_author_runtime_factory.py -q` | 1 passed |
| `python -m pytest backend/tests/test_story_api.py -q` | 6 passed，1 warning |
| `python -m pytest backend/tests/test_story_migration.py -q` | 7 passed |
| `python -m pytest backend/tests/test_simulation_gateway.py -q` | 2 passed |
| `python -m pytest backend/tests/test_bootstrap_routes.py -q` | 15 passed，1 warning |
| `python -m pytest backend/tests/ -q` | 最终 1401 passed，0 failed，0 skipped，1 warning；本轮前为 1374 passed |
| `python -m ruff check backend/story backend/api/story_routes.py backend/api/bootstrap_routes.py backend/bootstrap_prompts.py backend/tick_runtime.py backend/tests scripts/smoke_author_mode_recorded.py` | All checks passed（先机械清理 65 个测试文件的 128 项既有 lint） |
| `python -m compileall -q backend/story backend/api/story_routes.py backend/api/bootstrap_routes.py scripts/smoke_author_mode_recorded.py` | exit 0 |
| `npm run test:author` | 11 passed，0 failed；组件交互和 API mock，不再只有 SSR |
| `npm run build` | 59 modules；CSS 110.86 kB（gzip 19.29），JS 354.68 kB（gzip 105.93） |
| `python scripts/smoke_author_mode_recorded.py` | 十步全部 true；4 正式章节，Bible R3，State R5，5 条 memory，1 次 repair |
| `npm audit --omit=dev` | 0 production vulnerabilities |
| `git diff --check` | 无 whitespace error；Windows `core.autocrlf` 只给出 LF→CRLF 提示 |

唯一 pytest warning 是既有 Starlette `TestClient` / httpx 弃用提示。`npm install` 的完整开发依赖审计仍报告 4 项 advisory（1 low、1 moderate、2 high），但生产依赖审计为 0；未执行可能改变主版本的 `npm audit fix`。

## 录制式 smoke 边界

`scripts/smoke_author_mode_recorded.py` 使用 deterministic Writer 验证以下十步：自定义 seed、逐字保存、首节提交、Bible 改版、旧事务拦截、新事务成功、缺证据 delta、CanonicalState 排除、runtime 重建、原始 Bible 与长期记忆复用。

真实 Provider 调用和 token 都是 0；该证据只证明权威、恢复和上下文组装行为，不证明文学质量。首次验收报告中的真实 provider 数据属于先前运行，不计入本轮调用量。

## 修改文件

### 权威链与产品代码

- `backend/api/bootstrap_routes.py`、`backend/api/story_routes.py`：bootstrap 先存 Bible、风格按模式分流、stale/API 脱敏。
- `backend/story/models.py`、`persistence.py`、`migrations.py`：seed/provenance/style 字段、revision-aware 持久化、legacy 推断隔离。
- `backend/story/validator.py`、`writer.py`、`simulation_gateway.py`：逐项 evidence/路径/类型检查、prose-only repair、simulation 证据提取。
- `backend/story/service.py`、`backend/sections/section_store.py`：commit/recover Bible guard、基线快照和安全回滚。
- `backend/story/context_builder.py`：全局预算、不可变规则拒绝策略和 manifest。
- `frontend/src/dashboard/Shell.jsx`、`modals/NewNovelModal.jsx`、`views/StoryBibleView.jsx`、`views/AuthorStudioView.jsx`、`views/CanonicalStateView.jsx`：精确输入、权威编辑、stale/validator/budget 展示、author Tick 隔离与可注入 API。
- `frontend/tests/author-ui.test.mjs`、`frontend/package.json`、`frontend/package-lock.json`：11 项组件交互测试及轻量 `react-test-renderer` 开发依赖。
- `scripts/smoke_author_mode_recorded.py`：零 Provider 十步验收。

### 主要新增/扩展测试

- `backend/tests/test_author_context_validator.py`
- `backend/tests/test_author_generation_service.py`
- `backend/tests/test_bootstrap_routes.py`
- `backend/tests/test_story_migration.py`

### 文档

- `README.md`、`CHANGELOG.md`
- `docs/author-mode-architecture.md`
- `docs/author-mode-verification-20260722.md`（标记旧报告已被取代）
- `docs/author-mode-authority-hardening-20260722.md`

### 仅机械 lint 清理的测试文件

以下文件只移除未使用 import/变量、重命名歧义局部变量，或为必须位于 `sys.path` 调整后的 import 添加 `noqa: E402`：

`backend/tests/conftest.py`, `test_a1_compound_dedup.py`, `test_add_open_loop_dedup.py`, `test_adjective_runs_v2.py`, `test_analyzer_d4_per_bucket.py`, `test_analyzer_d7_narrate_cascade.py`, `test_analyzer_d8_quota_wall.py`, `test_auth_jwt.py`, `test_auth_rate_limit.py`, `test_bench_script_smoke.py`, `test_bench_tick_theme_args.py`, `test_character_agent_language.py`, `test_character_arc_tracker.py`, `test_character_visibility.py`, `test_create_novel_bootstrap.py`, `test_creativity_scorer.py`, `test_critic_force_above_len.py`, `test_critic_log.py`, `test_critic_log_skipped_rows.py`, `test_event_injector_prompt_contract.py`, `test_fact_ledger.py`, `test_goal_validator.py`, `test_hallucination_diagnostic_api.py`, `test_hallucination_observation.py`, `test_inject_event_validation.py`, `test_json_utils.py`, `test_llm_client_extra_body.py`, `test_llm_config_fallback.py`, `test_llm_observability.py`, `test_memory_compressor_closure.py`, `test_memory_store.py`, `test_multimodal_security.py`, `test_narrator_intensity_guard.py`, `test_open_loop_origin_events.py`, `test_open_loops_admin_api.py`, `test_orchestrator_close_loops.py`, `test_orchestrator_concurrency.py`, `test_orchestrator_p0.py`, `test_orchestrator_p1.py`, `test_orchestrator_state_transitions.py`, `test_parallelism.py`, `test_probe_quota.py`, `test_prose_dynamics.py`, `test_quality_metrics_compliance.py`, `test_quality_metrics_consistency.py`, `test_quality_metrics_judge.py`, `test_quality_metrics_longrange.py`, `test_quality_metrics_repetition.py`, `test_quality_spec.py`, `test_section_closing.py`, `test_section_routes.py`, `test_section_store.py`, `test_sense_diversity.py`, `test_showrunner_loops_to_close.py`, `test_sideline_runtime_cap.py`, `test_state_guard_adjudication.py`, `test_state_quarantine.py`, `test_story_arc_director.py`, `test_text_segmenter.py`, `test_tick_db_insert_ignore.py`, `test_tick_throughput.py`, `test_token_budget_safety.py`, `test_v217_coherency_sweep.py`, `test_working_memory.py`, `test_worldview_dump.py`。

## 已知低风险限制

- deterministic evidence 校验能证明短句可定位、路径/类型/领域约束成立，但不声称能自动判断所有文学层面的因果充分性。
- 当前录制 smoke 不验证真实 provider 的文学质量或配额；真实调用数据只存在于被取代的历史报告。
- 开发依赖仍有 4 项 npm advisory；生产依赖审计为 0。
- Starlette/httpx 测试适配层有 1 个弃用 warning，不影响运行时 API。
