"""
长期记忆模块（基于向量检索的 RAG）
使用 ChromaDB 向量数据库存储和检索历史事件
支持语义检索，而非简单的字符串匹配
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class LongTermEventMemory:
    """
    基于向量检索的长期事件记忆
    使用 ChromaDB 存储事件，支持语义检索
    """

    def __init__(self, memory_dir: str = "memory_system"):
        """
        初始化长期记忆
        
        Args:
            memory_dir: 记忆存储目录
        """
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # 向量数据库文件路径
        self.db_path = self.memory_dir / "long_term_memory_db"
        
        # 事件缓存
        self.events: List[Dict] = []
        self._events_by_id: Dict[str, Dict] = {}  # O(1) 事件查找索引
        self.events_file = self.memory_dir / "long_term_events.json"
        
        # 向量检索服务
        self.embedding_service = None
        self.chroma_client = None
        self.collection = None
        
        # 初始化向量数据库
        self._init_vector_db()
        
        # 从磁盘加载事件
        self.load_from_disk()
    
    def _init_vector_db(self):
        """初始化 ChromaDB 向量数据库"""
        try:
            import chromadb
            from chromadb.config import Settings
            
            # 创建持久化客户端
            self.chroma_client = chromadb.PersistentClient(
                path=str(self.db_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # 获取或创建集合
            self.collection = self.chroma_client.get_or_create_collection(
                name="novel_events",
                metadata={"hnsw:space": "cosine"}  # 使用余弦相似度
            )
            
            print(f"向量数据库初始化完成：{self.db_path}")
            
        except ImportError:
            print("警告：ChromaDB 未安装，将使用简单的内存检索")
            print("安装：pip install chromadb")
            self.collection = None
    
    def _get_embedding_service(self):
        """获取向量嵌入服务（延迟加载）"""
        if self.embedding_service is None:
            from core.embedding_service import EmbeddingService
            self.embedding_service = EmbeddingService(
                model_name="BAAI/bge-small-zh-v1.5"
            )
        return self.embedding_service
    
    def _generate_event_id(self, chapter_num: int, title: str, content: str) -> str:
        """
        生成事件的唯一 ID
        
        Args:
            chapter_num: 章节号
            title: 事件标题
            content: 事件内容
            
        Returns:
            str: 唯一 ID
        """
        text = f"{chapter_num}_{title}_{content[:100]}"
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _extract_summary(self, content: str, max_length: int = 200) -> str:
        """
        从内容中提取摘要
        
        Args:
            content: 原始内容
            max_length: 最大长度
            
        Returns:
            str: 摘要
        """
        if len(content) <= max_length:
            return content
        
        # 在句子边界处截断
        truncated = content[:max_length]
        last_sentence_end = max(
            truncated.rfind('。'),
            truncated.rfind('！'),
            truncated.rfind('？'),
            truncated.rfind('.\n')
        )
        
        if last_sentence_end > max_length // 2:
            return truncated[:last_sentence_end + 1]
        return truncated + "..."
    
    def add_event(
        self,
        chapter_num: int,
        title: str,
        content: str,
        entities: List[str] = None
    ):
        """
        添加事件到长期记忆
        
        Args:
            chapter_num: 章节号
            title: 章节标题
            content: 章节内容
            entities: 相关实体列表
        """
        # 创建事件记录
        event = {
            "id": self._generate_event_id(chapter_num, title, content),
            "chapter_num": chapter_num,
            "title": title,
            "content": content,
            "summary": self._extract_summary(content),
            "entities": entities or [],
            "timestamp": datetime.now().isoformat()
        }
        
        # 添加到内存
        self.events.append(event)
        self._events_by_id[event['id']] = event
        
        # 添加到向量数据库
        if self.collection:
            try:
                embedding_service = self._get_embedding_service()
                
                # 生成向量（使用摘要 + 实体）
                text_for_embedding = f"{event['summary']} {' '.join(event['entities'])}"
                embedding = embedding_service.embed_text(text_for_embedding)
                
                # 添加到 ChromaDB
                self.collection.add(
                    ids=[event['id']],
                    embeddings=[embedding.tolist()],
                    metadatas=[{
                        "chapter_num": chapter_num,
                        "title": title,
                        "entities": ",".join(entities) if entities else ""
                    }],
                    documents=[text_for_embedding]
                )
                
            except Exception as e:
                print(f"添加到向量数据库失败：{e}")
        
        # 保存到磁盘
        self.save_to_disk()
    
    def get_context_by_entities(self, entities: List[str], top_k: int = 3) -> List[Dict]:
        """
        根据实体检索相关事件（使用向量检索）
        
        Args:
            entities: 实体列表
            top_k: 返回最相关的 K 个事件
            
        Returns:
            List[Dict]: 相关事件列表
        """
        if not entities:
            return []
        
        # 构建查询文本
        query_text = " ".join(entities)
        
        # 使用向量检索
        if self.collection and len(self.events) > 0:
            try:
                embedding_service = self._get_embedding_service()
                query_embedding = embedding_service.embed_text(query_text)
                
                # 在 ChromaDB 中检索
                results = self.collection.query(
                    query_embeddings=[query_embedding.tolist()],
                    n_results=top_k,
                    include=["metadatas", "documents"]
                )
                
                # 提取结果
                if results and results['ids'] and len(results['ids'][0]) > 0:
                    event_ids = results['ids'][0]
                    relevant_events = []

                    for event_id in event_ids:
                        event = self._events_by_id.get(event_id)
                        if event:
                            relevant_events.append(event)

                    return relevant_events

            except Exception as e:
                print(f"向量检索失败：{e}")

        # 降级到简单的关键词匹配
        return self._keyword_match(entities, top_k)
    
    def _keyword_match(self, entities: List[str], top_k: int = 3) -> List[Dict]:
        """
        降级方案：关键词匹配
        
        Args:
            entities: 实体列表
            top_k: 返回数量
            
        Returns:
            List[Dict]: 匹配的事件
        """
        scored_events = []
        
        for event in self.events:
            score = 0
            # 检查实体是否出现在内容中
            for entity in entities:
                if entity in event['content']:
                    score += 1
                if entity in event.get('entities', []):
                    score += 2
            
            if score > 0:
                scored_events.append((score, event))
        
        # 按分数排序
        scored_events.sort(key=lambda x: x[0], reverse=True)
        
        return [event for score, event in scored_events[:top_k]]
    
    def search_by_query(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        通过自然语言查询检索事件
        
        Args:
            query: 查询文本（如"主角受重伤的情节"）
            top_k: 返回数量
            
        Returns:
            List[Dict]: 相关事件列表
        """
        if not self.events:
            return []
        
        # 使用向量检索
        if self.collection:
            try:
                embedding_service = self._get_embedding_service()
                query_embedding = embedding_service.embed_text(query)
                
                results = self.collection.query(
                    query_embeddings=[query_embedding.tolist()],
                    n_results=top_k,
                    include=["metadatas", "documents"]
                )
                
                if results and results['ids'] and len(results['ids'][0]) > 0:
                    event_ids = results['ids'][0]
                    relevant_events = []

                    for event_id in event_ids:
                        event = self._events_by_id.get(event_id)
                        if event:
                            relevant_events.append(event)

                    return relevant_events

            except Exception as e:
                print(f"查询失败：{e}")
        
        # 降级到关键词匹配
        keywords = query.split()
        return self._keyword_match(keywords, top_k)
    
    def get_all_events(self) -> List[Dict]:
        """获取所有事件"""
        return self.events
    
    def get_events_by_chapter(self, chapter_num: int) -> List[Dict]:
        """
        获取指定章节的事件
        
        Args:
            chapter_num: 章节号
            
        Returns:
            List[Dict]: 事件列表
        """
        return [e for e in self.events if e['chapter_num'] == chapter_num]
    
    def clear(self):
        """清空所有事件"""
        self.events = []
        self._events_by_id = {}
        
        if self.collection:
            try:
                self.chroma_client.delete_collection("novel_events")
                self.collection = self.chroma_client.get_or_create_collection(
                    name="novel_events",
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception as e:
                print(f"清空向量数据库失败：{e}")
        
        self.save_to_disk()
    
    def save_to_disk(self):
        """保存到磁盘"""
        try:
            with open(self.events_file, 'w', encoding='utf-8') as f:
                json.dump(self.events, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存事件失败：{e}")
    
    def load_from_disk(self):
        """从磁盘加载"""
        if os.path.exists(self.events_file):
            try:
                with open(self.events_file, 'r', encoding='utf-8') as f:
                    self.events = json.load(f)

                # 重建 O(1) 查找索引
                self._events_by_id = {e['id']: e for e in self.events}

                # 重新构建向量数据库索引
                if self.collection and self.events:
                    self._rebuild_index()

            except Exception as e:
                print(f"加载事件失败：{e}")
                self.events = []
                self._events_by_id = {}
    
    def _rebuild_index(self):
        """重建向量数据库索引"""
        try:
            embedding_service = self._get_embedding_service()
            
            # 批量生成向量
            texts = []
            ids = []
            metadatas = []
            
            for event in self.events:
                text = f"{event['summary']} {' '.join(event.get('entities', []))}"
                texts.append(text)
                ids.append(event['id'])
                metadatas.append({
                    "chapter_num": event['chapter_num'],
                    "title": event['title'],
                    "entities": ",".join(event.get('entities', []))
                })
            
            # 生成向量
            embeddings = embedding_service.embed_texts(texts)
            
            # 使用 upsert 避免重复 ID 错误
            self.collection.upsert(
                ids=ids,
                embeddings=[emb.tolist() for emb in embeddings],
                metadatas=metadatas,
                documents=texts
            )
            
            print(f"重建向量索引完成，共 {len(self.events)} 个事件")
            
        except Exception as e:
            print(f"重建索引失败：{e}")
    
    def to_context_format(self, events: List[Dict]) -> str:
        """
        将事件列表转换为上下文格式
        
        Args:
            events: 事件列表
            
        Returns:
            str: 格式化的上下文字符串
        """
        if not events:
            return "[无相关历史事件]"
        
        context_parts = ["[相关历史事件]:"]
        
        for event in events:
            context_parts.append(
                f"- 第{event['chapter_num']}章 ({event['title']}): "
                f"{event['summary']}"
            )
        
        return "\n".join(context_parts)
