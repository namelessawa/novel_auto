#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for EnhancedContinuityEvaluator
Tests for multi-dimensional continuity evaluation
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestContinuityDimension:
    """Tests for ContinuityDimension enum"""

    def test_all_dimensions_defined(self):
        """Test that all 8 dimensions are defined"""
        from evaluation.continuity_v2 import ContinuityDimension

        expected_dimensions = [
            "character", "plot", "setting", "theme",
            "style", "temporal", "relationship", "foreshadowing"
        ]

        for dim in expected_dimensions:
            assert ContinuityDimension(dim) is not None

    def test_dimension_values(self):
        """Test dimension values match expected strings"""
        from evaluation.continuity_v2 import ContinuityDimension

        assert ContinuityDimension.CHARACTER.value == "character"
        assert ContinuityDimension.PLOT.value == "plot"
        assert ContinuityDimension.FORESHADOWING.value == "foreshadowing"


class TestContinuityIssue:
    """Tests for ContinuityIssue dataclass"""

    def test_issue_creation(self):
        """Test creating a continuity issue"""
        from evaluation.continuity_v2 import ContinuityIssue, ContinuityDimension

        issue = ContinuityIssue(
            dimension=ContinuityDimension.CHARACTER,
            severity="major",
            description="Character behavior inconsistent",
            location="Chapter 5, paragraph 3",
            suggestion="Review character motivation",
            confidence=0.9
        )

        assert issue.dimension == ContinuityDimension.CHARACTER
        assert issue.severity == "major"
        assert issue.confidence == 0.9

    def test_issue_to_dict(self):
        """Test converting issue to dictionary"""
        from evaluation.continuity_v2 import ContinuityIssue, ContinuityDimension

        issue = ContinuityIssue(
            dimension=ContinuityDimension.PLOT,
            severity="critical",
            description="Plot hole detected",
            location="End of chapter",
            suggestion="Add foreshadowing",
            confidence=1.0
        )

        result = issue.to_dict()

        assert isinstance(result, dict)
        assert result['dimension'] == "plot"
        assert result['severity'] == "critical"


class TestContinuityScore:
    """Tests for ContinuityScore dataclass"""

    def test_score_creation(self):
        """Test creating a continuity score"""
        from evaluation.continuity_v2 import ContinuityScore

        score = ContinuityScore(
            overall_score=0.85,
            dimension_scores={"character": 0.9, "plot": 0.8},
            issues=[],
            strengths=["Good character development"]
        )

        assert score.overall_score == 0.85
        assert len(score.dimension_scores) == 2

    def test_score_to_dict(self):
        """Test converting score to dictionary"""
        from evaluation.continuity_v2 import ContinuityScore, ContinuityIssue, ContinuityDimension

        issues = [
            ContinuityIssue(
                dimension=ContinuityDimension.CHARACTER,
                severity="minor",
                description="Test issue",
                location="Test",
                suggestion="Test suggestion"
            )
        ]

        score = ContinuityScore(
            overall_score=0.75,
            dimension_scores={"character": 0.7, "plot": 0.8},
            issues=issues,
            strengths=["Good pacing"]
        )

        result = score.to_dict()

        assert isinstance(result, dict)
        assert 'overall_score' in result
        assert 'issues' in result
        assert len(result['issues']) == 1


class TestEnhancedContinuityEvaluator:
    """Tests for EnhancedContinuityEvaluator class"""

    def test_init_default_weights(self):
        """Test initialization with default weights"""
        from evaluation.continuity_v2 import EnhancedContinuityEvaluator, ContinuityDimension

        evaluator = EnhancedContinuityEvaluator()

        assert ContinuityDimension.CHARACTER in evaluator.weights
        assert ContinuityDimension.PLOT in evaluator.weights

    def test_init_custom_weights(self):
        """Test initialization with custom weights"""
        from evaluation.continuity_v2 import EnhancedContinuityEvaluator, ContinuityDimension

        custom_weights = {
            ContinuityDimension.CHARACTER: 0.3,
            ContinuityDimension.PLOT: 0.4,
            ContinuityDimension.SETTING: 0.1,
            ContinuityDimension.THEME: 0.1,
            ContinuityDimension.STYLE: 0.05,
            ContinuityDimension.TEMPORAL: 0.02,
            ContinuityDimension.RELATIONSHIP: 0.02,
            ContinuityDimension.FORESHADOWING: 0.01,
        }

        evaluator = EnhancedContinuityEvaluator(weights=custom_weights)

        assert evaluator.weights[ContinuityDimension.CHARACTER] == 0.3

    def test_evaluate_without_llm(self, sample_chapter, sample_chapter_2):
        """Test heuristic evaluation without LLM"""
        from evaluation.continuity_v2 import EnhancedContinuityEvaluator

        evaluator = EnhancedContinuityEvaluator(llm_client=None)

        score = evaluator.evaluate(
            previous_context=sample_chapter,
            new_content=sample_chapter_2
        )

        assert score.overall_score >= 0
        assert score.overall_score <= 1
        assert 'method' in score.metadata
        assert score.metadata['method'] == 'heuristic'

    def test_evaluate_with_memory_context(self, sample_chapter, sample_chapter_2):
        """Test evaluation with memory context"""
        from evaluation.continuity_v2 import EnhancedContinuityEvaluator

        evaluator = EnhancedContinuityEvaluator(llm_client=None)

        memory_context = {
            "characters": {"李明": {"state": "忧虑"}},
            "relationships": {"李明-王芳": "朋友"}
        }

        score = evaluator.evaluate(
            previous_context=sample_chapter,
            new_content=sample_chapter_2,
            memory_context=memory_context
        )

        assert score is not None

    def test_caching(self, sample_chapter, sample_chapter_2):
        """Test that evaluation results are cached"""
        from evaluation.continuity_v2 import EnhancedContinuityEvaluator

        evaluator = EnhancedContinuityEvaluator(llm_client=None)

        # First evaluation
        score1 = evaluator.evaluate(sample_chapter, sample_chapter_2)

        # Second evaluation with same input should return cached result
        score2 = evaluator.evaluate(sample_chapter, sample_chapter_2)

        # Should be same object due to caching
        assert score1 is score2

    def test_get_critical_issues(self):
        """Test filtering critical issues"""
        from evaluation.continuity_v2 import (
            EnhancedContinuityEvaluator,
            ContinuityScore,
            ContinuityIssue,
            ContinuityDimension
        )

        evaluator = EnhancedContinuityEvaluator()

        issues = [
            ContinuityIssue(
                dimension=ContinuityDimension.CHARACTER,
                severity="critical",
                description="Critical issue",
                location="Test",
                suggestion="Fix it"
            ),
            ContinuityIssue(
                dimension=ContinuityDimension.PLOT,
                severity="major",
                description="Major issue",
                location="Test",
                suggestion="Fix it"
            ),
            ContinuityIssue(
                dimension=ContinuityDimension.SETTING,
                severity="minor",
                description="Minor issue",
                location="Test",
                suggestion="Fix it"
            )
        ]

        score = ContinuityScore(
            overall_score=0.5,
            dimension_scores={},
            issues=issues,
            strengths=[]
        )

        critical = evaluator.get_critical_issues(score)

        assert len(critical) == 2  # critical and major
        assert all(i.severity in ("critical", "major") for i in critical)


class TestHeuristicEvaluation:
    """Tests for heuristic evaluation methods"""

    def test_character_consistency_detection(self, sample_chapter):
        """Test character consistency checking"""
        from evaluation.continuity_v2 import EnhancedContinuityEvaluator

        evaluator = EnhancedContinuityEvaluator()

        # Same characters - high consistency
        score1 = evaluator._check_character_consistency(
            sample_chapter,
            "李明和王芳在图书馆交谈。"
        )

        # Completely different characters - lower consistency
        score2 = evaluator._check_character_consistency(
            sample_chapter,
            "张三和李四在公园散步。"
        )

        assert score1 >= score2

    def test_setting_consistency_detection(self, sample_chapter):
        """Test setting consistency checking"""
        from evaluation.continuity_v2 import EnhancedContinuityEvaluator

        evaluator = EnhancedContinuityEvaluator()

        # Same setting
        score1 = evaluator._check_setting_consistency(
            sample_chapter,
            "他们在图书馆里继续交谈。"
        )

        # Different setting
        score2 = evaluator._check_setting_consistency(
            sample_chapter,
            "他们离开了图书馆，来到了公园。"
        )

        # Both should return valid scores
        assert 0 <= score1 <= 1
        assert 0 <= score2 <= 1

    def test_temporal_consistency_detection(self, sample_chapter):
        """Test temporal consistency checking"""
        from evaluation.continuity_v2 import EnhancedContinuityEvaluator

        evaluator = EnhancedContinuityEvaluator()

        score = evaluator._check_temporal_consistency(
            sample_chapter,
            "今天天气不错。"
        )

        assert 0 <= score <= 1


class TestContinuityEvaluatorAdapter:
    """Tests for backward compatibility adapter"""

    def test_adapter_interface(self):
        """Test that adapter provides legacy interface"""
        from evaluation.continuity_v2 import ContinuityEvaluatorAdapter

        # Create mock LLM client
        mock_llm_client = Mock()
        mock_llm_client.model_name = "test_model"

        # Create adapter with mock
        adapter = ContinuityEvaluatorAdapter.__new__(ContinuityEvaluatorAdapter)
        adapter.llm_client = mock_llm_client
        adapter.enhanced_evaluator = Mock()

        assert hasattr(adapter, 'evaluate_continuity')
        assert hasattr(adapter, 'enhanced_evaluator')

    def test_adapter_returns_legacy_format(self, sample_chapter, sample_chapter_2):
        """Test that adapter returns legacy format"""
        from evaluation.continuity_v2 import ContinuityEvaluatorAdapter, ContinuityScore

        # Create mock adapter
        adapter = ContinuityEvaluatorAdapter.__new__(ContinuityEvaluatorAdapter)
        adapter.llm_client = Mock()
        adapter.enhanced_evaluator = Mock()

        # Mock the enhanced evaluator evaluate method
        adapter.enhanced_evaluator.evaluate.return_value = ContinuityScore(
            overall_score=0.85,
            dimension_scores={
                'character': 0.9,
                'plot': 0.8,
                'setting': 0.85,
                'theme': 0.9,
                'style': 0.8
            },
            issues=[],
            strengths=[]
        )

        score, breakdown = adapter.evaluate_continuity(
            sample_chapter,
            sample_chapter_2
        )

        # Should return 0-100 scale
        assert 0 <= score <= 100
        assert isinstance(breakdown, dict)
        assert 'character_continuity' in breakdown


class TestFixPromptGeneration:
    """Tests for fix prompt generation"""

    def test_generate_fix_prompt(self):
        """Test generating fix prompt from issues"""
        from evaluation.continuity_v2 import (
            EnhancedContinuityEvaluator,
            ContinuityScore,
            ContinuityIssue,
            ContinuityDimension
        )

        evaluator = EnhancedContinuityEvaluator()

        issues = [
            ContinuityIssue(
                dimension=ContinuityDimension.CHARACTER,
                severity="major",
                description="Character acts out of character",
                location="Chapter 5",
                suggestion="Add motivation for behavior change"
            )
        ]

        score = ContinuityScore(
            overall_score=0.6,
            dimension_scores={},
            issues=issues,
            strengths=[]
        )

        prompt = evaluator.generate_fix_prompt(score, "Test chapter content")

        assert isinstance(prompt, str)
        assert "修改要求" in prompt
        assert "检测到的问题" in prompt
