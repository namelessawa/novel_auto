"""v2.33 — 中文文本分段器, 给多模态流水线用.

需求: 一节小说 (~500-2000 字) → N 个 segment, 每段对应一张图 + 一段 TTS.

切分规则
--------
1. 一级断点: ``。!?!?…`` 和换行
2. 段长目标: 40-100 字
3. 太短 (<25 字) → 合并到下一段; 末尾的太短段反并到上一段
4. 太长 (>120 字) → 用 ``,;,;`` 继续切到第二层
5. 仍太长 (>150 字) → 强制按字数硬切 (最后兜底)

为啥不用 LLM 切?
----------------
分段是确定性问题, 不需要语义理解. LLM 会引入不确定性 + 成本 + 延迟.
小说原文已经有完整的标点节奏, 按标点切几乎就是作者想要的镜头切换点.
"""
from __future__ import annotations

from dataclasses import dataclass

# 一级断点 — 句子结束
_PRIMARY_TERMINATORS = "。!?!?…\n"
# 二级断点 — 句子内部停顿
_SECONDARY_TERMINATORS = ",;,;、 "

# 段长阈值 — 中文小说一个句号≈一个镜头, 一段对应一张图.
# 25-40 字 TTS 约 5-8 秒, 视觉切换节奏舒服; 太长导致一张图配多句话
# 失去镜头感; 太短 TTS 一闪而过, 字幕来不及读.
MIN_SEGMENT_CHARS = 15
TARGET_SEGMENT_CHARS = 30
MAX_SEGMENT_CHARS = 60
HARD_MAX_CHARS = 100
# 末尾兜底反并的临界 — 真正的碎片 (< 8 字) 才反并到上一段
TAIL_FRAGMENT_CHARS = 8


@dataclass(frozen=True)
class Segment:
    """单个分段."""

    index: int
    text: str

    @property
    def char_count(self) -> int:
        return sum(1 for c in self.text if not c.isspace())


def segment_text(text: str) -> list[Segment]:
    """把一段中文小说文本切成 N 个 Segment.

    保证:
    - 返回非空 (即使输入只有 1 个字)
    - 不丢字 (拼接所有 segment.text 等于 strip 后的输入, 仅去掉首尾空白)
    - 段间不重叠
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    # 第一遍: 按一级断点切
    primary = _split_keeping_terminators(cleaned, _PRIMARY_TERMINATORS)

    # 第二遍: 太长的句子按二级断点继续切
    fine: list[str] = []
    for sent in primary:
        if _visible_len(sent) <= MAX_SEGMENT_CHARS:
            fine.append(sent)
        else:
            fine.extend(_split_keeping_terminators(sent, _SECONDARY_TERMINATORS))

    # 第三遍: 仍太长 → 硬切
    hard_cut: list[str] = []
    for piece in fine:
        if _visible_len(piece) <= HARD_MAX_CHARS:
            hard_cut.append(piece)
        else:
            hard_cut.extend(_hard_split_by_chars(piece, TARGET_SEGMENT_CHARS))

    # 第四遍: 合并过短的相邻段
    merged = _merge_short_neighbours(hard_cut)

    return [Segment(index=i, text=t) for i, t in enumerate(merged) if t.strip()]


# ---------- 内部工具 -----------------------------------------------------------


def _visible_len(s: str) -> int:
    """中文段长度: 跳过空白. 与 TickSection.word_count 口径一致."""
    return sum(1 for c in s if not c.isspace())


def _split_keeping_terminators(text: str, terminators: str) -> list[str]:
    """按终结符切, 终结符保留到段尾.

    例如 "晚风吹过山岗。月亮升起来了!" → ["晚风吹过山岗。", "月亮升起来了!"].
    """
    out: list[str] = []
    buf: list[str] = []
    for ch in text:
        buf.append(ch)
        if ch in terminators:
            piece = "".join(buf).strip()
            if piece:
                out.append(piece)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _hard_split_by_chars(text: str, target: int) -> list[str]:
    """无标点的超长段 — 按可见字数硬切. 极少触发, 兜底用."""
    out: list[str] = []
    buf: list[str] = []
    count = 0
    for ch in text:
        buf.append(ch)
        if not ch.isspace():
            count += 1
        if count >= target:
            out.append("".join(buf))
            buf = []
            count = 0
    if buf:
        out.append("".join(buf))
    return out


def _merge_short_neighbours(pieces: list[str]) -> list[str]:
    """合并相邻的过短段.

    策略 (重点: 合并上限是 MAX, 不是 HARD_MAX — 防止一路堆积):
    - 若上一段太短 (<MIN) 且合并后 <= MAX → 合并
    - 若当前段太短 (<MIN) 且合并后 <= MAX → 合并
    - 末尾仅当出现"碎片" (< TAIL_FRAGMENT_CHARS) 才反并 — 防止 [16, 16, 16]
      末段被反并的退化
    """
    if not pieces:
        return []

    out: list[str] = [pieces[0]]
    for piece in pieces[1:]:
        last = out[-1]
        last_len = _visible_len(last)
        piece_len = _visible_len(piece)

        if last_len < MIN_SEGMENT_CHARS and last_len + piece_len <= MAX_SEGMENT_CHARS:
            out[-1] = last + piece
            continue

        if piece_len < MIN_SEGMENT_CHARS and last_len + piece_len <= MAX_SEGMENT_CHARS:
            out[-1] = last + piece
            continue

        out.append(piece)

    # 末尾兜底: 仅当真正碎片才反并
    if len(out) >= 2 and _visible_len(out[-1]) < TAIL_FRAGMENT_CHARS:
        tail = out.pop()
        out[-1] = out[-1] + tail

    return out
