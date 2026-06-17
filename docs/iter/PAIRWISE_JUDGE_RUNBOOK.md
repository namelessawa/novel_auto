# Pairwise judge runbook — PHASE5_PLAN K 标准操作流程

> Status: tooling LANDED (Phase 5-D follow-up)
> Updated: 2026-06-17

Phase 5-A / 5-B / 5-E 都遵守"架构改动 mandatory cross-seed ×3"教训。
PHASE5_PLAN K 把这个流程从手动 (~半天 / cycle) 落到 3 个标准化脚本里。
本 runbook 把跑 cross-seed pairwise gate 的完整步骤固化。

## 3 个固定 seed (标准化)

PHASE4_FINAL + PHASE5_PLAN 选定 plot-light / medium / plot-dense 三档:

| name | theme key | label 中文 | bench 命名建议 |
| --- | --- | --- | --- |
| seed1 | `steampunk_archive` | 蒸汽朋克悬疑 (plot-light, 默认) | `<feature>-seed1-steampunk` |
| seed2 | `republic_spy` | 民国谍战 (plot-medium) | `<feature>-seed2-republic` |
| seed3 | `apocalypse_wasteland` | 末世废土 (plot-dense) | `<feature>-seed3-apocalypse` |

跨 seed 一致的 PASS 是 ship 的 ground truth。单 seed PASS 是 noise (iter#128 / iter#157 教训)。

## 一次 ship gate cycle 全流程

> 假设你刚改完 Phase 5+X 候选, 要决定 ship / revert。

### Step 1 — 跑 6 个 bench (baseline × 3 seed + candidate × 3 seed)

baseline = 你的 candidate revert 后的状态 (或 `main` HEAD)。
candidate = 你的改动启用后的状态。

```bash
# baseline (Phase 5+X 关掉, 跑 3 seed)
git checkout main -- backend/agents/
WORLD_STALE_SKIP_ENABLED=0 python scripts/bench_tick.py \
  --theme steampunk_archive --ticks 50 \
  --label phase5x-baseline-seed1-steampunk

python scripts/bench_tick.py \
  --theme republic_spy --ticks 50 \
  --label phase5x-baseline-seed2-republic

python scripts/bench_tick.py \
  --theme apocalypse_wasteland --ticks 50 \
  --label phase5x-baseline-seed3-apocalypse

# candidate (Phase 5+X 启用)
git checkout <feature-branch> -- backend/agents/
python scripts/bench_tick.py \
  --theme steampunk_archive --ticks 50 \
  --label phase5x-candidate-seed1-steampunk

python scripts/bench_tick.py \
  --theme republic_spy --ticks 50 \
  --label phase5x-candidate-seed2-republic

python scripts/bench_tick.py \
  --theme apocalypse_wasteland --ticks 50 \
  --label phase5x-candidate-seed3-apocalypse
```

**重要 env**:
* `LLM_PROVIDER=custom` — 走 ARK deepseek-v4-pro 生成
* `JUDGE_PROVIDER=ark_glm` (默认) 或 `mimo` — judge 路径
* `LLM_PER_CALL_SLEEP=3` — ARK TPM 救命旋钮 (撞 429 才开)

Bench 单 seed × 50 tick ≈ 35-50 分钟. 6 bench 串行 ≈ 4-5 小时.
长程 stress 用 `--ticks 200 --checkpoint-every 10`。

### Step 2 — 跑 3-seed pairwise judge

```bash
python scripts/cross_seed_pairwise.py \
  --pair seed1=docs/iter/bench-phase5x-baseline-seed1-steampunk.json,docs/iter/bench-phase5x-candidate-seed1-steampunk.json \
  --pair seed2=docs/iter/bench-phase5x-baseline-seed2-republic.json,docs/iter/bench-phase5x-candidate-seed2-republic.json \
  --pair seed3=docs/iter/bench-phase5x-baseline-seed3-apocalypse.json,docs/iter/bench-phase5x-candidate-seed3-apocalypse.json \
  --max-pairs 20 \
  --output docs/iter/verdict-phase5x-3seed.md
```

每 seed 跑 ≤20 pair (max-pairs); judge 走 `JUDGE_PROVIDER` env 决定的 endpoint。
单 seed ~30s-1min, 3 seed ~3 min。

### Step 3 — 读 verdict

`docs/iter/verdict-phase5x-3seed.md` 自带 ship gate 决策:

| overall B win rate | gate | 行动 |
| --- | --- | --- |
| ≥ 60% | **PASS — SHIP** | promote candidate, 入 PHASE_FINAL |
| 45-60% | MARGINAL — RETRY | 追加 seed4/5 或考虑 revert |
| < 45% | **FAIL — REVERT** | revert 改动, 写 lesson 入 ITERATION_LOG |

**单 seed 50% borderline = noise** (PHASE4 教训#3)。

## HARD STOP 路径

1. judge endpoint 死 (mimo/ark_glm 401 / 429 / timeout × 3 连续):
   - `pairwise_judge_phase5` 进程 exit 2
   - `cross_seed_pairwise` 见到 exit 2 立即 abort 剩下的 seed
   - 用户介入: 查 `JUDGE_PROVIDER` 配额 / 切 fallback / 修 endpoint
2. `_DEFAULT_SEED` 写法异常 (LLM bootstrap 失败 3 次):
   - bench_tick.py 自身 raise, cross_seed wrapper 把该 seed 标 error
   - 其他 seed 继续 (per-seed 隔离)

> 用户 [[feedback_mimo_hard_stop]] 规则: 不静默 fallback 到 det-only.

## 标准化 mode 速查

| 想做 | 命令 | 备注 |
| --- | --- | --- |
| 单 seed 短 bench | `bench_tick.py --theme T --ticks 50 --label L` | 3 min smoke |
| 单 seed 长程 stress | `bench_tick.py --theme T --ticks 200 --checkpoint-every 10` | 4-6 hr |
| 3-seed pairwise gate | `cross_seed_pairwise.py --pair seed1=...` × 3 | ship 决策 |
| 16 主题 × 13 风格 matrix | `matrix_bench.py --ticks 3` | preset 覆盖 |
| 单对 pairwise (临时) | `pairwise_judge_phase5.py --bench-a ... --bench-b ...` | 不入 3-seed gate |
| 已有 bench 跑 retro judge | `judge_existing.py docs/iter/bench-X.json` | 配额耗尽 fallback |

## 不在 runbook 里 (intentional)

* **自动 bench 触发**: 用户决定何时 cost (~4-5 hr × seed 数)
* **CI 集成**: 单 cycle ~5 hr + ARK 配额, 不适合 PR CI
* **持续监控**: 每 cycle 手动操作即可, 不值得 cron

## Sources

* `scripts/bench_tick.py` — 单 seed bench runner (Phase 5-D follow-up: 加 `--theme/--style`)
* `scripts/cross_seed_pairwise.py` — 3-seed 聚合 (Phase 5+ 已存在)
* `scripts/pairwise_judge_phase5.py` — 单对 mimo judge (Phase 5+ 已存在)
* `scripts/judge_existing.py` — 配额耗尽 retro judge (Phase 5+ 已存在)
* PHASE4 教训: `docs/iter/PHASE4_FINAL.md` § "Phase 4 教训 (cross-Phase)"
* PHASE5_PLAN: `docs/iter/PHASE5_PLAN.md` § Quality gate
