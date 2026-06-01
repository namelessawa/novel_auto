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
# DeepSeek API 配置
# ============================================================================

# API 密钥（优先从环境变量读取）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# API 基础 URL
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# 模型名称
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 最大 Token 数
MAX_TOKENS = int(os.getenv("DEEPSEEK_MAX_TOKENS", "8192"))

# 温度参数（控制生成随机性，0-1 之间）
TEMPERATURE = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7"))

# API 请求超时时间（秒）
API_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "120"))


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
    """验证必要的 API 密钥是否已配置"""
    warnings = []

    if not DEEPSEEK_API_KEY or (DEEPSEEK_API_KEY.startswith("sk-") and len(DEEPSEEK_API_KEY) < 20):
        warnings.append("警告：DeepSeek API 密钥可能未正确配置")

    if not DASHSCOPE_API_KEY:
        warnings.append("提示：DashScope API 密钥未配置，图片生成功能将不可用")

    return warnings


def print_config():
    """打印当前配置（用于调试）"""
    print("=" * 60)
    print("当前配置")
    print("=" * 60)
    print(f"项目根目录：{PROJECT_ROOT}")
    print(f"结果目录：{RESULTS_DIR}")
    print(f"DeepSeek API: {'已配置' if DEEPSEEK_API_KEY else '未配置'}")
    print(f"DashScope API: {'已配置' if DASHSCOPE_API_KEY else '未配置'}")
    print(f"多媒体功能：{'启用' if ENABLE_MULTIMEDIA_DEFAULT else '禁用'}")
    print(f"前端端口：{FRONTEND_PORT}")
    print("=" * 60)


# 自动创建日志目录
LOG_FILE.parent.mkdir(exist_ok=True)
