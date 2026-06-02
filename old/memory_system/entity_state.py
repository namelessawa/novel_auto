import copy
import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path


class EntityStateTracker:
    """
    全局状态追踪（实体状态机/知识图谱）
    维护一个动态更新的结构化数据，记录小说中的核心元素
    支持版本快照，可回溯到任意章节的状态
    """

    def __init__(self, memory_dir: str = "memory_system"):
        self.memory_dir = memory_dir
        self.state_file = os.path.join(memory_dir, "entity_state.json")
        self.snapshot_dir = Path(memory_dir) / "entity_snapshots"

        # 确保目录存在
        os.makedirs(self.memory_dir, exist_ok=True)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        # 初始化状态数据
        self.entities = {}  # 存储人物、地点、物品等实体
        self.world_state = {}  # 存储世界观/规则
        self.last_updated = None
        self.current_chapter = 0  # 当前章节号

        self.load_from_disk()

    def _save_snapshot(self, chapter_num: int):
        """
        保存当前状态的快照
        
        Args:
            chapter_num: 章节号
        """
        snapshot_data = {
            'chapter': chapter_num,
            'timestamp': datetime.now().isoformat(),
            'entities': copy.deepcopy(self.entities),
            'world_state': copy.deepcopy(self.world_state)
        }
        
        snapshot_file = self.snapshot_dir / f"chapter_{chapter_num:03d}.json"
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
        
        print(f"  已保存实体状态快照：第 {chapter_num} 章")

    def load_snapshot(self, chapter_num: int) -> bool:
        """
        加载指定章节的快照
        
        Args:
            chapter_num: 章节号
            
        Returns:
            bool: 是否成功加载
        """
        snapshot_file = self.snapshot_dir / f"chapter_{chapter_num:03d}.json"
        
        if not snapshot_file.exists():
            print(f"警告：找不到第 {chapter_num} 章的实体快照")
            return False
        
        try:
            with open(snapshot_file, 'r', encoding='utf-8') as f:
                snapshot_data = json.load(f)
            
            self.entities = snapshot_data.get('entities', {})
            self.world_state = snapshot_data.get('world_state', {})
            self.current_chapter = chapter_num
            self.last_updated = datetime.now().isoformat()
            
            print(f"  已加载第 {chapter_num} 章的实体状态快照")
            self.save_to_disk()
            return True
            
        except Exception as e:
            print(f"加载快照失败：{e}")
            return False

    def update_character(self, name: str, attributes: Dict[str, Any], chapter_num: int = None, save_snapshot: bool = True):
        """
        更新人物状态
        
        Args:
            name: 人物名称
            attributes: 属性字典
            chapter_num: 章节号（用于快照）
            save_snapshot: 是否保存快照
        """
        if 'characters' not in self.entities:
            self.entities['characters'] = {}

        if name not in self.entities['characters']:
            self.entities['characters'][name] = {}

        # 更新人物属性
        self.entities['characters'][name].update(attributes)
        self.entities['characters'][name]['last_updated'] = datetime.now().isoformat()
        
        # 记录章节号
        if chapter_num:
            self.entities['characters'][name]['last_chapter'] = chapter_num
            self.current_chapter = chapter_num

        # 保存快照（如果启用）
        if save_snapshot and chapter_num:
            self._save_snapshot(chapter_num)
        
        self.save_to_disk()

    def update_location(self, name: str, attributes: Dict[str, Any], chapter_num: int = None, save_snapshot: bool = True):
        """
        更新地点状态
        
        Args:
            name: 地点名称
            attributes: 属性字典
            chapter_num: 章节号（用于快照）
            save_snapshot: 是否保存快照
        """
        if 'locations' not in self.entities:
            self.entities['locations'] = {}

        if name not in self.entities['locations']:
            self.entities['locations'][name] = {}

        # 更新地点属性
        self.entities['locations'][name].update(attributes)
        self.entities['locations'][name]['last_updated'] = datetime.now().isoformat()
        
        # 记录章节号
        if chapter_num:
            self.entities['locations'][name]['last_chapter'] = chapter_num
            self.current_chapter = chapter_num

        # 保存快照（如果启用）
        if save_snapshot and chapter_num:
            self._save_snapshot(chapter_num)
        
        self.save_to_disk()

    def update_world_rule(self, name: str, description: str, chapter_num: int = None, save_snapshot: bool = True):
        """
        更新世界观/规则
        
        Args:
            name: 规则名称
            description: 规则描述
            chapter_num: 章节号（用于快照）
            save_snapshot: 是否保存快照
        """
        self.world_state[name] = {
            'description': description,
            'last_updated': datetime.now().isoformat()
        }
        
        # 记录章节号
        if chapter_num:
            self.world_state[name]['last_chapter'] = chapter_num
            self.current_chapter = chapter_num

        # 保存快照（如果启用）
        if save_snapshot and chapter_num:
            self._save_snapshot(chapter_num)
        
        self.save_to_disk()
    
    def get_character(self, name: str) -> Optional[Dict[str, Any]]:
        """获取人物状态"""
        if 'characters' in self.entities:
            return self.entities['characters'].get(name)
        return None
    
    def get_location(self, name: str) -> Optional[Dict[str, Any]]:
        """获取地点状态"""
        if 'locations' in self.entities:
            return self.entities['locations'].get(name)
        return None
    
    def get_world_state(self) -> Dict[str, Any]:
        """获取世界观状态"""
        return self.world_state
    
    def get_active_entities(self, context_keywords: List[str]) -> Dict[str, Any]:
        """根据上下文关键词获取活跃实体"""
        active_entities = {
            'characters': {},
            'locations': {},
            'world_state': {}
        }
        
        # 查找匹配的人物
        if 'characters' in self.entities:
            for char_name, char_data in self.entities['characters'].items():
                for keyword in context_keywords:
                    if keyword.lower() in char_name.lower():
                        active_entities['characters'][char_name] = char_data
                        break
        
        # 查找匹配的地点
        if 'locations' in self.entities:
            for loc_name, loc_data in self.entities['locations'].items():
                for keyword in context_keywords:
                    if keyword.lower() in loc_name.lower():
                        active_entities['locations'][loc_name] = loc_data
                        break
        
        # 返回所有世界观信息
        active_entities['world_state'] = self.world_state
        
        return active_entities
    
    def load_from_disk(self):
        """从磁盘加载实体状态"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.entities = data.get('entities', {})
                    self.world_state = data.get('world_state', {})
                    self.last_updated = data.get('last_updated')
            except Exception as e:
                print(f"加载实体状态失败: {e}")
                self.entities = {}
                self.world_state = {}
        else:
            self.entities = {}
            self.world_state = {}
    
    def save_to_disk(self):
        """保存实体状态到磁盘"""
        try:
            data = {
                'entities': self.entities,
                'world_state': self.world_state,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存实体状态失败: {e}")
    
    def clear(self):
        """清空实体状态"""
        self.entities = {}
        self.world_state = {}
        self.save_to_disk()
    
    def to_text_description(self, max_count: int = None) -> str:
        """
        将实体状态转换为文本描述，用于提示词

        Args:
            max_count: 最大实体数量限制，超出时只保留最近更新的实体
        """
        text_parts = ["[世界观与实体当前状态]:"]

        # 添加人物信息
        if 'characters' in self.entities and self.entities['characters']:
            characters = self.entities['characters']
            if max_count and len(characters) > max_count:
                # 按最后更新时间排序，保留最近的
                sorted_chars = sorted(
                    characters.items(),
                    key=lambda x: x[1].get('last_updated', ''),
                    reverse=True
                )[:max_count]
                characters = dict(sorted_chars)

            text_parts.append("\n人物档案:")
            for name, attrs in characters.items():
                text_parts.append(f"- {name}: {attrs}")

        # 添加地点信息
        if 'locations' in self.entities and self.entities['locations']:
            locations = self.entities['locations']
            if max_count and len(locations) > max_count:
                sorted_locs = sorted(
                    locations.items(),
                    key=lambda x: x[1].get('last_updated', ''),
                    reverse=True
                )[:max_count]
                locations = dict(sorted_locs)

            text_parts.append("\n地点设定:")
            for name, attrs in locations.items():
                text_parts.append(f"- {name}: {attrs}")

        # 添加世界观信息
        if self.world_state:
            text_parts.append("\n世界观/规则:")
            for name, attrs in self.world_state.items():
                desc = attrs.get('description', str(attrs))
                text_parts.append(f"- {name}: {desc}")

        return "\n".join(text_parts)


# ----------------------------------------------------------------------------
# v2.x 适配器 - 把旧 EntityStateTracker 的 dict 结构桥接到 tick 架构 TypedDict
# ----------------------------------------------------------------------------


class EntityStateAdapter:
    """把 ``EntityStateTracker`` 的 untyped dict 转为 tick 架构 Pydantic 模型。

    用于过渡期:旧 NovelGenerator 仍写 entity_state.json,新 Orchestrator 想读
    时通过此 Adapter 转为 ``WorldState`` / ``CharacterState`` 列表。
    """

    def __init__(self, tracker):
        self._tracker = tracker

    def to_world_state(self):
        """从 self._tracker.world_state 构造 WorldState(world_rules 列表)。"""
        from memory_system.models import Faction, TickLocation, WorldState

        rules = []
        for name, attrs in (self._tracker.world_state or {}).items():
            desc = attrs.get("description") if isinstance(attrs, dict) else str(attrs)
            if desc:
                rules.append(f"{name}: {desc}")

        locs_dict = self._tracker.entities.get("locations", {}) if self._tracker.entities else {}
        locations = []
        for name, attrs in locs_dict.items():
            attrs_d = attrs if isinstance(attrs, dict) else {}
            locations.append(
                TickLocation(
                    id=str(name),
                    name=str(name),
                    type=str(attrs_d.get("type", "region")),
                    current_state=str(attrs_d.get("description", "")),
                    notable_features=list(attrs_d.get("features", []) or []),
                )
            )

        return WorldState(
            world_time=0,
            era="",
            current_season="",
            weather="",
            locations=locations,
            factions=[],
            active_global_events=[],
            world_rules=rules[:10],
        )

    def to_character_states(self):
        """从 self._tracker.entities['characters'] 构造 CharacterState 列表。"""
        from memory_system.models import CharacterState

        chars_dict = self._tracker.entities.get("characters", {}) if self._tracker.entities else {}
        out = []
        for name, attrs in chars_dict.items():
            attrs_d = attrs if isinstance(attrs, dict) else {}
            facts = []
            for key in ("history", "background", "notes"):
                v = attrs_d.get(key)
                if v:
                    facts.append(f"{key}: {v}" if isinstance(v, str) else f"{key}: {v}")
            out.append(
                CharacterState(
                    character_id=str(name),
                    current_location=str(attrs_d.get("location", "")),
                    arc_goal=str(attrs_d.get("goal", attrs_d.get("arc_goal", ""))),
                    known_facts=facts[:10],
                    emotional_state=str(attrs_d.get("emotion", "neutral")),
                    inventory=list(attrs_d.get("inventory", []) or []),
                )
            )
        return out