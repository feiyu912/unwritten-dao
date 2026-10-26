from __future__ import annotations

import json

import httpx

from agent_runtime import (
    HashingEmbeddingProvider,
    InMemoryEpisodeStore,
    MemoryEpisode,
    OpenAICompatibleEmbeddingProvider,
    cosine,
)


def test_hashing_embeddings_are_deterministic_and_normalized() -> None:
    provider = HashingEmbeddingProvider(dim=64)
    first = provider.embed_many(["洞府 筑基丹", "黑市 灵石"])[0]
    second = provider.embed_many(["洞府 筑基丹"])[0]
    assert first == second
    assert len(first) == 64
    assert abs(sum(value * value for value in first) ** 0.5 - 1.0) < 1e-9


def test_cosine_ranks_aligned_vectors_higher() -> None:
    query = [1.0, 0.0]
    aligned = [0.9, 0.1]
    orthogonal = [0.0, 1.0]
    assert cosine(query, aligned) > cosine(query, orthogonal)
    assert cosine([0.0, 0.0], orthogonal) == 0.0


def test_openai_embedding_provider_orders_by_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body == {"model": "embed-model", "input": ["a", "b"]}
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    provider = OpenAICompatibleEmbeddingProvider(
        base_url="http://127.0.0.1:8080/v1",
        model="embed-model",
        dim=2,
        transport=httpx.MockTransport(handler),
    )
    vectors = provider.embed_many(["a", "b"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]


def test_memory_uses_query_embedding_when_available() -> None:
    store = InMemoryEpisodeStore(
        [
            MemoryEpisode(1, "npc", 1, "rune cave", 0.5, 0.0, 0, embedding=(1.0, 0.0)),
            MemoryEpisode(2, "npc", 2, "market stall", 0.5, 0.0, 0, embedding=(0.0, 1.0)),
        ]
    )
    hits = store.retrieve(
        npc_id="npc",
        now_tick=0,
        query="",
        query_embedding=[1.0, 0.0],
        top_k=2,
    )
    assert hits[0].memory_id == 1
