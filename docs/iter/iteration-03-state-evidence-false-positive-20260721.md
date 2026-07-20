# Iteration 03 — NarrativeStateGuard evidence false positives

- iteration_id: `20260721-03-state-evidence-false-positive`
- date: `2026-07-21`
- base_git_sha: `6cc1249`
- candidate_git_sha: `4c335c7` (attempt 1), `e63bb36` (attempt 2)
- provider: `custom`
- model: `glm-5.2` (DeepSeek fallback sample retained only as corroboration)
- themes: `apocalypse_wasteland`
- styles: `literary,first_person_immersive,ensemble_epic`
- seeds: style validator frozen bootstrap seed per run
- tick_counts: `4`

## Hypothesis

观察：GLM 4-Tick 压力序列 0/3 通过；9 个缺失正文 Tick 中，多个 Tick 的 LLM
verifier 同时给出 `reported_safe=true`、逐条 `met=true`、有效正文引文和有效账本路径，
但确定性语义检查仍判不安全，修订后再次以同一原因拒绝。DeepSeek 文学样本也复现。

根因假设：确定性高精度 gate 的语言模式过窄，只接受“雨在损坏句之前”、单句明确
写“两人进入”、以及预设物品/任务式代价；它不识别中文常见的结果后补天气、分句
先送伤员再跟进、`往里走` 和“欠一次”义务，因此产生假阳性。

准备修改的最小范围：只扩展 `NarrativeStateGuard._semantic_evidence_failure` 的
确定性证据识别；不改 LLM prompt、修订次数、阈值、Narrator 产出规则或状态账本。

预期改善的指标：真实失败样本中的雨损因果、两人过门和新债务不再被误杀；既有
“一人进城另一人留在外面”“污水损坏冒充雨损”“重复地图付款冒充新代价”仍拒绝。

可能退化的指标：放宽模式可能让模糊移动或无关天气被误当兑现。

验证方法：四个修改前失败的最小回归；全部既有 NarrativeStateGuard 测试；全后端；
同一 GLM、同一压力序列、同一三个风格对照，并逐 Tick核对事实守恒。

回滚条件：任一既有负例转为通过；新专名/知识越权/物品归属错误增加；目标正文虽
保留但 required end state 实际未兑现；或只对一个风格有效。

## Result

- files_changed:
  - attempted: `backend/agents/narrative_state_guard.py`
  - attempted tests: `backend/tests/test_narrative_state_guard_evidence_regressions.py`
  - both were removed by rollback commits `8799880` and `736977a`
- tests_added: 11 positive/negative evidence cases during the experiment; removed with the
  rejected implementation so the reverted production behavior and test suite remain aligned.
- baseline_metrics: GLM sequence `0/3`, accepted narrative ticks `6/12`
- candidate_metrics:
  - attempt 1 (`4c335c7`): `0/3`, accepted narrative ticks `6/12`;
    literary/first-person/ensemble = `1/4, 3/4, 2/4`.
  - attempt 2 (`e63bb36`): `0/3`, accepted narrative ticks `6/12`;
    literary/first-person/ensemble = `3/4, 2/4, 1/4`.
  - baseline and both candidates therefore have identical aggregate retained-Tick count,
    while the worst style remains `1/4`; no stable cross-style improvement.
- failure_samples:
  - true failures correctly kept rejecting: a character still on the roof instead of the
    wall, an unauthorized new name `老赵`, and ambiguous item holder/location changes.
  - false-positive evidence forms shifted across stochastic generations (pronoun crossing,
    rain causality, settlement interior aliases, extra knife/debt cost), so regex expansion
    improved one style while worsening another.
  - raw artifacts: `style-sequence-candidate-state-evidence-glm-20260721.json` and
    `style-sequence-candidate-state-evidence-v2-glm-20260721.json`.
- cost_delta: production delta is zero after rollback. Experimental real-model cost was
  incurred, but did not buy a stable quality gain.
- verdict: `REJECT`
- rollback_status: `COMPLETE` via `8799880` + `736977a`
- next_recommendation: retain a privacy-safe, exact replay fixture for rejected pre-guard
  candidate text (or a deterministic structured evidence payload) before further Gate tuning.
  Do not globally relax the verifier from stochastic re-generation alone.
