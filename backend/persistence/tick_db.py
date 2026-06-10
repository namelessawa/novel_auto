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
import threading
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
    """SQLite 持久化的 tick 日志 + 事件存储。

    v2.26 — 多租户改造后, 同一 TickDB 实例可能被 FastAPI thread pool 的不同
    worker 线程同时访问 (Depends 解析 runtime → runtime.tick_db.query 在 sync
    handler 里走 thread executor)。SQLite 默认 ``check_same_thread=True`` 会
    抛 ProgrammingError; 必须显式关掉 + 上互斥锁。

    锁粒度: 整个 ``_conn`` 操作串行。读写都不重叠 — autocommit 模式下并发
    ``BEGIN`` 会冲突 (transaction within transaction), 直接 lock 最稳。
    tick 操作频次很低 (秒级), 锁竞争不是瓶颈。
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        # check_same_thread=False — 允许跨线程使用 (锁保证安全, 见上注释)
        self._conn = sqlite3.connect(
            self._db_path, isolation_level=None, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        # 所有操作必须经过这把锁 — 包括 init_schema / 查询 / 写入。
        self._lock = threading.Lock()
        self.init_schema()

    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        # 幂等: 多个路径都可能 close (drop_cache / reload_cache / close_all_runtimes /
        # __exit__ / FastAPI shutdown), 避免 Python 3.10- 的双关报 ProgrammingError.
        with self._lock:
            if self._conn is None:
                return
            try:
                self._conn.close()
            finally:
                self._conn = None

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
        """事务写入 tick_log + 关联 events。Orchestrator 每 tick 调用一次。

        v2.21 — 冲突策略:
        - tick_log: ``INSERT OR IGNORE`` — 同 tick_id 重复(Orchestrator 重入
          或恢复后重放) 跳过, 保留首次记录, 不覆盖已生成事件统计。
        - events:   ``INSERT OR IGNORE`` — LLM 复用 event_id 时不静默覆盖原始
          事件; 改为 WARN 日志 + 跳过, Showrunner/NoveltyCritic 的历史统计保
          持稳定。此前 INSERT OR REPLACE 会把旧 description/narrative_value
          擦掉, 污染下游窗口聚合。
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                cur = self._conn.execute(
                    """
                    INSERT OR IGNORE INTO tick_log (
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
                if cur.rowcount == 0:
                    logger.warning(
                        "TickDB.insert_tick: tick_id=%d already exists, kept original record",
                        summary.tick,
                    )
                if events:
                    for e in events:
                        cur = self._conn.execute(
                            """
                            INSERT OR IGNORE INTO events (
                                event_id, tick_id, event_type, location, participants,
                                description, visible_to, narrative_value, consequences
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
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
                            ),
                        )
                        if cur.rowcount == 0:
                            logger.warning(
                                "TickDB.insert_tick: event_id=%s already exists at tick=%d, kept original",
                                e.id,
                                e.tick,
                            )
                self._conn.execute("COMMIT")
            except Exception:
                # _conn 可能已被 close() 置 None (例如 close 后仍有调用方写入,
                # BEGIN 抛 AttributeError 进到这里) — 直接 ROLLBACK 会二次
                # AttributeError 把原始异常掩盖掉。
                if self._conn is not None:
                    try:
                        self._conn.execute("ROLLBACK")
                    except sqlite3.Error:
                        logger.warning(
                            "TickDB ROLLBACK failed in insert_tick error path",
                            exc_info=True,
                        )
                raise

    # ------------------------------------------------------------------
    # 查询(Showrunner / NoveltyCritic 用)
    # ------------------------------------------------------------------

    def get_recent_ticks(self, n: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tick_log ORDER BY tick_id DESC LIMIT ?", (n,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_events_in_range(self, from_tick: int, to_tick: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE tick_id BETWEEN ? AND ? ORDER BY tick_id",
                (from_tick, to_tick),
            ).fetchall()
        return [self._event_row_to_dict(r) for r in rows]

    def get_event_stats(self, last_n_ticks: int = 50) -> dict:
        """事件类型分布 + 高 narrative_value 事件计数 + 平均 narrator_chars。

        供 Showrunner 评估宏观节奏: 是否平静、最近 narrator 强度等。
        """
        with self._lock:
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
            high_value_count = int(high_value_row["c"]) if high_value_row else 0

            # 锁内把 sqlite3.Row 拷贝为纯 Python 数据 — 不让 Row 对象逃出
            # 锁的作用域, 之后的聚合不再依赖连接相关对象。
            sampled = [
                (int(r["narrator_chars"] or 0), bool(r["narrator_produced"]))
                for r in tick_rows
            ]

        narrator_chars_sum = sum(chars for chars, _ in sampled)
        narrator_produced_count = sum(1 for _, produced in sampled if produced)
        avg_chars = narrator_chars_sum / len(sampled) if sampled else 0

        return {
            "by_type": by_type,
            "high_value_count": high_value_count,
            "avg_narrator_chars": round(avg_chars, 1),
            "narration_rate": round(narrator_produced_count / len(sampled), 3),
            "ticks_sampled": len(sampled),
        }

    def get_action_patterns(self, last_n_ticks: int = 100) -> dict:
        """character_action 类事件的描述前缀分布 - 供 NoveltyCritic 检测重复模式。

        简单实现:按 description 的前 12 字符做 token 化统计。
        """
        with self._lock:
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
        with self._lock:
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
        # v2.17 — 兼容别名层。SQL 列名(insert_tick 路径写入)与应用层
        # ``TickSummary`` 字段名不一致, 不在边界处对齐就会让消费方拿到 None:
        #   * tick_id            ↔ tick
        #   * narrator_produced  ↔ narrator_produced_text  (bool, DB 是 0/1)
        #   * narrator_chars     ↔ narrator_output_chars
        # 统一保留两个键, 旧/新调用方都不再踩坑。
        if "tick_id" in d and "tick" not in d:
            d["tick"] = d["tick_id"]
        if "narrator_produced" in d and "narrator_produced_text" not in d:
            d["narrator_produced_text"] = bool(d["narrator_produced"])
        if "narrator_chars" in d and "narrator_output_chars" not in d:
            d["narrator_output_chars"] = d["narrator_chars"]
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
