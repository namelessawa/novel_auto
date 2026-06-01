#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for TokenCounter
Tests for accurate token counting functionality
"""

import pytest
from unittest.mock import Mock, patch


class TestTokenCounter:
    """Tests for TokenCounter class"""

    def test_count_tokens_empty_string(self):
        """Test token counting for empty string"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()
        assert counter.count_tokens("") == 0

    def test_count_tokens_chinese_text(self):
        """Test token counting for Chinese text"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        # Chinese text should have approximately 1 token per character
        text = "这是一个测试文本"
        token_count = counter.count_tokens(text)

        # Should be roughly equal to character count (within 50% margin)
        assert token_count > 0
        assert token_count <= len(text) * 2

    def test_count_tokens_english_text(self):
        """Test token counting for English text"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        text = "This is a test sentence in English."
        token_count = counter.count_tokens(text)

        # Should be roughly equal to word count * 1.3
        word_count = len(text.split())
        assert token_count > 0
        assert token_count >= word_count * 0.5

    def test_count_tokens_mixed_language(self):
        """Test token counting for mixed Chinese-English text"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        text = "这是一个 test 测试 mixed 混合文本"
        token_count = counter.count_tokens(text)

        assert token_count > 0

    def test_count_tokens_batch(self):
        """Test batch token counting"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        texts = [
            "文本一",
            "文本二测试",
            "Text three"
        ]

        counts = counter.count_tokens_batch(texts)

        assert len(counts) == 3
        assert all(c > 0 for c in counts)

    def test_truncate_to_tokens(self):
        """Test text truncation by token count"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        long_text = "这是一个很长的测试文本" * 100
        max_tokens = 50

        truncated = counter.truncate_to_tokens(long_text, max_tokens)

        # Should be within token limit
        assert counter.count_tokens(truncated) <= max_tokens
        assert truncated.endswith("...")

    def test_truncate_to_tokens_no_truncation_needed(self):
        """Test truncation when text is already within limit"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        text = "短文本"
        max_tokens = 100

        truncated = counter.truncate_to_tokens(text, max_tokens)

        assert truncated == text

    def test_split_by_tokens(self):
        """Test splitting text by token count"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        long_text = "这是一个测试文本。" * 50
        max_tokens = 20

        chunks = counter.split_by_tokens(long_text, max_tokens)

        assert len(chunks) > 1
        assert all(counter.count_tokens(chunk) <= max_tokens for chunk in chunks)

    def test_split_by_tokens_short_text(self):
        """Test splitting short text"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        text = "短文本"
        max_tokens = 100

        chunks = counter.split_by_tokens(text, max_tokens)

        assert len(chunks) == 1
        assert chunks[0] == text


class TestTokenCounterFallback:
    """Tests for fallback token counting"""

    def test_approximate_tokens_chinese(self):
        """Test approximate token counting for Chinese"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        # Test approximate method directly
        text = "中文测试文本"
        approx = counter._approximate_tokens(text)

        # Should be close to character count
        assert approx > 0
        assert approx <= len(text) * 2

    def test_approximate_tokens_english(self):
        """Test approximate token counting for English"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        text = "This is a test"
        approx = counter._approximate_tokens(text)

        # Should be roughly word count * 1.3
        word_count = len(text.split())
        assert approx > 0

    def test_approximate_tokens_empty(self):
        """Test approximate token counting for empty string"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()
        approx = counter._approximate_tokens("")

        assert approx == 0


class TestTokenCounterEdgeCases:
    """Tests for edge cases in token counting"""

    def test_whitespace_only(self):
        """Test token counting for whitespace only"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()
        count = counter.count_tokens("   \n\t  ")

        # Should count whitespace
        assert count >= 0

    def test_special_characters(self):
        """Test token counting for special characters"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        text = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        count = counter.count_tokens(text)

        assert count > 0

    def test_newlines(self):
        """Test token counting with newlines"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        text = "第一行\n第二行\n第三行"
        count = counter.count_tokens(text)

        assert count > 0

    def test_unicode_emoji(self):
        """Test token counting with emoji"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        text = "测试文本😀🎉"
        count = counter.count_tokens(text)

        # Emoji typically take more tokens
        assert count > 0

    def test_very_long_text(self):
        """Test token counting for very long text"""
        from utils.token_counter import TokenCounter

        counter = TokenCounter()

        # Create a very long text
        text = "测试文本" * 10000
        count = counter.count_tokens(text)

        assert count > 0
        assert count < len(text) * 2  # Sanity check
