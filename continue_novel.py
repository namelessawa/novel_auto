#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说续写器
允许用户选择已生成的主题进行续写，并提供多种续写选项

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


def get_available_topics():
    """获取所有可用的主题目录"""
    results_dir = "results"
    if not os.path.exists(results_dir):
        return []

    topics = []
    for item in os.listdir(results_dir):
        item_path = os.path.join(results_dir, item)
        if os.path.isdir(item_path):
            # 检查目录中是否有章节文件
            chapter_files = [f for f in os.listdir(item_path) if f.startswith("chapter_") and f.endswith(".txt")]
            if chapter_files:
                topics.append(item)

    return topics


def continue_novel(topic=None):
    """
    续写小说

    Args:
        topic: 小说主题，如果为 None 则从命令行参数或用户输入获取
    """
    print("欢迎使用无限小说生成系统 - 续写模式")
    print("=" * 50)

    # 获取所有可用主题
    topics = get_available_topics()

    if not topics:
        print("未找到任何已创建的小说主题。请先创建新小说。")
        return

    # 如果指定了主题，直接使用该主题
    if topic:
        if topic not in topics:
            print(f"错误：主题 '{topic}' 不存在")
            return
        selected_topic = topic
    else:
        # 尝试从环境变量获取主题名（供前端调用）
        env_topic = os.getenv('NOVEL_TOPIC', '').strip()
        if env_topic:
            if env_topic not in topics:
                print(f"错误：主题 '{env_topic}' 不存在")
                return
            selected_topic = env_topic
        # 尝试从命令行参数获取
        elif len(sys.argv) > 1:
            topic_index = int(sys.argv[1]) - 1
            if 0 <= topic_index < len(topics):
                selected_topic = topics[topic_index]
            else:
                print("无效的主题索引")
                return
        # 尝试从环境变量获取索引（兼容旧方式）
        elif os.getenv('NOVEL_TOPIC_INDEX'):
            topic_index = int(os.getenv('NOVEL_TOPIC_INDEX')) - 1
            if 0 <= topic_index < len(topics):
                selected_topic = topics[topic_index]
            else:
                print("无效的主题索引")
                return
        # 从用户输入获取
        else:
            print("\n可用的小说主题:")
            for i, t in enumerate(topics, 1):
                print(f"{i}. {t}")

            while True:
                try:
                    choice = input(f"\n请选择要续写的小说 (1-{len(topics)}): ").strip()
                    topic_index = int(choice) - 1

                    if 0 <= topic_index < len(topics):
                        selected_topic = topics[topic_index]
                        break
                    else:
                        print(f"请输入有效范围内的数字 (1-{len(topics)})")
                except ValueError:
                    print("请输入有效的数字")
                except EOFError:
                    print("错误：无法读取输入")
                    return

    print(f"\n您选择了：{selected_topic}")

    # 创建生成器实例，指定主题目录，暂时禁用多媒体功能（需要安装额外依赖）
    topic_dir = os.path.join("results", selected_topic)
    generator = NovelGenerator(topic_dir=topic_dir, enable_multimedia=False)

    # 检查 API 密钥是否已配置
    if not generator.api_key:
        print("错误：请先配置 DEEPSEEK_API_KEY（通过前端设置页面或 .env 文件）")
        return

    # 记忆系统已在构造函数中自动加载

    # 获取当前章节编号
    chapter_files = [f for f in os.listdir(topic_dir) if f.startswith("chapter_") and f.endswith(".txt")]
    next_chapter_num = len(chapter_files) + 1

    # 读取自定义提示词（通过环境变量传入，供前端使用）
    custom_prompt = os.getenv('NOVEL_CUSTOM_PROMPT', '').strip()
    if custom_prompt:
        print(f"自定义提示词：{custom_prompt}")

    # 如果是前端调用，只生成一章
    if topic:
        print(f"\n准备生成第 {next_chapter_num} 章...")
        chapter_title = f"第{next_chapter_num}章"
        try:
            new_content = generator.generate_next_chapter_with_continuity_check(
                chapter_title, custom_prompt=custom_prompt
            )

            if new_content:
                # 章节生成和记忆更新已在 generate_next_chapter_with_continuity_check 中完成
                print(f"\n✓ 第 {next_chapter_num} 章已成功生成并保存到：{topic_dir}")
            else:
                print("✗ 章节生成失败")

        except Exception as e:
            print(f"生成过程中出现错误：{e}")
            import traceback
            traceback.print_exc()
    else:
        # 交互模式：开始续写循环
        while True:
            print(f"\n准备生成第 {next_chapter_num} 章...")

            # 生成下一章
            chapter_title = f"第{next_chapter_num}章"
            try:
                new_content = generator.generate_next_chapter_with_continuity_check(chapter_title)

                if new_content:
                    # 章节生成和记忆更新已在 generate_next_chapter_with_continuity_check 中完成
                    print(f"✓ 第 {next_chapter_num} 章已生成")
                    next_chapter_num += 1
                else:
                    print("✗ 章节生成失败")
                    break

            except Exception as e:
                print(f"生成过程中出现错误：{e}")
                import traceback
                traceback.print_exc()
                break

            # 显示选项
            print("\n请选择下一步操作:")
            print("1. 续写一章（生成下一章后再次询问）")
            print("2. 不续写了（退出程序）")

            while True:
                try:
                    option = input("请选择 (1/2): ").strip()
                    if option == '1':
                        print("将继续逐章生成...")
                        break
                    elif option == '2':
                        print("结束续写，感谢使用！")
                        return
                    else:
                        print("请输入有效选项 (1/2)")
                except EOFError:
                    print("错误：无法读取输入")
                    return


def continue_novel_interactive():
    """交互模式续写（供终端使用）"""
    continue_novel(topic=None)


if __name__ == "__main__":
    # 优先从环境变量获取主题名（前端通过 NOVEL_TOPIC 传递）
    env_topic = os.getenv('NOVEL_TOPIC', '').strip()
    if env_topic:
        continue_novel(topic=env_topic)
    elif len(sys.argv) > 1:
        try:
            int(sys.argv[1])
            continue_novel(topic=None)
        except ValueError:
            print("无效的参数")
    else:
        continue_novel_interactive()
