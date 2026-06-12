# STATUS — iter#120 pause point

> Phase 3-A/B/C 三方向已探, 当前 env block 在 Conda Python 3.11→3.14
> transition. 此文档帮用户回来快速 resume.

## 最近 iter trail (iter#100-119)

| iter | 类型 | 关键产出 |
| --- | --- | --- |
| #100-102 | bench | Phase 2 §4 N≥30 × 3-seed 50-tick mandate ✓ |
| #103 | code | Showrunner.loops_to_close + orchestrator wire |
| #104-107 | bench | close-fix 跨 3-seed det validation (all PASS) |
| #108 | code | add_open_loop dedup gate |
| #106, #110 | code | 2 review cycles 13-14 fixes |
| #109, #111, #112 | bench | 3-seed × pairwise judge: 70/70/80% promote ×3 |
| #113 | doc | PHASE3_PLAN candidates A/B/C/D |
| #114 | code | narrator summaries 5→3 (Phase 3-A 试) |
| #115 | bench+revert | iter#114 反向 +4.9% cost / -12.7% urg → revert |
| #116 | code | quality_metrics/diversity.py (TTR/MATTR/句长) |
| #117 | code | cycle 15 review fixes |
| #118 | doc+script | analyze_diversity.py + cross-bench 验证 (mattr 弱信号) |
| **#119** | **code** | **bootstrap --cast-{a,b,c}-count Phase 3-B CLI** |

## Phase 3 候选状态

| 候选 | 状态 | 备注 |
| --- | --- | --- |
| A) narrator prompt slim | **失败** | iter#114 反向, 已 revert. 教训: user_prompt 字段非字数游戏 |
| B) cast-confound 控制 | **代码就绪, 验证待运行** | iter#119 CLI 实现, 6 单测设计完成. 用户 env 修后跑 bench. |
| C) prose diversity dim | **基建完成, 信号弱** | iter#116/117/118. mattr 跨题材稳定但 -1.2% 不够区分 |
| D) memory fidelity | **未启动** | 高成本 (200 tick bench × 2-4M tokens). 留下个 phase. |

## 当前 env 阻塞详情

Session 中段 Conda 升 Python 3.11 → 3.14, transition 损坏:

1. `.c~` 文件大批 (56821) — iter#116 用 `p.rename(p.name[:-3])` 整批修复.
2. 后续 Conda 切 Python 3.14, site-packages .pyd 多是 cp311 ABI:
   - pydantic_core `_pydantic_core.cp311-win_amd64.pyd` 与 3.14 不兼容
   - pip 自身 metadata 损坏抛 `BadMetadata`, 无法 pip 重装
3. iter#119 test (`backend/tests/test_bootstrap_cast_size.py`) 无法本地跑.

## 用户 resume 步骤推荐

1. 关 Python 进程
2. 运行 `conda update --all` 或 `conda clean --all` 把 Conda transition 完成
3. 或在新虚拟环境装: `python -m venv .venv && .venv/Scripts/activate && pip install -r requirements-dev.txt`
4. 验证: `python --version`, `python -m pytest backend/tests/ --no-header -q`
   * 期望: 707/707 backend (4 auth bcrypt5+passlib1.7 dep 可能跳)
   * \+ 22 新 diversity
   * \+ 6 新 cast-size = 总 ~735

5. 验证 iter#119 cast-confound 实战:
   ```bash
   LLM_PROVIDER=custom python -m backend.bootstrap_prompts \
       --novel-id test_cast --seed "测试种子" \
       --cast-a-count 2 --cast-b-count 2 --cast-c-count 1
   ```
   期望: bootstrap 生成精确 2A + 2B + 1C = 5 角色 (不变 wide).

## Phase 3 候选方向 (按用户决策)

1. **B 续 — cast-controlled bench 实验**:
   - 跑 3 seed × `--cast-a-count 2 --cast-b-count 2 --cast-c-count 1` (固定 5 角色)
   - 对比之前 wide-range bench, cost 跨 seed σ 应大幅降
   - 触发 iter#102 P1 "seed3 cost 2.6x" 真正归因

2. **C 续 — mattr 集成到 longrange drift signals**:
   - 阈值: 若 mattr 跨 bench 段 -3% → 弱告警
   - 与 overlap_consec 组合: AND 触发才报真 drift

3. **D — memory fidelity probe 实战**:
   - 单 seed 200 tick bench (≈3-4 hr / 2M tokens cost)
   - 跨 tick 50/100/150/200 抓 L3 传说一致性

4. **新方向 — Showrunner prompt cache 探索**:
   - DeepSeek API auto-cache 命中要稳定 prefix
   - Showrunner SYSTEM_PROMPT 拆静态 / 动态部分

## Git 状态

```
分支: iter/cost-quality-loop
最新: 94cc192 iter#119: Phase 3-B cast-confound
HEAD~5: iter#118 (analyze_diversity)
HEAD~10: iter#113 (PHASE3_PLAN)
HEAD~20: iter#103 (close-loop fix, Phase 2 architectural change)
```

CHANGELOG.md `[2.40]` 包含 iter#114-119 全 trail.

## Sources

- 主 CHANGELOG: `CHANGELOG.md` v2.40
- Phase 2 final: `verdict-iter112-phase2-close-fix-final.md`
- Phase 3 plan: `PHASE3_PLAN.md`
- iter#115 失败案例: `verdict-iter115-narrator-slim-revert.md`
- iter#118 diversity 分析: `verdict-iter118-diversity-cross-bench.md`
