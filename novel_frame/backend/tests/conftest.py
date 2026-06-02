"""pytest fixtures for novel_frame backend tests.

确保两件事:
1. ``PROJECT_ROOT`` 和 ``novel_frame/backend`` 都加入 ``sys.path``,
   测试可以 ``from memory_system.models import ...`` 也可以
   ``from agents.xxx import ...``
2. 提供 ``mock_llm`` fixture - 把 ``nf_core.llm_client.llm_client.chat``
   patch 为可控 AsyncMock,所有依赖 ``llm_client`` 的 agent 都自动用 mock
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))

# PROJECT_ROOT 在前 - 让 memory_system / utils / core 等顶级包能被 import
for p in (_PROJECT_ROOT, _BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


@dataclass(frozen=True)
class FakeLLMResponse:
    """匹配 nf_core.llm_client.LLMResponse 结构。"""

    content: str
    usage_prompt_tokens: int = 0
    usage_completion_tokens: int = 0


@pytest.fixture
def mock_llm(monkeypatch):
    """把 nf_core.llm_client.llm_client.chat 替换为可控 AsyncMock。

    用法:
        async def test_x(mock_llm):
            mock_llm.set_responses([{"foo": "bar"}, "raw text"])
            ...
    """
    import json as _json

    import nf_core.llm_client as llm_module

    class _MockController:
        def __init__(self) -> None:
            self._queue: list[Any] = []
            self.calls: list[tuple[str, str]] = []  # (system, user)

        def set_responses(self, responses: list[Any]) -> None:
            self._queue = list(responses)

        def push(self, response: Any) -> None:
            self._queue.append(response)

        async def __call__(self, system_prompt: str, user_prompt: str, **kw) -> FakeLLMResponse:
            self.calls.append((system_prompt, user_prompt))
            if not self._queue:
                return FakeLLMResponse(content="{}")
            r = self._queue.pop(0)
            if isinstance(r, dict) or isinstance(r, list):
                return FakeLLMResponse(content=_json.dumps(r, ensure_ascii=False))
            return FakeLLMResponse(content=str(r))

    ctrl = _MockController()
    # patch singleton method 而非整个 llm_client 对象,所有已 import 的 agent
    # 都会自动看到 patched chat
    monkeypatch.setattr(llm_module.llm_client, "chat", ctrl, raising=True)

    # 也 patch chat_stream 避免意外触发
    async def _empty_stream(*args, **kwargs):
        if False:
            yield ""
        return

    monkeypatch.setattr(llm_module.llm_client, "chat_stream", _empty_stream, raising=True)
    return ctrl
