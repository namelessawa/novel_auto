"""PriorityMemoryStore — 持久化的分层记忆存储 + 多因子优先级。

解决三类问题 (来自 novel_quality_critique_and_iteration.md 主 Agent 关注列表):

1. **长期记忆与全局一致性崩塌** — 内存条目持久化到磁盘, 不依赖单一 LLM 上下文窗口
2. **RAG 检索式记忆的致命缺陷** — 多因子打分 (importance × recency × reference_count
   × emotional × char_overlap), 避免朴素 top-k 余弦相似的退化
3. **缺乏分层记忆与优先级机制** — 显式 L0-L3 层级 + protected_reason + 自动衰减

设计原则:
* **分层不平等** — 越接近当前 tick, 保留越完整 (L0 全文 → L1 摘要 → L2 抽象 → L3 传说)
* **优先级不只看 importance** — 引用次数高、情感标签 = trauma/vow/secret 的条目享受保护
* **衰减非剪枝** — 重要性随时间下降 (importance_eff), 但不删除条目, 仅影响检索排序
* **保护即不动** — protected_reason 非空的条目, 无论多老都不会被压缩或淘汰
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Iterable, Literal

from memory_system.models import MemoryEntry, MemoryTier

logger = logging.getLogger(__name__)


# 重要情感标签 — 自动 protected
TRAUMA_TAGS: frozenset[str] = frozenset({"trauma", "vow", "secret", "loss", "betrayal"})


@dataclass
class MemoryRecord:
    """MemoryEntry 的存储侧包装 — 增加运行时状态字段。"""

    entry: MemoryEntry
    last_access_tick: int = 0
    reference_count: int = 0
    decay_floor: float = 0.5  # importance × decay_floor 是 effective importance 的下限

    def to_dict(self) -> dict:
        return {
            "entry": self.entry.model_dump(mode="json"),
            "last_access_tick": self.last_access_tick,
            "reference_count": self.reference_count,
            "decay_floor": self.decay_floor,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryRecord":
        return cls(
            entry=MemoryEntry.model_validate(data["entry"]),
            last_access_tick=int(data.get("last_access_tick", 0)),
            reference_count=int(data.get("reference_count", 0)),
            decay_floor=float(data.get("decay_floor", 0.5)),
        )

    @property
    def is_protected(self) -> bool:
        if self.entry.protected_reason:
            return True
        if any(t in TRAUMA_TAGS for t in self.entry.emotional_tags):
            return True
        # 高引用次数 = 故事的"主弦", 等同保护
        return self.reference_count >= 3

    def effective_importance(self, current_tick: int) -> float:
        """运行时打分 — importance × 衰减因子 × 引用加成。"""
        ticks_since_access = max(0, current_tick - self.last_access_tick)
        # 衰减: 每 200 tick 衰减 30%, 但有 decay_floor 兜底
        decay = max(self.decay_floor, 1.0 - (ticks_since_access / 200.0) * 0.3)
        ref_bonus = min(0.5, self.reference_count * 0.15)
        return self.entry.importance * decay + ref_bonus * 10.0


@dataclass
class RetrievalQuery:
    """多因子检索的查询参数。"""

    current_tick: int
    query_chars: list[str] = field(default_factory=list)  # 出现的角色
    query_tags: list[str] = field(default_factory=list)  # 情感/主题标签
    query_text: str = ""  # 自由文本 (子串匹配, 非向量)
    tier_filter: list[MemoryTier] | None = None
    top_k: int = 8
    # 防"全是 L3 传说"的副作用 — 强制至少 N 条来自较新层
    min_l0_or_l1: int = 2


@dataclass(frozen=True)
class RetrievalResult:
    record: MemoryRecord
    score: float
    matched_dimensions: tuple[str, ...]


# ---------------------------------------------------------------------------
# 持久化存储
# ---------------------------------------------------------------------------


class PriorityMemoryStore:
    """分层记忆存储 + 多因子检索。原子写入磁盘。"""

    FILENAME = "memory_store.json"

    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir
        self._records: dict[str, MemoryRecord] = {}
        self._path = os.path.join(data_dir, self.FILENAME)

    # ------------------------------------------------------------------
    # 基础操作
    # ------------------------------------------------------------------

    def add(self, entry: MemoryEntry, *, current_tick: int = 0) -> MemoryRecord:
        """新增条目。已存在则覆盖 entry, 保留运行时状态。"""
        existing = self._records.get(entry.id)
        if existing is not None:
            existing.entry = entry
            return existing
        rec = MemoryRecord(entry=entry, last_access_tick=current_tick)
        self._records[entry.id] = rec
        return rec

    def add_many(self, entries: Iterable[MemoryEntry], *, current_tick: int = 0) -> None:
        for e in entries:
            self.add(e, current_tick=current_tick)

    def get(self, entry_id: str) -> MemoryRecord | None:
        return self._records.get(entry_id)

    def remove(self, entry_id: str) -> bool:
        """仅供测试 / GC 用 — 实际淘汰应通过 MemoryCompressor 升级层级。"""
        return self._records.pop(entry_id, None) is not None

    def all_records(self) -> list[MemoryRecord]:
        return list(self._records.values())

    def by_tier(self, tier: MemoryTier) -> list[MemoryRecord]:
        return [r for r in self._records.values() if r.entry.tier == tier]

    @property
    def size(self) -> int:
        return len(self._records)

    # ------------------------------------------------------------------
    # 访问 / 引用计数
    # ------------------------------------------------------------------

    def touch(self, entry_id: str, current_tick: int) -> None:
        """Narrator 引用了该条目 — 更新 last_access + reference_count。"""
        rec = self._records.get(entry_id)
        if rec is None:
            return
        rec.last_access_tick = current_tick
        rec.reference_count += 1

    def mark_protected(self, entry_id: str, reason: str) -> None:
        rec = self._records.get(entry_id)
        if rec is None:
            return
        new_entry = rec.entry.model_copy(update={"protected_reason": reason})
        rec.entry = new_entry

    # ------------------------------------------------------------------
    # 多因子检索 (anti-naive-RAG)
    # ------------------------------------------------------------------

    def retrieve(self, query: RetrievalQuery) -> list[RetrievalResult]:
        """多因子打分 + 防退化策略。

        打分公式 (每项归一化到 0-10 范围内):
        * importance_eff (上限 ~12, 含 reference_count 加成)
        * recency_score = 1 / (1 + ticks_since / 100) × 5
        * char_overlap × 4
        * tag_overlap × 3
        * text_substring × 2
        * tier_proximity: L0=+1.0, L1=+0.5, L2=0, L3=-0.5

        防退化:
        * tier_filter 可硬过滤
        * min_l0_or_l1 强制保留近期上下文
        * 同 involved 集合的条目去重 (避免堆叠相似条目)
        """
        candidates: list[RetrievalResult] = []
        for rec in self._records.values():
            if query.tier_filter and rec.entry.tier not in query.tier_filter:
                continue
            score, dims = self._score(rec, query)
            if score <= 0:
                continue
            candidates.append(
                RetrievalResult(record=rec, score=score, matched_dimensions=tuple(dims))
            )

        # 按 score 降序
        candidates.sort(key=lambda r: r.score, reverse=True)

        # 去重: 同 involved 集合 (非空) + 接近的 tick_range, 仅保留 score 最高
        # 空 involved 的条目不参与 dedup, 避免无关条目互相碰撞掉
        deduped: list[RetrievalResult] = []
        seen_keys: set[tuple] = set()
        for c in candidates:
            involved = tuple(sorted(c.record.entry.involved))
            if not involved:
                deduped.append(c)
                continue
            key = (
                involved,
                c.record.entry.original_tick_range[1] // 20,  # 桶宽 20 tick
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(c)

        # 防"全是 L3"的副作用
        topk = deduped[: query.top_k]
        if query.min_l0_or_l1 > 0:
            l0_l1 = [r for r in topk if r.record.entry.tier in ("L0", "L1")]
            if len(l0_l1) < query.min_l0_or_l1:
                # 从剩余 deduped 中拉 L0/L1 凑数
                extra = [
                    r
                    for r in deduped[query.top_k :]
                    if r.record.entry.tier in ("L0", "L1")
                ][: query.min_l0_or_l1 - len(l0_l1)]
                topk = (l0_l1 + extra + [r for r in topk if r not in l0_l1])[
                    : query.top_k
                ]
        return topk

    def _score(
        self, rec: MemoryRecord, query: RetrievalQuery
    ) -> tuple[float, list[str]]:
        dims: list[str] = []
        score = 0.0

        importance = rec.effective_importance(query.current_tick)
        score += importance
        dims.append(f"importance={importance:.1f}")

        ticks_since = max(0, query.current_tick - rec.last_access_tick)
        recency = 5.0 / (1.0 + ticks_since / 100.0)
        score += recency
        dims.append(f"recency={recency:.1f}")

        # 角色重叠
        if query.query_chars:
            overlap = len(set(query.query_chars) & set(rec.entry.involved))
            if overlap > 0:
                bonus = overlap * 4.0
                score += bonus
                dims.append(f"char_overlap={overlap}")

        # 情感/主题标签
        if query.query_tags:
            tag_overlap = len(set(query.query_tags) & set(rec.entry.emotional_tags))
            if tag_overlap > 0:
                score += tag_overlap * 3.0
                dims.append(f"tag_overlap={tag_overlap}")

        # 自由文本子串匹配 (廉价 fallback, 无 embedding 时也能工作)
        if query.query_text and query.query_text in rec.entry.summary:
            score += 2.0
            dims.append("text_match")

        # tier 近程加成
        tier_bonus = {"L0": 1.0, "L1": 0.5, "L2": 0.0, "L3": -0.5}.get(
            rec.entry.tier, 0.0
        )
        score += tier_bonus

        # 保护条目兜底加成
        if rec.is_protected:
            score += 2.0
            dims.append("protected")

        return score, dims

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def save(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)
        payload = {
            "version": 1,
            "records": [r.to_dict() for r in self._records.values()],
        }
        fd, tmp = tempfile.mkstemp(
            prefix=".memory_store_", suffix=".tmp", dir=self._data_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    def load(self) -> bool:
        if not os.path.exists(self._path):
            return False
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            logger.warning("PriorityMemoryStore load failed: %s", e)
            return False
        self._records.clear()
        for raw in payload.get("records", []) or []:
            try:
                rec = MemoryRecord.from_dict(raw)
                self._records[rec.entry.id] = rec
            except Exception as e:
                logger.warning("Skip invalid memory record: %s", e)
        return True

    # ------------------------------------------------------------------
    # GC / 升级辅助
    # ------------------------------------------------------------------

    def expired_below_tier(
        self,
        current_tick: int,
        *,
        tier: MemoryTier,
        boundary: int,
    ) -> list[MemoryRecord]:
        """返回当前 tier 中已超过 boundary tick 未访问且非保护的条目。

        交给 MemoryCompressor 升级层级用。
        """
        out: list[MemoryRecord] = []
        for rec in self._records.values():
            if rec.entry.tier != tier:
                continue
            if rec.is_protected:
                continue
            since = current_tick - rec.entry.original_tick_range[1]
            if since > boundary:
                out.append(rec)
        return out

    def replace_with_compressed(
        self,
        *,
        source_ids: list[str],
        new_entry: MemoryEntry,
        current_tick: int,
    ) -> MemoryRecord:
        """压缩完成: 用 new_entry 替换 source_ids 的多条 L_n, 引用计数继承累加。"""
        sum_refs = 0
        for sid in source_ids:
            rec = self._records.pop(sid, None)
            if rec is not None:
                sum_refs += rec.reference_count
        new_rec = MemoryRecord(
            entry=new_entry,
            last_access_tick=current_tick,
            reference_count=sum_refs,
        )
        self._records[new_entry.id] = new_rec
        return new_rec


__all__ = [
    "PriorityMemoryStore",
    "MemoryRecord",
    "RetrievalQuery",
    "RetrievalResult",
    "TRAUMA_TAGS",
]
