"""Narrative director helpers: rank real causal chains, never invent events."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from world_core.events import WorldEvent

IMPORTANCE: dict[str, float] = {
    "NPC_DIED": 1.0,
    "BREAKTHROUGH_ATTEMPT": 0.9,
    "SECRET_REALM_DISCOVERED": 0.9,
    "OPPORTUNITY_CLAIMED": 0.8,
    "COMBAT_RESOLVED": 0.8,
    "SECRET_REALM_ENTERED": 0.7,
    "ITEM_TRANSFERRED": 0.5,
    "SECRET_REALM_CLOSED": 0.4,
    "RELATIONSHIP_CHANGED": 0.3,
}


@dataclass(frozen=True)
class StoryThread:
    event_ids: tuple[int, ...]
    score: float
    headline: str


def find_story_threads(
    events: Iterable[WorldEvent],
    *,
    max_threads: int = 5,
    max_depth: int = 8,
    min_events: int = 3,
) -> list[StoryThread]:
    """Backtrack causal parents from important leaf events into ranked threads."""
    index = {event.event_id: event for event in events}
    leaves = sorted(
        (event for event in index.values() if event.type in IMPORTANCE),
        key=lambda event: (-IMPORTANCE[event.type], event.event_id),
    )
    threads: dict[int, StoryThread] = {}
    for leaf in leaves:
        chain: list[WorldEvent] = []
        node: WorldEvent | None = leaf
        seen: set[int] = set()
        while node is not None and node.event_id not in seen and len(chain) < max_depth:
            seen.add(node.event_id)
            chain.append(node)
            parent_id = node.causal_parent_ids[0] if node.causal_parent_ids else None
            node = index.get(parent_id) if parent_id is not None else None
        if len(chain) < min_events:
            continue
        chain.reverse()
        key = tuple(event.event_id for event in chain)
        score = round(
            sum(IMPORTANCE.get(event.type, 0.1) for event in chain) + 0.1 * len(chain),
            4,
        )
        headline = (
            f"{chain[0].type} → … → {chain[-1].type} (E{chain[0].event_id}…E{chain[-1].event_id})"
        )
        root = chain[0].event_id
        existing = threads.get(root)
        if existing is None or score > existing.score:
            threads[root] = StoryThread(event_ids=key, score=score, headline=headline)

    ordered = sorted(threads.values(), key=lambda thread: (-thread.score, thread.event_ids))
    return ordered[: max(0, max_threads)]


__all__ = ["IMPORTANCE", "StoryThread", "find_story_threads"]
