from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NoReturn

from world_core.commands import WorldCommand
from world_core.errors import CommandRejected
from world_core.events import EventType, WorldEvent
from world_core.goal_evolution import apply_death_goal_evolution
from world_core.models import (
    Belief,
    Npc,
    Relationship,
    WorldState,
    belief_key,
    relationship_key,
)


def reject(code: str, message: str, **details: Any) -> NoReturn:
    raise CommandRejected(code, message, details)


@dataclass
class Emitter:
    state: WorldState
    command: WorldCommand
    event_id: int = field(init=False)
    state_version_after: int = field(init=False)
    events: list[WorldEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.event_id = self.state.last_event_id
        self.state_version_after = self.state.state_version + 1

    def __call__(
        self,
        event_type: EventType,
        *,
        actor_ids: list[str] | None = None,
        target_ids: list[str] | None = None,
        location_id: str | None = None,
        parents: list[int] | None = None,
        rng_seed: int = 0,
        payload: dict[str, Any] | None = None,
        tick: int | None = None,
    ) -> int:
        self.event_id += 1
        event = WorldEvent(
            event_id=self.event_id,
            world_id=self.state.world_id,
            tick=self.state.tick if tick is None else tick,
            type=event_type,
            actor_ids=actor_ids or [],
            target_ids=target_ids or [],
            location_id=location_id,
            causal_parent_ids=parents or [],
            rng_seed=rng_seed,
            command_id=self.command.command_id,
            state_version_after=self.state_version_after,
            payload=payload or {},
        )
        self.events.append(event)
        return event.event_id


def require_actor(state: WorldState, command: WorldCommand) -> Npc:
    if command.actor_id is None:
        reject("missing_actor", "command requires an actor")
    npc = state.npcs.get(command.actor_id)
    if npc is None:
        reject("unknown_actor", f"unknown actor {command.actor_id}")
    if not npc.alive:
        reject("actor_dead", f"actor {npc.npc_id} is dead", npc_id=npc.npc_id)
    return npc


def require_idle(npc: Npc) -> None:
    if npc.active_action is not None:
        reject(
            "actor_busy",
            f"{npc.npc_id} is busy with {npc.active_action.type}",
            action=npc.active_action.type,
        )


def require_int(arguments: dict[str, Any], key: str, minimum: int, maximum: int) -> int:
    value = arguments.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        reject(
            "invalid_arguments",
            f"{key} must be an integer in [{minimum}, {maximum}]",
            argument=key,
        )
    return value


def require_str(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value:
        reject("invalid_arguments", f"{key} must be a non-empty string", argument=key)
    return value


def require_entity_ref(arguments: dict[str, Any], key: str) -> tuple[str, str]:
    value = arguments.get(key)
    if not isinstance(value, dict):
        reject("invalid_arguments", f"{key} must be an entity reference", argument=key)
    kind = value.get("kind")
    entity = value.get("id")
    if kind not in {"npc", "location"} or not isinstance(entity, str) or not entity:
        reject("invalid_arguments", f"{key} has an invalid entity reference", argument=key)
    return kind, entity


def add_belief(
    state: WorldState,
    *,
    npc_id: str,
    subject_key: str,
    predicate: str,
    object_value: Any,
    confidence: float,
    source_event_id: int | None,
) -> Belief:
    belief = Belief(
        npc_id=npc_id,
        subject_key=subject_key,
        predicate=predicate,
        object_value=object_value,
        confidence=confidence,
        source_event_id=source_event_id,
        acquired_tick=state.tick,
    )
    state.beliefs[belief_key(npc_id, subject_key, predicate)] = belief
    return belief


def adjust_relationship(
    state: WorldState,
    *,
    source_id: str,
    target_id: str,
    affinity: int = 0,
    trust: int = 0,
    fear: int = 0,
    respect: int = 0,
    debt: int = 0,
    last_event_id: int | None = None,
) -> Relationship:
    key = relationship_key(source_id, target_id)
    rel = state.relationships.get(key)
    if rel is None:
        rel = Relationship(source_npc_id=source_id, target_npc_id=target_id)
        state.relationships[key] = rel
    rel.affinity += affinity
    rel.trust += trust
    rel.fear += fear
    rel.respect += respect
    rel.debt += debt
    if last_event_id is not None:
        rel.last_event_id = last_event_id
    return rel


def kill_npc(
    state: WorldState,
    npc: Npc,
    *,
    cause: str,
    emitter: Emitter,
    parents: list[int] | None = None,
    rng_seed: int = 0,
    killer_id: str | None = None,
) -> int:
    if not npc.alive:
        return 0
    npc.alive = False
    npc.health = 0.0
    npc.death_tick = state.tick
    npc.death_cause = cause
    npc.active_action = None
    death_event_id = emitter(
        "NPC_DIED",
        actor_ids=[npc.npc_id],
        location_id=npc.location_id,
        parents=parents or [],
        rng_seed=rng_seed,
        payload={
            "cause": cause,
            "killer_id": killer_id,
            "age_ticks": state.tick - npc.birth_tick,
            "lifespan_ticks": npc.lifespan_ticks,
        },
    )
    apply_death_goal_evolution(
        state,
        npc,
        death_event_id=death_event_id,
        killer_id=killer_id,
    )
    return death_event_id


def owned_item_id(state: WorldState, npc: Npc, item_id: str) -> None:
    item = state.items.get(item_id)
    if item is None:
        reject("unknown_item", f"unknown item {item_id}", item_id=item_id)
    if item.hidden or item.owner_id != npc.npc_id or item_id not in npc.inventory:
        reject("item_not_owned", f"{npc.npc_id} does not own {item_id}", item_id=item_id)
