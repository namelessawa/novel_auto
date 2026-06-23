# iter#1 · det metric · B4 inner-monologue ratio (Phase 6-C 第三刀)

## Scope

Phase 6-C 第二刀 (verdict-phase6c-prose-integrated.md) 在结尾点名 "B (角色失真)
— 内心独白 vs 行动比 (B4)" 作为后续 det slice 首项. 本刀落地.

## 改动

- 新增 `quality_metrics/character_signal.py` (B4 lite det):
  - `count_dialogue_chars(text)` — 中文/直引/「」三类引号内 CJK 字符数
  - `count_inner_monologue_chars(text)` — 含 19 个显式 marker (心想/暗忖/想道/
    意识到/脑海中/回忆起/...) 的句子的 CJK 字符数; 引号内 marker 视为对白不计
  - `b4_inner_monologue_check(text)` — 三层 guard:
    1. inner_chars ≥ 60 (绝对下限, 避免短段噪声)
    2. inner/cjk ≥ 0.40 (相对下限, 避免单句独白误报)
    3. inner > dialogue × 1.5 (spec 比例); dialogue==0 时 fallback 比对
       非 inner 字符 (remainder==0 全独白极端情况直接 trigger)
  - `character_signal_report(text)` → `CharacterSignalReport` 数据契约
- `backend/agents/quality_checks.py`:
  - 新增 `check_inner_monologue_ratio(text)` wrapper (lazy import + env knob
    `CHARACTER_SIGNAL_ENABLE` 默认 True), 触发转 `DeterministicTrigger(B4,
    medium)`, evidence 前缀 `[character_signal]`.
  - 接入点: `run_deterministic_checks` 末尾, 在 `check_prose_dynamics` 之后.
- `backend/tests/test_quality_spec.py`: +5 测试 (healthy / inner_heavy /
  dialogue_heavy / env kill / run_deterministic_checks 集成).

## 验证

### 单元测试

```
backend/tests/test_quality_spec.py::test_check_inner_monologue_healthy_no_trigger PASSED
backend/tests/test_quality_spec.py::test_check_inner_monologue_heavy_triggers_b4 PASSED
backend/tests/test_quality_spec.py::test_check_inner_monologue_dialogue_heavy_no_trigger PASSED
backend/tests/test_quality_spec.py::test_check_inner_monologue_env_kill_switch PASSED
backend/tests/test_quality_spec.py::test_run_deterministic_checks_includes_b4 PASSED
```

全量 backend tests: **870 PASS** (vs phase6c 第二刀基线 835, 零回归).

### Offline replay — Phase 6-A.2 500-tick 271 narratives

实跑 `character_signal_report` 在 healthy 长程基线上, 看触发频次:

| 指标 | 数值 | 解读 |
|---|---:|---|
| narratives ≥ 100 chars | 271 | 校准基线 |
| **B4 触发** | **0 (0.00%)** | healthy bench 不触发, 符合 det 设计意图 ✓ |
| avg inner / cjk | 0.11% | 实测 healthy 长程内心独白几乎为 0 |
| avg dialogue / cjk | 9.26% | 实测对话占比, 远大于 inner |

**触发率 0%** 与 prose_dynamics D6 校准 (0.00%) / 老 E1 (0.00%) 完全一致 —
healthy bench 没有 FP, det 层仅在 LLM 退化为"全段独白"时介入 (典型失败模式).

cost 增量预期: < 0.5% (B4 触发率 ≤ 0.5% → critic REVISE 增量可忽略).

## verdict = PASS

- coverage∆: 新加 B4 dim det 路径 (B 维度首项 det check)
- token∆: 0 (healthy bench 0 触发)
- test∆: 835 → 870 (+5 B4 + 30 v2.48 dashboard test 增量, 零回归)
- 风险: 1★ — 接入路径与 E1/D6 同构, env kill switch 完备

Phase 6-C 第三刀 LANDED. det → REVISE 决策路径 B/D/E 三维度均已打通.

## 不在此刀

- B 维度其他子项 (B1/B2/B5/B6/B7) — semantic, 留 LLM critic
- C/F/G 各项 — 大多 semantic
- B4 严格 spec 实现 (区分 action vs environment 字数) — 需要中文 POS,
  超出 det 层范围, LLM critic 仍承担细化判断

## Sources

- Phase 6-C 第二刀 verdict: `docs/iter/verdict-phase6c-prose-integrated.md`
- spec: `docs/design/novel_quality_critique_and_iteration.md` B4
- 校准基线: `backend/data/users/bench/novels/bench_phase6a2-longrange-500tick_1781696585/narratives/` (271 narratives)
- 接入: `backend/agents/quality_checks.py::check_inner_monologue_ratio`
- 测试: `backend/tests/test_quality_spec.py::test_check_inner_monologue_*`
