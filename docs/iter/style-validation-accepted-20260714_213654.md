# 全部小说风格修订与最终验收

- 日期：2026-07-14（Asia/Shanghai）
- 验证与审读：Codex 本人；未委派子代理
- 生成：真实 LLM，未使用 mock
- 配置来源：仓库根目录 `coding.txt`
- endpoint：`https://ark.cn-beijing.volces.com/api/coding/v3`
- model：`deepseek-v4-pro`
- 密钥：只注入进程环境；所有报告与代码扫描结果为 0 泄漏

## 最终结论

当前代码下 16 种已注册小说风格均有由我阅读全文并接受的真实样本：

- 真实生成：**16/16**
- 非空正文：**16/16**
- 运行错误：**0**
- 人工风格验收：**16/16 通过**
- 最终证据集正文：11,020 字
- 最终证据集 tick tokens：74,928（冷启动消耗不在 TickRuntime tracker 内）
- 整个修订循环 tick tokens：206,818

最终可审计证据集为 `style-validation-accepted-20260714_213654.json`。其中保存了每种风格全文、来源轮次、tokens、耗时、Agent 调用、人工 verdict 与确定性指标。

## 受控验证方法

首次只冷启动一个 `steampunk_archive` 世界，之后把同一份 tick 0 状态复制给所有风格。每份只修改 `TickState.style_preset_key`，因此角色、世界、题材和模型固定，差异主要来自风格契约。

验证时关闭 `WORLD_STALE_SKIP`，保证有正文可审；关闭 Narrator critic，直接检查 preset 对原稿的约束力。每个通过样本都在第 1 tick 生成，无需用后续 tick 掩盖空输出。

## 修订过程

### 基线

第一轮虽然运行层 16/16 成功，但人工风格判定只有 10 通过、1 勉强、5 不通过：

- `xianxia_fast`：快，但没有兑现爽点
- `hot_blooded`：没有燃点、宣言或动作升级
- `black_humor`：只有黑暗，没有有效幽默
- `warm_healing`：仍以前景死亡预告和死鱼为中心
- `melancholic`：色调正确，但视点人物消失
- `classical_chapter`：几乎仍是现代白话

### 修订 1：提高风格契约的末端权重

风格 addendum 原本只出现在长 user prompt 最前部，容易被后续场景、素材、伏笔与摘要稀释。现在保留头部块以维持缓存/语感结构，同时在最终 `# 写作指令` 前增加高优先级风格复核，并再次给出完整契约。

同时把上述 6 种语义风格改成可观察验收标准，例如热血必须有两级升级动作、誓言/挑战和主动收束；治愈在灾变素材下不得改事实，但必须把镜头转向照料、修补或分享。

### 修订 2：收紧仍会“擦边”的三种风格

- `xianxia_fast` 改为“阻碍—出手—兑现—迎敌”强制四拍，找到线索本身不算兑现。
- `black_humor` 改为“荒谬要求—认真照办—干冷旁白—真实代价”，必须能单独划出逻辑反讽句。
- `classical_chapter` 规定首句、中段、末段的章回标记位置，并要求浅白文言句法而非只换古词。

### 修订 3：处理全量回归中的随机回退

- `somber` 增加 3–5 段、单句最多 120 字和禁止 300 字 run-on，防止“长句”退化成整篇一个句号。
- `warm_healing` 要求善意有可识别回执；独角戏不能修完物件便独自离开。
- `classical_chapter` 增加人物存在度，并禁止无对白时误用“言罢”。
- `screenplay_visual` 明确“镜头”只是写作思维，正文不得出现“镜头推向/特写/画面定格”等元指令。

## 最终逐风格人工验收

| 风格 | 结果 | 最终样本的可辨识证据 |
| --- | --- | --- |
| `literary` | 通过 | 补丁、锈屑、油灯、铜板等具体物持续承载情绪，内心薄而有目标。 |
| `xianxia_fast` | 通过 | 识别混剂、铜网封漏、封口失守、立即奔赴码头，动作反馈与新威胁连续兑现。 |
| `colloquial_web` | 通过 | “有人但懒得喊”等口语判断、短段与直接目标形成手机网文读感。 |
| `hot_blooded` | 通过 | 五处感叹号，身体疼痛、震动、宣言和迎向防线的动作同步升级。 |
| `somber` | 通过 | 5 个慢段，管网低鸣、松扣、消失的半个“熔”字与父亲遗物把时间和悲痛拉长。 |
| `lyrical_poetic` | 通过 | 路灯“咳嗽”、铁皮“弯腰”等隐喻均落在声光触感，人物动作没有被纯景物吞掉。 |
| `noir_cold` | 通过 | 短对白、未点的烟、敲手指等微动作代替情绪直报，无感叹和抒情泛滥。 |
| `black_humor` | 通过 | “理论上不存在，所以配给煤不会短缺”形成清晰制度反讽，随后立即落回冬天无煤的代价。 |
| `warm_healing` | 通过 | 苏雅替老李缝袖口、递凉茶，老李接杯，关系温度完成闭环。 |
| `melancholic` | 通过 | 苏雅贯穿每段，铜板、酸雨和无法逃离的死亡日期积累悲意，没有强行希望尾。 |
| `first_person_immersive` | 通过 | “我”稳定出现 6 次，所有声音、气味与判断都受限于当前视点。 |
| `ensemble_epic` | 通过 | 何安从铜扣联想到苏雅，并决定找魏庄，三条人物线在一个动作里交汇。 |
| `classical_chapter` | 通过 | “却说—但见—原来—正是”位置与语义正确，苏雅每段有动作，末段确有新变。 |
| `philosophical_meditative` | 通过 | 自动机错位话语、迟到十年的时间与油膜反复合拢落在何安的具体等待上。 |
| `screenplay_visual` | 通过 | 告示、手、巷口、外墙、驳船依次切换，视觉可拍且没有摄影机元语言。 |
| `rough_grit_realism` | 通过 | 碎玻璃、糖浆、伤口、坏膝盖、煤灰和腐鱼都有肉身重量，不美化贫穷。 |

## 自动指标

最终 16 篇全部通过仓库现有零成本检查：

- E1 句长过度均匀：0/16
- D6 抽象描写过量：0/16
- D1 世界观倾倒：0/16
- C6 显式封口式结尾：0/16
- E7 翻译腔：0/16
- B4 内心独白失衡：0/16

多样性指标：

- char-4 distinct：0.9918
- consecutive char-4 overlap：0.0042
- MATTR-100：0.7348
- 平均句长：23.36
- 平均句长标准差：13.29

没有发现 16 个风格只是复用同一组句子或模板换词。

## 代码与测试

本次只修改 4 个跟踪文件：

- `backend/novel_presets/style_presets.py`
- `backend/agents/narrator_agent.py`
- `backend/tests/test_novel_presets.py`
- `backend/tests/test_narrator_prefix_cache.py`

验证结果：

- 全后端测试（系统环境）：1135 通过，4 个因 Anaconda 的 protobuf/chromadb 版本冲突失败
- 同 4 项用项目 `.venv` 复跑：4/4 通过
- 改动相关定向测试：34/34 通过
- ruff：通过
- `git diff --check`：通过（仅有 Git 的 LF→CRLF 工作区提示）

系统环境的 4 个失败均发生在 `chromadb → opentelemetry → protobuf` 导入阶段，缺少 `google.protobuf.internal.builder`；项目 `.venv` 使用 protobuf 6.33.5、chromadb 1.5.5，可以正常通过，不是本次代码回归。

## 原始运行证据

- 基线：`style-validation-codex-20260714_210537.json`
- 修订 1：`style-validation-revision1-20260714_212125.json`
- 修订 2：`style-validation-revision2-20260714_212607.json`
- 全量回归：`style-validation-final-20260714_212823.json`
- 修订 3：`style-validation-revision3-20260714_213654.json`
- 最终合并证据：`style-validation-accepted-20260714_213654.json`
