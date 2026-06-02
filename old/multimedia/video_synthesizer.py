"""
视频合成服务模块
将文本、语音、图片合成视频
"""

import os
from pathlib import Path
from typing import List, Optional
try:
    from moviepy.editor import *
    MOVIEPY_AVAILABLE = True
except ImportError:
    print("Warning: moviepy not installed. Video synthesis functionality will be disabled.")
    # 定义空的类和函数作为占位符
    class VideoFileClip:
        def __init__(self, *args, **kwargs):
            pass
    class AudioFileClip:
        def __init__(self, *args, **kwargs):
            pass
        def __getattr__(self, name):
            # 返回一个模拟的方法，始终返回自身以支持链式调用
            def dummy_method(*args, **kwargs):
                return self
            return dummy_method
        @property
        def duration(self):
            return 0
        @property
        def size(self):
            return (1280, 720)
    class ImageClip:
        def __init__(self, *args, **kwargs):
            pass
        def __getattr__(self, name):
            def dummy_method(*args, **kwargs):
                return self
            return dummy_method
        def resize(self, *args, **kwargs):
            return self
        def set_position(self, *args, **kwargs):
            return self
        def set_duration(self, *args, **kwargs):
            return self
    class ColorClip:
        def __init__(self, *args, **kwargs):
            pass
        def __getattr__(self, name):
            def dummy_method(*args, **kwargs):
                return self
            return dummy_method
        def set_audio(self, *args, **kwargs):
            return self
    class TextClip:
        def __init__(self, *args, **kwargs):
            pass
        def __getattr__(self, name):
            def dummy_method(*args, **kwargs):
                return self
            return dummy_method
        def resize(self, *args, **kwargs):
            return self
        def set_start(self, *args, **kwargs):
            return self
        def set_end(self, *args, **kwargs):
            return self
        def set_position(self, *args, **kwargs):
            return self
        @property
        def size(self):
            return (100, 50)
    class CompositeVideoClip:
        def __init__(self, *args, **kwargs):
            pass
        def __getattr__(self, name):
            def dummy_method(*args, **kwargs):
                return self
            return dummy_method
    class concatenate_videoclips:
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, *args, **kwargs):
            return self
    MOVIEPY_AVAILABLE = False
import tempfile


class VideoSynthesizer:
    """
    视频合成服务类
    将文本、语音、图片合成视频
    """
    
    def __init__(self):
        """
        初始化视频合成服务
        """
        pass
    
    def create_video_from_multimedia(self, 
                                   text_content: str, 
                                   audio_path: str, 
                                   image_paths: List[str], 
                                   output_path: str,
                                   text_display_duration: float = 5.0) -> bool:
        """
        从文本、音频、图片合成视频
        
        Args:
            text_content: 文本内容
            audio_path: 音频文件路径
            image_paths: 图片文件路径列表
            output_path: 输出视频文件路径
            text_display_duration: 每段文本显示时长（秒）
            
        Returns:
            bool: 合成是否成功
        """
        if not MOVIEPY_AVAILABLE:
            print("视频合成功能不可用 - 请安装moviepy: pip install moviepy")
            return False
            
        try:
            # 加载音频
            audio_clip = AudioFileClip(audio_path)
            total_duration = audio_clip.duration
            
            # 创建图片轮播
            image_clips = []
            num_images = len(image_paths)
            
            if num_images > 0:
                # 计算每张图片显示时长
                image_duration = total_duration / num_images
                
                for img_path in image_paths:
                    img_clip = ImageClip(img_path).set_duration(image_duration)
                    img_clip = img_clip.resize(height=720)  # 调整高度为720p
                    img_clip = img_clip.set_position(('center', 'center'))
                    image_clips.append(img_clip)
                
                # 拼接图片剪辑
                image_sequence = concatenate_videoclips(image_clips, method="compose")
            else:
                # 如果没有图片，创建一个黑色背景
                image_sequence = ColorClip(size=(1280, 720), color=(0, 0, 0), duration=total_duration)
            
            # 设置音频
            image_sequence = image_sequence.set_audio(audio_clip)
            
            # 添加文本字幕
            video_with_text = self._add_text_subtitles(image_sequence, text_content, total_duration)
            
            # 输出视频
            video_with_text.write_videofile(
                output_path,
                fps=24,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True
            )
            
            print(f"视频已保存到: {output_path}")
            return True
            
        except Exception as e:
            print(f"视频合成失败: {str(e)}")
            return False
    
    def _add_text_subtitles(self, video_clip, text_content: str, total_duration: float):
        """
        为视频添加文本字幕
        
        Args:
            video_clip: 原始视频剪辑
            text_content: 文本内容
            total_duration: 视频总时长
            
        Returns:
            VideoClip: 添加了字幕的视频剪辑
        """
        if not MOVIEPY_AVAILABLE:
            # 如果moviepy不可用，直接返回原视频
            return video_clip
        
        # 将文本按句子分割
        sentences = self._split_text_into_sentences(text_content)
        
        if not sentences:
            return video_clip
        
        # 计算每个句子的显示时长
        sentence_duration = total_duration / len(sentences)
        
        # 创建文本剪辑列表
        text_clips = []
        
        for i, sentence in enumerate(sentences):
            start_time = i * sentence_duration
            end_time = min(start_time + sentence_duration, total_duration)
            
            # 创建文本剪辑
            txt_clip = TextClip(
                sentence,
                fontsize=24,
                color='white',
                bg_color='black',
                size=(video_clip.size[0] * 0.8, None),
                method='caption'
            )
            
            # 调整文本大小以适应视频宽度
            if txt_clip.size[0] > video_clip.size[0] * 0.9:
                txt_clip = txt_clip.resize(width=video_clip.size[0] * 0.9)
            
            # 设置位置和时间
            txt_clip = txt_clip.set_start(start_time).set_end(end_time)
            txt_clip = txt_clip.set_position(('center', 'bottom')).margin(bottom=50)
            
            text_clips.append(txt_clip)
        
        # 合成视频和文本
        final_video = CompositeVideoClip([video_clip] + text_clips)
        
        return final_video
    
    def _split_text_into_sentences(self, text: str) -> List[str]:
        """
        将文本分割成句子
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 句子列表
        """
        import re
        
        # 使用正则表达式分割句子
        sentences = re.split(r'[。！？.!?]', text)
        
        # 过滤空字符串并去除首尾空白
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # 如果句子太长，进一步分割
        final_sentences = []
        for sentence in sentences:
            if len(sentence) > 50:  # 如果句子超过50个字符
                # 按逗号分割
                sub_sentences = re.split(r'[，,]', sentence)
                for sub_sentence in sub_sentences:
                    sub_sentence = sub_sentence.strip()
                    if sub_sentence:
                        if len(sub_sentence) > 50:
                            # 如果仍然太长，按长度分割
                            for i in range(0, len(sub_sentence), 50):
                                final_sentences.append(sub_sentence[i:i+50])
                        else:
                            final_sentences.append(sub_sentence)
            else:
                final_sentences.append(sentence)
        
        return final_sentences
    
    def create_simple_video(self, 
                          audio_path: str, 
                          image_paths: List[str], 
                          output_path: str) -> bool:
        """
        创建简单视频（仅音频+图片轮播）
        
        Args:
            audio_path: 音频文件路径
            image_paths: 图片文件路径列表
            output_path: 输出视频文件路径
            
        Returns:
            bool: 合成是否成功
        """
        if not MOVIEPY_AVAILABLE:
            print("视频合成功能不可用 - 请安装moviepy: pip install moviepy")
            return False
            
        try:
            # 加载音频
            audio_clip = AudioFileClip(audio_path)
            total_duration = audio_clip.duration
            
            if len(image_paths) == 0:
                # 如果没有图片，创建纯音频视频
                black_clip = ColorClip(size=(1280, 720), color=(0, 0, 0), duration=total_duration)
                final_video = black_clip.set_audio(audio_clip)
            else:
                # 计算每张图片显示时长
                num_images = len(image_paths)
                image_duration = total_duration / num_images
                
                # 创建图片剪辑
                image_clips = []
                for img_path in image_paths:
                    img_clip = ImageClip(img_path).set_duration(image_duration)
                    img_clip = img_clip.resize(height=720)
                    img_clip = img_clip.set_position(('center', 'center'))
                    image_clips.append(img_clip)
                
                # 拼接图片
                image_sequence = concatenate_videoclips(image_clips, method="compose")
                
                # 设置音频
                final_video = image_sequence.set_audio(audio_clip)
            
            # 输出视频
            final_video.write_videofile(
                output_path,
                fps=24,
                codec='libx264',
                audio_codec='aac'
            )
            
            print(f"简单视频已保存到: {output_path}")
            return True
            
        except Exception as e:
            print(f"简单视频合成失败: {str(e)}")
            return False


# 示例使用
if __name__ == "__main__":
    synthesizer = VideoSynthesizer()
    
    # 示例：合成视频
    # synthesizer.create_video_from_multimedia(
    #     text_content="这是一段示例文本",
    #     audio_path="sample_audio.mp3",
    #     image_paths=["image1.jpg", "image2.jpg"],
    #     output_path="output_video.mp4"
    # )