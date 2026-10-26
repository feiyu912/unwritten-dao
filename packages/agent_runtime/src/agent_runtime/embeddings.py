"""Embedding providers and cosine similarity for episodic memory."""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from collections.abc import Sequence
from typing import Protocol

import httpx

from agent_runtime.providers import ProviderError

_WORD_RE = re.compile(r"[a-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


class EmbeddingProvider(Protocol):
    dim: int

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashingEmbeddingProvider:
    """Deterministic feature hashing; used to test the vector path offline.

    This is not a semantic model. It exists so the pgvector plumbing and
    cosine ranking can be exercised without network access.
    """

    def __init__(self, dim: int = 768) -> None:
        self.dim = dim

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _features(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class OpenAICompatibleEmbeddingProvider:
    dim: int
    name = "openai_embedding"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        dim: int = 768,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.dim = dim
        self.timeout = timeout
        self._transport = transport

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with httpx.Client(
                timeout=self.timeout, transport=self._transport, headers=headers
            ) as client:
                response = client.post(
                    f"{self.base_url}/embeddings",
                    json={"model": self.model, "input": list(texts)},
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"embedding request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(
                f"embedding endpoint returned {response.status_code}: {response.text[:300]}"
            )
        try:
            payload = response.json()
            rows = sorted(payload["data"], key=lambda row: row["index"])
            vectors = [row["embedding"] for row in rows]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("embedding response missing data[].embedding") from exc
        if len(vectors) != len(texts):
            raise ProviderError("embedding response length mismatch")
        return vectors


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def _features(text: str) -> set[str]:
    lowered = text.lower()
    words = set(_WORD_RE.findall(lowered))
    cjk = _CJK_RE.findall(lowered)
    bigrams = {"".join(pair) for pair in itertools.pairwise(cjk)}
    return words | bigrams


__all__ = [
    "EmbeddingProvider",
    "HashingEmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "cosine",
]
