"""加载 ``config.json`` 的 auth + smtp 段为 dataclass。

每次调用 ``get_auth_config() / get_smtp_config()`` 都会重读 config.json —
让 hot-reload 路径 (改 jwt_secret / smtp 凭据后) 立即生效, 不必重启进程。
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import dataclass

# backend/auth/config.py → ../../config.json (项目根)
_CONFIG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
)

_runtime_jwt_secret: str | None = None
_secret_lock = threading.Lock()


@dataclass(frozen=True)
class AuthConfig:
    enabled: bool = True
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_ttl_days: int = 7
    otp_ttl_seconds: int = 300
    otp_send_per_ip_per_hour: int = 3
    otp_send_per_email_per_hour: int = 3
    otp_verify_per_ip_per_15min: int = 10
    password_login_per_ip_per_15min: int = 5
    password_login_per_email_per_15min: int = 5
    ephemeral_ttl_hours: int = 24
    cleanup_interval_seconds: int = 3600


@dataclass(frozen=True)
class SMTPConfig:
    host: str = ""
    port: int = 465
    use_ssl: bool = True
    user: str = ""
    password: str = ""
    from_addr: str = ""
    from_name: str = "NovelAuto"

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password and self.from_addr)


def _load_config() -> dict:
    if not os.path.isfile(_CONFIG_PATH):
        return {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _get_or_create_runtime_secret() -> str:
    """生成进程内随机 secret — fallback 当 config.json 没填 jwt_secret。

    缺点: 重启进程已签发的 token 立即失效。生产应在 config.json 显式设置。
    """
    global _runtime_jwt_secret
    with _secret_lock:
        if _runtime_jwt_secret is None:
            _runtime_jwt_secret = secrets.token_urlsafe(64)
        return _runtime_jwt_secret


def get_auth_config() -> AuthConfig:
    raw = _load_config().get("auth", {}) or {}
    secret = raw.get("jwt_secret") or _get_or_create_runtime_secret()
    return AuthConfig(
        enabled=bool(raw.get("enabled", True)),
        jwt_secret=secret,
        jwt_algorithm=raw.get("jwt_algorithm", "HS256"),
        jwt_ttl_days=int(raw.get("jwt_ttl_days", 7)),
        otp_ttl_seconds=int(raw.get("otp_ttl_seconds", 300)),
        otp_send_per_ip_per_hour=int(raw.get("otp_send_per_ip_per_hour", 3)),
        otp_send_per_email_per_hour=int(raw.get("otp_send_per_email_per_hour", 3)),
        otp_verify_per_ip_per_15min=int(raw.get("otp_verify_per_ip_per_15min", 10)),
        password_login_per_ip_per_15min=int(
            raw.get("password_login_per_ip_per_15min", 5)
        ),
        password_login_per_email_per_15min=int(
            raw.get("password_login_per_email_per_15min", 5)
        ),
        ephemeral_ttl_hours=int(raw.get("ephemeral_ttl_hours", 24)),
        cleanup_interval_seconds=int(raw.get("cleanup_interval_seconds", 3600)),
    )


def get_smtp_config() -> SMTPConfig:
    raw = _load_config().get("smtp", {}) or {}
    return SMTPConfig(
        host=str(raw.get("host", "")),
        port=int(raw.get("port", 465)),
        use_ssl=bool(raw.get("use_ssl", True)),
        user=str(raw.get("user", "")),
        password=str(raw.get("password", "")),
        from_addr=str(raw.get("from_addr", "")),
        from_name=str(raw.get("from_name", "NovelAuto")),
    )
