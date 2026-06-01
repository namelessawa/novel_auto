#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Procedural Memory Module
Learned patterns for style, narrative techniques, and generation procedures

Inspired by cognitive science procedural memory:
- "How to" knowledge (skills, procedures)
- Pattern recognition and application
- Style templates and techniques
- Genre-specific conventions

Key Features:
1. Style Pattern Extraction - Analyze text for reusable patterns
2. Narrative Technique Templates - Common storytelling structures
3. Few-Shot Style Adaptation - Learn style from examples
4. Genre-Specific Patterns - Conventions by genre
"""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
from collections import Counter
import hashlib


@dataclass
class StylePattern:
    """
    A reusable style pattern

    Patterns capture:
    - Sentence structures
    - Dialogue formatting
    - Description techniques
    - Narrative voice patterns
    """
    id: str
    pattern_type: str  # "sentence", "dialogue", "description", "narration", "transition"
    name: str
    template: str  # Template with placeholders
    example: str  # Example usage
    genre_tags: List[str] = field(default_factory=list)
    usage_count: int = 0
    effectiveness_score: float = 0.5  # How well it works
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "name": self.name,
            "template": self.template,
            "example": self.example,
            "genre_tags": self.genre_tags,
            "usage_count": self.usage_count,
            "effectiveness_score": self.effectiveness_score,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'StylePattern':
        return cls(
            id=data["id"],
            pattern_type=data["pattern_type"],
            name=data["name"],
            template=data["template"],
            example=data["example"],
            genre_tags=data.get("genre_tags", []),
            usage_count=data.get("usage_count", 0),
            effectiveness_score=data.get("effectiveness_score", 0.5),
            metadata=data.get("metadata", {})
        )


@dataclass
class NarrativeTechnique:
    """
    A narrative technique (storytelling method)

    Techniques include:
    - Show don't tell
    - Foreshadowing
    - Chekhov's gun
    - Red herring
    - Dramatic irony
    """
    id: str
    name: str
    category: str  # "pacing", "revelation", "tension", "character", "theme"
    description: str
    implementation_guide: str
    prerequisites: List[str] = field(default_factory=list)
    effects: List[str] = field(default_factory=list)
    genre_affinity: List[str] = field(default_factory=list)
    usage_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "implementation_guide": self.implementation_guide,
            "prerequisites": self.prerequisites,
            "effects": self.effects,
            "genre_affinity": self.genre_affinity,
            "usage_count": self.usage_count,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'NarrativeTechnique':
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            description=data["description"],
            implementation_guide=data["implementation_guide"],
            prerequisites=data.get("prerequisites", []),
            effects=data.get("effects", []),
            genre_affinity=data.get("genre_affinity", []),
            usage_count=data.get("usage_count", 0),
            metadata=data.get("metadata", {})
        )


@dataclass
class StyleProfile:
    """
    A profile of a particular writing style

    Captures:
    - Sentence length preferences
    - Dialogue frequency
    - Description density
    - Vocabulary patterns
    """
    name: str
    sentence_length_avg: float = 20.0
    sentence_length_variance: float = 5.0
    dialogue_ratio: float = 0.3  # Ratio of dialogue to narrative
    description_density: float = 0.4  # How much description
    vocabulary_complexity: float = 0.5  # 0=simple, 1=complex
    emotional_intensity: float = 0.5  # Average emotional intensity
    pacing: float = 0.5  # 0=slow, 1=fast
    characteristic_patterns: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "sentence_length_avg": self.sentence_length_avg,
            "sentence_length_variance": self.sentence_length_variance,
            "dialogue_ratio": self.dialogue_ratio,
            "description_density": self.description_density,
            "vocabulary_complexity": self.vocabulary_complexity,
            "emotional_intensity": self.emotional_intensity,
            "pacing": self.pacing,
            "characteristic_patterns": self.characteristic_patterns
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'StyleProfile':
        return cls(
            name=data["name"],
            sentence_length_avg=data.get("sentence_length_avg", 20.0),
            sentence_length_variance=data.get("sentence_length_variance", 5.0),
            dialogue_ratio=data.get("dialogue_ratio", 0.3),
            description_density=data.get("description_density", 0.4),
            vocabulary_complexity=data.get("vocabulary_complexity", 0.5),
            emotional_intensity=data.get("emotional_intensity", 0.5),
            pacing=data.get("pacing", 0.5),
            characteristic_patterns=data.get("characteristic_patterns", [])
        )


class ProceduralMemory:
    """
    Procedural Memory for Style and Techniques

    Features:
    - Style pattern extraction from text
    - Narrative technique templates
    - Few-shot style adaptation
    - Genre-specific patterns

    TTL: Permanent (fine-tuned over time)
    """

    # Default style profiles
    DEFAULT_STYLES = {
        "classical": StyleProfile(
            name="classical",
            sentence_length_avg=30.0,
            dialogue_ratio=0.25,
            description_density=0.5,
            vocabulary_complexity=0.7,
            emotional_intensity=0.4,
            pacing=0.3
        ),
        "modern": StyleProfile(
            name="modern",
            sentence_length_avg=15.0,
            dialogue_ratio=0.4,
            description_density=0.3,
            vocabulary_complexity=0.4,
            emotional_intensity=0.6,
            pacing=0.6
        ),
        "literary": StyleProfile(
            name="literary",
            sentence_length_avg=25.0,
            dialogue_ratio=0.2,
            description_density=0.6,
            vocabulary_complexity=0.8,
            emotional_intensity=0.5,
            pacing=0.2
        ),
        "action": StyleProfile(
            name="action",
            sentence_length_avg=10.0,
            dialogue_ratio=0.3,
            description_density=0.2,
            vocabulary_complexity=0.3,
            emotional_intensity=0.8,
            pacing=0.9
        ),
        "romantic": StyleProfile(
            name="romantic",
            sentence_length_avg=20.0,
            dialogue_ratio=0.45,
            description_density=0.35,
            vocabulary_complexity=0.5,
            emotional_intensity=0.7,
            pacing=0.4
        )
    }

    def __init__(self, memory_dir: str = "memory_system"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Style patterns
        self._patterns: Dict[str, StylePattern] = {}
        self._patterns_by_type: Dict[str, List[str]] = {}

        # Narrative techniques
        self._techniques: Dict[str, NarrativeTechnique] = {}
        self._techniques_by_category: Dict[str, List[str]] = {}

        # Style profiles
        self._style_profiles: Dict[str, StyleProfile] = dict(self.DEFAULT_STYLES)
        self._current_style: Optional[str] = None

        # Learned patterns from analysis
        self._learned_patterns: List[Dict] = []

        # ID counters
        self._pattern_counter = 0
        self._technique_counter = 0

        # Files
        self.patterns_file = self.memory_dir / "procedural_patterns.json"
        self.techniques_file = self.memory_dir / "procedural_techniques.json"
        self.styles_file = self.memory_dir / "procedural_styles.json"

        # Load from disk
        self.load_from_disk()

        # Initialize default techniques if empty
        if not self._techniques:
            self._init_default_techniques()

    def _init_default_techniques(self):
        """Initialize default narrative techniques"""
        default_techniques = [
            NarrativeTechnique(
                id="tech_001",
                name="Show Don't Tell",
                category="revelation",
                description="Show actions and emotions rather than stating them directly",
                implementation_guide="Instead of 'He was angry', describe clenched fists, reddening face, harsh tone",
                effects=["immersion", "engagement"],
                genre_affinity=["literary", "action", "romantic"]
            ),
            NarrativeTechnique(
                id="tech_002",
                name="Foreshadowing",
                category="tension",
                description="Plant hints about future events",
                implementation_guide="Introduce objects, phrases, or minor events that will become significant later",
                effects=["anticipation", "satisfaction"],
                genre_affinity=["mystery", "thriller", "fantasy"]
            ),
            NarrativeTechnique(
                id="tech_003",
                name="Chekhov's Gun",
                category="pacing",
                description="Every element should serve a purpose",
                implementation_guide="If you mention a gun in act one, it must fire by act three. Remove irrelevant details.",
                effects=["coherence", "economy"],
                genre_affinity=["drama", "thriller", "mystery"]
            ),
            NarrativeTechnique(
                id="tech_004",
                name="Dramatic Irony",
                category="tension",
                description="Reader knows something character doesn't",
                implementation_guide="Reveal information to reader while keeping character ignorant, creating tension",
                effects=["tension", "engagement"],
                genre_affinity=["drama", "thriller", "comedy"]
            ),
            NarrativeTechnique(
                id="tech_005",
                name="Pacing Contrast",
                category="pacing",
                description="Alternate fast and slow scenes",
                implementation_guide="Follow action scenes with quieter moments. Balance tension with relief.",
                effects=["rhythm", "engagement"],
                genre_affinity=["action", "thriller", "adventure"]
            ),
            NarrativeTechnique(
                id="tech_006",
                name="Character Voice",
                category="character",
                description="Distinct dialogue patterns for each character",
                implementation_guide="Each character should have unique vocabulary, sentence structure, and speech patterns",
                effects=["distinctiveness", "authenticity"],
                genre_affinity=["literary", "romantic", "drama"]
            ),
            NarrativeTechnique(
                id="tech_007",
                name="Sensory Detail",
                category="revelation",
                description="Engage multiple senses in descriptions",
                implementation_guide="Don't just describe visually. Include sounds, smells, textures, tastes.",
                effects=["immersion", "vividness"],
                genre_affinity=["literary", "fantasy", "horror"]
            ),
            NarrativeTechnique(
                id="tech_008",
                name="Cliffhanger",
                category="tension",
                description="End sections with unresolved tension",
                implementation_guide="Create questions, danger, or revelations that demand resolution",
                effects=["anticipation", "retention"],
                genre_affinity=["thriller", "serial", "adventure"]
            )
        ]

        for tech in default_techniques:
            self._techniques[tech.id] = tech
            if tech.category not in self._techniques_by_category:
                self._techniques_by_category[tech.category] = []
            self._techniques_by_category[tech.category].append(tech.id)

        self._technique_counter = len(default_techniques)
        self.save_to_disk()

    def extract_pattern(self, text: str, context: Dict = None) -> Optional[StylePattern]:
        """
        Extract reusable pattern from text

        Args:
            text: Text to analyze
            context: Optional context (genre, author, etc.)

        Returns:
            Extracted StylePattern or None
        """
        # Sentence patterns
        sentences = re.split(r'[。！？.!?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return None

        # Analyze patterns
        patterns_found = []

        # Dialogue pattern
        dialogue_matches = re.findall(r'[""「」『』](.+?)[""「」『』]', text)
        if dialogue_matches:
            patterns_found.append({
                "type": "dialogue",
                "pattern": "「{dialogue}」",
                "examples": dialogue_matches[:3]
            })

        # Description pattern (long sentences without dialogue)
        long_sentences = [s for s in sentences if len(s) > 30 and '「' not in s]
        if long_sentences:
            patterns_found.append({
                "type": "description",
                "pattern": "{descriptive_sentence}",
                "examples": long_sentences[:3]
            })

        # Transition pattern
        transitions = [
            "然而", "但是", "不过", "于是", "因此", "之后",
            "Meanwhile", "However", "Therefore", "Later"
        ]
        for trans in transitions:
            if trans in text:
                trans_sentences = [s for s in sentences if trans in s]
                if trans_sentences:
                    patterns_found.append({
                        "type": "transition",
                        "pattern": f"{trans}，{{continuation}}",
                        "examples": trans_sentences[:2]
                    })

        # Create pattern object (just return first found for now)
        if patterns_found:
            p = patterns_found[0]
            self._pattern_counter += 1

            pattern = StylePattern(
                id=f"pat_{self._pattern_counter:04d}",
                pattern_type=p["type"],
                name=f"{p['type']}_pattern_{self._pattern_counter}",
                template=p["pattern"],
                example=p["examples"][0] if p["examples"] else "",
                genre_tags=context.get("genres", []) if context else []
            )

            self._patterns[pattern.id] = pattern
            if pattern.pattern_type not in self._patterns_by_type:
                self._patterns_by_type[pattern.pattern_type] = []
            self._patterns_by_type[pattern.pattern_type].append(pattern.id)

            self.save_to_disk()
            return pattern

        return None

    def analyze_style(self, text: str) -> StyleProfile:
        """
        Analyze text to extract style profile

        Args:
            text: Text to analyze

        Returns:
            StyleProfile with measured characteristics
        """
        # Sentence analysis
        sentences = re.split(r'[。！？.!?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return StyleProfile(name="analyzed")

        # Calculate metrics
        sentence_lengths = [len(s) for s in sentences]
        avg_length = sum(sentence_lengths) / len(sentence_lengths)
        variance = sum((l - avg_length) ** 2 for l in sentence_lengths) / len(sentence_lengths)

        # Dialogue ratio
        dialogue_chars = len(re.findall(r'[""「」『』].+?[""「」『』]', text))
        total_chars = len(text)
        dialogue_ratio = dialogue_chars / total_chars if total_chars > 0 else 0

        # Description density (long non-dialogue sentences)
        long_narrative = [s for s in sentences if len(s) > 20 and '「' not in s]
        description_density = len(long_narrative) / len(sentences) if sentences else 0

        # Vocabulary complexity (unique characters ratio)
        unique_chars = len(set(text))
        vocab_complexity = unique_chars / len(text) if text else 0.5

        # Emotional intensity (based on emotion words)
        emotion_words = ["激动", "愤怒", "悲伤", "喜悦", "恐惧", "惊讶", "爱", "恨"]
        emotion_count = sum(text.count(w) for w in emotion_words)
        emotional_intensity = min(1.0, emotion_count / (len(text) / 100))

        # Pacing (inverse of average sentence length, normalized)
        pacing = min(1.0, 30 / avg_length) if avg_length > 0 else 0.5

        return StyleProfile(
            name="analyzed",
            sentence_length_avg=avg_length,
            sentence_length_variance=variance ** 0.5,
            dialogue_ratio=dialogue_ratio,
            description_density=description_density,
            vocabulary_complexity=vocab_complexity,
            emotional_intensity=emotional_intensity,
            pacing=pacing
        )

    def apply_style(self, content: str, style_name: str) -> str:
        """
        Apply style profile to content

        Args:
            content: Original content
            style_name: Style profile to apply

        Returns:
            Styled content (in practice, would return prompts/guidance)
        """
        profile = self._style_profiles.get(style_name)
        if not profile:
            return content

        # In practice, this would guide the generation
        # For now, return style guidance
        return content  # Placeholder

    def get_style_guidance(self, style_name: str) -> str:
        """Get text guidance for a style profile"""
        profile = self._style_profiles.get(style_name)
        if not profile:
            return ""

        guidance_parts = [
            f"写作风格指导 ({profile.name}):",
            f"- 句子平均长度: {profile.sentence_length_avg:.0f}字",
            f"- 对话比例: {profile.dialogue_ratio*100:.0f}%",
            f"- 描写密度: {profile.description_density*100:.0f}%",
            f"- 词汇复杂度: {'高' if profile.vocabulary_complexity > 0.6 else '中' if profile.vocabulary_complexity > 0.4 else '低'}",
            f"- 情感强度: {'强烈' if profile.emotional_intensity > 0.6 else '适中' if profile.emotional_intensity > 0.4 else '温和'}",
            f"- 节奏: {'快' if profile.pacing > 0.6 else '中' if profile.pacing > 0.4 else '慢'}"
        ]

        return "\n".join(guidance_parts)

    def suggest_technique(self, context: Dict) -> List[NarrativeTechnique]:
        """
        Suggest narrative techniques based on context

        Args:
            context: Context dict with 'genre', 'scene_type', 'current_techniques', etc.

        Returns:
            List of suggested techniques
        """
        suggestions = []

        genre = context.get("genre", "")
        scene_type = context.get("scene_type", "")
        current = context.get("current_techniques", [])

        for tech in self._techniques.values():
            if tech.id in current:
                continue

            # Score based on genre affinity
            score = 0
            if genre in tech.genre_affinity:
                score += 2

            # Score based on category relevance
            if scene_type == "action" and tech.category in ["pacing", "tension"]:
                score += 1
            elif scene_type == "dialogue" and tech.category == "character":
                score += 1
            elif scene_type == "description" and tech.category in ["revelation"]:
                score += 1

            if score > 0:
                suggestions.append((score, tech))

        # Sort by score
        suggestions.sort(key=lambda x: x[0], reverse=True)
        return [tech for score, tech in suggestions[:5]]

    def get_techniques_by_category(self, category: str) -> List[NarrativeTechnique]:
        """Get all techniques in a category"""
        tech_ids = self._techniques_by_category.get(category, [])
        return [self._techniques[tid] for tid in tech_ids if tid in self._techniques]

    def get_patterns_by_type(self, pattern_type: str) -> List[StylePattern]:
        """Get all patterns of a type"""
        pattern_ids = self._patterns_by_type.get(pattern_type, [])
        return [self._patterns[pid] for pid in pattern_ids if pid in self._patterns]

    def set_current_style(self, style_name: str) -> bool:
        """Set the current writing style"""
        if style_name in self._style_profiles:
            self._current_style = style_name
            return True
        return False

    def get_current_style(self) -> Optional[StyleProfile]:
        """Get current style profile"""
        if self._current_style:
            return self._style_profiles.get(self._current_style)
        return None

    def add_custom_style(self, profile: StyleProfile):
        """Add a custom style profile"""
        self._style_profiles[profile.name] = profile
        self.save_to_disk()

    def record_technique_usage(self, technique_id: str):
        """Record that a technique was used"""
        if technique_id in self._techniques:
            self._techniques[technique_id].usage_count += 1
            self.save_to_disk()

    def record_pattern_usage(self, pattern_id: str, effective: bool = True):
        """Record pattern usage and effectiveness"""
        if pattern_id in self._patterns:
            pattern = self._patterns[pattern_id]
            pattern.usage_count += 1
            # Update effectiveness score (exponential moving average)
            if effective:
                pattern.effectiveness_score = pattern.effectiveness_score * 0.9 + 0.1
            else:
                pattern.effectiveness_score = pattern.effectiveness_score * 0.9
            self.save_to_disk()

    def clear(self):
        """Clear all procedural memory"""
        self._patterns.clear()
        self._patterns_by_type.clear()
        self._techniques.clear()
        self._techniques_by_category.clear()
        self._style_profiles = dict(self.DEFAULT_STYLES)
        self._learned_patterns.clear()
        self._pattern_counter = 0
        self._technique_counter = 0
        self._init_default_techniques()
        self.save_to_disk()

    def save_to_disk(self):
        """Save procedural memory to disk"""
        try:
            # Save patterns
            patterns_data = {
                "patterns": [p.to_dict() for p in self._patterns.values()],
                "pattern_counter": self._pattern_counter
            }
            with open(self.patterns_file, 'w', encoding='utf-8') as f:
                json.dump(patterns_data, f, ensure_ascii=False, indent=2)

            # Save techniques
            techniques_data = {
                "techniques": [t.to_dict() for t in self._techniques.values()],
                "technique_counter": self._technique_counter
            }
            with open(self.techniques_file, 'w', encoding='utf-8') as f:
                json.dump(techniques_data, f, ensure_ascii=False, indent=2)

            # Save styles
            styles_data = {
                "styles": {name: p.to_dict() for name, p in self._style_profiles.items()},
                "current_style": self._current_style
            }
            with open(self.styles_file, 'w', encoding='utf-8') as f:
                json.dump(styles_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"保存程序记忆失败: {e}")

    def load_from_disk(self):
        """Load procedural memory from disk"""
        # Load patterns
        if self.patterns_file.exists():
            try:
                with open(self.patterns_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for pattern_data in data.get("patterns", []):
                    pattern = StylePattern.from_dict(pattern_data)
                    self._patterns[pattern.id] = pattern
                    if pattern.pattern_type not in self._patterns_by_type:
                        self._patterns_by_type[pattern.pattern_type] = []
                    self._patterns_by_type[pattern.pattern_type].append(pattern.id)

                self._pattern_counter = data.get("pattern_counter", 0)

            except Exception as e:
                print(f"加载模式失败: {e}")

        # Load techniques
        if self.techniques_file.exists():
            try:
                with open(self.techniques_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for tech_data in data.get("techniques", []):
                    tech = NarrativeTechnique.from_dict(tech_data)
                    self._techniques[tech.id] = tech
                    if tech.category not in self._techniques_by_category:
                        self._techniques_by_category[tech.category] = []
                    self._techniques_by_category[tech.category].append(tech.id)

                self._technique_counter = data.get("technique_counter", 0)

            except Exception as e:
                print(f"加载技巧失败: {e}")

        # Load styles
        if self.styles_file.exists():
            try:
                with open(self.styles_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for name, profile_data in data.get("styles", {}).items():
                    self._style_profiles[name] = StyleProfile.from_dict(profile_data)

                self._current_style = data.get("current_style")

            except Exception as e:
                print(f"加载风格失败: {e}")

    def to_text_description(self) -> str:
        """Convert to text description for prompts"""
        parts = ["[程序记忆 - 写作技巧]:"]

        # Current style
        current = self.get_current_style()
        if current:
            parts.append(f"\n当前风格: {current.name}")
            parts.append(self.get_style_guidance(current.name))

        # Available techniques
        parts.append("\n可用叙事技巧:")
        for tech in list(self._techniques.values())[:5]:
            parts.append(f"- {tech.name}: {tech.description}")

        # Learned patterns
        if self._patterns:
            parts.append(f"\n已学习模式: {len(self._patterns)}个")

        return "\n".join(parts)

    def get_stats(self) -> Dict:
        """Get statistics about procedural memory"""
        return {
            "pattern_count": len(self._patterns),
            "technique_count": len(self._techniques),
            "style_count": len(self._style_profiles),
            "current_style": self._current_style,
            "pattern_types": {
                t: len(ids) for t, ids in self._patterns_by_type.items()
            },
            "technique_categories": {
                c: len(ids) for c, ids in self._techniques_by_category.items()
            }
        }


# Test
if __name__ == "__main__":
    pm = ProceduralMemory()

    # Test style analysis
    sample_text = """
    李明走进房间，看到了王芳。她正坐在窗边看书，阳光洒在她的脸上。
    「你来了？」王芳抬起头，微笑着问道。
    「是的，我来了。」李明回答，心中涌起一阵莫名的感动。
    然而，他知道，这次见面可能会改变一切。
    """

    profile = pm.analyze_style(sample_text)
    print("Analyzed style profile:")
    print(f"  Average sentence length: {profile.sentence_length_avg:.1f}")
    print(f"  Dialogue ratio: {profile.dialogue_ratio*100:.1f}%")
    print(f"  Pacing: {profile.pacing:.2f}")
    print()

    # Test technique suggestion
    print("Suggested techniques for romantic dialogue:")
    suggestions = pm.suggest_technique({
        "genre": "romantic",
        "scene_type": "dialogue"
    })
    for tech in suggestions[:3]:
        print(f"  - {tech.name}")
    print()

    # Test style guidance
    print(pm.get_style_guidance("romantic"))
