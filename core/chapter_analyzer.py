"""
章节分析器
在章节生成完成后，调用 LLM 分析章节内容，提取：
1. 出场人物及其状态
2. 角色关系变化
3. 关键事件
4. 章节摘要
"""

import json
from typing import Dict, Any, Optional

from .llm_client import LLMClient


# 分析用的系统提示词
ANALYSIS_SYSTEM_PROMPT = """你是一个专业的小说分析助手。你需要仔细阅读给定的小说章节内容，提取结构化信息。
请严格按照 JSON 格式输出分析结果，不要输出任何其他内容。"""

ANALYSIS_PROMPT_TEMPLATE = """请分析以下小说章节内容，提取关键信息。

## 章节信息
- 章节号：第{chapter_num}章
- 章节标题：{chapter_title}

## 章节内容
{chapter_content}

## 要求
请严格按照以下 JSON 格式输出分析结果：

```json
{{
  "characters": [
    {{
      "name": "角色名",
      "role": "主角/配角/反派/路人",
      "description": "简短描述该角色在本章中的表现和状态（50字以内）",
      "location": "角色在本章中所处的地点（如有）",
      "status_changes": "角色状态的重要变化（如受伤、获得能力等，无变化则为空字符串）"
    }}
  ],
  "relationships": [
    {{
      "char1": "角色1名",
      "char2": "角色2名",
      "relationship_type": "关系类型（如：师徒、恋人、仇敌、朋友、父子、同伴、对手等）",
      "emotion_changes": {{
        "trust": 0.0,
        "affection": 0.0,
        "loyalty": 0.0,
        "conflict": 0.0
      }},
      "event": "导致关系变化的事件描述（30字以内）"
    }}
  ],
  "locations": [
    {{
      "name": "地点名",
      "description": "地点描述（30字以内）"
    }}
  ],
  "key_events": [
    {{
      "title": "事件标题（10字以内）",
      "description": "事件描述（50字以内）",
      "involved_characters": ["相关角色名"]
    }}
  ],
  "chapter_summary": "本章内容摘要（100-200字，概述主要情节发展）",
  "story_arc": "本章所属的故事弧线名称（如：修炼篇、夺宝之战等，10字以内）",
  "story_arc_summary": "故事弧线进展描述（50字以内）"
}}
```

注意事项：
- emotion_changes 中的值表示情感变化量（-1.0 到 1.0），正数表示增加，负数表示减少
- 只提取本章中实际出现的角色，不要编造
- relationships 只列出本章中有互动的角色对
- 如果某个字段没有相关内容，返回空数组 [] 或空字符串 ""
"""


class ChapterAnalyzer:
    """
    使用 LLM 分析章节内容，提取结构化记忆信息
    """

    def __init__(self, llm_client: LLMClient):
        """
        Args:
            llm_client: LLM 客户端实例
        """
        self.llm_client = llm_client

    def analyze(
        self,
        chapter_num: int,
        chapter_title: str,
        chapter_content: str
    ) -> Optional[Dict[str, Any]]:
        """
        分析章节内容，返回结构化信息

        Args:
            chapter_num: 章节号
            chapter_title: 章节标题
            chapter_content: 章节内容

        Returns:
            解析后的分析结果字典，失败返回 None
        """
        # 如果内容过长，截取关键部分避免超出 token 限制
        content_for_analysis = self._truncate_content(chapter_content, max_chars=6000)

        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            chapter_num=chapter_num,
            chapter_title=chapter_title,
            chapter_content=content_for_analysis
        )

        print(f"正在使用 LLM 分析第 {chapter_num} 章内容...")

        try:
            result = self.llm_client.generate_json(
                prompt=prompt,
                system_prompt=ANALYSIS_SYSTEM_PROMPT,
                max_tokens=2048
            )

            if result:
                # 验证返回的 JSON 结构
                validated = self._validate_result(result)
                if validated:
                    print(f"✓ 第 {chapter_num} 章分析完成："
                          f"{len(validated.get('characters', []))} 个角色, "
                          f"{len(validated.get('relationships', []))} 组关系, "
                          f"{len(validated.get('key_events', []))} 个事件")
                    return validated

            print(f"✗ 第 {chapter_num} 章分析失败：LLM 返回为空")
            return None

        except Exception as e:
            print(f"✗ 第 {chapter_num} 章分析出错：{e}")
            return None

    def _truncate_content(self, content: str, max_chars: int = 6000) -> str:
        """截取内容，保留首尾部分"""
        if len(content) <= max_chars:
            return content

        # 保留开头和结尾
        head_size = max_chars * 2 // 3
        tail_size = max_chars - head_size
        return (
            content[:head_size]
            + "\n\n... [中间部分省略] ...\n\n"
            + content[-tail_size:]
        )

    def _validate_result(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """验证分析结果的结构完整性"""
        # 确保关键字段存在且类型正确
        validated = {
            'characters': [],
            'relationships': [],
            'locations': [],
            'key_events': [],
            'chapter_summary': '',
            'story_arc': '',
            'story_arc_summary': ''
        }

        # 角色
        for char in result.get('characters', []):
            if isinstance(char, dict) and char.get('name'):
                validated['characters'].append({
                    'name': str(char['name']).strip(),
                    'role': str(char.get('role', '未知')).strip(),
                    'description': str(char.get('description', '')).strip(),
                    'location': str(char.get('location', '')).strip(),
                    'status_changes': str(char.get('status_changes', '')).strip()
                })

        # 关系
        for rel in result.get('relationships', []):
            if isinstance(rel, dict) and rel.get('char1') and rel.get('char2'):
                emotions = rel.get('emotion_changes', {})
                if not isinstance(emotions, dict):
                    emotions = {}
                validated['relationships'].append({
                    'char1': str(rel['char1']).strip(),
                    'char2': str(rel['char2']).strip(),
                    'relationship_type': str(rel.get('relationship_type', '未知')).strip(),
                    'emotion_changes': {
                        'trust': float(emotions.get('trust', 0)),
                        'affection': float(emotions.get('affection', 0)),
                        'loyalty': float(emotions.get('loyalty', 0)),
                        'conflict': float(emotions.get('conflict', 0))
                    },
                    'event': str(rel.get('event', '')).strip()
                })

        # 地点
        for loc in result.get('locations', []):
            if isinstance(loc, dict) and loc.get('name'):
                validated['locations'].append({
                    'name': str(loc['name']).strip(),
                    'description': str(loc.get('description', '')).strip()
                })

        # 关键事件
        for evt in result.get('key_events', []):
            if isinstance(evt, dict) and evt.get('title'):
                involved = evt.get('involved_characters', [])
                if not isinstance(involved, list):
                    involved = []
                validated['key_events'].append({
                    'title': str(evt['title']).strip(),
                    'description': str(evt.get('description', '')).strip(),
                    'involved_characters': [str(c).strip() for c in involved]
                })

        # 摘要
        validated['chapter_summary'] = str(result.get('chapter_summary', '')).strip()
        validated['story_arc'] = str(result.get('story_arc', '')).strip()
        validated['story_arc_summary'] = str(result.get('story_arc_summary', '')).strip()

        return validated


def apply_analysis_to_memory(
    analysis: Dict[str, Any],
    chapter_num: int,
    chapter_title: str,
    chapter_content: str,
    entity_state,
    character_relationship,
    long_term_memory,
    hierarchical_summary
):
    """
    将 LLM 分析结果应用到各记忆模块

    Args:
        analysis: LLM 分析结果
        chapter_num: 章节号
        chapter_title: 章节标题
        chapter_content: 章节内容（用于长期记忆存储）
        entity_state: EntityStateTracker 实例
        character_relationship: CharacterRelationshipGraph 实例
        long_term_memory: LongTermEventMemory 实例
        hierarchical_summary: HierarchicalSummarizer 实例
    """
    print(f"正在将分析结果写入记忆系统...")

    # 1. 更新实体状态（角色）
    for char in analysis.get('characters', []):
        attrs = {
            'role': char.get('role', ''),
            'description': char.get('description', ''),
        }
        if char.get('location'):
            attrs['current_location'] = char['location']
        if char.get('status_changes'):
            attrs['status'] = char['status_changes']

        entity_state.update_character(
            name=char['name'],
            attributes=attrs,
            chapter_num=chapter_num,
            save_snapshot=False
        )

    # 保存一次快照（避免每个角色都保存）
    if analysis.get('characters'):
        entity_state._save_snapshot(chapter_num)

    # 2. 更新地点
    for loc in analysis.get('locations', []):
        entity_state.update_location(
            name=loc['name'],
            attributes={'description': loc.get('description', '')},
            chapter_num=chapter_num,
            save_snapshot=False
        )

    # 3. 更新角色关系
    for rel in analysis.get('relationships', []):
        existing = character_relationship.get_relationship(rel['char1'], rel['char2'])

        if existing:
            # 已有关系 → 更新情感值
            emotion_changes = rel.get('emotion_changes', {})
            non_zero_changes = {k: v for k, v in emotion_changes.items() if v != 0}
            if non_zero_changes:
                character_relationship.update_emotion(
                    char1=rel['char1'],
                    char2=rel['char2'],
                    emotion_changes=non_zero_changes,
                    chapter_num=chapter_num,
                    event=rel.get('event', '')
                )
        else:
            # 新关系 → 添加
            base_emotions = {
                'trust': 0.5,
                'affection': 0.5,
                'loyalty': 0.5,
                'conflict': 0.0
            }
            # 将变化量加到基础值上作为初始值
            emotion_changes = rel.get('emotion_changes', {})
            init_emotions = {
                k: max(0.0, min(1.0, base_emotions[k] + emotion_changes.get(k, 0)))
                for k in base_emotions
            }
            character_relationship.add_relationship(
                char1=rel['char1'],
                char2=rel['char2'],
                relationship_type=rel.get('relationship_type', '未知'),
                emotions=init_emotions,
                chapter_num=chapter_num,
                event=rel.get('event', '')
            )

    # 4. 添加关键事件到长期记忆
    involved_entities = set()
    for evt in analysis.get('key_events', []):
        involved_entities.update(evt.get('involved_characters', []))

    # 角色名也加入实体列表
    for char in analysis.get('characters', []):
        involved_entities.add(char['name'])

    long_term_memory.add_event(
        chapter_num=chapter_num,
        title=chapter_title,
        content=chapter_content,
        entities=list(involved_entities)
    )

    # 5. 更新层级摘要
    chapter_summary = analysis.get('chapter_summary', '')
    if chapter_summary:
        hierarchical_summary.add_low_level_summary(
            chapter_num=chapter_num,
            title=chapter_title,
            summary=chapter_summary
        )

    # 6. 更新故事弧线
    story_arc = analysis.get('story_arc', '')
    story_arc_summary = analysis.get('story_arc_summary', '')
    if story_arc and story_arc_summary:
        # 检查是否已有同名弧线，避免重复添加
        existing_arcs = [a['title'] for a in hierarchical_summary.mid_level_arcs]
        if story_arc not in existing_arcs:
            hierarchical_summary.add_mid_level_arc(story_arc, story_arc_summary)
        else:
            # 更新现有弧线的摘要
            for arc in hierarchical_summary.mid_level_arcs:
                if arc['title'] == story_arc:
                    arc['summary'] = story_arc_summary
                    break
            hierarchical_summary.save_to_disk()

    print(f"✓ 记忆系统更新完成："
          f"{len(analysis.get('characters', []))} 角色, "
          f"{len(analysis.get('relationships', []))} 关系, "
          f"{len(analysis.get('key_events', []))} 事件")
