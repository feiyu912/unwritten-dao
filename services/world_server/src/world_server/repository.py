"""Transactional persistence between world_core and PostgreSQL."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from world_core.commands import CommandResult
from world_core.events import WorldEvent

from world_core import CommandRejected, WorldCommand, WorldState, state_checksum
from world_core import apply_command as core_apply
from world_core import create_world as core_create_world
from world_core import snapshot as core_snapshot
from world_server.memory_store import record_event_memories
from world_server.models import (
    AgentDecisionRow,
    CommandLogRow,
    EventEdgeRow,
    SaveRow,
    WorldEventRow,
    WorldSnapshotRow,
    WorldStateRow,
)


class StaleStateVersion(Exception):
    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"expected state version {expected}, actual {actual}")
        self.expected = expected
        self.actual = actual


class IdempotencyConflict(Exception):
    def __init__(self, command_id: str) -> None:
        super().__init__(f"command_id {command_id} reused under a different idempotency key")
        self.command_id = command_id


class NotFound(Exception):
    pass


@dataclass(frozen=True)
class CausalChain:
    root_event_id: int
    events: list[WorldEvent]
    edges: list[dict[str, object]]


def bootstrap(session: Session, seed: int = 42) -> WorldState:
    """Create and persist the seed world if no world exists."""
    row = session.execute(select(WorldStateRow).limit(1)).scalar_one_or_none()
    if row is not None:
        return _state_from_row(row)
    state = core_create_world(seed)
    row = WorldStateRow(
        world_id=uuid.UUID(state.world_id),
        seed=state.world_seed,
        tick=state.tick,
        state_version=state.state_version,
        last_event_id=state.last_event_id,
        checksum=state_checksum(state),
        state=state.model_dump(mode="json"),
    )
    session.add(row)
    session.commit()
    return state


def load_state(session: Session) -> WorldState:
    row = _locked_world_row(session)
    return _state_from_row(row)


def apply_command(session: Session, command: WorldCommand) -> CommandResult:
    """Apply one command atomically; commit on success, rollback on rejection."""
    row = _locked_world_row(session)
    if command.world_id != str(row.world_id):
        raise CommandRejected("unknown_world", "command targets a different world")

    duplicate = session.execute(
        select(CommandLogRow).where(
            CommandLogRow.world_id == row.world_id,
            CommandLogRow.idempotency_key == command.idempotency_key,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        return CommandResult.model_validate(duplicate.response)

    if command.expected_state_version != row.state_version:
        raise StaleStateVersion(command.expected_state_version, row.state_version)

    command_id_conflict = session.execute(
        select(CommandLogRow.idempotency_key).where(
            CommandLogRow.world_id == row.world_id,
            CommandLogRow.command_id == uuid.UUID(command.command_id),
        )
    ).scalar_one_or_none()
    if command_id_conflict is not None and command_id_conflict != command.idempotency_key:
        raise IdempotencyConflict(command.command_id)

    state = _state_from_row(row)
    try:
        result = core_apply(state, command)
    except CommandRejected:
        session.rollback()
        raise

    for event in result.events:
        session.add(_event_row(row.world_id, event))
        for parent_id in event.causal_parent_ids:
            session.add(
                EventEdgeRow(
                    world_id=row.world_id,
                    parent_event_id=parent_id,
                    child_event_id=event.event_id,
                    relation="caused_by",
                )
            )
    record_event_memories(session, row.world_id, state, result.events)
    row.tick = state.tick
    row.state_version = result.state_version
    row.last_event_id = state.last_event_id
    row.checksum = state_checksum(state)
    row.state = state.model_dump(mode="json")
    session.add(
        CommandLogRow(
            world_id=row.world_id,
            idempotency_key=command.idempotency_key,
            command_id=uuid.UUID(command.command_id),
            accepted=result.accepted,
            state_version_after=result.state_version,
            response=result.model_dump(mode="json"),
        )
    )
    session.commit()
    return result


def list_events(
    session: Session,
    *,
    after: int = 0,
    limit: int = 200,
    event_type: str | None = None,
) -> list[WorldEvent]:
    query = (
        select(WorldEventRow)
        .order_by(WorldEventRow.event_id.asc())
        .where(WorldEventRow.event_id > after)
    )
    if event_type is not None:
        query = query.where(WorldEventRow.type == event_type)
    rows = session.execute(query.limit(limit)).scalars().all()
    return _events_from_rows(session, rows)


def save_snapshot(session: Session, *, label: str | None = None) -> dict[str, object]:
    row = _locked_world_row(session)
    snapshot = WorldSnapshotRow(
        world_id=row.world_id,
        tick=row.tick,
        last_event_id=row.last_event_id,
        state_version=row.state_version,
        world_seed=row.seed,
        sim_version=row.state["sim_version"],
        ruleset_version=row.state["ruleset_version"],
        checksum=row.checksum,
        state=row.state,
    )
    session.add(snapshot)
    session.flush()
    save = SaveRow(world_id=row.world_id, snapshot_id=snapshot.snapshot_id, label=label)
    session.add(save)
    session.commit()
    return {
        "save_id": str(save.save_id),
        "snapshot_id": str(snapshot.snapshot_id),
        "tick": row.tick,
        "checksum": row.checksum,
    }


def load_snapshot(session: Session, save_id: str) -> dict[str, object]:
    save = session.execute(
        select(SaveRow).where(SaveRow.save_id == uuid.UUID(save_id))
    ).scalar_one_or_none()
    if save is None:
        raise NotFound(f"unknown save {save_id}")
    snapshot = session.execute(
        select(WorldSnapshotRow).where(WorldSnapshotRow.snapshot_id == save.snapshot_id)
    ).scalar_one()
    row = _locked_world_row(session)
    _delete_after(session, row.world_id, snapshot.last_event_id, snapshot.state_version)
    row.tick = snapshot.tick
    row.state_version = snapshot.state_version
    row.last_event_id = snapshot.last_event_id
    row.checksum = snapshot.checksum
    row.state = snapshot.state
    session.commit()
    return core_snapshot(WorldState.model_validate(snapshot.state))


def causality(session: Session, event_id: int, *, depth: int = 8) -> CausalChain:
    world_row = session.execute(select(WorldStateRow).limit(1)).scalar_one_or_none()
    if world_row is None:
        raise NotFound("no world exists")
    edge_map: dict[int, list[tuple[int, str]]] = {}
    frontier = [event_id]
    seen_edges: set[tuple[int, int]] = set()
    for _ in range(depth):
        if not frontier:
            break
        parents = (
            session.execute(
                select(EventEdgeRow).where(
                    EventEdgeRow.world_id == world_row.world_id,
                    EventEdgeRow.child_event_id.in_(frontier),
                )
            )
            .scalars()
            .all()
        )
        next_frontier: list[int] = []
        for edge in parents:
            if (edge.parent_event_id, edge.child_event_id) in seen_edges:
                continue
            seen_edges.add((edge.parent_event_id, edge.child_event_id))
            edge_map.setdefault(edge.child_event_id, []).append(
                (edge.parent_event_id, edge.relation)
            )
            next_frontier.append(edge.parent_event_id)
        frontier = sorted(set(next_frontier))
    rows = (
        session.execute(
            select(WorldEventRow).where(
                WorldEventRow.world_id == world_row.world_id,
                WorldEventRow.event_id.in_([event_id, *seen_parent_ids(seen_edges)]),
            )
        )
        .scalars()
        .all()
    )
    collected = {row.event_id: row for row in rows}
    if event_id not in collected:
        raise NotFound(f"unknown event {event_id}")
    return CausalChain(
        root_event_id=event_id,
        events=_events_from_rows(session, sorted(collected.values(), key=lambda r: r.event_id)),
        edges=[
            {
                "parent_event_id": parent,
                "child_event_id": child,
                "relation": next(rel for p, rel in edge_map[child] if p == parent),
            }
            for parent, child in sorted(seen_edges, key=lambda pair: pair[1])
        ],
    )


def seen_parent_ids(edges: set[tuple[int, int]]) -> list[int]:
    return sorted({parent for parent, _child in edges})


def _locked_world_row(session: Session) -> WorldStateRow:
    row = session.execute(select(WorldStateRow).limit(1).with_for_update()).scalar_one_or_none()
    if row is None:
        raise NotFound("no world exists; bootstrap first")
    return row


def _state_from_row(row: WorldStateRow) -> WorldState:
    state = WorldState.model_validate(row.state)
    expected = state_checksum(state)
    if expected != row.checksum:
        raise ValueError(f"persisted world checksum mismatch: {row.checksum} != {expected}")
    return state


def _event_row(world_id: uuid.UUID, event: WorldEvent) -> WorldEventRow:
    return WorldEventRow(
        world_id=world_id,
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


def _events_from_rows(session: Session, rows: list[WorldEventRow]) -> list[WorldEvent]:
    if not rows:
        return []
    event_ids = [row.event_id for row in rows]
    parent_rows = (
        session.execute(
            select(EventEdgeRow).where(
                EventEdgeRow.world_id == rows[0].world_id,
                EventEdgeRow.child_event_id.in_(event_ids),
            )
        )
        .scalars()
        .all()
    )
    parents: dict[int, list[int]] = {}
    for edge in parent_rows:
        parents.setdefault(edge.child_event_id, []).append(edge.parent_event_id)
    events: list[WorldEvent] = []
    for row in rows:
        events.append(
            WorldEvent(
                event_id=row.event_id,
                world_id=str(row.world_id),
                tick=row.tick,
                type=row.type,  # type: ignore[arg-type]
                actor_ids=list(row.actor_ids),
                target_ids=list(row.target_ids),
                location_id=row.location_id,
                causal_parent_ids=sorted(parents.get(row.event_id, [])),
                rng_seed=row.rng_seed,
                command_id=str(row.command_id) if row.command_id else None,
                state_version_after=row.state_version_after,
                payload=row.payload,
            )
        )
    return events


def _delete_after(
    session: Session, world_id: uuid.UUID, last_event_id: int, state_version: int
) -> None:
    session.execute(
        delete(EventEdgeRow).where(
            EventEdgeRow.world_id == world_id,
            EventEdgeRow.child_event_id > last_event_id,
        )
    )
    session.execute(
        delete(WorldEventRow).where(
            WorldEventRow.world_id == world_id,
            WorldEventRow.event_id > last_event_id,
        )
    )
    session.execute(
        delete(CommandLogRow).where(
            CommandLogRow.world_id == world_id,
            CommandLogRow.state_version_after > state_version,
        )
    )


def save_decisions(
    session: Session,
    *,
    world_id: str,
    records: list[object],
    proposal: object | None,
) -> None:
    """Persist decision audit records; the proposal is stored on accepted rows."""
    proposal_payload = None
    if proposal is not None and hasattr(proposal, "model_dump"):
        proposal_payload = proposal.model_dump(mode="json")  # type: ignore[union-attr]
    for record in records:
        payload = proposal_payload if getattr(record, "accepted", False) else None
        session.add(
            AgentDecisionRow(
                world_id=uuid.UUID(world_id),
                decision_id=record.decision_id,
                npc_id=uuid.UUID(record.npc_id),
                tick=record.tick,
                world_version=record.world_version,
                provider=record.provider,
                model_version=record.model_version,
                system_prompt=record.system_prompt,
                user_prompt=record.user_prompt,
                raw_response=record.raw_response,
                attempts=record.attempts,
                accepted=record.accepted,
                error=record.error,
                latency_ms=record.latency_ms,
                proposal=payload,
            )
        )
    session.commit()


def list_decisions(
    session: Session,
    *,
    npc_id: str | None = None,
    tick: int | None = None,
    accepted_only: bool = False,
    limit: int = 200,
) -> list[AgentDecisionRow]:
    world_row = session.execute(select(WorldStateRow).limit(1)).scalar_one_or_none()
    if world_row is None:
        return []
    query = select(AgentDecisionRow).where(AgentDecisionRow.world_id == world_row.world_id)
    if npc_id is not None:
        query = query.where(AgentDecisionRow.npc_id == uuid.UUID(npc_id))
    if tick is not None:
        query = query.where(AgentDecisionRow.tick == tick)
    if accepted_only:
        query = query.where(AgentDecisionRow.accepted.is_(True))
    query = query.order_by(AgentDecisionRow.id.asc()).limit(limit)
    return list(session.execute(query).scalars().all())
