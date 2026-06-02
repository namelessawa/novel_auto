"""Shared config bridge for the backend tick engine.

After the v2.x consolidation only ``core/config.py`` remains active — it
exposes ``get_active_llm_config()`` which ``backend/config/settings.py``
loads via ``importlib`` to read the user's ``.env`` (LLM_PROVIDER + keys).

All v1.x runtime modules (``generator``, ``chapter_analyzer``,
``llm_client``, ``embedding_service``, ``background_task``, ``novel_manager``)
have been archived to ``old/core/``.
"""

from . import config

__all__ = ["config"]
