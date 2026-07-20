# Iteration 04 — blind style classification

- iteration_id: `20260721-04-blind-style-classification`
- date: `2026-07-21`
- base_git_sha: `d6cee26`
- candidate_git_sha: `3965449a860708ed911c0781c51a7708c1ee7d6b`
- provider: `custom`
- model: `glm-5.2`
- themes: read from input artifact
- styles: dynamically read from `list_style_keys()`
- seeds: existing baseline artifacts; no new prose generation
- tick_counts: existing single-Tick samples

## Hypothesis

观察：现有 semantic style judge 直接拿目标 preset 判断合规，无法证明隐藏标签后仍可
辨认，也不能产出 top-1/top-3 或混淆矩阵。

根因假设：当前任务是目标已知的合规检查，不是目标未知的多类识别；高分会系统性
高估真实风格辨识度。

准备修改的最小范围：新增只读离线脚本，对注册表全部风格生成随机匿名候选契约，
只向 judge 提供正文与候选，逐样本 checkpoint，输出 top-1/top-3/混淆矩阵。

预期改善的指标：首次获得无目标标签泄漏的分类准确率、跨题材 pressure/compatible
分层结果和具体混淆对象；不改变任何生产生成结果。

可能退化的指标：同模型自偏；候选契约措辞过于显式；候选位置偏差；judge 成本。

验证方法：匿名 prompt 单测、salt 顺序单测、输出归一化和矩阵单测、全后端测试；
随后对 12 段 GLM 风格 baseline 运行真实分类。

回滚条件：prompt 泄漏 expected key/label；候选列表来自硬编码副本；无效 judge 输出
被当成命中；脚本无法 checkpoint/resume；或修改生产路径。

## Result

- files_changed:
  - `scripts/classify_styles_blind.py`: 动态匿名候选、逐样本 checkpoint/resume、
    top-1/top-3/混淆矩阵、真实 token 读取、50k 默认硬预算
  - `backend/tests/test_blind_style_classifier.py`: 标签隐藏、随机顺序、归一化、
    混淆矩阵、typed usage 与预算 fail-closed 回归
- tests_added: `backend/tests/test_blind_style_classifier.py`
- baseline_metrics: semantic contract judge `9/12` accepted, but not blind
- candidate_metrics:
  - 真实分类 run Git SHA: `c38fc7c69f329964d270c2da067849c91b67cde2`
  - valid: `12/12`
  - top-1: `6/12 = 0.5000`
  - top-3: `7/12 = 0.5833`
  - pressure: top-1 `2/6`, top-3 `3/6`
  - compatible: top-1 `4/6`, top-3 `4/6`
  - trial1 与 token-fix 后复测聚合完全一致；逐样本完整排名有 `2/12`
    变化，说明仍有 judge 方差
- failure_samples:
  - pressure / apocalypse_wasteland / `warm_healing`: top-3 为
    `rough_grit_realism, noir_cold, literary`
  - pressure / apocalypse_wasteland / `ensemble_epic`: top-3 为
    `xianxia_fast, rough_grit_realism, noir_cold`
  - pressure / apocalypse_wasteland / `philosophical_meditative`: top-3 为
    `noir_cold, rough_grit_realism, melancholic`
  - compatible / history_military / `ensemble_epic`: top-3 为
    `noir_cold, literary, melancholic`
  - compatible / scifi_soft_lit / `philosophical_meditative`: top-3 为
    `noir_cold, literary, melancholic`
- cost_delta:
  - 第二次完整分类 `56,874` judge tokens，墙钟 `142.3s`
  - 第一次分类 `130.9s`，因 usage 字段读取错误，token 数无效；原始结果保留
  - 完整 12 样本超过仓库默认 50k 预算，因此产物明确使用
    `--judge-budget 60000`；候选默认已改为 50k fail-closed
- verdict: `ACCEPT`（接受测量工具，不代表接受任何生产 Prompt 或默认值）
- rollback_status: `not required`; 生产生成链路未修改
- next_recommendation: 以两个场景都出现的
  `philosophical_meditative -> noir_cold` 为单一问题，先检查可观察特征差异及
  压力场景事实兑现，再提出最小、可证伪的生成侧假设。

## Evidence artifacts

- `docs/iter/blind-style-baseline-glm-20260721.json`
- `docs/iter/blind-style-baseline-glm-20260721.md`
- `docs/iter/blind-style-baseline-glm-trial1-pre-token-fix-20260721.json`
- `docs/iter/blind-style-baseline-glm-trial1-pre-token-fix-20260721.md`

产物只保存正文 SHA-256、字数、匿名判定及短证据，不复制正文。provider metadata
只记录模型、URL 与凭据是否存在，不保存凭据值。

## Verification

```powershell
python -m pytest backend/tests/test_blind_style_classifier.py -q
python -m pytest backend/tests/ -q
python scripts/classify_styles_blind.py `
  --input docs/iter/style-baseline-glm-20260721.json `
  --provider-file coding.txt `
  --sample-styles xianxia_fast,noir_cold,warm_healing,ensemble_epic,philosophical_meditative,rough_grit_realism `
  --judge-budget 60000 `
  --out docs/iter/blind-style-baseline-glm-20260721.json
```

最终 Gate A：`1222 passed, 1 warning`。warning 是既有
`StarletteDeprecationWarning`。
