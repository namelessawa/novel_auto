"""bcrypt 包装 — passlib + bcrypt backend, cost=12。

cost=12 是 2026 年安全/性能均衡: ~250ms/hash 在现代 CPU, 攻击者爆破不
经济, 用户登录无感。如未来 CPU 进一步快可调到 13。
"""
from __future__ import annotations

import logging

from passlib.context import CryptContext

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(password: str) -> str:
    """bcrypt 哈希一个密码 (含随机 salt, 同输入输出不同)。

    raises: ValueError — 密码超过 bcrypt 上限 (72 字节 utf-8)
    """
    # bcrypt 截断 72 字节 — passlib 1.7.5+ 抛 ValueError, 老版本静默截断。
    # 我们在 Pydantic max_length=128 已挡, 但 utf-8 中文 1 字符=3 字节
    # → 24 中文字符就到 72 字节边界。这里显式校验。
    if len(password.encode("utf-8")) > 72:
        raise ValueError("密码过长 (bcrypt 限制 72 字节, 中文约 24 字)")
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """常数时间比较 — 失败/异常都返回 False, 不抛。"""
    if not hashed:
        return False
    try:
        return _pwd_context.verify(password, hashed)
    except Exception as e:
        logger.warning("password verify exception: %s", e)
        return False
