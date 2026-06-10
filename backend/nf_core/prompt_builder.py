"""PromptBuilder — token 自适应裁剪工具(从 core/generator.py 提取)。

新架构中所有 agent 都应该通过此类构造 prompt,避免在每个 agent 里重复实现
token 计数 + 优先级裁剪逻辑。

设计要点:

* 用 ``tiktoken`` 计算精确 token 数(LLMClient 内部也用同一库)
* 按 ``(label, content, priority)`` 三元组构造段落,优先级越低越先裁剪
* 单段超出预算时按 token 截断尾部,不截断段头
* 通过 ``budget`` 参数显式声明 prompt 预算,缺省 6000 给响应留 2000(8k 模型)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

try:
    import tiktoken
    _ENCODING = tiktoken.get_encoding("cl100k_base")
except (ImportError, Exception):
    _ENCODING = None

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptSection:
    """单段 prompt 内容 + 元数据。

    优先级语义(prompt.md "适配 token 优先级"):
    1 = 最高(必保留) - 系统指令、当前任务
    3 = 中(可压缩) - 角色状态、最近事件
    5 = 低(优先裁剪) - 长期摘要、RAG 历史片段
    """

    label: str
    content: str
    priority: int = 3

    @property
    def header(self) -> str:
        return f"【{self.label}】\n"

    def render(self) -> str:
        return self.header + self.content.rstrip() + "\n\n"


@dataclass
class PromptBuildResult:
    text: str
    token_count: int
    sections_kept: list[str] = field(default_factory=list)
    sections_dropped: list[str] = field(default_factory=list)
    sections_truncated: list[str] = field(default_factory=list)
    over_budget: bool = False


class PromptBuilder:
    """token 预算敏感的 prompt 构造器。"""

    DEFAULT_BUDGET = 6000

    def __init__(self, budget: int = DEFAULT_BUDGET) -> None:
        self._budget = budget

    @property
    def budget(self) -> int:
        return self._budget

    def set_budget(self, budget: int) -> None:
        self._budget = max(512, int(budget))

    def build(
        self,
        sections: list[PromptSection],
        *,
        header: str = "",
        footer: str = "",
    ) -> PromptBuildResult:
        """按优先级裁剪 sections,返回 PromptBuildResult。

        Strategy:
        1. 计算 header + footer 固定开销
        2. 按 (priority asc, original_index asc) 排序 sections 渲染
        3. 若超预算,从优先级最高数字开始 drop(整段)
        4. 若 drop 完仍超,逐段截断 content 末尾 token
        5. 极端情况强制截断,标记 over_budget=True
        """
        header_text = header.rstrip() + "\n\n" if header else ""
        footer_text = "\n" + footer.lstrip() if footer else ""
        fixed_tokens = _count_tokens(header_text + footer_text)
        available = max(0, self._budget - fixed_tokens)

        # 排序: 优先级低的 (数字大) 先被丢弃,保留输入顺序作为 stable key
        ordered = list(enumerate(sections))
        ordered.sort(key=lambda t: (t[1].priority, t[0]))

        rendered: dict[int, tuple[PromptSection, str, int]] = {}
        for idx, sec in ordered:
            r = sec.render()
            rendered[idx] = (sec, r, _count_tokens(r))

        kept_indices = set(range(len(sections)))
        total = sum(rendered[i][2] for i in kept_indices)
        dropped: list[str] = []

        # 优先级语义:
        #   priority 1     - 必保留(不 drop 不 truncate),不存在时仍超预算 → over_budget
        #   priority 2-3   - 可截断,不可整段 drop(保留 label 提示)
        #   priority >= 4  - 可整段 drop
        drop_order = sorted(
            kept_indices,
            key=lambda i: (-rendered[i][0].priority, -i),
        )

        # 阶段 1: drop priority >= 4 的段
        for idx in drop_order:
            if total <= available:
                break
            sec, r, t = rendered[idx]
            if sec.priority < 4:
                continue
            kept_indices.discard(idx)
            dropped.append(sec.label)
            total -= t

        truncated: list[str] = []
        if total > available:
            # 阶段 2: 截断 priority 2-3 (priority=1 永不截断)
            for idx in drop_order:
                if total <= available:
                    break
                if idx not in kept_indices:
                    continue
                sec, r, t = rendered[idx]
                if sec.priority <= 1:
                    continue
                target = max(50, t - (total - available))
                truncated_text = _truncate_to_tokens(r, target)
                new_t = _count_tokens(truncated_text)
                if new_t >= t:
                    # 无 tiktoken 时字符近似的取整误差可能让截断零进展,
                    # 甚至因追加省略号反向膨胀 — 跳过本段, 防预算统计失真。
                    logger.warning(
                        "PromptBuilder truncation made no progress on section "
                        "%r (%d -> %d tokens), skipping",
                        sec.label,
                        t,
                        new_t,
                    )
                    continue
                rendered[idx] = (sec, truncated_text, new_t)
                total = total - t + new_t
                truncated.append(sec.label)

        # 拼装(按原始顺序)
        parts: list[str] = []
        if header_text:
            parts.append(header_text)
        for i in range(len(sections)):
            if i in kept_indices:
                parts.append(rendered[i][1])
        if footer_text:
            parts.append(footer_text)
        final = "".join(parts).strip() + "\n"
        final_tokens = _count_tokens(final)

        return PromptBuildResult(
            text=final,
            token_count=final_tokens,
            sections_kept=[sections[i].label for i in range(len(sections)) if i in kept_indices],
            sections_dropped=dropped,
            sections_truncated=truncated,
            over_budget=final_tokens > self._budget,
        )

    @staticmethod
    def count_tokens(text: str) -> int:
        return _count_tokens(text)


# ----------------------------------------------------------------------------
# Token 计数 / 截断辅助
# ----------------------------------------------------------------------------


def _count_tokens(text: str) -> int:
    if not text:
        return 0
    if _ENCODING is not None:
        try:
            return len(_ENCODING.encode(text))
        except Exception:
            pass
    # 兜底: 中文 1.5 字符/token 近似(英文偏少,只做粗估)
    return max(1, int(len(text) / 1.5))


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    if _ENCODING is not None:
        try:
            tokens = _ENCODING.encode(text)
            if len(tokens) <= max_tokens:
                return text
            return _ENCODING.decode(tokens[:max_tokens]) + "…\n"
        except Exception:
            pass
    # 字符近似
    char_limit = int(max_tokens * 1.5)
    if len(text) <= char_limit:
        return text
    return text[:char_limit] + "…\n"
