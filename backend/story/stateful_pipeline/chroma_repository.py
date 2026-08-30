"""ChromaDB memory adapter for the stateful pipeline.

Wraps ChromaDB with:
  - Idempotent document IDs (deterministic, no uuid4)
  - Per-novel isolation via collection naming or metadata filter
  - Upsert semantics (retry-safe)
  - Rebuild capability from source data
"""

from __future__ import annotations

import logging
import os
from typing import Any

os.environ["ANONYMIZED_TELEMETRY"] = "False"

logger = logging.getLogger(__name__)


def _patch_posthog() -> None:
    try:
        import posthog
        posthog.capture = lambda *args, **kwargs: None
        posthog.Posthog.capture = lambda *args, **kwargs: None
    except ImportError:
        pass


def generate_document_id(
    novel_id: str,
    chapter: int,
    schema_revision: int,
    field_key: str,
    item_index: int,
) -> str:
    """Generate a deterministic document ID for ChromaDB.

    Format: {novel_id}:{chapter}:{schema_revision}:{field}:{index}
    Ensures retry produces the same ID (idempotent upsert).
    """
    return f"{novel_id}:{chapter}:{schema_revision}:{field_key}:{item_index}"


class ChromaMemoryRepository:
    """ChromaDB-backed memory store with idempotent operations.

    ChromaDB is a derived/retrieval store. It must never be the
    source of truth for canonical state. All data should be
    rebuildable from the committed chapter information.
    """

    COLLECTION_NAME = "pipeline_memory"

    def __init__(self, persist_dir: str | None = None) -> None:
        _patch_posthog()
        import chromadb

        from config.settings import settings

        persist_dir = os.path.abspath(persist_dir or settings.chroma_persist_dir)
        os.makedirs(persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    async def upsert_documents(
        self,
        novel_id: str,
        chapter: int,
        schema_revision: int,
        documents: list[dict[str, Any]],
    ) -> list[str]:
        """Upsert memory documents for a chapter.

        Each document dict should have:
          - content: str (the memory text)
          - field: str (source field key)
          - entities: list[str] (optional)

        Returns list of document IDs written.
        """
        if not documents:
            return []

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for idx, doc in enumerate(documents):
            content = doc.get("content", "")
            field_key = doc.get("field", "unknown")

            doc_id = generate_document_id(
                novel_id, chapter, schema_revision, field_key, idx
            )
            ids.append(doc_id)
            texts.append(content)
            metadatas.append({
                "novel_id": novel_id,
                "chapter": chapter,
                "schema_revision": schema_revision,
                "field": field_key,
                "entities": ",".join(doc.get("entities", [])),
            })

        try:
            self._collection.upsert(
                ids=ids,
                documents=texts,
                metadatas=metadatas,
            )
        except Exception as e:
            logger.error("ChromaMemoryRepository upsert failed: %s", e)
            raise

        return ids

    async def query(
        self,
        novel_id: str,
        query_text: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Query memories for a novel.

        Strictly filters by novel_id to prevent cross-novel retrieval.
        """
        if self._collection.count() == 0:
            return []

        try:
            results = self._collection.query(
                query_texts=[query_text],
                n_results=min(top_k, self._collection.count()),
                where={"novel_id": novel_id},
            )
        except Exception as e:
            logger.error("ChromaMemoryRepository query failed: %s", e)
            return []

        documents: list[dict[str, Any]] = []
        if results and results.get("documents"):
            # ChromaDB returns nested lists: [[doc1, doc2, ...]] for one query
            doc_list = results["documents"][0] if results["documents"] else []
            metadata_list = results["metadatas"][0] if results.get("metadatas") else []
            distance_list = results["distances"][0] if results.get("distances") else []

            for i, doc in enumerate(doc_list):
                metadata = metadata_list[i] if i < len(metadata_list) else {}
                distance = distance_list[i] if i < len(distance_list) else 1.0
                documents.append({
                    "content": doc,
                    "metadata": metadata,
                    "distance": distance,
                })

        return documents

    async def query_recent_chapters(
        self,
        novel_id: str,
        chapters: list[int],
        limit_per_chapter: int = 5,
    ) -> dict[int, list[dict[str, Any]]]:
        """Retrieve memories for specific chapters."""
        results: dict[int, list[dict[str, Any]]] = {ch: [] for ch in chapters}

        for chapter in chapters:
            try:
                # Query with empty text but filter by chapter
                all_docs = self._collection.get(
                    where={"novel_id": novel_id},
                    limit=100,
                )
                if all_docs and all_docs.get("documents"):
                    for i, doc in enumerate(all_docs["documents"]):
                        metadata = all_docs["metadatas"][i] if all_docs.get("metadatas") else {}
                        if metadata.get("chapter") == chapter:
                            results[chapter].append({
                                "id": all_docs["ids"][i],
                                "content": doc,
                                "metadata": metadata,
                            })
            except Exception as e:
                logger.error("ChromaMemoryRepository query_recent_chapters failed: %s", e)

        return results

    async def count(self, novel_id: str) -> int:
        """Count documents for a novel."""
        try:
            all_docs = self._collection.get(
                where={"novel_id": novel_id},
            )
            return len(all_docs["ids"]) if all_docs and all_docs.get("ids") else 0
        except Exception:
            return 0

    async def rebuild(
        self,
        novel_id: str,
        chapter_informations: list[dict[str, Any]],
        schema_revision: int,
    ) -> int:
        """Rebuild ChromaDB from committed chapter information.

        This ensures vector data can be recovered from source data.
        ChromaDB corruption should never cause data loss.

        Returns number of documents written.
        """
        total_written = 0

        for chapter_info in chapter_informations:
            chapter = chapter_info["chapter_number"]
            data = chapter_info.get("data", {})

            documents = []
            for field_key, items in data.items():
                if isinstance(items, list):
                    for idx, item in enumerate(items):
                        content = self._format_item_as_memory(item, field_key)
                        if content:
                            documents.append({
                                "content": content,
                                "field": field_key,
                                "entities": self._extract_entities(item),
                            })

            if documents:
                await self.upsert_documents(
                    novel_id=novel_id,
                    chapter=chapter,
                    schema_revision=schema_revision,
                    documents=documents,
                )
                total_written += len(documents)

        return total_written

    def _format_item_as_memory(self, item: Any, field_key: str) -> str:
        """Convert a structured item to natural language memory."""
        if isinstance(item, dict):
            # Try common patterns
            if "name" in item:
                parts = [f"{item['name']}"]
                if "description" in item:
                    parts.append(item["description"])
                if "status" in item:
                    parts.append(f"状态：{item['status']}")
                return "；".join(parts)
            # Fallback: serialize
            return str(item)
        elif isinstance(item, str):
            return item
        return str(item)

    def _extract_entities(self, item: Any) -> list[str]:
        """Extract entity names from an item."""
        entities = []
        if isinstance(item, dict):
            for key in ("name", "character", "location", "entity"):
                if key in item and isinstance(item[key], str):
                    entities.append(item[key])
        return entities

    async def clear_novel(self, novel_id: str) -> int:
        """Remove all documents for a novel (for testing/rebuild)."""
        try:
            all_docs = self._collection.get(
                where={"novel_id": novel_id},
            )
            if all_docs and all_docs.get("ids"):
                self._collection.delete(ids=all_docs["ids"])
                return len(all_docs["ids"])
        except Exception as e:
            logger.error("ChromaMemoryRepository clear_novel failed: %s", e)
        return 0
