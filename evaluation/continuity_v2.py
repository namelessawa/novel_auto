#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced Continuity Evaluator
Multi-dimensional continuity assessment with LLM-powered analysis

This module provides sophisticated continuity evaluation that goes beyond
simple text matching, using semantic understanding and narrative structure
analysis to ensure story coherence.

Features:
- Multi-dimensional continuity scoring
- Semantic contradiction detection
- Character consistency validation
- Plot logic verification
- Temporal consistency checking
- Context-aware scoring weights
"""

import os
import json
import hashlib
import logging
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class ContinuityDimension(Enum):
    """Dimensions for continuity evaluation"""
    CHARACTER = "character"           # Character behavior, traits, state
    PLOT = "plot"                     # Plot progression, causality
    SETTING = "setting"               # Locations, environment, time
    THEME = "theme"                   # Thematic consistency
    STYLE = "style"                   # Writing style, tone
    TEMPORAL = "temporal"             # Time flow, chronology
    RELATIONSHIP = "relationship"     # Character relationships
    FORESHADOWING = "foreshadowing"   # Setup-payoff consistency


@dataclass
class ContinuityIssue:
    """Represents a detected continuity issue"""
    dimension: ContinuityDimension
    severity: str  # "critical", "major", "minor", "suggestion"
    description: str
    location: str  # Where in the text the issue occurs
    suggestion: str  # How to fix it
    confidence: float = 1.0

    def to_dict(self) -> Dict:
        return {
            "dimension": self.dimension.value,
            "severity": self.severity,
            "description": self.description,
            "location": self.location,
            "suggestion": self.suggestion,
            "confidence": self.confidence
        }


@dataclass
class ContinuityScore:
    """Detailed continuity scoring result"""
    overall_score: float
    dimension_scores: Dict[str, float]
    issues: List[ContinuityIssue]
    strengths: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "overall_score": self.overall_score,
            "dimension_scores": self.dimension_scores,
            "issues": [i.to_dict() for i in self.issues],
            "strengths": self.strengths,
            "metadata": self.metadata
        }


class EnhancedContinuityEvaluator:
    """
    Enhanced continuity evaluator with multi-dimensional analysis

    Uses LLM for semantic understanding and provides detailed
    feedback for iterative refinement.
    """

    # 评估缓存上限 (FIFO) — 防止长跑进程内存无界增长
    CACHE_MAX_ENTRIES = 128

    # Default weights for dimension scoring
    DEFAULT_WEIGHTS = {
        ContinuityDimension.CHARACTER: 0.20,
        ContinuityDimension.PLOT: 0.25,
        ContinuityDimension.SETTING: 0.10,
        ContinuityDimension.THEME: 0.10,
        ContinuityDimension.STYLE: 0.05,
        ContinuityDimension.TEMPORAL: 0.10,
        ContinuityDimension.RELATIONSHIP: 0.15,
        ContinuityDimension.FORESHADOWING: 0.05,
    }

    def __init__(
        self,
        llm_client=None,
        weights: Optional[Dict[ContinuityDimension, float]] = None,
        strictness: float = 0.7
    ):
        """
        Initialize the enhanced continuity evaluator

        Args:
            llm_client: LLM client for semantic analysis
            weights: Custom dimension weights
            strictness: Strictness level (0.0-1.0), affects issue detection sensitivity
        """
        self.llm_client = llm_client
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self.strictness = strictness

        # Cache for repeated evaluations
        self._cache: Dict[str, ContinuityScore] = {}

    def evaluate(
        self,
        previous_context: str,
        new_content: str,
        memory_context: Optional[Dict] = None
    ) -> ContinuityScore:
        """
        Perform comprehensive continuity evaluation

        Args:
            previous_context: Previous chapter/content for context
            new_content: New content to evaluate
            memory_context: Additional context from memory system

        Returns:
            ContinuityScore with detailed results
        """
        # Check cache
        cache_key = self._compute_cache_key(previous_context, new_content, memory_context)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Perform LLM-based evaluation
        if self.llm_client:
            score = self._llm_evaluate(previous_context, new_content, memory_context)
        else:
            score = self._heuristic_evaluate(previous_context, new_content)

        # Cache result — FIFO 淘汰最早的条目, 上限 CACHE_MAX_ENTRIES
        while len(self._cache) >= self.CACHE_MAX_ENTRIES:
            self._cache.pop(next(iter(self._cache)))
        self._cache[cache_key] = score
        return score

    def _llm_evaluate(
        self,
        previous_context: str,
        new_content: str,
        memory_context: Optional[Dict]
    ) -> ContinuityScore:
        """Use LLM for semantic evaluation"""
        # backend 的 LLMClient 没有 generate_json 方法 — hasattr 防御,
        # 缺失时按 degraded 启发式处理而非 AttributeError 崩掉整次扫描。
        generate_json = getattr(self.llm_client, "generate_json", None)
        if not callable(generate_json):
            logger.warning(
                "连续性 LLM 客户端 %s 缺少 generate_json 方法，退化为启发式评估（已标记 degraded）",
                type(self.llm_client).__name__,
            )
            score = self._heuristic_evaluate(previous_context, new_content)
            score.metadata["degraded"] = True
            score.metadata["degraded_reason"] = "llm_client_missing_generate_json"
            return score

        prompt = self._build_evaluation_prompt(previous_context, new_content, memory_context)

        result = generate_json(prompt)

        if not result:
            # LLM 评估失败时不能静默地按启发式 ~0.8 通过，否则
            # 损坏的章节会被当作合格分数放行。标记为 degraded 并告警。
            logger.warning("连续性 LLM 评估失败，退化为启发式评估（结果不可靠，已标记 degraded）")
            score = self._heuristic_evaluate(previous_context, new_content)
            score.metadata["degraded"] = True
            score.metadata["degraded_reason"] = "llm_evaluation_failed"
            return score

        # Parse LLM response
        dimension_scores = {}
        issues = []
        strengths = []

        for dim in ContinuityDimension:
            dim_key = f"{dim.value}_continuity"
            if dim_key in result:
                dimension_scores[dim.value] = result[dim_key]
            else:
                dimension_scores[dim.value] = 0.8  # Default

        # Parse issues
        for issue_data in result.get("issues", []):
            try:
                dim = ContinuityDimension(issue_data.get("dimension", "plot"))
                issues.append(ContinuityIssue(
                    dimension=dim,
                    severity=issue_data.get("severity", "minor"),
                    description=issue_data.get("description", ""),
                    location=issue_data.get("location", ""),
                    suggestion=issue_data.get("suggestion", ""),
                    confidence=issue_data.get("confidence", 1.0)
                ))
            except (ValueError, KeyError):
                continue

        strengths = result.get("strengths", [])

        # Calculate overall score
        overall = self._compute_weighted_score(dimension_scores)

        return ContinuityScore(
            overall_score=overall,
            dimension_scores=dimension_scores,
            issues=issues,
            strengths=strengths,
            metadata={
                "method": "llm",
                "model": getattr(self.llm_client, 'model_name', 'unknown'),
                "timestamp": datetime.now().isoformat()
            }
        )

    def _heuristic_evaluate(
        self,
        previous_context: str,
        new_content: str
    ) -> ContinuityScore:
        """Fallback heuristic evaluation without LLM"""
        dimension_scores = {}
        issues = []
        strengths = []

        # Character continuity - check for character name consistency
        char_score = self._check_character_consistency(previous_context, new_content)
        dimension_scores[ContinuityDimension.CHARACTER.value] = char_score
        if char_score < 0.7:
            issues.append(ContinuityIssue(
                dimension=ContinuityDimension.CHARACTER,
                severity="major" if char_score < 0.5 else "minor",
                description="Character name or trait inconsistency detected",
                location="Multiple occurrences",
                suggestion="Review character names and traits for consistency"
            ))

        # Setting continuity
        setting_score = self._check_setting_consistency(previous_context, new_content)
        dimension_scores[ContinuityDimension.SETTING.value] = setting_score

        # Temporal consistency
        temporal_score = self._check_temporal_consistency(previous_context, new_content)
        dimension_scores[ContinuityDimension.TEMPORAL.value] = temporal_score

        # Default scores for dimensions requiring semantic understanding
        for dim in [ContinuityDimension.PLOT, ContinuityDimension.THEME,
                    ContinuityDimension.STYLE, ContinuityDimension.RELATIONSHIP,
                    ContinuityDimension.FORESHADOWING]:
            dimension_scores[dim.value] = 0.8  # Default neutral score

        overall = self._compute_weighted_score(dimension_scores)

        if overall >= 0.7:
            strengths.append("Basic continuity maintained")

        return ContinuityScore(
            overall_score=overall,
            dimension_scores=dimension_scores,
            issues=issues,
            strengths=strengths,
            metadata={"method": "heuristic", "timestamp": datetime.now().isoformat()}
        )

    def _build_evaluation_prompt(
        self,
        previous_context: str,
        new_content: str,
        memory_context: Optional[Dict]
    ) -> str:
        """Build the LLM evaluation prompt"""
        # Extract relevant context parts
        prev_preview = previous_context[-1500:] if len(previous_context) > 1500 else previous_context
        new_preview = new_content[:1500] if len(new_content) > 1500 else new_content

        memory_section = ""
        # 仅接受 dict — 误传字符串时跳过而非 `'key' in str` 子串误命中后
        # str['key'] 抛 TypeError (ConsistencyGuardianAdapter 修复前的事故模式)。
        # v2.38 (iter#26) — json indent 去掉, 节省 30% memory_section 体积.
        if isinstance(memory_context, dict) and memory_context:
            # Include key memory info — 'characters' 与 'character_states' 两个键
            # 都识别 (旧节级管线用前者, tick 架构 guardian 曾用后者)。
            char_states = memory_context.get("characters") or memory_context.get("character_states")
            if char_states:
                memory_section += f"\n已知角色状态:\n{json.dumps(char_states, ensure_ascii=False, default=str)}\n"
            if memory_context.get("world_state"):
                memory_section += f"\n世界状态:\n{json.dumps(memory_context['world_state'], ensure_ascii=False, default=str)}\n"
            if "relationships" in memory_context:
                memory_section += f"\n已知角色关系:\n{json.dumps(memory_context['relationships'], ensure_ascii=False, default=str)}\n"
            if "recent_events" in memory_context:
                memory_section += f"\n最近事件:\n{memory_context['recent_events']}\n"

        # v2.38 (iter#26) — 8 维度详细子项压缩到单行 ~80 chars/dim. 节省
        # ~400 chars 总体. 评估精度保留.
        prompt = f"""请作为专业小说编辑, 对新章节进行连续性评估.

## 前文上下文
{prev_preview}

## 新章节内容
{new_preview}
{memory_section}

## 评估要求 (每维度 0.0-1.0 分)

1. **character_continuity**: 人物行为/状态/对话风格是否一致
2. **plot_continuity**: 情节衔接、逻辑漏洞、因果关系
3. **setting_continuity**: 地点转换、环境描述、场景细节
4. **theme_continuity**: 主题与核心冲突推进
5. **style_continuity**: 叙述风格、语言特色
6. **temporal_continuity**: 时间线、时间跳跃合理性
7. **relationship_continuity**: 角色关系与铺垫
8. **foreshadowing_continuity**: 伏笔回收与新伏笔自然度

## 输出格式
请返回JSON格式：
{{
    "character_continuity": 0.x,
    "plot_continuity": 0.x,
    "setting_continuity": 0.x,
    "theme_continuity": 0.x,
    "style_continuity": 0.x,
    "temporal_continuity": 0.x,
    "relationship_continuity": 0.x,
    "foreshadowing_continuity": 0.x,
    "issues": [
        {{
            "dimension": "character|plot|setting|theme|style|temporal|relationship|foreshadowing",
            "severity": "critical|major|minor|suggestion",
            "description": "问题描述",
            "location": "问题位置（引用原文）",
            "suggestion": "修改建议",
            "confidence": 0.x
        }}
    ],
    "strengths": ["亮点1", "亮点2"]
}}
"""
        return prompt

    def _check_character_consistency(self, previous: str, new: str) -> float:
        """Heuristic character consistency check"""
        import re

        # Extract character names (Chinese names pattern)
        prev_names = set(re.findall(r'[一-鿿]{2,4}(?:·[一-鿿]{2,4})*', previous))
        new_names = set(re.findall(r'[一-鿿]{2,4}(?:·[一-鿿]{2,4})*', new))

        if not prev_names or not new_names:
            return 0.8

        # Check overlap
        overlap = len(prev_names & new_names)
        total = len(prev_names | new_names)

        if total == 0:
            return 0.8

        return overlap / total if total > 0 else 0.8

    def _check_setting_consistency(self, previous: str, new: str) -> float:
        """Heuristic setting consistency check"""
        # Simple location keyword matching
        location_keywords = ['房间', '街道', '森林', '山', '河', '城市', '村庄', '宫殿', '花园']
        prev_locations = set(loc for loc in location_keywords if loc in previous)
        new_locations = set(loc for loc in location_keywords if loc in new)

        # If both have location mentions, check if there's reasonable transition
        if prev_locations and new_locations:
            overlap = prev_locations & new_locations
            # Allow for location changes, just check if not completely disjoint
            if len(overlap) > 0:
                return 0.9
            return 0.7  # Location changed, might need transition
        return 0.8

    def _check_temporal_consistency(self, previous: str, new: str) -> float:
        """Heuristic temporal consistency check"""
        time_indicators = ['今天', '明天', '昨天', '早上', '晚上', '中午', '黄昏', '夜晚']
        prev_times = [t for t in time_indicators if t in previous]
        new_times = [t for t in time_indicators if t in new]

        if prev_times and new_times:
            # Simple check - no direct contradiction
            return 0.8
        return 0.85

    def _compute_weighted_score(self, dimension_scores: Dict[str, float]) -> float:
        """Compute overall weighted score"""
        total = 0.0
        weight_sum = 0.0

        for dim, weight in self.weights.items():
            dim_key = dim.value if isinstance(dim, ContinuityDimension) else dim
            if dim_key in dimension_scores:
                total += dimension_scores[dim_key] * weight
                weight_sum += weight

        return total / weight_sum if weight_sum > 0 else 0.0

    def _compute_cache_key(
        self,
        previous_context: str,
        new_content: str,
        memory_context: Optional[Dict]
    ) -> str:
        """Compute cache key for evaluation results"""
        # default=str 保证 memory_context 中出现的非 JSON 原生类型
        # （如 datetime、set）不会让缓存键计算抛出 TypeError 而中断评估。
        content = f"{previous_context}|||{new_content}|||{json.dumps(memory_context, sort_keys=True, default=str)}"
        return hashlib.md5(content.encode()).hexdigest()

    def get_critical_issues(self, score: ContinuityScore) -> List[ContinuityIssue]:
        """Get only critical and major issues from score"""
        return [i for i in score.issues if i.severity in ("critical", "major")]

    def generate_fix_prompt(
        self,
        score: ContinuityScore,
        new_content: str,
        previous_context: str = ""
    ) -> str:
        """
        Generate a prompt for fixing identified issues

        Args:
            score: 评估结果
            new_content: 需要修复的完整章节内容（不再截断，避免丢失后半段）
            previous_context: 前一章上下文，让优化器知道需要与什么衔接
        """
        issues_text = "\n".join([
            f"- [{i.severity}] {i.dimension.value}: {i.description}"
            f"\n  位置: {i.location}"
            f"\n  建议: {i.suggestion}"
            for i in score.issues
        ])

        # 前文上下文（仅取结尾部分用于衔接判断）
        prev_section = ""
        if previous_context:
            prev_preview = previous_context[-1500:] if len(previous_context) > 1500 else previous_context
            prev_section = f"""## 前文上下文（仅供衔接参考，不要重复输出）
{prev_preview}

"""

        prompt = f"""请修复以下章节中的连续性问题：

{prev_section}## 原章节内容
{new_content}

## 检测到的问题
{issues_text}

## 修改要求
1. 保持原有的叙事风格和语气
2. 只修改有问题的地方，尽量少改动
3. 确保修改后的内容与前文自然衔接
4. 保持字数相近
5. 必须输出完整章节，不要省略或截断任何段落

请输出修改后的完整章节内容："""
        return prompt


class ContinuityEvaluatorAdapter:
    """
    Adapter for backward compatibility with existing ChapterContinuityEvaluator

    This adapter wraps the enhanced evaluator to provide a compatible interface
    with the legacy continuity evaluator.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str = "deepseek-chat",
        **kwargs
    ):
        """Initialize adapter with legacy parameters"""
        from core.llm_client import LLMClient

        self.llm_client = LLMClient(
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            # v2.38 (iter#9) — continuity 检查输出是 JSON 报告, 几千 tokens 够.
            max_tokens=4096,
            temperature=0.2
        )

        self.enhanced_evaluator = EnhancedContinuityEvaluator(
            llm_client=self.llm_client,
            **kwargs
        )

        # Legacy weights for compatibility
        self.legacy_weights = {
            'character_continuity': 0.25,
            'plot_continuity': 0.35,
            'setting_continuity': 0.15,
            'theme_continuity': 0.15,
            'style_continuity': 0.10
        }

    def evaluate_continuity(
        self,
        previous_chapter: str,
        new_chapter: str,
        memory_context: Optional[Dict] = None
    ) -> Tuple[float, Dict]:
        """
        Legacy-compatible evaluation interface

        Args:
            previous_chapter: Previous chapter content
            new_chapter: New chapter content
            memory_context: Optional memory context

        Returns:
            Tuple of (score, score_breakdown)
        """
        result = self.enhanced_evaluator.evaluate(
            previous_chapter,
            new_chapter,
            memory_context
        )

        # Map to legacy format.
        # 缺失维度回退到 overall_score（而非 1.0），避免把未评分的维度
        # 伪装成满分从而掩盖真实问题。
        fallback = result.overall_score
        score_breakdown = {
            'character_continuity': result.dimension_scores.get('character', fallback),
            'plot_continuity': result.dimension_scores.get('plot', fallback),
            'setting_continuity': result.dimension_scores.get('setting', fallback),
            'theme_continuity': result.dimension_scores.get('theme', fallback),
            'style_continuity': result.dimension_scores.get('style', fallback)
        }

        # Print issues if any
        if result.issues:
            print(f"检测到 {len(result.issues)} 个连续性问题:")
            for issue in result.issues:
                print(f"  [{issue.severity}] {issue.dimension.value}: {issue.description}")

        return (result.overall_score * 100, score_breakdown)
