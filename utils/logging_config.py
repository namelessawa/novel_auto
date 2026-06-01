"""
集中式日志配置

将分散在各模块中的 print() 诊断输出统一接入 Python logging，
日志级别 / 文件路径 / 详细模式均从 config.py 读取：

- LOG_LEVEL    日志级别（默认 INFO）
- VERBOSE_LOG  为 true 时强制 DEBUG 级别
- LOG_FILE     日志文件路径

用法：
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("第 %s 章已保存", num)

所有 logger 都是 "novel_auto" 的子 logger，共享同一组 handler；
面向用户的交互式 CLI 输出（菜单、提示）仍使用 print()。
"""

import logging
import sys

from core.config import LOG_LEVEL, VERBOSE_LOG, LOG_FILE

ROOT_LOGGER_NAME = "novel_auto"
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_configured = False


def configure_logging(force: bool = False) -> None:
    """初始化根 logger 的 handler（幂等，可重复调用）。"""
    global _configured
    if _configured and not force:
        return

    level = logging.DEBUG if VERBOSE_LOG else getattr(
        logging, str(LOG_LEVEL).upper(), logging.INFO
    )

    root = logging.getLogger(ROOT_LOGGER_NAME)
    root.setLevel(level)
    root.handlers.clear()
    root.propagate = False  # 不向 Python 根 logger 冒泡，避免重复输出

    console_formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(console_formatter)
    root.addHandler(console)

    # 文件 handler（始终 UTF-8；失败时静默降级为仅控制台）
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(file_handler)
    except Exception:  # noqa: BLE001 - 文件不可写时不应阻断主流程
        pass

    _configured = True


def get_logger(name: str = None) -> logging.Logger:
    """获取一个 "novel_auto.*" 子 logger（首次调用时自动配置）。"""
    configure_logging()
    if not name or name == "__main__":
        return logging.getLogger(ROOT_LOGGER_NAME)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
