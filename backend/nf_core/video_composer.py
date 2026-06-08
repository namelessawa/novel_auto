"""v2.33 — 视频合成: N 张图 + N 段音频 + 字幕 → mp4.

ffmpeg 来源
-----------
``imageio_ffmpeg.get_ffmpeg_exe()`` — pip 装的静态二进制, 跨平台. 不依赖系统 ffmpeg.

合成思路
--------
单次 ffmpeg 调用 + filter_complex, 一气呵成:
1. 每张图 ``-loop 1 -t <duration>`` 当作一段无音视频
2. 缩放并 padding 到统一分辨率 + 设 SAR/fps
3. concat 视频流, concat 音频流
4. ``subtitles=`` filter 烧入 SRT 字幕

为啥不分两步 (先各段视频再 concat)?
单次 filter_complex 省一次解编码, 质量损失只发生一次. 缺点是命令长,
但用 list 拼参数 + cwd 切到 work_dir, 路径转义问题最小.

字幕字体
--------
默认 ``Microsoft YaHei`` — 本项目主要部署 Windows. Linux 部署需自行 PR
fallback (libass 自动 fontconfig 查找, 装了 noto-sans-cjk 即可).

测试策略
--------
``build_ffmpeg_args`` 纯函数, 单测覆盖. 真实合成 (subprocess.run)
不在 CI 跑 — 太重, 留给手动 smoke test.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# 视频默认参数 — 720p 25fps, 与多数短视频平台兼容
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 25
# 单段最短显示时长 — 防止 TTS 太短导致图片闪过
MIN_SEGMENT_SECONDS = 0.8

# 全局 ffmpeg 并发上限 — 多用户同时合成时防止 CPU/IO 抢爆.
# 1080p libx264 单进程在中等机器约 1-2 cores; 2 个并发对 4 核机器是合理上限.
# 实际取 asyncio.Semaphore(2), 在 compose_video_async 里申请.
MAX_CONCURRENT_FFMPEG = 2
_ffmpeg_semaphore: asyncio.Semaphore | None = None


def _get_ffmpeg_semaphore() -> asyncio.Semaphore:
    """惰性创建全局信号量 — 避免 import 期就触发 event loop."""
    global _ffmpeg_semaphore
    if _ffmpeg_semaphore is None:
        _ffmpeg_semaphore = asyncio.Semaphore(MAX_CONCURRENT_FFMPEG)
    return _ffmpeg_semaphore

# libass force_style — 字体黑底白字带描边, 移动端可读性最好
DEFAULT_SUBTITLE_STYLE = (
    "FontName=Microsoft YaHei,"
    "FontSize=24,"
    "PrimaryColour=&HFFFFFF,"
    "OutlineColour=&H000000,"
    "BorderStyle=1,"  # 1=描边, 3=不透明背景框
    "Outline=2,"
    "Shadow=0,"
    "Alignment=2,"  # 底部居中
    "MarginV=40"
)


class VideoComposeError(Exception):
    """视频合成失败."""


@dataclass(frozen=True)
class VideoSegmentSpec:
    """单段视频规格 — 一张图 + 一段音频 + 字幕文本."""

    image_filename: str  # 相对 work_dir 的图片名 (eg "img_001.png")
    audio_filename: str  # 相对 work_dir 的音频名 (eg "audio_001.mp3")
    duration_ms: int     # 这一段视频持续时间 (由 TTS 时长决定)
    subtitle_text: str   # 字幕文字 (= segment 原文)


@dataclass(frozen=True)
class FFmpegBuildResult:
    args: list[str]
    srt_content: str
    srt_filename: str = "subtitles.srt"
    output_filename: str = "output.mp4"


def get_ffmpeg_exe() -> str:
    """拿 ffmpeg 二进制路径. 首次调用时 imageio-ffmpeg 会下/拷贝."""
    try:
        import imageio_ffmpeg  # type: ignore
    except ImportError as e:
        raise VideoComposeError(
            "imageio-ffmpeg 未安装 — pip install imageio-ffmpeg"
        ) from e

    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise VideoComposeError(f"获取 ffmpeg 路径失败: {e}") from e


def build_srt(items: list[VideoSegmentSpec]) -> str:
    """把 segments 串成 SRT 字幕文本.

    时间戳累加: 第 i 段的开始 = 前 i-1 段时长之和.
    """
    lines: list[str] = []
    cursor_ms = 0
    for idx, item in enumerate(items, start=1):
        dur = max(int(MIN_SEGMENT_SECONDS * 1000), int(item.duration_ms))
        start_ms = cursor_ms
        end_ms = cursor_ms + dur
        cursor_ms = end_ms
        lines.append(str(idx))
        lines.append(f"{_ms_to_srt_ts(start_ms)} --> {_ms_to_srt_ts(end_ms)}")
        # SRT 不允许空白行作为分段, 内部用 \\N (libass) 换行, 这里强制单行
        lines.append(_sanitize_srt_text(item.subtitle_text))
        lines.append("")  # 段间空行
    return "\n".join(lines)


def build_ffmpeg_args(
    *,
    items: list[VideoSegmentSpec],
    output_filename: str = "output.mp4",
    srt_filename: str = "subtitles.srt",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_FPS,
    subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
    ffmpeg_path: str | None = None,
) -> FFmpegBuildResult:
    """纯函数: 构造 ffmpeg 命令行参数. 不执行.

    所有文件名都是相对路径 — 实际执行时 cwd=work_dir.
    """
    if not items:
        raise VideoComposeError("没有 segments, 无法合成")

    exe = ffmpeg_path or "ffmpeg"
    args: list[str] = [exe, "-y", "-hide_banner", "-loglevel", "error"]

    # ---- 输入: 每张图 -loop 1 -t <duration>, 每段音频直接 -i ----
    n = len(items)
    for item in items:
        dur_s = max(MIN_SEGMENT_SECONDS, item.duration_ms / 1000.0)
        # 注意 -loop 1 必须在 -i 之前; -t 控制循环时长
        args.extend(["-loop", "1", "-t", f"{dur_s:.3f}", "-i", item.image_filename])
    for item in items:
        args.extend(["-i", item.audio_filename])

    # ---- filter_complex ----
    # 视频流索引: 0, 1, ..., n-1
    # 音频流索引: n, n+1, ..., 2n-1
    video_chain_parts: list[str] = []
    for i in range(n):
        # 缩放保持比例, padding 黑边, 设 SAR=1 + 固定 fps
        video_chain_parts.append(
            f"[{i}:v]"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,"
            f"fps={fps}"
            f"[v{i}]"
        )
    # concat 视频段
    video_concat_input = "".join(f"[v{i}]" for i in range(n))
    if n == 1:
        # n=1 时 concat 也能工作, 但直接重命名更省一次操作
        video_chain_parts.append(f"[v0]copy[concat_v]")
    else:
        video_chain_parts.append(
            f"{video_concat_input}concat=n={n}:v=1:a=0[concat_v]"
        )

    # 字幕烧入 — 注意 filter 内的 ':' 和 '\\' 需要转义, 但单纯文件名 (无路径分隔) 不用
    safe_srt = _escape_filter_path(srt_filename)
    style_escaped = subtitle_style.replace("'", r"\'")
    video_chain_parts.append(
        f"[concat_v]subtitles={safe_srt}:force_style='{style_escaped}'[outv]"
    )

    # 音频 concat
    audio_concat_input = "".join(f"[{n + i}:a]" for i in range(n))
    if n == 1:
        audio_chain = f"[{n}:a]anull[outa]"
    else:
        audio_chain = f"{audio_concat_input}concat=n={n}:v=0:a=1[outa]"

    filter_complex = ";".join(video_chain_parts + [audio_chain])
    args.extend(["-filter_complex", filter_complex])

    # ---- 输出 ----
    args.extend([
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        output_filename,
    ])

    srt_content = build_srt(items)
    return FFmpegBuildResult(
        args=args,
        srt_content=srt_content,
        srt_filename=srt_filename,
        output_filename=output_filename,
    )


async def compose_video_async(
    *,
    work_dir: str,
    items: list[VideoSegmentSpec],
    output_filename: str = "output.mp4",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_FPS,
    subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
    timeout_seconds: int = 600,
) -> Path:
    """async 包装 — 申请全局信号量后 to_thread 调 compose_video.

    上层 route 用这个版本, 防多用户同时跑爆 CPU.
    """
    sem = _get_ffmpeg_semaphore()
    async with sem:
        return await asyncio.to_thread(
            compose_video,
            work_dir=work_dir,
            items=items,
            output_filename=output_filename,
            width=width,
            height=height,
            fps=fps,
            subtitle_style=subtitle_style,
            timeout_seconds=timeout_seconds,
        )


def compose_video(
    *,
    work_dir: str,
    items: list[VideoSegmentSpec],
    output_filename: str = "output.mp4",
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    fps: int = DEFAULT_FPS,
    subtitle_style: str = DEFAULT_SUBTITLE_STYLE,
    timeout_seconds: int = 600,
) -> Path:
    """实际跑 ffmpeg — 落到 work_dir / output_filename. 同步调用.

    work_dir 必须已经放好所有 image_filename / audio_filename 引用的文件.
    上层 async 路径请走 compose_video_async (有全局并发上限).
    """
    work = Path(work_dir)
    if not work.is_dir():
        raise VideoComposeError(f"work_dir 不存在: {work_dir}")

    ffmpeg_path = get_ffmpeg_exe()

    result = build_ffmpeg_args(
        items=items,
        output_filename=output_filename,
        width=width,
        height=height,
        fps=fps,
        subtitle_style=subtitle_style,
        ffmpeg_path=ffmpeg_path,
    )

    # 写 SRT
    srt_path = work / result.srt_filename
    srt_path.write_text(result.srt_content, encoding="utf-8")

    logger.info(
        "ffmpeg compose: cwd=%s n_segments=%d → %s",
        work, len(items), output_filename,
    )

    try:
        proc = subprocess.run(
            result.args,
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as e:
        raise VideoComposeError(
            f"ffmpeg 超时 ({timeout_seconds}s) — 段数太多或机器太慢"
        ) from e
    except FileNotFoundError as e:
        raise VideoComposeError(f"ffmpeg 二进制找不到: {ffmpeg_path}") from e

    if proc.returncode != 0:
        # ffmpeg 的真错误信息在 stderr — stdout 通常空
        snippet = (proc.stderr or "(no stderr)")[-1500:]
        raise VideoComposeError(
            f"ffmpeg 退出码 {proc.returncode}, stderr 末尾:\n{snippet}"
        )

    output_path = work / output_filename
    if not output_path.is_file():
        raise VideoComposeError(f"ffmpeg 跑完但没产出 {output_path}")
    return output_path


# ---------- 工具函数 ---------------------------------------------------------


def _ms_to_srt_ts(ms: int) -> str:
    """毫秒 → SRT 时间戳 HH:MM:SS,mmm."""
    if ms < 0:
        ms = 0
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    seconds, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def _sanitize_srt_text(text: str) -> str:
    """SRT 单行 — 把换行替成空格, libass 自己处理软换行."""
    return text.replace("\r", " ").replace("\n", " ").strip()


def _escape_filter_path(filename: str) -> str:
    """转义 filter_complex 里的文件路径.

    ffmpeg filter 用 ':' 分隔 key=value, 路径里的 ':' 会被误解析.
    最稳: 单引号包住, 同时反斜杠转义引号 & 冒号.
    本项目只传相对文件名 (eg "subtitles.srt"), 没有路径分隔符, 但稳妥起见仍处理.
    """
    # 单引号包裹是最稳的, 内部如果有 ' 会爆 — 我们 SRT 文件名是确定性的, 不会有 '
    return filename.replace("\\", "/").replace(":", r"\:")
