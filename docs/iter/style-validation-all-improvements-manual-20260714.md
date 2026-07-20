# 16 种小说风格双场景人工验收（2026-07-14）

## 结论

- 验证模型：`deepseek-v4-pro`，配置来自根目录 `coding.txt`；报告不含 API key。
- 场景：同一末世压力素材 16 篇 + 各风格适配题材 16 篇。
- 最终结果：**32/32 通过**。每篇均由 Codex 直接阅读正文后判定，不以 det PASS 代替人工判断。
- 主批次 semantic judge：关闭（`--no-judge`）；确定性规则恒跑，语义项由本报告人工复核。黑色幽默定向收口轮另启 semantic judge。
- 人工发现并修复 2 类自动验收盲点：首次 `screenplay_visual / mecha_pilot` 正文含“全景，”摄影景别指令；黑色幽默曾复刻契约示例句式，且 judge 一度用高总分掩盖“未独立成句”的硬缺项。已分别扩充 det、删除诱导示例、增加 judge blocking-issue 归一化并重跑。
- 最终黑色幽默双场景均经 semantic judge（9/10、无 blocking issue）和人工复核通过；其他样本用 det + 人工复核。

## 逐项结果

| 风格 | 压力场景 | 适配题材 | 人工结论 |
|---|---:|---:|---|
| literary | 1365 字 | 857 字 / scifi_soft_lit | 通过：具象物、动作承情绪、内心薄笔成立 |
| xianxia_fast | 835 字 | 829 字 / xianxia_cultivation | 通过：阻碍→出手→可用兑现→更近威胁完整 |
| colloquial_web | 1142 字 | 941 字 / system_cheat | 通过：现代口语、短段、信息直接 |
| hot_blooded | 1234 字 | 1290 字 / mecha_pilot | 通过：受阻后再冲、外放宣言、动作收尾 |
| somber | 1316 字 | 856 字 / republic_spy | 通过：3–5 段、具体物承载内心、无 run-on |
| lyrical_poetic | 1133 字 | 1255 字 / ancient_romance | 通过：感官落点、韵律与人物动作均在 |
| noir_cold | 918 字 | 1028 字 / republic_spy | 通过：短对白、物件推断、克制且无感叹号 |
| black_humor | 1284 字 | 1327 字 / workplace_drama | 通过：荒谬制度、认真照办、独立行政反讽、真实代价齐全 |
| warm_healing | 1225 字 | 869 字 / gourmet_culinary | 通过：修补/分享、关系温度变化、温柔动作收尾 |
| melancholic | 619 字 | 741 字 / campus_youth | 通过：人物持续在场、具体未遂愿望、无强行希望尾 |
| first_person_immersive | 948 字 | 872 字 / urban_mystery | 通过：“我”有限视点，未偷写门外人物心理 |
| ensemble_epic | 1309 字 | 827 字 / history_military | 通过：其他角色通过信物/军报进入因果链 |
| classical_chapter | 1032 字 | 741 字 / wuxia_jianghu | 通过：开头、章回标记、浅白文言句法、末段格式成立 |
| philosophical_meditative | 1177 字 | 874 字 / scifi_soft_lit | 通过：名字/时间命题落在地图、镜子与人物反应上 |
| screenplay_visual | 1254 字 | 842 字 / mecha_pilot | 通过（重跑后）：可拍动作与空间切换成立，无景别/摄影指令 |
| rough_grit_realism | 1420 字 | 1052 字 / apocalypse_wasteland | 通过：肉身负担、破损物、气味与疲惫具体，无伤痛美化 |

## 验收口径

1. 事实与角色知识边界没有被风格要求篡改。
2. 风格区别落实到视点、句式、段落、动作选择和收尾，而非只替换形容词。
3. 压力场景验证风格在不利题材下仍可辨认；适配题材验证它在合适素材下能发挥上限。
4. 对自动规则无法可靠判断的语义项（真实笑点、关系温度、悲而不滥、群像因果）逐篇人工阅读。

结构化原始结果见 `style-validation-all-improvements-20260714.json`。
