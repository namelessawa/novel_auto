# Phase 6-A 500-tick stress runbook

> Phase 6 候选 C — 单 seed 500 tick 长程持久性验证.
>
> 现已 PASS: 200 tick × seed1, 100 tick × 3 seed (Phase 5-D follow-up).
> 候补: 500 tick (~10h, ~5M tokens) 验证 memory_compressor L0→L1→L2→L3
> 长程 drift / sideline + stale-skip 累积稳定性 / clean_rate 长程趋势.

## 1 · Kickoff 命令

```bash
# 主 bench (seed1 = steampunk_archive 与 Phase 5-D follow-up 对齐)
LLM_PROVIDER=custom \
ARK_API_KEY=$ARK_API_KEY \
ARK_BASE_URL=$ARK_BASE_URL \
ARK_MODEL=$ARK_MODEL \
python scripts/bench_tick.py \
    --ticks 500 \
    --theme steampunk_archive \
    --style literary \
    --cast-a-count 2 --cast-b-count 2 --cast-c-count 1 \
    --checkpoint-every 10 \
    --longrange-every 5 \
    --label phase6a-500tick-seed1 \
    --log-level WARNING
```

* `--cast-a-count 2 --cast-b-count 2 --cast-c-count 1` = cast221 锁定 (Phase
  3-B sweet-spot, iter#124-127).
* `--checkpoint-every 10` — 长程 bench 重点防止 crash 丢全部进度. 中途 kill 时
  最近 checkpoint 留 disk.
* `--longrange-every 5` — Stage 3 长程采样 100 个 tick 采样 (500/5).

## 2 · 预期资源

| 资源 | 估算 |
| --- | ---: |
| 时长 | ~10 小时 (avg 68s/tick × 500) |
| Tokens (生成) | ~5M output + ~30M input |
| Tokens (judge) | 0 (本 bench 不开 `--quality`) |
| 磁盘 | bench-{label}.json ~3MB, narratives/ ~2.5MB, checkpoint snapshot ~50KB |

> Note: 不开 `--quality` 是有意 — Phase 6-A 目标是 drift 验证, 不是 pairwise.
> Pairwise 留 6-C 阶段集中跑.

## 3 · 同步监控

每 50 tick (~50 分钟) 看一次 checkpoint:

```bash
python scripts/analyze_longrange_drift.py docs/iter/bench-phase6a-500tick-seed1.json
```

紧盯 6 个信号:

| 信号 | drift 警告阈值 |
| --- | --- |
| avg_dur_per_tick 50-bucket | 任何 50-bucket > 起始 50-bucket × 1.5 |
| total_tokens 50-bucket cumulative slope | 单调上升斜率 < 8% (否则警告 cascade) |
| narrator clean_rate 50-bucket | 任何 50-bucket clean_rate 比起始 ↓ ≥15pp |
| open_loops 数 (snapshot 长期) | 上限 6 (`EVENT_INJECTOR_OPEN_LOOP_CAP`) 应不被持续突破 |
| memory_compressor L0→L1 触发次数 | 必须每 ~50 tick 至少触发 1 次 (说明压缩正常) |
| consistency_guardian 累计 contradictions | 长程不能爆 (300+) |

## 4 · 完成判定 (verdict-phase6a-500tick.md gate)

PASS:
* 500 tick 全跑完, completed_ticks == 500
* 无 drift 信号 (所有 50-bucket 内 6 个指标在阈值内)
* 末段 narrative quality samples 抽 10 段 manual 看 ≥7 段无明显退化

WARN (可 ship, 但留 note):
* drift 信号 1-2 项触发但 quality 抽样无肉眼可见退化
* 后续 phase 需带 long-context calibration 数据点

FAIL (revert / 复盘):
* drift 信号 3+ 项 / 完成率 < 90%
* memory_compressor 没触发 (说明压缩 silent 坏掉)
* clean_rate 长程 cascade 下跌

## 5 · 复盘产物

跑完后产:
* `docs/iter/bench-phase6a-500tick-seed1.{json,md}` — 原 bench 输出
* `docs/iter/longrange-phase6a-500tick-seed1.{json,md}` — longrange 采样
* `docs/iter/verdict-phase6a-500tick.md` — 人工写的结论, 含 6 指标 + 抽样段
* `docs/iter/PHASE6A_FINAL.md` — 若 PASS, archive 给后续 phase 参考

## 6 · 不在此 bench

* Cross-seed 扩展 — 单 seed 跑过了再做 3-seed (若有差异再做)
* 多 POV / 多模态 — 与 6-A 解耦, 留 6-D/E
* --quality pairwise — 留 6-C 集中跑, 减少 6-A 单变量影响

## 7 · 长程 checkpoint 中断恢复

bench_tick.py 不支持 mid-run resume (一次性 process). 中断后:
1. 不要删 bench-{label}.json — 保留最近 checkpoint 作为已完成片段证据
2. 重新跑相同 --label 会**覆盖** 之前的 partial JSON
3. 若 80%+ tick 已完成, partial json 足够分析, 不必重新跑
4. 若 < 50%, 直接重跑 (不重要)

## 8 · Cron 部署 (可选)

若要后台跑, 在 SessionEnd / nightly cron 触发. 推荐:

```bash
# crontab -e
0 22 * * 0  cd /e/pythonproject/novel_auto && \
   nohup python scripts/bench_tick.py \
       --ticks 500 --theme steampunk_archive --style literary \
       --cast-a-count 2 --cast-b-count 2 --cast-c-count 1 \
       --checkpoint-every 10 \
       --label phase6a-500tick-$(date +%Y%m%d) \
       > logs/phase6a-$(date +%Y%m%d).log 2>&1 &
```

## 9 · Quota smoke (推荐流程)

跑长程 bench 前用 `scripts/probe_quota.py` (iter#HHH) 1 个 LLM call 验证
quota, 比老的 `bench_tick.py --ticks 1` 快 3x (≤1s vs 3s) 且 tokens 少 95%
(~200 vs 4000).

```bash
python scripts/probe_quota.py
echo "exit: $?"   # 0=healthy / 1=quota wall / 2=other error
```

cron 入口模板:

```bash
python scripts/probe_quota.py
if [ $? -eq 0 ]; then
    python scripts/bench_tick.py --ticks 500 ... &
else
    echo "quota not healthy, abort" >&2
fi
```

## 10 · Cross-seed (3-seed) 批量

iter#OO 加 `--themes` (comma-separated) 顺序跑 N seed, 比起 launch 3 次省事:

```bash
python scripts/bench_tick.py --ticks 500 \\
    --themes 'steampunk_archive,republic_spy,apocalypse_wasteland' \\
    --style literary \\
    --cast-a-count 2 --cast-b-count 2 --cast-c-count 1 \\
    --checkpoint-every 10 --longrange-every 5 \\
    --label phase6a-multi-$(date +%Y%m%d)
```

完成后用 iter#TT3 的 `compare_bench.py` 出 cross-seed 对比 markdown:

```bash
python scripts/compare_bench.py \\
    docs/iter/bench-phase6a-multi-*-steampunk_archive.json \\
    docs/iter/bench-phase6a-multi-*-republic_spy.json \\
    docs/iter/bench-phase6a-multi-*-apocalypse_wasteland.json \\
    --out-md docs/iter/verdict-3seed-compare.md
```

**注意 quota**: 单 seed 500-tick ≈ 3M tokens, DeepSeek 5h 滚动窗约 ~5M.
3-seed 顺序跑需要跨 ≥2 个 quota window (~10h+), 实测 quota 触底会被
orchestrator 优雅降级 (LLM no-op), 后续 tick 0.3s/tick 完成但 narrative
为空.
