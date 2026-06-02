#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说开头生成器 (v2.x 重构后)

v1.x 行为: 直接实例化 ``core.NovelGenerator._call_api()`` 生成第一章。
v2.x 行为: HTTP 客户端,委托给 tick 后端的 bootstrap_prompts + Orchestrator。

环境变量:

* ``NOVEL_TOPIC`` - 小说主题(必填),也作为 novel_id 的 slug 来源
* ``TICK_BACKEND_URL`` - FastAPI 后端 URL,默认 http://127.0.0.1:8000
* ``LEGACY_GENERATOR=1`` - 强制走 v1.x NovelGenerator 路径(向后兼容)

支持模式:
1. 命令行: ``python create_novel.py <topic>``
2. 环境变量: ``NOVEL_TOPIC=xxx python create_novel.py``
3. 交互: ``python create_novel.py`` (无参数 → input())
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

# Windows 终端 UTF-8 修复(保留 v1.x 行为)
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")


_DEFAULT_BACKEND = "http://127.0.0.1:8000"
_HEALTH_TIMEOUT = 2.0
_RUN_TIMEOUT = 600.0


def _backend_url() -> str:
    return os.environ.get("TICK_BACKEND_URL", _DEFAULT_BACKEND).rstrip("/")


def _resolve_topic() -> str | None:
    if len(sys.argv) > 1:
        return sys.argv[1].strip()
    env_topic = os.environ.get("NOVEL_TOPIC", "").strip()
    if env_topic:
        return env_topic
    try:
        return input("请输入小说主题: ").strip()
    except EOFError:
        return None


def _backend_alive() -> bool:
    try:
        with urllib.request.urlopen(
            f"{_backend_url()}/", timeout=_HEALTH_TIMEOUT
        ) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _http_post(path: str, payload: dict, timeout: float = _RUN_TIMEOUT) -> dict:
    req = urllib.request.Request(
        f"{_backend_url()}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(path: str, timeout: float = _HEALTH_TIMEOUT) -> dict:
    req = urllib.request.Request(f"{_backend_url()}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _create_via_tick_backend(topic: str) -> bool:
    """走 v2.x HTTP 路径:bootstrap 一个新世界 + 推进一个 tick。

    bootstrap 由 backend 的 ``/api/tick/run`` + 用户已经调用 bootstrap_prompts.py
    完成。本函数只负责:
    1. 验证 backend 已就绪
    2. 调用 /api/tick/run 推进一个 tick 产出第一章叙述
    3. 显示输出文件路径
    """
    print(f"[tick] 检查后端 {_backend_url()} …")
    status = _http_get("/api/tick/status")
    print(
        f"[tick] current_tick={status['current_tick']}, "
        f"open_loops={status['open_loop_count']}, "
        f"characters={status['character_count']}"
    )
    if status["character_count"] == 0:
        print()
        print("=" * 60)
        print("⚠ 后端未 bootstrap - 请先运行:")
        print()
        print(f"  python -m novel_frame.backend.bootstrap_prompts \\")
        print(f"      --novel-id {topic} \\")
        print(f'      --seed "你的世界种子描述" \\')
        print(f'      --positioning "古典含蓄、心理白描" \\')
        print(f'      --references "Le Guin / 古龙"')
        print()
        print("然后重启 backend 并设置 ACTIVE_NOVEL_DATA_DIR 指向 bootstrap 目录。")
        print("=" * 60)
        return False

    print(f"[tick] 推进 tick 生成第一章…")
    result = _http_post("/api/tick/run", payload={})
    if not result.get("ok"):
        print(f"✗ tick 推进失败: {result}")
        return False

    summary = result["summary"]
    if summary["narrator_produced_text"]:
        print(
            f"✓ 第一章已生成 ({summary['narrator_output_chars']} 字符) "
            f"@ tick={summary['tick']}"
        )
        print(f"  事件数: {len(summary['events_generated'])}")
        print(f"  agents: {', '.join(summary['agents_called'])}")
    else:
        print(
            f"○ tick {summary['tick']} Narrator 评估后选择沉默,本 tick 无产出。"
            f" 再运行一次 /api/tick/run 推进。"
        )
    return True


def _create_via_legacy(topic: str) -> bool:
    """走 v1.x NovelGenerator 路径(向后兼容)。"""
    print(f"[legacy] 使用 v1.x NovelGenerator 生成…")
    from core import NovelGenerator

    topic_dir = os.path.join("results", topic)
    os.makedirs(topic_dir, exist_ok=True)
    generator = NovelGenerator(topic_dir=topic_dir, enable_multimedia=False)

    if not generator.api_key:
        print("✗ 请先配置 LLM API 密钥(.env 或前端设置页)")
        return False

    print(f"正在为 '{topic}' 主题生成第一章…")
    first_chapter_prompt = (
        f"请为'{topic}'主题创作一部小说的第一章。要求:"
        "引入主要角色,设定故事背景,建立基本冲突或悬念,吸引读者兴趣。"
    )

    try:
        first_chapter_content = generator._call_api(first_chapter_prompt)
        if not first_chapter_content:
            print("✗ 生成失败,请检查 API 配置和网络。")
            return False
        generator.initialize_first_chapter("第一章", first_chapter_content)
        print(f"✓ 第一章已保存到 {topic_dir}")
        return True
    except Exception as e:
        print(f"✗ 生成出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_new_novel(topic: str | None = None) -> bool:
    print("=" * 50)
    print("无限小说生成系统 - 创建新小说 (v2.x)")
    print("=" * 50)

    if topic is None:
        topic = _resolve_topic()
    if not topic:
        print("✗ 主题不能为空")
        return False

    force_legacy = os.environ.get("LEGACY_GENERATOR", "0") == "1"
    if force_legacy:
        return _create_via_legacy(topic)

    if _backend_alive():
        try:
            return _create_via_tick_backend(topic)
        except (urllib.error.URLError, OSError) as e:
            print(f"⚠ tick 后端通信失败({e}),退回 legacy 路径。")
            return _create_via_legacy(topic)

    print(f"[fallback] tick 后端 {_backend_url()} 不可达,使用 legacy 路径。")
    print("           启动后端: python -m agent_backend --port 8000")
    return _create_via_legacy(topic)


if __name__ == "__main__":
    sys.exit(0 if create_new_novel() else 1)
