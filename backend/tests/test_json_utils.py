"""nf_core.json_utils.strip_code_fence — LLM 输出 markdown 围栏剥离 (v2.19.6)。

8 个 agent 此前各自内联同一段 fence stripping 逻辑 (character_agent /
narrator_agent / novelty_critic / event_injector / memory_compressor /
character_arc_tracker / showrunner; narrative_critic 已抽出私有 helper)。
统一到 nf_core/json_utils.strip_code_fence 后, 未来 LLM 输出格式变化只需修一处,
不会再有 7 处行为漂移。

本 helper 必须保留原行为 (不引入新语义), 防意外回归:
* 整体以 ``` 开头时, 跳过第一行 (含可能的 'json' 语言标签), 末行也是 ``` 时去掉
* 不以 ``` 开头的原样返回 (即使内含 ``` 也不动)
* 前后空白被剥
* 空字符串安全
"""

from __future__ import annotations

import pytest

from nf_core.json_utils import strip_code_fence


def test_plain_json_pass_through() -> None:
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'


def test_simple_fence_stripped() -> None:
    raw = "```\n{\"a\": 1}\n```"
    assert strip_code_fence(raw) == '{"a": 1}'


def test_fence_with_language_tag() -> None:
    raw = "```json\n{\"a\": 1}\n```"
    assert strip_code_fence(raw) == '{"a": 1}'


def test_fence_with_leading_trailing_whitespace() -> None:
    raw = "   \n```json\n{\"a\": 1}\n```\n  "
    assert strip_code_fence(raw) == '{"a": 1}'


def test_inline_triple_backticks_not_stripped() -> None:
    """文本中包含 ``` 但不在开头时不剥 — 保持原 7 处实现的行为。"""
    raw = 'before ``` mid ```'
    assert strip_code_fence(raw) == 'before ``` mid ```'


def test_empty_string_safe() -> None:
    assert strip_code_fence("") == ""


def test_only_whitespace_safe() -> None:
    assert strip_code_fence("   \n  ") == ""


def test_fence_open_only_no_close() -> None:
    """开了 ``` 但末尾没闭合 — 跳过第一行, 后面照旧。"""
    raw = "```json\n{\"a\": 1}"
    assert strip_code_fence(raw) == '{"a": 1}'


def test_multiline_json_inside_fence() -> None:
    raw = "```json\n{\n  \"a\": 1,\n  \"b\": [1, 2]\n}\n```"
    assert strip_code_fence(raw) == '{\n  "a": 1,\n  "b": [1, 2]\n}'
