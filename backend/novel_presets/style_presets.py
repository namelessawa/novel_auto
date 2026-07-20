"""风格 preset 注册表 — 让用户按个人口味挑写作风格.

每个 StylePreset 是 narrator 的"风格契约 addendum", 在 user_prompt 头部
追加 (与 style_anchors 同位置, 互相补充). 不改 SYSTEM (保 prefix cache).

约定:
* ``narrator_addendum`` 80-420 字, 直接告诉模型本作"怎么写"
* 不与 ``NARRATOR_SYSTEM_PROMPT`` 的硬约束冲突 (那些是所有风格共有的底线)
* 一句话能讲完风格特征 + 一句话讲读者预期 + 一句话讲禁区
* 版本、提示哈希与完整 snapshot 随 novel 持久化; 注册表升级不悄然改写旧作品

只追加不修改 key — 改 key 等于打破 user 已绑定 novel 的风格契约.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any


STYLE_PRESET_SCHEMA_VERSION = "2026-07-15.5"


@dataclass(frozen=True)
class StylePreset:
    key: str
    label: str
    description: str  # UI 介绍, 也写进 verdict 帮助对比
    narrator_addendum: str  # 拼到 user_prompt 头部的风格契约
    version: str = STYLE_PRESET_SCHEMA_VERSION
    # 长 prompt 尾部只重复这个短清单, 避免每 tick 把 addendum 原样再发一次。
    final_checklist: str = "保持本作句式、视点、节奏和收尾特征; 事实以素材为准。"
    # production / bench 共用的确定性验收规则 id。
    det_rules: tuple[str, ...] = ("no_meta_leak",)
    # 强格式不必每 tick 都拉满: 第 1 tick、每 N tick、或高重要性场景严格执行。
    strict_every_ticks: int = 1
    strict_importance: int = 7
    conflict_policy: str = (
        "事实与风格冲突时保留事实; 风格只改变叙述方式, 不新增事件、人物或设定。"
    )

    @property
    def prompt_hash(self) -> str:
        """可复现的完整风格契约 SHA-256。"""
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_snapshot(self) -> dict[str, Any]:
        """写入 TickState 的 JSON-safe 冻结契约。"""
        data = asdict(self)
        data["det_rules"] = list(self.det_rules)
        data["prompt_hash"] = self.prompt_hash
        return data

    @classmethod
    def from_snapshot(cls, payload: dict[str, Any]) -> "StylePreset":
        """从旧/新 TickState 恢复; 忽略派生字段与未来未知字段。"""
        allowed = {
            "key", "label", "description", "narrator_addendum", "version",
            "final_checklist", "det_rules", "strict_every_ticks",
            "strict_importance", "conflict_policy",
        }
        clean = {k: v for k, v in payload.items() if k in allowed}
        clean["det_rules"] = tuple(clean.get("det_rules") or ("no_meta_leak",))
        return cls(**clean)


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
            "强制四拍: ①前 80 字亮出具体阻碍; ②角色立刻出手/取物/作选择; ③同一场内"
            "兑现可用收益, 让障碍让步、局势反转或角色拿到能马上使用的优势; ④最后两句"
            "让更近的新威胁当场撞上来, 角色已经迎上去. 短句优先, 一段一个动作镜头, "
            "每次行动立刻给可见反馈. 素材没有境界/数值时不得编造等级, 改用武器、线索、"
            "路线或信息差制造爽点; 找到线索不算兑现, 必须在本段立刻用它打开门、逼退阻碍"
            "或抢先一步. 禁: 长段环境铺垫, 只调查不兑现, 最后一段写死物/远景, 内心反复挣扎.\n\n"
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
            "开场压缩过场, 立刻选择素材中最值得燃的一次出手、承诺或反抗. 本段必须有 "
            "至少两级升级动作 (受阻→再冲/倒下→起身/犹疑→出手), 并让呼吸、心跳、疼痛"
            "或血涌和动作同拍. 必须出现一句角色说出口的誓言/挑战和至少一个感叹号; "
            "感叹号不能代替行动. 结尾以宣言、冲锋或瞄准收束, 不得停在凝视、回忆、"
            "倒影等静态感伤画面. 禁: 平铺直叙, 过度内敛, 长段环境铺垫.\n\n"
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
            "长句优先但不准写成一整段只有一个句号: 全文分 3-5 段, 每段 3-6 句, "
            "单句建议 25-80 字、最多 120 字; 时常包含半句失语/被打断的句. 内心"
            "比例可达 40%, 但绑在具体物上 (一颗扣子, 一道光斑). 时间感拉长: "
            "几秒钟可写一整段. 禁: 300 字以上无句号的 run-on, 短句堆叠, 大动作链, "
            "段末钩子.\n"
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
            "强制三拍且顺序不可打乱: ①荒谬制度/礼节/工具提出一本正经的要求; ②角色用"
            "极认真、极实用的动作照办; ③独立写一句 narrator 干冷旁白揭穿其荒谬, 紧接"
            "一句落回饥饿、罚款、伤亡等真实代价. 干冷旁白不是标语、引号内公文或环境比喻, "
            "要让一本正经的行政措辞与现场后果发生逻辑错位，句法必须从本场景独立生长；"
            "不要写成‘无生命制度不受伤、执行者会受伤’的对偶模板. 交稿前必须能单独划出"
            "一句笑点; 划不出就重写. 禁: 谐音梗, "
            "卖萌, 羞辱受苦角色, 单靠尸体/脏污充当幽默.\n"
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
            "本段中心必须是照料、修补、分享或体谅这类小行动, 至少写出一次关系温度的"
            "变化和一句轻声对白/可辨认的互动. 用食物、衣物、信件、工具、颜色或气味"
            "承载温暖, 结尾落在一个小小缓解, 不留灾难钩子. 若素材含死亡、暴力或灾变, "
            "不得篡改事实, 但只把它压成远景压力/物件痕迹, 镜头留给人物怎样互相照顾; "
            "禁止正面描写尸体、伤害过程和死亡倒计时. 若简报中确实只有一人, 就写其"
            "照料活物、修补他人物件或回应既有善意, 并留下便条、食物、归位标记等"
            "收件人日后能认出的回执; 不能只修完就独自离开, 也不凭空安排相遇.\n"
            "**最低人物存在度**: 日常细节必须挂在视点角色动作上, 每段至少有角色动作, "
            "整段至少有 1 个关系/照料 beat, 收尾必须停在给予、分享、等待回应或被温柔"
            "接住的动作上. 禁: 急剧反转, 冷酷旁观, 大段冲突.\n\n"
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
            "**最低人物存在度 (硬约束)**: 第一段前两句内点出视点角色名字或代词; "
            "之后每段都要有该角色的名字/代词和一个具体动作, 不得连续两句只写环境. "
            "全文至少有 1 句克制的内心, 写他/她失去或无法得到的具体愿望. 交稿前若"
            "删掉环境仍看不见一个人在承受, 必须重写.\n\n"
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
            "本段严格聚焦指定视点角色；调度器会在连续段落间轮换参与者，"
            "所有感知、判断和不确定性都必须属于该视点，不得写另一人的内心或把视点"
            "抢回固定主角。至少一位其他已有重要角色 mention 1 次（当场动作 / "
            "信物 / 传闻 / 回忆任一均可），让读者感到群像同时在动。连续 2–3 段至少"
            "一次，在收尾 1–3 句用已有人物的动作、信物、未回应消息或未确认处境留出"
            "动向空白；可以落在当前"
            "视点，但必须指向另一既有人物尚未确认的动向或处境。不得为此凭空新造"
            "人名、遗物或传闻。素材只给称谓时继续用称谓，不另造姓名、旧债或搭档。"
            "禁：一对一对话占满整段。\n\n"
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
            "硬格式: 首句必须以'却说'或'且说'起; 中段必须自然出现'原来', 并多用"
            "'遂/便/乃/但见'连接动作; 末段首句必须逐字以'正是/却闻/只见'之一领起"
            "新变. 全文至少出现 4 个互不相同的章回标记. '言罢'只能紧跟真实对白, "
            "无人开口时不得使用. 首段前两句必须点出视点人物, 以后每段都要有其动作, "
            "不准写成无人物的古风天气报告. 不是给现代白话换几个古词: "
            "叙述句须有浅白文言的省略、倒装和四字节拍, 现代器物名可以保留, 句法必须有"
            "说书人口吻; 有对白一律用'道/曰/言罢', 不用现代对白标签. 禁: 连续三句"
            "现代新闻式白话, 网络词, 心理学术语, 用近义词逃避上述字面格式.\n\n"
        ),
    ),
    # --- Phase 5+ 扩量: 哲思 / 戏剧化 / 粗粝写实 --------------------------
    "philosophical_meditative": StylePreset(
        key="philosophical_meditative",
        label="哲思冥想 (博尔赫斯式)",
        version="2026-07-21.1",
        description=(
            "外象事件少, 时间感破碎, 角色行动是哲学命题的载体. 适合实验/哲思文学."
        ),
        narrator_addendum=(
            "# 本作风格契约 — philosophical_meditative\n"
            "外象事件可压缩, 重点是角色被某个概念 (镜像 / 时间 / 名字 / 选择) "
            "缠住的状态. 每个叙述单元必须推进一个可辨认的概念问题: 用 1-2 句"
            "说清问题, 落到一个具体物 (一面镜, 一张地图, 一个名字的发音变了), "
            "再由视点人物的选择或代价承接, 不作议论文结论. 时间感可错位 "
            "(此刻同时是十年后). 高压场景也不得退化成纯短对白和动作流: 至少保留"
            "一次“具体物→概念问题→人物选择”链, 同时完整写出事件结果, 不为哲思"
            "新增事实.\n"
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
            "无内心独白 — 心理用动作 + 表情显. 这是写作思维而非正文术语: 小说正文"
            "不得出现'镜头推向/镜头跟随/镜头切到/特写/画面定格'等摄影指令, 要让段落"
            "本身完成切换. 禁: 抽象比喻, 长心理段, 摄影机元语言.\n\n"
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


# 可观察的短清单与确定性规则集中维护。完整 addendum 负责语义，短清单只在
# prompt 尾部复核；规则 id 由 quality_metrics.style_contract 消费。
_STYLE_RUNTIME_CONTRACTS: dict[str, dict[str, Any]] = {
    "literary": {
        "final_checklist": "每段有具体物; 情绪落到动作/物件; 内心不超过两句。",
        "det_rules": ("no_meta_leak", "character_presence"),
    },
    "xianxia_fast": {
        "final_checklist": "严格段执行阻碍→出手→可用兑现→近威胁; 结尾必须是人物动作。",
        "det_rules": ("no_meta_leak", "active_ending"),
        "strict_every_ticks": 3,
    },
    "colloquial_web": {
        "final_checklist": "现代口语、短段短句、直说发生了什么; 不文绉绉。",
        "det_rules": ("no_meta_leak", "short_paragraphs"),
    },
    "hot_blooded": {
        "final_checklist": "严格段至少两级升级动作、一句说出口的誓言/挑战、一个感叹号，动作收尾。",
        "det_rules": ("no_meta_leak", "hot_blooded_observables", "active_ending"),
        "strict_every_ticks": 3,
    },
    "somber": {
        "final_checklist": "3-5 段，每段人物在场；单句不超120字，不写300字无句号。",
        "det_rules": ("no_meta_leak", "somber_structure", "character_presence"),
        "strict_every_ticks": 2,
    },
    "lyrical_poetic": {
        "final_checklist": "隐喻必须落到感官物；段落有呼吸；人物至少一个物理动作。",
        "det_rules": ("no_meta_leak", "character_presence"),
    },
    "noir_cold": {
        "final_checklist": "不用感叹号和情绪直报；短对白；每段有人物动作或对白。",
        "det_rules": ("no_meta_leak", "no_exclamation", "character_presence"),
    },
    "black_humor": {
        "final_checklist": "严格段依次写荒谬要求→认真照办→独立干冷反讽→真实代价；不羞辱受苦者，不复刻契约示例句式。",
        "det_rules": (
            "no_meta_leak", "character_presence", "black_humor_originality",
        ),
        "strict_every_ticks": 2,
    },
    "warm_healing": {
        "final_checklist": "写清照料/修补/分享及关系变化；不正写死亡暴力；以给予或回应收尾。",
        "det_rules": ("no_meta_leak", "warm_safety", "character_presence"),
        "strict_every_ticks": 2,
    },
    "melancholic": {
        "final_checklist": "首段前两句出现人物；每段有人物动作；写一个无法得到的具体愿望。",
        "det_rules": ("no_meta_leak", "character_presence"),
    },
    "first_person_immersive": {
        "final_checklist": "全篇用“我”的有限视点；不写他人内心，不切全知镜头。",
        "det_rules": ("no_meta_leak", "first_person"),
    },
    "ensemble_epic": {
        "final_checklist": "指定视点清楚且不抢回固定主角；另一既有角色以动作/信物/传闻/回忆在场；连续2–3段至少一次在收尾1–3句留人物动向，不凭空造人/物。",
        "det_rules": ("no_meta_leak", "character_presence"),
    },
    "classical_chapter": {
        "final_checklist": "严格段首句却说/且说，至少4种章回标记，末段正是/却闻/只见起；人物持续在场。",
        "det_rules": ("no_meta_leak", "classical_markers", "character_presence"),
        "strict_every_ticks": 3,
    },
    "philosophical_meditative": {
        "final_checklist": "至少一条可辨认概念问题；以具体物触发，由视点人物选择或代价承接；高压场景不丢事件结果。",
        "det_rules": ("no_meta_leak", "character_presence"),
    },
    "screenplay_visual": {
        "final_checklist": "可拍动作与对白推进；不用内心独白；正文不得出现摄影机指令。",
        "det_rules": ("no_meta_leak", "no_camera_meta"),
        "strict_every_ticks": 2,
    },
    "rough_grit_realism": {
        "final_checklist": "至少一个破损物或肉身负担；不美化伤痛、贫穷和战争。",
        "det_rules": ("no_meta_leak", "character_presence"),
    },
}

STYLE_PRESETS = {
    key: replace(preset, **_STYLE_RUNTIME_CONTRACTS[key])
    for key, preset in STYLE_PRESETS.items()
}


def get_style_preset(key: str) -> StylePreset:
    if key not in STYLE_PRESETS:
        valid = ", ".join(sorted(STYLE_PRESETS))
        raise KeyError(f"unknown style key {key!r}. valid: {valid}")
    return STYLE_PRESETS[key]


def list_style_keys() -> list[str]:
    return sorted(STYLE_PRESETS)
