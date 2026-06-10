"""quality_spec — 集中维护小说质量规范 (novel_quality_critique_and_iteration.md)。

承载 7 类 (A-G) 触发条件、AI 套话黑名单、陈词滥调黑名单与"展示而非告诉"对照表,
统一暴露给 Narrator / NarrativeCritic / Writer 等所有 Agent。

设计原则:
* 单一真理源 - 任何 Agent 都不应在自己 prompt 里复制规范文本,而应引用本模块。
* 静态常量 - 规范在整篇创作中保持恒定,运行期不可变。
* 模块化片段 - 可按用途裁剪(完整版给 critic,精简版嵌入 narrator system prompt)。

不属于此模块的:
* 运行时滚动状态(最近三段开头句式、段落黑名单) - 由 TickState 维护
* 触发后的动作执行 - 由 NarrativeCritic 与 Orchestrator 协作
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["high", "medium", "low"]
CategoryCode = Literal["A", "B", "C", "D", "E", "F", "G"]


@dataclass(frozen=True)
class TriggerRule:
    """规范中的一条触发条件。"""

    code: str  # 如 "A1", "G6"
    category: CategoryCode
    description: str
    severity: Severity


# ---------------------------------------------------------------------------
# A-G 触发条件清单 (与 novel_quality_critique_and_iteration.md §1 对齐)
# ---------------------------------------------------------------------------

TRIGGER_RULES: tuple[TriggerRule, ...] = (
    # A. 重复性
    TriggerRule("A1", "A", "同段内同一实词 (动/名/形) 出现 ≥3 次, 且非刻意修辞", "medium"),
    TriggerRule("A2", "A", "连续 3+ 句采用相同句式 (长度相近、结构相同)", "medium"),
    TriggerRule("A3", "A", "同一意象 / 比喻在 2 章内出现 ≥3 次", "medium"),
    TriggerRule("A4", "A", "出现 AI 高频套话 (见 AI_CLICHE_BLACKLIST)", "high"),
    TriggerRule("A5", "A", "连续 3 段以同一种方式起笔 (动作 / 对话 / 心理 / 环境)", "medium"),
    TriggerRule("A6", "A", "连续 ≥2 段使用 总结性独白 收尾", "high"),
    TriggerRule("A7", "A", "段落开头句式与 最近三段开头句式 记录命中", "medium"),
    # B. 角色失真
    TriggerRule("B1", "B", "角色行为违背已确立的动机或性格, 且未交代变化", "high"),
    TriggerRule("B2", "B", "去掉名字后无法分辨是谁在说话", "high"),
    TriggerRule("B3", "B", "配角只为输出信息 / 推动主角, 无独立议程", "medium"),
    TriggerRule("B4", "B", "内心独白字数 > (行动 + 对话) 字数 × 1.5", "medium"),
    TriggerRule("B5", "B", "主角在场景内全程 正确, 未犯错、未困惑、未失态", "high"),
    TriggerRule("B6", "B", "不同角色面对同一事件反应趋同, 缺乏个体性", "medium"),
    TriggerRule("B7", "B", "全知反派: 反派的每一步算计都被旁白替读者揭穿", "medium"),
    # C. 情节
    TriggerRule("C1", "C", "重大转折前 1500 字内无任何铺垫 (细节 / 台词 / 气氛)", "high"),
    TriggerRule("C2", "C", "角色做出违背性格的选择, 仅为推动剧情", "high"),
    TriggerRule("C3", "C", "冲突通过巧合 / 突然出现的外力 / 新角色解决", "high"),
    TriggerRule("C4", "C", "整个场景内主角无外部障碍且无内部张力", "high"),
    TriggerRule("C5", "C", "关键事件 ≤100 字带过, 而琐碎场景 >1000 字", "medium"),
    TriggerRule("C6", "C", "章节结尾无悬念、无未解问题、无新欲望", "medium"),
    TriggerRule("C7", "C", "提前剧透: 叙述者暗示 她不知道这是最后一次……", "medium"),
    TriggerRule("C8", "C", "情节走向 安全: 每一步都在合理预期内, 无意外", "high"),
    # D. 描写
    TriggerRule("D1", "D", "单次背景设定 / 世界观倾倒 >300 字", "high"),
    TriggerRule("D2", "D", "形容词连续堆砌 ≥3 个修饰同一事物", "medium"),
    TriggerRule("D3", "D", "出现陈词滥调 (见 CLICHE_BLACKLIST)", "medium"),
    TriggerRule("D4", "D", "用 告诉 代替 展示: 直接说情绪, 而非通过动作 / 细节 / 对话 / 环境呈现", "high"),
    TriggerRule("D5", "D", "整段只有视觉描写, 缺另一种感官", "medium"),
    TriggerRule("D6", "D", "描述全是抽象 (美丽 / 宏伟 / 古老), 无可视化具体物", "high"),
    TriggerRule("D7", "D", "比喻的本体与喻体都是抽象 (如 愤怒像怒火)", "medium"),
    TriggerRule("D8", "D", "摄像机扫视 式描写, 缺乏视点人物的主观选择", "medium"),
    # E. 语言
    TriggerRule("E1", "E", "句子长度分布过于均匀 (标准差小), 缺乏节奏", "medium"),
    TriggerRule("E2", "E", "句式过分对仗工整 (典型 AI 腔)", "high"),
    TriggerRule("E3", "E", "POV 在同场景内无设计地切换", "high"),
    TriggerRule("E4", "E", "时态 / 人称混乱", "high"),
    TriggerRule("E5", "E", "角色对话与其档案中的 说话风格 不符", "high"),
    TriggerRule("E6", "E", "对话过度文绉绉, 缺口语该有的不规则 (打断 / 犹豫 / 跑题 / 错听)", "medium"),
    TriggerRule("E7", "E", "翻译腔: 密集出现 这是一个……的人、对于……来说", "medium"),
    # F. 结构
    TriggerRule("F1", "F", "与上一段在时间 / 空间 / 人物状态上出现矛盾", "high"),
    TriggerRule("F2", "F", "主线在本章中完全消失, 且非有意宕开", "medium"),
    TriggerRule("F3", "F", "已埋设伏笔 >5 章未触及、未提示", "medium"),
    TriggerRule("F4", "F", "新引入设定与既有设定冲突", "high"),
    TriggerRule("F5", "F", "主题先行: 角色 / 旁白直接宣讲价值观", "high"),
    TriggerRule("F6", "F", "章节切分位置缺乏戏剧理由 (只是 写够字数)", "medium"),
    # G. AI 特有失败模式
    TriggerRule("G1", "G", "过度圆满: 所有角色得到照顾, 无人付出真实代价", "high"),
    TriggerRule("G2", "G", "说教: 对读者直接宣讲价值观", "high"),
    TriggerRule("G3", "G", "过度解释: 事件刚发生即被旁白告知意义", "medium"),
    TriggerRule("G4", "G", "强行收尾: 章节末必须给 反思 / 升华 / 总结", "medium"),
    TriggerRule("G5", "G", "留白缺失: 重要瞬间不敢沉默, 必须填满文字", "medium"),
    TriggerRule("G6", "G", "安全感强迫: 回避不适、模糊、道德灰色、未解释", "high"),
    TriggerRule("G7", "G", "平衡癖: 每个立场 各打五十大板, 怕得罪任何一方", "medium"),
    TriggerRule("G8", "G", "完美修辞: 每句都精巧, 反而不像人写的", "medium"),
    TriggerRule("G9", "G", "配角戏份精确分配, 每个角色都有 亮相时刻, 像例行公事", "medium"),
)


# 快速索引
RULES_BY_CODE: dict[str, TriggerRule] = {r.code: r for r in TRIGGER_RULES}
HIGH_SEVERITY_CODES: tuple[str, ...] = tuple(
    r.code for r in TRIGGER_RULES if r.severity == "high"
)


# ---------------------------------------------------------------------------
# 黑名单 — AI 高频套话 (A4 自动触发)
# ---------------------------------------------------------------------------

AI_CLICHE_BLACKLIST: tuple[str, ...] = (
    "心中涌起一股",
    "不禁",
    "不由得",
    "仿佛",  # 含 仿佛……一般 / 仿佛……一样
    "似乎……又似乎",
    "他明白,这一切",
    "她明白,这一切",
    "无论如何",
    "无论怎样",
    "一切都将不同",
    "一切都变了",
    "这一刻,他知道",
    "这一刻,她知道",
    "的同时,也",
    "不仅仅是",
    "不只是",
    "在这个……的世界里",
    "命运的齿轮",
    "命运的安排",
    "时间仿佛静止",
    "思绪万千",
    "心潮澎湃",
    "百感交集",
    "五味杂陈",
    "千言万语",
    "缓缓地",  # 单段 ≥2 次才触发, 但提示给 LLM 直接禁用更安全
    "轻轻地",
    "静静地",
)


# ---------------------------------------------------------------------------
# 陈词滥调黑名单 (D3 自动触发)
# ---------------------------------------------------------------------------

CLICHE_BLACKLIST: tuple[str, ...] = (
    "月光如水",
    "星光璀璨",
    "阳光明媚",
    "微风拂面",
    "美丽动人",
    "风度翩翩",
    "英姿飒爽",
    "倾国倾城",
    "如释重负",
    "如临大敌",
    "如梦初醒",
    "脸色苍白",
    "脸色铁青",
    "面如死灰",
    "眼神坚定",
    "目光如炬",
    "双眼放光",
    "嘴角上扬",
    "嘴角微微一笑",
    "露出一抹微笑",
    "时光荏苒",
    "白驹过隙",
    "物是人非",
    "内心深处",
    "内心一颤",
    "心如刀绞",
    "鸦雀无声",
    "万籁俱寂",
)


# ---------------------------------------------------------------------------
# 展示 vs 告诉对照表 (D4 修订参考)
# ---------------------------------------------------------------------------

SHOW_DONT_TELL_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("他很愤怒", "他把茶杯放回桌上, 杯底磕出一声闷响, 茶水溢出来一点。"),
    ("她很疲惫", "她坐下时没有把椅子拉开, 膝盖直接撞在了桌沿。她没有揉。"),
    ("房间很乱", "一只袜子搭在台灯上。"),
    ("他爱她", "她说她不喝甜的。他记得。每次都记得。"),
    ("气氛紧张", "没人去拿桌上唯一一杯水。"),
)


# ---------------------------------------------------------------------------
# 多样性维度 (跨段评估)
# ---------------------------------------------------------------------------

OPENING_TYPES: tuple[str, ...] = ("动作", "对话", "环境", "心理", "时间标记", "物件特写")
SENSE_TYPES: tuple[str, ...] = ("视", "听", "嗅", "味", "触", "体感", "心理")
SENTENCE_RHYTHMS: tuple[str, ...] = ("全短句", "全长句", "长短交错", "突变节奏")
TIME_FEELS: tuple[str, ...] = ("实时推进", "跳跃", "倒叙嵌入", "慢镜")
VIEWPOINT_DISTANCES: tuple[str, ...] = ("紧贴角色", "拉远旁观", "物件视角")


# ---------------------------------------------------------------------------
# Prompt 片段 — 嵌入到生成 Agent 的 system prompt
# ---------------------------------------------------------------------------


def render_blacklist_block() -> str:
    """注入到 Narrator/Writer system prompt 的硬黑名单段落。"""
    ai_lines = "\n".join(f"  - {w}" for w in AI_CLICHE_BLACKLIST)
    cliche_lines = "\n".join(f"  - {w}" for w in CLICHE_BLACKLIST)
    return f"""\
# 硬性禁用清单 (出现即视为低质量, 必须重写)

## AI 高频套话 (A4 — 高严重度, 不得出现, 无例外)
{ai_lines}

## 陈词滥调 (D3 — 中严重度, 仅当场景真的需要才允许, 否则改写)
{cliche_lines}

## 替代策略
* 想写"仿佛 X" → 改为只在此场景成立的具体细节
* 想写"内心深处" / 直接说情绪 → 改为身体动作 + 周遭物件的反应 (展示而非告诉)
* 想写"缓缓地" / "静静地" → 删除副词, 用动词的具体性表达节奏
"""


def render_show_dont_tell_block() -> str:
    rows = "\n".join(
        f"  | {bad} | {good} |" for bad, good in SHOW_DONT_TELL_EXAMPLES
    )
    return f"""\
# 展示而非告诉 (D4 — 必读对照)

  | 不要写 (告诉) | 改为 (展示) |
{rows}

* 直接说情绪 ("他很愤怒") = D4 触发, 高严重度
* 身体动作 + 周遭物件的具体反应 = 正确路径
"""


def render_anti_pattern_block() -> str:
    """禁止段末总结升华 / 配角例行戏份等 AI 失败模式。"""
    return """\
# 段落禁忌 (G1-G9 失败模式)

* 不要在段末写"反思 / 升华 / 总结"句 (G4) — 允许在动作或细节中收尾, 让读者参与构建意义
* 不要写"过度圆满"段落 — 主角有所得必有所失 (G1, 代价原则)
* 不要让叙述者替读者揭穿反派算计 (B7, 全知反派)
* 不要在事件刚发生时立即解释其意义 (G3, 过度解释)
* 不要每个角色都恰好有"亮相时刻" (G9, 例行公事感)
* 不要回避不适、模糊、道德灰色 (G6, 安全感强迫)
* 不要每句话都精巧对仗 (G8, 完美修辞 → 不像人写)

# 句长节奏 (E1 防退化)
* 句长必须长短交错: 段落内至少出现 1 个 ≤5 字的短句 (动作 / 物件 / 名词)
* 长句 (>25 字) 与短句 (≤8 字) 必须穿插, 不要全部 12-20 字均匀长度
* 段落开篇或中段允许"突变节奏" — 一个 3-5 字的独立短句作为节拍标记
* 反例: "他抬起头。雨开始下。她转过身。" — 句长均匀, 触发 E1
* 正例: "他抬起头。雨。她没动, 只是把伞往身后藏了藏, 像是怕被人看见。" — 长短交错

# 段末禁忌 — 高严重度反例 (实测发现, 必须避免)
段末**绝不**允许出现以下"只有 X 和 Y"/"剩下 X"/"风声 / 呼吸"类升华:
* ❌ "...只有风声和自己的呼吸。"
* ❌ "...只剩下一片寂静。"
* ❌ "...剩下的, 只有夜色。"
* ❌ "...天地间, 仿佛只剩他一人。"
* ❌ "...时间仿佛静止了。"
这是规范 A6 (高严重度) 的典型实例 — 一旦命中, 整段判 REWRITE。

段末正确收尾方向 (任选一):
* ✓ 落在动作: "他把帽檐往下压了压。" / "他没回头。"
* ✓ 落在物件: "桌上的茶碗还摆着, 凉透了。" / "门闩没锁。"
* ✓ 落在对话: "走吧。"
* ✓ 落在细节: "袖口沾了一点泥。"

# 段首禁忌 — 主角名垄断
连续段落**不允许**全部以主角名起笔。即便 POV 紧贴主角, 也必须:
* 第 2 段改为环境 / 物件 / 第三方动作起笔, 主角名移到第 2-3 句出现
* 第 3 段改为时间标记 / 心理 / 对话起笔
* 主角名连续 3 段起笔 → A7 触发 (中严重度)
* 实测反例: 段1 "陈默坐在桌前"; 段2 "陈默从旧书店"; 段3 "陈默穿过两条街"
* 正例: 段1 "陈默坐在桌前"; 段2 "门外, 脚步声响起"; 段3 "雨停了一刻钟"

# 留白原则
* 同样能写明白或留白时, 留白更佳
* 重要瞬间允许沉默, 不必填满文字
"""


def render_diversity_block() -> str:
    """跨段多样性指令。"""
    return f"""\
# 跨段多样性要求

相邻段落必须在以下维度中至少一个有显著变化, 否则触发 A5 (中严重度):

* 段落起笔: {' / '.join(OPENING_TYPES)}
* 主导感官: {' / '.join(SENSE_TYPES)}
* 句长分布: {' / '.join(SENTENCE_RHYTHMS)}
* 时间感: {' / '.join(TIME_FEELS)}
* 视点距离: {' / '.join(VIEWPOINT_DISTANCES)}
"""


def render_full_critique_block() -> str:
    """完整 A-G 7 类触发条件清单 (供 NarrativeCritic 使用)。"""
    lines = []
    by_cat: dict[str, list[TriggerRule]] = {}
    for r in TRIGGER_RULES:
        by_cat.setdefault(r.category, []).append(r)
    cat_names = {
        "A": "重复性 (REPETITION)",
        "B": "角色失真 (CHARACTER)",
        "C": "情节 (PLOT)",
        "D": "描写 (PROSE)",
        "E": "语言 (LANGUAGE)",
        "F": "结构 (STRUCTURE)",
        "G": "AI 特有失败模式 (AI-PATTERN)",
    }
    for cat in "ABCDEFG":
        lines.append(f"\n## {cat}. {cat_names[cat]}\n")
        for r in by_cat[cat]:
            lines.append(f"  | {r.code} | {r.description} | {r.severity} |")
    return "# 质量不良判定清单 (A-G 共 50 项)\n" + "\n".join(lines)


def render_narrator_quality_block() -> str:
    """嵌入 Narrator system prompt 的精简质量段。"""
    return (
        render_blacklist_block()
        + "\n"
        + render_show_dont_tell_block()
        + "\n"
        + render_anti_pattern_block()
        + "\n"
        + render_diversity_block()
    )


def render_narrator_discipline_block() -> str:
    """v2.37 — Narrator system prompt 用的紧凑风格纪律段。

    设计动机: 此前 Narrator prompt 注入完整黑名单 (55 条触发规则 + 56 个禁词
    逐行列出), 负面约束在体量上压倒一切正向指导, 模型在"处处避雷"的压力下
    退缩到最安全的输出 — 无人物无对话的感官碎片, 恰是实测里"与标题脱节的
    意境流水"。完整清单仍由 NarrativeCritic 做确定性检测兜底 (render_full_*
    系列), Narrator 侧只保留高频踩雷项的紧凑提示。
    """
    ai_words = "、".join(AI_CLICHE_BLACKLIST)
    cliche_words = "、".join(CLICHE_BLACKLIST)
    return f"""\
# 风格纪律 (违反会被审稿层打回重写, 一次写对省两次返工)

1. 禁 AI 套话: {ai_words} — 这些词出现即返工。想写"仿佛 X", 改写为只在此
   场景成立的具体细节。
2. 慎用陈词: {cliche_words} — 除非场景真的需要, 否则换成自己的话。
3. 不直接报情绪 ("他很愤怒"❌) — 写身体动作 + 物件反应 ("他把茶杯磕回桌上,
   茶水溢出来一点"✓)。
4. 段末停在动作 / 物件 / 对话上 ("他没回头。"✓) — 不写反思、升华、总结句,
   不写"只剩下风声和呼吸"式收尾。
5. 相邻段落换一种起笔 (动作 / 对话 / 环境 / 物件 / 时间标记轮换), 不连续
   三段用主角名开头。
6. 胜利要有代价, 失败要有理由; 道德灰色和未解之谜可以留着不解释。
"""


# ---------------------------------------------------------------------------
# 决策矩阵 (NarrativeCritic 使用)
# ---------------------------------------------------------------------------


def decide_action(
    high_count: int, medium_count: int
) -> Literal["REWRITE", "REVISE", "POLISH", "RED_TEAM"]:
    """规范 §2.1 决策矩阵。

    | 触发情况 | 决策 |
    |----------|------|
    | ≥1 项高严重度 | REWRITE |
    | 0 项高 + ≥3 项中 | REVISE |
    | 0 项高 + ≤2 项中 | POLISH & ACCEPT |
    | 全部通过 | RED_TEAM 复查 |
    """
    if high_count >= 1:
        return "REWRITE"
    if medium_count >= 3:
        return "REVISE"
    if medium_count >= 1:
        return "POLISH"
    return "RED_TEAM"


__all__ = [
    "TriggerRule",
    "TRIGGER_RULES",
    "RULES_BY_CODE",
    "HIGH_SEVERITY_CODES",
    "AI_CLICHE_BLACKLIST",
    "CLICHE_BLACKLIST",
    "SHOW_DONT_TELL_EXAMPLES",
    "OPENING_TYPES",
    "SENSE_TYPES",
    "SENTENCE_RHYTHMS",
    "TIME_FEELS",
    "VIEWPOINT_DISTANCES",
    "render_blacklist_block",
    "render_show_dont_tell_block",
    "render_anti_pattern_block",
    "render_diversity_block",
    "render_full_critique_block",
    "render_narrator_quality_block",
    "render_narrator_discipline_block",
    "decide_action",
]
