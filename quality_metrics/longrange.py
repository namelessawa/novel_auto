"""Long-range quality drift metrics (Phase 2 Stage 3 §6).

Short bench (<20 tick) 测不出 infinite-novel 的真正失败模式:
* memory 保真度衰减 — L0→L1→L2 每层压缩都可能失真
* 伏笔回收率漂移 — 开多回少, 故事越积越乱
* novelty 衰减 — 套路化 / 反复同样冲突 / 同样修辞

本模块输出 **time-series** (随 tick 数变化的曲线), 而非单点值. Caller
按需在每 N tick 采样一次 snapshot, 我们提供 reducer.

iter#86 ship 3 个 reducer + tests. iter#87 跑 100+ tick 长程 bench
得真实曲线. iter#88+ 据曲线立优化项.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class OpenLoopSnapshot:
    """伏笔状态快照 — 调用方从 TickState.get_open_loops() 加 last_referenced_tick
    构造."""

    tick: int
    open_count: int
    closed_count: int  # 累计已关闭 (touched 满 N 次或归档)
    stale_open_count: int  # 当前 open 中 stale_ticks > 20 的数量
    avg_urgency: float = 0.0


@dataclass
class ForeshadowingCurve:
    """伏笔簿记随 tick 的变化."""

    samples: list[OpenLoopSnapshot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def open_to_closed_ratio_at_end(self) -> float:
        """终态 open / max(closed, 1). 越大表示故事堆积越多未回收."""
        if not self.samples:
            return 0.0
        last = self.samples[-1]
        return last.open_count / max(1, last.closed_count)

    @property
    def stale_ratio_at_end(self) -> float:
        """终态 stale_open / max(total_open, 1). 衡量伏笔僵死程度."""
        if not self.samples:
            return 0.0
        last = self.samples[-1]
        return last.stale_open_count / max(1, last.open_count)

    def to_dict(self) -> dict:
        return {
            "sample_count": len(self.samples),
            "open_to_closed_ratio_at_end": round(self.open_to_closed_ratio_at_end, 4),
            "stale_ratio_at_end": round(self.stale_ratio_at_end, 4),
            "samples": [
                {
                    "tick": s.tick,
                    "open": s.open_count,
                    "closed": s.closed_count,
                    "stale_open": s.stale_open_count,
                    "avg_urgency": round(s.avg_urgency, 2),
                }
                for s in self.samples
            ],
            "notes": list(self.notes),
        }


def foreshadowing_curve(snapshots: Sequence[OpenLoopSnapshot]) -> ForeshadowingCurve:
    """聚合 OpenLoopSnapshot 序列到 curve.

    无 sample → 空 curve + note. 单 sample → 终态只可计算静态比率,
    无趋势线 (note).
    """
    curve = ForeshadowingCurve(samples=list(snapshots))
    if not snapshots:
        curve.notes.append("empty_input")
        return curve
    if len(snapshots) < 3:
        curve.notes.append("trend_needs_more_samples")
    return curve


@dataclass
class NoveltySample:
    """novelty_critic 触发记录 — 调用方从 TickState.novelty_warnings 或
    NoveltyCriticOutput.detected_patterns 列举."""

    tick: int
    pattern_count: int  # 本次 critique 报的 pattern 数
    overall_score: int  # NoveltyCriticOutput.overall_novelty_score (1-10)


@dataclass
class NoveltyDecayCurve:
    samples: list[NoveltySample] = field(default_factory=list)

    @property
    def mean_score(self) -> float:
        if not self.samples:
            return 0.0
        return sum(s.overall_score for s in self.samples) / len(self.samples)

    @property
    def trend(self) -> str:
        """early vs late half 的均分差异:
        > 0.5 = 改善 / < -0.5 = 衰减 / 其他 = stable.
        """
        if len(self.samples) < 4:
            return "insufficient_data"
        half = len(self.samples) // 2
        early = sum(s.overall_score for s in self.samples[:half]) / half
        late = sum(s.overall_score for s in self.samples[half:]) / (
            len(self.samples) - half
        )
        delta = late - early
        if delta > 0.5:
            return "improving"
        if delta < -0.5:
            return "decaying"
        return "stable"

    def to_dict(self) -> dict:
        return {
            "sample_count": len(self.samples),
            "mean_score": round(self.mean_score, 4),
            "trend": self.trend,
            "samples": [
                {"tick": s.tick, "pattern_count": s.pattern_count, "score": s.overall_score}
                for s in self.samples
            ],
        }


def novelty_decay_curve(samples: Sequence[NoveltySample]) -> NoveltyDecayCurve:
    return NoveltyDecayCurve(samples=list(samples))


@dataclass
class MemoryProbe:
    """在某 tick 注入一个标识性事实, 多 tick 后探针式检索看其是否仍可寻."""

    inject_tick: int
    probe_id: str  # 任意人工标识符
    probe_text: str  # 注入的关键 substring (检索时 substring 匹配 summary_tree)
    found_in_l0: bool = False
    found_in_l1: bool = False
    found_in_l2: bool = False
    last_check_tick: int = -1

    @property
    def best_layer_found(self) -> str:
        # 优先 L0 (最近, 未压缩); 否则降级.
        for layer in ("l0", "l1", "l2"):
            if getattr(self, f"found_in_{layer}"):
                return layer
        return "none"


@dataclass
class MemoryFidelityReport:
    probes: list[MemoryProbe] = field(default_factory=list)

    @property
    def total_probes(self) -> int:
        return len(self.probes)

    @property
    def lost_probes(self) -> int:
        return sum(1 for p in self.probes if p.best_layer_found == "none")

    @property
    def fidelity(self) -> float:
        if not self.probes:
            return 0.0
        return 1 - self.lost_probes / self.total_probes

    @property
    def per_layer_count(self) -> dict[str, int]:
        out = {"l0": 0, "l1": 0, "l2": 0, "none": 0}
        for p in self.probes:
            out[p.best_layer_found] += 1
        return out

    def to_dict(self) -> dict:
        return {
            "total_probes": self.total_probes,
            "lost_probes": self.lost_probes,
            "fidelity": round(self.fidelity, 4),
            "per_layer_count": dict(self.per_layer_count),
            "probes": [
                {
                    "inject_tick": p.inject_tick,
                    "probe_id": p.probe_id,
                    "best_layer": p.best_layer_found,
                    "last_check_tick": p.last_check_tick,
                }
                for p in self.probes
            ],
        }


def memory_fidelity_report(probes: Sequence[MemoryProbe]) -> MemoryFidelityReport:
    return MemoryFidelityReport(probes=list(probes))


__all__ = [
    "OpenLoopSnapshot",
    "ForeshadowingCurve",
    "foreshadowing_curve",
    "NoveltySample",
    "NoveltyDecayCurve",
    "novelty_decay_curve",
    "MemoryProbe",
    "MemoryFidelityReport",
    "memory_fidelity_report",
]
