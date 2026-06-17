"""风格 preset 注册表 — 让用户按个人口味挑写作风格.

每个 StylePreset 是 narrator 的"风格契约 addendum", 在 user_prompt 头部
追加 (与 style_anchors 同位置, 互相补充). 不改 SYSTEM (保 prefix cache).

约定:
* ``narrator_addendum`` 80-220 字, 直接告诉模型本作"怎么写"
* 不与 ``NARRATOR_SYSTEM_PROMPT`` 的硬约束冲突 (那些是所有风格共有的底线)
* 一句话能讲完风格特征 + 一句话讲读者预期 + 一句话讲禁区

只追加不修改 key — 改 key 等于打破 user 已绑定 novel 的风格契约.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StylePreset:
    key: str
    label: str
    description: str  # UI 介绍, 也写进 verdict 帮助对比
    narrator_addendum: str  # 拼到 user_prompt 头部的风格契约


STYLE_PRESETS: dict[str, StylePreset] = {
    # --- 默认 (向后兼容现有 narrator 习惯) --------------------------------
    "literary": StylePreset(
        key="literary",
        label="描写细致 (文学性, 默认)",
        description=(
            "具象意象 + 内心薄笔, 节奏舒缓但每段必有实物. 适合文学读者."
        ),
        narrator_addendum=(
            "# 本作风格契约 — literary\n"
            "每段至少一个摄像机拍得到的具体物 (颜色/温度/质感). 情绪由身体"
            "动作和物件反应承载, 不直报. 内心 1-2 句白描即可, 贴着目标走. "
            "对白节制, 引号外配一个动作 beat. 禁: 大段心理独白, 抽象形容词堆叠.\n\n"
        ),
    ),
    # --- 快节奏 / 通俗网文 -------------------------------------------------
    "xianxia_fast": StylePreset(
        key="xianxia_fast",
        label="爽文快节奏 (网文动作向)",
        description=(
            "动作密集 + 即时反馈 + 战力等级化. 节奏快, 章节钩子强, 段末必留悬念."
        ),
        narrator_addendum=(
            "# 本作风格契约 — xianxia_fast\n"
            "短句优先, 一段一个动作镜头. 角色出招/出物/出选择必立刻有反馈 "
            "(对手反应/数值/旁观者). 段末必留一个钩子 (新威胁/新发现/对手未说完"
            "的半句话). 禁: 长段环境铺垫, 内心反复挣扎.\n\n"
        ),
    ),
    "colloquial_web": StylePreset(
        key="colloquial_web",
        label="大白话网文 (口语轻读)",
        description=(
            "用现代口语, 段落短, 信息密度高. 适合手机端碎片阅读."
        ),
        narrator_addendum=(
            "# 本作风格契约 — colloquial_web\n"
            "用现代日常口语写, 不避网络词. 每段 2-4 句, 一句一行也可. 角色心"
            "理直接说 ('他想这下完了'). 描写一句话带过, 重心在'发生了什么'. "
            "禁: 古典书面语, 长复句, 文绉绉.\n\n"
        ),
    ),
    "hot_blooded": StylePreset(
        key="hot_blooded",
        label="燃血热血 (高能高燃)",
        description=(
            "情绪外放, 关键节拍上情感和动作齐爆. 适合热血少年向题材."
        ),
        narrator_addendum=(
            "# 本作风格契约 — hot_blooded\n"
            "关键节拍 (出手/承诺/觉醒) 把情感与动作放大: 短句 + 感叹 + 物理"
            "节奏 (心跳/呼吸/血涌). 平淡过场可压缩. 段末常以一句宣言或一次"
            "瞄准收束. 禁: 平铺直叙, 过度内敛.\n\n"
        ),
    ),
    # --- 严肃 / 文学 / 反类型 ----------------------------------------------
    "somber": StylePreset(
        key="somber",
        label="沉郁严肃 (严肃文学)",
        description=(
            "长句多, 内心比例高, 节奏慢, 时间感被刻意拉长. 适合严肃文学读者."
        ),
        narrator_addendum=(
            "# 本作风格契约 — somber\n"
            "长句优先, 一段可含 4-7 句, 时常包含半句失语/被打断的句. 内心"
            "比例可达 40%, 但绑在具体物上 (一颗扣子, 一道光斑). 时间感拉长: "
            "几秒钟可写一整段. 禁: 短句堆叠, 大动作链, 段末钩子.\n"
            "**最低人物存在度**: 每段视点角色至少 1 个具体动作或半句话, "
            "内心独白也算角色存在. 不允许整段纯环境/纯氛围.\n\n"
        ),
    ),
    "lyrical_poetic": StylePreset(
        key="lyrical_poetic",
        label="抒情诗化 (诗意散文)",
        description=(
            "句子有节奏/韵律, 重感官与隐喻. 接近散文诗的小说."
        ),
        narrator_addendum=(
            "# 本作风格契约 — lyrical_poetic\n"
            "句子讲究内在节奏 (3+5 / 4+4 字组), 用通感和隐喻, 但每个隐喻必须"
            "落到一个具体感官触点. 段落像呼吸, 长短交错. 角色名可少出现, "
            "用代词或借物指代. 禁: 数据化描写, 直白叙述, 网络词.\n"
            "**最低人物存在度**: 抒情段也必须有视点角色的 1 个物理 beat "
            "(放下杯, 抬手, 半句话) — 不写纯景物诗.\n\n"
        ),
    ),
    "noir_cold": StylePreset(
        key="noir_cold",
        label="冷峻冷酷 (黑色硬派)",
        description=(
            "克制叙述, 拒绝感伤, 物件 > 心理. 适合悬疑/犯罪/谍战调性."
        ),
        narrator_addendum=(
            "# 本作风格契约 — noir_cold\n"
            "拒绝感伤化, 不用 '突然' / '心跳加速' 类直报情绪. 心理活动转化"
            "成动作: 嘴角动了一下, 烟掐灭. 信息克制 — 读者比角色多知 0.5 步. "
            "对白短, 一句话一个意图. 禁: 抒情段落, 内心独白, 感叹号.\n"
            "**最低人物存在度**: 信息克制不等于角色消失. 每段视点角色至少 "
            "1 个 micro-action 或 1 句对白, 纯环境镜头 ≤ 2 句.\n\n"
        ),
    ),
    "black_humor": StylePreset(
        key="black_humor",
        label="黑色幽默 (荒诞讽刺)",
        description=(
            "用讽刺与不协调制造笑点, 但底色是悲. 适合社会讽刺/反英雄题材."
        ),
        narrator_addendum=(
            "# 本作风格契约 — black_humor\n"
            "用 不协调 (高场合 + 低细节, 严肃语气 + 荒诞动作) 制造笑点. "
            "narrator 偶尔越位 1 句调侃, 但只调侃情景不调侃角色. 笑点之后"
            "立刻沉. 禁: 直接抖包袱, 谐音梗, 卖萌.\n"
            "**最低人物存在度**: 笑点附着在视点角色的具体反应/选择上, "
            "不写无角色的环境讽刺.\n\n"
        ),
    ),
    "warm_healing": StylePreset(
        key="warm_healing",
        label="治愈温馨 (慢生活)",
        description=(
            "低冲突, 高细节, 重日常质感与人际温度. 适合治愈/治愈系/慢生活题材."
        ),
        narrator_addendum=(
            "# 本作风格契约 — warm_healing\n"
            "冲突轻, 注意力放在日常细节 (做饭, 拆信, 雨后的味道). 角色之间"
            "用善意误会推进, 化解时不写大动作. 颜色和气味出现频率高. 禁: "
            "急剧反转, 死亡, 暴力, 大段冲突.\n"
            "**最低人物存在度**: 日常细节挂在视点角色的动作上 (她切开柠檬, "
            "不是 '柠檬被切开'). 每段至少 1 句对白或角色互动 beat.\n\n"
        ),
    ),
    "melancholic": StylePreset(
        key="melancholic",
        label="致郁忧伤 (悲怆基调)",
        description=(
            "整体压抑底色, 美但不温, 用细节积累悲. 适合悲剧 / 文学悲伤系."
        ),
        narrator_addendum=(
            "# 本作风格契约 — melancholic\n"
            "整体压抑, 但不靠惨剧堆量 — 用细节积累 (放凉的茶, 半句没说完的"
            "话, 永远关着的那扇门). 美感存在但不带温度. 角色克制. 禁: 强行"
            "希望尾, 救赎弧的明示, 笑场.\n"
            "**最低人物存在度**: 角色克制不等于角色缺席. 每段至少 1 个视点"
            "角色的具体动作 + 1-2 句内心 (写角色的痛, 不是世界的描写).\n\n"
        ),
    ),
    # --- 视角 / 结构变体 ---------------------------------------------------
    "first_person_immersive": StylePreset(
        key="first_person_immersive",
        label="第一人称沉浸 ('我' 视角)",
        description=(
            "用 '我' 写, 限制信息边界, 即时感受 > 全知描写. 沉浸感强."
        ),
        narrator_addendum=(
            "# 本作风格契约 — first_person_immersive\n"
            "用第一人称 '我' 写, 视点角色看不到的东西一律不写. 把 '心想' / "
            "'觉得' 等距离化词砍掉 — 直接写感受. 不全知, 不切镜头. 第二个人"
            "称代词指当下对话对象. 禁: 上帝视角描写, 跨角色心理, 时间错位.\n\n"
        ),
    ),
    "ensemble_epic": StylePreset(
        key="ensemble_epic",
        label="群像史诗 (多 POV)",
        description=(
            "多视角切换, 每段聚焦不同角色, 命运交织. 适合群像 / 史诗 / 群英类."
        ),
        narrator_addendum=(
            "# 本作风格契约 — ensemble_epic\n"
            "本段聚焦视点角色, 但其他重要角色至少 mention 1 次 (信物 / 传闻 / "
            "回忆), 让读者感到群像同时在动. 每段尾留一个'其他角色此刻可能在"
            "做什么'的空白. 禁: 一对一对话占满整段.\n\n"
        ),
    ),
    "classical_chapter": StylePreset(
        key="classical_chapter",
        label="章回体古典 (传统笔法)",
        description=(
            "近《红楼》《水浒》节奏, 偶用半文言, 段末偶有'欲知后事如何'式 cliff. 适合古风/历史."
        ),
        narrator_addendum=(
            "# 本作风格契约 — classical_chapter\n"
            "用浅白文言混现代书面语, 关键名词不避字面 (一灯, 一砚, 一刃). "
            "对白简练但用'道''说''言'区分. 段末偶有一行带 '只见''却闻' 的"
            "悬念转. 禁: 现代口语词, 网络词, 心理学化术语.\n\n"
        ),
    ),
    # --- Phase 5+ 扩量: 哲思 / 戏剧化 / 粗粝写实 --------------------------
    "philosophical_meditative": StylePreset(
        key="philosophical_meditative",
        label="哲思冥想 (博尔赫斯式)",
        description=(
            "外象事件少, 时间感破碎, 角色行动是哲学命题的载体. 适合实验/哲思文学."
        ),
        narrator_addendum=(
            "# 本作风格契约 — philosophical_meditative\n"
            "外象事件可压缩, 重点是角色被某个概念 (镜像 / 时间 / 名字 / 选择) "
            "缠住的状态. 一段允许 1-2 句抽象命题但必须落到一个具体物 (一面镜, "
            "一张地图, 一个名字的发音变了). 时间感可错位 (此刻同时是十年后).\n"
            "**最低人物存在度**: 哲学命题挂在视点角色的具体反应上 (停下, 重读, "
            "抬眼), 不写无角色的概念散文.\n\n"
        ),
    ),
    "screenplay_visual": StylePreset(
        key="screenplay_visual",
        label="戏剧化镜头 (剧本笔法)",
        description=(
            "段落即'镜头', 切换频繁, 视觉细节优先. 适合改编向 / 视觉强烈题材."
        ),
        narrator_addendum=(
            "# 本作风格契约 — screenplay_visual\n"
            "每段是一个'镜头': 开篇 1 句定景 (景别 + 主体 + 状态), 中间 1-2 句"
            "动作或对白, 段末 1 句'切换钩' (镜头将转向何处). 描述视觉可拍, "
            "无内心独白 — 心理用动作 + 表情显. 禁: 抽象比喻, 长心理段.\n\n"
        ),
    ),
    "rough_grit_realism": StylePreset(
        key="rough_grit_realism",
        label="粗粝写实 (反美化)",
        description=(
            "肉身重量感强, 拒绝优雅. 物体破损/气味/汗水/疲倦都正面写. 适合底层 / 战争 / 末世粗砺题材."
        ),
        narrator_addendum=(
            "# 本作风格契约 — rough_grit_realism\n"
            "拒绝美化 — 汗、油、伤口、霉味、肌肉酸都正面写. 物件残破才真实 "
            "(裂的杯沿, 缺角的桌, 鞋底磨穿). 角色累, 角色疼, 角色饿. 对白带"
            "口音/口语/粗话 (节制). 禁: 浪漫化伤痛, 美化贫穷, 抒情过场.\n\n"
        ),
    ),
}


def get_style_preset(key: str) -> StylePreset:
    if key not in STYLE_PRESETS:
        valid = ", ".join(sorted(STYLE_PRESETS))
        raise KeyError(f"unknown style key {key!r}. valid: {valid}")
    return STYLE_PRESETS[key]


def list_style_keys() -> list[str]:
    return sorted(STYLE_PRESETS)
