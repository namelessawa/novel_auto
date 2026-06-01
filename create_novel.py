#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说开头生成器
用户输入主题，生成第一章关于该主题的内容

支持两种模式：
1. 命令行模式：通过参数传入主题（供前端调用）
2. 交互模式：通过 input() 获取主题（供终端使用）
"""

import os
import sys

# 设置标准输出编码为 UTF-8，解决 Windows 终端乱码问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')


from core import NovelGenerator


def create_new_novel(topic=None):
    """
    创建新小说
    
    Args:
        topic: 小说主题，如果为 None 则从命令行参数或用户输入获取
    """
    print("欢迎使用无限小说生成系统 - 新小说创建")
    print("=" * 50)

    # 获取用户输入的主题
    if topic is None:
        # 尝试从命令行参数获取
        if len(sys.argv) > 1:
            topic = sys.argv[1].strip()
            print(f"从命令行参数获取主题：{topic}")
        # 尝试从环境变量获取（供前端调用）
        elif os.getenv('NOVEL_TOPIC'):
            topic = os.getenv('NOVEL_TOPIC').strip()
            print(f"从环境变量获取主题：{topic}")
        # 从用户输入获取
        else:
            try:
                topic = input("请输入小说主题：").strip()
            except EOFError:
                print("错误：无法读取输入")
                return

    if not topic:
        print("主题不能为空！")
        return

    # 创建主题对应的目录
    topic_dir = os.path.join("results", topic)
    os.makedirs(topic_dir, exist_ok=True)

    # 创建生成器实例，指定主题目录，暂时禁用多媒体功能（需要安装额外依赖）
    generator = NovelGenerator(topic_dir=topic_dir, enable_multimedia=False)

    # 检查 API 密钥是否已配置
    if not generator.api_key:
        print("错误：请先在 api_config/config.py 中设置 DEEPSEEK_API_KEY")
        return

    print(f"\n正在为 '{topic}' 主题生成第一章...")

    # 生成第一章的提示词
    first_chapter_prompt = f"请为'{topic}'主题创作一部小说的第一章。要求：引入主要角色，设定故事背景，建立基本冲突或悬念，吸引读者兴趣。"

    try:
        # 调用 API 生成第一章内容
        first_chapter_content = generator._call_api(first_chapter_prompt)

        if not first_chapter_content:
            print("生成失败，请检查 API 配置和网络连接。")
            return

        # 初始化生成器的记忆系统（这会自动保存到 topic_dir）
        generator.initialize_first_chapter("第一章", first_chapter_content)

        print(f"\n✓ 第一章已成功生成并保存到：{topic_dir}")
        print(f"✓ '{topic}' 主题的小说已创建完成！")
        print(f"\n提示：多媒体功能需要安装额外依赖（edge-tts, moviepy, dashscope）")

    except Exception as e:
        print(f"生成过程中出现错误：{e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    create_new_novel()
