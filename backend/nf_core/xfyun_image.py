"""科大讯飞 MaaS 图片生成 (Text-to-Image) /v2.1/tti — HTTPS POST 客户端.

文档: https://www.xfyun.cn/doc/spark/图片生成.html

协议
----
* HTTPS POST (非 WebSocket)
* 鉴权: HMAC-SHA256 签名作为 query string (host/date/request-line)
* 默认 host: ``maas-api.cn-huabei-1.xf-yun.com`` (MaaS 平台, 跑 Qwen / 通用 模型)
  备用 host: ``xingchen-api.cn-huabei-1.xf-yun.com`` (Kolors 模型专用)
  老的 ``spark-api.cn-huabei-1.xf-yun.com`` 是 Spark Chat, 不是图片生成

请求 body
---------
``header.app_id`` 必填; ``uid`` 可选; ``patch_id`` 可选 (LoRA 列表)
``parameter.chat``: domain (= modelid), width, height, seed,
  num_inference_steps, guidance_scale, scheduler 全部必填
``payload.message.text[0]`` user content
``payload.negative_prompts.text`` 可选

支持的分辨率: 768x768 / 1024x1024 / 576x1024 / 768x1024 / 1024x576 / 1024x768
支持的 scheduler: DPM++ 2M Karras / DPM++ SDE Karras / DDIM / Euler a / Euler
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import secrets as _secrets
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urlencode, urlparse

import httpx

logger = logging.getLogger(__name__)

XFYUN_DEFAULT_ENDPOINT = "https://maas-api.cn-huabei-1.xf-yun.com/v2.1/tti"

# v2.33 安全 — endpoint hostname 白名单. 用户传 X-Image-Endpoint header 时,
# 必须命中这里, 否则拒掉. 防 SSRF: 攻击者把 endpoint 指到 169.254.169.254 / 内网
# 也能拿到我们签出去的 HMAC headers, 从而盗用讯飞凭据.
# 讯飞官方有多个 region host, 全部列出 — 用户走哪个 region 都行.
_ALLOWED_ENDPOINT_HOSTS: frozenset[str] = frozenset({
    "maas-api.cn-huabei-1.xf-yun.com",
    "maas-api.cn-huabei-3.xf-yun.com",
    "xingchen-api.cn-huabei-1.xf-yun.com",  # Kolors 专用
    "spark-api.cn-huabei-1.xf-yun.com",     # 部分模型保留
})

# 文档列出的合法分辨率组合 — 偏离这个集合 → code=10005
SUPPORTED_RESOLUTIONS: frozenset[tuple[int, int]] = frozenset({
    (768, 768),
    (1024, 1024),
    (576, 1024),
    (768, 1024),
    (1024, 576),
    (1024, 768),
})

SUPPORTED_SCHEDULERS: frozenset[str] = frozenset({
    "DPM++ 2M Karras",
    "DPM++ SDE Karras",
    "DDIM",
    "Euler a",
    "Euler",
})

# 业务错误码 → 中文 hint, 用户看到立刻知道怎么修.
_XFYUN_CODE_HINTS: dict[int, str] = {
    10003: "消息格式错误 — 请求体 JSON 结构有问题",
    10004: "schema 错误 — body 缺必填字段",
    10005: (
        "参数值错误 — width/height 必须是 768x768 / 1024x1024 / 576x1024 / "
        "768x1024 / 1024x576 / 1024x768 之一; scheduler 必须在文档列表里"
    ),
    10008: "服务容量不足 — 讯飞侧拥堵, 重试",
    10021: "输入审核不通过 — 提示词被讯飞内容审核拦截",
    10022: "图片审核不通过 — 生成结果触发了讯飞内容审核",
    # 旧码 (保留兼容老的错误)
    10110: "鉴权失败 — APIKey/APISecret 错或容器时区漂移 (>5min)",
    10160: "AppID 不存在或填错位置 (App ID/APIKey/APISecret 别填混)",
    10165: "domain 字段不对 — 检查 ModelID 填的是否正确",
    11200: "服务无权限 — 讯飞控制台开通对应服务",
    11201: (
        "AppID 未开通该模型服务 — 关键: 不同模型 (general/xopqwentti20b/Kolors) "
        "需分别在讯飞 MaaS 平台开通; host 也要对应 (maas-api / xingchen-api)"
    ),
    11202: "授权额度用完 / 已过期",
    11203: "并发限流 — 等几秒重试",
}


def _format_business_error(code: int, message: str) -> str:
    hint = _XFYUN_CODE_HINTS.get(code)
    if hint:
        return f"xfyun error code={code} ({message}) — {hint}"
    return f"xfyun error code={code}: {message or 'unknown'}"


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
    """HMAC-SHA256 query string 鉴权参数 — 与 v2.1 鉴权同源."""
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
    width: int = 768,
    height: int = 768,
    domain: str = "general",
    endpoint: str = XFYUN_DEFAULT_ENDPOINT,
    seed: int | None = None,
    num_inference_steps: int = 20,
    guidance_scale: float = 5.0,
    scheduler: str = "DPM++ 2M Karras",
    negative_prompt: str = "",
    patch_id: list[str] | None = None,
    uid: str = "novel_auto",
    timeout: float = 60.0,
) -> str:
    """调用 xfyun MaaS 图片生成, 返回 base64 编码的 PNG.

    raises XfyunImageError: 凭据缺失 / 分辨率不合法 / 鉴权失败 / 业务错误码.
    """
    if not (app_id and api_key and api_secret):
        raise XfyunImageError("xfyun 凭据不完整 (需要 AppID + APISecret + APIKey)")

    # 客户端预校验 — 不让讯飞侧 10005 浪费一次往返
    if (int(width), int(height)) not in SUPPORTED_RESOLUTIONS:
        raise XfyunImageError(
            f"分辨率 {width}x{height} 不支持; 仅可选 "
            "768x768 / 1024x1024 / 576x1024 / 768x1024 / 1024x576 / 1024x768"
        )
    if scheduler not in SUPPORTED_SCHEDULERS:
        raise XfyunImageError(
            f"scheduler {scheduler!r} 不支持; 仅可选 "
            "DPM++ 2M Karras / DPM++ SDE Karras / DDIM / Euler a / Euler"
        )

    parsed = urlparse(endpoint)
    if not parsed.netloc or not parsed.path:
        raise XfyunImageError(f"endpoint URL 不合法: {endpoint!r}")
    # 安全 — 防 SSRF. parsed.hostname 是小写不带端口的 host, 不能用 netloc
    # (后者可能含 user:pass@host:port, 绕过白名单).
    if parsed.scheme != "https":
        raise XfyunImageError(f"endpoint 必须是 https: {endpoint!r}")
    if (parsed.hostname or "") not in _ALLOWED_ENDPOINT_HOSTS:
        raise XfyunImageError(
            f"endpoint host 不在白名单: {parsed.hostname!r}. "
            f"允许: {sorted(_ALLOWED_ENDPOINT_HOSTS)}"
        )
    host = parsed.netloc
    path = parsed.path

    params = _sign_params(
        api_key=api_key, api_secret=api_secret, host=host, path=path, method="POST"
    )
    url = f"https://{host}{path}?" + urlencode(params)

    # seed 不给就随机 — 文档要求 0~INT_MAX
    effective_seed = int(seed) if seed is not None else _secrets.randbelow(2**31)

    # patch_id 文档写"可选", 实测必填 (10004 SchemaCheckError) — 永远存在,
    # 没值就空数组. 全量模型 (xopqwentti20b 等) 用 []; 非全量 LoRA 微调模型
    # 从讯飞星辰平台拿 patch_id 数组填进来.
    header_block: dict[str, object] = {
        "app_id": app_id,
        "uid": uid,
        "patch_id": list(patch_id) if patch_id else [],
    }

    body = {
        "header": header_block,
        "parameter": {
            "chat": {
                "domain": domain or "general",
                "width": int(width),
                "height": int(height),
                "seed": effective_seed,
                "num_inference_steps": int(num_inference_steps),
                "guidance_scale": float(guidance_scale),
                "scheduler": scheduler,
            }
        },
        "payload": {
            "message": {
                "text": [{"role": "user", "content": prompt}],
            }
        },
    }
    if negative_prompt:
        body["payload"]["negative_prompts"] = {"text": negative_prompt}

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
            hint = " — endpoint URL path 不对"
        raise XfyunImageError(
            f"xfyun HTTP {resp.status_code}{hint}: {snippet}"
        )

    try:
        data = resp.json()
    except ValueError as e:
        raise XfyunImageError(f"xfyun 返回非 JSON: {resp.text[:300]}") from e

    header = data.get("header", {}) or {}
    code = int(header.get("code", 0) or 0)
    if code != 0:
        raise XfyunImageError(
            _format_business_error(code, str(header.get("message", "")))
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
