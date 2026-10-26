"""Episodic memory storage and hybrid retrieval.

Semantic scoring is lexical in R1/R2 (character bigrams for CJK, words for
ASCII) so retrieval is deterministic and dependency-free. The store interface
is ready for a pgvector-backed implementation in the server.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from world_core.ruleset import RULESET

_WORD_RE = re.compile(r"[a-z0-9_]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def tokens(text: str) -> set[str]:
    lowered = text.lower()
    words = set(_WORD_RE.findall(lowered))
    cjk = _CJK_RE.findall(lowered)
    bigrams = {"".join(pair) for pair in itertools.pairwise(cjk)}
    return words | bigrams


@dataclass(frozen=True)
class MemoryEpisode:
    memory_id: int
    npc_id: str
    source_event_id: int
    summary: str
    importance: float
    emotional_valence: float
    created_tick: int
    related_npc_ids: tuple[str, ...] = ()
    embedding: tuple[float, ...] | None = None


class MemoryStore(Protocol):
    def add(self, episode: MemoryEpisode) -> None: ...

    def retrieve(
        self,
        *,
        npc_id: str,
        now_tick: int,
        query: str = "",
        person_ids: Sequence[str] = (),
        causal_event_ids: Sequence[int] = (),
        top_k: int = 5,
    ) -> list[MemoryEpisode]: ...


def score_memory(
    episode: MemoryEpisode,
    *,
    now_tick: int,
    query_tokens: set[str],
    person_ids: Sequence[str],
    causal_event_ids: Sequence[int],
    query_embedding: Sequence[float] | None = None,
) -> float:
    weights = RULESET.memory["score_weights"]
    summary_tokens = tokens(episode.summary)
    if query_embedding is not None and episode.embedding is not None:
        from agent_runtime.embeddings import cosine

        semantic = max(0.0, cosine(query_embedding, episode.embedding))
    elif query_tokens and summary_tokens:
        semantic = len(query_tokens & summary_tokens) / len(query_tokens | summary_tokens)
    else:
        semantic = 0.0
    age = max(0, now_tick - episode.created_tick)
    recency = 1.0 / (1.0 + age / 365.0)
    person = 1.0 if set(episode.related_npc_ids) & set(person_ids) else 0.0
    causal = 1.0 if episode.source_event_id in set(causal_event_ids) else 0.0
    score = (
        float(weights["semantic"]) * semantic
        + float(weights["recency"]) * recency
        + float(weights["importance"]) * max(0.0, min(1.0, episode.importance))
        + float(weights["person"]) * person
        + float(weights["causal"]) * causal
    )
    return round(score, 10)


class InMemoryEpisodeStore:
    """Deterministic store used by tests and headless replay."""

    def __init__(self, episodes: Iterable[MemoryEpisode] = ()) -> None:
        self._episodes: list[MemoryEpisode] = list(episodes)

    def add(self, episode: MemoryEpisode) -> None:
        self._episodes.append(episode)

    def retrieve(
        self,
        *,
        npc_id: str,
        now_tick: int,
        query: str = "",
        person_ids: Sequence[str] = (),
        causal_event_ids: Sequence[int] = (),
        query_embedding: Sequence[float] | None = None,
        top_k: int = 5,
    ) -> list[MemoryEpisode]:
        query_tokens = tokens(query)
        scored: list[tuple[float, MemoryEpisode]] = []
        for episode in self._episodes:
            if episode.npc_id != npc_id:
                continue
            scored.append(
                (
                    score_memory(
                        episode,
                        now_tick=now_tick,
                        query_tokens=query_tokens,
                        person_ids=person_ids,
                        causal_event_ids=causal_event_ids,
                        query_embedding=query_embedding,
                    ),
                    episode,
                )
            )
        scored.sort(key=lambda pair: (-pair[0], pair[1].memory_id))
        return [episode for _, episode in scored[: max(0, top_k)]]


__all__ = [
    "InMemoryEpisodeStore",
    "MemoryEpisode",
    "MemoryStore",
    "score_memory",
    "tokens",
]
