"""
统一配置文件
所有项目配置项都集中在此文件中

建议将敏感信息（如 API 密钥）存储在环境变量中
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# 加载.env 文件中的环境变量
load_dotenv()


# ============================================================================
# 基础配置
# ============================================================================

# 项目根目录（此文件位于 core/，上溯一级才是项目根）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 结果目录
RESULTS_DIR = PROJECT_ROOT / "results"

# 临时目录
TEMP_DIR = PROJECT_ROOT / "temp"

# 确保目录存在
RESULTS_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)


# ============================================================================
# LLM 提供商配置（多提供商抽象）
# ============================================================================
#
# 通过 `LLM_PROVIDER` 切换默认提供商。catalog 驱动 — 加一家 provider 只改
# `_PROVIDER_CATALOG` 一行, PROVIDERS / _PROVIDER_PUBLIC_META / _FALLBACK_ORDER
# 自动派生。所有 catalog 内 provider 都是 **OpenAI 兼容**(Bearer + base_url),
# 现有 OpenAI SDK (`backend/nf_core/llm_client.py`) 直接调.
#
# 非 OpenAI 兼容的 provider (Anthropic Messages API / Gemini 原生 / 百度文心
# v1 / 腾讯混元 / 智谱 v3 JWT 等) 不在此 catalog — 可走 one-api 网关转 OpenAI
# 兼容, 或在 custom provider 填 1 个外部网关 endpoint.
#
# 运行时 `get_active_llm_config()` 返回当前生效的
# `{provider, label, api_key, base_url, model, max_tokens, temperature, timeout}`.

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()

# 通用默认参数（被各提供商共享，除非提供商单独覆盖）
DEFAULT_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", os.getenv("DEEPSEEK_MAX_TOKENS", "8192")))
DEFAULT_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", os.getenv("DEEPSEEK_TEMPERATURE", "0.7")))
DEFAULT_TIMEOUT = int(os.getenv("LLM_TIMEOUT", os.getenv("DEEPSEEK_TIMEOUT", "120")))


# Provider catalog — (key, label, default_base_url, default_model, env_prefix).
# env_prefix=PREFIX → 读取 PREFIX_API_KEY / PREFIX_BASE_URL / PREFIX_MODEL.
# default base_url / model 是用户没填 env 时的合理默认 (跟官方文档对齐).
#
# 排序: 国内主力 → 海外主力 → custom 兜底.
_PROVIDER_CATALOG: tuple[tuple[str, str, str, str, str], ...] = (
    # ─── 已有 (历史 default) ────────────────────────────────────────────
    ("deepseek",    "DeepSeek",                          "https://api.deepseek.com/v1",                          "deepseek-chat",                                       "DEEPSEEK"),
    ("mimo",        "MiMo (小米)",                       "https://token-plan-cn.xiaomimimo.com/v1",              "mimo-chat",                                           "MIMO"),
    # ─── 国内 OpenAI 兼容 ─────────────────────────────────────────────
    ("qwen",        "通义千问 (DashScope OpenAI 兼容)",   "https://dashscope.aliyuncs.com/compatible-mode/v1",    "qwen-plus",                                           "QWEN"),
    ("zhipu",       "智谱 GLM",                          "https://open.bigmodel.cn/api/paas/v4",                 "glm-4-plus",                                          "ZHIPU"),
    ("moonshot",    "Moonshot Kimi",                     "https://api.moonshot.cn/v1",                           "moonshot-v1-32k",                                     "MOONSHOT"),
    ("baidu",       "百度千帆 v2 (OpenAI 兼容)",          "https://qianfan.baidubce.com/v2",                      "ernie-4.0-turbo-128k",                                "BAIDU"),
    ("ark",         "火山引擎方舟 (豆包)",                 "https://ark.cn-beijing.volces.com/api/v3",             "doubao-pro-32k",                                      "ARK"),
    ("siliconflow", "SiliconFlow (硅基流动)",             "https://api.siliconflow.cn/v1",                        "Qwen/Qwen2.5-72B-Instruct",                           "SILICONFLOW"),
    ("stepfun",     "阶跃星辰 step",                      "https://api.stepfun.com/v1",                           "step-1-256k",                                         "STEPFUN"),
    ("minimax",     "MiniMax",                           "https://api.minimax.chat/v1",                          "abab6.5-chat",                                        "MINIMAX"),
    ("baichuan",    "百川 Baichuan",                     "https://api.baichuan-ai.com/v1",                       "Baichuan4-Turbo",                                     "BAICHUAN"),
    ("lingyiwanwu", "零一万物 (Yi)",                      "https://api.lingyiwanwu.com/v1",                       "yi-large",                                            "LINGYIWANWU"),
    ("ai360",       "360 智脑",                          "https://api.360.cn/v1",                                "360gpt-pro",                                          "AI360"),
    # ─── 海外 OpenAI 兼容 ─────────────────────────────────────────────
    ("openai",      "OpenAI",                            "https://api.openai.com/v1",                            "gpt-4o-mini",                                         "OPENAI"),
    ("xai",         "xAI Grok",                          "https://api.x.ai/v1",                                  "grok-2-latest",                                       "XAI"),
    ("groq",        "Groq",                              "https://api.groq.com/openai/v1",                       "llama-3.3-70b-versatile",                             "GROQ"),
    ("openrouter",  "OpenRouter",                        "https://openrouter.ai/api/v1",                         "openai/gpt-4o-mini",                                  "OPENROUTER"),
    ("together",    "Together AI",                       "https://api.together.xyz/v1",                          "meta-llama/Llama-3.3-70B-Instruct-Turbo",             "TOGETHER"),
    ("fireworks",   "Fireworks AI",                      "https://api.fireworks.ai/inference/v1",                "accounts/fireworks/models/llama-v3p3-70b-instruct",   "FIREWORKS"),
    ("mistral",     "Mistral La Plateforme",             "https://api.mistral.ai/v1",                            "mistral-large-latest",                                "MISTRAL"),
    ("novita",      "Novita AI",                         "https://api.novita.ai/v3/openai",                      "meta-llama/llama-3.3-70b-instruct",                   "NOVITA"),
    ("gemini_oai",  "Google Gemini (OpenAI 兼容层)",       "https://generativelanguage.googleapis.com/v1beta/openai",  "gemini-1.5-flash",                                  "GEMINI_OAI"),
    # ─── 兜底 ─────────────────────────────────────────────────────────
    ("custom",      "Custom (任意 OpenAI 兼容)",          "",                                                     "",                                                    "CUSTOM"),
)


def _build_provider(key: str, label: str, default_base_url: str, default_model: str, env_prefix: str) -> dict:
    """从 catalog 一行 + env 派生 provider 配置 dict.

    env_prefix=ARK → 读 ARK_API_KEY / ARK_BASE_URL / ARK_MODEL, 留空时回落到
    default_base_url / default_model. custom 类 provider (空 default) 不会
    通过 _complete() 校验, 自动跳过 fallback.
    """
    return {
        "label": label,
        "api_key": os.getenv(f"{env_prefix}_API_KEY", ""),
        "base_url": os.getenv(f"{env_prefix}_BASE_URL", default_base_url),
        "model": os.getenv(f"{env_prefix}_MODEL", default_model),
        "env_prefix": env_prefix,
    }


# Catalog → PROVIDERS dict (运行时唯一权威, 保持 key→entry 字典契约不变)
PROVIDERS = {spec[0]: _build_provider(*spec) for spec in _PROVIDER_CATALOG}

# 备用 provider 搜索顺序 — 当 active provider 缺 api_key 时按顺序找第一个
# api_key + base_url + model 都齐的 provider 顶上. catalog 顺序 = fallback 顺序
# (国内主力优先, custom 最后兜底).
_FALLBACK_ORDER = tuple(spec[0] for spec in _PROVIDER_CATALOG)

# --- Backward compat: 历史顶层常量 (judge.py / 旧 scripts 直读 env 名时仍可用) -
# `os.getenv` 这些常量在 import 时一次性 snapshot, runtime monkeypatch.setenv
# 后不会变 — 跟 _PROVIDER_CATALOG 解析时机一致, 不引入新约束.
DEEPSEEK_API_KEY = PROVIDERS["deepseek"]["api_key"]
DEEPSEEK_BASE_URL = PROVIDERS["deepseek"]["base_url"]
DEEPSEEK_MODEL = PROVIDERS["deepseek"]["model"]
MIMO_API_KEY = PROVIDERS["mimo"]["api_key"]
MIMO_BASE_URL = PROVIDERS["mimo"]["base_url"]
MIMO_MODEL = PROVIDERS["mimo"]["model"]
CUSTOM_API_KEY = PROVIDERS["custom"]["api_key"]
CUSTOM_BASE_URL = PROVIDERS["custom"]["base_url"]
CUSTOM_MODEL = PROVIDERS["custom"]["model"]


def get_active_llm_config() -> dict:
    """
    返回当前生效的 LLM 配置。

    选择优先级:
      1. ``LLM_PROVIDER`` 指定的 provider, 且 base_url + model + api_key 全齐
      2. 否则按 _FALLBACK_ORDER 顺序找第一个齐的 provider (warn log)
      3. 都没齐 → 保持 active 为 LLM_PROVIDER 指定值, 让上游 OpenAI client
         报清晰的 "Missing credentials" 而不是这里掩盖错误

    Returns:
        dict: 包含 provider/label/api_key/base_url/model/max_tokens/temperature/timeout
    """
    import logging

    requested = LLM_PROVIDER if LLM_PROVIDER in PROVIDERS else "deepseek"
    cfg = PROVIDERS.get(requested, PROVIDERS["deepseek"])
    active = requested

    def _complete(c: dict) -> bool:
        return bool(c.get("api_key") and c.get("base_url") and c.get("model"))

    if not _complete(cfg):
        # 找一个完整的 fallback provider
        for name in _FALLBACK_ORDER:
            fb = PROVIDERS.get(name) or {}
            if name != active and _complete(fb):
                logging.getLogger(__name__).warning(
                    "LLM_PROVIDER=%s 配置不完整(api_key/base_url/model 缺一), "
                    "自动 fallback 到 %s。要消除此警告: 在 .env 填齐该 provider 的凭据, "
                    "或把 LLM_PROVIDER 改成 %s。",
                    requested,
                    name,
                    name,
                )
                active = name
                cfg = fb
                break
        # 全员都不齐: 保留原 cfg, 让 OpenAI client 给出 Missing credentials, 此处不掩盖
        else:
            if not _complete(cfg):
                logging.getLogger(__name__).warning(
                    "所有 provider (deepseek/mimo/custom) 都缺凭据。"
                    ".env 至少填一个 *_API_KEY。当前 LLM_PROVIDER=%s 将原样返回, "
                    "上游 LLM 调用会报 Missing credentials。",
                    requested,
                )

    return {
        "provider": active,
        "label": cfg["label"],
        "api_key": cfg["api_key"],
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "max_tokens": DEFAULT_MAX_TOKENS,
        "temperature": DEFAULT_TEMPERATURE,
        "timeout": DEFAULT_TIMEOUT,
    }


# --- 向后兼容别名 -----------------------------------------------------------
# 旧代码继续使用 DEEPSEEK_* / MODEL_NAME / MAX_TOKENS / TEMPERATURE 时，
# 这些变量映射到当前生效的提供商，避免老代码失效。
_active = get_active_llm_config()

# 当 LLM_PROVIDER != "deepseek" 时，DEEPSEEK_* 变量也会指向 active 配置
# （这样 generator.py 老路径不用改也能用上新提供商）。
MODEL_NAME = _active["model"]
MAX_TOKENS = _active["max_tokens"]
TEMPERATURE = _active["temperature"]
API_TIMEOUT = _active["timeout"]


# ============================================================================
# DashScope API 配置（图片生成）
# ============================================================================

# API 密钥
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")

# 模型名称
IMAGE_GENERATION_MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-image-2.0")

# API 基础 URL
DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")

# 生成图片数量
IMAGES_PER_CHAPTER = int(os.getenv("DASHSCOPE_IMAGES_PER_CHAPTER", "2"))

# 是否添加水印
IMAGE_WATERMARK = os.getenv("DASHSCOPE_WATERMARK", "true").lower() == "true"


# ============================================================================
# 多媒体配置
# ============================================================================

# 是否默认启用多媒体功能
ENABLE_MULTIMEDIA_DEFAULT = os.getenv("ENABLE_MULTIMEDIA", "false").lower() == "true"

# TTS 配置
TTS_VOICE = os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoNeural")  # 默认语音
TTS_RATE = os.getenv("TTS_RATE", "+0%")  # 语速
TTS_VOLUME = os.getenv("TTS_VOLUME", "+0%")  # 音量

# 视频配置
VIDEO_FPS = int(os.getenv("VIDEO_FPS", "24"))  # 帧率
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1280"))  # 宽度
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "720"))  # 高度


# ============================================================================
# 记忆系统配置
# ============================================================================

# 滑动窗口最大 Token 数
SLIDING_WINDOW_MAX_TOKENS = int(os.getenv("SLIDING_WINDOW_MAX_TOKENS", "2500"))

# 连续性检查阈值
CONTINUITY_THRESHOLD = float(os.getenv("CONTINUITY_THRESHOLD", "80.0"))

# 摘要最大长度
SUMMARY_MAX_LENGTH = int(os.getenv("SUMMARY_MAX_LENGTH", "100"))


# ============================================================================
# 前端配置
# ============================================================================

# 前端服务器端口
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "8080"))

# 前端服务器主机
FRONTEND_HOST = os.getenv("FRONTEND_HOST", "0.0.0.0")


# ============================================================================
# 日志配置
# ============================================================================

# 日志级别
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# 是否启用详细日志
VERBOSE_LOG = os.getenv("VERBOSE_LOG", "false").lower() == "true"

# 日志文件
LOG_FILE = PROJECT_ROOT / "novel_auto.log"


# ============================================================================
# 配置验证
# ============================================================================

def validate_api_keys():
    """验证当前 active 提供商的 API 密钥是否已配置"""
    warnings = []
    active = get_active_llm_config()

    if not active["api_key"]:
        warnings.append(
            f"警告：当前提供商 [{active['label']}] 的 API 密钥未配置"
        )
    elif active["provider"] == "deepseek" and active["api_key"].startswith("sk-") \
            and len(active["api_key"]) < 20:
        warnings.append("警告：DeepSeek API 密钥长度可疑")

    if not DASHSCOPE_API_KEY:
        warnings.append("提示：DashScope API 密钥未配置，图片生成功能将不可用")

    return warnings


# 公开元数据注册表 — 不含 api_key，给展示/日志层使用。catalog 自动派生.
_PROVIDER_PUBLIC_META = {
    key: {"label": cfg["label"], "endpoint": cfg["base_url"], "model": cfg["model"]}
    for key, cfg in PROVIDERS.items()
}


def _safe_summary(_active: dict | None = None) -> dict:
    """构建不含敏感字段的展示用 summary。

    实现上完全独立于 active 配置（参数仅为向后兼容保留），
    所有返回值都从 _PROVIDER_PUBLIC_META 公开元数据派生，
    凭据状态用 boolean 截断，避免任何凭据值流向日志。
    """
    provider = LLM_PROVIDER if LLM_PROVIDER in _PROVIDER_PUBLIC_META else "deepseek"
    meta = _PROVIDER_PUBLIC_META[provider]
    if not meta.get("endpoint") or not meta.get("model"):
        provider = "deepseek"
        meta = _PROVIDER_PUBLIC_META["deepseek"]
    # 凭据存在性 → boolean，丢弃凭据内容. catalog 自动派生.
    _key_lookup = {key: cfg["api_key"] for key, cfg in PROVIDERS.items()}
    has_credential = bool(_key_lookup.get(provider))
    return {
        "label": meta["label"],
        "provider": provider,
        "endpoint": meta["endpoint"],
        "model": meta["model"],
        "credential_status": "configured" if has_credential else "missing",
    }


def print_config():
    """打印当前配置（用于调试，不会输出任何凭据）"""
    summary = _safe_summary()
    dashscope_status = "configured" if DASHSCOPE_API_KEY else "missing"
    multimedia_status = "enabled" if ENABLE_MULTIMEDIA_DEFAULT else "disabled"
    print("=" * 60)
    print("当前配置")
    print("=" * 60)
    print(f"项目根目录：{PROJECT_ROOT}")
    print(f"结果目录：{RESULTS_DIR}")
    print(f"LLM 提供商：{summary['label']} ({summary['provider']})")
    print(f"  endpoint: {summary['endpoint']}")
    print(f"  model:    {summary['model']}")
    print(f"  status:   {summary['credential_status']}")
    print(f"DashScope: {dashscope_status}")
    print(f"多媒体功能：{multimedia_status}")
    print(f"前端端口：{FRONTEND_PORT}")
    print("=" * 60)


# 自动创建日志目录
LOG_FILE.parent.mkdir(exist_ok=True)
