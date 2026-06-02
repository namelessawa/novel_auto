"""
多媒体资源管理器
统一管理文本、语音、图片和视频的生成与存储
"""

import os
from pathlib import Path
from typing import List, Optional
from core.config import (
    DASHSCOPE_API_KEY,
    IMAGES_PER_CHAPTER,
    TTS_VOICE,
    TTS_RATE,
    TTS_VOLUME,
)
from .tts_service import TTSService
from .image_generator import ImageGenerator
from .video_synthesizer import VideoSynthesizer


class MultimediaManager:
    """
    多媒体资源管理器
    负责协调文本、语音、图片和视频的生成与存储
    """

    def __init__(self, api_key: str = None):
        """
        初始化多媒体管理器

        Args:
            api_key: 图片生成 API 密钥
        """
        # 使用配置文件中的默认值
        self.api_key = api_key or DASHSCOPE_API_KEY
        
        # 初始化 TTS 服务
        self.tts_service = TTSService(output_dir="temp_audio")
        
        # 初始化图片生成器
        self.image_generator = ImageGenerator(api_key=self.api_key)
        
        # 初始化视频合成器
        self.video_synthesizer = VideoSynthesizer()

    def generate_multimedia_for_chapter(
        self,
        chapter_title: str,
        chapter_content: str,
        topic_dir: str,
        num_images: int = None
    ) -> bool:
        """
        为指定章节生成全套多媒体内容

        Args:
            chapter_title: 章节标题
            chapter_content: 章节内容
            topic_dir: 主题目录
            num_images: 生成图片数量（默认使用配置文件中的值）

        Returns:
            bool: 生成是否成功
        """
        if num_images is None:
            num_images = IMAGES_PER_CHAPTER
            
        try:
            # 创建章节多媒体目录
            chapter_num = self._extract_chapter_number(chapter_title)
            multimedia_dir = Path(topic_dir) / "multimedia" / f"chapter_{chapter_num:03d}_{chapter_title}"
            multimedia_dir.mkdir(parents=True, exist_ok=True)

            # 创建音频子目录
            audio_dir = multimedia_dir / "audio"
            audio_dir.mkdir(exist_ok=True)

            # 创建图片子目录
            images_dir = multimedia_dir / "images"
            images_dir.mkdir(exist_ok=True)

            # 创建视频子目录
            video_dir = multimedia_dir / "video"
            video_dir.mkdir(exist_ok=True)

            # 生成音频
            audio_path = audio_dir / f"chapter_{chapter_num:03d}_audio.mp3"
            print(f"正在生成音频：{audio_path}")
            audio_success = self.tts_service.synthesize_chapter_audio(chapter_content, str(audio_path))

            if not audio_success:
                print("音频生成失败")
                return False

            # 生成图片
            print(f"正在生成图片到：{images_dir}")
            image_paths = self.image_generator.generate_chapter_images(
                chapter_content,
                str(images_dir),
                num_images=num_images
            )

            if not image_paths:
                print("图片生成失败或未生成任何图片")
                # 即使图片生成失败，也继续执行（视频可以只有音频）

            # 生成视频
            video_path = video_dir / f"chapter_{chapter_num:03d}_video.mp4"
            print(f"正在生成视频：{video_path}")

            if image_paths and os.path.exists(str(audio_path)):
                # 如果有图片和音频，生成完整视频
                video_success = self.video_synthesizer.create_video_from_multimedia(
                    chapter_content,
                    str(audio_path),
                    image_paths,
                    str(video_path)
                )
            elif os.path.exists(str(audio_path)):
                # 如果只有音频，生成简单视频（黑屏 + 音频）
                video_success = self.video_synthesizer.create_simple_video(
                    str(audio_path),
                    image_paths,
                    str(video_path)
                )
            else:
                print("缺少音频文件，无法生成视频")
                video_success = False

            if not video_success:
                print("视频生成失败")
                return False

            print(f"章节 {chapter_title} 的多媒体内容生成完成")
            print(f"  - 音频：{audio_path}")
            print(f"  - 图片：{len(image_paths)} 张")
            print(f"  - 视频：{video_path}")

            return True

        except Exception as e:
            print(f"生成章节多媒体内容时出错：{str(e)}")
            return False

    def _extract_chapter_number(self, chapter_title: str) -> int:
        """
        从章节标题中提取章节号

        Args:
            chapter_title: 章节标题

        Returns:
            int: 章节号
        """
        import re
        # 尝试匹配 "第 X 章" 格式
        match = re.search(r'第 (\d+) 章', chapter_title)
        if match:
            return int(match.group(1))

        # 如果没有找到，返回 1 作为默认值
        return 1


# 示例使用
if __name__ == "__main__":
    # 需要提供 API 密钥
    # manager = MultimediaManager(api_key="your-dashscope-api-key")

    # 示例内容
    # chapter_title = "第一章"
    # chapter_content = "这是一个示例章节内容，用于测试多媒体生成功能。"
    # topic_dir = "./results/test_topic"

    # success = manager.generate_multimedia_for_chapter(chapter_title, chapter_content, topic_dir)
    # if success:
    #     print("多媒体内容生成成功！")
    # else:
    #     print("多媒体内容生成失败！")
    pass  # 添加 pass 语句以避免缩进错误
