"""
向量嵌入服务
使用 Sentence Transformers 生成文本的向量表示
支持多种 Embedding 模型
"""

import numpy as np
from typing import List, Optional, Union
from pathlib import Path


class EmbeddingService:
    """
    向量嵌入服务
    使用 Sentence Transformers 生成文本向量
    """
    
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        """
        初始化嵌入服务
        
        Args:
            model_name: 模型名称
                - BAAI/bge-small-zh-v1.5: 中文小模型（推荐）
                - BAAI/bge-base-zh-v1.5: 中文中等模型
                - BAAI/bge-large-zh-v1.5: 中文大型模型
                - sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2: 多语言模型
        """
        self.model_name = model_name
        self.model = None
        self.cache_dir = Path.home() / ".cache" / "novel_auto" / "embeddings"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def load_model(self):
        """加载嵌入模型"""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                print(f"正在加载嵌入模型：{self.model_name}")
                self.model = SentenceTransformer(
                    self.model_name,
                    cache_folder=str(self.cache_dir)
                )
                print("嵌入模型加载完成")
            except ImportError:
                print("错误：请安装 sentence-transformers 库")
                print("运行：pip install sentence-transformers")
                raise
            except Exception as e:
                print(f"加载模型失败：{e}")
                raise
    
    def embed_text(self, text: str) -> np.ndarray:
        """
        生成单个文本的向量
        
        Args:
            text: 输入文本
            
        Returns:
            np.ndarray: 向量表示
        """
        if self.model is None:
            self.load_model()
        
        # 生成向量
        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True  # 归一化，便于余弦相似度计算
        )
        
        return embedding
    
    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        批量生成文本向量
        
        Args:
            texts: 文本列表
            
        Returns:
            np.ndarray: 向量矩阵 (n_texts, embedding_dim)
        """
        if self.model is None:
            self.load_model()
        
        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=len(texts) > 10
        )
        
        return embeddings
    
    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        计算两个向量的余弦相似度
        
        Args:
            vec1: 向量 1
            vec2: 向量 2
            
        Returns:
            float: 余弦相似度 (0-1 之间)
        """
        # 因为向量已经归一化，点积就是余弦相似度
        return float(np.dot(vec1, vec2))
    
    def find_similar(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5
    ) -> List[tuple]:
        """
        查找与查询最相似的文档
        
        Args:
            query: 查询文本
            documents: 文档列表
            top_k: 返回最相似的 K 个文档
            
        Returns:
            List[tuple]: [(文档索引，相似度分数，文档内容), ...]
        """
        if not documents:
            return []
        
        # 生成查询向量
        query_embedding = self.embed_text(query)
        
        # 生成所有文档的向量
        doc_embeddings = self.embed_texts(documents)
        
        # 计算相似度
        similarities = []
        for i, doc_emb in enumerate(doc_embeddings):
            sim = self.cosine_similarity(query_embedding, doc_emb)
            similarities.append((i, sim, documents[i]))
        
        # 按相似度排序
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # 返回 top_k
        return similarities[:top_k]


# 使用 DashScope API 的嵌入服务（备选方案）
class DashScopeEmbeddingService:
    """
    使用阿里云 DashScope API 的嵌入服务
    作为本地模型的备选方案
    """
    
    def __init__(self, api_key: str = None, model_name: str = "text-embedding-v2"):
        """
        初始化 DashScope 嵌入服务
        
        Args:
            api_key: API 密钥
            model_name: 模型名称
        """
        import os
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.model_name = model_name
        
        if not self.api_key:
            raise ValueError("请设置 DASHSCOPE_API_KEY 环境变量")
    
    def embed_text(self, text: str) -> list:
        """
        生成文本向量
        
        Args:
            text: 输入文本
            
        Returns:
            list: 向量表示
        """
        try:
            import dashscope
            from dashscope import TextEmbedding
            
            response = TextEmbedding.call(
                model=self.model_name,
                input=text,
                api_key=self.api_key
            )
            
            if response.status_code == 200:
                return response.output['embeddings'][0]['embedding']
            else:
                print(f"DashScope API 调用失败：{response.message}")
                return None
                
        except Exception as e:
            print(f"生成向量失败：{e}")
            return None


# 使用示例
if __name__ == "__main__":
    # 使用本地模型
    service = EmbeddingService()
    
    # 测试向量生成
    text = "这是一个测试句子"
    embedding = service.embed_text(text)
    print(f"向量维度：{embedding.shape}")
    print(f"向量前 5 个值：{embedding[:5]}")
    
    # 测试相似度查找
    query = "主角受伤"
    documents = [
        "他咳出一口鲜血，倒在地上",
        "阳光明媚，天气很好",
        "她受了重伤，生命垂危",
        "小鸟在树上唱歌"
    ]
    
    results = service.find_similar(query, documents, top_k=2)
    print(f"\n查询：{query}")
    print("最相似的文档:")
    for idx, score, doc in results:
        print(f"  相似度：{score:.4f} - {doc}")
