"""Canonical past: seed beliefs become real, queryable events.

Genesis events are not commands: they describe facts/rumors that predate the
playable timeline. They occupy event ids 1..N so later actions can cite them
as true causes (e.g. taking a map because a rumor motivated the search).
"""

from __future__ import annotations

from world_core.events import WorldEvent
from world_core.models import WorldState


def assign_genesis(state: WorldState) -> None:
    """Assign contiguous genesis event ids to seeded beliefs."""
    beliefs = sorted(
        state.beliefs.values(),
        key=lambda belief: (belief.npc_id, belief.subject_key, belief.predicate),
    )
    for index, belief in enumerate(beliefs, start=1):
        belief.source_event_id = index
    state.last_event_id = len(beliefs)


def genesis_events(state: WorldState) -> list[WorldEvent]:
    beliefs = sorted(
        state.beliefs.values(),
        key=lambda belief: belief.source_event_id or 0,
    )
    events: list[WorldEvent] = []
    for belief in beliefs:
        if belief.source_event_id is None:
            raise ValueError("belief without genesis source; call assign_genesis first")
        events.append(
            WorldEvent(
                event_id=belief.source_event_id,
                world_id=state.world_id,
                tick=0,
                type="BELIEF_ACQUIRED",
                actor_ids=[belief.npc_id],
                causal_parent_ids=[],
                rng_seed=0,
                command_id=None,
                state_version_after=1,
                payload={
                    "subject_key": belief.subject_key,
                    "predicate": belief.predicate,
                    "object_value": belief.object_value,
                    "confidence": belief.confidence,
                },
            )
        )
    ids = [event.event_id for event in events]
    if ids != list(range(1, len(events) + 1)):
        raise ValueError("genesis event ids must be contiguous from 1")
    if state.last_event_id != len(events):
        raise ValueError("world last_event_id must equal the genesis event count")
    return events


__all__ = ["assign_genesis", "genesis_events"]
