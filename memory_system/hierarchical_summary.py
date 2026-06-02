"""层级摘要 (LEGACY since v2.x).

v2.x 新架构使用 ``novel_frame/backend/memory/summary_tree.py`` (SummaryTree)
+ ``novel_frame/backend/agents/memory_compressor.py`` (MemoryCompressor) 取代。
本模块仍然保留以兼容 NovelGenerator,并新增 ``get_l1_summaries`` /
``get_l2_arcs`` / ``get_l3_outline`` 读取接口供 MemoryCompressor 反向读取。
"""

import json
import os
from typing import Dict, List, Optional
from datetime import datetime


class HierarchicalSummarizer:
    """
    层级摘要机制
    对历史文本进行分级压缩，包括高层大纲、中层弧线和底层提要
    """
    
    def __init__(self, memory_dir: str = "memory_system"):
        self.memory_dir = memory_dir
        self.summary_file = os.path.join(memory_dir, "hierarchical_summary.json")
        
        # 确保目录存在
        os.makedirs(self.memory_dir, exist_ok=True)
        
        # 初始化摘要数据
        self.high_level_outline = ""  # 整本小说的核心主线与最终目标
        self.mid_level_arcs = []      # 当前剧情篇章的梗概
        self.low_level_summaries = [] # 最近章节的具体剧情走向
        self.last_updated = None
        
        self.load_from_disk()
    
    def update_high_level_outline(self, outline: str):
        """更新高层大纲"""
        self.high_level_outline = outline
        self.last_updated = datetime.now().isoformat()
        self.save_to_disk()
    
    def add_mid_level_arc(self, arc_title: str, arc_summary: str):
        """添加中层剧情弧线"""
        arc_entry = {
            'title': arc_title,
            'summary': arc_summary,
            'created_at': datetime.now().isoformat()
        }
        self.mid_level_arcs.append(arc_entry)
        
        # 限制中层弧线数量，只保留最近的几个
        if len(self.mid_level_arcs) > 10:  # 可调整数量
            self.mid_level_arcs = self.mid_level_arcs[-10:]
        
        self.last_updated = datetime.now().isoformat()
        self.save_to_disk()
    
    def add_low_level_summary(self, chapter_num: int, title: str, summary: str):
        """添加底层章节摘要"""
        summary_entry = {
            'chapter_num': chapter_num,
            'title': title,
            'summary': summary,
            'created_at': datetime.now().isoformat()
        }
        self.low_level_summaries.append(summary_entry)
        
        # 限制底层摘要数量，只保留最近的几个
        if len(self.low_level_summaries) > 5:  # 只保留最近5章
            self.low_level_summaries = self.low_level_summaries[-5:]
        
        self.last_updated = datetime.now().isoformat()
        self.save_to_disk()
    
    def get_hierarchical_context(self, max_levels: int = 3) -> str:
        """
        获取层级摘要上下文

        Args:
            max_levels: 最大层级数 (1=仅高层大纲, 2=+弧线, 3=+章节摘要)
        """
        context_parts = ["[故事大纲与前情提要]:"]

        # 添加高层大纲 (level 1)
        if max_levels >= 1 and self.high_level_outline:
            context_parts.append(f"\n高层大纲: {self.high_level_outline}")

        # 添加中层剧情弧线 (level 2)
        if max_levels >= 2 and self.mid_level_arcs:
            context_parts.append("\n中层剧情弧线:")
            for arc in self.mid_level_arcs[-3:]:
                context_parts.append(f"- {arc['title']}: {arc['summary']}")

        # 添加底层章节摘要 (level 3)
        if max_levels >= 3 and self.low_level_summaries:
            context_parts.append("\n近期章节摘要:")
            for summary in self.low_level_summaries:
                context_parts.append(f"第{summary['chapter_num']}章《{summary['title']}》: {summary['summary']}")

        return "\n".join(context_parts)
    
    def load_from_disk(self):
        """从磁盘加载摘要数据"""
        if os.path.exists(self.summary_file):
            try:
                with open(self.summary_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.high_level_outline = data.get('high_level_outline', '')
                    self.mid_level_arcs = data.get('mid_level_arcs', [])
                    self.low_level_summaries = data.get('low_level_summaries', [])
                    self.last_updated = data.get('last_updated')
            except Exception as e:
                print(f"加载层级摘要失败: {e}")
                self.high_level_outline = ""
                self.mid_level_arcs = []
                self.low_level_summaries = []
        else:
            self.high_level_outline = ""
            self.mid_level_arcs = []
            self.low_level_summaries = []
    
    def save_to_disk(self):
        """保存摘要数据到磁盘"""
        try:
            data = {
                'high_level_outline': self.high_level_outline,
                'mid_level_arcs': self.mid_level_arcs,
                'low_level_summaries': self.low_level_summaries,
                'last_updated': self.last_updated
            }
            with open(self.summary_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存层级摘要失败: {e}")
    
    def clear(self):
        """清空摘要数据"""
        self.high_level_outline = ""
        self.mid_level_arcs = []
        self.low_level_summaries = []
        self.save_to_disk()

    # ------------------------------------------------------------------
    # v2.x 适配器 - MemoryCompressor 的 L1/L2/L3 读取接口
    # ------------------------------------------------------------------

    def get_l1_summaries(self):
        """L1 = 章节级摘要(low_level_summaries),返回纯字符串列表。"""
        return [s.get("summary", "") for s in self.low_level_summaries if s.get("summary")]

    def get_l2_arcs(self):
        """L2 = 弧线级摘要(mid_level_arcs),返回 (title, summary) 元组列表。"""
        return [
            (a.get("title", "未命名弧线"), a.get("summary", ""))
            for a in self.mid_level_arcs
            if a.get("summary")
        ]

    def get_l3_outline(self):
        """L3 = 全书大纲(high_level_outline)。"""
        return self.high_level_outline or ""