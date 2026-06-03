"""Settings loaded from the project-root config.json.

Bridge note:
LLM 凭据的真正来源是项目根 ``.env``;``core/config.py`` 的
``get_active_llm_config()`` 暴露 active provider 给后端。
``config.json`` 仍然作为 memory/vector_db/server 等非 LLM 配置的来源,
当 ``.env`` 缺失时也可兜底 LLM 段。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

# backend/config/settings.py → ../.. = 项目根
_PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.json")
_MAIN_PROJECT_ROOT = _PROJECT_ROOT  # 保留别名兼容(单仓库后两者相同)


def _try_load_main_project_llm() -> dict | None:
    """尝试从主项目 core/config.py 读取 active LLM provider。

    通过 importlib 以独立模块名加载 (``_main_project_config``),避免污染
    ``sys.modules['core']``。失败时返回 None — 调用方回退到 config.json。
    """
    import importlib.util

    config_path = os.path.join(_MAIN_PROJECT_ROOT, "core", "config.py")
    if not os.path.isfile(config_path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("_main_project_config", config_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.get_active_llm_config()  # type: ignore[attr-defined]
    except Exception:
        return None


def _load_config() -> dict:
    path = os.path.normpath(_CONFIG_PATH)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"config.json not found at {path}. "
            "Copy config.example.json to config.json and fill in your API key."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(cfg: dict) -> None:
    path = os.path.normpath(_CONFIG_PATH)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")


@dataclass(frozen=True)
class Settings:
    # LLM
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str

    # Memory
    working_memory_size: int
    summary_merge_threshold: int
    section_summary_length: int

    # Vector DB
    chroma_persist_dir: str
    embedding_top_k: int

    # Knowledge Graph
    graph_snapshot_dir: str

    # Pipeline
    max_validation_retries: int
    max_chapter_retries: int

    # Server
    host: str
    port: int
    frontend_port: int
    cors_origins: list[str] = field(default_factory=lambda: ["*"])


def _resolve_llm_block(cfg: dict) -> dict:
    """统一 LLM 配置来源：主项目 active provider → config.json llm 段。

    返回结构：{api_key, base_url, model, provider, source}
    其中 source ∈ {"main_env", "config.json"}，用于诊断。
    """
    main = _try_load_main_project_llm()
    if main and main.get("base_url") and main.get("model"):
        return {
            "api_key": main.get("api_key", ""),
            "base_url": main.get("base_url"),
            "model": main.get("model"),
            "provider": main.get("provider", "deepseek"),
            "timeout": int(main.get("timeout", 120)),
            "source": "main_env",
        }
    # 兜底：config.json
    llm = cfg.get("llm", {})
    return {
        "api_key": llm.get("api_key", ""),
        "base_url": llm.get("base_url", "https://api.deepseek.com"),
        "model": llm.get("model", "deepseek-chat"),
        "provider": "deepseek",  # config.json 默认是 deepseek
        "timeout": int(llm.get("timeout", 120)),
        "source": "config.json",
    }


def _build_settings() -> Settings:
    cfg = _load_config()
    llm = _resolve_llm_block(cfg)
    mem = cfg.get("memory", {})
    vec = cfg.get("vector_db", {})
    kg = cfg.get("knowledge_graph", {})
    pipe = cfg.get("pipeline", {})
    srv = cfg.get("server", {})

    return Settings(
        deepseek_api_key=llm["api_key"],
        deepseek_base_url=llm["base_url"],
        deepseek_model=llm["model"],
        working_memory_size=mem.get("working_memory_size", 3),
        summary_merge_threshold=mem.get("summary_merge_threshold", 10),
        section_summary_length=mem.get("section_summary_length", 50),
        chroma_persist_dir=vec.get("persist_dir", "./data/chroma"),
        embedding_top_k=vec.get("top_k", 5),
        graph_snapshot_dir=kg.get("snapshot_dir", "./data/snapshots"),
        max_validation_retries=pipe.get("max_validation_retries", 3),
        max_chapter_retries=pipe.get("max_chapter_retries", 2),
        host=srv.get("host", "0.0.0.0"),
        port=srv.get("backend_port", 8000),
        frontend_port=srv.get("frontend_port", 3000),
        cors_origins=srv.get("cors_origins", ["*"]),
    )


def _mask(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) > 10:
        return api_key[:6] + "****" + api_key[-4:]
    return "****"


def get_llm_config() -> dict:
    """Return current LLM configuration with masked api_key."""
    cfg = _load_config()
    llm = _resolve_llm_block(cfg)
    return {
        "api_key_masked": _mask(llm["api_key"]),
        "has_api_key": bool(llm["api_key"]),
        "base_url": llm["base_url"],
        "model": llm["model"],
        "provider": llm["provider"],
        "source": llm["source"],
    }


def update_llm_config(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> dict:
    """Update LLM config in config.json and return masked result.

    Note: 当主项目 .env 提供了 active provider 时，``get_llm_config()`` 仍然
    优先返回主项目的值；此处的更新仅影响 config.json 兜底段。如需切换全局提供商，
    请直接编辑主项目 ``.env`` 的 ``LLM_PROVIDER``。
    """
    cfg = _load_config()
    llm_block = cfg.setdefault("llm", {})
    if api_key is not None:
        llm_block["api_key"] = api_key
    if base_url is not None:
        llm_block["base_url"] = base_url
    if model is not None:
        llm_block["model"] = model
    _save_config(cfg)
    # 重新走 resolve 链返回当前 active 值
    return get_llm_config()


settings = _build_settings()
