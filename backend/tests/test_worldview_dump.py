"""Phase 6 iter#XX — D1 世界观倾倒 (infodump) det tests."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]
for p in (_ROOT, _BACKEND):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import pytest

from quality_metrics.worldview_dump import worldview_dump_report


# ---------------------------------------------------------------------------
# Trigger: pure infodump > 300 chars
# ---------------------------------------------------------------------------


def test_pure_worldview_dump_triggers_d1() -> None:
    """300+ 字无对话/角色代词/动作动词 → D1."""
    # 一段纯世界观介绍, 无 他/她/我/对话 marks.
    text = (
        "蒸汽朋克都市铁影城建于第三纪元末. 这是一座由黄铜与铸铁构筑的多层环形城市, "
        "中心是巨大的钟楼塔. 钟楼底层为档案馆, 收藏自第一纪元以来的所有官方记录. "
        "档案馆的每一份卷宗都按编号归档, 编号系统遵循古老的天文历法. 第二层为外城"
        "守备处, 第三层为内城贵族区, 第四层为机械工厂, 第五层为蒸汽动力中枢. "
        "整座城市由二十四个区组成, 每个区由一名长老管辖. 长老议会每月初一在钟楼顶端"
        "集会, 议会由七位执政者主持. 执政者世袭, 每个家族对应一个区. 城市的能源完全"
        "来自地下温泉, 蒸汽通过管道输送到每一栋建筑. 管道的纹路是古老的螺旋形, 据说"
        "能引导能量流动. 整个城市被一道高耸的铁墙包围, 墙外是无人居住的荒原. 荒原上"
        "有古老的纪念碑, 上面刻着第一纪元统治者的名字. 据说纪念碑下藏着远古的秘密. "
        "城市的法律由议会颁布, 每条法律都用古老的符文记录在铜板上, 悬挂于钟楼塔的"
        "正厅之内."
    )
    report = worldview_dump_report(text)
    assert report.d1_triggered, (
        f"expected D1: longest={report.longest_dump_len}"
    )
    assert report.longest_dump_len >= 300


# ---------------------------------------------------------------------------
# Negative: normal narrative with dialogue/pronoun breaks
# ---------------------------------------------------------------------------


def test_narrative_with_dialogue_no_trigger() -> None:
    """正常 narrative 频繁有他/她/对话 → 不触发."""
    text = (
        "苏默走过那条狭窄的赤铜巷, 鞋底沾上灰色粉末. 守备官把卷宗递过来, 他点了点头. "
        "「编号 6-17、6-18、6-19. 」守备官说. 他没回答, 接过卷宗, "
        "塞进布袋. 他走出守备处, 雨已经停了. 远处的钟楼显出轮廓. 他想起昨夜读到"
        "的那一行字, 心里有些不安. 林雪应该已经在档案馆了, 他朝那个方向走去. 路上他遇见"
        "了几个穿灰袍的人, 都没说话. 他走得很快, 想尽快见到林雪. 档案馆的门半掩着. "
        "他推开门, 听见里面有翻动卷宗的声音. 林雪坐在桌前, 抬头看他."
    )
    report = worldview_dump_report(text)
    assert not report.d1_triggered, (
        f"narrative should not trigger: longest={report.longest_dump_len}"
    )


def test_short_dump_no_trigger() -> None:
    """长 narrative 但每段 < 300 字 dump → 不触发."""
    text = (
        "苏默走过那条狭窄的赤铜巷, 鞋底沾上灰色粉末. 铁影城的建筑层层叠叠, "
        "由黄铜与铸铁构筑, 钟楼塔耸立在中心, 整座城市笼罩在浓雾里. 他想起以前的事. "
        "守备官把卷宗递过来. 「编号 6-17、6-18、6-19. 」守备官说. 苏默点头. "
        "外城是机械工厂区, 内城是贵族区, 蒸汽管道沿着每条街道布设. 他没多问, 接过卷宗, "
        "塞进布袋. 雨已经停了."
    )
    report = worldview_dump_report(text)
    # 即便 worldview snippet 存在, 都 < 300 字, 不触发
    assert not report.d1_triggered


# ---------------------------------------------------------------------------
# Short text guard
# ---------------------------------------------------------------------------


def test_short_text_no_trigger() -> None:
    text = "铁影城建在山顶."
    report = worldview_dump_report(text)
    assert not report.d1_triggered


def test_empty_text_no_trigger() -> None:
    assert not worldview_dump_report("").d1_triggered


# ---------------------------------------------------------------------------
# Threshold
# ---------------------------------------------------------------------------


def test_custom_dump_min_len_threshold() -> None:
    """长 worldview. min_len=200 触发, min_len=1000 不触发."""
    text = (
        "蒸汽朋克都市铁影城建于第三纪元末. 这是一座由黄铜与铸铁构筑的多层环形城市, "
        "中心是巨大的钟楼塔. 钟楼底层为档案馆, 收藏自第一纪元以来的所有官方记录. "
        "档案馆的每一份卷宗都按编号归档, 编号系统遵循古老的天文历法. 第二层为外城"
        "守备处, 第三层为内城贵族区, 第四层为机械工厂, 第五层为蒸汽动力中枢. "
        "整座城市由二十四个区组成. 城市的能源完全来自地下温泉. 蒸汽通过管道输送. "
        "整个城市被高耸的铁墙包围, 墙外是无人居住的荒原. 荒原上有古老的纪念碑."
    )
    # min_len=200 → 触发
    assert worldview_dump_report(text, dump_min_len=200).d1_triggered
    # min_len=1000 → 不触发 (dump 段不够长)
    assert not worldview_dump_report(text, dump_min_len=1000).d1_triggered
