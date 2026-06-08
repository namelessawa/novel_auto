"""v2.26 — /api/llm/random-{seed,title} 单元测试。

聚焦 prompt 客制化逻辑 + header 校验 + key-not-stored 保证。
SMTP + LLM 都 mock, 不出网。
"""

from __future__ import annotations

import pytest

from api.llm_routes import (
    RandomSeedRequest,
    RandomTitleRequest,
    random_seed,
    random_title,
)


class _FakeUser:
    id = "user_abc"
    email = "u@x.com"
    has_password = False
    save_my_works = False


@pytest.fixture
def mock_one_shot(monkeypatch):
    """拦截 _one_shot_complete, 记录 (system, user) prompt 用以断言客制化逻辑。"""
    calls: list[dict] = []

    async def _fake(**kw):
        calls.append(kw)
        # 模拟返回
        if "标题" in kw["system_prompt"]:
            return "《星河颂》"
        return "这是一个被生成的世界种子描述, 故意有书名号《》该被剥离。"

    monkeypatch.setattr("api.llm_routes._one_shot_complete", _fake)
    return calls


@pytest.mark.asyncio
async def test_random_seed_with_existing_title_customizes_prompt(mock_one_shot):
    req = RandomSeedRequest(existing_title="星河旅人")
    resp = await random_seed(
        req,
        current_user=_FakeUser(),
        x_user_llm_key="sk-test",
        x_user_llm_base_url=None,
        x_user_llm_model=None,
    )
    assert resp.text  # 非空
    # 客制化 prompt 应提到标题
    assert "星河旅人" in mock_one_shot[0]["user_prompt"]
    # 应使用默认 base_url
    assert mock_one_shot[0]["base_url"] == "https://api.deepseek.com"


@pytest.mark.asyncio
async def test_random_seed_no_title_uses_generic_prompt(mock_one_shot):
    req = RandomSeedRequest(existing_title="")
    await random_seed(
        req,
        current_user=_FakeUser(),
        x_user_llm_key="sk-test",
        x_user_llm_base_url=None,
        x_user_llm_model=None,
    )
    assert "随机" in mock_one_shot[0]["user_prompt"]


@pytest.mark.asyncio
async def test_random_title_with_seed_customizes_prompt(mock_one_shot):
    req = RandomTitleRequest(existing_seed="末世修仙, 门派与凡人的撕裂")
    resp = await random_title(
        req,
        current_user=_FakeUser(),
        x_user_llm_key="sk-test",
        x_user_llm_base_url=None,
        x_user_llm_model=None,
    )
    assert resp.text
    # 标题应去掉 LLM 返回的书名号
    assert "《" not in resp.text
    assert "》" not in resp.text
    # prompt 中应包含种子内容
    assert "末世修仙" in mock_one_shot[0]["user_prompt"]


@pytest.mark.asyncio
async def test_random_title_no_seed_uses_generic_prompt(mock_one_shot):
    req = RandomTitleRequest(existing_seed="")
    await random_title(
        req,
        current_user=_FakeUser(),
        x_user_llm_key="sk-test",
        x_user_llm_base_url=None,
        x_user_llm_model=None,
    )
    assert "随机" in mock_one_shot[0]["user_prompt"]


@pytest.mark.asyncio
async def test_random_seed_rejects_missing_api_key():
    from fastapi import HTTPException

    req = RandomSeedRequest(existing_title="")
    with pytest.raises(HTTPException) as exc:
        await random_seed(
            req,
            current_user=_FakeUser(),
            x_user_llm_key=None,
            x_user_llm_base_url=None,
            x_user_llm_model=None,
        )
    assert exc.value.status_code == 400
    assert "X-User-LLM-Key" in exc.value.detail


@pytest.mark.asyncio
async def test_random_seed_rejects_empty_api_key():
    from fastapi import HTTPException

    req = RandomSeedRequest(existing_title="")
    with pytest.raises(HTTPException) as exc:
        await random_seed(
            req,
            current_user=_FakeUser(),
            x_user_llm_key="   ",  # whitespace-only
            x_user_llm_base_url=None,
            x_user_llm_model=None,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_custom_base_url_and_model_passed_through(mock_one_shot):
    req = RandomSeedRequest(existing_title="")
    await random_seed(
        req,
        current_user=_FakeUser(),
        x_user_llm_key="sk-test",
        x_user_llm_base_url="https://custom.llm/v1",
        x_user_llm_model="custom-model-x",
    )
    assert mock_one_shot[0]["base_url"] == "https://custom.llm/v1"
    assert mock_one_shot[0]["model"] == "custom-model-x"
