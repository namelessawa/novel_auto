"""v2.33 — video_composer 单测.

只测纯函数 (build_ffmpeg_args, build_srt, _ms_to_srt_ts) — 实际 ffmpeg
subprocess 不在 CI 跑.
"""
from __future__ import annotations

from nf_core.video_composer import (
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MIN_SEGMENT_SECONDS,
    VideoSegmentSpec,
    _ms_to_srt_ts,
    build_ffmpeg_args,
    build_srt,
)


def _make_segs(n: int) -> list[VideoSegmentSpec]:
    return [
        VideoSegmentSpec(
            image_filename=f"img_{i+1:03d}.png",
            audio_filename=f"audio_{i+1:03d}.mp3",
            duration_ms=3000 + i * 500,
            subtitle_text=f"这是第{i+1}段字幕",
        )
        for i in range(n)
    ]


def test_ms_to_srt_ts_zero():
    assert _ms_to_srt_ts(0) == "00:00:00,000"


def test_ms_to_srt_ts_normal():
    # 1h 2m 3s 456ms
    ms = (1 * 3600 + 2 * 60 + 3) * 1000 + 456
    assert _ms_to_srt_ts(ms) == "01:02:03,456"


def test_ms_to_srt_ts_negative_clamped():
    assert _ms_to_srt_ts(-1) == "00:00:00,000"


def test_build_srt_two_segments():
    segs = _make_segs(2)
    srt = build_srt(segs)
    # 应包含两块, 时间累加
    assert "1\n00:00:00,000 --> 00:00:03,000\n这是第1段字幕" in srt
    assert "2\n00:00:03,000 --> 00:00:06,500\n这是第2段字幕" in srt


def test_build_srt_enforces_min_duration():
    # duration_ms 太短 → 应该被拉到 MIN_SEGMENT_SECONDS
    short = VideoSegmentSpec(
        image_filename="img_001.png",
        audio_filename="audio_001.mp3",
        duration_ms=100,  # 100ms 远低于 800ms 下限
        subtitle_text="短",
    )
    srt = build_srt([short])
    expected_end_ms = int(MIN_SEGMENT_SECONDS * 1000)
    expected_end = _ms_to_srt_ts(expected_end_ms)
    assert expected_end in srt


def test_build_ffmpeg_args_single_segment():
    segs = _make_segs(1)
    r = build_ffmpeg_args(items=segs)
    # 输入: 1 张图 + 1 段音频
    assert r.args.count("-i") == 2
    assert "img_001.png" in r.args
    assert "audio_001.mp3" in r.args
    # 输出
    assert r.output_filename == "output.mp4"
    assert r.args[-1] == "output.mp4"
    # filter_complex 应该有 copy (n=1 特判) 而非 concat
    fc = r.args[r.args.index("-filter_complex") + 1]
    assert "concat=n=1" not in fc  # n=1 走 copy 分支
    assert "subtitles=subtitles.srt" in fc


def test_build_ffmpeg_args_three_segments():
    segs = _make_segs(3)
    r = build_ffmpeg_args(items=segs)
    # 3 张图 + 3 段音频 = 6 个 -i
    assert r.args.count("-i") == 6
    fc = r.args[r.args.index("-filter_complex") + 1]
    # 视频 / 音频 concat 都应该有 n=3
    assert "concat=n=3:v=1:a=0" in fc
    assert "concat=n=3:v=0:a=1" in fc


def test_build_ffmpeg_args_scaling_to_target_size():
    segs = _make_segs(2)
    r = build_ffmpeg_args(items=segs, width=1920, height=1080, fps=30)
    fc = r.args[r.args.index("-filter_complex") + 1]
    assert "scale=1920:1080" in fc
    assert "pad=1920:1080" in fc
    assert "fps=30" in fc


def test_build_ffmpeg_args_defaults_match_constants():
    segs = _make_segs(1)
    r = build_ffmpeg_args(items=segs)
    fc = r.args[r.args.index("-filter_complex") + 1]
    assert f"scale={DEFAULT_WIDTH}:{DEFAULT_HEIGHT}" in fc
    assert f"fps={DEFAULT_FPS}" in fc


def test_build_ffmpeg_args_includes_libx264_and_aac():
    segs = _make_segs(2)
    r = build_ffmpeg_args(items=segs)
    assert "libx264" in r.args
    assert "aac" in r.args
    assert "yuv420p" in r.args


def test_build_ffmpeg_args_subtitle_style_baked_in():
    segs = _make_segs(2)
    r = build_ffmpeg_args(items=segs, subtitle_style="FontSize=99")
    fc = r.args[r.args.index("-filter_complex") + 1]
    assert "FontSize=99" in fc


def test_build_ffmpeg_args_empty_raises():
    import pytest

    from nf_core.video_composer import VideoComposeError

    with pytest.raises(VideoComposeError):
        build_ffmpeg_args(items=[])


def test_segment_loop_duration_floor():
    # duration_ms=0 → 实际 -t 应该是 MIN_SEGMENT_SECONDS
    spec = VideoSegmentSpec(
        image_filename="img_001.png",
        audio_filename="audio_001.mp3",
        duration_ms=0,
        subtitle_text="x",
    )
    r = build_ffmpeg_args(items=[spec])
    # 找到 -t 的下一个值
    t_idx = r.args.index("-t")
    val = float(r.args[t_idx + 1])
    assert val >= MIN_SEGMENT_SECONDS
