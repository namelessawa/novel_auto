#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Token Counter Utility
Provides accurate token counting using tiktoken for memory management
"""

from typing import List, Union
from pathlib import Path

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


class TokenCounter:
    """
    Token counting utility using tiktoken

    Provides accurate token counting for:
    - Chinese text (using cl100k_base encoding)
    - English text
    - Mixed language content
    """

    # Default encoding for most modern LLMs
    DEFAULT_ENCODING = "cl100k_base"

    def __init__(self, encoding_name: str = None):
        """
        Initialize token counter

        Args:
            encoding_name: tiktoken encoding name (default: cl100k_base)
        """
        self.encoding_name = encoding_name or self.DEFAULT_ENCODING
        self._encoding = None

    @property
    def encoding(self):
        """Lazy load encoding"""
        if self._encoding is None:
            if not TIKTOKEN_AVAILABLE:
                raise ImportError(
                    "tiktoken is required for accurate token counting. "
                    "Install with: pip install tiktoken"
                )
            self._encoding = tiktoken.get_encoding(self.encoding_name)
        return self._encoding

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text

        Args:
            text: Text to count

        Returns:
            int: Number of tokens
        """
        if not text:
            return 0

        try:
            return len(self.encoding.encode(text))
        except Exception:
            # Fallback to approximation
            return self._approximate_tokens(text)

    def count_tokens_batch(self, texts: List[str]) -> List[int]:
        """
        Count tokens in multiple texts

        Args:
            texts: List of texts

        Returns:
            List[int]: Token counts for each text
        """
        return [self.count_tokens(text) for text in texts]

    def _approximate_tokens(self, text: str) -> int:
        """
        Approximate token count when tiktoken fails

        Uses simple heuristic:
        - Chinese characters: ~1 token each
        - English words: ~1.3 tokens each
        - Other: ~0.5 tokens per character

        Args:
            text: Text to approximate

        Returns:
            int: Approximate token count
        """
        if not text:
            return 0

        # Count Chinese characters
        chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')

        # Count English words
        english_words = len([w for w in text.split() if w.isascii()])

        # Other characters
        other_chars = len(text) - chinese_chars - sum(len(w) for w in text.split() if w.isascii())

        # Approximate
        return int(chinese_chars * 1.0 + english_words * 1.3 + other_chars * 0.5)

    def truncate_to_tokens(self, text: str, max_tokens: int, suffix: str = "...") -> str:
        """
        Truncate text to fit within token limit

        Args:
            text: Text to truncate
            max_tokens: Maximum tokens
            suffix: Suffix to add when truncated

        Returns:
            str: Truncated text
        """
        if not text:
            return text

        current_tokens = self.count_tokens(text)
        if current_tokens <= max_tokens:
            return text

        # Binary search for optimal truncation point
        left, right = 0, len(text)

        while left < right:
            mid = (left + right + 1) // 2
            truncated = text[:mid]
            if self.count_tokens(truncated) <= max_tokens - len(suffix):
                left = mid
            else:
                right = mid - 1

        return text[:left] + suffix

    def split_by_tokens(self, text: str, max_tokens: int) -> List[str]:
        """
        Split text into chunks by token count

        Args:
            text: Text to split
            max_tokens: Maximum tokens per chunk

        Returns:
            List[str]: List of text chunks
        """
        if not text:
            return []

        if self.count_tokens(text) <= max_tokens:
            return [text]

        chunks = []
        remaining = text

        while remaining:
            # Find split point
            left, right = 0, len(remaining)

            while left < right:
                mid = (left + right + 1) // 2
                chunk = remaining[:mid]
                if self.count_tokens(chunk) <= max_tokens:
                    left = mid
                else:
                    right = mid - 1

            if left == 0:
                # Single character is too long, force split
                chunks.append(remaining[:100])
                remaining = remaining[100:]
            else:
                chunks.append(remaining[:left])
                remaining = remaining[left:]

        return chunks


def get_token_counter() -> TokenCounter:
    """
    Get a global token counter instance

    Returns:
        TokenCounter: Token counter instance
    """
    return TokenCounter()
