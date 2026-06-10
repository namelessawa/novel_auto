"""CreativityScorer — 词汇/结构/情感多样性滑窗追踪。

针对主 Agent 关注问题清单的最后一项:
* **缺乏真正的创造力与情感体验** — 不是审美判断, 而是测量"系统是否在
  渐进套路化"。当滑窗指标显著低于基线时触发 alert, 注入 Narrator 提醒。

设计:
* 三层指标:
  * 词汇多样性 (lexical): type-token ratio + hapax_legomena ratio + 重复 2-gram 数
  * 结构多样性 (structural): 句长 std/mean + 段落起笔类型分布熵
  * 情感多样性 (emotional): 段落情感关键词集合大小 / 情感 valence 变化
* 滑窗 (默认 10 段) 内的当前值 vs 全局基线 (前 N 段) 对比
* 退化 > 20% → alert; 用规范的 codes (CRX_LEX / CRX_STRUCT / CRX_EMO)
* 全确定性 — 无 LLM 调用, 推理 < 1ms
"""

from __future__ import annotations

import math
import re
from collections import Counter, deque
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 静态情感词典 — 中文常见 (扩展可注册)
# ---------------------------------------------------------------------------

EMOTION_LEXICON: dict[str, tuple[str, ...]] = {
    "joy": ("笑", "高兴", "欣喜", "雀跃", "兴奋", "愉快", "欢喜"),
    "sadness": ("哭", "悲", "难过", "哀", "怆", "痛苦", "凄凉"),
    "anger": ("怒", "怒火", "愤怒", "怒气", "盛怒", "暴怒"),
    "fear": ("怕", "恐惧", "战栗", "畏惧", "胆怯", "惊恐"),
    "surprise": ("惊", "惊讶", "震惊", "诧异", "意外"),
    "calm": ("静", "安宁", "平静", "沉默", "镇定"),
    "love": ("爱", "怜惜", "温柔", "亲切"),
    "shame": ("羞", "愧", "尴尬", "窘"),
}

ALL_EMOTION_WORDS: tuple[str, ...] = tuple(
    w for words in EMOTION_LEXICON.values() for w in words
)


# ---------------------------------------------------------------------------
# 数据契约
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParagraphMetrics:
    """单段产出的测量值 — 不可变, 历史可重放。"""

    tick: int
    char_count: int
    token_count: int  # 中文按字符近似
    unique_token_count: int
    hapax_count: int  # 只出现一次的 token
    repeated_2gram_count: int
    sentence_count: int
    sentence_len_mean: float
    sentence_len_std: float
    opening_signature: str
    detected_emotions: tuple[str, ...]
    emotional_categories: tuple[str, ...]  # joy/sadness/...

    @property
    def ttr(self) -> float:
        """type-token ratio — 词汇多样性核心指标。"""
        if self.token_count == 0:
            return 0.0
        return self.unique_token_count / self.token_count

    @property
    def hapax_ratio(self) -> float:
        if self.token_count == 0:
            return 0.0
        return self.hapax_count / self.token_count


@dataclass
class CreativityAlert:
    code: str
    severity: str  # "high" | "medium"
    metric: str
    baseline: float
    current: float
    drop_pct: float
    advice: str

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "metric": self.metric,
            "baseline": round(self.baseline, 4),
            "current": round(self.current, 4),
            "drop_pct": round(self.drop_pct, 4),
            "advice": self.advice,
        }


@dataclass
class CreativityReport:
    paragraph_count: int
    window_size: int
    baseline_size: int
    avg_ttr_window: float = 0.0
    avg_ttr_baseline: float = 0.0
    avg_struct_window: float = 0.0
    avg_struct_baseline: float = 0.0
    emotion_diversity_window: int = 0
    emotion_diversity_baseline: int = 0
    alerts: list[CreativityAlert] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "paragraph_count": self.paragraph_count,
            "window_size": self.window_size,
            "baseline_size": self.baseline_size,
            "avg_ttr_window": round(self.avg_ttr_window, 4),
            "avg_ttr_baseline": round(self.avg_ttr_baseline, 4),
            "avg_struct_window": round(self.avg_struct_window, 4),
            "avg_struct_baseline": round(self.avg_struct_baseline, 4),
            "emotion_diversity_window": self.emotion_diversity_window,
            "emotion_diversity_baseline": self.emotion_diversity_baseline,
            "alerts": [a.to_dict() for a in self.alerts],
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

_CJK_PAT = re.compile(r"[一-龥]")
_SENT_SPLIT_PAT = re.compile(r"[。!?！？；;]")


def _tokenize(text: str) -> list[str]:
    """中文按字符分词 (轻量, 无依赖)。"""
    return _CJK_PAT.findall(text)


def _two_grams(tokens: list[str]) -> list[str]:
    return [tokens[i] + tokens[i + 1] for i in range(len(tokens) - 1)]


def _stddev(values: list[float], mean: float) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def compute_metrics(text: str, *, tick: int = -1) -> ParagraphMetrics:
    """从原始段落计算 ParagraphMetrics — 全确定性。"""
    tokens = _tokenize(text)
    sentences = [s for s in _SENT_SPLIT_PAT.split(text) if s.strip()]
    sent_lens = [len(s) for s in sentences]
    sent_mean = sum(sent_lens) / len(sent_lens) if sent_lens else 0.0
    sent_std = _stddev([float(x) for x in sent_lens], sent_mean)

    counter = Counter(tokens)
    unique = len(counter)
    hapax = sum(1 for _, c in counter.items() if c == 1)

    grams = _two_grams(tokens)
    gram_counter = Counter(grams)
    repeated_grams = sum(c for g, c in gram_counter.items() if c >= 2)

    detected_emotions: list[str] = []
    detected_categories: set[str] = set()
    for cat, words in EMOTION_LEXICON.items():
        for w in words:
            if w in text:
                detected_emotions.append(w)
                detected_categories.add(cat)
                break  # 每类只记一个 token, 避免堆叠

    opening = text.lstrip()[:6]

    return ParagraphMetrics(
        tick=tick,
        char_count=len(text),
        token_count=len(tokens),
        unique_token_count=unique,
        hapax_count=hapax,
        repeated_2gram_count=repeated_grams,
        sentence_count=len(sentences),
        sentence_len_mean=sent_mean,
        sentence_len_std=sent_std,
        opening_signature=opening,
        detected_emotions=tuple(detected_emotions),
        emotional_categories=tuple(sorted(detected_categories)),
    )


# ---------------------------------------------------------------------------
# CreativityScorer
# ---------------------------------------------------------------------------


class CreativityScorer:
    """滑窗追踪 + 基线对比 + 退化 alert。"""

    def __init__(
        self,
        *,
        window_size: int = 10,
        baseline_size: int = 20,
        drop_threshold_pct: float = 0.20,
    ) -> None:
        self._window_size = max(3, window_size)
        self._baseline_size = max(3, baseline_size)
        self._drop_threshold = drop_threshold_pct
        self._history: deque[ParagraphMetrics] = deque()
        self._baseline_locked = False
        self._baseline_metrics: list[ParagraphMetrics] = []
        # 真实累计 ingest 数 — _history 会被滑窗裁剪, len(_history) 不是累计值
        self._total_ingested = 0

    @property
    def history_size(self) -> int:
        return len(self._history)

    @property
    def baseline_locked(self) -> bool:
        return self._baseline_locked

    def ingest_paragraph(self, text: str, *, tick: int = -1) -> ParagraphMetrics:
        """登记一段产出。返回该段的 metrics, 供调试/诊断。"""
        metrics = compute_metrics(text, tick=tick)
        self._history.append(metrics)
        self._total_ingested += 1
        # 首次窗口填满即锁定 baseline
        if (
            not self._baseline_locked
            and len(self._history) >= self._baseline_size
        ):
            self._baseline_metrics = list(self._history)[: self._baseline_size]
            self._baseline_locked = True
        # 保留最近 window + baseline 的副本
        while len(self._history) > self._baseline_size + self._window_size:
            self._history.popleft()
        return metrics

    def report(self) -> CreativityReport:
        """生成当前 CreativityReport — 基于最近 window 与 baseline 对比。"""
        rep = CreativityReport(
            # 报告真实累计段数 — len(_history) 是被裁剪后的窗口长度
            paragraph_count=self._total_ingested,
            window_size=self._window_size,
            baseline_size=self._baseline_size,
        )
        if not self._baseline_locked or len(self._history) < self._window_size:
            rep.summary = "尚未锁定基线"
            return rep

        window = list(self._history)[-self._window_size :]
        baseline = self._baseline_metrics

        # 词汇 — 平均 TTR
        ttr_w = _avg(m.ttr for m in window)
        ttr_b = _avg(m.ttr for m in baseline)
        rep.avg_ttr_window = ttr_w
        rep.avg_ttr_baseline = ttr_b

        # 结构 — 平均 sentence_len_std (节奏多样性)
        struct_w = _avg(m.sentence_len_std for m in window)
        struct_b = _avg(m.sentence_len_std for m in baseline)
        rep.avg_struct_window = struct_w
        rep.avg_struct_baseline = struct_b

        # 情感 — 窗口内涉及的不同 emotional_categories 总数
        emo_w = len({cat for m in window for cat in m.emotional_categories})
        emo_b = len({cat for m in baseline for cat in m.emotional_categories})
        rep.emotion_diversity_window = emo_w
        rep.emotion_diversity_baseline = emo_b

        # Alert: 词汇多样性退化
        if ttr_b > 0 and (ttr_b - ttr_w) / ttr_b > self._drop_threshold:
            rep.alerts.append(
                CreativityAlert(
                    code="CRX_LEX",
                    severity="medium",
                    metric="ttr",
                    baseline=ttr_b,
                    current=ttr_w,
                    drop_pct=(ttr_b - ttr_w) / ttr_b,
                    advice="词汇多样性下降 — Narrator 应主动引入新词/具体物名, 避免同义词替换",
                )
            )

        # Alert: 句长节奏退化 (struct std 降低 → 单调)
        if struct_b > 0 and (struct_b - struct_w) / struct_b > self._drop_threshold:
            rep.alerts.append(
                CreativityAlert(
                    code="CRX_STRUCT",
                    severity="medium",
                    metric="sentence_len_std",
                    baseline=struct_b,
                    current=struct_w,
                    drop_pct=(struct_b - struct_w) / struct_b,
                    advice="句长节奏趋于均匀 — 下段尝试突变 (突然一短句或一长句)",
                )
            )

        # Alert: 情感多样性退化 (绝对数字, baseline 是窗口长度上限)
        if emo_b > 0 and (emo_b - emo_w) / emo_b > self._drop_threshold:
            severity = "high" if emo_w <= 1 else "medium"
            rep.alerts.append(
                CreativityAlert(
                    code="CRX_EMO",
                    severity=severity,
                    metric="emotion_category_count",
                    baseline=float(emo_b),
                    current=float(emo_w),
                    drop_pct=(emo_b - emo_w) / emo_b,
                    advice="情感色彩单一 — 下段引入与当前主导情感对比的体感反应",
                )
            )

        rep.summary = (
            f"段数={rep.paragraph_count}, "
            f"alerts={len(rep.alerts)}; "
            f"ttr={ttr_w:.2f}/{ttr_b:.2f}, "
            f"struct={struct_w:.1f}/{struct_b:.1f}, "
            f"emo={emo_w}/{emo_b}"
        )
        return rep


def _avg(values) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


__all__ = [
    "CreativityScorer",
    "CreativityReport",
    "CreativityAlert",
    "ParagraphMetrics",
    "compute_metrics",
    "EMOTION_LEXICON",
]
