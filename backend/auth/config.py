"""加载 ``config.json`` 的 auth + smtp 段为 dataclass。

``get_smtp_config()`` 每次重读 config.json; ``get_auth_config()`` 自 v2.37
起基于文件 mtime 缓存 — mtime 未变直接返回缓存的 frozen dataclass, 文件被
修改后 mtime 变化自动失效, hot-reload 语义保持不变 (无 TTL)。
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
    # v2.37 — False (默认/直连部署): get_client_ip 只信 request.client.host,
    # 防止客户端伪造 X-Forwarded-For / CF-Connecting-IP 绕过按 IP 限流。
    # 部署在 Cloudflare Tunnel / nginx 反代之后时必须显式设 true, 否则所有
    # 用户共享代理出口 IP, 限流会误伤。
    trusted_proxy: bool = False


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
    """生成进程内随机 secret — fallback 当 config.json/env 没填 jwt_secret。

    缺点: 重启进程已签发的 token 立即失效。生产应在 ``JWT_SECRET`` env 或
    ``config.json`` 显式设置。第一次生成时打 WARNING, 让运维注意到。
    """
    global _runtime_jwt_secret
    with _secret_lock:
        if _runtime_jwt_secret is None:
            _runtime_jwt_secret = secrets.token_urlsafe(64)
            import logging
            logging.getLogger(__name__).warning(
                "[auth] JWT_SECRET 未设置 — 使用进程内随机 secret. 进程重启后"
                "所有已签发 token 立即失效。生产请设置 JWT_SECRET env var 或"
                "config.json auth.jwt_secret。"
            )
        return _runtime_jwt_secret


# v2.37 — get_auth_config 的 mtime 缓存: (mtime, AuthConfig)。AuthConfig 是
# frozen dataclass, 跨线程共享只读安全。锁仅保护缓存元组的读写一致性。
_auth_cfg_cache: tuple[float, AuthConfig] | None = None
_auth_cfg_lock = threading.Lock()


def _config_mtime() -> float:
    try:
        return os.path.getmtime(_CONFIG_PATH)
    except OSError:
        return -1.0  # 文件不存在 — 用哨兵值, 文件出现后 mtime 变化即失效


def get_auth_config() -> AuthConfig:
    """读 auth 段, 基于 config.json mtime 缓存。

    此前每请求重读 + 重 parse config.json (get_current_user 热路径)。现在
    mtime 未变直接返回缓存; 文件修改 → mtime 变化 → 自动重读, 无 TTL。
    """
    global _auth_cfg_cache
    mtime = _config_mtime()
    with _auth_cfg_lock:
        cached = _auth_cfg_cache
        if cached is not None and cached[0] == mtime:
            return cached[1]

    raw = _load_config().get("auth", {}) or {}
    # secret 优先级: env JWT_SECRET > config.json auth.jwt_secret > 进程内随机.
    # 进程内随机是兜底, 进程重启时已签发 token 立即失效, 仅用于 dev / 临时部署。
    secret = (
        os.environ.get("JWT_SECRET", "").strip()
        or raw.get("jwt_secret")
        or _get_or_create_runtime_secret()
    )
    cfg = AuthConfig(
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
        trusted_proxy=bool(raw.get("trusted_proxy", False)),
    )
    with _auth_cfg_lock:
        _auth_cfg_cache = (mtime, cfg)
    return cfg


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
