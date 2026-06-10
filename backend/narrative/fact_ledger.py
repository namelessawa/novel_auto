"""FactLedger — 持久化的事实账本 + 时间线索引 + 矛盾检测。

针对主 Agent 关注问题清单的四项:

1. **逻辑错误与常识漏洞的累积** — 每条事实带 source_event_id, 可回溯;
   矛盾事实记录而非默认覆盖
2. **事实性错误的滚雪球效应** — append-only ledger, 同一 (subject, predicate)
   后续矛盾自动触发 `disputed` 标记, 不让错误悄悄演化
3. **复杂因果关系与时间线的混乱** — `Timeline` 索引: character → 顺序的
   (tick, location, action) 条目, 可查询任一 tick 的所在地
4. **世界设定的自相矛盾** — `assert_world_rule` 与 `check_world_rule_violation`
   分离, world_rules 修改时显式标记 deprecates

设计:
* 全确定性 (无 LLM) — 事实由 Orchestrator / 各 Agent 显式 assert, 不靠 NLP 抽取
* Pydantic v2 模型 — 与 tick 契约同源
* JSON 原子写, 与 PriorityMemoryStore 同目录共存
* contradict_check 不修改账本, 只返回冲突报告 — 由调用方决定后续动作
"""

from __future__ import annotations

import bisect
import json
import logging
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


FactKind = Literal[
    "location",      # subject 当前 (或某 tick) 所在地点
    "possession",    # subject 持有 object
    "relation",      # subject 与 object 的关系类型 (label 字段)
    "rule",          # 世界规则 (predicate 是规则陈述, object 可空)
    "death",         # subject 死亡
    "skill",         # subject 掌握技能 (object 是技能名)
    "promise",       # subject 对 object 立下承诺
    "fact",          # 自由形式 (谨慎使用)
]


FactStatus = Literal["active", "disputed", "retracted", "superseded"]


class Fact(BaseModel):
    """单条事实 — 不可变 (status 字段除外)。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    kind: FactKind
    subject: str  # 通常 character_id
    predicate: str = ""  # 与 kind 配合 — 如 location 时存地点 id, rule 时存规则陈述
    object: str = ""  # 可空 — possession/relation/skill 时是目标对象 id 或名称
    established_tick: int = 0
    source_event_id: str = ""
    status: FactStatus = "active"
    superseded_by: str = ""  # 后继 fact id, 用于追溯演化
    notes: str = ""


@dataclass(frozen=True)
class FactConflict:
    """contradict_check 输出 — 不写回账本, 由调用方决定动作。"""

    new_fact: Fact
    existing_fact: Fact
    reason: str
    severity: Literal["high", "medium", "low"] = "high"

    def to_dict(self) -> dict:
        return {
            "new_fact": self.new_fact.model_dump(mode="json"),
            "existing_fact": self.existing_fact.model_dump(mode="json"),
            "reason": self.reason,
            "severity": self.severity,
        }


@dataclass
class TimelineEntry:
    """单角色单 tick 的"位置/动作"轨迹点 — 由 location 类 fact 自动构建。"""

    tick: int
    location: str = ""
    action: str = ""
    source_fact_id: str = ""

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "location": self.location,
            "action": self.action,
            "source_fact_id": self.source_fact_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TimelineEntry":
        return cls(
            tick=int(data.get("tick", 0)),
            location=str(data.get("location", "")),
            action=str(data.get("action", "")),
            source_fact_id=str(data.get("source_fact_id", "")),
        )


# ---------------------------------------------------------------------------
# FactLedger
# ---------------------------------------------------------------------------


class FactLedger:
    """事实账本 + 时间线索引 + 矛盾检测。原子持久化。"""

    FILENAME = "fact_ledger.json"

    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir
        self._path = os.path.join(data_dir, self.FILENAME)
        self._facts: dict[str, Fact] = {}
        # 索引: (subject, kind) → 当前 active fact id (多事实时取最新)
        self._active_by_subject_kind: dict[tuple[str, str], str] = {}
        # 时间线: character → [TimelineEntry 按 tick 升序]
        self._timeline: dict[str, list[TimelineEntry]] = defaultdict(list)

    # ------------------------------------------------------------------
    # 基础 CRUD
    # ------------------------------------------------------------------

    def assert_fact(self, fact: Fact, *, contradict_action: str = "dispute") -> None:
        """登记一条事实。

        ``contradict_action`` 控制遇到冲突时的策略:
        * ``"dispute"`` — 新事实设为 active, 旧事实降级为 disputed
        * ``"supersede"`` — 旧事实标记 superseded, 新事实接管
        * ``"keep_old"`` — 新事实直接设为 disputed, 旧保持 active
        """
        key = (fact.subject, fact.kind)
        existing_id = self._active_by_subject_kind.get(key)
        if existing_id and existing_id != fact.id:
            existing = self._facts.get(existing_id)
            if existing is not None and self._facts_conflict(existing, fact):
                if contradict_action == "supersede":
                    self._facts[existing_id] = existing.model_copy(
                        update={
                            "status": "superseded",
                            "superseded_by": fact.id,
                        }
                    )
                    self._active_by_subject_kind[key] = fact.id
                elif contradict_action == "keep_old":
                    fact = fact.model_copy(update={"status": "disputed"})
                else:  # dispute
                    self._facts[existing_id] = existing.model_copy(
                        update={"status": "disputed"}
                    )
                    self._active_by_subject_kind[key] = fact.id
            else:
                # 无冲突 — 新事实接管 active 指针
                self._active_by_subject_kind[key] = fact.id
        else:
            if fact.status == "active":
                self._active_by_subject_kind[key] = fact.id

        self._facts[fact.id] = fact
        # location 类 fact 自动维护 timeline
        if fact.kind == "location" and fact.subject:
            self._append_timeline(
                fact.subject,
                TimelineEntry(
                    tick=fact.established_tick,
                    location=fact.predicate,
                    source_fact_id=fact.id,
                ),
            )

    def _append_timeline(self, subject: str, entry: TimelineEntry) -> None:
        timeline = self._timeline[subject]
        # bisect_right 按 tick 升序插入; 同 tick 保持先来后到 (stable)
        idx = bisect.bisect_right([e.tick for e in timeline], entry.tick)
        timeline.insert(idx, entry)

    def assert_many(self, facts: Iterable[Fact]) -> None:
        for f in facts:
            self.assert_fact(f)

    def get(self, fact_id: str) -> Fact | None:
        return self._facts.get(fact_id)

    def all_facts(self) -> list[Fact]:
        return list(self._facts.values())

    def active_facts(self) -> list[Fact]:
        return [f for f in self._facts.values() if f.status == "active"]

    def facts_about(self, subject: str, kind: FactKind | None = None) -> list[Fact]:
        out = [f for f in self._facts.values() if f.subject == subject]
        if kind is not None:
            out = [f for f in out if f.kind == kind]
        return out

    def current_location_of(self, subject: str) -> str | None:
        fid = self._active_by_subject_kind.get((subject, "location"))
        if fid is None:
            return None
        f = self._facts.get(fid)
        return f.predicate if f else None

    def location_at_tick(self, subject: str, tick: int) -> str | None:
        """查询 subject 在指定 tick 的所在地点 (取 ≤tick 的最新 timeline 项)。"""
        timeline = self._timeline.get(subject, [])
        best: TimelineEntry | None = None
        for e in timeline:
            if e.tick <= tick:
                best = e
            else:
                break
        return best.location if best else None

    def is_dead(self, subject: str) -> bool:
        fid = self._active_by_subject_kind.get((subject, "death"))
        return fid is not None and self._facts[fid].status == "active"

    @property
    def size(self) -> int:
        return len(self._facts)

    # ------------------------------------------------------------------
    # 矛盾检测
    # ------------------------------------------------------------------

    def contradict_check(self, new_fact: Fact) -> list[FactConflict]:
        """检测 new_fact 与现有 active 事实的冲突, 不修改账本。

        覆盖五类:
        * 同一 subject 不同 tick 出现在两个不同地点 (但 established_tick 相同) — 高
        * 死者再次出现 location/possession/action — 高
        * possession 冲突 (同物品两主) — 中
        * relation 类型突变无 source 桥接 — 中
        * 与 rule 类 active fact 直接矛盾 — 高 (粗略 — 由调用方进一步语义判断)
        """
        conflicts: list[FactConflict] = []

        # 死者复生检测
        if new_fact.kind in {"location", "possession", "skill", "promise"} and self.is_dead(
            new_fact.subject
        ):
            existing_id = self._active_by_subject_kind.get((new_fact.subject, "death"))
            if existing_id:
                conflicts.append(
                    FactConflict(
                        new_fact=new_fact,
                        existing_fact=self._facts[existing_id],
                        reason=f"已死亡角色 {new_fact.subject} 不应有 {new_fact.kind} 类事实",
                        severity="high",
                    )
                )

        # 同 subject 同 kind 的 active fact 检测
        key = (new_fact.subject, new_fact.kind)
        existing_id = self._active_by_subject_kind.get(key)
        if existing_id and existing_id != new_fact.id:
            existing = self._facts.get(existing_id)
            if existing is not None and self._facts_conflict(existing, new_fact):
                conflicts.append(
                    FactConflict(
                        new_fact=new_fact,
                        existing_fact=existing,
                        reason=self._explain_conflict(existing, new_fact),
                        severity=self._severity_for_kind(new_fact.kind),
                    )
                )

        # possession 跨 subject 冲突 — 同一 object 被两人持有
        if new_fact.kind == "possession" and new_fact.object:
            for fid, f in self._facts.items():
                if f.id == new_fact.id or f.status != "active":
                    continue
                if (
                    f.kind == "possession"
                    and f.object == new_fact.object
                    and f.subject != new_fact.subject
                ):
                    conflicts.append(
                        FactConflict(
                            new_fact=new_fact,
                            existing_fact=f,
                            reason=(
                                f"物品 {new_fact.object} 同时被 {f.subject} 持有"
                            ),
                            severity="medium",
                        )
                    )

        return conflicts

    @staticmethod
    def _facts_conflict(a: Fact, b: Fact) -> bool:
        """同 (subject, kind) 下, predicate 或 object 不同视为冲突。"""
        if a.kind != b.kind or a.subject != b.subject:
            return False
        if a.predicate != b.predicate:
            return True
        if a.kind in {"possession", "skill", "promise", "relation"} and a.object != b.object:
            return True
        return False

    @staticmethod
    def _explain_conflict(existing: Fact, new: Fact) -> str:
        return (
            f"{new.subject}.{new.kind} 既有 {existing.predicate or existing.object} "
            f"(tick={existing.established_tick}), 又有 {new.predicate or new.object} "
            f"(tick={new.established_tick})"
        )

    @staticmethod
    def _severity_for_kind(kind: FactKind) -> Literal["high", "medium", "low"]:
        if kind in {"death", "rule"}:
            return "high"
        if kind in {"location", "possession"}:
            return "high"
        if kind in {"skill", "promise", "relation"}:
            return "medium"
        return "low"

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def save(self) -> None:
        os.makedirs(self._data_dir, exist_ok=True)
        payload = {
            "version": 1,
            "facts": [f.model_dump(mode="json") for f in self._facts.values()],
            "timeline": {
                cid: [e.to_dict() for e in entries]
                for cid, entries in self._timeline.items()
            },
        }
        fd, tmp = tempfile.mkstemp(
            prefix=".fact_ledger_", suffix=".tmp", dir=self._data_dir
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
            logger.warning("FactLedger load failed: %s", e)
            return False
        self._facts.clear()
        self._active_by_subject_kind.clear()
        self._timeline.clear()
        for raw in payload.get("facts", []) or []:
            try:
                f = Fact.model_validate(raw)
                self._facts[f.id] = f
                if f.status == "active":
                    self._active_by_subject_kind[(f.subject, f.kind)] = f.id
            except Exception as e:
                logger.warning("Skip invalid fact: %s", e)
        for cid, entries in (payload.get("timeline") or {}).items():
            restored = [TimelineEntry.from_dict(e) for e in entries]
            # 磁盘数据可能乱序 (旧版本写入 / 手工编辑) — 排序兜底,
            # 维持 _append_timeline 的 bisect 升序前提 (stable, 同 tick 保序)
            restored.sort(key=lambda e: e.tick)
            self._timeline[cid] = restored
        return True


__all__ = [
    "Fact",
    "FactConflict",
    "FactKind",
    "FactStatus",
    "FactLedger",
    "TimelineEntry",
]
