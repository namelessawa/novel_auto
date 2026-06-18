"""v2.20 — LLMConfigUpdateRequest.provider 真正影响 active provider。

此前 (v2.17–v2.19): PUT /api/config/llm 接受 api_key/base_url/model 写 config.json,
但 active provider 由 .env LLM_PROVIDER 决定, 前端下拉等于摆设。

本测试钉死: update_llm_config(provider=...) 写 os.environ['LLM_PROVIDER'],
让下一次 _try_load_main_project_llm() 通过 importlib 重 exec core/config.py 时
读到新值。
"""

from __future__ import annotations

import importlib
import json
import os

import pytest

from config.settings import _VALID_PROVIDERS, update_llm_config

# 私有访问: monkeypatch _save_config / _load_config 必须走模块对象, 不能用
# settings 实例 (它是 frozen dataclass)。参见 test_llm_config_fallback.py 同因。
_settings_mod = importlib.import_module("config.settings")


@pytest.fixture(autouse=True)
def isolate_config_json(tmp_path, monkeypatch):
    """v2.21 — 重定向 config.json 读写到 tmp_path, 避免污染真实文件。

    此前 update_llm_config 在 _save_config(cfg) 时无条件把项目根 config.json
    rewrite 一次, 测试运行后真实文件被覆盖 (即便内容相同也会触发文件 mtime
    与可能的换行 / 字段顺序变化, 进而干扰 git 状态与生产配置)。
    """
    fake_path = tmp_path / "config.json"
    # 写一份最小可解析配置, 让 _load_config 不抛 FileNotFoundError
    fake_path.write_text(
        json.dumps({"llm": {"api_key": "", "base_url": "", "model": ""}}),
        encoding="utf-8",
    )

    def _fake_load() -> dict:
        with open(fake_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _fake_save(cfg: dict) -> None:
        with open(fake_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    monkeypatch.setattr(_settings_mod, "_load_config", _fake_load)
    monkeypatch.setattr(_settings_mod, "_save_config", _fake_save)
    yield fake_path


@pytest.fixture
def restore_env_provider():
    """保留 / 恢复 LLM_PROVIDER, 避免单测互相污染。"""
    saved = os.environ.get("LLM_PROVIDER")
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = saved


def test_provider_none_keeps_env_unchanged(restore_env_provider):
    """provider=None (默认) 不应触动 os.environ。"""
    os.environ["LLM_PROVIDER"] = "deepseek"
    update_llm_config(provider=None)
    assert os.environ["LLM_PROVIDER"] == "deepseek"


def test_provider_switch_writes_env(restore_env_provider):
    """合法 provider 写入 os.environ['LLM_PROVIDER'] 立即生效。"""
    os.environ["LLM_PROVIDER"] = "deepseek"
    update_llm_config(provider="mimo")
    assert os.environ["LLM_PROVIDER"] == "mimo"


@pytest.mark.parametrize("p", list(_VALID_PROVIDERS))
def test_all_valid_providers_accepted(restore_env_provider, p):
    """catalog 全部合法 provider 都能写入 (v2.45 扩到 23 个)."""
    update_llm_config(provider=p)
    assert os.environ["LLM_PROVIDER"] == p


def test_provider_case_normalized(restore_env_provider):
    """大小写 / 前后空格自动归一化为 lower-case。"""
    update_llm_config(provider="  MIMO  ")
    assert os.environ["LLM_PROVIDER"] == "mimo"


def test_invalid_provider_rejected(restore_env_provider):
    """非法 provider 抛 ValueError, 不污染 os.environ。

    用 catalog 不存在的伪 ID. 此前用 'openai' 当反例, v2.45 catalog 扩展后
    openai 已是合法 provider, 故改为 sentinel.
    """
    os.environ["LLM_PROVIDER"] = "deepseek"
    with pytest.raises(ValueError, match="非法"):
        update_llm_config(provider="not_a_real_provider_xyz")
    assert os.environ["LLM_PROVIDER"] == "deepseek"


def test_empty_string_provider_rejected(restore_env_provider):
    """空字符串和全空白都视为非法 — 与 None (保持不变) 区分。"""
    os.environ["LLM_PROVIDER"] = "deepseek"
    with pytest.raises(ValueError, match="不可为空"):
        update_llm_config(provider="")
    with pytest.raises(ValueError, match="不可为空"):
        update_llm_config(provider="   ")
    assert os.environ["LLM_PROVIDER"] == "deepseek"
