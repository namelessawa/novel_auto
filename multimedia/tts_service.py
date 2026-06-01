"""
文本转语音服务模块
支持多种TTS引擎，包括Edge TTS、Azure TTS等
"""

import asyncio
import edge_tts
import os
from pathlib import Path
from typing import Optional


class TTSService:
    """
    文本转语音服务类
    """
    
    def __init__(self, output_dir: str = "temp_audio"):
        """
        初始化TTS服务
        
        Args:
            output_dir: 音频输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 默认语音配置
        self.default_voice = "zh-CN-XiaoxiaoNeural"  # 中文女声
        self.default_rate = "+0%"  # 语速
        self.default_volume = "+0%"  # 音量
    
    async def text_to_speech(self, text: str, output_path: str, voice: str = None, 
                           rate: str = None, volume: str = None) -> bool:
        """
        将文本转换为语音
        
        Args:
            text: 要转换的文本
            output_path: 输出音频文件路径
            voice: 语音类型，默认使用中文女声
            rate: 语速，默认正常
            volume: 音量，默认正常
            
        Returns:
            bool: 转换是否成功
        """
        try:
            # 使用默认配置或传入的配置
            voice = voice or self.default_voice
            rate = rate or self.default_rate
            volume = volume or self.default_volume
            
            # 创建通信对象
            communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
            
            # 保存音频到文件
            await communicate.save(output_path)
            
            print(f"音频已保存到: {output_path}")
            return True
            
        except Exception as e:
            print(f"TTS转换失败: {str(e)}")
            return False
    
    def synthesize_chapter_audio(self, chapter_content: str, output_file: str) -> bool:
        """
        为整章内容生成音频
        
        Args:
            chapter_content: 章节内容
            output_file: 输出音频文件路径
            
        Returns:
            bool: 生成是否成功
        """
        # 分割长文本，避免TTS服务限制
        chunks = self._split_text_for_tts(chapter_content)
        
        if len(chunks) == 1:
            # 短文本直接转换
            return asyncio.run(self.text_to_speech(chapter_content, output_file))
        else:
            # 长文本分块处理后合并
            temp_files = []
            for i, chunk in enumerate(chunks):
                temp_file = self.output_dir / f"temp_chunk_{i}.mp3"
                temp_files.append(temp_file)
                
                success = asyncio.run(self.text_to_speech(chunk, str(temp_file)))
                if not success:
                    # 清理临时文件
                    self._cleanup_temp_files(temp_files)
                    return False
            
            # 合并音频片段
            success = self._merge_audio_files(temp_files, output_file)
            
            # 清理临时文件
            self._cleanup_temp_files(temp_files)
            
            return success
    
    def _split_text_for_tts(self, text: str, max_chars: int = 1000) -> list:
        """
        将长文本分割为适合TTS处理的块
        
        Args:
            text: 原始文本
            max_chars: 每块最大字符数
            
        Returns:
            list: 分割后的文本块列表
        """
        if len(text) <= max_chars:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # 按句子分割，避免在句子中间切断
        sentences = text.split('。')
        sentences = [s + '。' for s in sentences[:-1]] + [sentences[-1]]  # 重新加上句号
        
        for sentence in sentences:
            if len(current_chunk + sentence) <= max_chars:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _merge_audio_files(self, input_files: list, output_file: str) -> bool:
        """
        合并多个音频文件
        
        Args:
            input_files: 输入音频文件列表
            output_file: 输出音频文件路径
            
        Returns:
            bool: 合并是否成功
        """
        try:
            import subprocess
            
            # 使用ffmpeg合并音频文件
            cmd = ['ffmpeg', '-y']
            
            for file in input_files:
                cmd.extend(['-i', str(file)])
            
            cmd.extend([
                '-c:a', 'copy',  # 音频编码
                '-f', 'concat',  # 格式
                '-safe', '0',    # 安全模式
                output_file
            ])
            
            # 执行合并命令
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"音频合并失败: {result.stderr}")
                return False
            
            print(f"音频合并完成: {output_file}")
            return True
            
        except Exception as e:
            print(f"音频合并出错: {str(e)}")
            return False
    
    def _cleanup_temp_files(self, temp_files: list):
        """
        清理临时文件
        
        Args:
            temp_files: 临时文件列表
        """
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                print(f"删除临时文件失败 {temp_file}: {str(e)}")


# 示例使用
if __name__ == "__main__":
    # 创建TTS服务实例
    tts = TTSService()
    
    # 示例文本
    sample_text = "这是一段测试文本，用于演示文本转语音功能。"
    
    # 生成音频
    success = asyncio.run(tts.text_to_speech(sample_text, "sample_output.mp3"))
    
    if success:
        print("TTS转换成功！")
    else:
        print("TTS转换失败！")