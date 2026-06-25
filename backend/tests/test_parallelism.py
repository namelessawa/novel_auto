"""Phase 6 iter#VV — E2 parallelism det tests."""

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

from quality_metrics.parallelism import parallelism_report


# ---------------------------------------------------------------------------
# Trigger cases
# ---------------------------------------------------------------------------


def test_classic_ai_parallelism_triggers() -> None:
    """4 对相邻同长同末字 → 强 E2 trigger."""
    text = (
        "他走了进来. 风停了, 雨停了. 灯灭了, 火灭了. 屋里静了, 心也静了. "
        "夜深了, 人散了. 远处那盏灯还亮着, 像一颗不肯落下的星."
    )
    report = parallelism_report(text)
    assert report.e2_triggered, f"counts: {report.parallel_pairs}/{report.total_clause_pairs}"
    assert report.parallel_pairs >= 3


def test_long_clauses_no_trigger() -> None:
    """clause 都 >12 字 → 不进对仗判定."""
    text = (
        "他终于走进了那扇紧闭的木门里面, "
        "里面的人却没有像他预想的那样转过头来. "
        "他于是默默地站在门口看了很久, "
        "屋里的灯光一直没有再亮起来过."
    )
    report = parallelism_report(text)
    assert not report.e2_triggered


# ---------------------------------------------------------------------------
# Negative cases — natural prose
# ---------------------------------------------------------------------------


def test_natural_prose_no_trigger() -> None:
    """正常 prose 没有大量对仗 → 不触发."""
    text = (
        "苏默走过那条狭窄的赤铜巷, 鞋底沾上灰色粉末. 守备官把卷宗递过来, "
        "手心出汗. 三份卷宗, 封蜡完好. 编号 6-17、6-18、6-19. "
        "他抬眼看了看墙上的钟, 时间还早."
    )
    report = parallelism_report(text)
    assert not report.e2_triggered


def test_one_pair_no_trigger() -> None:
    """仅 1 对对仗 < min_pairs → 不触发."""
    text = (
        "他走过那条街道, 雨水从瓦檐滴下来. 远处一辆马车驶过. "
        "他停下脚步等了一会儿. 风停了, 雨停了. 他望向远方那座钟楼. "
        "钟楼里没有声音传来. 街道上空无一人. 他继续往前走去."
    )
    report = parallelism_report(text)
    # 只 1 对 "风停了, 雨停了", < 3 不触发
    assert not report.e2_triggered


# ---------------------------------------------------------------------------
# Short text guard
# ---------------------------------------------------------------------------


def test_short_text_no_trigger() -> None:
    text = "风停了, 雨停了."
    report = parallelism_report(text)
    assert not report.e2_triggered


def test_empty_text() -> None:
    assert not parallelism_report("").e2_triggered


# ---------------------------------------------------------------------------
# Threshold
# ---------------------------------------------------------------------------


def test_custom_min_pairs_threshold() -> None:
    text = (
        "他走了进来. 风停了, 雨停了. 灯灭了, 火灭了. 屋里静了, 心也静了. "
        "夜深了, 人散了. 远处那盏灯还亮着, 像一颗不肯落下的星."
    )
    # 默认 min_pairs=3 → 触发
    assert parallelism_report(text, min_pairs=3).e2_triggered
    # min_pairs=10 → 不触发 (实际 4 对)
    assert not parallelism_report(text, min_pairs=10).e2_triggered


# ---------------------------------------------------------------------------
# Edge: same length but different last char → not parallel
# ---------------------------------------------------------------------------


def test_same_length_different_endings_no_trigger() -> None:
    """同长但末字不同 → 不算对仗."""
    text = (
        "他走进屋. 灯亮起, 夜显形. 屋里有人, 桌上有书. 他走过去, 翻开第一页. "
        "墙上的钟摆来回晃动, 发出滴答声响, 他听了一会儿继续读下去."
    )
    report = parallelism_report(text)
    # 即便 4 字 clause 多, 末字都不同 → 不触发
    assert not report.e2_triggered
