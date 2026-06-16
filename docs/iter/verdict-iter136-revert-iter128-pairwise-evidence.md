# iter#136 — REVERT iter#128 cast=3 default 基于 3-seed pairwise 决定证据

> Phase 3-B verdict 重新评估. iter#133/134/135 3-seed × mimo pairwise 给
> 出与 det 指标**完全相反**的结论. iter#128 cast=3 default 必须 revert.

## 3-seed × pairwise FINAL matrix

| seed | cast=3 win | wide win | tie | verdict | det 说 |
| --- | ---: | ---: | ---: | --- | --- |
| seed1 (蒸汽朋克) | 20% | **80%** | 0% | v15_hold | cast=3 distinct +2.6% |
| seed2 (民国) | 50% | 50% | 0% | v16_borderline | cast=3 distinct -1.0% |
| seed3 (末世) | 30% | **60%** | 10% | v15_hold | cast=3 distinct +0.3% |
| **avg** | **33.3%** | **63.3%** | 3.3% | **wide preferred** | det 误导 |

cast=3 跨 3-seed 平均 33.3% win-rate vs wide 63.3%. **2/3 v15_hold**.

## Phase 2 vs Phase 3-B det-mimo 一致性对比

| 场景 | det 说 | mimo 说 | 一致? |
| --- | --- | --- | --- |
| Phase 2 close-fix vs Phase 2 baseline (#109/#111/#112) | close-fix slight 优 | **close-fix 70-80% 胜** | ✓ 一致 |
| **Phase 3-B cast=3 vs close-fix wide (#133/#134/#135)** | **cast=3 看似优** | **wide 63% 胜** | **✗ 反向** |

Phase 2 close-fix 改动 (架构层) 让 det 与 mimo 同向; Phase 3-B cast count
改动 (配置层) 让 det 与 mimo 反向. 揭露: **det 指标对 prose dynamics
不敏感**, 只测 vocabulary diversity / repetition. mimo 测 plot drive +
character voice + interaction.

cast=3 = 1A+2B+0C 限 character interaction 多元性, 但 det 看不出.

## REVERT iter#128 action

`backend/bootstrap_prompts.py`:
- 默认 0/3 设 → 回到 wide range "6-10 / 3A+3-4B+2-3C"
- 修 docstring 反映 mimo quality 验证: "默认 wide, cast=3 仅 cost-first
  opt-in"
- 修 inline comment 同步
- 用户 `--cast-a-count 1 --cast-b-count 2 --cast-c-count 0` 仍可显式 opt-in
  cast=3 cost-first 模式

## 修改后双指标权衡

| config | cost (跨 3-seed avg) | mimo pairwise win |
| --- | ---: | ---: |
| cast=3 (1A+2B+0C, iter#128 试) | -36.4% vs Phase 2 baseline (best cost) | **33.3%** (worst quality) |
| **wide 6-10 (iter#136 revert)** | baseline (no change) | **63.3%** (better quality) |

trade-off 清晰. wide 是 quality-first default, cast=3 是 cost-first opt-in.

## 教训 (Phase 3-B retrospective)

1. **det 指标不够**: distinct char-2 / drift / avg_urg 都是表层指标. 没 catch
   character interaction 多元性这种"功能维度"差异.
2. **pairwise judge 是 quality gate ground truth**: Phase 2 流程对的, Phase
   3-B iter#119-128 只跑 det 验证就改 default 是 process gap.
3. **配置-level 改动也需 mimo gate**, 不只架构改动 (iter#103 close-fix 当时
   跑了 pairwise).

## Phase 3-B 最终 status update

| 候选 | 状态 | 净结果 |
| --- | --- | --- |
| A) narrator slim | 失败 revert (#114-115) | 教训 |
| **B) cast-confound** | **opt-in only (#119-127 + revert #136)** | **基建 OK, default 退回 wide** |
| C) prose diversity dim | 弱信号 (#116-118) | mattr 跨题材稳定但弱 |
| D) memory fidelity | 未启动 | 留 Phase 4 |

Phase 3-B 净: CLI 基建 (--cast-{a,b,c}-count) 保留作 cost-first opt-in 路径,
default behavior 不变.

## 跨 Phase cost 评估 revision

之前 iter#130 PHASE3_FINAL 称 "-36.4% vs Phase 2 baseline" → revised.

Phase 3-B default revert 后:
- 基建保留: --cast-{a,b,c}-count CLI + all-or-nothing 校验 + compliance warning
- default behavior: 与 Phase 2 一致 (wide range)
- 净 cost: 同 Phase 2 = ~25% of v1.x baseline (无 Phase 3-B 额外 cost 收益)

**修正累计**: Phase 1 -77% + Phase 2 ≈ 0 net + Phase 3-B 0 net = **-77%** vs
v1.x. (iter#130 称 -85.4% 基于 cast=3 default, revert 后正确数据是 -77%)

## 双指标 delta

cost delta: +36.4% (vs iter#128, revert 回 wide)
quality delta: +30 pp pairwise win-rate (33.3% → 63.3%)

## Continuation

iter#137+ 候选:
1. PHASE3_FINAL.md 更新 (iter#130 文档过时)
2. README.md 更新 (iter#132 cast=3 推荐过时)
3. cycle 18 review (iter#128/#129/#136 都是 code 改动)
4. 继续 Phase 4 候选探索 (memory fidelity / showrunner runtime cast cap)

## Sources

- iter#133 pairwise (seed1): `verdict-iter133-seed1-cast3-vs-closefix.{json,md}`
- iter#134 pairwise (seed2): `verdict-iter134-seed2-cast3-vs-closefix.{json,md}`
- iter#135 pairwise (seed3): `verdict-iter135-seed3-cast3-vs-closefix.{json,md}`
- iter#130 (过时): `PHASE3_FINAL.md`
- iter#133 finding doc: `verdict-iter133-cast3-pairwise-contradiction.md`
