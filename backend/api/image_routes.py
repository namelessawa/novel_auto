"""v2.28 — 多模态: 文生图端点。

| Method | Path                  | 用途                       |
|--------|-----------------------|----------------------------|
| POST   | /api/image/generate   | 文本 → 图片 (base64 PNG)   |

凭据通过 header 一次性传递, 后端用完即丢, 与 /api/llm/random-* 同思路:
* X-Image-Provider — 默认 xfyun, 可选 openai / stability / custom
* X-Image-App-Id   — xfyun 需要
* X-Image-Api-Key  — 必填
* X-Image-Api-Secret — xfyun 需要
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from auth import User, get_current_user
from nf_core import xfyun_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/image", tags=["image"])


class GenerateImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    width: int = Field(default=512, ge=128, le=2048)
    height: int = Field(default=512, ge=128, le=2048)


class GenerateImageResponse(BaseModel):
    provider: str
    image_base64: str
    mime_type: str = "image/png"


@router.post("/generate", response_model=GenerateImageResponse)
async def generate_image(
    req: GenerateImageRequest,
    current_user: User = Depends(get_current_user),
    x_image_provider: str = Header(default="xfyun", alias="X-Image-Provider"),
    x_image_app_id: str = Header(default="", alias="X-Image-App-Id"),
    x_image_api_key: str = Header(default="", alias="X-Image-Api-Key"),
    x_image_api_secret: str = Header(default="", alias="X-Image-Api-Secret"),
    x_image_model: str = Header(default="", alias="X-Image-Model"),
) -> GenerateImageResponse:
    provider = (x_image_provider or "xfyun").strip().lower()

    if provider == "xfyun":
        # 校验凭据存在 — 缺一律 400, 别让讯飞侧 401 浪费一次握手往返
        missing = []
        if not x_image_app_id.strip():
            missing.append("X-Image-App-Id (AppID)")
        if not x_image_api_key.strip():
            missing.append("X-Image-Api-Key (APIKey)")
        if not x_image_api_secret.strip():
            missing.append("X-Image-Api-Secret (APISecret)")
        if missing:
            raise HTTPException(
                status_code=400,
                detail="讯飞凭据缺失: " + ", ".join(missing),
            )

        # model 即讯飞 domain — 用户没填走 general; 新模型如 xopqwentti20b 必须填
        domain = (x_image_model or "").strip() or "general"

        try:
            b64 = await xfyun_image.generate_image(
                app_id=x_image_app_id.strip(),
                api_key=x_image_api_key.strip(),
                api_secret=x_image_api_secret.strip(),
                prompt=req.prompt,
                width=req.width,
                height=req.height,
                domain=domain,
            )
        except xfyun_image.XfyunImageError as e:
            # 显式 log 让 docker logs 能定位 — HTTPException.detail 不进 stdlib log
            logger.warning(
                "xfyun image generation failed for user=%s: %s",
                current_user.id,
                e,
            )
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:  # pragma: no cover
            logger.exception("xfyun image generation crashed")
            raise HTTPException(status_code=500, detail=f"图片生成失败: {e}")
        return GenerateImageResponse(
            provider="xfyun", image_base64=b64, mime_type="image/png"
        )

    raise HTTPException(
        status_code=501,
        detail=f"暂未实现 provider={provider!r} (目前仅 xfyun)",
    )
