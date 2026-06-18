"""SQLite store — users + otp_records 两表, 共用 ``backend/data/auth.db``。

为何不复用 ticks.db: ticks.db 是每 novel 一个 (data/users/{uid}/novels/{nid}/),
而 users/otp 是全局的。独立 auth.db 让权限 / 备份 / 迁移都简单。

WAL 模式 + isolation_level=None — 让多请求并发读写不阻塞。每次操作开关
连接 — SQLite 连接对象不该跨线程, 这样最安全 (HTTP 路由在 thread pool 跑)。
"""
from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

_DEFAULT_DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "auth.db")
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    save_my_works INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    last_login_at REAL,
    password_version INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS otp_records (
    email TEXT NOT NULL,
    purpose TEXT NOT NULL,
    otp_hash TEXT NOT NULL,
    expires_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (email, purpose)
);

CREATE INDEX IF NOT EXISTS idx_otp_expires ON otp_records(expires_at);
"""


class UserStore:
    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # 写入路径只能串行 — Python 标准 sqlite3 模块在 WAL + 多写者下仍有偶发
        # database is locked. 显式互斥避免这种 race。
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # 迁移: 老 DB 没有 password_version 列, 加上 default 0 让全部已签发 token
            # 第一次过校验 (pv=0 in payload == pv=0 in db)。增量改密后 pv 自增, 旧 token 被踢。
            cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            if "password_version" not in cols:
                conn.execute(
                    "ALTER TABLE users ADD COLUMN "
                    "password_version INTEGER NOT NULL DEFAULT 0"
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # isolation_level=None — autocommit 模式, 每条 SQL 立即 commit。
        # 我们不需要事务原子化 (单行操作), 这样最简单。
        conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
        finally:
            conn.close()

    # ---- users ----------------------------------------------------------
    def get_by_email(self, email: str) -> dict | None:
        email = email.lower()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email=?", (email,)
            ).fetchone()
            return dict(row) if row else None

    def get_by_id(self, user_id: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id=?", (user_id,)
            ).fetchone()
            return dict(row) if row else None

    def create(self, email: str) -> dict:
        email = email.lower()
        user_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO users (id, email, save_my_works, created_at) "
                "VALUES (?, ?, 0, ?)",
                (user_id, email, now),
            )
            row = conn.execute(
                "SELECT * FROM users WHERE id=?", (user_id,)
            ).fetchone()
        return dict(row)

    def update_password(self, user_id: str, password_hash: str) -> int:
        """更新密码 + 自增 password_version, 返回新 password_version。

        password_version 是 JWT 失效信号: payload.pv != db.password_version 即视为
        过期, 让旧 token 立即失效 (防 session-fixation / 被盗 token 持续可用)。
        """
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash=?, "
                "password_version=password_version+1 WHERE id=?",
                (password_hash, user_id),
            )
            row = conn.execute(
                "SELECT password_version FROM users WHERE id=?", (user_id,)
            ).fetchone()
            return int(row[0]) if row else 0

    def update_save_my_works(self, user_id: str, value: bool) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE users SET save_my_works=? WHERE id=?",
                (1 if value else 0, user_id),
            )

    def touch_last_login(self, user_id: str) -> None:
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE users SET last_login_at=? WHERE id=?",
                (now, user_id),
            )

    def list_all(self) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY created_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- otp ------------------------------------------------------------
    def put_otp(
        self,
        email: str,
        purpose: str,
        otp_hash: str,
        expires_at: float,
    ) -> None:
        """覆盖式写入 — 同 (email, purpose) 上一个未消费的 OTP 被替换。

        attempts 重置为 0 让用户重新拿到 5 次尝试。
        """
        email = email.lower()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO otp_records "
                "(email, purpose, otp_hash, expires_at, attempts) "
                "VALUES (?, ?, ?, ?, 0)",
                (email, purpose, otp_hash, expires_at),
            )

    def get_otp(self, email: str, purpose: str) -> dict | None:
        email = email.lower()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM otp_records WHERE email=? AND purpose=?",
                (email, purpose),
            ).fetchone()
            return dict(row) if row else None

    def increment_otp_attempts(self, email: str, purpose: str) -> int:
        email = email.lower()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE otp_records SET attempts=attempts+1 "
                "WHERE email=? AND purpose=?",
                (email, purpose),
            )
            row = conn.execute(
                "SELECT attempts FROM otp_records WHERE email=? AND purpose=?",
                (email, purpose),
            ).fetchone()
            return int(row[0]) if row else 0

    def delete_otp(self, email: str, purpose: str) -> None:
        email = email.lower()
        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM otp_records WHERE email=? AND purpose=?",
                (email, purpose),
            )

    def purge_expired_otps(self) -> int:
        now = datetime.now(timezone.utc).timestamp()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM otp_records WHERE expires_at < ?", (now,)
            )
            return cur.rowcount


_store: UserStore | None = None
_store_lock = threading.Lock()


def get_user_store() -> UserStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = UserStore()
        return _store


def _reset_for_tests(db_path: str | None = None) -> UserStore:
    """测试钩子 — 用临时 db 替换单例。"""
    global _store
    with _store_lock:
        _store = UserStore(db_path=db_path or _DEFAULT_DB_PATH)
        return _store
