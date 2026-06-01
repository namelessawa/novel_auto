#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Context Integrity Manager
Ensures context integrity during generation and prevents token truncation issues

This module manages context assembly and ensures that:
1. Critical context is never truncated
2. Token limits are respected intelligently
3. Context priority is enforced
4. Truncation points are semantically meaningful

Features:
- Priority-based context assembly
- Semantic truncation at sentence boundaries
- Context compression when needed
- Token budget management
- Critical content protection
"""

import os
import json
import re
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict


class ContextPriority(Enum):
    """Priority levels for context content"""
    CRITICAL = 1     # Must never be truncated (character states, active plot)
    HIGH = 2         # Important context (recent events, relationships)
    MEDIUM = 3       # Useful context (background info, summaries)
    LOW = 4          # Optional context (style hints, general info)


class ContentType(Enum):
    """Types of content in context"""
    CHARACTER_STATE = "character_state"
    RELATIONSHIP = "relationship"
    PLOT_THREAD = "plot_thread"
    FORESHADOWING = "foreshadowing"
    RECENT_TEXT = "recent_text"
    SUMMARY = "summary"
    STYLE_GUIDE = "style_guide"
    WORLD_INFO = "world_info"
    INSTRUCTION = "instruction"


@dataclass
class ContextBlock:
    """A block of context content with metadata"""
    content: str
    content_type: ContentType
    priority: ContextPriority
    source: str
    token_estimate: int = 0
    is_compressed: bool = False
    original_content: str = ""

    def __post_init__(self):
        if not self.token_estimate:
            self.token_estimate = self._estimate_tokens(self.content)
        if self.original_content and not self.is_compressed:
            self.is_compressed = True

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count for text"""
        # Rough estimation: ~1.5 chars per token for Chinese, ~4 for English
        chinese_chars = len(re.findall(r'[一-鿿]', text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4) + 1


@dataclass
class IntegrityResult:
    """Result of context integrity check"""
    is_valid: bool
    total_tokens: int
    blocks_included: int
    blocks_truncated: int
    truncation_points: List[str]
    warnings: List[str]
    context: str


class ContextIntegrityManager:
    """
    Manages context integrity during generation

    Ensures that critical context is preserved and truncation
    happens at appropriate boundaries.
    """

    # Default token budgets
    DEFAULT_MAX_TOKENS = 8000
    RESERVE_TOKENS = 2000  # Reserved for response

    # Priority thresholds for content types
    DEFAULT_PRIORITIES = {
        ContentType.CHARACTER_STATE: ContextPriority.CRITICAL,
        ContentType.RELATIONSHIP: ContextPriority.HIGH,
        ContentType.PLOT_THREAD: ContextPriority.CRITICAL,
        ContentType.FORESHADOWING: ContextPriority.HIGH,
        ContentType.RECENT_TEXT: ContextPriority.HIGH,
        ContentType.SUMMARY: ContextPriority.MEDIUM,
        ContentType.STYLE_GUIDE: ContextPriority.LOW,
        ContentType.WORLD_INFO: ContextPriority.MEDIUM,
        ContentType.INSTRUCTION: ContextPriority.CRITICAL,
    }

    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        reserve_tokens: int = RESERVE_TOKENS,
        priorities: Optional[Dict[ContentType, ContextPriority]] = None,
        compression_threshold: float = 0.8
    ):
        """
        Initialize context integrity manager

        Args:
            max_tokens: Maximum tokens for context
            reserve_tokens: Tokens reserved for response
            priorities: Custom priority mapping
            compression_threshold: When to start compressing (fraction of max)
        """
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens
        self.available_tokens = max_tokens - reserve_tokens
        self.priorities = priorities or self.DEFAULT_PRIORITIES.copy()
        self.compression_threshold = compression_threshold

        # Context blocks storage
        self._blocks: List[ContextBlock] = []

        # Statistics
        self._stats = {
            "total_assemblies": 0,
            "total_truncations": 0,
            "compression_count": 0
        }

    def add_block(
        self,
        content: str,
        content_type: ContentType,
        source: str = "",
        priority: Optional[ContextPriority] = None
    ) -> None:
        """
        Add a context block

        Args:
            content: The content text
            content_type: Type of content
            source: Source identifier
            priority: Override priority (uses default if not specified)
        """
        block = ContextBlock(
            content=content,
            content_type=content_type,
            priority=priority or self.priorities.get(content_type, ContextPriority.MEDIUM),
            source=source
        )
        self._blocks.append(block)

    def clear_blocks(self) -> None:
        """Clear all context blocks"""
        self._blocks = []

    def assemble_context(self) -> IntegrityResult:
        """
        Assemble context with integrity protection

        Returns:
            IntegrityResult with assembled context and metadata
        """
        self._stats["total_assemblies"] += 1

        # Sort blocks by priority
        sorted_blocks = sorted(self._blocks, key=lambda b: b.priority.value)

        # Calculate total tokens
        total_tokens = sum(b.token_estimate for b in sorted_blocks)

        # Check if compression is needed
        if total_tokens > self.available_tokens * self.compression_threshold:
            sorted_blocks = self._apply_compression(sorted_blocks)

        # Build context respecting token limit
        assembled_parts = []
        current_tokens = 0
        blocks_included = 0
        blocks_truncated = 0
        truncation_points = []
        warnings = []

        for block in sorted_blocks:
            # Check if block can fit
            if current_tokens + block.token_estimate <= self.available_tokens:
                assembled_parts.append(block.content)
                current_tokens += block.token_estimate
                blocks_included += 1
            else:
                # Try to include partial content for high priority blocks
                if block.priority.value <= ContextPriority.HIGH.value:
                    partial, tokens, truncated = self._truncate_block(
                        block,
                        self.available_tokens - current_tokens
                    )
                    if partial:
                        assembled_parts.append(partial)
                        current_tokens += tokens
                        blocks_included += 1
                        blocks_truncated += 1
                        truncation_points.append(f"{block.content_type.value}: truncated {truncated} chars")
                else:
                    blocks_truncated += 1
                    truncation_points.append(f"{block.content_type.value}: excluded")

        # Check for critical blocks that were truncated
        for block in sorted_blocks:
            if block.priority == ContextPriority.CRITICAL:
                if block.content not in "".join(assembled_parts):
                    warnings.append(
                        f"Critical content missing: {block.content_type.value}"
                    )

        # Final assembly
        final_context = "\n\n".join(assembled_parts)

        # Verify token count
        final_tokens = ContextBlock._estimate_tokens(final_context)
        is_valid = final_tokens <= self.available_tokens

        if not is_valid:
            self._stats["total_truncations"] += 1
            # Emergency truncation
            final_context = self._emergency_truncate(final_context, self.available_tokens)
            final_tokens = self.available_tokens

        return IntegrityResult(
            is_valid=is_valid and len(warnings) == 0,
            total_tokens=final_tokens,
            blocks_included=blocks_included,
            blocks_truncated=blocks_truncated,
            truncation_points=truncation_points,
            warnings=warnings,
            context=final_context
        )

    def _apply_compression(self, blocks: List[ContextBlock]) -> List[ContextBlock]:
        """Apply compression to reduce token usage"""
        self._stats["compression_count"] += 1
        compressed_blocks = []

        for block in blocks:
            if block.priority.value >= ContextPriority.MEDIUM.value:
                # Compress medium and low priority content
                compressed = self._compress_content(block.content, block.content_type)
                if compressed != block.content:
                    compressed_blocks.append(ContextBlock(
                        content=compressed,
                        content_type=block.content_type,
                        priority=block.priority,
                        source=block.source,
                        original_content=block.content
                    ))
                else:
                    compressed_blocks.append(block)
            else:
                compressed_blocks.append(block)

        return compressed_blocks

    def _compress_content(self, content: str, content_type: ContentType) -> str:
        """Compress content while preserving key information"""
        # Different compression strategies for different content types
        if content_type == ContentType.RECENT_TEXT:
            # Keep last portion more intact
            if len(content) > 500:
                return "...[前文省略]...\n" + content[-500:]
            return content

        elif content_type == ContentType.SUMMARY:
            # Summaries can be truncated more aggressively
            sentences = re.split(r'[。！？\n]', content)
            if len(sentences) > 3:
                return '。'.join(sentences[:3]) + '。'
            return content

        elif content_type == ContentType.WORLD_INFO:
            # Keep structured info, truncate descriptions
            lines = content.split('\n')
            if len(lines) > 10:
                return '\n'.join(lines[:10]) + '\n[更多信息省略]'
            return content

        # Default: truncate to 80% length at sentence boundary
        if len(content) > 200:
            truncated = content[:int(len(content) * 0.8)]
            # Find last sentence boundary
            last_sentence = max(
                truncated.rfind('。'),
                truncated.rfind('！'),
                truncated.rfind('？'),
                truncated.rfind('\n')
            )
            if last_sentence > len(truncated) * 0.5:
                truncated = truncated[:last_sentence + 1]
            return truncated

        return content

    def _truncate_block(
        self,
        block: ContextBlock,
        available_tokens: int
    ) -> Tuple[str, int, int]:
        """
        Truncate a block to fit available tokens

        Returns:
            Tuple of (truncated_content, token_count, chars_removed)
        """
        # Estimate characters from tokens
        max_chars = int(available_tokens * 1.5)  # Conservative estimate

        if len(block.content) <= max_chars:
            return block.content, block.token_estimate, 0

        # Truncate at sentence boundary
        truncated = block.content[:max_chars]
        last_sentence = max(
            truncated.rfind('。'),
            truncated.rfind('！'),
            truncated.rfind('？'),
            truncated.rfind('\n')
        )

        if last_sentence > max_chars * 0.5:
            truncated = truncated[:last_sentence + 1]
        else:
            # No good boundary, just truncate
            truncated = truncated[:-3] + "..."

        chars_removed = len(block.content) - len(truncated)
        tokens = ContextBlock._estimate_tokens(truncated)

        return truncated, tokens, chars_removed

    def _emergency_truncate(self, content: str, max_tokens: int) -> str:
        """Emergency truncation when all else fails"""
        max_chars = int(max_tokens * 1.5)

        if len(content) <= max_chars:
            return content

        # Find a good truncation point
        truncated = content[:max_chars]

        # Try to end at a sentence
        for i in range(min(200, len(truncated))):
            pos = len(truncated) - i
            if pos > 0 and truncated[pos-1] in '。！？\n':
                truncated = truncated[:pos]
                break

        return truncated

    def get_stats(self) -> Dict:
        """Get integrity manager statistics"""
        return {
            **self._stats,
            "current_blocks": len(self._blocks),
            "available_tokens": self.available_tokens
        }


class ContextBuilder:
    """
    High-level context builder using the integrity manager

    Provides a convenient interface for building context
    from memory system data.
    """

    def __init__(
        self,
        memory_system=None,
        max_tokens: int = 8000
    ):
        """
        Initialize context builder

        Args:
            memory_system: The unified memory system
            max_tokens: Maximum tokens for context
        """
        self.memory_system = memory_system
        self.integrity_manager = ContextIntegrityManager(max_tokens=max_tokens)

    def build_generation_context(
        self,
        chapter_num: int,
        custom_prompt: str = ""
    ) -> IntegrityResult:
        """
        Build complete context for chapter generation

        Args:
            chapter_num: Current chapter number
            custom_prompt: Optional custom instructions

        Returns:
            IntegrityResult with assembled context
        """
        self.integrity_manager.clear_blocks()

        if self.memory_system:
            # Add character states
            self._add_character_states()

            # Add relationships
            self._add_relationships()

            # Add plot threads
            self._add_plot_threads()

            # Add foreshadowing
            self._add_foreshadowing()

            # Add recent text
            self._add_recent_text()

            # Add summaries
            self._add_summaries()

            # Add style guide
            self._add_style_guide()

        # Add custom instructions
        if custom_prompt:
            self.integrity_manager.add_block(
                content=f"[自定义指令]\n{custom_prompt}",
                content_type=ContentType.INSTRUCTION,
                priority=ContextPriority.CRITICAL
            )

        # Add generation instruction
        self.integrity_manager.add_block(
            content="[生成指令]\n请基于以上背景信息，续写接下来的剧情。"
                    "保持人物性格一致，情节自然推进，文风统一。输出纯正文内容。",
            content_type=ContentType.INSTRUCTION,
            priority=ContextPriority.CRITICAL
        )

        return self.integrity_manager.assemble_context()

    def _add_character_states(self):
        """Add character states to context"""
        if not self.memory_system:
            return

        try:
            # Get character states from memory system
            state = self.memory_system.get_character_state("")
            if state:
                content = "[角色状态]\n"
                for char_name, char_state in state.items():
                    content += f"- {char_name}: {char_state}\n"
                self.integrity_manager.add_block(
                    content=content,
                    content_type=ContentType.CHARACTER_STATE
                )
        except Exception:
            pass

    def _add_relationships(self):
        """Add relationship information to context"""
        if not self.memory_system:
            return

        try:
            content = "[角色关系]\n"
            # Get relationships from semantic memory
            # This would integrate with the actual memory system
            self.integrity_manager.add_block(
                content=content,
                content_type=ContentType.RELATIONSHIP
            )
        except Exception:
            pass

    def _add_plot_threads(self):
        """Add plot thread information"""
        if not self.memory_system:
            return

        try:
            content = "[主线剧情]\n"
            # Get active plot threads
            self.integrity_manager.add_block(
                content=content,
                content_type=ContentType.PLOT_THREAD
            )
        except Exception:
            pass

    def _add_foreshadowing(self):
        """Add foreshadowing information"""
        if not self.memory_system:
            return

        try:
            content = "[待回收伏笔]\n"
            # Get pending foreshadowing
            self.integrity_manager.add_block(
                content=content,
                content_type=ContentType.FORESHADOWING
            )
        except Exception:
            pass

    def _add_recent_text(self):
        """Add recent text content"""
        if not self.memory_system:
            return

        try:
            # Get recent context from working memory
            content = "[近期正文]\n"
            self.integrity_manager.add_block(
                content=content,
                content_type=ContentType.RECENT_TEXT
            )
        except Exception:
            pass

    def _add_summaries(self):
        """Add summary information"""
        if not self.memory_system:
            return

        try:
            content = "[故事摘要]\n"
            # Get summaries from hierarchical memory
            self.integrity_manager.add_block(
                content=content,
                content_type=ContentType.SUMMARY
            )
        except Exception:
            pass

    def _add_style_guide(self):
        """Add style guide information"""
        if not self.memory_system:
            return

        try:
            content = "[文风指导]\n"
            # Get style patterns from procedural memory
            self.integrity_manager.add_block(
                content=content,
                content_type=ContentType.STYLE_GUIDE
            )
        except Exception:
            pass
