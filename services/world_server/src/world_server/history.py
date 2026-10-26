"""Run the agent loop offline and persist the resulting history in one transaction."""

from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from agent_runtime import RivalryPolicy, build_observation, proposal_to_command
from world_core import (
    PLAYER_ID,
    WorldEvent,
    WorldState,
    advance_time,
    state_checksum,
    validate_state,
)
from world_core import (
    apply_command as core_apply,
)
from world_server.memory_store import record_event_memories
from world_server.models import (
    EventEdgeRow,
    WorldEventRow,
    WorldStateRow,
)


def reset_local_world(session: Session) -> None:
    session.execute(
        text(
            "TRUNCATE save, world_snapshot, command_log, event_edge, "
            "world_event, world_state, memory_episode, agent_decision CASCADE"
        )
    )
    session.commit()


def simulate_days(state: WorldState, days: int) -> list[WorldEvent]:
    policy = RivalryPolicy()
    events: list[WorldEvent] = []
    for _ in range(days):
        for npc in sorted(state.npcs.values(), key=lambda item: item.npc_id):
            if npc.npc_id == PLAYER_ID or not npc.alive or npc.active_action is not None:
                continue
            observation = build_observation(state, npc.npc_id)
            proposal = policy.decide(observation)
            command = proposal_to_command(state, proposal)
            events.extend(core_apply(state, command).events)
        advance = advance_time(state, 1)
        events.extend(advance.events)
    return events


def persist_history(session: Session, state: WorldState, events: list[WorldEvent]) -> None:
    if validate_state(state):
        raise ValueError(f"refusing to persist invalid state: {validate_state(state)}")
    row = session.execute(select(WorldStateRow).limit(1).with_for_update()).scalar_one_or_none()
    if row is None:
        raise ValueError("bootstrap the world before persisting history")

    for event in events:
        session.add(
            WorldEventRow(
                world_id=row.world_id,
                event_id=event.event_id,
                tick=event.tick,
                type=event.type,
                actor_ids=list(event.actor_ids),
                target_ids=list(event.target_ids),
                location_id=event.location_id,
                rng_seed=event.rng_seed,
                command_id=uuid.UUID(event.command_id) if event.command_id else None,
                state_version_after=event.state_version_after,
                payload=event.payload,
            )
        )
        for parent_id in event.causal_parent_ids:
            session.add(
                EventEdgeRow(
                    world_id=row.world_id,
                    parent_event_id=parent_id,
                    child_event_id=event.event_id,
                    relation="caused_by",
                )
            )
    record_event_memories(session, row.world_id, state, events)

    row.tick = state.tick
    row.state_version = state.state_version
    row.last_event_id = state.last_event_id
    row.checksum = state_checksum(state)
    row.state = state.model_dump(mode="json")
    session.commit()


__all__ = ["persist_history", "reset_local_world", "simulate_days"]
