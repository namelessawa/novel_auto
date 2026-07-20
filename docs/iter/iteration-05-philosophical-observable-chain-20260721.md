# Iteration 05 — philosophical observable chain

- iteration_id: `20260721-05-philosophical-observable-chain`
- date: `2026-07-21`
- base_git_sha: `0b095484aeed309c90ab6432d07ce6619619371a`
- candidate_git_sha: `41d363270836f50f9c03448f62e405217f4683f8`
- provider: `custom`
- model: `glm-5.2`
- themes: `apocalypse_wasteland`, `scifi_soft_lit`
- styles: `philosophical_meditative`（候选）；盲测分类仍读取全注册表
- seeds: 主题注册表的持久 seed；provider 不提供可验证的采样 seed 回显
- tick_counts: `1` per scenario

## Hypothesis

观察：盲测中 `philosophical_meditative` 在 pressure 与 compatible 两种场景均被
Top-1 判为 `noir_cold`，且两次都未进入 Top-3。目标已知 semantic judge 对
compatible 给 `9.0`，仍指出时间错位未明确；pressure 文本则几乎完全由短对白、
动作和克制信息构成。

根因假设：现契约只“允许”1–2句抽象命题，没有要求出现可观察的命题推进；模型在
行动压力下可以合法省略该风格唯一的区分性结构，剩余约束与 `noir_cold` 高度重叠。

准备修改的最小范围：只升级 `philosophical_meditative` 的版本、addendum 与尾部短
清单；要求每个叙述单元至少一次“具体物→概念问题→人物选择/代价”链，并明确不能
漏写事件结果或新增事实。不修改 Narrator、其他 preset、全局 schema 或旧 snapshot。

预期改善的指标：同输入场景的两段候选至少进入盲测 Top-3，且目标已知 semantic
judge 均通过；事实复验、人物存在与事件兑现不得下降。

可能退化的指标：高压段因抽象句拖慢动作；模型写成议论文；为制造哲思新增世界规则；
prompt 变长；同模型盲 judge 自偏。

验证方法：preset 可观察准则与独立版本单测；全后端测试；同 provider/model/theme/
event/tick 参数重跑 pressure+compatible；目标已知 judge 和全候选匿名盲测双重检查。
provider API 不回显采样 seed，因此把模型随机性列为显式限制，不宣称字节级复现。

回滚条件：任一场景新增事实/状态硬错误、事件结果漏写、只提升目标已知 judge 而盲测
仍双失败、兼容场景恶化、或其他 preset 的版本/hash 被改变。

## Result

- files_changed (candidate, subsequently reverted):
  - `backend/novel_presets/style_presets.py`: scoped philosophical contract
    `2026-07-21.1`, prompt hash `4f16f22d…`
  - `backend/tests/test_novel_presets.py`: observable-chain and scoped-version tests
- tests_added: `backend/tests/test_novel_presets.py`
- baseline_metrics:
  - blind top-1 `0/2`, top-3 `0/2`
  - target-known accepted `1/2`; 两段 semantic score 均为 `9.0`
  - state conflicts `0/2`
- candidate_metrics:
  - target-known accepted `2/2`; semantic score 均为 `9.0`
  - deterministic pass `2/2`; state conflicts `0/2`; rewrite `0/2`
  - blind top-1 `0/2`, top-3 `0/2`（目标指标无改善）
  - pressure top-3: `noir_cold, rough_grit_realism, xianxia_fast`
  - compatible top-3: `noir_cold, literary, melancholic`
- failure_samples:
  - pressure 候选明确写出“他扣的不是通行证。他扣的是时间”，但这一句没有改变
    全段的短对白、动作替代心理、信息延迟结构，盲判仍为 `noir_cold`
  - compatible 候选使用镜中时钟延迟和地图名字移动，盲判仍认为核心是克制第三人称、
    物件承载心理，也判为 `noir_cold`
- cost_delta:
  - candidate generation + target-known judge wall time `362.8s`
  - blind judge `10,105` tokens / `32.5s`
  - `validate_styles.py` 当前未把生成/semantic judge token 写入产物，因此总 token
    delta 不可得；这是下一轮应修的测量盲区，不能把未知写成零
- verdict: `REJECT`
- rollback_status: `complete` via
  `9713158d1847fa64de489f8cd86b5ee69c347d6f`
- next_recommendation: 不继续增加同类哲思措辞。先让 `validate_styles.py` 记录各阶段
  token/时延，再研究段落层可观察结构指标；在有跨 seed 证据前不改生产 preset。

## Evidence artifacts

- `docs/iter/style-candidate-philosophical-glm-20260721.json`
- `docs/iter/style-candidate-philosophical-glm-20260721.md`
- `docs/iter/blind-style-candidate-philosophical-glm-20260721.json`
- `docs/iter/blind-style-candidate-philosophical-glm-20260721.md`

## Acceptance decision

目标已知 judge 提升而盲测不变，属于 rubric 顺应而非稳定辨识度提升，命中强制回滚
条件。候选没有事实硬错误，但这不能替代目标指标改善。候选及失败产物保留，生产
风格契约、版本和 prompt hash 均已恢复。

## Verification

```powershell
python -m pytest backend/tests/test_novel_presets.py backend/tests/test_narrator_prefix_cache.py -q
python -m pytest backend/tests/ -q
```

候选 Gate A 为 `1224 passed, 1 warning`；回滚后为 `1222 passed, 1 warning`。
warning 是既有 `StarletteDeprecationWarning`。
