import json
import os
from typing import List, Dict, Optional

# Import token counter for accurate token counting
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.token_counter import TokenCounter


class SlidingWindowMemory:
    """
    滑动窗口机制（短期记忆）
    保留最近生成的N个Token（例如最后的2000-3000字）

    Updated to use token-based counting (not character count) for accuracy
    """

    def __init__(self, max_tokens: int = 2500, memory_dir: str = "memory_system"):
        self.max_tokens = max_tokens
        self.memory_dir = memory_dir
        self.window_file = os.path.join(memory_dir, "sliding_window.json")

        # 确保目录存在
        os.makedirs(self.memory_dir, exist_ok=True)

        # 初始化窗口内容
        self.content = []

        # Token counter for accurate counting
        self.token_counter = TokenCounter()

        self.load_from_disk()
    
    def add_content(self, chapter_title: str, chapter_content: str):
        """添加新的章节内容到滑动窗口"""
        # Calculate token count using accurate token counting
        new_item = {
            "title": chapter_title,
            "content": chapter_content,
            "token_count": self.token_counter.count_tokens(chapter_content),
            "char_count": len(chapter_content)  # Keep for backward compatibility
        }

        # 添加到内容列表
        self.content.append(new_item)

        # 如果超出最大token限制，则移除最早的内容
        self._trim_to_max_tokens()

        # 保存到磁盘
        self.save_to_disk()
    
    def get_context(self, max_chars: int = None, max_tokens: int = None) -> str:
        """
        获取当前滑动窗口的内容作为上下文

        Args:
            max_chars: 最大字符数限制，超出时从最早的内容开始截断 (deprecated)
            max_tokens: 最大token数限制，超出时截断

        Returns:
            str: Context string
        """
        context_parts = []
        for item in self.content:
            context_parts.append(f"### {item['title']}\n{item['content']}\n")

        result = "".join(context_parts)

        # Use token-based limiting if specified
        if max_tokens:
            result = self.token_counter.truncate_to_tokens(result, max_tokens)
        elif max_chars and len(result) > max_chars:
            # Fallback to character-based for backward compatibility
            result = result[-max_chars:]

        return result

    def get_token_count(self) -> int:
        """
        Get total token count of all content in window

        Returns:
            int: Total token count
        """
        return sum(item.get('token_count', item.get('char_count', 0)) for item in self.content)

    def _trim_to_max_tokens(self):
        """修剪内容以保持在最大token限制内 (uses accurate token counting)"""
        total_tokens = self.get_token_count()

        while total_tokens > self.max_tokens and len(self.content) > 1:
            removed_item = self.content.pop(0)
            total_tokens -= removed_item.get('token_count', removed_item.get('char_count', 0))
    
    def load_from_disk(self):
        """从磁盘加载滑动窗口内容"""
        if os.path.exists(self.window_file):
            try:
                with open(self.window_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.content = data.get('content', [])
            except Exception as e:
                print(f"加载滑动窗口失败: {e}")
                self.content = []
        else:
            self.content = []
    
    def save_to_disk(self):
        """保存滑动窗口内容到磁盘"""
        try:
            data = {
                'max_tokens': self.max_tokens,
                'content': self.content
            }
            with open(self.window_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存滑动窗口失败: {e}")
    
    def clear(self):
        """清空滑动窗口"""
        self.content = []
        self.save_to_disk()

    # ------------------------------------------------------------------
    # v2.x 适配器 - MemoryCompressor / TickState 读取接口
    # ------------------------------------------------------------------

    def get_sections(self):
        """返回所有滑动窗口条目的 Section dataclass 列表(v2.x 兼容)。

        SlidingWindow 旧实现以章节聚合内容,这里把每条转换为遗留
        ``memory_system.models.Section``,供 MemoryCompressor / SummaryTree 消费。
        """
        from memory_system.models import Section

        sections = []
        for idx, item in enumerate(self.content, start=1):
            title = item.get("title") or f"chapter_{idx}"
            content = item.get("content") or ""
            sections.append(
                Section(
                    chapter=idx,
                    section=1,
                    title=str(title)[:120],
                    content=str(content),
                    summary="",
                    word_count=item.get("char_count", len(content)),
                )
            )
        return sections