"""LLM 配置优先级 (v2.21) — config.json 用户态优先于 .env。

回归 P0:此前 _resolve_llm_block 永远先看 main_env (.env), 而 core/config.py
里 DEEPSEEK_BASE_URL/MODEL 用 os.getenv 默认值填满, 触发 main_env 分支必中,
config.json 的 api_key 实际从未生效 → PUT /api/config/llm 静默无效。

新规则:
- config.json.llm.api_key 非空 → 整段以 config.json 为权威 (UI 写入路径)
- 否则回退到 main_env
- 都缺 → 兜底空 api_key, 让上游显式报错
"""

from __future__ import annotations

import importlib

import pytest

# 注意:不能直接 `import config.settings as settings_mod` — config/__init__.py 把
# `config.settings` 重导成 Settings 实例 (frozen dataclass), 失去模块属性。
# 强制用 importlib 拿到模块对象本身, 才能 monkeypatch 私有函数。
settings_mod = importlib.import_module("config.settings")


def _stub_main(monkeypatch, payload: dict | None) -> None:
    """Patch _try_load_main_project_llm 返回固定值, 避免读真实 .env。"""
    monkeypatch.setattr(
        settings_mod, "_try_load_main_project_llm", lambda: payload
    )


def test_config_json_with_api_key_wins(monkeypatch):
    """config.json 有 api_key → 走 config.json, 即使 main_env 也完整。"""
    _stub_main(
        monkeypatch,
        {
            "api_key": "sk-env-key",
            "base_url": "https://env.example.com",
            "model": "env-model",
            "provider": "deepseek",
            "timeout": 120,
        },
    )
    cfg = {
        "llm": {
            "api_key": "sk-user-key",
            "base_url": "https://user.example.com",
            "model": "user-model",
        }
    }
    block = settings_mod._resolve_llm_block(cfg)
    assert block["source"] == "config.json"
    assert block["api_key"] == "sk-user-key"
    assert block["base_url"] == "https://user.example.com"
    assert block["model"] == "user-model"


def test_main_env_used_when_config_json_api_key_empty(monkeypatch):
    """config.json 没有 api_key → 走 main_env。"""
    _stub_main(
        monkeypatch,
        {
            "api_key": "sk-env-key",
            "base_url": "https://env.example.com",
            "model": "env-model",
            "provider": "mimo",
            "timeout": 90,
        },
    )
    cfg = {"llm": {"api_key": "", "base_url": "", "model": ""}}
    block = settings_mod._resolve_llm_block(cfg)
    assert block["source"] == "main_env"
    assert block["api_key"] == "sk-env-key"
    assert block["base_url"] == "https://env.example.com"
    assert block["model"] == "env-model"
    assert block["provider"] == "mimo"


def test_main_env_used_when_llm_section_missing(monkeypatch):
    """config.json 完全没有 llm 段 → 走 main_env (不应崩溃)。"""
    _stub_main(
        monkeypatch,
        {
            "api_key": "sk-env-key",
            "base_url": "https://env.example.com",
            "model": "env-model",
            "provider": "deepseek",
        },
    )
    block = settings_mod._resolve_llm_block({})
    assert block["source"] == "main_env"
    assert block["api_key"] == "sk-env-key"


def test_fallback_to_empty_when_neither_has_api_key(monkeypatch):
    """两个来源都缺 api_key — main_env 没 base_url/model → 走最终兜底, api_key 空。"""
    _stub_main(monkeypatch, None)  # 模拟 .env 完全不存在
    cfg = {"llm": {"base_url": "https://x.example.com", "model": "m"}}
    block = settings_mod._resolve_llm_block(cfg)
    assert block["source"] == "config.json"
    assert block["api_key"] == ""
    assert block["base_url"] == "https://x.example.com"
    assert block["model"] == "m"


def test_partial_user_config_inherits_defaults(monkeypatch):
    """config.json 只填了 api_key, base_url/model 留空 → 用 deepseek 默认。"""
    _stub_main(
        monkeypatch,
        {
            "api_key": "sk-env",
            "base_url": "https://env.example.com",
            "model": "env-model",
        },
    )
    cfg = {"llm": {"api_key": "sk-user", "base_url": "", "model": ""}}
    block = settings_mod._resolve_llm_block(cfg)
    assert block["source"] == "config.json"
    assert block["api_key"] == "sk-user"
    # 注意: 不继承 main_env 的 base_url/model — 用 sane default
    # 避免 "用户改了 api_key 但 model 隐式还指向 env" 的混淆
    assert block["base_url"] == "https://api.deepseek.com"
    assert block["model"] == "deepseek-chat"
