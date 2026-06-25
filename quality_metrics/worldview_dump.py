"""Phase 6 iter#XX — D1 世界观倾倒 (infodump) det.

> Aligns with `docs/design/novel_quality_critique_and_iteration.md`:
>
> | code | trigger |
> | --- | --- |
> | D1   | 单次背景设定 / 世界观倾倒 >300 字 (high) |

## Strategy

寻找连续 ≥ 300 字的"纯背景描写" — 段内:
* 0 dialogue marks (无 「」 / "" / 「)
* 0 character pronouns (无 他 / 她 / 我 / 你 在前 200 字内 — 真 dump 不会
  快速回到角色视点)
* 0 action verbs (走 / 说 / 看 / 想 等)

Trigger 条件: 文本含一段 ≥ DUMP_MIN_LEN 字 无以上 3 类标记的 prose.

## False positive 防御

* 短文本 < 350 字 整段 skip (不可能有 300 字连续 dump)
* MIN_LEN 可调 (env DUMP_MIN_LEN, default 300)

## env knob

* WORLDVIEW_DUMP_ENABLE (default True)
* WORLDVIEW_DUMP_MIN_LEN (default 300)
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_DIALOGUE_MARKS = frozenset({"「", "」", "『", "』", "\"", '"', "“", "”", "'", "‘", "’"})
_CHARACTER_PRONOUNS = frozenset({"他", "她", "我", "你", "您", "咱", "俺", "他们", "她们"})
# Common action verbs — 跨场景普遍, 出现即说明 narrator 在写角色行动
_ACTION_VERBS = frozenset({
    # 物理动作 only — 来/去/上/下/应/说 等过多 FP (未来/过去/应该/来源 等).
    # POV/dialogue marks 已分开处理, 此处只承担"narrator 在写身体动作"信号.
    "走", "跑", "跳", "坐", "站", "躺", "蹲", "趴",
    "推", "拉", "扔", "拿", "握", "捏", "翻", "转", "弯",
    "摸", "碰", "触", "抓",
    "睡", "醒", "吃", "喝", "笑", "哭",
    # 按/压/举 — preposition / formal verb 偶发 FP (按编号 / 高压 / 举行), 不放
})

# 200 chars — 略低于 default dump_min_len 300, 但允许测试用 custom min_len=200.
# 实际生产 default min_len=300 仍是高 bar (无可能在 200 字内出现 300 字 dump).
_MIN_TEXT_LEN = 200
_DEFAULT_DUMP_MIN_LEN = 300


@dataclass(frozen=True)
class WorldviewDumpReport:
    text_length: int
    longest_dump_len: int
    dump_position: tuple[int, int]
    d1_triggered: bool
    d1_evidence: str

    def to_dict(self) -> dict:
        return {
            "text_length": self.text_length,
            "longest_dump_len": self.longest_dump_len,
            "dump_position": list(self.dump_position),
            "d1": {"triggered": self.d1_triggered, "evidence": self.d1_evidence},
        }


def _is_clean_dump_char(ch: str) -> bool:
    """字符不是 dialogue/pronoun/action — 即"背景描写"字符."""
    if ch in _DIALOGUE_MARKS:
        return False
    if ch in _CHARACTER_PRONOUNS:
        return False
    if ch in _ACTION_VERBS:
        return False
    return True


def worldview_dump_report(
    text: str,
    *,
    dump_min_len: int = _DEFAULT_DUMP_MIN_LEN,
) -> WorldviewDumpReport:
    """Scan text for longest 'clean' (no dialogue/pronoun/action) run.

    返回最长 run 信息 + 是否 ≥ dump_min_len → triggered.
    """
    if not text or len(text.strip()) < _MIN_TEXT_LEN:
        return WorldviewDumpReport(
            text_length=len(text or ""),
            longest_dump_len=0,
            dump_position=(0, 0),
            d1_triggered=False,
            d1_evidence="",
        )

    longest_len = 0
    longest_start = 0
    longest_end = 0
    cur_len = 0
    cur_start = 0
    for i, ch in enumerate(text):
        if _is_clean_dump_char(ch):
            if cur_len == 0:
                cur_start = i
            cur_len += 1
            if cur_len > longest_len:
                longest_len = cur_len
                longest_start = cur_start
                longest_end = i + 1
        else:
            cur_len = 0

    triggered = longest_len >= dump_min_len
    evidence = ""
    if triggered:
        snippet_start = max(0, longest_start)
        snippet_end = min(len(text), snippet_start + 60)
        snippet = text[snippet_start:snippet_end]
        evidence = (
            f"连续 {longest_len} 字无对话/角色代词/动作动词 "
            f"(位置 {longest_start}-{longest_end}). 起段: '{snippet}...'"
        )
    return WorldviewDumpReport(
        text_length=len(text),
        longest_dump_len=longest_len,
        dump_position=(longest_start, longest_end),
        d1_triggered=triggered,
        d1_evidence=evidence,
    )


__all__ = [
    "WorldviewDumpReport",
    "worldview_dump_report",
]
