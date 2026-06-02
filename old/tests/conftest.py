"""
Test configuration and fixtures
"""
import os
import sys
import pytest
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def temp_memory_dir(tmp_path):
    """Create a temporary directory for memory files"""
    memory_dir = tmp_path / "test_memory"
    memory_dir.mkdir(exist_ok=True)
    return str(memory_dir)


@pytest.fixture
def sample_chapter():
    """Sample chapter content for testing"""
    return """李明站在图书馆的门口，看着窗外的细雨，心中充满了不安。
今天是他和王芳约定的见面时间，但他迟迟不敢进去。
上次两人因为那本古书的事情发生了争执，不知道今天见面会是什么结果。

王芳早已在图书馆等候，她坐在靠窗的位置，手里翻看着那本书。
看到李明进来，她抬起头，眼中闪过一丝复杂的神情。"""


@pytest.fixture
def sample_chapter_2():
    """Second sample chapter for continuity testing"""
    return """李明走到王芳面前，看到她眼中的复杂神情，心里一紧。
"你来了。"王芳轻声说道，合上了手中的书。
"嗯，我来了。"李明点点头，在她对面坐下。

窗外的雨渐渐大了起来，雨滴敲打着玻璃窗。
两人相对无言，空气中弥漫着尴尬的气息。"""


@pytest.fixture
def sample_characters():
    """Sample character list"""
    return ["李明", "王芳", "张伟"]


@pytest.fixture
def sample_entities():
    """Sample entity data for testing"""
    return {
        "characters": [
            {"name": "李明", "traits": ["勇敢", "善良"], "state": "忧虑"},
            {"name": "王芳", "traits": ["聪明", "温柔"], "state": "复杂"}
        ],
        "locations": [
            {"name": "图书馆", "description": "安静的读书场所"}
        ]
    }


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing"""
    return {
        "characters": [
            {"name": "李明", "traits": ["勇敢"], "state": "忧虑"}
        ],
        "relationships": [
            {"char1": "李明", "char2": "王芳", "type": "朋友"}
        ],
        "events": [
            {"description": "李明来到图书馆见王芳", "importance": 0.8}
        ]
    }
