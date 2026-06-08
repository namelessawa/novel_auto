"""科大讯飞 Spark 图片生成 (Text-to-Image) v2.1/tti — HTTPS POST 客户端.

文档: https://www.xfyun.cn/doc/spark/图片生成.html

协议
----
* 不是 WebSocket — Spark Chat 是 wss, 但图片生成 v2.1/tti 是 https POST
* URL: ``https://spark-api.cn-huabei-1.xf-yun.com/v2.1/tti?authorization=...&date=...&host=...``
* 鉴权: HMAC-SHA256 签名作为 query string (与 wss 鉴权同源, 只是 request-line 用 POST)
* Body: header / parameter.chat / payload.message JSON
* 响应: 单条 JSON, payload.choices.text[].content 是完整 base64 PNG

v2.30 前的实现用 wss:// 走 WebSocket 握手, 对端立即 RST (ConnectionResetError)
就是因为协议错: tti 端点根本不支持 WebSocket upgrade.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

XFYUN_DEFAULT_HOST = "spark-api.cn-huabei-1.xf-yun.com"
XFYUN_DEFAULT_PATH = "/v2.1/tti"


class XfyunImageError(Exception):
    """通用 xfyun 调用错误 — routes 层 502/400 透传."""


def _sign_params(
    *,
    api_key: str,
    api_secret: str,
    host: str,
    path: str,
    method: str = "POST",
) -> dict[str, str]:
    """生成 HMAC-SHA256 query string 鉴权参数.

    讯飞规范: signature_origin = "host: {host}\\ndate: {date}\\n{METHOD} {path} HTTP/1.1"
    HMAC-SHA256(api_secret, signature_origin) → base64 → signature.
    Authorization = base64('api_key="...", algorithm="hmac-sha256", headers="host date request-line", signature="..."')
    """
    date = format_datetime(datetime.now(timezone.utc), usegmt=True)
    signature_origin = f"host: {host}\ndate: {date}\n{method} {path} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode()
    auth_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(auth_origin.encode("utf-8")).decode()
    return {
        "authorization": authorization,
        "date": date,
        "host": host,
    }


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
    """调用 xfyun 图片生成, 返回 base64 编码的 PNG.

    raises XfyunImageError: 凭据缺失 / 鉴权失败 / 网络问题 / xfyun 业务错误码.
    """
    if not (app_id and api_key and api_secret):
        raise XfyunImageError("xfyun 凭据不完整 (需要 AppID + APISecret + APIKey)")

    params = _sign_params(
        api_key=api_key, api_secret=api_secret, host=host, path=path, method="POST"
    )
    url = f"https://{host}{path}?" + urlencode(params)

    body = {
        "header": {"app_id": app_id},
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

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=body)
    except httpx.TimeoutException as e:
        raise XfyunImageError(f"xfyun HTTPS 请求超时 ({timeout}s)") from e
    except httpx.HTTPError as e:
        type_name = type(e).__name__
        text = str(e).strip() or repr(e)
        raise XfyunImageError(f"xfyun HTTPS 错误 ({type_name}): {text}") from e
    except Exception as e:  # pragma: no cover
        type_name = type(e).__name__
        text = str(e).strip() or repr(e)
        logger.warning("xfyun unexpected exception type=%s text=%r", type_name, text)
        raise XfyunImageError(f"xfyun 调用失败 ({type_name}): {text}") from e

    if resp.status_code != 200:
        snippet = (resp.text or "(empty body)")[:400]
        hint = ""
        if resp.status_code in (401, 403):
            hint = " — 多半是 AppID/APIKey/APISecret 错或不属于同一应用"
        elif resp.status_code == 404:
            hint = " — 端点 path 不对, 讯飞控制台对照确认"
        raise XfyunImageError(
            f"xfyun HTTP {resp.status_code}{hint}: {snippet}"
        )

    try:
        data = resp.json()
    except ValueError as e:
        raise XfyunImageError(
            f"xfyun 返回非 JSON: {resp.text[:300]}"
        ) from e

    header = data.get("header", {}) or {}
    code = header.get("code", 0)
    if code != 0:
        raise XfyunImageError(
            f"xfyun error code={code}: {header.get('message', 'unknown')}"
        )

    choices = (data.get("payload") or {}).get("choices") or {}
    chunks: list[str] = []
    for t in choices.get("text", []) or []:
        content = t.get("content") or ""
        if content:
            chunks.append(content)

    if not chunks:
        raise XfyunImageError(
            f"xfyun 未返回图像数据; 响应 head: {json.dumps(data)[:300]}"
        )

    full = "".join(chunks)
    try:
        base64.b64decode(full, validate=True)
    except (ValueError, binascii.Error) as e:
        raise XfyunImageError(f"xfyun 返回非法 base64: {e}") from e
    return full
