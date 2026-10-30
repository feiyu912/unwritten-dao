"""OpenAI-compatible inference provider.

Works with hosted chat-completions APIs and local servers (llama.cpp / vLLM)
that expose the same shape. Never logs credentials.
"""

from __future__ import annotations

from collections.abc import Mapping
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
        extra_headers: Mapping[str, str] | None = None,
        user_agent: str = "unwritten-dao/0.1",
        reasoning_effort: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self._transport = transport
        self.extra_headers = dict(extra_headers or {})
        self.user_agent = user_agent
        self.reasoning_effort = reasoning_effort

    def complete(self, *, system: str, user: str) -> str:
        return self._chat(system=system, user=user, json_mode=True)

    def complete_text(self, *, system: str, user: str) -> str:
        return self._chat(system=system, user=user, json_mode=False)

    def _chat(self, *, system: str, user: str, json_mode: bool) -> str:
        headers = {"Content-Type": "application/json", "User-Agent": self.user_agent}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
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
