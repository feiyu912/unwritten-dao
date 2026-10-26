"""Turn committed events into episodic memories and retrieve them per NPC."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from world_core.events import WorldEvent
from world_core.models import WorldState
from world_core.ruleset import RULESET

from agent_runtime import InMemoryEpisodeStore, MemoryEpisode
from world_server.embeddings import build_embedding_provider
from world_server.models import MemoryEpisodeRow
from world_server.summaries import summarize_event

LOGGER = logging.getLogger(__name__)

# event type -> (importance, emotional valence); absent types are not remembered
_MEMORY_RULES: dict[str, tuple[float, float]] = {
    "ITEM_TRANSFERRED": (0.5, 0.1),
    "ITEM_CONSUMED": (0.45, 0.0),
    "LOCATION_INVESTIGATED": (0.35, 0.0),
    "SECRET_REALM_DISCOVERED": (0.9, 0.7),
    "SECRET_REALM_ENTERED": (0.7, 0.4),
    "SECRET_REALM_CLOSED": (0.5, -0.2),
    "OPPORTUNITY_CLAIMED": (0.8, 0.0),
    "BREAKTHROUGH_ATTEMPT": (0.9, 0.0),
    "NPC_DIED": (1.0, -0.9),
    "COMBAT_RESOLVED": (0.85, -0.5),
    "RELATIONSHIP_CHANGED": (0.4, -0.1),
    "BELIEF_ACQUIRED": (0.35, 0.0),
    "KNOWLEDGE_ACQUIRED": (0.35, 0.0),
    "CULTIVATION_COMPLETED": (0.25, 0.1),
}


def _valence(event_type: str, payload: dict[str, Any], base: float) -> float:
    if event_type == "OPPORTUNITY_CLAIMED":
        return 0.6 if payload.get("success") else -0.3
    if event_type == "BREAKTHROUGH_ATTEMPT":
        return 0.7 if payload.get("success") else -0.6
    return base


def memory_candidates(state: WorldState, event: WorldEvent) -> list[tuple[str, str, float, float]]:
    rule = _MEMORY_RULES.get(event.type)
    if rule is None:
        return []
    importance, base_valence = rule
    summary = summarize_event(event.type, event.payload, state)
    valence = _valence(event.type, event.payload, base_valence)
    npc_ids = sorted(set(event.actor_ids) | set(event.target_ids))
    return [(npc_id, summary, importance, valence) for npc_id in npc_ids]


def record_event_memories(
    session: Session, world_id: uuid.UUID, state: WorldState, events: list[WorldEvent]
) -> None:
    """Insert memories for the events of one committed command (same transaction)."""
    if not events:
        return
    event_ids = [event.event_id for event in events]
    existing: set[tuple[uuid.UUID, int]] = {
        (row[0], row[1])
        for row in session.execute(
            select(MemoryEpisodeRow.npc_id, MemoryEpisodeRow.source_event_id).where(
                MemoryEpisodeRow.source_event_id.in_(event_ids)
            )
        ).all()
    }
    candidates: list[tuple[str, str, float, float, int, int]] = []
    for event in events:
        for npc_id, summary, importance, valence in memory_candidates(state, event):
            key = (uuid.UUID(npc_id), event.event_id)
            if key in existing:
                continue
            existing.add(key)
            candidates.append((npc_id, summary, importance, valence, event.event_id, event.tick))
    if not candidates:
        return
    embeddings: list[list[float] | None] = [None] * len(candidates)
    provider = build_embedding_provider()
    if provider is not None:
        try:
            vectors = provider.embed_many([row[1] for row in candidates])
            embeddings = [list(vector) for vector in vectors]
        except Exception as exc:  # derived index only; never fail the world transaction
            LOGGER.warning("memory embedding failed, storing rows without vectors: %s", exc)
    for (npc_id, summary, importance, valence, event_id, event_tick), embedding in zip(
        candidates, embeddings, strict=True
    ):
        session.add(
            MemoryEpisodeRow(
                npc_id=uuid.UUID(npc_id),
                source_event_id=event_id,
                summary=summary,
                importance=importance,
                emotional_valence=valence,
                created_tick=event_tick,
                embedding=embedding,
            )
        )


def retrieve_memories(
    session: Session,
    state: WorldState,
    npc_id: str,
    *,
    recent_event_ids: list[int] | None = None,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(MemoryEpisodeRow)
            .where(MemoryEpisodeRow.npc_id == uuid.UUID(npc_id))
            .order_by(MemoryEpisodeRow.created_tick.desc(), MemoryEpisodeRow.memory_id.desc())
            .limit(200)
        )
        .scalars()
        .all()
    )
    if not rows:
        return []
    episodes = [
        MemoryEpisode(
            memory_id=row.memory_id,
            npc_id=str(row.npc_id),
            source_event_id=row.source_event_id,
            summary=row.summary,
            importance=row.importance,
            emotional_valence=row.emotional_valence,
            created_tick=row.created_tick,
            embedding=tuple(row.embedding) if row.embedding is not None else None,
        )
        for row in rows
    ]
    store = InMemoryEpisodeStore(episodes)
    query = " ".join(goal.kind for goal in state.npcs[npc_id].goals if goal.status == "active")
    query_embedding = None
    provider = build_embedding_provider()
    if provider is not None:
        try:
            query_embedding = provider.embed_many([query or "memory"])[0]
        except Exception as exc:
            LOGGER.warning("query embedding failed, falling back to lexical: %s", exc)
    hits = store.retrieve(
        npc_id=npc_id,
        now_tick=state.tick,
        query=query,
        causal_event_ids=recent_event_ids or [],
        query_embedding=query_embedding,
        top_k=top_k or int(RULESET.memory["recall_top_k"]),
    )
    return [
        {
            "event_id": episode.source_event_id,
            "tick": episode.created_tick,
            "summary": episode.summary,
            "importance": episode.importance,
            "emotional_valence": episode.emotional_valence,
        }
        for episode in hits
    ]


__all__ = ["memory_candidates", "record_event_memories", "retrieve_memories"]
