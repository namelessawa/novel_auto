"""
角色关系图谱模块
记录和分析角色之间的关系，包括情感、立场、亲密度等
"""

import json
import os
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path


class CharacterRelationshipGraph:
    """
    角色关系图谱
    维护角色之间的关系网络，支持关系查询和更新
    """

    def __init__(self, memory_dir: str = "memory_system"):
        """
        初始化关系图谱
        
        Args:
            memory_dir: 记忆存储目录
        """
        self.memory_dir = Path(memory_dir)
        self.data_file = self.memory_dir / "character_relationships.json"
        
        # 确保目录存在
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # 关系数据结构
        # {
        #     "character1": {
        #         "character2": {
        #             "relationship_type": "师徒",
        #             "emotions": {
        #                 "trust": 0.8,      # 信任度
        #                 "affection": 0.6,  # 好感度
        #                 "loyalty": 0.9,    # 忠诚度
        #                 "conflict": 0.1    # 冲突度
        #             },
        #             "status": "active",    # active/broken/dead
        #             "history": [           # 关系变化历史
        #                 {
        #                     "chapter": 1,
        #                     "event": "救命恩人",
        #                     "change": {"affection": +0.3},
        #                     "date": "2024-01-01T00:00:00"
        #                 }
        #             ],
        #             "notes": "多次救命恩人，关系深厚"
        #         }
        #     }
        # }
        self.relationships: Dict[str, Dict[str, Dict]] = {}
        
        self.load_from_disk()

    def add_relationship(
        self,
        char1: str,
        char2: str,
        relationship_type: str,
        emotions: Dict[str, float] = None,
        chapter_num: int = None,
        event: str = None
    ):
        """
        添加或更新角色关系
        
        Args:
            char1: 角色 1 名称
            char2: 角色 2 名称
            relationship_type: 关系类型（如：师徒、恋人、仇敌、朋友）
            emotions: 情感字典
            chapter_num: 章节号
            event: 关系事件描述
        """
        # 初始化角色
        if char1 not in self.relationships:
            self.relationships[char1] = {}
        if char2 not in self.relationships:
            self.relationships[char2] = {}
        
        # 默认情感值
        if emotions is None:
            emotions = {
                'trust': 0.5,
                'affection': 0.5,
                'loyalty': 0.5,
                'conflict': 0.0
            }
        
        # 更新关系
        self.relationships[char1][char2] = {
            'relationship_type': relationship_type,
            'emotions': emotions,
            'status': 'active',
            'last_updated': datetime.now().isoformat(),
            'history': []
        }
        
        # 添加历史记录
        if chapter_num or event:
            history_entry = {
                'chapter': chapter_num,
                'event': event or f"建立{relationship_type}关系",
                'change': {'initial': True},
                'date': datetime.now().isoformat()
            }
            self.relationships[char1][char2]['history'].append(history_entry)
        
        # 反向关系（对称）
        if char2 not in self.relationships:
            self.relationships[char2] = {}
        
        # 反向关系类型可能不同（如单恋）
        reverse_type = self._get_reverse_relationship(relationship_type)
        self.relationships[char2][char1] = {
            'relationship_type': reverse_type,
            'emotions': emotions.copy(),
            'status': 'active',
            'last_updated': datetime.now().isoformat(),
            'history': []
        }
        
        if chapter_num or event:
            history_entry = {
                'chapter': chapter_num,
                'event': event or f"建立{reverse_type}关系",
                'change': {'initial': True},
                'date': datetime.now().isoformat()
            }
            self.relationships[char2][char1]['history'].append(history_entry)
        
        self.save_to_disk()

    def update_emotion(
        self,
        char1: str,
        char2: str,
        emotion_changes: Dict[str, float],
        chapter_num: int = None,
        event: str = None,
        notes: str = None
    ):
        """
        更新角色间的情感值
        
        Args:
            char1: 角色 1 名称
            char2: 角色 2 名称
            emotion_changes: 情感变化字典（如：{'affection': 0.2, 'conflict': -0.1}）
            chapter_num: 章节号
            event: 事件描述
            notes: 备注
        """
        if char1 not in self.relationships or char2 not in self.relationships[char1]:
            print(f"警告：{char1} 和 {char2} 之间不存在关系")
            return False
        
        relationship = self.relationships[char1][char2]
        
        # 更新情感值
        for emotion, change in emotion_changes.items():
            if emotion in relationship['emotions']:
                old_value = relationship['emotions'][emotion]
                new_value = max(0.0, min(1.0, old_value + change))  # 限制在 0-1 之间
                relationship['emotions'][emotion] = new_value
        
        relationship['last_updated'] = datetime.now().isoformat()
        
        # 添加历史记录
        if chapter_num is not None or event:
            history_entry = {
                'chapter': chapter_num,
                'event': event or '情感变化',
                'change': emotion_changes,
                'date': datetime.now().isoformat()
            }
            relationship['history'].append(history_entry)
        
        # 更新备注
        if notes:
            relationship['notes'] = notes
        
        self.save_to_disk()
        return True

    def get_relationship(self, char1: str, char2: str) -> Optional[Dict]:
        """
        获取两个角色之间的关系
        
        Args:
            char1: 角色 1 名称
            char2: 角色 2 名称
            
        Returns:
            Optional[Dict]: 关系信息，不存在返回 None
        """
        if char1 in self.relationships and char2 in self.relationships[char1]:
            return self.relationships[char1][char2].copy()
        return None

    def get_all_relationships(self, character: str) -> Dict[str, Dict]:
        """
        获取某个角色的所有关系
        
        Args:
            character: 角色名称
            
        Returns:
            Dict[str, Dict]: 关系字典
        """
        if character in self.relationships:
            return {k: v.copy() for k, v in self.relationships[character].items()}
        return {}

    def get_relationship_summary(self, character: str) -> str:
        """
        获取角色关系的文本摘要
        
        Args:
            character: 角色名称
            
        Returns:
            str: 关系摘要
        """
        relationships = self.get_all_relationships(character)
        
        if not relationships:
            return f"[{character}] 暂无已知关系"
        
        summary_parts = [f"[{character} 的人际关系]:"]
        
        for other_char, rel in relationships.items():
            rel_type = rel.get('relationship_type', '未知')
            emotions = rel.get('emotions', {})
            
            # 情感描述
            emotion_desc = []
            if emotions.get('affection', 0.5) > 0.7:
                emotion_desc.append("好感")
            elif emotions.get('affection', 0.5) < 0.3:
                emotion_desc.append("反感")
            
            if emotions.get('trust', 0.5) > 0.7:
                emotion_desc.append("信任")
            elif emotions.get('trust', 0.5) < 0.3:
                emotion_desc.append("怀疑")
            
            if emotions.get('conflict', 0) > 0.5:
                emotion_desc.append("冲突")
            
            emotion_str = f"({', '.join(emotion_desc)})" if emotion_desc else ""
            
            summary_parts.append(f"  - {other_char}: {rel_type} {emotion_str}")
        
        return "\n".join(summary_parts)

    def analyze_relationship_tension(self, char1: str, char2: str) -> Dict[str, Any]:
        """
        分析两个角色之间的关系张力
        
        Args:
            char1: 角色 1 名称
            char2: 角色 2 名称
            
        Returns:
            Dict: 张力分析结果
        """
        relationship = self.get_relationship(char1, char2)
        
        if not relationship:
            return {'exists': False}
        
        emotions = relationship.get('emotions', {})
        
        # 计算张力分数
        positive = (
            emotions.get('trust', 0.5) * 0.3 +
            emotions.get('affection', 0.5) * 0.4 +
            emotions.get('loyalty', 0.5) * 0.3
        )
        negative = emotions.get('conflict', 0)
        
        tension_score = abs(positive - negative)
        stability = 1.0 - min(positive, negative)  # 越低越不稳定
        
        return {
            'exists': True,
            'relationship_type': relationship.get('relationship_type'),
            'positive_score': positive,
            'negative_score': negative,
            'tension_score': tension_score,
            'stability': stability,
            'status': relationship.get('status'),
            'history_count': len(relationship.get('history', []))
        }

    def _get_reverse_relationship(self, relationship_type: str) -> str:
        """
        获取反向关系类型
        
        Args:
            relationship_type: 原关系类型
            
        Returns:
            str: 反向关系类型
        """
        # 对称关系
        symmetric = ['朋友', '敌人', '夫妻', '恋人', '同事', '盟友', '仇敌']
        if relationship_type in symmetric:
            return relationship_type
        
        # 非对称关系映射
        reverse_map = {
            '暗恋': '被暗恋',
            '救命恩人': '被救者',
            '恩人': '受恩者',
            '主人': '仆人',
            '上司': '下属',
            '师父': '徒弟',
            '徒弟': '师父',
            '师徒': '师徒',
            '父亲': '儿子',
            '儿子': '父亲',
            '母亲': '女儿',
            '女儿': '母亲',
            '父子': '父子',
            '母女': '母女',
        }
        
        return reverse_map.get(relationship_type, relationship_type)

    def to_text_description(self) -> str:
        """
        转换为文本描述（用于 Prompt）
        
        Returns:
            str: 关系描述文本
        """
        if not self.relationships:
            return "[角色关系]: 暂无已知角色关系"
        
        all_chars = set(self.relationships.keys())
        descriptions = ["[角色关系图谱]:"]
        
        for char in sorted(all_chars):
            relationships = self.get_all_relationships(char)
            if relationships:
                rel_strs = []
                for other, rel in relationships.items():
                    rel_type = rel.get('relationship_type', '未知')
                    rel_strs.append(f"{other}({rel_type})")
                
                if rel_strs:
                    descriptions.append(f"  {char}: {', '.join(rel_strs)}")
        
        return "\n".join(descriptions)

    def save_to_disk(self):
        """保存到磁盘"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.relationships, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存关系数据失败：{e}")

    def load_from_disk(self):
        """从磁盘加载"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.relationships = json.load(f)
            except Exception as e:
                print(f"加载关系数据失败：{e}")
                self.relationships = {}

    def clear(self):
        """清空所有关系"""
        self.relationships = {}
        self.save_to_disk()


# ----------------------------------------------------------------------------
# v2.x 适配器 - 把情感量化逻辑提取为独立工具类
# ----------------------------------------------------------------------------


class RelationAnalyzer:
    """情感向量 + 张力打分提取版 - 与 CharacterRelationshipGraph 解耦。

    新架构中 ``KnowledgeGraph.Relation.attributes`` 是关系存储后端,
    本类负责对其计算情感张力,供 Showrunner / ConsistencyGuardian 调用。
    """

    EMOTION_KEYS = ("trust", "affection", "loyalty", "conflict")

    @staticmethod
    def emotion_vector(rel_attributes: dict) -> dict:
        """从一个关系的 attributes dict 提取情感四元向量,缺失值视为 0。"""
        emo = (rel_attributes or {}).get("emotions", {}) or rel_attributes or {}
        return {
            k: float(emo.get(k, 0.0))
            for k in RelationAnalyzer.EMOTION_KEYS
        }

    @staticmethod
    def tension_score(rel_attributes: dict) -> float:
        """关系张力分数 0-1。conflict 高 + trust/affection 低 → 高张力。"""
        v = RelationAnalyzer.emotion_vector(rel_attributes)
        positive = (v["trust"] + v["affection"] + v["loyalty"]) / 3.0
        return max(0.0, min(1.0, v["conflict"] - positive * 0.5 + 0.5))

    @staticmethod
    def stability_score(rel_attributes: dict) -> float:
        """稳定性 0-1。trust + loyalty 平均。"""
        v = RelationAnalyzer.emotion_vector(rel_attributes)
        return max(0.0, min(1.0, (v["trust"] + v["loyalty"]) / 2.0))

    @staticmethod
    def trust_int(rel_attributes: dict) -> int:
        """折算为 tick 架构 Relationship.trust (-10 到 +10)。"""
        v = RelationAnalyzer.emotion_vector(rel_attributes)
        # trust 0-1 → 0 到 +10; conflict 0-1 → 0 到 -10
        score = v["trust"] * 10 - v["conflict"] * 10
        return int(round(max(-10, min(10, score))))


# 使用示例
if __name__ == "__main__":
    graph = CharacterRelationshipGraph("test_memory")
    
    # 添加关系
    graph.add_relationship(
        "林风", "慕容雪", "恋人",
        emotions={
            'trust': 0.9,
            'affection': 0.95,
            'loyalty': 0.8,
            'conflict': 0.1
        },
        chapter_num=1,
        event="初次相遇，一见钟情"
    )
    
    graph.add_relationship(
        "林风", "王霸", "仇敌",
        emotions={
            'trust': 0.1,
            'affection': 0.1,
            'loyalty': 0.0,
            'conflict': 0.9
        },
        chapter_num=2,
        event="争夺宝物，结下梁子"
    )
    
    # 更新情感
    graph.update_emotion(
        "林风", "慕容雪",
        {'affection': 0.05, 'trust': 0.05},
        chapter_num=3,
        event="慕容雪救了林风一命",
        notes="感情加深"
    )
    
    # 查询关系
    print("\n林风与慕容雪的关系:")
    rel = graph.get_relationship("林风", "慕容雪")
    if rel:
        print(f"  关系类型：{rel['relationship_type']}")
        print(f"  情感状态：{rel['emotions']}")
    
    # 关系摘要
    print("\n" + graph.get_relationship_summary("林风"))
    
    # 张力分析
    print("\n林风与王霸的关系张力:")
    tension = graph.analyze_relationship_tension("林风", "王霸")
    print(f"  张力分数：{tension.get('tension_score', 0):.2f}")
    print(f"  稳定性：{tension.get('stability', 0):.2f}")
    
    # 清理测试数据
    import shutil
    if os.path.exists("test_memory"):
        shutil.rmtree("test_memory")
