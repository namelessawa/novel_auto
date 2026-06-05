"""SectionCloser — v2.24 新增 Agent #10。

> 续写一节 = 推 N 个 tick 直到 SectionCloser 同意切节。
> 它的判定决定每节字数稳定性,以及 Narrator 沉默 tick 的补叙。

三合一职责
----------
1. **切节判定** (``decide_close``): 接收当前累积的 narrative 文本 + 沉默 tick
   摘要 + tick 数, 返回 ``should_close: bool``。判定条件:
   - 硬条件: ``tick_count >= MAX_TICKS_PER_SECTION`` (硬上限兜底)
   - 软条件: ``words >= TARGET_WORDS * 0.8`` AND LLM 判"内容闭合"
   - 字数下限保护: ``words < MIN_WORDS_PER_SECTION`` 时拒绝切

2. **补叙生成** (``draft_closure_supplement``): 用户选择"保留 Narrator 沉默",
   切节时把这一节里被跳过的 tick (only ``tick_summary_for_record``) 总结成
   一段不超过 200 字的收束, 贴在节尾。无沉默 tick 则返回空串。

3. **标题生成** (``generate_title``): 4-12 字小标题。复用 pipeline/engine.py
   _generate_section_title 的清洗逻辑。

阈值默认 (可通过环境变量覆盖)
-----------------------------
- TARGET: ``SECTION_TARGET_WORDS`` (默认 3000)
- MIN:    ``SECTION_MIN_WORDS`` (默认 2400)
- MAX_TICKS: ``SECTION_MAX_TICKS`` (默认 30)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

from nf_core.json_utils import strip_code_fence
from nf_core.llm_client import llm_client

logger = logging.getLogger(__name__)


# ---- 阈值 (env 可覆盖) ------------------------------------------------------


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("env %s=%r 解析失败, 回退默认 %d", name, raw, default)
        return default


def section_target_words() -> int:
    return _int_env("SECTION_TARGET_WORDS", 3000)


def section_min_words() -> int:
    return _int_env("SECTION_MIN_WORDS", 2400)


def section_max_ticks() -> int:
    return _int_env("SECTION_MAX_TICKS", 30)


# ---- 数据契约 ---------------------------------------------------------------


@dataclass(frozen=True)
class SilentTickRecord:
    """Narrator 沉默时 (should_narrate=False) 留下的 tick 摘要。

    仅记录被跳过的 tick — 已被 Narrator 写出 narrative 的 tick 不在此列。
    SectionCloser 切节时用这些摘要写补叙段。
    """

    tick: int
    summary: str
    skip_reason: str = ""


@dataclass(frozen=True)
class SectionClosureDecision:
    """``decide_close`` 输出。"""

    should_close: bool
    reason: str
    words: int
    tick_count: int


@dataclass(frozen=True)
class SectionClosureOutput:
    """``close_section`` 输出。"""

    title: str
    closure_supplement: str
    final_content: str
    word_count: int
    consumed_silent_ticks: list[int] = field(default_factory=list)


# ---- 主类 -------------------------------------------------------------------


class SectionCloser:
    """切节决策 + 补叙 + 标题三合一。

    所有 LLM 调用失败都走确定性 fallback — 此 Agent 不允许阻塞续写任务。
    """

    def __init__(
        self,
        target_words: int | None = None,
        min_words: int | None = None,
        max_ticks: int | None = None,
    ) -> None:
        self.target_words = target_words if target_words is not None else section_target_words()
        self.min_words = min_words if min_words is not None else section_min_words()
        self.max_ticks = max_ticks if max_ticks is not None else section_max_ticks()
        if self.min_words > self.target_words:
            raise ValueError(
                f"min_words ({self.min_words}) 不能大于 target_words ({self.target_words})"
            )

    # ------------------------------------------------------------------
    # 1) 切节判定
    # ------------------------------------------------------------------

    async def decide_close(
        self,
        *,
        narrative_text: str,
        tick_count: int,
        novel_title: str = "",
    ) -> SectionClosureDecision:
        words = _count_words(narrative_text)

        # 硬上限优先 — 即使内容半截也要切, 否则一节字数失控
        if tick_count >= self.max_ticks:
            return SectionClosureDecision(
                should_close=True,
                reason=f"tick_count={tick_count} >= max={self.max_ticks} (硬上限)",
                words=words,
                tick_count=tick_count,
            )

        # 字数下限保护 — 不到 min 一律不切, 不浪费 LLM 调用
        if words < self.min_words:
            return SectionClosureDecision(
                should_close=False,
                reason=f"words={words} < min={self.min_words} (字数下限)",
                words=words,
                tick_count=tick_count,
            )

        # 进入软判定区间 — 询问 LLM 内容是否闭合
        is_closed, llm_reason = await self._llm_judge_closure(
            narrative_text=narrative_text,
            words=words,
            tick_count=tick_count,
            novel_title=novel_title,
        )
        if is_closed:
            return SectionClosureDecision(
                should_close=True,
                reason=f"words={words} 达标, LLM 判定内容闭合: {llm_reason}",
                words=words,
                tick_count=tick_count,
            )
        # 字数超过 target * 1.2 时, 即使 LLM 觉得没闭合也强行切 — 防止冗长
        upper = int(self.target_words * 1.2)
        if words >= upper:
            return SectionClosureDecision(
                should_close=True,
                reason=f"words={words} >= upper={upper} (上限保护)",
                words=words,
                tick_count=tick_count,
            )
        return SectionClosureDecision(
            should_close=False,
            reason=f"words={words} 在区间内, LLM 判定未闭合: {llm_reason}",
            words=words,
            tick_count=tick_count,
        )

    async def _llm_judge_closure(
        self,
        *,
        narrative_text: str,
        words: int,
        tick_count: int,
        novel_title: str,
    ) -> tuple[bool, str]:
        title_hint = f"《{novel_title}》" if novel_title and novel_title != "未命名小说" else ""
        # 只看末尾 ~2000 字 — 收束信号在尾部, 头部信息无关切节决策
        tail = narrative_text[-2000:] if len(narrative_text) > 2000 else narrative_text

        system_prompt = (
            "你是一位连载小说编辑, 任务是判断一段累积的小说正文是否到了"
            "可以切成「一节」的位置。\n"
            "判定标准 (满足任一即视为闭合):\n"
            "1. 场景结束: 角色离开当前场景, 或场景气氛明显转换\n"
            "2. 冲突推进段落完成: 一次对抗 / 对话 / 情绪起伏告一段落\n"
            "3. 时间跳跃: 文本暗示进入下一时段 (黄昏 / 次日 / 几天后)\n"
            "4. 收束句: 末段以动作/物件/对话停住, 留下回味\n"
            "如果以下情况则视为未闭合:\n"
            "- 末段是半句话 / 对话进行到一半\n"
            "- 一个明显的悬念刚被抛出但未给反应\n"
            "- 战斗 / 关键决定正在进行中\n"
            "输出严格 JSON: {\"closed\": true|false, \"reason\": \"一句话\"}"
        )
        user_prompt = (
            f"{title_hint}\n当前累积字数: {words}, tick 数: {tick_count}\n\n"
            f"【正文末尾 (供判定)】\n{tail}\n\n请输出严格 JSON 判定:"
        )

        try:
            resp = await llm_client.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=128,
                agent_id="section_closer_judge",
                priority="optional",
            )
        except Exception as e:
            logger.warning("SectionCloser LLM judge failed (non-fatal): %s", e)
            # LLM 不可用时的 fallback: 字数到 target 就视为闭合
            if words >= self.target_words:
                return True, f"LLM 不可用, 字数 {words} 达 target 视为闭合"
            return False, f"LLM 不可用, 字数 {words} 未达 target 不切"

        try:
            payload = json.loads(strip_code_fence(resp.content))
            closed = bool(payload.get("closed", False))
            reason = str(payload.get("reason", "")).strip() or "(LLM 未给理由)"
            return closed, reason
        except Exception as e:
            logger.warning("SectionCloser LLM 输出解析失败 (%s): %s", e, resp.content[:200])
            # 解析失败时保守: 字数达 target 就切, 否则不切
            if words >= self.target_words:
                return True, "LLM 输出无法解析, 字数达 target 兜底切"
            return False, "LLM 输出无法解析, 字数未达 target 兜底不切"

    # ------------------------------------------------------------------
    # 2) 切节 — 补叙 + 标题 + 终稿
    # ------------------------------------------------------------------

    async def close_section(
        self,
        *,
        narrative_text: str,
        silent_ticks: list[SilentTickRecord],
        chapter: int,
        section_no: int,
        novel_title: str = "",
    ) -> SectionClosureOutput:
        """生成补叙 (若有沉默 tick) + 拼正文 + 生成标题。"""
        supplement = ""
        consumed: list[int] = []
        if silent_ticks:
            supplement = await self._draft_closure_supplement(
                silent_ticks=silent_ticks,
                novel_title=novel_title,
                preceding_tail=narrative_text[-800:] if narrative_text else "",
            )
            consumed = [r.tick for r in silent_ticks]

        if supplement:
            final_content = f"{narrative_text.rstrip()}\n\n{supplement}"
        else:
            final_content = narrative_text

        title = await self._generate_title(
            chapter=chapter,
            section_no=section_no,
            content=final_content,
            novel_title=novel_title,
        )

        return SectionClosureOutput(
            title=title,
            closure_supplement=supplement,
            final_content=final_content,
            word_count=_count_words(final_content),
            consumed_silent_ticks=consumed,
        )

    async def _draft_closure_supplement(
        self,
        *,
        silent_ticks: list[SilentTickRecord],
        novel_title: str,
        preceding_tail: str,
    ) -> str:
        """把沉默 tick 摘要总结为不超过 200 字的过渡段, 衔接到当前正文末尾。"""
        if not silent_ticks:
            return ""

        title_hint = f"《{novel_title}》" if novel_title and novel_title != "未命名小说" else ""
        summaries_dump = "\n".join(
            f"- tick {r.tick}: {r.summary}" for r in silent_ticks[:30]
        )

        system_prompt = (
            "你是连载小说的叙述者。给你这一节里被快速带过的几个 tick 摘要 — "
            "Narrator 选择不为它们独立成段, 但切节前需要把它们以一段过渡文字"
            "扫尾, 让读者知道这段时间发生了什么、节奏没有断。\n"
            "要求:\n"
            "1. 总长度 80-200 字, 不要超过\n"
            "2. 不要堆砌动词列表, 用流畅的过渡叙述\n"
            "3. 不要重复正文已经写过的内容\n"
            "4. 结尾停在动作 / 物件 / 时间, 不要总结升华\n"
            "5. 仅输出过渡段正文, 不要任何前言后语"
        )
        user_prompt = (
            f"{title_hint}\n【正文末尾 (供衔接)】\n{preceding_tail or '(无)'}\n\n"
            f"【需要带过的几个 tick】\n{summaries_dump}\n\n"
            "请输出 80-200 字的收束过渡段:"
        )

        try:
            resp = await llm_client.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=400,
                agent_id="section_closer_supplement",
                priority="optional",
            )
        except Exception as e:
            logger.warning("SectionCloser supplement LLM failed (non-fatal): %s", e)
            return _fallback_supplement(silent_ticks)

        text = resp.content.strip()
        # 兜底清洗
        text = strip_code_fence(text).strip()
        if not text:
            return _fallback_supplement(silent_ticks)
        # 限长保护 (按字符, 中文场景下 ~= 字)
        if len(text) > 240:
            text = text[:240].rstrip() + "……"
        return text

    async def _generate_title(
        self,
        *,
        chapter: int,
        section_no: int,
        content: str,
        novel_title: str,
    ) -> str:
        fallback = _fallback_title_from_content(content) or f"第{section_no}节"
        if not content.strip():
            return fallback

        title_hint = f"《{novel_title}》" if novel_title and novel_title != "未命名小说" else ""
        try:
            resp = await llm_client.chat(
                system_prompt=(
                    "你是一位小说编辑。请基于本节正文为它取一个 4-12 字的小节标题。\n"
                    "要求:\n"
                    "1. 仅输出标题文字, 不要书名号 / 引号 / 章节编号 / 标点\n"
                    "2. 不要使用「开篇介绍」「本节讲述」之类的元描述\n"
                    "3. 与小说题材一致"
                ),
                user_prompt=(
                    f"{title_hint}第{chapter}章 第{section_no}节\n\n"
                    f"【正文节选】\n{content[:1500]}\n\n请输出标题:"
                ),
                temperature=0.6,
                max_tokens=24,
                agent_id="section_closer_title",
                priority="optional",
            )
            title = resp.content.strip().split("\n")[0].strip()
            title = title.strip("《》\"'“”‘’").strip()
            if 1 <= len(title) <= 20:
                return title
        except Exception as e:
            logger.warning("SectionCloser title LLM failed (non-fatal): %s", e)
        return fallback


# ---- 模块级工具 -------------------------------------------------------------


def _count_words(text: str) -> int:
    """字数 = 去掉空白后的字符数 (中文 1 字 = 1 字符, 与读者预期一致)。"""
    if not text:
        return 0
    return sum(1 for ch in text if not ch.isspace())


def _fallback_title_from_content(content: str) -> str:
    """LLM 失败时的标题兜底: 取正文首句前 4-14 字。"""
    text = content.strip()
    if not text:
        return ""
    for sep in ("。", "!", "?", "!", "?", "\n"):
        idx = text.find(sep)
        if 0 < idx <= 30:
            text = text[:idx]
            break
    text = text.strip()
    return text[:14] if len(text) > 14 else text


def _fallback_supplement(silent_ticks: list[SilentTickRecord]) -> str:
    """LLM 失败时的补叙兜底: 把沉默 tick 摘要直接接成一段。

    不漂亮但保证语义不丢失 — 后续 MemoryCompressor 仍能正确把这些事件归并。
    """
    if not silent_ticks:
        return ""
    parts = []
    for r in silent_ticks[:10]:
        s = r.summary.strip()
        if not s:
            continue
        # 去掉 "tick N:" 前缀这种 record-keeping 痕迹
        if s.startswith("tick "):
            idx = s.find(":")
            if 0 < idx < 12:
                s = s[idx + 1 :].strip()
        parts.append(s)
    if not parts:
        return ""
    body = " ".join(parts)
    if len(body) > 200:
        body = body[:200].rstrip() + "……"
    return body
