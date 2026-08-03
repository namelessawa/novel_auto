"""Import-order-safe runtime configuration for OpenAI-compatible providers.

Provider credentials must never be captured as a module-import side effect.
This module keeps the immutable configuration separate from client instances,
resolves it at call time, and caches clients by a non-secret configuration
fingerprint.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib
import json
import os
import re
import secrets
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator, Mapping
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from openai import AsyncOpenAI


class ProviderConfigurationError(ValueError):
    """The selected provider configuration is incomplete or malformed."""


def _as_int(value: Any, *, default: int, minimum: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ProviderConfigurationError("provider integer setting is invalid") from exc
    if parsed < minimum:
        raise ProviderConfigurationError("provider integer setting is out of range")
    return parsed


def _as_float(
    value: Any,
    *,
    default: float,
    minimum: float = 0.0,
    maximum: float | None = None,
) -> float:
    if value in (None, ""):
        return default
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ProviderConfigurationError("provider numeric setting is invalid") from exc
    if parsed < minimum or (maximum is not None and parsed > maximum):
        raise ProviderConfigurationError("provider numeric setting is out of range")
    return parsed


def _key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


_DIAGNOSTIC_FINGERPRINT_SALT = secrets.token_bytes(32)


@dataclass(frozen=True, slots=True)
class ProviderRuntimeConfig:
    """Complete immutable configuration for one provider client."""

    provider: str
    api_key: str = field(repr=False)
    base_url: str = field(repr=False)
    model: str
    thinking_mode: str
    timeout: float
    max_retries: int
    temperature: float
    max_tokens_cap: int
    source: str

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()
        api_key = self.api_key.strip()
        base_url = self.base_url.strip()
        model = self.model.strip()
        thinking_mode = self.thinking_mode.strip().lower()
        source = self.source.strip() or "unknown"
        if not provider:
            raise ProviderConfigurationError("provider is required")
        if not api_key:
            raise ProviderConfigurationError("provider credential is required")
        if not base_url:
            raise ProviderConfigurationError("provider base URL is required")
        parsed_url = urlsplit(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ProviderConfigurationError("provider base URL is invalid")
        if not model:
            raise ProviderConfigurationError("provider model is required")
        if self.timeout <= 0:
            raise ProviderConfigurationError("provider timeout must be positive")
        if self.max_retries < 0:
            raise ProviderConfigurationError("provider retries cannot be negative")
        if not 0 <= self.temperature <= 2:
            raise ProviderConfigurationError("provider temperature must be between 0 and 2")
        if self.max_tokens_cap <= 0:
            raise ProviderConfigurationError("provider max token cap must be positive")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "thinking_mode", thinking_mode)
        object.__setattr__(self, "source", source)

    @classmethod
    def from_explicit(
        cls,
        *,
        provider: str,
        api_key: str,
        base_url: str,
        model: str,
        thinking_mode: str = "",
        timeout: float = 600.0,
        max_retries: int = 0,
        temperature: float = 0.7,
        max_tokens_cap: int = 65536,
        source: str = "explicit",
    ) -> "ProviderRuntimeConfig":
        mode = thinking_mode.strip().lower()
        if not mode and model.strip().lower().startswith("glm-"):
            mode = "disabled"
        return cls(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            thinking_mode=mode,
            timeout=float(timeout),
            max_retries=int(max_retries),
            temperature=float(temperature),
            max_tokens_cap=int(max_tokens_cap),
            source=source,
        )

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any],
        *,
        source: str,
        default_provider: str = "custom",
    ) -> "ProviderRuntimeConfig":
        normalized = {
            str(key).strip().upper(): str(value).strip()
            for key, value in values.items()
            if value not in (None, "")
        }

        def pick(*names: str) -> str:
            for name in names:
                value = normalized.get(name)
                if value:
                    return value
            return ""

        provider = pick("LLM_PROVIDER", "PROVIDER") or default_provider
        prefix = provider.strip().upper()
        api_key = pick(
            f"{prefix}_API_KEY",
            "CUSTOM_API_KEY",
            "OPENAI_API_KEY",
            "API_KEY",
            "KEY",
        )
        base_url = pick(
            f"{prefix}_BASE_URL",
            "CUSTOM_BASE_URL",
            "OPENAI_BASE_URL",
            "BASE_URL",
            "URL",
        )
        model = pick(
            f"{prefix}_MODEL",
            "CUSTOM_MODEL",
            "OPENAI_MODEL",
            "MODEL",
        )
        thinking_mode = pick("LLM_THINKING_MODE", "THINKING_MODE")
        return cls.from_explicit(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            thinking_mode=thinking_mode,
            timeout=_as_float(
                pick("LLM_TIMEOUT", "TIMEOUT"),
                default=600.0,
                minimum=0.001,
            ),
            max_retries=_as_int(
                pick("LLM_MAX_RETRIES", "MAX_RETRIES", "RETRIES"),
                default=0,
            ),
            temperature=_as_float(
                pick("LLM_TEMPERATURE", "TEMPERATURE"),
                default=0.7,
                minimum=0.0,
                maximum=2.0,
            ),
            max_tokens_cap=_as_int(
                pick("LLM_MAX_TOKENS_CAP", "MAX_TOKENS_CAP"),
                default=65536,
                minimum=1,
            ),
            source=source,
        )

    @classmethod
    def from_user_request(
        cls,
        *,
        api_key: str,
        provider: str = "",
        base_url: str = "",
        model: str = "",
        thinking_mode: str = "",
        timeout: float = 600.0,
        max_retries: int = 0,
        temperature: float = 0.7,
        max_tokens_cap: int = 65536,
    ) -> "ProviderRuntimeConfig":
        """Build one atomic user-scoped provider configuration.

        A request credential must never inherit an endpoint or model from the
        server fallback.  When a provider is named, only that provider's public
        catalog defaults may fill omitted fields.  Supplying a custom endpoint
        without a provider selects ``custom`` and therefore requires an
        explicit model.
        """

        requested = provider.strip().lower()
        if not requested:
            requested = "custom" if base_url.strip() else "deepseek"
        defaults = get_provider_catalog_defaults(requested)
        resolved_base_url = base_url.strip() or defaults["base_url"]
        resolved_model = model.strip() or defaults["model"]
        return cls.from_explicit(
            provider=requested,
            api_key=api_key,
            base_url=resolved_base_url,
            model=resolved_model,
            thinking_mode=thinking_mode,
            timeout=timeout,
            max_retries=max_retries,
            temperature=temperature,
            max_tokens_cap=max_tokens_cap,
            source="request",
        )

    @classmethod
    def from_provider_file(cls, path: Path) -> "ProviderRuntimeConfig":
        provider_path = path.resolve()
        if not provider_path.is_file():
            raise FileNotFoundError(provider_path)
        values = {
            str(key).upper(): str(value)
            for key, value in dotenv_values(provider_path).items()
            if value not in (None, "")
        }
        # Accept the historical ``key: value`` and Chinese-label formats without
        # persisting or reflecting any value.
        for raw in provider_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            separator = "=" if "=" in line else (":" if ":" in line else "")
            if not separator:
                continue
            name, value = (part.strip() for part in line.split(separator, 1))
            upper_name = name.upper()
            values.setdefault(upper_name, value)
            lowered = name.lower()
            if "key" in lowered or "密钥" in lowered:
                values.setdefault("KEY", value)
            elif "url" in lowered or "地址" in lowered:
                values.setdefault("URL", value)
            elif "model" in lowered or "模型" in lowered:
                values.setdefault("MODEL", value)
        return cls.from_mapping(
            values,
            source="provider_file",
            default_provider="custom",
        )

    @property
    def key_fingerprint(self) -> str:
        return hmac.new(
            _DIAGNOSTIC_FINGERPRINT_SALT,
            self.api_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:8]

    @property
    def client_cache_key(self) -> str:
        payload = {
            "provider": self.provider,
            "base_url": self.base_url.rstrip("/"),
            "model": self.model,
            "api_key_sha256": _key_hash(self.api_key),
            "thinking_mode": self.thinking_mode,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @property
    def config_fingerprint(self) -> str:
        # Public diagnostics may expose this value.  It intentionally excludes
        # both the credential and its hash so it cannot be used as a credential
        # correlation or offline-guessing oracle.
        payload = {
            "provider": self.provider,
            "base_url": self.base_url.rstrip("/"),
            "model": self.model,
            "thinking_mode": self.thinking_mode,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "temperature": self.temperature,
            "max_tokens_cap": self.max_tokens_cap,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()[:16]

    def diagnostics(self) -> dict[str, Any]:
        diagnostics = {
            "provider": self.provider,
            "model": self.model,
            "source": self.source,
            "thinking_mode": self.thinking_mode,
            "timeout": self.timeout,
            "retries": self.max_retries,
            "temperature": self.temperature,
            "max_tokens_cap": self.max_tokens_cap,
            "credential_present": bool(self.api_key),
            "config_fingerprint": self.config_fingerprint,
        }
        if self.api_key:
            diagnostics["key_fingerprint"] = self.key_fingerprint
        return diagnostics

    def with_overrides(self, **changes: Any) -> "ProviderRuntimeConfig":
        return replace(self, **changes)


_request_provider_var: ContextVar[ProviderRuntimeConfig | None] = ContextVar(
    "llm_request_provider_config",
    default=None,
)
_stage_provider_var: ContextVar[ProviderRuntimeConfig | None] = ContextVar(
    "llm_stage_provider_config",
    default=None,
)


def set_request_provider_config(
    config: ProviderRuntimeConfig,
) -> Token[ProviderRuntimeConfig | None]:
    return _request_provider_var.set(config)


def reset_request_provider_config(
    token: Token[ProviderRuntimeConfig | None],
) -> None:
    _request_provider_var.reset(token)


def get_request_provider_config() -> ProviderRuntimeConfig | None:
    return _request_provider_var.get()


def set_stage_provider_config(
    config: ProviderRuntimeConfig,
) -> Token[ProviderRuntimeConfig | None]:
    return _stage_provider_var.set(config)


def reset_stage_provider_config(
    token: Token[ProviderRuntimeConfig | None],
) -> None:
    _stage_provider_var.reset(token)


def get_stage_provider_config() -> ProviderRuntimeConfig | None:
    return _stage_provider_var.get()


def configure_stage_provider_from_file(
    path: Path,
) -> tuple[ProviderRuntimeConfig, Token[ProviderRuntimeConfig | None]]:
    """Read a provider file once and bind it to the current stage context."""

    config = ProviderRuntimeConfig.from_provider_file(path)
    return config, set_stage_provider_config(config)


@contextmanager
def stage_provider_scope(
    config: ProviderRuntimeConfig,
) -> Iterator[ProviderRuntimeConfig]:
    """Bind a stage provider for exactly one explicit lexical scope."""

    token = set_stage_provider_config(config)
    try:
        yield config
    finally:
        reset_stage_provider_config(token)


@contextmanager
def stage_provider_file_scope(path: Path) -> Iterator[ProviderRuntimeConfig]:
    """Parse a provider file once and restore the previous stage on exit."""

    config = ProviderRuntimeConfig.from_provider_file(path)
    with stage_provider_scope(config):
        yield config


def get_provider_catalog_defaults(provider: str) -> dict[str, str]:
    """Return credential-free defaults for one supported provider."""

    normalized = provider.strip().lower()
    try:
        module = importlib.import_module("core.config")
        catalog = module.get_provider_catalog()
    except (ImportError, AttributeError, OSError, TypeError) as exc:
        raise ProviderConfigurationError(
            "provider catalog is unavailable"
        ) from exc
    for item in catalog:
        if str(item.get("provider") or "").strip().lower() == normalized:
            return {
                "base_url": str(item.get("default_base_url") or "").strip(),
                "model": str(item.get("default_model") or "").strip(),
            }
    raise ProviderConfigurationError("provider is not supported")


def _server_provider_config() -> ProviderRuntimeConfig | None:
    try:
        module = importlib.import_module("config.settings")
        resolver = getattr(module, "resolve_server_llm_block_now", None)
        if not callable(resolver):
            return None
        block = resolver()
        if not block:
            return None
        return ProviderRuntimeConfig.from_explicit(
            provider=str(block.get("provider") or "custom"),
            api_key=str(block.get("api_key") or ""),
            base_url=str(block.get("base_url") or ""),
            model=str(block.get("model") or ""),
            thinking_mode=str(block.get("thinking_mode") or ""),
            timeout=float(block.get("timeout") or 600),
            max_retries=int(block.get("max_retries") or 0),
            temperature=float(
                0.7
                if block.get("temperature") in (None, "")
                else block["temperature"]
            ),
            max_tokens_cap=int(block.get("max_tokens_cap") or 65536),
            source="server_config",
        )
    except (ImportError, OSError, ValueError, TypeError):
        return None


def _environment_provider_config() -> ProviderRuntimeConfig | None:
    try:
        module = importlib.import_module("core.config")
        resolver = getattr(module, "resolve_llm_config_now", None)
        block = resolver() if callable(resolver) else module.get_active_llm_config()
        return ProviderRuntimeConfig.from_explicit(
            provider=str(block.get("provider") or "custom"),
            api_key=str(block.get("api_key") or ""),
            base_url=str(block.get("base_url") or ""),
            model=str(block.get("model") or ""),
            thinking_mode=str(
                block.get("thinking_mode")
                or os.environ.get("LLM_THINKING_MODE")
                or ""
            ),
            timeout=float(block.get("timeout") or 600),
            max_retries=_as_int(
                os.environ.get("LLM_MAX_RETRIES"),
                default=0,
            ),
            temperature=float(
                0.7
                if block.get("temperature") in (None, "")
                else block["temperature"]
            ),
            max_tokens_cap=_as_int(
                os.environ.get("LLM_MAX_TOKENS_CAP"),
                default=65536,
                minimum=1,
            ),
            source="environment",
        )
    except (ImportError, OSError, ValueError, TypeError):
        return None


def resolve_provider_runtime(
    explicit: ProviderRuntimeConfig | None = None,
    *,
    include_request: bool = True,
    include_stage: bool = True,
    include_server: bool = True,
    include_environment: bool = True,
) -> ProviderRuntimeConfig:
    """Resolve current config with explicit/request/stage/server/env priority."""

    if explicit is not None:
        return explicit
    if include_request:
        request_config = get_request_provider_config()
        if request_config is not None:
            return request_config
    if include_stage:
        stage_config = get_stage_provider_config()
        if stage_config is not None:
            return stage_config
    if include_server:
        server_config = _server_provider_config()
        if server_config is not None:
            return server_config
    if include_environment:
        environment_config = _environment_provider_config()
        if environment_config is not None:
            return environment_config
    raise ProviderConfigurationError(
        "no complete provider runtime configuration is available"
    )


ClientFactory = Callable[[ProviderRuntimeConfig], Any]


def _default_client_factory(config: ProviderRuntimeConfig) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        max_retries=config.max_retries,
        timeout=httpx.Timeout(config.timeout, connect=min(15.0, config.timeout)),
    )


@dataclass(slots=True)
class _ClientEntry:
    key: str
    client: Any
    ref_count: int = 0
    retired: bool = False


class ProviderClientLease:
    """One reference-counted borrow from a provider client registry."""

    __slots__ = ("_entry", "_registry", "_released")

    def __init__(
        self,
        registry: "ProviderClientRegistry",
        entry: _ClientEntry,
    ) -> None:
        self._registry = registry
        self._entry = entry
        self._released = False

    @property
    def client(self) -> Any:
        return self._entry.client

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._registry._release_entry(self._entry)


class ProviderClientRegistry:
    """Bounded cache whose retired clients close after their last borrower."""

    def __init__(
        self,
        *,
        client_factory: ClientFactory | None = None,
        max_size: int = 32,
    ) -> None:
        self._client_factory = client_factory or _default_client_factory
        self._max_size = max(1, int(max_size))
        self._cache: "OrderedDict[str, _ClientEntry]" = OrderedDict()
        self._entries: dict[int, _ClientEntry] = {}
        self._retired: list[Any] = []
        self._close_tasks: set[asyncio.Task[Any]] = set()
        self._lock = threading.RLock()

    @property
    def cache_size(self) -> int:
        with self._lock:
            return len(self._cache)

    def cache_keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._cache)

    def get_client(self, config: ProviderRuntimeConfig) -> Any:
        """Compatibility view; production calls should use ``acquire``."""

        key = config.client_cache_key
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                self._cache.move_to_end(key)
                return entry.client
            client = self._client_factory(config)
            entry = _ClientEntry(key=key, client=client)
            self._cache[key] = entry
            self._entries[id(entry)] = entry
            while len(self._cache) > self._max_size:
                _, stale_entry = self._cache.popitem(last=False)
                self._mark_retired_locked(stale_entry)
            return client

    def acquire(self, config: ProviderRuntimeConfig) -> ProviderClientLease:
        key = config.client_cache_key
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                entry = _ClientEntry(
                    key=key,
                    client=self._client_factory(config),
                )
                self._cache[key] = entry
                self._entries[id(entry)] = entry
            else:
                self._cache.move_to_end(key)
            entry.ref_count += 1
            while len(self._cache) > self._max_size:
                _, stale_entry = self._cache.popitem(last=False)
                self._mark_retired_locked(stale_entry)
            return ProviderClientLease(self, entry)

    def _release_entry(self, entry: _ClientEntry) -> None:
        with self._lock:
            tracked = self._entries.get(id(entry))
            if tracked is not entry or entry.ref_count <= 0:
                return
            entry.ref_count -= 1
            if entry.retired and entry.ref_count == 0:
                self._entries.pop(id(entry), None)
                self._retire(entry.client)

    def _mark_retired_locked(self, entry: _ClientEntry) -> None:
        if entry.retired:
            return
        entry.retired = True
        if entry.ref_count == 0:
            self._entries.pop(id(entry), None)
            self._retire(entry.client)

    def invalidate(self, config: ProviderRuntimeConfig | None = None) -> None:
        with self._lock:
            if config is None:
                stale = list(self._cache.values())
                self._cache.clear()
            else:
                entry = self._cache.pop(config.client_cache_key, None)
                stale = [entry] if entry is not None else []
            for entry in stale:
                self._mark_retired_locked(entry)

    def _retire(self, client: Any) -> None:
        close = getattr(client, "close", None)
        if not callable(close):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._retired.append(client)
            return
        task = loop.create_task(self._close_one(client))
        self._close_tasks.add(task)
        task.add_done_callback(self._consume_close_task)

    def _consume_close_task(self, task: asyncio.Task[Any]) -> None:
        self._close_tasks.discard(task)
        if task.cancelled():
            return
        # Retrieve the exception so a failed close never produces an
        # unobserved-task warning.  Shutdown remains best-effort.
        task.exception()

    @staticmethod
    async def _close_one(client: Any) -> None:
        close = getattr(client, "close", None)
        if not callable(close):
            return
        result = close()
        if hasattr(result, "__await__"):
            await result

    async def aclose_retired(self) -> None:
        with self._lock:
            retired = self._retired
            self._retired = []
            close_tasks = tuple(self._close_tasks)
        if retired or close_tasks:
            await asyncio.gather(
                *close_tasks,
                *(self._close_one(client) for client in retired),
                return_exceptions=True,
            )

    async def aclose_all(self) -> None:
        with self._lock:
            active = list(self._cache.values())
            self._cache.clear()
            for entry in active:
                self._mark_retired_locked(entry)
        await self.aclose_retired()


provider_client_registry = ProviderClientRegistry()


@asynccontextmanager
async def ephemeral_provider_client(
    config: ProviderRuntimeConfig,
) -> AsyncIterator[Any]:
    """Yield a one-shot client that is never inserted into the registry."""

    client = _default_client_factory(config)
    try:
        yield client
    finally:
        try:
            await ProviderClientRegistry._close_one(client)
        except Exception:
            # Closing is best-effort and must not replace the sanitized result
            # of the provider call with an unrelated transport teardown error.
            pass


@dataclass(frozen=True, slots=True)
class ProviderRuntimeReceipt:
    """Secret-free identity of the exact runtime used by one Provider call."""

    provider: str
    model: str
    thinking_mode: str
    max_retries: int
    source: str
    config_fingerprint: str


class ProviderError(RuntimeError):
    """Sanitized provider failure safe for API, task, log and evidence surfaces."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        http_status: int,
        http_category: str,
        config: ProviderRuntimeConfig | ProviderRuntimeReceipt,
        upstream_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.http_category = http_category
        self.config = config
        self.upstream_status = upstream_status
        self.provider_stage = ""
        self.provider_primary_calls = 0
        self.structured_output_repair_calls = 0
        self.provider_call_count = 0

    def to_detail(self) -> dict[str, Any]:
        receipt = safe_provider_runtime_receipt(self.config)
        details = (
            {
                "provider": receipt.provider,
                "model": receipt.model,
                "thinking_mode": receipt.thinking_mode,
                "sdk_retries": receipt.max_retries,
                "source": receipt.source,
                "config_fingerprint": receipt.config_fingerprint,
            }
            if receipt is not None
            else {
                "provider": "unknown",
                "model": "unknown",
                "thinking_mode": "unknown",
                "sdk_retries": 0,
                "source": "unknown",
                "config_fingerprint": "",
            }
        )
        if (
            isinstance(self.upstream_status, int)
            and not isinstance(self.upstream_status, bool)
            and 100 <= self.upstream_status <= 599
        ):
            details["upstream_status"] = self.upstream_status
        return {
            "code": (
                self.code
                if is_recognized_provider_error(self)
                else "PROVIDER_UNAVAILABLE"
            ),
            "message": provider_error_public_message(self),
            "details": details,
        }

    def to_probe_detail(self, *, latency_ms: float = 0.0) -> dict[str, Any]:
        """Return the flat, secret-safe contract for the Provider probe API.

        Probe failures intentionally do not reuse ``self.message``.  Although
        normal classification creates a sanitized message, callers may pass a
        pre-built ``ProviderError`` whose message contains an upstream body,
        request header, endpoint, or prompt.  The probe surface therefore maps
        only the stable error code and exposes no raw exception material.
        """

        receipt = safe_provider_runtime_receipt(self.config)
        return {
            "success": False,
            "http_category": (
                self.http_category
                if is_recognized_provider_error(self)
                else "unavailable"
            ),
            "code": (
                self.code
                if is_recognized_provider_error(self)
                else "PROVIDER_UNAVAILABLE"
            ),
            "message": provider_error_public_message(self, english=True),
            "provider": receipt.provider if receipt is not None else "unknown",
            "model": receipt.model if receipt is not None else "unknown",
            "thinking_mode": (
                receipt.thinking_mode if receipt is not None else "unknown"
            ),
            "sdk_retries": receipt.max_retries if receipt is not None else 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms": round(max(0.0, float(latency_ms)), 2),
            "source": receipt.source if receipt is not None else "unknown",
            "config_fingerprint": (
                receipt.config_fingerprint if receipt is not None else ""
            ),
        }


PROVIDER_ERROR_CATEGORY_BY_CODE = {
    "PROVIDER_AUTH_FAILED": "auth",
    "PROVIDER_RATE_LIMITED": "rate_limit",
    "PROVIDER_REQUEST_INVALID": "request_invalid",
    "PROVIDER_TIMEOUT": "timeout",
    "PROVIDER_UNAVAILABLE": "unavailable",
    "PROVIDER_OUTPUT_INVALID": "output_invalid",
}
_PROVIDER_ERROR_PUBLIC_MESSAGES = {
    "PROVIDER_AUTH_FAILED": "模型服务认证失败",
    "PROVIDER_RATE_LIMITED": "模型服务请求过于频繁",
    "PROVIDER_REQUEST_INVALID": "模型服务拒绝了当前模型或请求参数",
    "PROVIDER_TIMEOUT": "模型服务响应超时",
    "PROVIDER_UNAVAILABLE": "模型服务暂时不可用",
    "PROVIDER_OUTPUT_INVALID": "模型服务输出无法解析",
}
_PROVIDER_ERROR_PUBLIC_MESSAGES_EN = {
    "PROVIDER_AUTH_FAILED": "Provider authentication failed",
    "PROVIDER_RATE_LIMITED": "Provider rate limit exceeded",
    "PROVIDER_REQUEST_INVALID": "Provider rejected the request",
    "PROVIDER_TIMEOUT": "Provider response timed out",
    "PROVIDER_UNAVAILABLE": "Provider is temporarily unavailable",
    "PROVIDER_OUTPUT_INVALID": "Provider output was invalid",
}
_SAFE_PROVIDER_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_SAFE_PROVIDER_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:/@-]{0,191}")
_SAFE_PROVIDER_SOURCE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")
_SAFE_THINKING_MODE = re.compile(r"[A-Za-z0-9_.-]{0,31}")
_SAFE_CONFIG_FINGERPRINT = re.compile(r"[0-9a-f]{16}")


def is_recognized_provider_error(value: Any) -> bool:
    return bool(
        isinstance(value, ProviderError)
        and PROVIDER_ERROR_CATEGORY_BY_CODE.get(str(value.code))
        == str(value.http_category)
    )


def provider_error_public_message(
    value: ProviderError,
    *,
    english: bool = False,
) -> str:
    messages = (
        _PROVIDER_ERROR_PUBLIC_MESSAGES_EN
        if english
        else _PROVIDER_ERROR_PUBLIC_MESSAGES
    )
    return messages.get(str(value.code), "Provider request failed")


def safe_provider_runtime_receipt(value: Any) -> ProviderRuntimeReceipt | None:
    """Extract only bounded, non-secret runtime identity fields."""

    try:
        provider = str(value.provider)
        model = str(value.model)
        thinking_mode = str(value.thinking_mode)
        retries = int(value.max_retries)
        source = str(value.source)
        fingerprint = str(value.config_fingerprint)
    except (AttributeError, TypeError, ValueError):
        return None
    if (
        not _SAFE_PROVIDER_NAME.fullmatch(provider)
        or not _SAFE_PROVIDER_MODEL.fullmatch(model)
        or "://" in model
        or not _SAFE_THINKING_MODE.fullmatch(thinking_mode)
        or not 0 <= retries <= 100
        or not _SAFE_PROVIDER_SOURCE.fullmatch(source)
        or not _SAFE_CONFIG_FINGERPRINT.fullmatch(fingerprint)
    ):
        return None
    return ProviderRuntimeReceipt(
        provider=provider,
        model=model,
        thinking_mode=thinking_mode,
        max_retries=retries,
        source=source,
        config_fingerprint=fingerprint,
    )


def classify_provider_exception(
    exc: Exception,
    config: ProviderRuntimeConfig,
) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    raw_status = getattr(exc, "status_code", None)
    try:
        status_code = int(raw_status) if raw_status is not None else None
    except (TypeError, ValueError):
        status_code = None
    class_name = type(exc).__name__.lower()
    if status_code in {401, 403} or "authentication" in class_name:
        return ProviderError(
            code="PROVIDER_AUTH_FAILED",
            message="模型服务认证失败",
            http_status=424,
            http_category="auth",
            config=config,
            upstream_status=status_code,
        )
    if status_code == 429 or "ratelimit" in class_name:
        return ProviderError(
            code="PROVIDER_RATE_LIMITED",
            message="模型服务请求过于频繁",
            http_status=429,
            http_category="rate_limit",
            config=config,
            upstream_status=status_code,
        )
    if status_code in {400, 404, 409, 422}:
        return ProviderError(
            code="PROVIDER_REQUEST_INVALID",
            message="模型服务拒绝了当前模型或请求参数",
            http_status=422,
            http_category="request_invalid",
            config=config,
            upstream_status=status_code,
        )
    if status_code in {408, 504} or "timeout" in class_name:
        return ProviderError(
            code="PROVIDER_TIMEOUT",
            message="模型服务响应超时",
            http_status=504,
            http_category="timeout",
            config=config,
            upstream_status=status_code,
        )
    return ProviderError(
        code="PROVIDER_UNAVAILABLE",
        message="模型服务暂时不可用",
        http_status=502,
        http_category="unavailable",
        config=config,
        upstream_status=status_code,
    )


def provider_output_invalid(
    config: ProviderRuntimeConfig,
    message: str = "模型服务输出无法解析",
) -> ProviderError:
    return ProviderError(
        code="PROVIDER_OUTPUT_INVALID",
        message=message,
        http_status=502,
        http_category="output_invalid",
        config=config,
    )


__all__ = [
    "ProviderClientLease",
    "ProviderClientRegistry",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderRuntimeConfig",
    "ProviderRuntimeReceipt",
    "PROVIDER_ERROR_CATEGORY_BY_CODE",
    "classify_provider_exception",
    "configure_stage_provider_from_file",
    "ephemeral_provider_client",
    "get_provider_catalog_defaults",
    "get_request_provider_config",
    "get_stage_provider_config",
    "is_recognized_provider_error",
    "provider_client_registry",
    "provider_output_invalid",
    "provider_error_public_message",
    "reset_request_provider_config",
    "reset_stage_provider_config",
    "resolve_provider_runtime",
    "set_request_provider_config",
    "set_stage_provider_config",
    "safe_provider_runtime_receipt",
    "stage_provider_file_scope",
    "stage_provider_scope",
]
