#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for EmbeddingService
Tests for vector embedding generation and similarity search
"""

import pytest
import numpy as np
from unittest.mock import Mock


class TestEmbeddingService:
    """Tests for the EmbeddingService class"""

    def test_embed_text_returns_numpy_array(self):
        """Test that embed_text returns a numpy array"""
        from core.embedding_service import EmbeddingService

        # Mock the model
        mock_model = Mock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3, 0.4])

        service = EmbeddingService()
        service.model = mock_model

        result = service.embed_text("测试文本")

        assert isinstance(result, np.ndarray)
        assert len(result) == 4

    def test_embed_texts_batch_processing(self):
        """Test that embed_texts processes multiple texts correctly"""
        from core.embedding_service import EmbeddingService

        mock_model = Mock()
        mock_model.encode.return_value = np.array([
            [0.1, 0.2],
            [0.3, 0.4],
            [0.5, 0.6]
        ])

        service = EmbeddingService()
        service.model = mock_model

        texts = ["文本1", "文本2", "文本3"]
        result = service.embed_texts(texts)

        assert isinstance(result, np.ndarray)
        assert result.shape[0] == 3

    def test_cosine_similarity_normalized_vectors(self):
        """Test cosine similarity calculation"""
        from core.embedding_service import EmbeddingService

        service = EmbeddingService()

        # Test with identical normalized vectors
        vec1 = np.array([0.5, 0.5, 0.5, 0.5])
        vec2 = np.array([0.5, 0.5, 0.5, 0.5])

        similarity = service.cosine_similarity(vec1, vec2)

        assert 0.99 < similarity <= 1.0

    def test_cosine_similarity_different_vectors(self):
        """Test cosine similarity with different vectors"""
        from core.embedding_service import EmbeddingService

        service = EmbeddingService()

        vec1 = np.array([1.0, 0.0])
        vec2 = np.array([0.0, 1.0])

        similarity = service.cosine_similarity(vec1, vec2)

        assert 0.0 <= similarity < 0.1

    def test_find_similar_returns_top_k(self):
        """Test that find_similar returns correct number of results"""
        from core.embedding_service import EmbeddingService

        mock_model = Mock()

        def mock_encode(texts, **kwargs):
            if isinstance(texts, str):
                return np.array([0.1, 0.2, 0.3])
            else:
                return np.array([
                    [0.5, 0.5, 0.5],
                    [0.9, 0.1, 0.1],
                    [0.1, 0.9, 0.1],
                    [0.1, 0.1, 0.9]
                ])

        mock_model.encode = mock_encode

        service = EmbeddingService()
        service.model = mock_model

        query = "测试查询"
        documents = ["文档1", "文档2", "文档3", "文档4"]

        results = service.find_similar(query, documents, top_k=2)

        assert len(results) == 2
        assert all(isinstance(r, tuple) and len(r) == 3 for r in results)

    def test_find_similar_empty_documents(self):
        """Test find_similar with empty document list"""
        from core.embedding_service import EmbeddingService

        service = EmbeddingService()
        results = service.find_similar("查询", [], top_k=5)

        assert results == []

    def test_fallback_to_keyword_matching(self):
        """Test fallback keyword matching in LongTermEventMemory"""
        from memory_system.long_term_memory import LongTermEventMemory

        memory = LongTermEventMemory.__new__(LongTermEventMemory)
        memory.events = [
            {"id": "1", "content": "李明在图书馆", "entities": ["李明"]}
        ]
        memory._events_by_id = {"1": memory.events[0]}

        result = memory._keyword_match(["李明"], top_k=1)

        assert len(result) == 1
        assert "李明" in result[0]["content"]


class TestEmbeddingServiceErrorHandling:
    """Tests for error handling in EmbeddingService"""

    def test_embedding_generation_error(self):
        """Test handling of embedding generation errors"""
        from core.embedding_service import EmbeddingService

        mock_model = Mock()
        mock_model.encode.side_effect = Exception("Encoding failed")

        service = EmbeddingService()
        service.model = mock_model

        with pytest.raises(Exception):
            service.embed_text("测试")


class TestEmbeddingServiceIntegration:
    """Integration tests for EmbeddingService with real models"""

    @pytest.mark.skip(reason="Requires model download - run manually")
    def test_real_embedding_generation(self):
        """Test actual embedding generation with real model"""
        from core.embedding_service import EmbeddingService

        service = EmbeddingService(model_name="BAAI/bge-small-zh-v1.5")
        embedding = service.embed_text("这是一个测试句子")

        assert isinstance(embedding, np.ndarray)
        assert embedding.shape[0] > 0
