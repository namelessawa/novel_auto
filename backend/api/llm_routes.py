"""v2.26 — /api/llm/random-seed + /api/llm/random-title + /api/llm/random-positioning。

用户的 API key 通过请求 header 一次性传递, 后端用完即丢, 不持久化 / 不缓存 /
不写日志。这是 "登录不保存任何东西" 设计的核心实现点。

| Method | Path                          | 用途                                  |
|--------|-------------------------------|---------------------------------------|
| POST   | /api/llm/random-seed          | 生成随机世界种子 (可基于已有标题)      |
| POST   | /api/llm/random-title         | 生成随机小说标题 (可基于已有种子)      |
| POST   | /api/llm/random-positioning   | 生成作品定位 (基于已有标题 / 种子)     |

请求 header
-----------
* ``X-User-LLM-Key`` — 用户的 API key (必填)
* ``X-User-LLM-Base-Url`` — OpenAI 兼容 base url (默认 https://api.deepseek.com)
* ``X-User-LLM-Model`` — 模型名 (默认 deepseek-chat)

联动逻辑 (前端 prompt 客制化)
-----------------------------
* 两侧都空: 完全随机生成
* 一侧已填: 根据已填侧生成匹配的另一侧
"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from auth import User, get_current_user
from nf_core.llm_client import extract_message_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/llm", tags=["llm"])


class RandomSeedRequest(BaseModel):
    existing_title: str = Field(default="", description="已有标题, 用于客制化种子")


class RandomTitleRequest(BaseModel):
    existing_seed: str = Field(default="", description="已有种子, 用于客制化标题")


class RandomPositioningRequest(BaseModel):
    existing_title: str = Field(default="", description="作品标题")
    existing_seed: str = Field(default="", description="世界种子描述")


class RandomResponse(BaseModel):
    text: str


def _validate_header_key(key: str | None) -> str:
    if not key or not key.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "缺少 X-User-LLM-Key header — 随机生成必须使用您的 API key。"
                "请先在「设置」中填写。"
            ),
        )
    return key.strip()


async def _one_shot_complete(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
) -> str:
    """一次性 LLM 调用 — 不复用全局 llm_client, 用调用方 key.

    出错时把错误细节透传给前端 (脱敏 key).

    max_tokens 默认 2048 — 给 reasoning 模型 (MiMo / DeepSeek-Reasoner)
    留足思维链空间. 之前 200 / 32 太小, 推理过程把 budget 吃完, content
    返回空字符串 → 502. 兼容: 非 reasoning 模型也不会输出 2048 字 (system
    prompt 已限定 60-150 字 / 2-6 字).
    """
    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30)
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.95,
            max_tokens=max_tokens,
        )
        # 抽文本 — content 空时退到 reasoning_content, 兼容推理模型
        choice = resp.choices[0]
        text = extract_message_text(choice.message)
        if not text:
            finish_reason = getattr(choice, "finish_reason", "?")
            logger.warning(
                "LLM 返回空: model=%s finish_reason=%s — 可能 reasoning 模型 "
                "max_tokens 不够或上游审核拦截", model, finish_reason,
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    f"LLM 返回为空 (finish_reason={finish_reason}). "
                    "若用 reasoning 模型 (MiMo / DeepSeek-Reasoner / QwQ), "
                    "建议换非推理变体, 或检查是否被内容审核拦截."
                ),
            )
        return text
    except HTTPException:
        raise
    except Exception as e:
        # 不暴露 key 痕迹
        msg = str(e).replace(api_key, "<redacted>") if api_key else str(e)
        logger.error("user-key one-shot LLM call failed: %s", msg)
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {msg}")


_SEED_SYSTEM_PROMPT = (
    "你是小说世界观策划师。给出一段 60-150 字的"
    "**世界种子描述**——一个可以让作家展开长篇小说的核心设定。\n"
    "要求:\n"
    "- 包含: 时代/世界类型 + 核心矛盾 + 主角处境\n"
    "- 风格鲜明, 避免老套\n"
    "- 不要起标题, 不要分段, 不要解释, 仅输出种子描述本体"
)

_TITLE_SYSTEM_PROMPT = (
    "你是小说编辑。为一本小说取一个简短有韵味的中文标题 (2-6 字)。\n"
    "要求:\n"
    "- 只输出标题, 不要书名号, 不要任何解释\n"
    "- 不超过 6 个字\n"
    "- 有意境, 避免直白说明"
)

_POSITIONING_SYSTEM_PROMPT = (
    "你是小说文风顾问。根据用户给出的标题 (可能也给出种子), 推断一句"
    "**贴合该作品的作品定位描述** — 描述这部小说应有的语感:"
    "句长偏好 + 修辞密度 + 节奏 + 调性。\n"
    "示例: '动作密集, 短句为主, 比喻克制, 节奏紧张' / "
    "'古典含蓄, 心理白描, 节奏舒缓, 避免华丽辞藻' / "
    "'冷峻干净, 信息密度高, 节奏明快, 偶有黑色幽默'。\n"
    "要求:\n"
    "- 直接输出定位描述本体, 不解释, 不加引号, 不分段\n"
    "- 不超过 30 字\n"
    "- 题材决定语感: 奇幻动作向就该短句紧凑, 言情就该细腻, 不要套模板"
)


@router.post("/random-seed", response_model=RandomResponse)
async def random_seed(
    req: RandomSeedRequest,
    current_user: User = Depends(get_current_user),
    x_user_llm_key: str | None = Header(default=None, alias="X-User-LLM-Key"),
    x_user_llm_base_url: str | None = Header(
        default=None, alias="X-User-LLM-Base-Url"
    ),
    x_user_llm_model: str | None = Header(
        default=None, alias="X-User-LLM-Model"
    ),
) -> RandomResponse:
    api_key = _validate_header_key(x_user_llm_key)
    base_url = (x_user_llm_base_url or "https://api.deepseek.com").strip()
    model = (x_user_llm_model or "deepseek-chat").strip()

    title = req.existing_title.strip()
    if title:
        user_prompt = (
            f"请根据小说标题《{title}》, 生成一段与之贴合的世界种子描述。"
        )
    else:
        user_prompt = "请随机生成一段新颖的世界种子描述。"

    text = await _one_shot_complete(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=_SEED_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=2048,
    )
    # _one_shot_complete 已经处理空 content → 502, 此处不需要再判
    return RandomResponse(text=text)


@router.post("/random-title", response_model=RandomResponse)
async def random_title(
    req: RandomTitleRequest,
    current_user: User = Depends(get_current_user),
    x_user_llm_key: str | None = Header(default=None, alias="X-User-LLM-Key"),
    x_user_llm_base_url: str | None = Header(
        default=None, alias="X-User-LLM-Base-Url"
    ),
    x_user_llm_model: str | None = Header(
        default=None, alias="X-User-LLM-Model"
    ),
) -> RandomResponse:
    api_key = _validate_header_key(x_user_llm_key)
    base_url = (x_user_llm_base_url or "https://api.deepseek.com").strip()
    model = (x_user_llm_model or "deepseek-chat").strip()

    seed = req.existing_seed.strip()
    if seed:
        user_prompt = (
            f"请根据以下世界种子, 取一个匹配的中文小说标题:\n\n{seed[:500]}"
        )
    else:
        user_prompt = "请随机取一个有意境的中文小说标题。"

    text = await _one_shot_complete(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=_TITLE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=1024,  # reasoning 模型留思维链空间; 非 reasoning 模型也不会输出这么多
    )
    # reasoning 模型可能在 reasoning_content 里有多段, 取最后一段非空行作为标题
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    cleaned = lines[-1] if lines else ""
    # 清理: 去书名号, 取前 20 字
    for ch in "《》<>「」『』\"'`":
        cleaned = cleaned.replace(ch, "")
    cleaned = cleaned.strip()[:20]
    if not cleaned:
        raise HTTPException(status_code=502, detail="LLM 返回为空 (清理后)")
    return RandomResponse(text=cleaned)


@router.post("/random-positioning", response_model=RandomResponse)
async def random_positioning(
    req: RandomPositioningRequest,
    current_user: User = Depends(get_current_user),
    x_user_llm_key: str | None = Header(default=None, alias="X-User-LLM-Key"),
    x_user_llm_base_url: str | None = Header(
        default=None, alias="X-User-LLM-Base-Url"
    ),
    x_user_llm_model: str | None = Header(
        default=None, alias="X-User-LLM-Model"
    ),
) -> RandomResponse:
    """根据标题 (+ 可选种子) 推一段适合该题材的作品定位字符串.

    用于"标题已填 → 随机种子"联动: 同时把高级配置里的作品定位也自动填好,
    免得用户拿到一个奇幻动作题材的标题, 还在用默认的"古典含蓄"模板生成
    style_anchors, 最终 narrator 产出与标题脱节。"""
    api_key = _validate_header_key(x_user_llm_key)
    base_url = (x_user_llm_base_url or "https://api.deepseek.com").strip()
    model = (x_user_llm_model or "deepseek-chat").strip()

    title = req.existing_title.strip()
    seed = req.existing_seed.strip()
    if not title and not seed:
        raise HTTPException(
            status_code=400,
            detail="random-positioning 需要 existing_title 或 existing_seed 至少一项",
        )
    parts: list[str] = []
    if title:
        parts.append(f"标题:《{title}》")
    if seed:
        parts.append(f"种子: {seed[:500]}")
    user_prompt = "为以下作品推一段作品定位:\n" + "\n".join(parts)

    text = await _one_shot_complete(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt=_POSITIONING_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=1024,
    )
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    cleaned = lines[-1] if lines else ""
    for ch in "《》<>「」『』\"'`":
        cleaned = cleaned.replace(ch, "")
    cleaned = cleaned.strip()[:60]
    if not cleaned:
        raise HTTPException(status_code=502, detail="LLM 返回为空 (清理后)")
    return RandomResponse(text=cleaned)
