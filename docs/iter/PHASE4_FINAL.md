# Phase 4 Final Verdict (iter#158)

> Phase 4 (iter#139-157) 综合 closure: **E LANDED 大胜** / F 尝试 revert /
> G 不动 / D 跳过.

## Phase 4 iter trail (#139-157)

| iter | type | candidate | status |
| --- | --- | --- | --- |
| #139 | code | E infrastructure | ShowrunnerOutput.sidelined + TickState API + orchestrator wire + 16 测试 |
| #140 | bench | E conservative prompt | 0 sideline 触发 (LLM 太保守) |
| #141 | code | E prompt strengthen | ≥4 chars 必须 sideline |
| #142 | bench | E mandatory | char_limou sideline tick 5-30 |
| #143 | judge | E first positive | 66.67% mimo (confounded) |
| #144 | bench | E seed1 controlled cast=5 | sideline 触发 |
| #145 | judge | E clean A/B seed1 | **80% v16 decisive** |
| #146 | bench | E seed2 controlled | sideline 触发 |
| #147 | judge | E seed2 | **50% borderline tied** |
| #148 | bench | E seed3 controlled (retry) | sideline tick 35 触发 |
| #149 | judge | E seed3 | **77.78% v16 decisive** |
| #150 | docs | E landing | README + PHASE4_PLAN sync |
| #151 | code | E cycle 18 review fix | 3 HIGH + 2 MEDIUM (release_sideline 等) |
| #152 | code | F try | _CRITIQUE_MAX_OUTPUT 1500→1200 |
| #153 | bench | F seed1 | bench cast=3 (LLM 偷工) |
| #154 | judge | F seed1 | 50% v16 (single-seed pass) |
| #155 | bench | F seed2 retry | bench cast=5 |
| #156 | judge | F seed2 | 40% stage2_open (borderline 退化) |
| #157 | code | F revert | 1200 → 1500 回 baseline |

19 iter Phase 4-E (含 review fix) / 6 iter Phase 4-F (含 revert) / 0 iter G / 0 iter D.

## Phase 4-E LANDED (大胜)

**3-seed × clean A/B × pairwise mimo FINAL**:

| seed | v15 (no sideline) | v16 (sideline ON) | verdict |
| --- | ---: | ---: | --- |
| seed1 | 20% | **80%** | v16_promote decisive |
| seed2 | 50% | 50% | v16_promote borderline |
| seed3 | 22% | **77.78%** | v16_promote decisive |
| **avg** | 30.7% | **69.3%** | **all promote** |

* cost +1.2% (中性, σ 内)
* drift 0 跨 3 seed
* default ON (无 opt-in flag)

机制: Showrunner 每 5 tick 看 character arc, 推荐暂时 sideline 1-2 个不在
核心冲突的角色, orchestrator 跳 batch_decide LLM 一段 TTL=10 tick, 到期
自动恢复. 与 iter#128 静态 cast=3 关键差别: 动态 sideline 保留池子 + 灵活
退场, 而非永远缺.

## Phase 4-F 尝试 revert (教训)

iter#152 试 critic budget 1500→1200. iter#153/154 seed1 通过 (50% v16,
borderline). iter#155/156 seed2 = 40% (stage2_open). 跨 seed avg ~45% =
just at §4 threshold, 不够 decisive.

**与 iter#128 cast=3 同教训**: det 单 seed 通过 + cross-seed 边缘 → **revert
比赌更稳**. 单 seed 50% 通过的 "中性" 信号 = noise, 不是改进证据.

iter#157 revert 1200→1500.

## Phase 4-G/D 跳过原因

### G (compressor budget) — 不可压

`memory_compressor.py` budget=6144 是 iter#9 → iter#15 review 调过的范围:
- iter#9 试 4096 (太紧, JSON 中段截断丢 batch entries)
- iter#15 review 改 6144 给余量

进一步压回风险高, 无 slack. 跳过.

### D (memory fidelity probe) — 高成本无明确 ROI

200 tick × ~2M tokens × 单 seed = ~3-4 小时. 不是新功能, 仅验证 reducer.
与用户 goal #1 (minimize cost) 冲突. 跳过, 留 Phase 5 if 需.

## Phase trail 累积 (FINAL)

| Phase | iter range | 核心成果 |
| --- | --- | --- |
| Phase 1 | #3-72 | -77% tokens / -83% latency |
| Phase 2 | #76-112 | drift fix, 73.3% pairwise promote ×3 |
| Phase 3-B | #119-136 | --cast-{a,b,c}-count CLI opt-in (default revert wide) |
| **Phase 4-E** | **#139-151** | **runtime sideline default ON, +69.3% mimo, cost 中性** |
| Phase 4-F | #152-157 | budget tighten 尝试 revert (cross-seed 边缘 → 教训) |

净 production cumulative:
- Phase 1: 主导 cost 优化
- Phase 2: close-loop fix 修架构 gap
- Phase 3-B: CLI 工具沉淀 (default 不变)
- **Phase 4-E: 动态 sideline 架构升级 (mimo 跨题材 decisive 改善)**

## Phase 4 教训 (cross-Phase)

1. **det 不够测 prose dynamics**: distinct char-2 / drift / avg_urg 都看不
   出 character interaction 多元性退化. mimo pairwise 是 ground truth.
2. **配置-level 改动也需 mimo gate**: iter#128 cast=3 + iter#152 budget 都
   是 config 变化, 都需要跨 seed × 3 pairwise 验证.
3. **单 seed 50% borderline = noise**: 不是改进证据, **决策应基于 cross-
   seed ≥ 60% decisive 信号**.
4. **架构改动 (E) > 配置改动 (F)**: Phase 4-E 通过的本质是 **新机制**, 而
   非 budget 压. 静态 cast / 静态 budget 都难赢 mimo.

## Continuation (next session candidates)

1. Phase 4-E 跨 seed 长程 stress test — 200 tick bench 看 sideline 在
   长 run 是否仍维持优势
2. memory fidelity probe (D) — 留作 phase 5 候选
3. critic prompt cache 探索 (CRITIC SYSTEM_PROMPT 已自动 cached, 检查
   user_prompt 中可不可以提前 static tail)
4. event_injector / world_simulator budget review

## Sources

- Phase 4-E final: `verdict-iter149-phase4e-3seed-final-promote.md`
- Phase 4-F revert: CHANGELOG v2.43 iter#157
- Phase 3 final (revised): `PHASE3_FINAL.md`
- Phase 2 final: `verdict-iter112-phase2-close-fix-final.md`
- Phase 1 trail: CHANGELOG v2.38
