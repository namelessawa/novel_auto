"""Phase 6 iter#UU — D5 single-sense det tests."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]
for p in (_ROOT, _BACKEND):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


from quality_metrics.sense_diversity import sense_diversity_report  # noqa: E402


# ---------------------------------------------------------------------------
# Trigger cases — pure visual stream
# ---------------------------------------------------------------------------


def test_pure_visual_triggers_d5() -> None:
    """全是视觉关键词 (≥200 字, 视觉 ≥5, 其他 0) → D5."""
    text = (
        "他望见远处的灰色高山, 山影在暮色里若隐若现. 红色的夕阳挂在山尖, "
        "映出深紫的天空. 山下的影子拉得很长. 他看着那片广阔的金黄草地, "
        "白色的鸟在天空盘旋. 河水反射出蓝色的天空, 平静无波. 远处的高楼"
        "亮起一盏盏黄色的灯, 像撒了一地的星. 他注视良久, 看见月亮升起来,"
        "白色的圆盘照亮整片大地. 暗影渐渐拉长, 天空变成了深蓝色."
    )
    report = sense_diversity_report(text)
    assert report.d5_triggered, f"expected D5: {report.counts}"
    assert "视觉" in report.d5_evidence


# ---------------------------------------------------------------------------
# Negative cases — has other senses
# ---------------------------------------------------------------------------


def test_visual_plus_audio_no_trigger() -> None:
    """视觉 + 听觉 → 多元, 不触发."""
    text = (
        "他望见远处的灰色高山, 山影在暮色里若隐若现. 风嘶吼着穿过山谷, "
        "卷起阵阵呜咽. 红色的夕阳挂在山尖, 映出深紫的天空. 远处传来一声鸟鸣, "
        "在群山间回荡. 他看着那片广阔的金黄草地. 风声越发响亮. 暗影渐渐拉长."
    )
    report = sense_diversity_report(text)
    assert not report.d5_triggered
    assert report.counts.get("audio", 0) > 0


def test_visual_plus_touch_no_trigger() -> None:
    text = (
        "他望见远处的灰色高山, 山影在暮色里若隐若现. 风很凉, 吹得脸颊"
        "冰冷, 像被人按了一下. 红色的夕阳挂在山尖, 映出深紫的天空. "
        "他摸了摸冻僵的耳朵, 又把双手握在一起取暖. 看着那片广阔的金黄草地. "
        "远处一片暗影. 寒意从地里钻上来, 一点一点贴上他的脊背."
    )
    report = sense_diversity_report(text)
    assert not report.d5_triggered
    assert report.counts.get("touch", 0) > 0


def test_visual_plus_smell_no_trigger() -> None:
    text = (
        "他望见远处的灰色高山, 山影在暮色里若隐若现. 焦味从山下飘上来, "
        "夹着血腥的气味. 红色的夕阳挂在山尖, 映出深紫的天空. 他看着"
        "那片广阔的金黄草地. 一阵草味扑面而来, 混着潮湿的土味. 远处一片"
        "暗影. 烟味越发浓重, 呛得他咳嗽起来."
    )
    report = sense_diversity_report(text)
    assert not report.d5_triggered
    assert report.counts.get("smell", 0) > 0


# ---------------------------------------------------------------------------
# Short text guard
# ---------------------------------------------------------------------------


def test_short_text_no_trigger() -> None:
    """< 200 字 → 不查."""
    text = "他看见红色, 看见黄色, 看见黑色, 看见白色, 看见灰色."
    report = sense_diversity_report(text)
    assert not report.d5_triggered


def test_empty_text_no_trigger() -> None:
    assert not sense_diversity_report("").d5_triggered


# ---------------------------------------------------------------------------
# Threshold knob
# ---------------------------------------------------------------------------


def test_below_visual_min_no_trigger() -> None:
    """长 narrative 但视觉 < 5 → 不触发 (虽然其他 0)."""
    text = (
        "他静静地走着, 路上没有遇到任何人. 街道空空荡荡, 角落里堆着杂物. "
        "他想起以前发生的事, 觉得有些感慨. 时间过得很快, 一晃就是十年. "
        "现在的他, 已经不是当年的他了. 走着走着, 不知不觉到了目的地. "
        "他停下脚步, 调整心情, 准备进去."
    )
    report = sense_diversity_report(text)
    # 这段几乎没视觉 keyword, 不触发
    assert not report.d5_triggered


def test_custom_visual_min_threshold() -> None:
    """长文 28 视觉. vm=5 触发, vm=50 不触发."""
    text = (
        "他望见远处的灰色高山. 山影若隐若现. 红色的夕阳挂在山尖, 映出深紫"
        "的天空. 他看着那片广阔的草地. 白色的鸟在飞过去. 暗影拉长. 远处一片"
        "深色的丘陵. 月亮升起来, 照亮大地. 天空变成了深蓝. 黄色的灯光在远处"
        "亮起, 像一颗颗星点缀着山脚."
    )
    # vm=5 默认: visual count 28 → trigger
    r5 = sense_diversity_report(text, visual_min=5)
    assert r5.d5_triggered, f"vm=5: counts={r5.counts}"
    # vm=50 → count 28 < 50, 不 trigger
    r50 = sense_diversity_report(text, visual_min=50)
    assert not r50.d5_triggered, f"vm=50: counts={r50.counts}"
