"""Embedding provider selection for memory indexing."""

from __future__ import annotations

import os

from agent_runtime import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)

DIM = 768


def build_embedding_provider() -> EmbeddingProvider | None:
    mode = os.environ.get("EMBEDDING_PROVIDER", "off").strip().lower()
    if mode in {"hash", "hashing"}:
        return HashingEmbeddingProvider(dim=DIM)
    if mode == "openai":
        base_url = os.environ.get("EMBEDDING_BASE_URL") or os.environ.get("LLM_BASE_URL")
        model = os.environ.get("EMBEDDING_MODEL")
        if not base_url or not model:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=openai requires EMBEDDING_BASE_URL (or LLM_BASE_URL) "
                "and EMBEDDING_MODEL"
            )
        dim = int(os.environ.get("EMBEDDING_DIM", str(DIM)))
        if dim != DIM:
            raise RuntimeError(f"embedding dim must be {DIM} to match memory_episode")
        return OpenAICompatibleEmbeddingProvider(
            base_url=base_url,
            model=model,
            api_key=os.environ.get("EMBEDDING_API_KEY") or os.environ.get("LLM_API_KEY"),
            dim=dim,
        )
    return None


__all__ = ["DIM", "build_embedding_provider"]
