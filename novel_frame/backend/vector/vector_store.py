"""Vector Store — ChromaDB-backed RAG for long-term detail retrieval."""

from __future__ import annotations

import logging
import os

# Suppress broken posthog telemetry in chromadb 0.5.x
# The posthog 7.x capture() signature is incompatible with chromadb's usage.
os.environ["ANONYMIZED_TELEMETRY"] = "False"

import posthog  # noqa: E402

posthog.capture = lambda *args, **kwargs: None  # noqa: E402
posthog.Posthog.capture = lambda *args, **kwargs: None  # noqa: E402

import chromadb  # noqa: E402

from config.settings import settings  # noqa: E402
from core.models import Section  # noqa: E402

logger = logging.getLogger(__name__)


class VectorStore:
    """Manages embedding storage and semantic retrieval of historical sections."""

    def __init__(self, persist_dir: str | None = None) -> None:
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
