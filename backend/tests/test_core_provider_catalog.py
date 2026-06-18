"""v2.45 — core/config.py 的 PROVIDER catalog 集成测试.

Catalog 是数据驱动 — 加 provider 只改 ``_PROVIDER_CATALOG`` 一行, 这里钉住
契约不回归:
* 每个 catalog 行能生成完整 PROVIDERS entry (label/api_key/base_url/model)
* env_prefix 派生的 env 变量 (PREFIX_API_KEY / PREFIX_BASE_URL / PREFIX_MODEL)
  能被 monkeypatch 注入并影响 get_active_llm_config 结果
* 23 个 catalog provider 都暴露在 PROVIDERS dict + _PROVIDER_PUBLIC_META
* 历史顶层常量 (DEEPSEEK_API_KEY 等) 仍可 import (judge.py / 旧 scripts 用)
* fallback chain 覆盖完整 catalog 顺序 (不再硬编码 3 个)
"""

from __future__ import annotations

import importlib
import os

import pytest


def _reload_config():
    """重新 exec core/config.py — 让 monkeypatch.setenv 后的 env 立即生效.

    模块级别 os.getenv 在 import 时一次性 snapshot, reload 才能拿到最新值.
    """
    import core.config as cfg_mod

    return importlib.reload(cfg_mod)


@pytest.fixture
def restore_env_vars():
    """保护 LLM_PROVIDER + 所有 *_API_KEY env, 避免测试互相污染."""
    saved: dict[str, str | None] = {}
    keys_to_track = ["LLM_PROVIDER"]
    # 拿 catalog snapshot 决定要保护哪些 env (不能 import 后用, 因为 reload 会变)
    import core.config as cfg_mod

    for spec in cfg_mod._PROVIDER_CATALOG:
        prefix = spec[4]
        for suffix in ("_API_KEY", "_BASE_URL", "_MODEL"):
            keys_to_track.append(f"{prefix}{suffix}")
    for k in keys_to_track:
        saved[k] = os.environ.get(k)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_catalog_size_and_required_keys(restore_env_vars) -> None:
    """Catalog 至少含 deepseek/mimo/custom (历史 default), 总数 ≥ 20."""
    cfg = _reload_config()
    keys = list(cfg.PROVIDERS.keys())
    assert "deepseek" in keys
    assert "mimo" in keys
    assert "custom" in keys
    # v2.45 — 加入 19 个新 OpenAI 兼容 provider 后总数应 ≥ 20
    assert len(keys) >= 20, f"catalog 缩水 ({len(keys)}), 检查是否误删 provider"


def test_every_provider_entry_has_complete_shape(restore_env_vars) -> None:
    """所有 catalog 派生 entry 必须有 label/api_key/base_url/model/env_prefix."""
    cfg = _reload_config()
    required = {"label", "api_key", "base_url", "model", "env_prefix"}
    for key, entry in cfg.PROVIDERS.items():
        assert set(entry.keys()) >= required, (
            f"provider {key!r} entry 缺字段: {required - set(entry.keys())}"
        )
        assert isinstance(entry["label"], str) and entry["label"]
        assert isinstance(entry["env_prefix"], str) and entry["env_prefix"]


def test_public_meta_mirrors_providers(restore_env_vars) -> None:
    """_PROVIDER_PUBLIC_META 必须覆盖 PROVIDERS 全部 key, 内部一致."""
    cfg = _reload_config()
    assert set(cfg._PROVIDER_PUBLIC_META.keys()) == set(cfg.PROVIDERS.keys())
    for key, meta in cfg._PROVIDER_PUBLIC_META.items():
        prov = cfg.PROVIDERS[key]
        assert meta["label"] == prov["label"]
        assert meta["endpoint"] == prov["base_url"]
        assert meta["model"] == prov["model"]


def test_fallback_order_full_catalog(restore_env_vars) -> None:
    """_FALLBACK_ORDER 跟 catalog 顺序一致 — fallback 链路覆盖所有 provider."""
    cfg = _reload_config()
    catalog_keys = tuple(spec[0] for spec in cfg._PROVIDER_CATALOG)
    assert cfg._FALLBACK_ORDER == catalog_keys


def test_new_provider_env_resolves(monkeypatch, restore_env_vars) -> None:
    """填了 ARK env 三件套 → 切到 ark 后 get_active_llm_config 返回 ark."""
    monkeypatch.setenv("LLM_PROVIDER", "ark")
    monkeypatch.setenv("ARK_API_KEY", "fake-ark-key")
    monkeypatch.setenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    monkeypatch.setenv("ARK_MODEL", "doubao-pro-32k")
    cfg = _reload_config()
    active = cfg.get_active_llm_config()
    assert active["provider"] == "ark"
    assert active["api_key"] == "fake-ark-key"
    assert active["model"] == "doubao-pro-32k"


def test_default_base_url_when_env_unset(monkeypatch, restore_env_vars) -> None:
    """没填 GROQ_BASE_URL → catalog default 顶上 (https://api.groq.com/openai/v1)."""
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-key")
    monkeypatch.delenv("GROQ_BASE_URL", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    cfg = _reload_config()
    assert cfg.PROVIDERS["groq"]["base_url"] == "https://api.groq.com/openai/v1"
    assert cfg.PROVIDERS["groq"]["model"] == "llama-3.3-70b-versatile"


def test_backward_compat_top_level_constants(restore_env_vars) -> None:
    """DEEPSEEK_API_KEY / MIMO_BASE_URL / CUSTOM_MODEL 等顶层常量仍存在."""
    cfg = _reload_config()
    # 至少能访问, 不报 AttributeError. 值可以是空字符串 (env 未配置).
    assert isinstance(cfg.DEEPSEEK_API_KEY, str)
    assert isinstance(cfg.DEEPSEEK_BASE_URL, str)
    assert isinstance(cfg.DEEPSEEK_MODEL, str)
    assert isinstance(cfg.MIMO_API_KEY, str)
    assert isinstance(cfg.MIMO_BASE_URL, str)
    assert isinstance(cfg.MIMO_MODEL, str)
    assert isinstance(cfg.CUSTOM_API_KEY, str)


def test_fallback_skips_provider_without_credentials(monkeypatch, restore_env_vars) -> None:
    """LLM_PROVIDER=zhipu 但 zhipu env 全空 → fallback 到 catalog 第一个齐的."""
    monkeypatch.setenv("LLM_PROVIDER", "zhipu")
    monkeypatch.delenv("ZHIPU_API_KEY", raising=False)
    # 让 deepseek 齐
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-ds-key")
    cfg = _reload_config()
    active = cfg.get_active_llm_config()
    # deepseek 顺位最高且齐, 应被选中
    assert active["provider"] == "deepseek"
    assert active["api_key"] == "fake-ds-key"
