"""v2.33 — extract_message_text fallback 单测.

覆盖 reasoning 模型 (MiMo / DeepSeek-Reasoner) 在 max_tokens 不够时,
正文 content 是空字符串但答案在 reasoning_content 里的兼容场景.
"""
from __future__ import annotations

from types import SimpleNamespace

from nf_core.llm_client import extract_message_text


def test_normal_content_returned():
    msg = SimpleNamespace(content="正文输出", reasoning_content="思维过程")
    assert extract_message_text(msg) == "正文输出"


def test_content_empty_falls_back_to_reasoning_attribute():
    # reasoning_content 作为属性挂在 message 上 (部分二改 SDK)
    msg = SimpleNamespace(content="", reasoning_content="答案在思维链里")
    assert extract_message_text(msg) == "答案在思维链里"


def test_content_none_falls_back_to_reasoning():
    msg = SimpleNamespace(content=None, reasoning_content="思维链作为答案")
    assert extract_message_text(msg) == "思维链作为答案"


def test_content_whitespace_only_falls_back():
    msg = SimpleNamespace(content="   \n  ", reasoning_content="真答案")
    assert extract_message_text(msg) == "真答案"


def test_reasoning_in_model_extra_dict():
    # OpenAI 官方 SDK 把未知字段塞 model_extra
    msg = SimpleNamespace(
        content="",
        model_extra={"reasoning_content": "extra 里的答案"},
    )
    # model_extra 优先级与 attribute 并列, 任一非空即取
    assert extract_message_text(msg) == "extra 里的答案"


def test_both_empty_returns_empty_string():
    msg = SimpleNamespace(content="", reasoning_content="")
    assert extract_message_text(msg) == ""


def test_missing_reasoning_field_no_crash():
    msg = SimpleNamespace(content="正常文本")
    # 没有 reasoning_content 字段也不该崩
    assert extract_message_text(msg) == "正常文本"


def test_strips_surrounding_whitespace():
    msg = SimpleNamespace(content="  正文  \n")
    assert extract_message_text(msg) == "正文"


def test_reasoning_content_stripped():
    msg = SimpleNamespace(content="", reasoning_content="  思维链  \n")
    assert extract_message_text(msg) == "思维链"
