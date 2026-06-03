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
# 通过 `LLM_PROVIDER` 切换默认提供商：
#   - "deepseek"  → 使用 DeepSeek 官方 API
#   - "mimo"      → 使用小米 MiMo API（OpenAI 兼容）
#   - "custom"    → 使用 CUSTOM_* 系列环境变量自定义提供商
#
# 每个提供商分别用独立的环境变量保存凭据，运行时 `get_active_llm_config()`
# 会返回当前生效的 `{api_key, base_url, model, max_tokens, temperature, timeout}`。

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()

# 通用默认参数（被各提供商共享，除非提供商单独覆盖）
DEFAULT_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", os.getenv("DEEPSEEK_MAX_TOKENS", "8192")))
DEFAULT_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", os.getenv("DEEPSEEK_TEMPERATURE", "0.7")))
DEFAULT_TIMEOUT = int(os.getenv("LLM_TIMEOUT", os.getenv("DEEPSEEK_TIMEOUT", "120")))

# --- DeepSeek ---------------------------------------------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# --- MiMo（小米）-----------------------------------------------------------
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-chat")

# --- Custom（任意 OpenAI 兼容端点）-----------------------------------------
CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY", "")
CUSTOM_BASE_URL = os.getenv("CUSTOM_BASE_URL", "")
CUSTOM_MODEL = os.getenv("CUSTOM_MODEL", "")

# 已知提供商注册表：name → {api_key, base_url, model}
PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "api_key": DEEPSEEK_API_KEY,
        "base_url": DEEPSEEK_BASE_URL,
        "model": DEEPSEEK_MODEL,
    },
    "mimo": {
        "label": "MiMo (小米)",
        "api_key": MIMO_API_KEY,
        "base_url": MIMO_BASE_URL,
        "model": MIMO_MODEL,
    },
    "custom": {
        "label": "Custom",
        "api_key": CUSTOM_API_KEY,
        "base_url": CUSTOM_BASE_URL,
        "model": CUSTOM_MODEL,
    },
}


def get_active_llm_config() -> dict:
    """
    返回当前生效的 LLM 配置。

    根据 `LLM_PROVIDER` 选择对应提供商；若所选提供商缺少关键字段，回退到 DeepSeek
    （保持向后兼容）。

    Returns:
        dict: 包含 provider/label/api_key/base_url/model/max_tokens/temperature/timeout
    """
    provider = LLM_PROVIDER if LLM_PROVIDER in PROVIDERS else "deepseek"
    cfg = PROVIDERS.get(provider, PROVIDERS["deepseek"])

    if not cfg.get("base_url") or not cfg.get("model"):
        # 配置不完整 → 回退到 DeepSeek
        provider = "deepseek"
        cfg = PROVIDERS["deepseek"]

    return {
        "provider": provider,
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


# 公开元数据注册表 — 不含 api_key，给展示/日志层使用。
_PROVIDER_PUBLIC_META = {
    "deepseek": {"label": "DeepSeek", "endpoint": DEEPSEEK_BASE_URL, "model": DEEPSEEK_MODEL},
    "mimo": {"label": "MiMo (小米)", "endpoint": MIMO_BASE_URL, "model": MIMO_MODEL},
    "custom": {"label": "Custom", "endpoint": CUSTOM_BASE_URL, "model": CUSTOM_MODEL},
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
    # 凭据存在性 → boolean，丢弃凭据内容
    _key_lookup = {
        "deepseek": DEEPSEEK_API_KEY,
        "mimo": MIMO_API_KEY,
        "custom": CUSTOM_API_KEY,
    }
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
