"""Settings loaded from the project-root config.json.

Bridge note (v2.21 优先级):
1. ``config.json.llm.api_key`` 非空 → 整段以 config.json 为权威。这是 UI
   PUT /api/config/llm 唯一能真正生效的入口。
2. 否则回退到主项目 ``.env`` (经 ``core/config.py:get_active_llm_config()``)。
3. 都缺失则用 config.json 默认 endpoint, api_key 为空 — 让上游显式报错。

memory/vector_db/server 等非 LLM 段仅来自 config.json, 与 .env 无关。
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


def resolve_llm_block_now() -> dict:
    """重新解析 LLM 块,不复用模块导入期的快照。

    供 hot-reload 路径调用 — 例如 PUT /api/config/llm 写入 config.json 后,
    llm_client.reload() 通过本入口拿到 *当前* 真实的 api_key/base_url/model。
    """
    return _resolve_llm_block(_load_config())


def _resolve_llm_block(cfg: dict) -> dict:
    """统一 LLM 配置来源：config.json (用户态) → 主项目 active provider → 默认。

    返回结构：{api_key, base_url, model, provider, source}
    其中 source ∈ {"main_env", "config.json"}，用于诊断。

    v2.21 — 优先级翻转: 此前 main_env 永远胜出 (即便 api_key 为空), 因为
    core/config.py 的 DEEPSEEK_BASE_URL/MODEL 用 os.getenv 默认值填满了 base_url
    与 model, 触发 main_env 分支总是命中。结果 PUT /api/config/llm 写入的
    api_key 不会被读到, UI 上"保存成功"实际无效。

    新规则:
    1. ``config.json.llm.api_key`` 非空 → 视为用户通过 UI / 手工显式指定凭据,
       config.json 整段(api_key/base_url/model)作为权威。这是 UI 写入路径
       唯一能真正生效的入口。
    2. 否则回退到 main_env (.env 经 core/config.py)。
    3. 都空 → 最终 fallback 到 config.json 默认值 (api_key=""), 让上游
       明确知道凭据缺失而非默默使用错误 key。
    """
    llm = cfg.get("llm", {}) or {}

    # Priority 1 — config.json 用户态(api_key 非空才视为有效用户配置)
    if llm.get("api_key"):
        return {
            "api_key": llm["api_key"],
            "base_url": llm.get("base_url") or "https://api.deepseek.com",
            "model": llm.get("model") or "deepseek-chat",
            "provider": llm.get("provider", "deepseek"),
            "timeout": int(llm.get("timeout", 120)),
            "source": "config.json",
        }

    # Priority 2 — main_env (.env 经 core/config.py)
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

    # Priority 3 — 最终兜底 (api_key 显式为空, 让上游明确报错)
    return {
        "api_key": "",
        "base_url": llm.get("base_url", "https://api.deepseek.com"),
        "model": llm.get("model", "deepseek-chat"),
        "provider": "deepseek",
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


_VALID_PROVIDERS = ("deepseek", "mimo", "custom")


def update_llm_config(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> dict:
    """Update LLM config in config.json (+ active provider env) and return masked result.

    ``api_key`` / ``base_url`` / ``model`` 写入 ``config.json.llm`` 兜底段。
    ``provider`` 切换 active provider, 写到 ``os.environ['LLM_PROVIDER']`` —
    ``_try_load_main_project_llm`` 通过 importlib 在每次调用时重 exec
    ``core/config.py``, 因此修改立即对下一次 ``llm_client.reload()`` 生效。

    Provider 切换同时落盘 ``config.json.llm.provider`` 与 ``os.environ['LLM_PROVIDER']``:
    后者立即对当前进程生效, 前者保证 _resolve_llm_block 在 api_key 非空走 config.json
    分支时返回新 provider — 否则 UI 保存后再读会拿到旧值。
    """
    # v2.22 — 原子化: 先校验 provider, 再统一写盘。
    # 此前 _save_config 在 provider 校验前执行, 非法 provider 会留下被部分修改
    # 的 config.json (api_key/base_url/model 已写) 再抛错。
    normalized_provider: str | None = None
    if provider is not None:
        normalized_provider = provider.strip().lower()
        if not normalized_provider:
            raise ValueError("provider 不可为空字符串; 留空则保持当前值不变")
        if normalized_provider not in _VALID_PROVIDERS:
            raise ValueError(
                f"provider {provider!r} 非法; 仅接受 {list(_VALID_PROVIDERS)}"
            )

    cfg = _load_config()
    llm_block = cfg.setdefault("llm", {})
    if api_key is not None:
        llm_block["api_key"] = api_key
    if base_url is not None:
        llm_block["base_url"] = base_url
    if model is not None:
        llm_block["model"] = model
    if normalized_provider is not None:
        # 写回 config.json 是必要的: api_key 非空时 _resolve_llm_block 走 config.json
        # 分支, 只读 llm.provider; 不写盘则下次 reload 仍是旧 provider。
        llm_block["provider"] = normalized_provider
    _save_config(cfg)

    if normalized_provider is not None:
        os.environ["LLM_PROVIDER"] = normalized_provider

    # 重新走 resolve 链返回当前 active 值
    return get_llm_config()


settings = _build_settings()
