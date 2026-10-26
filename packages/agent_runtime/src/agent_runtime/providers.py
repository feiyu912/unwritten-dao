"""OpenAI-compatible inference provider.

Works with hosted chat-completions APIs and local servers (llama.cpp / vLLM)
that expose the same shape. Never logs credentials.
"""

from __future__ import annotations

from typing import Any

import httpx


class ProviderError(RuntimeError):
    """The inference endpoint failed or returned an unusable payload."""


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 20.0,
        temperature: float = 0.2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self._transport = transport

    def complete(self, *, system: str, user: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self._transport,
                headers=headers,
            ) as client:
                response = client.post(f"{self.base_url}/chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise ProviderError(f"inference request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(
                f"inference endpoint returned {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("inference response missing choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("inference response content is empty")
        return content


__all__ = ["OpenAICompatibleProvider", "ProviderError"]
