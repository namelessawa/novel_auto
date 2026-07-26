# Stage 1 Full Matrix Real Provider Validation

## 1. 结论

```text
STAGE1_FAIL
```

不进入 Stage 2。

15 个主题/风格组合和 45 次真实连续生成均已完成，但正式提交、最终
Narrative Contract 和 Repair 成功率均未达到 Gate。失败发生后没有修改
Prompt、Validator、Contract、Repair Patch 安全规则或 fixture，也没有重跑或
覆盖失败 transaction。

## 2. 环境

| 项目 | 值 |
| --- | --- |
| branch | `codex/stage1-full-matrix-validation-20260726` |
| execution commit | `6458951d948d55d1fff096e67ff49ec3604d47e5` (`test: harden stage1 matrix evidence`) |
| baseline commit | `607f0445dd534dc4a1cbe240881289b5c433ad85` |
| provider | `custom`（凭据来自 `coding.txt`，未写入产物） |
| model | `glm-5.2` |
| seed | `20260726` |
| desired length | 900 |
| checkpoint | 每节；runtime 每 2 节重建 |
| 时间 | 2026-07-26 20:40:13–21:03:29, Asia/Shanghai |
| provider calls | 71（45 Writer + 26 Repair） |
| prompt tokens | 311,459 |
| completion tokens | 74,770 |
| total tokens | 386,229 |
| mean latency | 30.9078 秒/attempt |

执行前验证：

* `python -m ruff check ...`：通过；
* 定向回归：14 passed；
* `python -m pytest backend/tests/ -q`：1494 passed，1 个既有
  StarletteDeprecationWarning。

真实执行命令：

```bash
python scripts/run_author_stage1_matrix.py \
  --provider-file coding.txt \
  --themes reality_mystery,action_conflict,warm_relationship \
  --styles literary,noir_cold,warm_healing,hot_blooded,classical_chapter \
  --sections-per-combo 3 \
  --checkpoint-every 1 \
  --runtime-rebuild-every 2 \
  --desired-length 900 \
  --seed 20260726 \
  --output-dir .tmp/stage1-full-matrix-20260726
```

## 3. Gate 表

| 项目 | 实际 | Gate | 结果 |
| --- | ---: | ---: | --- |
| 组合完成 | 15/15 | 15/15 | PASS |
| 真实 attempts | 45/45 | 45/45 | PASS |
| 正式提交 | 39/45 (86.67%) | ≥43/45 | **FAIL** |
| 最终 Contract pass | 39/45 (86.67%) | ≥95% | **FAIL** |
| Repair success | 20/26 (76.92%) | ≥90% | **FAIL** |
| Repair dependency | 26/45 (57.78%) | 既有 runner Gate ≤40% | **FAIL** |
| 硬事实错误提交 | 0 | 0 | PASS |
| 状态冲突提交 | 0 | 0 | PASS |
| 非法 ThreadChange 提交 | 0 | 0 | PASS |
| 无证据 StateDelta 提交 | 0 | 0 | PASS |
| transaction 数据损坏 | 0 | 0 | PASS |
| revision 跳号/断链 | 0 | 0 | PASS |
| 重复正式章节 | 0 | 0 | PASS |
| 重复 transaction | 0 | 0 | PASS |
| StoryBible revision 变化 | 0 | 0 | PASS |
| provider errors | 0 | 0 | PASS |

补充结果：

* required events completed：44/45；
* required end states reached：44/45；
* 被 Validator 丢弃、未提交的 StateDelta：12；
* 被 Validator 丢弃、未提交的 ThreadChange：6；
* 45 个 `(run_id, transaction_id)` 全部唯一，39 个已提交
  `(run_id, section_id)` 全部唯一；
* 5 个组合在拒绝 transaction 后复用了同一个 canonical section slot。
  这些拒绝 transaction revision 未推进，也不构成重复正式提交。

## 4. 按主题与风格

### 4.1 按主题

| 主题 | Attempts | Commit | 成功率 | Repair | Repair 成功 | Drift warning |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| reality_mystery | 15 | 13 | 86.67% | 9 | 7/9 (77.78%) | 5 |
| action_conflict | 15 | 13 | 86.67% | 9 | 7/9 (77.78%) | 3 |
| warm_relationship | 15 | 13 | 86.67% | 8 | 6/8 (75.00%) | 1 |

三个主题均为 13/15，没有单一主题独占失败；差异主要来自风格。

### 4.2 按风格

| 风格 | Attempts | Commit | 成功率 | Repair | Repair 成功 | Drift warning |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| literary | 9 | 9 | 100.00% | 5 | 5/5 (100.00%) | 0 |
| noir_cold | 9 | 6 | 66.67% | 8 | 5/8 (62.50%) | 0 |
| warm_healing | 9 | 9 | 100.00% | 1 | 1/1 (100.00%) | 0 |
| hot_blooded | 9 | 8 | 88.89% | 5 | 4/5 (80.00%) | 6 |
| classical_chapter | 9 | 7 | 77.78% | 7 | 5/7 (71.43%) | 3 |

`noir_cold` 是最弱风格：3 个拒绝、88.89% Repair 依赖。`literary` 和
`warm_healing` 均为 9/9，但 `literary` 仍有 55.56% Repair 依赖。

## 5. 45 节详细统计

`#` 是组合内 attempt 序号。拒绝后 canonical revision 不推进，因此下一
transaction 可以继续使用同一 canonical section slot。

| Theme | Style | # | Section | Commit | Contract | Repair | Patch | Revision | Tokens | Latency(s) |
| --- | --- | ---: | --- | --- | --- | --- | ---: | --- | ---: | ---: |
| reality_mystery | literary | 1 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 8,591 | 26.4741 |
| reality_mystery | literary | 2 | ch0001_s0002 | PASS | PASS | no | 0 | 2→3 | 5,991 | 21.9804 |
| reality_mystery | literary | 3 | ch0001_s0003 | PASS | PASS | no | 0 | 3→4 | 6,581 | 25.6210 |
| reality_mystery | noir_cold | 1 | ch0001_s0001 | REJECT | FAIL | yes | 1 | 1→1 | 8,610 | 27.0809 |
| reality_mystery | noir_cold | 2 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 9,208 | 29.0668 |
| reality_mystery | noir_cold | 3 | ch0001_s0002 | PASS | PASS | no | 0 | 2→3 | 6,163 | 21.2191 |
| reality_mystery | warm_healing | 1 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 10,641 | 35.2731 |
| reality_mystery | warm_healing | 2 | ch0001_s0002 | PASS | PASS | no | 0 | 2→3 | 7,030 | 26.7737 |
| reality_mystery | warm_healing | 3 | ch0001_s0003 | PASS | PASS | no | 0 | 3→4 | 7,998 | 33.9467 |
| reality_mystery | hot_blooded | 1 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 8,077 | 20.3006 |
| reality_mystery | hot_blooded | 2 | ch0001_s0002 | PASS | PASS | yes | 2 | 2→3 | 11,789 | 43.1625 |
| reality_mystery | hot_blooded | 3 | ch0001_s0003 | PASS | PASS | yes | 1 | 3→4 | 11,521 | 43.8520 |
| reality_mystery | classical_chapter | 1 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 9,479 | 27.3049 |
| reality_mystery | classical_chapter | 2 | ch0001_s0002 | REJECT | FAIL | yes | 1 | 2→2 | 9,596 | 26.3966 |
| reality_mystery | classical_chapter | 3 | ch0001_s0002 | PASS | PASS | no | 0 | 2→3 | 6,780 | 28.9251 |
| action_conflict | literary | 1 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 8,708 | 25.3906 |
| action_conflict | literary | 2 | ch0001_s0002 | PASS | PASS | yes | 1 | 2→3 | 9,406 | 26.8328 |
| action_conflict | literary | 3 | ch0001_s0003 | PASS | PASS | no | 0 | 3→4 | 6,400 | 25.9826 |
| action_conflict | noir_cold | 1 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 9,795 | 32.7630 |
| action_conflict | noir_cold | 2 | ch0001_s0002 | PASS | PASS | yes | 1 | 2→3 | 10,249 | 36.5630 |
| action_conflict | noir_cold | 3 | ch0001_s0003 | REJECT | FAIL | yes | 1 | 3→3 | 10,685 | 34.9945 |
| action_conflict | warm_healing | 1 | ch0001_s0001 | PASS | PASS | no | 0 | 1→2 | 6,143 | 29.8453 |
| action_conflict | warm_healing | 2 | ch0001_s0002 | PASS | PASS | no | 0 | 2→3 | 7,622 | 34.9512 |
| action_conflict | warm_healing | 3 | ch0001_s0003 | PASS | PASS | no | 0 | 3→4 | 9,169 | 47.7341 |
| action_conflict | hot_blooded | 1 | ch0001_s0001 | PASS | PASS | no | 0 | 1→2 | 5,375 | 20.6667 |
| action_conflict | hot_blooded | 2 | ch0001_s0002 | PASS | PASS | no | 0 | 2→3 | 7,033 | 33.9966 |
| action_conflict | hot_blooded | 3 | ch0001_s0003 | PASS | PASS | yes | 1 | 3→4 | 11,586 | 40.2564 |
| action_conflict | classical_chapter | 1 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 10,259 | 38.5613 |
| action_conflict | classical_chapter | 2 | ch0001_s0002 | REJECT | FAIL | yes | 1 | 2→2 | 10,249 | 29.8222 |
| action_conflict | classical_chapter | 3 | ch0001_s0002 | PASS | PASS | yes | 1 | 2→3 | 11,041 | 34.0668 |
| warm_relationship | literary | 1 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 8,866 | 25.0459 |
| warm_relationship | literary | 2 | ch0001_s0002 | PASS | PASS | no | 0 | 2→3 | 6,135 | 24.4432 |
| warm_relationship | literary | 3 | ch0001_s0003 | PASS | PASS | yes | 1 | 3→4 | 9,516 | 26.5808 |
| warm_relationship | noir_cold | 1 | ch0001_s0001 | REJECT | FAIL | yes | 1 | 1→1 | 8,513 | 19.5734 |
| warm_relationship | noir_cold | 2 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 8,886 | 26.7843 |
| warm_relationship | noir_cold | 3 | ch0001_s0002 | PASS | PASS | yes | 1 | 2→3 | 10,064 | 30.3936 |
| warm_relationship | warm_healing | 1 | ch0001_s0001 | PASS | PASS | no | 0 | 1→2 | 5,712 | 22.9118 |
| warm_relationship | warm_healing | 2 | ch0001_s0002 | PASS | PASS | no | 0 | 2→3 | 7,061 | 32.0994 |
| warm_relationship | warm_healing | 3 | ch0001_s0003 | PASS | PASS | no | 0 | 3→4 | 8,284 | 36.3459 |
| warm_relationship | hot_blooded | 1 | ch0001_s0001 | REJECT | FAIL | yes | 2 | 1→1 | 9,438 | 26.4543 |
| warm_relationship | hot_blooded | 2 | ch0001_s0001 | PASS | PASS | no | 0 | 1→2 | 6,095 | 31.4125 |
| warm_relationship | hot_blooded | 3 | ch0001_s0002 | PASS | PASS | no | 0 | 2→3 | 7,945 | 49.6853 |
| warm_relationship | classical_chapter | 1 | ch0001_s0001 | PASS | PASS | yes | 1 | 1→2 | 10,088 | 36.9654 |
| warm_relationship | classical_chapter | 2 | ch0001_s0002 | PASS | PASS | no | 0 | 2→3 | 6,796 | 38.5321 |
| warm_relationship | classical_chapter | 3 | ch0001_s0003 | PASS | PASS | yes | 1 | 3→4 | 11,055 | 33.8172 |

## 6. 失败案例

每个拒绝 transaction 的完整原始正文、Validator 历史、Repair Patch、修复后
正文和最终拒绝原因均保存在对应
`.tmp/stage1-full-matrix-20260726/runs/<theme>__<style>/rejections/`
JSON 中。

| Theme / Style / Attempt | Writer 原始问题 | Repair Patch | 最终结果 |
| --- | --- | --- | --- |
| reality_mystery / noir_cold / 1 | `END_STATE_WRONG_HOLDER`, `NARRATIVE_TOO_SHORT`；329 字 | 1×insert，目标 `end_1`，Patch Validator accepted | 352 字，仍 `NARRATIVE_TOO_SHORT`，REJECT |
| reality_mystery / classical_chapter / 2 | event incomplete/missing、wrong holder、too short；303 字 | 1×insert，目标 `handover_2`, `end_2`，accepted | 352 字，仍 `NARRATIVE_TOO_SHORT`，REJECT |
| action_conflict / noir_cold / 3 | `NARRATIVE_TOO_SHORT`；327 字 | 1×insert，accepted | 450 字，但 required event/end state 回归并触发 `REPAIR_REGRESSION`，REJECT |
| action_conflict / classical_chapter / 2 | `REQUIRED_EVENT_TARGET_MISMATCH`, `NARRATIVE_TOO_SHORT`；302 字 | 1×insert，目标 `handover_2`，accepted | 328 字，仍 `NARRATIVE_TOO_SHORT`，REJECT |
| warm_relationship / noir_cold / 1 | event incomplete/missing、`END_STATE_NOT_REACHED`、too short；299 字 | 1×insert，目标 `handover_1`, `end_1`，accepted | 342 字，仍 `NARRATIVE_TOO_SHORT`，REJECT |
| warm_relationship / hot_blooded / 1 | 新增 backstory、number、injury；565 字 | 2×delete，accepted | 仍有 `UNSUPPORTED_INJURY_ADDED`；556 字，REJECT |

失败分类：

* A / Writer：6 个拒绝的原始输出均存在确定性 Contract 问题；短文本和
  风格诱发的额外事实是主因。
* B / Repair：6 个失败 Repair 的 Patch Validator 均接受补丁，但最终
  Contract 未通过；其中 4 个未补足 450 字，1 个产生修复回归，1 个未清除
  injury 事实。
* C / Validator：本次没有人审或 LLM Judge，不能据此认定任何 false
  positive；没有发现 Validator 运行损坏。
* D / 长期记忆：未观察到确定性记忆丢失，但三节长度和选择代理不足以证明
  长期语义召回。

## 7. 长期稳定性分析

### 人物、知识、关系和物品

| 指标 | 数值 |
| --- | ---: |
| character continuity errors | 0 |
| knowledge boundary errors | 0 |
| relationship conflicts | 0 |
| item owner conflicts | 0 |
| item state conflicts | 0 |

以上为最终提交的确定性检查结果，不等价于人类文学审阅。

### Memory

| 指标 | 数值 |
| --- | ---: |
| 15 个组合最终 memory records 合计 | 115 |
| memory selected 合计 | 64 |
| 有 reference hit 的 attempts | 27/45 |
| 第 1→第 3 attempt 选择命中 | 12/12 eligible |

其余 3 个组合因首个 attempt 被拒绝，没有可用于该代理指标的首节新增
memory。该指标只证明 context selection 命中 ID，不证明语义引用质量。

### StoryThread

| 指标 | 数值 |
| --- | ---: |
| threads opened | 7 |
| threads advanced | 5 |
| threads resolved | 0 |
| max active threads | 2 |
| active threads >12 | 0 |
| 连续三节无主线推进 warning | 10/15 组合 |

没有无限开线，但 10 个组合没有检测到三节内主线推进，应作为后续修复重点。

### 风格稳定和敏感风险

* style contract pass：36/45；style drift warning：9/45。
* `hot_blooded` 观察到 `UNSUPPORTED_INJURY_ADDED` 4 次、
  `UNSUPPORTED_BACKSTORY_ADDED` 1 次。
* `classical_chapter` 未观察到新增历史人物/组织/日期的对应敏感码，但有
  2 个拒绝和 7/9 Repair 依赖。
* `warm_healing` 为 9/9、1/9 Repair，没有观察到删除主要冲突的敏感码。
* `noir_cold` 没有观察到时间压力弱化敏感码，但其 Contract/Repair 结果最差，
  因而不能仅凭该敏感码为 0 判定风格稳定。

### 重复和 Token 趋势

| Attempt ordinal | Mean tokens | Mean latency(s) | Repairs | Mean consecutive n-gram overlap |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 8,553.00 | 27.6408 | 12 | 0.0000 |
| 2 | 8,209.73 | 30.8545 | 7 | 0.0496 |
| 3 | 8,985.87 | 34.2281 | 7 | 0.1349 |

总体 mean opening overlap 为 0.0210，mean consecutive n-gram overlap 为
0.0615，最大值 0.3412。第三节平均 overlap 和 latency 上升；3 节窗口不足以
推断无限长程退化，但该趋势应保留为 Stage 1 风险信号。

## 8. 证据与可复现性

本地证据目录：

```text
.tmp/stage1-full-matrix-20260726/
```

证据计数：

| 证据 | 数量 |
| --- | ---: |
| combo report | 15 |
| per-section checkpoints | 45 |
| primary final samples | 45 |
| repair-before samples | 26 |
| repair-after samples | 26 |
| generation transactions | 45 |
| rejection evidence | 6 |

关键产物 SHA-256：

| 产物 | SHA-256 |
| --- | --- |
| `stage1-matrix.json` | `b51c821044a7800ec6e0449a578417871791f08402a7e3be44f070c59b288348` |
| `stage1-matrix.md` | `ca007964bbeb04b68142ab84a4ea354c57f9918ad4d9562d5df065dc3eaaffb8` |
| `analysis.json` | `db8ce513eaac02466288e7f2b601cbc54b89c9a5f79279a4cde8bca09bea7eba` |
| `analysis.md` | `48edb6025a485d43e8f342f8e84c65c994d9d830c1ecb5b32713780e632f959e` |

对全部 JSON/TXT/MD/LOG 执行 `coding.txt` API key 和 base URL 精确扫描：
0 命中；`CUSTOM_API_KEY`、`OPENAI_API_KEY`、`api_key` 和环境变量载荷字段：
0 命中。

证据边界：

| 类型 | 是否执行 |
| --- | --- |
| deterministic | 是 |
| recorded | 否 |
| real provider | 是 |
| human review | 否 |
| LLM judge | 否 |

本 Stage 1 只能说明：在这 45 次真实、每组合 3 次连续生成中，权威状态安全
Gate 阻止了错误提交；它没有证明文学质量、无限长篇稳定性或所有主题有效。
由于正式提交、Contract 和 Repair Gate 未通过，结论保持
`STAGE1_FAIL`。
