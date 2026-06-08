"""科大讯飞 Spark 图片生成 (Text-to-Image) WebSocket 客户端。

文档: https://www.xfyun.cn/doc/spark/图片生成.html

API 形态
--------
WebSocket: ``wss://spark-api.cn-huabei-1.xf-yun.com/v2.1/tti``
鉴权: URL query string 携带 HMAC-SHA256 签名 (host + date + request-line)。

请求 JSON 结构 (单条):
    {
      "header": {"app_id": ..., "uid": "novel_auto"},
      "parameter": {"chat": {"domain": "general", "width": 512, "height": 512}},
      "payload": {"message": {"text": [{"role": "user", "content": "prompt"}]}}
    }

响应是若干 WebSocket 帧, 每帧 payload.choices.text[].content 是 base64 切片;
header.status == 2 表示流结束, 拼接全部 content 即完整图。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urlencode

import websockets
import websockets.exceptions

logger = logging.getLogger(__name__)

XFYUN_DEFAULT_HOST = "spark-api.cn-huabei-1.xf-yun.com"
XFYUN_DEFAULT_PATH = "/v2.1/tti"


class XfyunImageError(Exception):
    """通用 xfyun 调用错误 — routes 层 502/400 透传。"""


def _sign_url(api_key: str, api_secret: str, host: str, path: str) -> str:
    """生成带 HMAC-SHA256 签名的 wss:// URL — xfyun spark 系列通用鉴权。"""
    date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode()
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode()
    params = {
        "authorization": authorization,
        "date": date,
        "host": host,
    }
    return f"wss://{host}{path}?{urlencode(params)}"


async def generate_image(
    *,
    app_id: str,
    api_key: str,
    api_secret: str,
    prompt: str,
    width: int = 512,
    height: int = 512,
    host: str = XFYUN_DEFAULT_HOST,
    path: str = XFYUN_DEFAULT_PATH,
    timeout: float = 60.0,
) -> str:
    """调用 xfyun 文生图, 返回 base64 编码的 PNG 图像数据。

    raises
    ------
    XfyunImageError — 凭据缺失 / 鉴权失败 / 网络问题 / xfyun 业务错误码。
    """
    if not (app_id and api_key and api_secret):
        raise XfyunImageError("xfyun 凭据不完整 (需要 AppID + APISecret + APIKey)")

    url = _sign_url(api_key, api_secret, host, path)
    request_body = {
        "header": {"app_id": app_id, "uid": "novel_auto"},
        "parameter": {
            "chat": {
                "domain": "general",
                "width": int(width),
                "height": int(height),
            }
        },
        "payload": {
            "message": {
                "text": [{"role": "user", "content": prompt}],
            }
        },
    }

    chunks: list[str] = []
    try:
        async with asyncio.timeout(timeout):
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps(request_body, ensure_ascii=False))
                async for message in ws:
                    data = json.loads(message)
                    header = data.get("header", {}) or {}
                    code = header.get("code", 0)
                    if code != 0:
                        raise XfyunImageError(
                            f"xfyun error code={code}: "
                            f"{header.get('message', 'unknown')}"
                        )
                    choices = (data.get("payload") or {}).get("choices") or {}
                    for t in choices.get("text", []) or []:
                        content = t.get("content") or ""
                        if content:
                            chunks.append(content)
                    if header.get("status") == 2:
                        break
    except asyncio.TimeoutError as e:
        raise XfyunImageError(f"xfyun 调用超时 ({timeout}s)") from e
    except XfyunImageError:
        raise
    except Exception as e:
        # 不再细分异常类 — websockets 11/12/13 把 InvalidStatusCode 改名为
        # InvalidStatus, 子类化也乱; 统一抓 + 把 type/status/message 全挖出来,
        # 保证 detail 永远非空, 用户能定位.
        type_name = type(e).__name__
        text = str(e).strip() or repr(e)
        # 尝试多种 attribute path 提取 HTTP 状态码
        status_code = (
            getattr(e, "status_code", None)
            or getattr(getattr(e, "response", None), "status_code", None)
            or getattr(e, "code", None)
        )
        if status_code:
            hint = ""
            if status_code in (401, 403):
                hint = " — 多半是 AppID/APIKey/APISecret 错或不属于同一应用"
            raise XfyunImageError(
                f"xfyun 握手失败 (HTTP {status_code}, {type_name}){hint}"
            ) from e
        # 最后 fallback — 至少给出 type + 文字
        logger.warning("xfyun unexpected exception type=%s text=%r", type_name, text)
        raise XfyunImageError(f"xfyun 调用失败 ({type_name}): {text}") from e

    if not chunks:
        raise XfyunImageError("xfyun 未返回图像数据 (response empty)")

    full = "".join(chunks)
    # 简单合法性校验 — base64 不合法直接报错
    try:
        base64.b64decode(full, validate=True)
    except (ValueError, base64.binascii.Error) as e:
        raise XfyunImageError(f"xfyun 返回非法 base64: {e}") from e
    return full
