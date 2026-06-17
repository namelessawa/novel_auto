"""主题 seed 注册表 — 覆盖主流网文类型.

每个 ThemeSeed 包含:
* ``key`` — 程序化标识 (小写 snake_case, CLI / API 用)
* ``label`` — 中文显示名 (UI 用)
* ``category`` — 大类聚合 (用于 matrix 分组展示)
* ``seed`` — 80-180 字 bootstrap seed, 直接喂给 ``bootstrap_world``

Seed 写作要求 (内部约束):
* 1-2 句, 给一个明确的视点角色 + 一个明确的世界悬念
* 时空具体 (年代 / 地点) 比抽象设定更好
* 留 1 个未解锚 (一件物 / 一段未明的话 / 一个倒计时)
* 不直接 spoil 主线 — narrator 会自由展开

只追加不修改 key 字段 — 改 key 等于打破 bootstrap CLI 兼容性.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeSeed:
    key: str
    label: str
    category: str
    seed: str


THEME_SEEDS: dict[str, ThemeSeed] = {
    # --- 玄幻 / 仙侠 / 奇幻 大类 -------------------------------------------
    "xianxia_cultivation": ThemeSeed(
        key="xianxia_cultivation",
        label="仙侠修真",
        category="fantasy_cn",
        seed=(
            "凡人少年陈砚在终南山外的药铺学徒, 某夜山下溪边捡到一片可吞食的"
            "玉简, 体内沉寂的灵脉骤然觉醒。一里外的青云宗山门, 守山长老的"
            "镇魔灯第一次跳了。"
        ),
    ),
    "high_fantasy_xuanhuan": ThemeSeed(
        key="high_fantasy_xuanhuan",
        label="玄幻冒险",
        category="fantasy_cn",
        seed=(
            "废墟王朝纪元六千年, 北境冰原裂缝中走出一名失忆的少女, 左掌刻着"
            "禁忌神纹, 身后跟着一头不会发声的青色幼狼。她唯一记得的, 是必须"
            "在第十三个月圆之夜赶到东海。"
        ),
    ),
    "western_fantasy": ThemeSeed(
        key="western_fantasy",
        label="西式奇幻",
        category="fantasy_cn",
        seed=(
            "教会执剑修女艾莎在边境小镇调查一桩'被偷走的影子'案, 镇上失踪的"
            "孩子一个个回家, 却再也没有自己的影子, 月光下走过, 地上空空荡荡。"
            "市长不让她进市政厅地下室。"
        ),
    ),
    "wuxia_jianghu": ThemeSeed(
        key="wuxia_jianghu",
        label="武侠江湖",
        category="fantasy_cn",
        seed=(
            "前朝最后一位锦衣卫指挥使的孙女沈砚清独自走进剑南道, 腰间挂着一柄"
            "无锋的祖传短刀, 怀里揣着一封发不出去的密信。客栈说书人提到她爹"
            "时压低了声音。"
        ),
    ),
    # --- 都市 / 现代 大类 --------------------------------------------------
    "urban_mystery": ThemeSeed(
        key="urban_mystery",
        label="都市悬疑",
        category="modern_cn",
        seed=(
            "失业的法医实习生周岭在出租屋发现前租客留下的加密硬盘, 解开"
            "第一层后只看到一段无声视频: 一只手把一枚校徽放进信封, 校徽属于"
            "他七年前死去的妹妹。"
        ),
    ),
    "modern_romance": ThemeSeed(
        key="modern_romance",
        label="现代言情",
        category="modern_cn",
        seed=(
            "建筑师林晚在上海老洋房改造项目里, 第三次撞见那位拒绝署名的设计"
            "顾问。他每次只留一张铅笔草图, 落款是七年前已注销的事务所章。"
            "今天的草图画着她未告诉任何人的卧室窗外那棵树。"
        ),
    ),
    "campus_youth": ThemeSeed(
        key="campus_youth",
        label="校园青春",
        category="modern_cn",
        seed=(
            "高三复读生苏屿第一次进新班级, 后排靠窗的位置上是去年校刊封面"
            "那个永远不交作业的学神。第一节晚自习的灯坏了, 教室半暗中, 学神"
            "把一支削得很尖的铅笔递过来。"
        ),
    ),
    "workplace_drama": ThemeSeed(
        key="workplace_drama",
        label="职场商战",
        category="modern_cn",
        seed=(
            "29 岁的项目经理夏宁被空降进一家即将被并购的家族广告公司, 第一"
            "天发现办公桌抽屉里有一封盖着前总监私章的辞职信, 日期是三天后, "
            "签名一栏是她的名字。"
        ),
    ),
    # --- 末世 / 科幻 大类 --------------------------------------------------
    "apocalypse_wasteland": ThemeSeed(
        key="apocalypse_wasteland",
        label="末世废土",
        category="speculative",
        seed=(
            "末日第七年, 北方避难城邦最后一台水净化器今晨彻底报废, 前工程"
            "师陆深必须在三天内带着三个收养的孩子穿越被变异兽群占据的旧"
            "公路, 找到传说中尚在运作的南方循环站。"
        ),
    ),
    "scifi_hard": ThemeSeed(
        key="scifi_hard",
        label="硬科幻",
        category="speculative",
        seed=(
            "土星轨道科研站值班的最后一日, 工程师齐安在切换电力的瞬间, 发现"
            "通讯天线背面多了一行手写刻字, 笔迹是他自己的, 但他从未上过站"
            "外。任务交接还有 17 小时。"
        ),
    ),
    "scifi_soft_lit": ThemeSeed(
        key="scifi_soft_lit",
        label="软科幻文学",
        category="speculative",
        seed=(
            "未来的城市每周可付费删除一段记忆, 删除师叶宁的第三百次预约客户"
            "递来的纸条上写着: '请删除上周二下午我没见到你的那段。' 系统记录"
            "里, 她上周二下午没有出诊。"
        ),
    ),
    "supernatural_horror": ThemeSeed(
        key="supernatural_horror",
        label="灵异恐怖",
        category="speculative",
        seed=(
            "民俗调查员邢午在湘西山村调研'回门夜'习俗时, 旅店老板娘第七次"
            "用同样的语气说同一句话: '今晚锁好门, 别看井里。'外面下着雨, 他"
            "的手电只剩半格电。"
        ),
    ),
    # --- 历史 / 古典 大类 --------------------------------------------------
    "republic_spy": ThemeSeed(
        key="republic_spy",
        label="民国谍战",
        category="historical",
        seed=(
            "1937 年深秋的上海法租界, 在英商烟草公司做会计的青年江望舒, 偶然"
            "在客户的雪茄盒夹层里发现一份用密语写成的电报抄件, 内容指向"
            "半月后即将发生的码头血案。"
        ),
    ),
    "ancient_romance": ThemeSeed(
        key="ancient_romance",
        label="古风言情",
        category="historical",
        seed=(
            "大昭三十年清明, 工部尚书独女谢知微从西域回京, 马车在城门口被"
            "拦下三回, 第三回拦车的是一身青衫的太常寺少卿, 他没说话, 只递"
            "了一只小小的旧梨木匣。"
        ),
    ),
    "history_military": ThemeSeed(
        key="history_military",
        label="历史军事",
        category="historical",
        seed=(
            "建安十三年冬, 江东水师小校陈渡奉命押送一批新铸的环首刀去夏口, "
            "船至赤壁江段, 北风骤变, 他在甲板上拦下一名穿着平民服色但腰间"
            "悬着曹军号牌的瘦削老者。"
        ),
    ),
    # --- 网文爆款 子类 (Phase 5+ 扩量) -----------------------------------
    "system_cheat": ThemeSeed(
        key="system_cheat",
        label="系统流爽文",
        category="modern_cn",
        seed=(
            "送外卖的大学生周野在暴雨夜被电流击中, 醒来听见一个机械女声: "
            "'宿主, 检测到时空裂缝, 签到系统强制绑定. 第一个签到地点: "
            "三里屯顶级私募基金 9 层 CEO 办公室, 倒计时 60 分钟.'"
        ),
    ),
    "transmigration_book": ThemeSeed(
        key="transmigration_book",
        label="穿书穿越",
        category="modern_cn",
        seed=(
            "网文编辑沈昭加班审稿到凌晨, 一行字突然把她吸了进去. 她睁眼"
            "发现自己穿成了刚审完那本 200 万字总裁文里第三章被原女主推下楼"
            "的炮灰女配, 而剧情正卡在'楼梯口'前三句对白."
        ),
    ),
    "mecha_pilot": ThemeSeed(
        key="mecha_pilot",
        label="机甲驾驶员",
        category="speculative",
        seed=(
            "第三次环太平洋裂缝战役第七年, 联军最后一台四代机甲'孤狼' "
            "重启需要双人神经同步. 唯一活下来能匹配的副驾, 是十年前被列为"
            "叛徒处决的前队长林越的双胞胎妹妹林夙."
        ),
    ),
    "showbiz_entertainment": ThemeSeed(
        key="showbiz_entertainment",
        label="娱乐圈流量",
        category="modern_cn",
        seed=(
            "选秀出道第三年的过气小生顾辞, 在直播间被一条全网热搜炸到掉粉"
            "百万 — 七年前他被代笔的那部短篇小说获了文学奖, 真作者刚现身,"
            "是当年说'你写得真好'的剧组场记."
        ),
    ),
    "gourmet_culinary": ThemeSeed(
        key="gourmet_culinary",
        label="美食技能",
        category="modern_cn",
        seed=(
            "祖传刀工的鱼生师傅阿杰被诊出味觉减退, 师父留下的最后嘱托是"
            "在闭店前做完一道叫'忘味'的怀石. 那道菜的方子写在一张老照片"
            "背面, 照片里的人他从来没见过."
        ),
    ),
    # --- 默认 (向后兼容: 原 bench_tick.py _DEFAULT_SEED) ------------------
    "steampunk_archive": ThemeSeed(
        key="steampunk_archive",
        label="蒸汽朋克悬疑 (默认)",
        category="speculative",
        seed=(
            "蒸汽朋克都市边缘的破败档案馆,一个失语的少女管理员每夜整理着"
            "不该存在的卷宗,卷宗里记录的未来事件正在一件件成真。"
        ),
    ),
}


def get_theme_seed(key: str) -> ThemeSeed:
    """Lookup with friendly error listing valid keys."""
    if key not in THEME_SEEDS:
        valid = ", ".join(sorted(THEME_SEEDS))
        raise KeyError(f"unknown theme key {key!r}. valid: {valid}")
    return THEME_SEEDS[key]


def list_theme_keys() -> list[str]:
    """Sorted list of theme keys for CLI --help / UI dropdown."""
    return sorted(THEME_SEEDS)
