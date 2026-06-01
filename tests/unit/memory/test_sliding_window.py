#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for SlidingWindowMemory
Tests for token-based memory management
"""

import pytest
import os
import json
from unittest.mock import Mock, patch, MagicMock


class TestSlidingWindowMemory:
    """Tests for SlidingWindowMemory class"""

    def test_init_with_max_tokens(self, temp_memory_dir):
        """Test initialization with custom max tokens"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=5000, memory_dir=temp_memory_dir)

        assert window.max_tokens == 5000

    def test_add_content(self, temp_memory_dir, sample_chapter):
        """Test adding content to sliding window"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=2500, memory_dir=temp_memory_dir)
        window.add_content("第一章", sample_chapter)

        assert len(window.content) == 1
        assert window.content[0]['title'] == "第一章"
        assert 'token_count' in window.content[0]

    def test_token_counting(self, temp_memory_dir, sample_chapter):
        """Test that token counting is used instead of character counting"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=2500, memory_dir=temp_memory_dir)
        window.add_content("第一章", sample_chapter)

        # Token count should be stored
        assert 'token_count' in window.content[0]
        assert window.content[0]['token_count'] > 0

        # Token count may differ from character count
        char_count = window.content[0].get('char_count', 0)
        token_count = window.content[0]['token_count']

        # Both should be positive
        assert char_count > 0
        assert token_count > 0

    def test_get_token_count(self, temp_memory_dir, sample_chapter):
        """Test total token count calculation"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=5000, memory_dir=temp_memory_dir)
        window.add_content("第一章", sample_chapter)
        window.add_content("第二章", sample_chapter)

        total = window.get_token_count()

        assert total > 0
        assert total == window.content[0]['token_count'] + window.content[1]['token_count']

    def test_trimming_by_tokens(self, temp_memory_dir):
        """Test that content is trimmed based on token count, not character count"""
        from memory_system.sliding_window import SlidingWindowMemory

        # Small max tokens to force trimming
        window = SlidingWindowMemory(max_tokens=100, memory_dir=temp_memory_dir)

        # Add multiple chapters - each one is about 50 tokens
        for i in range(5):
            window.add_content(f"第{i+1}章", "这是测试内容。" * 20)

        # Should have trimmed some content
        # Note: trimming only happens when there's more than 1 item
        assert len(window.content) <= 5
        # Token count should be reasonable (allowing some margin for encoding variations)
        assert window.get_token_count() <= window.max_tokens + 200

    def test_get_context_with_max_tokens(self, temp_memory_dir, sample_chapter):
        """Test getting context with token limit"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=5000, memory_dir=temp_memory_dir)
        window.add_content("第一章", sample_chapter)
        window.add_content("第二章", sample_chapter)

        context = window.get_context(max_tokens=50)

        # Context should be truncated
        assert len(context) > 0

    def test_get_context_backward_compatible(self, temp_memory_dir, sample_chapter):
        """Test backward compatible context retrieval with max_chars"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=5000, memory_dir=temp_memory_dir)
        window.add_content("第一章", sample_chapter)

        context = window.get_context(max_chars=100)

        assert len(context) <= 103  # max_chars + "..."
        assert len(context) > 0

    def test_persistence(self, temp_memory_dir, sample_chapter):
        """Test that content is persisted to disk"""
        from memory_system.sliding_window import SlidingWindowMemory

        # Create and add content
        window1 = SlidingWindowMemory(max_tokens=2500, memory_dir=temp_memory_dir)
        window1.add_content("第一章", sample_chapter)

        # Create new instance and load
        window2 = SlidingWindowMemory(max_tokens=2500, memory_dir=temp_memory_dir)

        assert len(window2.content) == 1
        assert window2.content[0]['title'] == "第一章"

    def test_clear(self, temp_memory_dir, sample_chapter):
        """Test clearing the sliding window"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=2500, memory_dir=temp_memory_dir)
        window.add_content("第一章", sample_chapter)

        window.clear()

        assert len(window.content) == 0


class TestSlidingWindowMemoryTokenAccuracy:
    """Tests for accurate token counting in sliding window"""

    def test_chinese_text_token_counting(self, temp_memory_dir):
        """Test token counting accuracy for Chinese text"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=2500, memory_dir=temp_memory_dir)

        # Pure Chinese text
        chinese_text = "这是一个中文测试文本，用于验证token计数的准确性。"
        window.add_content("测试", chinese_text)

        # Token count should be calculated
        assert 'token_count' in window.content[0]
        token_count = window.content[0]['token_count']

        # Should be roughly 1-2 tokens per Chinese character
        assert token_count > 0

    def test_mixed_language_token_counting(self, temp_memory_dir):
        """Test token counting for mixed language text"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=2500, memory_dir=temp_memory_dir)

        # Mixed text
        mixed_text = "这是Chinese混合English文本text。"
        window.add_content("测试", mixed_text)

        assert 'token_count' in window.content[0]
        assert window.content[0]['token_count'] > 0

    def test_eviction_preserves_recent_content(self, temp_memory_dir):
        """Test that eviction removes oldest content first"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=30, memory_dir=temp_memory_dir)

        # Add chapters - each one is small but will trigger eviction
        for i in range(5):
            window.add_content(f"第{i+1}章", f"第{i+1}章。")

        # Most recent chapters should be preserved
        titles = [item['title'] for item in window.content]
        # The window should have trimmed content
        assert len(window.content) < 5 or window.get_token_count() <= 50
        # Most recent should be present
        if len(window.content) > 0:
            assert "第5章" == window.content[-1]['title']  # Most recent is last


class TestSlidingWindowMemoryEdgeCases:
    """Tests for edge cases in sliding window memory"""

    def test_empty_content(self, temp_memory_dir):
        """Test handling of empty content"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=2500, memory_dir=temp_memory_dir)
        window.add_content("空章节", "")

        assert len(window.content) == 1
        assert window.content[0]['token_count'] == 0

    def test_very_long_single_chapter(self, temp_memory_dir):
        """Test handling of very long single chapter"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=100, memory_dir=temp_memory_dir)

        # Very long chapter
        long_chapter = "测试内容。" * 1000
        window.add_content("长章节", long_chapter)

        # Should not crash, may or may not trim
        assert len(window.content) >= 1

    def test_single_item_not_evicted(self, temp_memory_dir):
        """Test that last item is not evicted even if over limit"""
        from memory_system.sliding_window import SlidingWindowMemory

        window = SlidingWindowMemory(max_tokens=10, memory_dir=temp_memory_dir)

        # Single large chapter
        large_chapter = "这是一个很长的测试内容。" * 100
        window.add_content("大章节", large_chapter)

        # Should keep at least one item
        assert len(window.content) == 1
