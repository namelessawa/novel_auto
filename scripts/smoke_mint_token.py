"""v2.48 smoke-test 用 — 直接往 backend/data/auth.db 写一个测试用户,
然后用 .env 里固定的 JWT_SECRET 签一个 token 出来。

设计取舍:
- 不走 OTP/邮件: 那需要 SMTP, 太重
- 不复用 UserStore singleton: 那需要 backend 进程注入, 太脏
- 直接 sqlite3 + jose.jwt.encode: 共享 DB 文件, JWT_SECRET 经 .env 共享

跑完后 backend 该用户立即可用 (sqlite WAL, 无需重启).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# load .env so JWT_SECRET 跟 backend 一致
from dotenv import load_dotenv

load_dotenv()

from jose import jwt  # noqa: E402

ROOT = Path(__file__).parent
DB_PATH = ROOT / "backend" / "data" / "auth.db"
EMAIL = "smoke@local.test"

JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    print("ERROR: JWT_SECRET not in env — backend uses random secret, tokens won't validate", file=sys.stderr)
    sys.exit(1)

# Upsert user
con = sqlite3.connect(str(DB_PATH), isolation_level=None, timeout=10)
con.row_factory = sqlite3.Row
row = con.execute("SELECT id, password_version FROM users WHERE email=?", (EMAIL,)).fetchone()
if row:
    user_id = row["id"]
    pv = int(row["password_version"] or 0)
    print(f"# reuse user id={user_id} pv={pv}", file=sys.stderr)
else:
    user_id = uuid.uuid4().hex
    now_ts = datetime.now(timezone.utc).timestamp()
    con.execute(
        "INSERT INTO users (id, email, save_my_works, created_at) VALUES (?, ?, 0, ?)",
        (user_id, EMAIL, now_ts),
    )
    pv = 0
    print(f"# created user id={user_id}", file=sys.stderr)
con.close()

# Mint JWT
now = datetime.now(timezone.utc)
payload = {
    "sub": user_id,
    "email": EMAIL,
    "pv": pv,
    "jti": uuid.uuid4().hex,
    "iat": int(now.timestamp()),
    "exp": int((now + timedelta(hours=1)).timestamp()),
}
token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
print(token)
