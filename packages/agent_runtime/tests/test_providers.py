from __future__ import annotations

import json

import httpx
import pytest
from agent_runtime.providers import OpenAICompatibleProvider, ProviderError


def _completion(content: str) -> dict[str, object]:
    return {
        "id": "cmpl-1",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }


def test_openai_compatible_provider_sends_expected_request() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion('{"intent":"wait"}'))

    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:8080/v1/",
        model="local-model",
        api_key="secret-token",
        transport=httpx.MockTransport(handler),
    )
    reply = provider.complete(system="sys", user="usr")

    assert reply == '{"intent":"wait"}'
    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert captured["auth"] == "Bearer secret-token"
    body = captured["body"]
    assert body["model"] == "local-model"
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    assert body["response_format"] == {"type": "json_object"}


def test_openai_compatible_provider_omits_authorization_without_key() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=_completion("{}"))

    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:8080/v1",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    provider.complete(system="s", user="u")
    assert captured["auth"] is None


def test_openai_compatible_provider_raises_on_error_status() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:8080/v1",
        model="m",
        transport=httpx.MockTransport(lambda request: httpx.Response(503, text="busy")),
    )
    with pytest.raises(ProviderError) as error:
        provider.complete(system="s", user="u")
    assert "503" in str(error.value)


def test_openai_compatible_provider_raises_on_bad_payload() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:8080/v1",
        model="m",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []})),
    )
    with pytest.raises(ProviderError):
        provider.complete(system="s", user="u")


def test_openai_compatible_provider_raises_on_empty_content() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:8080/v1",
        model="m",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=_completion("   "))),
    )
    with pytest.raises(ProviderError):
        provider.complete(system="s", user="u")
