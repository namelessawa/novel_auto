from __future__ import annotations

import asyncio
import importlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import nf_core.provider_runtime as provider_runtime_module
from nf_core.provider_runtime import (
    ProviderClientRegistry,
    ProviderConfigurationError,
    ProviderRuntimeConfig,
    classify_provider_exception,
    configure_stage_provider_from_file,
    ephemeral_provider_client,
    get_request_provider_config,
    get_stage_provider_config,
    reset_request_provider_config,
    reset_stage_provider_config,
    resolve_provider_runtime,
    set_request_provider_config,
    set_stage_provider_config,
    stage_provider_scope,
)


class _FakeClient:
    def __init__(self, config: ProviderRuntimeConfig) -> None:
        self.config = config
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _config(*, key: str, model: str = "model-a") -> ProviderRuntimeConfig:
    return ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key=key,
        base_url="https://provider.invalid/v1",
        model=model,
        thinking_mode="disabled",
        timeout=30,
        max_retries=0,
        temperature=0.2,
        max_tokens_cap=4096,
        source="test",
    )


def _provider_file(tmp_path: Path, *, model: str = "glm-5.2") -> Path:
    path = tmp_path / "coding.txt"
    path.write_text(
        "\n".join(
            (
                "KEY=test-provider-key",
                "URL=https://provider.invalid/v1",
                f"MODEL={model}",
                "LLM_TIMEOUT=45",
                "LLM_MAX_RETRIES=0",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_provider_file_builds_strong_config_without_mutating_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("CUSTOM_API_KEY", "pre-existing")
    before = {
        "LLM_PROVIDER": os.environ["LLM_PROVIDER"],
        "CUSTOM_API_KEY": os.environ["CUSTOM_API_KEY"],
    }

    token = None
    try:
        config, token = configure_stage_provider_from_file(
            _provider_file(tmp_path)
        )
        assert isinstance(config, ProviderRuntimeConfig)
        assert config.provider == "custom"
        assert config.model == "glm-5.2"
        assert config.thinking_mode == "disabled"
        assert config.timeout == 45
        assert config.max_retries == 0
        assert config.source == "provider_file"
        assert before == {
            "LLM_PROVIDER": os.environ["LLM_PROVIDER"],
            "CUSTOM_API_KEY": os.environ["CUSTOM_API_KEY"],
        }
    finally:
        if token is not None:
            reset_stage_provider_config(token)


def test_diagnostics_never_include_key_or_full_url() -> None:
    config = _config(key="super-secret-provider-key")

    rendered = repr(config.diagnostics())

    assert "super-secret-provider-key" not in repr(config)
    assert "super-secret-provider-key" not in rendered
    assert "https://provider.invalid/v1" not in rendered
    assert config.key_fingerprint in rendered
    assert len(config.key_fingerprint) == 8
    assert (
        config.key_fingerprint
        != provider_runtime_module._key_hash(config.api_key)[:8]
    )
    assert config.config_fingerprint in rendered


def test_public_config_fingerprint_is_not_derived_from_credential() -> None:
    first = _config(key="credential-one")
    second = _config(key="credential-two")

    assert first.config_fingerprint == second.config_fingerprint
    assert first.client_cache_key != second.client_cache_key


def test_cache_isolated_by_hashed_key_and_does_not_store_plaintext_keys() -> None:
    registry = ProviderClientRegistry(client_factory=_FakeClient, max_size=8)
    first = _config(key="credential-one")
    second = _config(key="credential-two")

    first_client = registry.get_client(first)
    second_client = registry.get_client(second)

    assert first_client is not second_client
    assert all("credential-" not in key for key in registry.cache_keys())


def test_cache_key_covers_provider_model_and_thinking_mode() -> None:
    base = _config(key="shared-credential")

    assert base.client_cache_key != base.with_overrides(
        provider="openai",
    ).client_cache_key
    assert base.client_cache_key != base.with_overrides(
        model="model-b",
    ).client_cache_key
    assert base.client_cache_key != base.with_overrides(
        thinking_mode="enabled",
    ).client_cache_key


@pytest.mark.asyncio
async def test_request_contexts_do_not_cross_credentials() -> None:
    first = _config(key="credential-one", model="model-one")
    second = _config(key="credential-two", model="model-two")

    async def read(config: ProviderRuntimeConfig) -> tuple[str, str]:
        token = set_request_provider_config(config)
        try:
            await asyncio.sleep(0)
            current = get_request_provider_config()
            assert current is not None
            return current.key_fingerprint, current.model
        finally:
            reset_request_provider_config(token)

    results = await asyncio.gather(read(first), read(second))

    assert results == [
        (first.key_fingerprint, "model-one"),
        (second.key_fingerprint, "model-two"),
    ]
    assert get_request_provider_config() is None


@pytest.mark.asyncio
async def test_registry_invalidate_closes_retired_clients() -> None:
    registry = ProviderClientRegistry(client_factory=_FakeClient, max_size=8)
    config = _config(key="credential-one")
    client = registry.get_client(config)

    registry.invalidate(config)
    await registry.aclose_retired()

    assert client.closed is True
    assert registry.cache_size == 0


@pytest.mark.asyncio
async def test_registry_does_not_close_retired_client_until_lease_released() -> None:
    registry = ProviderClientRegistry(client_factory=_FakeClient, max_size=1)
    first = _config(key="credential-one")
    second = _config(key="credential-two")
    lease = registry.acquire(first)
    first_client = lease.client

    registry.get_client(second)
    await registry.aclose_retired()
    assert first_client.closed is False

    lease.release()
    await registry.aclose_retired()
    assert first_client.closed is True


def test_stage_scope_restores_previous_config() -> None:
    first = _config(key="credential-one", model="model-one")
    second = _config(key="credential-two", model="model-two")
    token = set_stage_provider_config(first)
    try:
        with stage_provider_scope(second):
            assert get_stage_provider_config() is second
        assert get_stage_provider_config() is first
    finally:
        reset_stage_provider_config(token)


def test_reload_with_explicit_config_does_not_rebind_stage() -> None:
    import nf_core.llm_client as llm_module

    stage = _config(key="stage", model="stage-model")
    replacement = _config(key="replacement", model="replacement-model")
    token = set_stage_provider_config(stage)
    try:
        applied = llm_module.llm_client.reload(config=replacement)
        assert applied["model"] == "replacement-model"
        assert get_stage_provider_config() is stage
    finally:
        reset_stage_provider_config(token)


def test_stage_resolution_short_circuits_lower_priority_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(key="stage-only")
    token = set_stage_provider_config(config)
    monkeypatch.setattr(
        provider_runtime_module,
        "_server_provider_config",
        lambda: (_ for _ in ()).throw(AssertionError("server resolver called")),
    )
    monkeypatch.setattr(
        provider_runtime_module,
        "_environment_provider_config",
        lambda: (_ for _ in ()).throw(
            AssertionError("environment resolver called")
        ),
    )
    try:
        assert resolve_provider_runtime() is config
    finally:
        reset_stage_provider_config(token)


def test_user_provider_defaults_are_atomic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_runtime_module,
        "get_provider_catalog_defaults",
        lambda provider: {
            "base_url": f"https://{provider}.example/v1",
            "model": f"{provider}-model",
        },
    )

    config = ProviderRuntimeConfig.from_user_request(
        provider="openai",
        api_key="openai-user-key",
    )

    assert config.provider == "openai"
    assert config.base_url == "https://openai.example/v1"
    assert config.model == "openai-model"


def test_zero_temperature_survives_server_runtime_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_module = importlib.import_module("config.settings")
    monkeypatch.setattr(
        settings_module,
        "_load_config",
        lambda: {
            "llm": {
                "provider": "custom",
                "api_key": "zero-temperature-key",
                "base_url": "https://zero.example/v1",
                "model": "zero-model",
                "temperature": 0,
            }
        },
    )

    block = settings_module.resolve_server_llm_block_now()
    config = provider_runtime_module._server_provider_config()

    assert block["temperature"] == 0
    assert config is not None
    assert config.temperature == 0


def test_custom_user_endpoint_requires_explicit_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_runtime_module,
        "get_provider_catalog_defaults",
        lambda provider: {"base_url": "", "model": ""},
    )

    with pytest.raises(ProviderConfigurationError, match="model is required"):
        ProviderRuntimeConfig.from_user_request(
            api_key="custom-user-key",
            base_url="https://custom.example/v1",
        )


@pytest.mark.asyncio
async def test_ephemeral_client_never_enters_global_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeClient(_config(key="ephemeral"))
    monkeypatch.setattr(
        provider_runtime_module,
        "_default_client_factory",
        lambda config: client,
    )
    before = provider_runtime_module.provider_client_registry.cache_size

    async with ephemeral_provider_client(_config(key="ephemeral")) as actual:
        assert actual is client
        assert provider_runtime_module.provider_client_registry.cache_size == before

    assert client.closed is True


def test_provider_error_classification_is_safe_and_specific() -> None:
    config = _config(key="never-render-this")

    class UpstreamAuthError(RuntimeError):
        status_code = 401

    error = classify_provider_exception(
        UpstreamAuthError(
            "401 from https://provider.invalid/v1; key=never-render-this"
        ),
        config,
    )
    detail = error.to_detail()

    assert error.code == "PROVIDER_AUTH_FAILED"
    assert error.http_status == 424
    assert detail["code"] == "PROVIDER_AUTH_FAILED"
    assert detail["details"]["provider"] == "custom"
    assert detail["details"]["model"] == "model-a"
    serialized = repr(detail)
    assert "never-render-this" not in serialized
    assert "https://provider.invalid/v1" not in serialized


def test_probe_detail_does_not_trust_provider_error_message() -> None:
    config = _config(key="probe-secret-must-not-render", model="glm-5.2")
    error = provider_runtime_module.ProviderError(
        code="PROVIDER_UNAVAILABLE",
        message=(
            "Authorization: Bearer probe-secret-must-not-render; "
            "https://provider.invalid/v1; prompt=raw; response=raw"
        ),
        http_status=502,
        http_category="unavailable",
        config=config,
        upstream_status=503,
    )

    detail = error.to_probe_detail()

    assert detail == {
        "success": False,
        "http_category": "unavailable",
        "code": "PROVIDER_UNAVAILABLE",
        "message": "Provider is temporarily unavailable",
        "provider": "custom",
        "model": "glm-5.2",
        "thinking_mode": "disabled",
        "sdk_retries": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "latency_ms": 0.0,
        "source": "test",
        "config_fingerprint": config.config_fingerprint,
    }
    rendered = repr(detail)
    assert "probe-secret-must-not-render" not in rendered
    assert "https://provider.invalid/v1" not in rendered
    assert "Authorization" not in rendered
    assert "prompt=raw" not in rendered


@pytest.mark.parametrize(
    ("status_code", "expected_code", "expected_http_status"),
    [
        (400, "PROVIDER_REQUEST_INVALID", 422),
        (404, "PROVIDER_REQUEST_INVALID", 422),
        (408, "PROVIDER_TIMEOUT", 504),
        (503, "PROVIDER_UNAVAILABLE", 502),
    ],
)
def test_provider_error_classification_by_status(
    status_code: int,
    expected_code: str,
    expected_http_status: int,
) -> None:
    class UpstreamError(RuntimeError):
        pass

    exc = UpstreamError("provider body must not be reflected")
    exc.status_code = status_code
    error = classify_provider_exception(exc, _config(key="classified"))

    assert error.code == expected_code
    assert error.http_status == expected_http_status


def test_runtime_fails_closed_without_any_complete_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_runtime_module,
        "_server_provider_config",
        lambda: None,
    )
    monkeypatch.setattr(
        provider_runtime_module,
        "_environment_provider_config",
        lambda: None,
    )

    with pytest.raises(
        provider_runtime_module.ProviderConfigurationError,
        match="no complete provider runtime configuration",
    ):
        provider_runtime_module.resolve_provider_runtime()


@pytest.mark.asyncio
async def test_early_llm_client_import_uses_later_provider_file_config(
    tmp_path: Path,
) -> None:
    """Importing the proxy first must not freeze credentials or model state."""
    import nf_core.llm_client as llm_module

    seen: dict[str, object] = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            seen["request"] = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="ok",
                            reasoning_content=None,
                        )
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=3,
                    completion_tokens=1,
                    prompt_tokens_details=None,
                ),
            )

    class FakeRuntimeClient:
        def __init__(self, config: ProviderRuntimeConfig) -> None:
            seen["config"] = config
            self.chat = SimpleNamespace(completions=FakeCompletions())

        async def close(self) -> None:
            return None

    registry = llm_module.provider_client_registry
    original_factory = registry._client_factory
    registry.invalidate()
    config, token = configure_stage_provider_from_file(
        _provider_file(tmp_path, model="glm-5.2")
    )
    registry._client_factory = FakeRuntimeClient
    try:
        response = await llm_module.llm_client.chat(
            system_prompt="system",
            user_prompt="user",
            max_tokens=16,
            agent_id="provider-runtime-test",
            priority="critical",
        )
    finally:
        registry.invalidate()
        await registry.aclose_retired()
        registry._client_factory = original_factory
        reset_stage_provider_config(token)

    used = seen["config"]
    request = seen["request"]
    assert isinstance(used, ProviderRuntimeConfig)
    assert used.key_fingerprint == config.key_fingerprint
    assert used.model == "glm-5.2"
    assert used.thinking_mode == "disabled"
    assert isinstance(request, dict)
    assert request["model"] == "glm-5.2"
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert response.content == "ok"


@pytest.mark.asyncio
async def test_chat_releases_lease_when_provider_output_is_invalid() -> None:
    import nf_core.llm_client as llm_module

    config = _config(key="malformed-output")
    seen: dict[str, object] = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            del kwargs
            return SimpleNamespace(choices=[], usage=None)

    class FakeClient:
        def __init__(self, runtime: ProviderRuntimeConfig) -> None:
            del runtime
            self.chat = SimpleNamespace(completions=FakeCompletions())
            self.closed = False
            seen["client"] = self

        async def close(self) -> None:
            self.closed = True

    registry = llm_module.provider_client_registry
    original_factory = registry._client_factory
    registry.invalidate()
    await registry.aclose_retired()
    registry._client_factory = FakeClient
    token = set_stage_provider_config(config)
    try:
        with pytest.raises(provider_runtime_module.ProviderError) as raised:
            await llm_module.llm_client.chat(
                system_prompt="system",
                user_prompt="user",
                priority="critical",
            )
        assert raised.value.code == "PROVIDER_OUTPUT_INVALID"
        registry.invalidate(config)
        await registry.aclose_retired()
    finally:
        registry._client_factory = original_factory
        reset_stage_provider_config(token)

    client = seen["client"]
    assert client.closed is True
