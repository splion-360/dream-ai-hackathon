from __future__ import annotations

import json

import httpx
import pytest

from math_tutor.generation import (
    GenerationConfig,
    NebiusTokenFactoryClient,
    ProviderError,
)

NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1"


def test_generate_sends_frozen_decoding_config_and_preserves_usage() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers["authorization"]
        observed["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-123",
                "model": "Qwen/Qwen3-4B",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "```python\nfrom manim import *\n```",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 23,
                    "completion_tokens": 11,
                    "total_tokens": 34,
                },
            },
        )

    config = GenerationConfig()
    client = NebiusTokenFactoryClient(
        api_key="nebius-secret",
        config=config,
        base_url=NEBIUS_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    result = client.generate("Explain a derivative visually.")

    assert observed == {
        "url": "https://api.tokenfactory.nebius.com/v1/chat/completions",
        "authorization": "Bearer nebius-secret",
        "payload": {
            "model": "Qwen/Qwen3-4B",
            "messages": [
                {"role": "system", "content": config.system_prompt},
                {"role": "user", "content": "Explain a derivative visually."},
            ],
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 4096,
            "seed": 42,
        },
    }
    assert result.content == "```python\nfrom manim import *\n```"
    assert result.model == "Qwen/Qwen3-4B"
    assert result.request_id == "chatcmpl-123"
    assert result.finish_reason == "stop"
    assert result.usage.prompt_tokens == 23
    assert result.usage.completion_tokens == 11
    assert result.usage.total_tokens == 34
    assert result.elapsed_seconds >= 0
    assert json.loads(result.provider_response)["id"] == "chatcmpl-123"


def test_system_prompt_requires_imports_for_every_referenced_module() -> None:
    config = GenerationConfig()

    assert "Start the code with exactly these three lines" in config.system_prompt
    assert "from manim import *\nimport math\nimport numpy as np" in config.system_prompt


def test_health_distinguishes_reachable_api_from_unavailable_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "Qwen/Qwen3-30B-A3B-Instruct-2507"}]},
        )

    client = NebiusTokenFactoryClient(
        api_key="nebius-secret",
        config=GenerationConfig(),
        base_url=NEBIUS_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    health = client.health()

    assert health.reachable is True
    assert health.model == "Qwen/Qwen3-4B"
    assert health.model_available is False
    assert health.error is None


def test_provider_error_does_not_expose_credentials_or_response_body() -> None:
    secret = "nebius-do-not-leak"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"rejected credential {secret}")

    client = NebiusTokenFactoryClient(
        api_key=secret,
        config=GenerationConfig(),
        base_url=NEBIUS_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError) as caught:
        client.generate("Prompt")

    assert str(caught.value) == "Nebius generation request failed with HTTP 401"
    assert secret not in str(caught.value)


def test_malformed_success_response_is_a_sanitized_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "chatcmpl-broken", "choices": []})

    client = NebiusTokenFactoryClient(
        api_key="nebius-secret",
        config=GenerationConfig(),
        base_url=NEBIUS_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderError, match="malformed response"):
        client.generate("Prompt")
