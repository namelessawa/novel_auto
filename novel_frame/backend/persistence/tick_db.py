"""TickDB — SQLite WAL 模式的 tick 日志与事件存储。

为什么用 SQLite 而非 JSONL:
* Showrunner 需要 "最近 20 tick 的 event_stats" - SQLite GROUP BY 即可
* NoveltyCritic 需要 "最近 50 character_action 的 action_type 分布" - O(log n) 查询
* WAL 模式: 单文件,无独立进程,读写并发友好
* Python 标准库 ``sqlite3`` 零额外依赖

表结构:

```sql
CREATE TABLE tick_log (
  tick_id INTEGER PRIMARY KEY,
  world_time INTEGER,
  narrator_produced INTEGER,
  narrator_chars INTEGER,
  agents_called TEXT,        -- JSON list
  events_generated TEXT,     -- JSON list
  state_changes_summary TEXT,
  world_time_advanced TEXT,
  next_tick_recommendations TEXT,  -- JSON list
  created_at TEXT
);

CREATE TABLE events (
  event_id TEXT PRIMARY KEY,
  tick_id INTEGER REFERENCES tick_log(tick_id),
  event_type TEXT,
  location TEXT,
  participants TEXT,         -- JSON list
  description TEXT,
  visible_to TEXT,           -- JSON list
  narrative_value INTEGER,
  consequences TEXT          -- JSON list
);
```
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone

from memory_system.models import Event, TickSummary

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tick_log (
    tick_id INTEGER PRIMARY KEY,
    world_time INTEGER NOT NULL,
    narrator_produced INTEGER NOT NULL DEFAULT 0,
    narrator_chars INTEGER NOT NULL DEFAULT 0,
    agents_called TEXT NOT NULL DEFAULT '[]',
    events_generated TEXT NOT NULL DEFAULT '[]',
    state_changes_summary TEXT,
    world_time_advanced TEXT,
    next_tick_recommendations TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    tick_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    location TEXT,
    participants TEXT NOT NULL DEFAULT '[]',
    description TEXT,
    visible_to TEXT NOT NULL DEFAULT '[]',
    narrative_value INTEGER NOT NULL DEFAULT 0,
    consequences TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (tick_id) REFERENCES tick_log(tick_id)
);

CREATE INDEX IF NOT EXISTS idx_events_tick ON events(tick_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
"""


class TickDB:
    """SQLite 持久化的 tick 日志 + 事件存储。线程不安全 - 单实例单线程使用。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self.init_schema()

    def init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TickDB":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def insert_tick(
        self,
        summary: TickSummary,
        events: list[Event] | None = None,
    ) -> None:
        """事务写入 tick_log + 关联 events。Orchestrator 每 tick 调用一次。"""
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._conn.execute("BEGIN")
            self._conn.execute(
                """
                INSERT OR REPLACE INTO tick_log (
                    tick_id, world_time, narrator_produced, narrator_chars,
                    agents_called, events_generated, state_changes_summary,
                    world_time_advanced, next_tick_recommendations, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.tick,
                    summary.world_time,
                    1 if summary.narrator_produced_text else 0,
                    summary.narrator_output_chars,
                    json.dumps(summary.agents_called, ensure_ascii=False),
                    json.dumps(summary.events_generated, ensure_ascii=False),
                    summary.state_changes_summary,
                    summary.world_time_advanced,
                    json.dumps(summary.next_tick_recommendations, ensure_ascii=False),
                    now,
                ),
            )
            if events:
                self._conn.executemany(
                    """
                    INSERT OR REPLACE INTO events (
                        event_id, tick_id, event_type, location, participants,
                        description, visible_to, narrative_value, consequences
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            e.id,
                            e.tick,
                            e.type,
                            e.location,
                            json.dumps(e.participants, ensure_ascii=False),
                            e.description,
                            json.dumps(e.visible_to, ensure_ascii=False),
                            e.narrative_value,
                            json.dumps(e.consequences, ensure_ascii=False),
                        )
                        for e in events
                    ],
                )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ------------------------------------------------------------------
    # 查询(Showrunner / NoveltyCritic 用)
    # ------------------------------------------------------------------

    def get_recent_ticks(self, n: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM tick_log ORDER BY tick_id DESC LIMIT ?", (n,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_events_in_range(self, from_tick: int, to_tick: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE tick_id BETWEEN ? AND ? ORDER BY tick_id",
            (from_tick, to_tick),
        ).fetchall()
        return [self._event_row_to_dict(r) for r in rows]

    def get_event_stats(self, last_n_ticks: int = 50) -> dict:
        """事件类型分布 + 高 narrative_value 事件计数 + 平均 narrator_chars。

        供 Showrunner 评估宏观节奏: 是否平静、最近 narrator 强度等。
        """
        # 找出最近 N 个 tick_id
        tick_rows = self._conn.execute(
            "SELECT tick_id, narrator_produced, narrator_chars FROM tick_log "
            "ORDER BY tick_id DESC LIMIT ?",
            (last_n_ticks,),
        ).fetchall()
        if not tick_rows:
            return {
                "by_type": {},
                "high_value_count": 0,
                "avg_narrator_chars": 0,
                "narration_rate": 0.0,
                "ticks_sampled": 0,
            }
        tick_ids = [r["tick_id"] for r in tick_rows]
        placeholders = ",".join("?" * len(tick_ids))

        type_rows = self._conn.execute(
            f"SELECT event_type, COUNT(*) AS c FROM events "
            f"WHERE tick_id IN ({placeholders}) GROUP BY event_type",
            tick_ids,
        ).fetchall()
        by_type = {r["event_type"]: r["c"] for r in type_rows}

        high_value_row = self._conn.execute(
            f"SELECT COUNT(*) AS c FROM events "
            f"WHERE tick_id IN ({placeholders}) AND narrative_value >= 7",
            tick_ids,
        ).fetchone()
        high_value_count = high_value_row["c"] if high_value_row else 0

        narrator_chars_sum = sum(r["narrator_chars"] for r in tick_rows)
        narrator_produced_count = sum(1 for r in tick_rows if r["narrator_produced"])
        avg_chars = narrator_chars_sum / len(tick_rows) if tick_rows else 0

        return {
            "by_type": by_type,
            "high_value_count": high_value_count,
            "avg_narrator_chars": round(avg_chars, 1),
            "narration_rate": round(narrator_produced_count / len(tick_rows), 3),
            "ticks_sampled": len(tick_rows),
        }

    def get_action_patterns(self, last_n_ticks: int = 100) -> dict:
        """character_action 类事件的描述前缀分布 - 供 NoveltyCritic 检测重复模式。

        简单实现:按 description 的前 12 字符做 token 化统计。
        """
        rows = self._conn.execute(
            "SELECT description FROM events "
            "WHERE event_type='character_action' "
            "AND tick_id > (SELECT MAX(tick_id) FROM tick_log) - ? "
            "ORDER BY tick_id DESC",
            (last_n_ticks,),
        ).fetchall()
        prefix_counter: Counter = Counter()
        for r in rows:
            desc = r["description"] or ""
            prefix_counter[desc[:12]] += 1
        # 仅返回 top 20 prefixes (出现 >=2 次)
        top = [{"prefix": p, "count": c} for p, c in prefix_counter.most_common(20) if c >= 2]
        return {
            "total_actions_sampled": len(rows),
            "frequent_prefixes": top,
        }

    def get_open_loop_age_stats(self) -> dict:
        """OpenLoop 生命周期需要 TickState - 这里只提供时间窗口数据。占位接口。"""
        return {"placeholder": True}

    def count_ticks(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM tick_log").fetchone()
        return int(row["c"]) if row else 0

    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        for k in ("agents_called", "events_generated", "next_tick_recommendations"):
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except (TypeError, json.JSONDecodeError):
                    pass
        return d

    @staticmethod
    def _event_row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        for k in ("participants", "visible_to", "consequences"):
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except (TypeError, json.JSONDecodeError):
                    pass
        return d
