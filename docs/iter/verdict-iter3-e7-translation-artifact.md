# iter#3 · det metric · E7 translation-artifact (Phase 6-C 第四刀)

## Scope

Phase 6-C 第三刀 (iter#1 B4) 后续 slice. E7 是 spec medium severity, 用
mechanical pattern density 检测翻译腔 (英文化句式) — 与 D6/B4 同构 det
wrapper, 同样 healthy 0 触发 + LLM 退化时 catch 的设计意图.

## 改动

- 新增 `quality_metrics/translation_artifact.py` (E7 lite det):
  - 7 个翻译腔 pattern:
    - 对于…来说 / 对…而言 — 英文 "for X" / "to X" 直译
    - 这是一个…的 — "this is a/an ... X" 直译
    - 被…所… — Chinese 非正式 prose 罕用的英式被动
    - 长定语链 — `(X的Y的Z的){3+}` 形式
    - 不仅…而且… — formulaic translation cadence
    - 由于…的原因 — 翻译式 cause marker
  - `e7_translation_artifact_check(text, min_hits=2)` — 总命中数 ≥ 2 才
    触发, 避免 isolated accident (例: 一段 1000 字内偶现 1 次"对于他来说"
    不算翻译腔).
  - `translation_artifact_report(text)` → `TranslationArtifactReport`.
- `backend/agents/quality_checks.py`:
  - 新增 `check_translation_artifact(text)` wrapper (lazy import + env knob
    `TRANSLATION_ARTIFACT_ENABLE` 默认 True), 触发转
    `DeterministicTrigger(E7, medium)`, evidence 前缀
    `[translation_artifact]`.
  - 接入点: `run_deterministic_checks` 末尾, 在 `check_inner_monologue_ratio`
    之后.
- `backend/tests/test_quality_spec.py`: +5 测试 (healthy / heavy / single_hit
  / env kill / 主入口集成).

## 验证

### 单元测试

```
test_check_translation_artifact_healthy_no_trigger PASSED
test_check_translation_artifact_heavy_triggers_e7 PASSED
test_check_translation_artifact_single_hit_no_trigger PASSED
test_check_translation_artifact_env_kill_switch PASSED
test_run_deterministic_checks_includes_e7 PASSED
```

全量 backend tests: **884 PASS** (iter#2 879 → 884, 零回归).

### Offline replay — Phase 6-A.2 500-tick 271 narratives

实跑 `translation_artifact_report` 在 healthy 长程基线上:

| 指标 | 数值 | 解读 |
|---|---:|---|
| narratives ≥ 100 chars | 271 | 校准基线 |
| **E7 触发** | **0 (0.00%)** | healthy bench 不触发, 符合 det 设计意图 ✓ |
| 总 pattern hits | 2 | 跨 271 段仅 2 个孤立 single-hit |
| 单段最大 hits | 1 | 远低于 min_hits=2 触发阈值 |

271 段平均每段 < 0.01 个 pattern hit — 中文长程 prose 几乎不用翻译腔,
det 触发率 0 与 D6 / B4 一致.

cost 增量预期: < 0.1% (E7 触发率 ≈ 0 → critic REVISE 增量可忽略).

## verdict = PASS

- coverage∆: 新加 E7 dim det 路径 (E 维度补完: E1 + E7 都已 det 覆盖)
- token∆: 0 (healthy bench 0 触发)
- test∆: 879 → 884 (+5, 零回归)
- 风险: 1★ — wrapper 接入路径与 E1/D6/B4 同构, env kill switch 完备

Phase 6-C 第四刀 LANDED. det → REVISE 决策路径 B/D/E 三维度均扩展.

## 不在此刀

- E2 对仗 / E3 POV / E4 时态人称 / E5 角色对话风格 / E6 文绉绉 — semantic,
  留 LLM critic
- B/C/D 其他子项 (B1/B2/B5 等) — semantic
- E7 严格 NLP 实现 (依存分析判定翻译腔) — 超出 det 层范围

## Sources

- Phase 6-C 第三刀: iter#1 B4 commit 87b7a49
- spec: `docs/design/novel_quality_critique_and_iteration.md` E7
- 校准基线: `backend/data/users/bench/novels/bench_phase6a2-longrange-500tick_1781696585/narratives/` (271 narratives)
- 接入: `backend/agents/quality_checks.py::check_translation_artifact`
- 测试: `backend/tests/test_quality_spec.py::test_check_translation_artifact_*`
