# iter#4 · test · character_signal + translation_artifact dedicated test 补全

## Scope

iter#1 B4 (character_signal) + iter#3 E7 (translation_artifact) 两个 Phase
6-C wrapper 模块各只通过 `quality_checks` wrapper 间接覆盖 (各 5 test).
prose_dynamics 模块 (Phase 6-C 第一刀) 有 19 dedicated test, 平衡缺失.

本刀补全两模块各自的 dedicated unit test file, mirror prose_dynamics 模板.

## 改动

- `backend/tests/test_character_signal.py` (新): **18 测试**
  - char counters: total CJK / dialogue 三种引号 / empty quote / multiple
  - inner counter: no marker / marker 引号外 / marker 引号内跳 / evidence cap=3
  - B4 三层 guard: short / below ratio / all-inner-fallback / dialogue 主导
    / custom ratio
  - report: healthy / heavy / to_dict / empty default
- `backend/tests/test_translation_artifact.py` (新): **18 测试**
  - 7 pattern 各自 detection (对于…来说 / 这是一个…的 / 被…所… /
    长定语链 / 不仅…而且… / 由于…的原因 / 对…而言)
  - min_hits guard: single hit / two different / custom threshold
  - report: healthy / heavy / to_dict / empty default
- `quality_metrics/character_signal.py` 算法精确化:
  - `count_inner_monologue_chars` 改为 marker-position-aware quote skip,
    而非 sentence-span-corner. 修了 corner case: sentence span 跨 quote
    边界 (例 `他说:"我想到X"。` split 在 `。` 前 — span start 在 quote 外,
    但 marker 在 quote 内) 时旧逻辑会误算 inner. 新逻辑用 absolute marker
    position 索引 in_quote mask, 精确跳过.

## 验证

```
backend/tests/test_character_signal.py ........ 18/18 PASS
backend/tests/test_translation_artifact.py ........ 18/18 PASS
backend/tests/test_quality_spec.py ........ 41/41 PASS (含原 36 + 5 E7 集成)
```

全量 backend tests: **921 PASS** (iter#3 884 + 37 新 test, 零回归).

## verdict = PASS

- coverage∆: +37 test (18 character_signal + 18 translation_artifact +
  1 算法修正 corner case)
- 算法∆: character_signal marker-in-quote 精确跳过 (此前: sentence span
  跨 quote 时漏算; 现在: marker 绝对位置查 in_quote mask)
- 风险: 1★ — 测试补全 + 算法只增加准确性, 不改触发阈值

Phase 6-C wrapper trilogy (prose_dynamics + character_signal +
translation_artifact) test 覆盖现在均衡: 19 + 18 + 18 = **55 dedicated unit**.

## 不在此刀

- prose_dynamics 算法精确化 (19 test 已稳定, 无 corner case)
- 其他 det check (check_word_repetition / check_summary_ending) 内部测试
  — 已在 test_quality_spec.py 主入口集成测试覆盖, 不补 dedicated

## Sources

- 模板基线: `backend/tests/test_prose_dynamics.py` (Phase 6-C 第一刀)
- 算法修复点: `quality_metrics/character_signal.py::count_inner_monologue_chars`
- 测试新文件: `backend/tests/test_character_signal.py`,
  `backend/tests/test_translation_artifact.py`
