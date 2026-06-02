#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说续写器 (v2.x 重构后)

v1.x 行为: 直接实例化 ``NovelGenerator.generate_next_chapter_with_continuity_check()``。
v2.x 行为: HTTP 客户端,POST /api/tick/run 推进 tick 让 Orchestrator 产出叙述。

环境变量:

* ``NOVEL_TOPIC`` - 已存在的小说主题(必填或交互选择)
* ``TICK_BACKEND_URL`` - FastAPI 后端 URL,默认 http://127.0.0.1:8000
* ``NOVEL_CUSTOM_PROMPT`` - 可选,作为本 tick 的提示,通过 inject-event 注入
* ``LEGACY_GENERATOR=1`` - 强制走 v1.x NovelGenerator 路径
* ``TICKS_TO_RUN`` - v2.x 单次推进 tick 数(默认 1)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Windows 终端 UTF-8 修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")


_DEFAULT_BACKEND = "http://127.0.0.1:8000"


def _backend_url() -> str:
    return os.environ.get("TICK_BACKEND_URL", _DEFAULT_BACKEND).rstrip("/")


def _http_post(path: str, payload: dict, timeout: float = 600.0) -> dict:
    req = urllib.request.Request(
        f"{_backend_url()}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(path: str, timeout: float = 2.0) -> dict:
    req = urllib.request.Request(f"{_backend_url()}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _backend_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{_backend_url()}/", timeout=2.0) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def get_available_topics() -> list[str]:
    """与 v1.x 兼容:返回 results/ 下的章节目录名列表。"""
    results_dir = "results"
    if not os.path.exists(results_dir):
        return []
    topics = []
    for item in os.listdir(results_dir):
        item_path = os.path.join(results_dir, item)
        if os.path.isdir(item_path):
            chapter_files = [
                f for f in os.listdir(item_path)
                if f.startswith("chapter_") and f.endswith(".txt")
            ]
            if chapter_files:
                topics.append(item)
    return topics


def _ticks_to_run() -> int:
    raw = os.environ.get("TICKS_TO_RUN", "1").strip()
    try:
        n = int(raw)
        return max(1, min(n, 50))  # 单次调用最多 50 tick
    except ValueError:
        return 1


def _continue_via_tick_backend() -> bool:
    print(f"[tick] 检查后端 {_backend_url()} …")
    status = _http_get("/api/tick/status")
    print(
        f"[tick] current_tick={status['current_tick']}, "
        f"open_loops={status['open_loop_count']}, "
        f"is_paused={status['is_paused']}"
    )
    if status["character_count"] == 0:
        print()
        print("⚠ 后端尚未 bootstrap,无可推进的世界。请先运行 bootstrap_prompts.py。")
        return False

    # 可选: 把 NOVEL_CUSTOM_PROMPT 包装为 inject-event,让本 tick 有用户意图
    custom_prompt = os.environ.get("NOVEL_CUSTOM_PROMPT", "").strip()
    if custom_prompt:
        print(f"[tick] 注入用户提示: {custom_prompt[:80]}")
        try:
            _http_post(
                "/api/tick/inject-event",
                payload={
                    "description": custom_prompt[:500],
                    "narrative_value": 7,
                    "visible_to": ["all"],
                    "type": "dramatic",
                },
            )
        except Exception as e:
            print(f"  ⚠ inject-event 失败(非致命): {e}")

    target_ticks = _ticks_to_run()
    print(f"[tick] 推进 {target_ticks} 个 tick …")
    produced_count = 0
    skipped_count = 0
    for i in range(target_ticks):
        try:
            result = _http_post("/api/tick/run", payload={})
        except urllib.error.URLError as e:
            print(f"✗ tick {i + 1} 通信失败: {e}")
            return produced_count > 0

        summary = result.get("summary", {})
        if summary.get("narrator_produced_text"):
            produced_count += 1
            print(
                f"  ✓ tick {summary['tick']}: "
                f"{summary['narrator_output_chars']} 字符, "
                f"events={len(summary.get('events_generated', []))}"
            )
        else:
            skipped_count += 1
            print(
                f"  ○ tick {summary.get('tick', '?')}: Narrator 沉默 "
                f"({summary.get('state_changes_summary', '')})"
            )

    print(
        f"\n完成 {target_ticks} tick: 产出 {produced_count} 章, "
        f"沉默 {skipped_count} tick (Narrator 品味决定)"
    )
    return True


def _continue_via_legacy(topic: str) -> bool:
    """v1.x 路径(向后兼容)。"""
    print(f"[legacy] 使用 v1.x NovelGenerator 续写 '{topic}' …")
    from core import NovelGenerator

    topic_dir = os.path.join("results", topic)
    if not os.path.exists(topic_dir):
        print(f"✗ 主题目录不存在: {topic_dir}")
        return False

    generator = NovelGenerator(topic_dir=topic_dir, enable_multimedia=False)
    if not generator.api_key:
        print("✗ 请先配置 LLM API 密钥")
        return False

    chapter_files = [
        f for f in os.listdir(topic_dir) if f.startswith("chapter_") and f.endswith(".txt")
    ]
    next_num = len(chapter_files) + 1
    custom_prompt = os.environ.get("NOVEL_CUSTOM_PROMPT", "").strip()

    chapter_title = f"第{next_num}章"
    try:
        new_content = generator.generate_next_chapter_with_continuity_check(
            chapter_title, custom_prompt=custom_prompt
        )
        if new_content:
            print(f"✓ 第 {next_num} 章已保存到 {topic_dir}")
            return True
        print("✗ 章节生成失败")
        return False
    except Exception as e:
        print(f"✗ 出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def continue_novel(topic: str | None = None) -> bool:
    print("=" * 50)
    print("无限小说生成系统 - 续写 (v2.x)")
    print("=" * 50)

    force_legacy = os.environ.get("LEGACY_GENERATOR", "0") == "1"

    # v2.x 路径优先,不需要 topic 参数(由后端 ACTIVE_NOVEL_ID 决定)
    if not force_legacy and _backend_alive():
        try:
            return _continue_via_tick_backend()
        except urllib.error.URLError as e:
            print(f"⚠ tick 后端通信失败({e}),退回 legacy 路径。")

    # legacy 路径需要 topic
    if topic is None:
        topic = os.environ.get("NOVEL_TOPIC", "").strip()
    if not topic and len(sys.argv) > 1:
        try:
            idx = int(sys.argv[1]) - 1
            topics = get_available_topics()
            if 0 <= idx < len(topics):
                topic = topics[idx]
        except ValueError:
            pass

    if not topic:
        topics = get_available_topics()
        if not topics:
            print("✗ 未找到任何已创建的小说主题。请先创建新小说。")
            return False
        print("\n可用的小说主题:")
        for i, t in enumerate(topics, 1):
            print(f"  {i}. {t}")
        try:
            choice = input(f"\n请选择 (1-{len(topics)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(topics):
                topic = topics[idx]
        except (ValueError, EOFError):
            print("✗ 无效输入")
            return False

    if not topic:
        print("✗ 未选择主题")
        return False

    return _continue_via_legacy(topic)


def continue_novel_interactive() -> bool:
    return continue_novel(topic=None)


if __name__ == "__main__":
    sys.exit(0 if continue_novel() else 1)
