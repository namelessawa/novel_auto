"""Tiny env-var helpers — boolean / int with robust parsing.

v2.38 (iter#68) — 多 agent 各自抄 case-insensitive truthy 集合 (off:
``0/false/no/off``; on: ``1/true/yes/on``) 容易在新增时漏拼写或大小写.
集中到一处, 调用方传 env name + 默认 → 拿 bool.

设计:
* 默认行为按 ``default_when_missing`` 决定: 通常 LLM 行为开关默认 True
* 显式 off-集合命中 → False
* 显式 on-集合命中 → True
* 缓存这些函数行为, 不持有状态
"""

from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def env_bool(
    name: str,
    *,
    default: bool = False,
    _raw_override: str | None = None,
) -> bool:
    """读 env name, 返回 robust bool.

    ``_raw_override`` (test-only) 可跳过 os.environ.get; name 在该路径下
    仅用于错误信息上下文, 实际值取自 _raw_override. 生产代码 don't pass.
    未设置或不在 truthy/falsy 集合时返回 ``default``.
    """
    value = (
        _raw_override if _raw_override is not None else os.environ.get(name, "")
    ).strip().lower()
    if value in _FALSY:
        return False
    if value in _TRUTHY:
        return True
    return default


def env_bool_tri(name: str) -> bool | None:
    """三态版: 显式 on/off → bool; 未设置或未识别 → None (调用方决定 fallback).

    用于"NARRATOR_ENABLE_CRITIC 缺省时走 pytest 自动判断"这种逻辑.
    """
    value = os.environ.get(name, "").strip().lower()
    if value in _FALSY:
        return False
    if value in _TRUTHY:
        return True
    return None


__all__ = ["env_bool", "env_bool_tri"]
