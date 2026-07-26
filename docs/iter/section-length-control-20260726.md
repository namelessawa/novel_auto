# Section Length Control + Style Compatible Expansion

## 1. 结论

`SECTION_LENGTH_FAIL`

最终代码完成了离线回归和 `action_conflict` 真实 Mini Matrix。真实矩阵为
9/15 正式提交，未达到 14/15 准入线；Contract、Repair 成功率和 Repair
依赖率也未过 Gate。因此不具备重新执行 45 节 Stage 1 Full Matrix 的资格，
本阶段没有运行完整 45 节。

## 2. 修改内容

### WritingPlan

- 新增服务端权威模型 `backend/story/writing_plan.py`。
- `SectionWritingPlanBuilder` 只从 NarrativeContract、EventExecutionPlan、
  SectionGoal 和 StyleContract 生成计划，Writer 不能修改结构。
- 固定生成 opening、development、conflict、resolution 四段预算，并携带
  required events、required end states、`min_chars` 和 `max_chars`。
- WritingPlan 放入受保护的 `narrative_contract` context slot，事务、预览 API
  和生成结果均保留该计划。

### StyleLengthContract

- 为 `literary`、`noir_cold`、`warm_healing`、`hot_blooded`、
  `classical_chapter` 分别定义允许与禁止的扩写维度。
- `noir_cold` 明确“冷峻不等于简短”；`hot_blooded` 禁止新增战争、死亡、
  敌人、伤势和伤亡数字；`classical_chapter` 禁止通过朝代、家族、官职、
  日期或新人物补长度。
- Writer prompt 直接呈现服务端四段预算、硬长度范围、事件与终态，并要求
  返回前内部核对非空白字符数。

### EXPAND Patch

- Repair Patch 新增 `expand` 类型、`target_chars` 和 `purpose`。
- `target_chars` 表示期望补量，`max_chars` 表示服务端硬上限；单 patch
  仍不超过 300 字，Repair 后正文仍必须落在 WritingPlan 的最终长度范围。
- EXPAND 只能扩写已有动作、环境、已有人物互动和已存在情绪；继续执行
  新人物、数字、日期、亲属、伤亡、伤势、背景、世界规则、历史背景和
  状态变更检查。
- Repair 顺序固定为：缺失/未完成事件、最终状态、删除非法事实、长度扩写、
  风格微调；只允许一次 Repair，没有增加 Writer 或 Critic。

### Validator

- 新增 `backend/story/section_length_validator.py`。
- 初稿和 Repair 后分别记录 chars、target、min/max、ratio、accepted 和
  violation code。
- 低于下限产生 `NARRATIVE_TOO_SHORT`，高于上限产生
  `NARRATIVE_TOO_LONG`；没有降低原 NarrativeContract、事件完成、实体或
  新增事实标准。

### UI

- Author Studio 预览 WritingPlan 四段结构、目标范围以及风格允许/禁止扩写项。
- Validation 区展示初稿与最终 Length Report，便于区分“初稿长度问题”和
  “Repair 后仍未达标”。

## 3. 离线结果

| 数据集 | 结果 | Repair | Regression | Bad commit / validator failure | Gate |
| --- | ---: | ---: | ---: | ---: | --- |
| 24 个历史冻结失败案例 | 24/24 recovered | 17/17 | 0 | bad commit 0 | 通过 |
| Stage 1 最终 6 个冻结失败案例 | 6/6 | 6/6 patch accepted | 0 | patch failure 0；validator failure 0 | 通过 |

证据文件：

- `.tmp/section-length-control-r3/offline-24.json` —
  SHA-256 `95fcf8367d33ff20098dca69072b13c245bbbb55757b71d72cf88e6ab812b165`
- `.tmp/section-length-control-r3/offline-six.json` —
  SHA-256 `cf549c02375ab02a97d3befd86a4e7608ef2622bf1d3d710d2975562e92387f8`

这两组是 recorded fixture 的确定性回放，不是真实 provider 新生成，也不等同于
人工文学质量审查。

## 4. 15 节真实 Mini Matrix

参数：

| 参数 | 值 |
| --- | --- |
| theme | `action_conflict` |
| styles | `literary,noir_cold,warm_healing,hot_blooded,classical_chapter` |
| sections per style | 3 |
| model | `glm-5.2` |
| desired length | 900 |
| accepted range | 900–1100 |
| seed | 20260726 |
| runtime rebuild | 每节 |

逐风格结果：

| 风格 | 尝试 | 提交 | Repair | Repair 成功 | 平均长度 | Token | 平均 latency | Provider error | 最终失败码 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| literary | 3 | 1 | 3 | 1/3 | 1244.67 | 35,043 | 41.7640s | 1 | `NARRATIVE_TOO_LONG`、`REQUIRED_EVENT_MISSING`、`REPAIR_REGRESSION` |
| noir_cold | 3 | 2 | 3 | 2/3 | 1147.00 | 38,637 | 52.5236s | 0 | `NARRATIVE_TOO_LONG` |
| warm_healing | 3 | 0 | 3 | 0/3 | 1207.00 | 34,957 | 42.3162s | 0 | `NARRATIVE_TOO_LONG` ×3 |
| hot_blooded | 3 | 3 | 3 | 3/3 | 1043.00 | 37,161 | 41.8831s | 0 | 无 |
| classical_chapter | 3 | 3 | 0 | 0/0 | 995.33 | 25,005 | 35.1098s | 0 | 无 |
| **合计** | **15** | **9** | **12** | **6/12** | **1127.40** | **170,803** | **42.7193s** | **1** | — |

聚合安全结果：

- hard fact error commits：0
- state conflict commits：0
- transaction data corruption：0
- illegal thread change commits：0
- evidenceless state delta commits：0
- required events completed：14/15
- required end states reached：15/15

Gate：

| 指标 | 要求 | 实际 | 结果 |
| --- | ---: | ---: | --- |
| 正式提交 | ≥14/15 | 9/15 | 未通过 |
| Contract | ≥93% | 60% | 未通过 |
| Repair success | ≥90% | 50% | 未通过 |
| 平均长度 | ≥850 | 1127.40 | 通过 |
| Repair dependency | ≤40% | 80% | 未通过 |
| 硬事实错误 | 0 | 0 | 通过 |
| 状态冲突 | 0 | 0 | 通过 |
| 事务损坏 | 0 | 0 | 通过 |
| Provider error | 0 | 1 | 未通过 |

长度从“普遍过短”转为部分风格越过上限，尤其是 `warm_healing`。这证明
WritingPlan/EXPAND 能提高长度，但当前 prompt 对 900–1100 上界的服从仍不稳定，
且 Repair 依赖率仍远高于目标。本次没有通过调低长度、删除失败样本或放宽事实安全
来制造通过结果。

真实证据文件：

- `.tmp/section-length-control-r3/real-mini/stage1-matrix.json` —
  SHA-256 `38c43a12fa280271445a8294f14c862b4f98d28a44ef6abc28566fab93aa3dd7`
- `.tmp/section-length-control-r3/real-mini/stage1-matrix.md` —
  SHA-256 `73533518ac1967db7ed2a19ab9faee570d2d15c64a51be21596a3151ee64ef95`

## 5. Stage 1 资格判断

不允许重新执行 45 节。Mini Matrix 未通过硬 Gate，因此
`3 themes × 5 styles × 3 sections` 没有启动，也没有消耗额外的 45 节真实调用。

## 6. 验证

- 后端全量：1506 passed，1 个既有 Starlette deprecation warning。
- Section Length / Repair 定向：34 passed。
- 前端 Author UI：14 passed。
- 前端生产构建：通过。
- Python compile：通过。
- `git diff --check`：通过。

## 7. 证据边界

| 类型 | 本阶段状态 | 能证明什么 |
| --- | --- | --- |
| deterministic | 有 | 长度、Contract、事件、终态、Patch、状态和事务门禁的机器判定 |
| recorded | 有 | 24+6 冻结失败案例在当前代码上的离线回放 |
| real provider | 有 | glm-5.2 对固定主题 5×3 的真实生成与真实 Repair 表现 |
| human review | 无 | 未做人工文学质量评分 |
| LLM judge | 无 | 未使用额外模型做质量裁判 |

即使 15 节全部通过，也不能推出长篇稳定；本次 15 节本身未通过，因此更不能对
长程主题稳定、背景一致或文学质量作扩大结论。
