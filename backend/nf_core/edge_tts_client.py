"""v2.33 — edge-tts wrapper: 文本 → mp3 + 时长.

为啥用 edge-tts
----------------
* 开源 MIT, 不要 API key
* 中文音色 100+ (晓晓/晓伊/云扬/云夏/辽宁小贝...)
* 不需要 GPU, 不下模型, 一行调用
* 直接 stream 出 mp3, 同时给 WordBoundary 事件 → 不用 ffprobe 也能拿时长

时长获取顺序
-------------
1. WordBoundary 事件累加 (最后一个事件 offset+duration) — 精确, 不依赖文件
2. mutagen 读 mp3 metadata — 兜底, 文件落盘后读
"""
from __future__ import annotations

import logging
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)


# 默认女声 — 晓晓, 温柔感强, 适合小说叙述
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

# 常用中文音色清单 — 暴露给前端选择
SUPPORTED_VOICES: list[dict[str, str]] = [
    {"id": "zh-CN-XiaoxiaoNeural", "label": "晓晓 (女, 温柔)"},
    {"id": "zh-CN-XiaoyiNeural", "label": "晓伊 (女, 活泼)"},
    {"id": "zh-CN-YunxiNeural", "label": "云希 (男, 阳光)"},
    {"id": "zh-CN-YunyangNeural", "label": "云扬 (男, 沉稳)"},
    {"id": "zh-CN-YunjianNeural", "label": "云健 (男, 解说)"},
    {"id": "zh-CN-YunxiaNeural", "label": "云夏 (男, 治愈)"},
    {"id": "zh-CN-liaoning-XiaobeiNeural", "label": "辽宁小贝 (女, 东北)"},
    {"id": "zh-CN-shaanxi-XiaoniNeural", "label": "陕西小妮 (女, 西北)"},
]

# 白名单 id — routes 层校验用户传的 voice 参数, 不在白名单直接拒.
# 防: 用户传任意字符串导致 edge_tts 抛 KeyError / 异常信息泄露内部细节.
SUPPORTED_VOICE_IDS: frozenset[str] = frozenset(v["id"] for v in SUPPORTED_VOICES)


class TTSError(Exception):
    """edge-tts 调用错误."""


async def synthesize(
    *,
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    volume: str = "+0%",
) -> int:
    """文本合成成 mp3 落到 output_path, 返回时长 ms.

    参数
    ----
    rate: 语速调整, edge-tts 接受 "+10%" / "-20%" 这种字符串
    volume: 音量调整, 同上

    返回
    ----
    时长 ms (int). WordBoundary 拿不到时会 fallback 到 mutagen 读 mp3.
    """
    if not text or not text.strip():
        raise TTSError("TTS 输入文本为空")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            volume=volume,
        )
    except Exception as e:
        raise TTSError(f"edge_tts.Communicate 构造失败: {e}") from e

    audio_bytes = bytearray()
    last_word_end_100ns = 0  # WordBoundary offset + duration (100ns 单位)

    try:
        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                audio_bytes.extend(chunk.get("data") or b"")
            elif ctype == "WordBoundary":
                offset = int(chunk.get("offset") or 0)
                duration = int(chunk.get("duration") or 0)
                end = offset + duration
                if end > last_word_end_100ns:
                    last_word_end_100ns = end
    except Exception as e:
        raise TTSError(f"edge-tts stream 失败: {e}") from e

    if not audio_bytes:
        raise TTSError("edge-tts 未返回音频数据 (可能是 voice 名称错误或网络断)")

    out.write_bytes(bytes(audio_bytes))

    # 100ns → ms: 除 10000
    duration_ms = last_word_end_100ns // 10_000
    if duration_ms <= 0:
        duration_ms = _probe_mp3_duration_ms(out)
    if duration_ms <= 0:
        # 极端兜底: 按字数估算, 中文 TTS 大约 250 字/分钟
        char_count = sum(1 for c in text if not c.isspace())
        duration_ms = max(1000, int(char_count / 250 * 60 * 1000))
        logger.warning(
            "edge-tts: 无法读到 duration, 用字数估算 %d ms for %d chars",
            duration_ms, char_count,
        )

    return duration_ms


def _probe_mp3_duration_ms(path: Path) -> int:
    """用 mutagen 读 mp3 时长 — WordBoundary 缺失时的兜底."""
    try:
        from mutagen.mp3 import MP3  # type: ignore

        audio = MP3(str(path))
        seconds = float(audio.info.length or 0.0)
        return int(seconds * 1000)
    except Exception as e:
        logger.warning("mutagen 读 mp3 时长失败 (%s): %s", path, e)
        return 0
