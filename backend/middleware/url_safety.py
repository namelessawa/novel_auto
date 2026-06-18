"""SSRF-safe URL validation.

用户可以通过 ``X-User-LLM-Base-Url`` / ``X-Image-Endpoint`` 把任意 URL 传给后端,
后端会 HTTP / WSS 连过去。不校验 → 攻击者能让后端打内网 (127.0.0.1, 10.0.0.0/8,
169.254.169.254 metadata 等), 等价 SSRF。

本模块给出 ``is_safe_public_url`` — 仅放行公网 http/https/ws/wss + 非保留地址。

不做 DNS 解析校验 (DNS rebinding 防御): 受信连接默认走 SDK 自身 timeout +
后端在生产应该跑在受限 egress 网络下。这里挡的是 "用户直接写 127.0.0.1" 这类
基本攻击。
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https", "ws", "wss"})


def _hostname_is_private(host: str) -> bool:
    """判断 hostname 是否指向内网/保留地址。

    - 直接 IP 字面量: 用 ipaddress 判断 (loopback / private / link-local / reserved)
    - 域名: 用启发式黑名单 (localhost / *.local / *.internal / *.lan)
    """
    if not host:
        return True
    h = host.strip().lower()
    if h in {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}:
        return True
    if h.endswith(".local") or h.endswith(".internal") or h.endswith(".lan"):
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def is_safe_public_url(url: str) -> bool:
    """放行: scheme 在白名单 + host 是公网域名/IP。

    返回 False 的情形:
    - 空字符串 / None
    - scheme 不是 http/https/ws/wss
    - host 解析为内网/保留 IP
    - host 是 localhost / *.local 等明显内网名
    """
    if not url:
        return False
    try:
        p = urlparse(url.strip())
    except ValueError:
        return False
    if p.scheme.lower() not in _ALLOWED_SCHEMES:
        return False
    if not p.hostname:
        return False
    return not _hostname_is_private(p.hostname)
