from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from api import routes
from api.llm_routes import _one_shot_complete
from middleware.user_llm import UserLLMHeadersMiddleware
import nf_core.provider_runtime as provider_runtime_module
from nf_core.llm_client import LLMResponse
from nf_core.provider_runtime import (
    ProviderError,
    ProviderRuntimeConfig,
    provider_client_registry,
    reset_request_provider_config,
    set_request_provider_config,
)


def _config() -> ProviderRuntimeConfig:
    return ProviderRuntimeConfig.from_explicit(
        provider="custom",
        api_key="api-secret-must-not-render",
        base_url="https://provider.invalid/v1",
        model="glm-5.2",
        thinking_mode="disabled",
        timeout=30,
        max_retries=0,
        source="request",
    )


@pytest.mark.asyncio
async def test_provider_catalog_is_public_and_credential_free() -> None:
    payload = await routes.get_llm_providers_route(current_user=object())

    assert payload["providers"]
    assert {"provider", "label", "default_base_url", "default_model"} == set(
        payload["providers"][0]
    )
    rendered = json.dumps(payload)
    assert "api_key" not in rendered
    assert "credential" not in rendered


@pytest.mark.asyncio
async def test_runtime_endpoint_is_redacted() -> None:
    config = _config()
    token = set_request_provider_config(config)
    try:
        payload = await routes.get_llm_runtime_route(current_user=object())
    finally:
        reset_request_provider_config(token)

    rendered = json.dumps(payload)
    assert payload["provider"] == "custom"
    assert payload["model"] == "glm-5.2"
    assert payload["thinking_mode"] == "disabled"
    assert payload["key_fingerprint"] == config.key_fingerprint
    assert len(payload["key_fingerprint"]) == 8
    assert "api-secret-must-not-render" not in rendered
    assert "https://provider.invalid/v1" not in rendered
    assert "base_url" not in payload


@pytest.mark.asyncio
async def test_probe_success_uses_current_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nf_core.llm_client import llm_client

    async def fake_chat(**kwargs):
        assert kwargs["max_tokens"] == 16
        return LLMResponse(
            content="OK",
            usage_prompt_tokens=3,
            usage_completion_tokens=1,
        )

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    config = _config()
    cache_size_before = provider_client_registry.cache_size
    token = set_request_provider_config(config)
    try:
        payload = await routes.probe_llm_runtime_route(
            routes.LLMProbeRequest(),
            current_user=object(),
        )
    finally:
        reset_request_provider_config(token)

    assert payload["success"] is True
    assert payload["code"] == "OK"
    assert payload["prompt_tokens"] == 3
    assert payload["completion_tokens"] == 1
    assert payload["config_fingerprint"] == config.config_fingerprint
    assert provider_client_registry.cache_size == cache_size_before


@pytest.mark.parametrize(
    ("code", "http_status", "http_category", "upstream_status"),
    [
        ("PROVIDER_AUTH_FAILED", 424, "auth", 401),
        ("PROVIDER_RATE_LIMITED", 429, "rate_limit", 429),
        ("PROVIDER_UNAVAILABLE", 502, "unavailable", 503),
    ],
)
@pytest.mark.asyncio
async def test_probe_provider_failures_have_one_flat_safe_contract(
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    http_status: int,
    http_category: str,
    upstream_status: int,
) -> None:
    from nf_core.llm_client import llm_client

    config = _config()
    raw_sensitive_message = (
        "Authorization: Bearer api-secret-must-not-render; "
        "url=https://provider.invalid/v1; prompt=never-render-this; "
        "response=raw-upstream-body"
    )

    async def fake_chat(**kwargs):
        del kwargs
        raise ProviderError(
            code=code,
            message=raw_sensitive_message,
            http_status=http_status,
            http_category=http_category,
            config=config,
            upstream_status=upstream_status,
        )

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    token = set_request_provider_config(config)
    try:
        with pytest.raises(HTTPException) as raised:
            await routes.probe_llm_runtime_route(
                routes.LLMProbeRequest(),
                current_user=object(),
            )
    finally:
        reset_request_provider_config(token)

    assert raised.value.status_code == http_status
    detail = raised.value.detail
    assert detail["success"] is False
    assert detail["http_category"] == http_category
    assert detail["code"] == code
    assert detail["provider"] == "custom"
    assert detail["model"] == "glm-5.2"
    assert detail["source"] == "request"
    assert detail["config_fingerprint"] == config.config_fingerprint
    assert detail["prompt_tokens"] == 0
    assert detail["completion_tokens"] == 0
    assert isinstance(detail["latency_ms"], (int, float))
    assert detail["latency_ms"] >= 0
    rendered = json.dumps(detail)
    for forbidden in (
        "api-secret-must-not-render",
        "https://provider.invalid/v1",
        "Authorization",
        "Bearer",
        "never-render-this",
        "raw-upstream-body",
    ):
        assert forbidden not in rendered


@pytest.mark.asyncio
async def test_user_one_shot_does_not_cache_request_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from nf_core.llm_client import llm_client

    async def fake_chat(**kwargs):
        assert kwargs["provider_config"].source == "request"
        assert kwargs["client_override"] is not None
        return LLMResponse(
            content="OK",
            usage_prompt_tokens=1,
            usage_completion_tokens=1,
        )

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    config = _config()
    token = set_request_provider_config(config)
    before = provider_client_registry.cache_size
    try:
        result = await _one_shot_complete(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            system_prompt="system",
            user_prompt="user",
        )
    finally:
        reset_request_provider_config(token)

    assert result == "OK"
    assert provider_client_registry.cache_size == before


def _request_runtime_test_app() -> Starlette:
    async def inspect_runtime(request):
        del request
        current = provider_runtime_module.get_request_provider_config()
        assert current is not None
        return JSONResponse(
            {
                "provider": current.provider,
                "base_url": current.base_url,
                "model": current.model,
            }
        )

    app = Starlette(routes=[Route("/", inspect_runtime)])
    app.add_middleware(UserLLMHeadersMiddleware)
    return app


def _cors_request_runtime_test_app() -> Starlette:
    app = _request_runtime_test_app()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://author.example"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


def test_request_headers_use_named_provider_defaults_atomically(
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

    with TestClient(_request_runtime_test_app()) as client:
        response = client.get(
            "/",
            headers={
                "X-User-LLM-Key": "request-only-key",
                "X-User-LLM-Provider": "openai",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai",
        "base_url": "https://openai.example/v1",
        "model": "openai-model",
    }
    assert provider_runtime_module.get_request_provider_config() is None


def test_request_headers_reject_unsafe_url_without_fallback() -> None:
    with TestClient(_request_runtime_test_app()) as client:
        response = client.get(
            "/",
            headers={
                "X-User-LLM-Key": "request-only-key",
                "X-User-LLM-Base-Url": "http://127.0.0.1:9999/v1",
                "X-User-LLM-Model": "unsafe-model",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROVIDER_BASE_URL_UNSAFE"
    assert "127.0.0.1" not in response.text


def test_middleware_provider_error_remains_readable_through_cors() -> None:
    with TestClient(_cors_request_runtime_test_app()) as client:
        response = client.get(
            "/",
            headers={
                "Origin": "https://author.example",
                "X-User-LLM-Key": "request-only-key",
                "X-User-LLM-Base-Url": "http://127.0.0.1:9999/v1",
                "X-User-LLM-Model": "unsafe-model",
            },
        )

    assert response.status_code == 400
    assert response.headers["access-control-allow-origin"] == (
        "https://author.example"
    )
    assert response.json()["detail"]["code"] == "PROVIDER_BASE_URL_UNSAFE"


def test_request_headers_reject_invalid_numeric_config_as_4xx() -> None:
    with TestClient(_request_runtime_test_app()) as client:
        response = client.get(
            "/",
            headers={
                "X-User-LLM-Key": "request-only-key",
                "X-User-LLM-Timeout": "-1",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PROVIDER_CONFIG_INVALID"


@pytest.mark.parametrize(
    ("header", "value"),
    [
        ("X-User-LLM-Timeout", "0"),
        ("X-User-LLM-Max-Retries", "0"),
    ],
)
def test_request_config_header_requires_key_even_when_numeric_value_is_zero(
    header: str,
    value: str,
) -> None:
    with TestClient(_request_runtime_test_app()) as client:
        response = client.get("/", headers={header: value})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PROVIDER_CREDENTIAL_REQUIRED"
