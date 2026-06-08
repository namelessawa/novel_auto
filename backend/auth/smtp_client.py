"""SMTP — 发送 OTP 验证码邮件。aiosmtplib 异步, 不阻塞 event loop。

腾讯企业邮箱: smtp.exmail.qq.com:465 (SSL)。授权码 ≠ 登录密码。
``from_addr`` 必须与 ``user`` 同账号 (反垃圾邮件检查)。
"""
from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from .config import get_smtp_config

logger = logging.getLogger(__name__)


class SMTPError(Exception):
    pass


async def send_otp_email(to_addr: str, code: str, purpose: str = "登录") -> None:
    cfg = get_smtp_config()
    if not cfg.configured:
        raise SMTPError(
            "SMTP 未配置 — config.json 的 smtp 段缺少 host/user/password/from_addr"
        )

    msg = EmailMessage()
    if cfg.from_name:
        msg["From"] = f"{cfg.from_name} <{cfg.from_addr}>"
    else:
        msg["From"] = cfg.from_addr
    msg["To"] = to_addr
    msg["Subject"] = f"【NovelAuto】您的{purpose}验证码: {code}"
    msg.set_content(
        f"您的{purpose}验证码是 {code}\n\n"
        f"验证码 5 分钟内有效。如果不是本人操作请忽略此邮件。\n\n"
        f"-- NovelAuto"
    )

    try:
        # 465 SSL: use_tls=True (隐式 SSL, 握手即 TLS)
        # 587 STARTTLS: use_tls=False, start_tls=True
        await aiosmtplib.send(
            msg,
            hostname=cfg.host,
            port=cfg.port,
            username=cfg.user,
            password=cfg.password,
            use_tls=cfg.use_ssl,
            start_tls=False if cfg.use_ssl else True,
            timeout=15,
        )
        logger.info("OTP email sent to %s (purpose=%s)", to_addr, purpose)
    except aiosmtplib.SMTPException as e:
        logger.error("SMTP send failed to %s: %s", to_addr, e)
        raise SMTPError(f"SMTP 发送失败: {e}") from e
    except Exception as e:
        logger.exception("SMTP unexpected error to %s", to_addr)
        raise SMTPError(f"SMTP 未知错误: {e}") from e
