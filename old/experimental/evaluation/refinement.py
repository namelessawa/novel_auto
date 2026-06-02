#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Iterative Refinement System
Dynamic optimization pipeline for generation quality

This module implements an iterative refinement loop that:
1. Evaluates generated content against continuity and quality criteria
2. Identifies specific issues and improvement opportunities
3. Generates targeted refinements
4. Validates improvements before acceptance

Features:
- Configurable refinement strategies
- Maximum iteration limits to prevent infinite loops
- Quality score tracking across iterations
- Selective refinement (only fix what's broken)
- LLM-powered refinement generation
"""

import os
import json
import time
from typing import List, Dict, Tuple, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class RefinementStrategy(Enum):
    """Strategies for content refinement"""
    FULL_REWRITE = "full_rewrite"       # Rewrite entire content
    TARGETED_FIX = "targeted_fix"       # Fix specific issues only
    INCREMENTAL = "incremental"         # Small incremental improvements
    HYBRID = "hybrid"                   # Mix of strategies based on severity


class RefinementStatus(Enum):
    """Status of refinement process"""
    ACCEPTED = "accepted"               # Content accepted as-is
    REFINED = "refined"                 # Successfully refined
    FAILED = "failed"                   # Failed to meet criteria
    TIMEOUT = "timeout"                 # Max iterations reached


@dataclass
class RefinementStep:
    """Single step in the refinement process"""
    iteration: int
    score: float
    issues: List[Dict]
    changes_made: str          # 人类可读的变更描述（如 "Full rewrite performed"）
    content: str = ""          # 该步实际产出的章节正文（用于回溯"最佳版本"）
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class RefinementResult:
    """Complete refinement result"""
    original_content: str
    final_content: str
    status: RefinementStatus
    steps: List[RefinementStep]
    initial_score: float
    final_score: float
    improvement: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def iterations(self) -> int:
        return len(self.steps)

    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "initial_score": self.initial_score,
            "final_score": self.final_score,
            "improvement": self.improvement,
            "iterations": self.iterations,
            "steps": [
                {
                    "iteration": s.iteration,
                    "score": s.score,
                    "changes": s.changes_made
                }
                for s in self.steps
            ]
        }


class IterativeRefinement:
    """
    Iterative refinement system for content optimization

    Provides a structured approach to improving generated content
    through iterative evaluation and refinement cycles.
    """

    def __init__(
        self,
        evaluator=None,
        llm_client=None,
        strategy: RefinementStrategy = RefinementStrategy.HYBRID,
        threshold: float = 80.0,
        max_iterations: int = 3,
        min_improvement: float = 5.0,
        score_tolerance: float = 2.0
    ):
        """
        Initialize iterative refinement system

        Args:
            evaluator: Continuity evaluator instance
            llm_client: LLM client for generating refinements
            strategy: Refinement strategy to use
            threshold: Acceptance threshold (0-100)
            max_iterations: Maximum refinement iterations
            min_improvement: Minimum improvement per iteration to continue
            score_tolerance: Acceptable score variance for early stopping
        """
        self.evaluator = evaluator
        self.llm_client = llm_client
        self.strategy = strategy
        self.threshold = threshold
        self.max_iterations = max_iterations
        self.min_improvement = min_improvement
        self.score_tolerance = score_tolerance

        # Callbacks for progress tracking
        self._on_iteration: Optional[Callable] = None
        self._on_accept: Optional[Callable] = None
        self._on_reject: Optional[Callable] = None

    def refine(
        self,
        content: str,
        context: str,
        memory_context: Optional[Dict] = None,
        custom_criteria: Optional[List[str]] = None
    ) -> RefinementResult:
        """
        Iteratively refine content until it meets quality criteria

        Args:
            content: Content to refine
            context: Previous context for evaluation
            memory_context: Memory system context
            custom_criteria: Additional quality criteria

        Returns:
            RefinementResult with refinement details
        """
        steps: List[RefinementStep] = []
        current_content = content

        # Initial evaluation
        initial_score, initial_issues = self._evaluate(
            context, current_content, memory_context
        )

        # Check if already acceptable
        if initial_score >= self.threshold:
            return RefinementResult(
                original_content=content,
                final_content=content,
                status=RefinementStatus.ACCEPTED,
                steps=[RefinementStep(
                    iteration=0,
                    score=initial_score,
                    issues=initial_issues,
                    changes_made="No changes needed"
                )],
                initial_score=initial_score,
                final_score=initial_score,
                improvement=0.0
            )

        # Track scores for convergence detection
        current_score = initial_score
        # 在循环外初始化，避免 iteration 1 走 regression/continue 分支时
        # 第 2 轮引用未赋值的 current_issues 导致 UnboundLocalError。
        current_issues = initial_issues
        # 直接跟踪"最佳版本"的正文与分数，避免 score_history 与 steps
        # 因 regression 分支错位导致的索引错误。
        best_content = current_content
        best_score = initial_score

        # Refinement loop
        for iteration in range(1, self.max_iterations + 1):
            # Generate refinement
            refined_content, changes = self._generate_refinement(
                context=context,
                content=current_content,
                issues=initial_issues if iteration == 1 else current_issues,
                memory_context=memory_context,
                custom_criteria=custom_criteria,
                iteration=iteration
            )

            # Evaluate refined content
            new_score, new_issues = self._evaluate(
                context, refined_content, memory_context
            )

            # Record step（保存实际正文，便于回溯最佳版本）
            step = RefinementStep(
                iteration=iteration,
                score=new_score,
                issues=new_issues,
                changes_made=changes,
                content=refined_content
            )
            steps.append(step)

            # 跟踪迄今为止的最佳版本
            if new_score > best_score:
                best_score = new_score
                best_content = refined_content

            # Progress callback
            if self._on_iteration:
                self._on_iteration(step)

            # Check for improvement
            improvement = new_score - current_score

            if new_score >= self.threshold:
                # Acceptance criteria met
                if self._on_accept:
                    self._on_accept(refined_content, new_score)
                return RefinementResult(
                    original_content=content,
                    final_content=refined_content,
                    status=RefinementStatus.REFINED,
                    steps=steps,
                    initial_score=initial_score,
                    final_score=new_score,
                    improvement=new_score - initial_score
                )

            # Check for stagnation
            if improvement < self.min_improvement and iteration > 1:
                # Not improving enough, use best version
                break

            # Check for score regression
            if new_score < current_score - self.score_tolerance:
                # Regression detected, revert
                continue

            # Update for next iteration
            current_content = refined_content
            current_score = new_score
            current_issues = new_issues

        # Max iterations reached or stagnation：直接使用跟踪到的最佳正文，
        # （best_content 默认为原始 content，best_score 默认为 initial_score）
        final_content = best_content

        status = RefinementStatus.TIMEOUT if len(steps) >= self.max_iterations else RefinementStatus.FAILED

        if self._on_reject:
            self._on_reject(final_content, best_score)

        return RefinementResult(
            original_content=content,
            final_content=final_content,
            status=status,
            steps=steps,
            initial_score=initial_score,
            final_score=best_score,
            improvement=best_score - initial_score
        )

    def _evaluate(
        self,
        context: str,
        content: str,
        memory_context: Optional[Dict]
    ) -> Tuple[float, List[Dict]]:
        """Evaluate content and return score with issues"""
        if self.evaluator:
            result = self.evaluator.evaluate(context, content, memory_context)
            issues = [i.to_dict() for i in result.issues]
            return result.overall_score * 100, issues

        # Fallback: simple heuristic scoring
        score = self._heuristic_score(context, content)
        return score, []

    def _heuristic_score(self, context: str, content: str) -> float:
        """Simple heuristic scoring without LLM"""
        # Length check
        if len(content) < 100:
            return 50.0

        # Basic coherence indicators
        score = 70.0

        # Check for abrupt endings
        if not content.rstrip().endswith(('。', '！', '？', '.', '!', '?')):
            score -= 10

        # Check for reasonable length relative to context
        if len(content) > 5000:
            score += 5  # Longer content often more coherent

        return min(100.0, max(0.0, score))

    def _generate_refinement(
        self,
        context: str,
        content: str,
        issues: List[Dict],
        memory_context: Optional[Dict],
        custom_criteria: Optional[List[str]],
        iteration: int
    ) -> Tuple[str, str]:
        """
        Generate refined content based on issues

        Returns:
            Tuple of (refined_content, changes_description)
        """
        if not self.llm_client:
            return content, "No LLM client available"

        # Determine strategy
        strategy = self._select_strategy(issues, iteration)

        if strategy == RefinementStrategy.FULL_REWRITE:
            return self._full_rewrite(context, content, issues, memory_context)
        elif strategy == RefinementStrategy.TARGETED_FIX:
            return self._targeted_fix(context, content, issues, memory_context)
        elif strategy == RefinementStrategy.INCREMENTAL:
            return self._incremental_fix(context, content, issues, memory_context)
        else:  # HYBRID
            return self._hybrid_fix(context, content, issues, memory_context, iteration)

    def _select_strategy(
        self,
        issues: List[Dict],
        iteration: int
    ) -> RefinementStrategy:
        """Select refinement strategy based on issues and iteration"""
        if self.strategy != RefinementStrategy.HYBRID:
            return self.strategy

        # Hybrid strategy selection
        critical_count = sum(1 for i in issues if i.get("severity") == "critical")
        major_count = sum(1 for i in issues if i.get("severity") == "major")

        if critical_count >= 2 or iteration == 1:
            return RefinementStrategy.FULL_REWRITE
        elif major_count >= 2:
            return RefinementStrategy.TARGETED_FIX
        else:
            return RefinementStrategy.INCREMENTAL

    def _full_rewrite(
        self,
        context: str,
        content: str,
        issues: List[Dict],
        memory_context: Optional[Dict]
    ) -> Tuple[str, str]:
        """Full content rewrite"""
        issues_text = self._format_issues(issues)

        prompt = f"""请重写以下章节，解决检测到的问题：

## 前文上下文
{context[-1000:]}

## 原章节
{content}

## 需要解决的问题
{issues_text}

## 重写要求
1. 保持原有的叙事风格和核心情节
2. 解决所有标注的问题
3. 确保与前文自然衔接
4. 保持相近的字数

请输出重写后的完整章节："""

        refined = self.llm_client.generate(prompt)
        return refined or content, "Full rewrite performed"

    def _targeted_fix(
        self,
        context: str,
        content: str,
        issues: List[Dict],
        memory_context: Optional[Dict]
    ) -> Tuple[str, str]:
        """Targeted fix for specific issues"""
        # Filter to major/critical issues
        target_issues = [i for i in issues if i.get("severity") in ("critical", "major")]
        issues_text = self._format_issues(target_issues)

        prompt = f"""请修复以下章节中的特定问题，尽量保持其他内容不变：

## 原章节
{content}

## 需要修复的问题
{issues_text}

## 修复要求
1. 只修改与问题相关的部分
2. 保持原有的叙事风格
3. 不要大幅改动其他内容

请输出修复后的完整章节："""

        refined = self.llm_client.generate(prompt)
        changes = f"Fixed {len(target_issues)} targeted issues"
        return refined or content, changes

    def _incremental_fix(
        self,
        context: str,
        content: str,
        issues: List[Dict],
        memory_context: Optional[Dict]
    ) -> Tuple[str, str]:
        """Small incremental improvements"""
        # Take only the most important issue
        if not issues:
            return content, "No issues to fix"

        primary_issue = issues[0]
        issues_text = f"- {primary_issue.get('description', 'Unknown issue')}"
        suggestion = primary_issue.get('suggestion', '')

        prompt = f"""请对以下章节进行小幅改进：

## 原章节
{content[:1500]}...

## 需要改进的问题
{issues_text}

## 建议改进方向
{suggestion}

请输出改进后的章节开头部分（保持后续内容基本不变）："""

        refined_prefix = self.llm_client.generate(prompt)

        if refined_prefix:
            # Combine refined prefix with rest of content
            refined = refined_prefix + content[1500:]
            return refined, f"Incremental fix: {primary_issue.get('description', '')[:50]}"

        return content, "No changes made"

    def _hybrid_fix(
        self,
        context: str,
        content: str,
        issues: List[Dict],
        memory_context: Optional[Dict],
        iteration: int
    ) -> Tuple[str, str]:
        """Hybrid approach combining strategies"""
        # First iteration: targeted fix for major issues
        if iteration == 1:
            return self._targeted_fix(context, content, issues, memory_context)
        # Second iteration: incremental improvement
        elif iteration == 2:
            return self._incremental_fix(context, content, issues, memory_context)
        # Final iteration: full rewrite if still not meeting criteria
        else:
            return self._full_rewrite(context, content, issues, memory_context)

    def _format_issues(self, issues: List[Dict]) -> str:
        """Format issues for prompt"""
        if not issues:
            return "无特定问题"

        lines = []
        for i, issue in enumerate(issues, 1):
            severity = issue.get("severity", "unknown")
            desc = issue.get("description", "")
            suggestion = issue.get("suggestion", "")
            lines.append(f"{i}. [{severity}] {desc}")
            if suggestion:
                lines.append(f"   建议: {suggestion}")

        return "\n".join(lines)

    def set_callbacks(
        self,
        on_iteration: Optional[Callable] = None,
        on_accept: Optional[Callable] = None,
        on_reject: Optional[Callable] = None
    ):
        """Set callback functions for progress tracking"""
        self._on_iteration = on_iteration
        self._on_accept = on_accept
        self._on_reject = on_reject


class RefinementPipeline:
    """
    Multi-stage refinement pipeline

    Combines multiple refinement stages for comprehensive
    content optimization.
    """

    def __init__(self, stages: Optional[List[Dict]] = None):
        """
        Initialize pipeline with stages

        Args:
            stages: List of stage configurations
        """
        self.stages = stages or [
            {"name": "continuity", "threshold": 75.0, "max_iterations": 2},
            {"name": "quality", "threshold": 80.0, "max_iterations": 2},
            {"name": "polish", "threshold": 85.0, "max_iterations": 1}
        ]

        self._stage_results: List[Dict] = []

    def process(
        self,
        content: str,
        context: str,
        evaluator=None,
        llm_client=None
    ) -> Tuple[str, List[Dict]]:
        """
        Process content through all stages

        Returns:
            Tuple of (final_content, stage_results)
        """
        current_content = content
        self._stage_results = []

        for stage in self.stages:
            refiner = IterativeRefinement(
                evaluator=evaluator,
                llm_client=llm_client,
                threshold=stage["threshold"],
                max_iterations=stage.get("max_iterations", 2)
            )

            result = refiner.refine(current_content, context)

            self._stage_results.append({
                "stage": stage["name"],
                "result": result.to_dict()
            })

            current_content = result.final_content

        return current_content, self._stage_results
