"""SMTP — 发送 OTP 验证码邮件 (text + HTML multipart)。

腾讯企业邮箱: smtp.exmail.qq.com:465 (SSL)。授权码 ≠ 登录密码。
``from_addr`` 必须与 ``user`` 同账号 (反垃圾邮件检查)。

v2.27 — HTML 模板. 邮件客户端 (Gmail / Outlook / 网易 / iOS Mail) 都 render
HTML; 旧的纯文本 client / 屏幕阅读器走 plain fallback。
"""
from __future__ import annotations

import logging
from email.message import EmailMessage
from email.utils import make_msgid

import aiosmtplib

from .config import get_smtp_config

logger = logging.getLogger(__name__)


class SMTPError(Exception):
    pass


# 内联 CSS — 多数邮件客户端会剥掉 <style>, 关键样式必须 inline。
# 极简: brand 头 + 大字号 OTP 圈 + 灰色脚注。深色主题在 Gmail 上自动反色,
# 浅色背景在 iOS Dark Mode 不会被压成全黑, 故全部走浅色 + 一点点紫。
_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NovelAuto 验证码</title>
</head>
<body style="margin:0;padding:0;background:#f4f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;color:#1f2330;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#f4f5f9;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="480" style="max-width:480px;background:#ffffff;border-radius:12px;box-shadow:0 4px 16px rgba(34,40,60,0.06);overflow:hidden;">
          <tr>
            <td style="padding:32px 36px 8px 36px;text-align:left;">
              <div style="font-size:13px;color:#8b5cf6;letter-spacing:2px;font-weight:600;">NOVELAUTO</div>
              <div style="font-size:20px;font-weight:600;color:#1f2330;margin-top:6px;">您的{purpose_label}验证码</div>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 36px 16px 36px;">
              <div style="font-size:14px;color:#6b7080;line-height:1.6;">
                请在 5 分钟内输入下方验证码完成{purpose_label}。
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:0 36px 8px 36px;">
              <div style="background:linear-gradient(135deg,#8b5cf6 0%,#06b6d4 100%);border-radius:10px;padding:24px;text-align:center;">
                <div style="font-size:11px;color:rgba(255,255,255,0.75);letter-spacing:3px;font-weight:600;">VERIFICATION CODE</div>
                <div style="font-size:36px;font-weight:700;color:#ffffff;letter-spacing:10px;font-family:'SF Mono','Menlo','Consolas',monospace;margin-top:10px;">{code}</div>
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 36px 8px 36px;">
              <div style="font-size:12px;color:#9ca3af;line-height:1.7;">
                · 验证码 5 分钟内有效, 输错 5 次需重新获取<br>
                · 如果不是您本人操作, 请忽略此邮件
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 36px 28px 36px;border-top:1px solid #f0f1f5;margin-top:8px;">
              <div style="font-size:11px;color:#aab0bd;text-align:center;">
                此邮件由 NovelAuto 自动发出, 请勿回复
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

_PLAIN_TEMPLATE = (
    "您的{purpose_label}验证码: {code}\n"
    "\n"
    "请在 5 分钟内输入, 输错 5 次需重新获取。\n"
    "如果不是您本人操作, 请忽略此邮件。\n"
    "\n"
    "-- NovelAuto"
)


async def send_otp_email(to_addr: str, code: str, purpose: str = "登录") -> None:
    cfg = get_smtp_config()
    if not cfg.configured:
        raise SMTPError(
            "SMTP 未配置 — config.json 的 smtp 段缺少 host/user/password/from_addr"
        )

    purpose_label = purpose  # "登录" / "注册"

    msg = EmailMessage()
    if cfg.from_name:
        msg["From"] = f"{cfg.from_name} <{cfg.from_addr}>"
    else:
        msg["From"] = cfg.from_addr
    msg["To"] = to_addr
    msg["Subject"] = f"【NovelAuto】您的{purpose_label}验证码: {code}"
    # 给 Gmail 等帮助降低进 spam 的可能 — 显式 Message-ID 用 from_addr 的域名
    msg["Message-ID"] = make_msgid(domain=cfg.from_addr.split("@")[-1])

    # plain 在前, html 在后 — RFC 2046 alternative 顺序: 最后一个最优先
    msg.set_content(_PLAIN_TEMPLATE.format(code=code, purpose_label=purpose_label))
    msg.add_alternative(
        _HTML_TEMPLATE.format(code=code, purpose_label=purpose_label),
        subtype="html",
    )

    try:
        # 465 SSL: use_tls=True; 587 STARTTLS: use_tls=False, start_tls=True
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
