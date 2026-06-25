"""Vector Store — ChromaDB-backed RAG for long-term detail retrieval.

iter#AA — module-level chromadb/posthog import 改 lazy. chromadb 在
opentelemetry-proto 1.40 (需要 protobuf ≥ 4) 上有 transitive 导入失败,
当前 env 是 protobuf 3.10. 13 个 backend 测试因此 collection error,
其实只 import 本模块不实例化 VectorStore 不应触发 chromadb chain.
"""

from __future__ import annotations

import logging
import os

# Suppress broken posthog telemetry in chromadb 0.5.x — set env at module load
# so any indirect import of posthog sees ANONYMIZED_TELEMETRY=False.
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from config.settings import settings
from memory_system.models import Section

logger = logging.getLogger(__name__)


def _patch_posthog() -> None:
    """iter#AA — lazy posthog patch, only when VectorStore instantiated."""
    try:
        import posthog
        posthog.capture = lambda *args, **kwargs: None
        posthog.Posthog.capture = lambda *args, **kwargs: None
    except ImportError:
        pass


class VectorStore:
    """Manages embedding storage and semantic retrieval of historical sections."""

    def __init__(self, persist_dir: str | None = None) -> None:
        # iter#AA — chromadb 在 __init__ 内 import, 让 module load 不挂 protobuf
        # 失败. 测试 import VectorStore 类但不实例化时安全.
        _patch_posthog()
        import chromadb  # noqa: WPS433 (intentional lazy)
        persist_dir = os.path.abspath(persist_dir or settings.chroma_persist_dir)
        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name="novel_sections",
            metadata={"hnsw:space": "cosine"},
        )

    async def add_section(self, section: Section) -> None:
        doc_id = f"ch{section.chapter}_s{section.section}"
        try:
            self._collection.upsert(
                ids=[doc_id],
                documents=[section.content],
                metadatas=[
                    {
                        "chapter": section.chapter,
                        "section": section.section,
                        "title": section.title,
                        "summary": section.summary or "",
                    }
                ],
            )
        except Exception as e:
            logger.error("VectorStore add_section failed: %s", e)

    async def query(self, text: str, top_k: int | None = None) -> list[dict]:
        k = top_k or settings.embedding_top_k
        if self._collection.count() == 0:
            return []
        try:
            results = self._collection.query(
                query_texts=[text],
                n_results=min(k, self._collection.count()),
            )
        except Exception as e:
            logger.error("VectorStore query failed: %s", e)
            return []
        docs: list[dict] = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = (
                    results["metadatas"][0][i] if results["metadatas"] else {}
                )
                distance = (
                    results["distances"][0][i]
                    if results.get("distances")
                    else None
                )
                docs.append(
                    {"content": doc, "metadata": meta, "distance": distance}
                )
        return docs

    @property
    def count(self) -> int:
        try:
            return self._collection.count()
        except Exception:
            return 0

    def clear(self) -> None:
        self._client.delete_collection("novel_sections")
        self._collection = self._client.get_or_create_collection(
            name="novel_sections",
            metadata={"hnsw:space": "cosine"},
        )
