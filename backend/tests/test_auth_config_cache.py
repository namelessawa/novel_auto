"""v2.37 — get_auth_config 基于 config.json mtime 的缓存。

mtime 未变 → 返回缓存对象 (不重读文件); 文件被修改 (mtime 变化) → 自动重读,
hot-reload 语义保持 (无 TTL)。
"""

from __future__ import annotations

import json
import os

import pytest

import auth.config as auth_config_mod


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    """指向 tmp config.json + 清空缓存; teardown 再清, 防止污染其他测试。"""
    path = str(tmp_path / "config.json")
    monkeypatch.setattr(auth_config_mod, "_CONFIG_PATH", path)
    monkeypatch.setattr(auth_config_mod, "_auth_cfg_cache", None)
    yield path
    auth_config_mod._auth_cfg_cache = None


def _write(path: str, auth_block: dict, mtime: float) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"auth": auth_block}, f)
    os.utime(path, (mtime, mtime))  # 显式控制 mtime, 避开文件系统粒度问题


def test_same_mtime_returns_cached_object(isolated_config) -> None:
    _write(isolated_config, {"jwt_ttl_days": 9, "jwt_secret": "s"}, 1_000_000.0)
    a = auth_config_mod.get_auth_config()
    b = auth_config_mod.get_auth_config()
    assert a.jwt_ttl_days == 9
    assert a is b  # 命中缓存 — 同一 frozen dataclass 实例


def test_mtime_change_invalidates_cache(isolated_config) -> None:
    _write(isolated_config, {"jwt_ttl_days": 9, "jwt_secret": "s"}, 1_000_000.0)
    a = auth_config_mod.get_auth_config()
    assert a.jwt_ttl_days == 9

    _write(isolated_config, {"jwt_ttl_days": 3, "jwt_secret": "s"}, 1_000_001.0)
    b = auth_config_mod.get_auth_config()
    assert b.jwt_ttl_days == 3
    assert a is not b


def test_missing_file_then_created_invalidates(isolated_config) -> None:
    """文件不存在 → 默认配置; 文件出现 → mtime 哨兵失效, 读到新值。"""
    cfg = auth_config_mod.get_auth_config()
    assert cfg.jwt_ttl_days == 7  # 默认值

    _write(isolated_config, {"jwt_ttl_days": 2, "jwt_secret": "s"}, 1_000_000.0)
    assert auth_config_mod.get_auth_config().jwt_ttl_days == 2


def test_trusted_proxy_default_false(isolated_config) -> None:
    """v2.37 — trusted_proxy 缺省必须 False (直连部署防 XFF 伪造)。"""
    _write(isolated_config, {"jwt_secret": "s"}, 1_000_000.0)
    assert auth_config_mod.get_auth_config().trusted_proxy is False

    _write(isolated_config, {"jwt_secret": "s", "trusted_proxy": True}, 1_000_001.0)
    assert auth_config_mod.get_auth_config().trusted_proxy is True
