"""Build the per-NPC observation contract from authoritative world state.

The builder is deliberately conservative: it only exposes what the NPC can
currently perceive or already knows. In particular a secret-realm interior (and
any adjacency to it) must never appear before that location is in the NPC's
``known_locations`` list.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from world_core.models import Item, Location, Npc, WorldState

from agent_runtime.models import (
    PROPOSAL_INTENTS,
    ActionProposal,
    ActiveActionView,
    KnownLocation,
    MemoryRecord,
    NpcObservation,
    ObservationSelf,
    ObservedBelief,
    ObservedGoal,
    ObservedItem,
    ObservedRelationship,
    RecentEvent,
    VisibleNpc,
    VisibleOpportunity,
)

_MEMORY_KEYS = ("event_id", "tick", "summary", "importance", "emotional_valence")
_RECENT_EVENT_KEYS = ("event_id", "tick", "type", "summary")


def build_observation(
    state: WorldState,
    npc_id: str,
    *,
    memories: Sequence[Mapping[str, Any]] = (),
    recent_events: Sequence[Mapping[str, Any]] = (),
) -> NpcObservation:
    """Return everything ``npc_id`` may legitimately know at this tick."""
    npc = state.npcs.get(npc_id)
    if npc is None:
        raise KeyError(f"unknown npc {npc_id}")
    location = state.locations.get(npc.location_id)
    if location is None:
        raise KeyError(f"npc {npc_id} is at unknown location {npc.location_id}")

    known_ids = _known_location_ids(npc, state)
    return NpcObservation(
        npc_id=npc.npc_id,
        tick=state.tick,
        world_version=state.state_version,
        location_id=npc.location_id,
        self=ObservationSelf(
            name=npc.name,
            realm=npc.realm,
            stage=npc.stage,
            qi=npc.qi,
            foundation=npc.foundation,
            health=npc.health,
            wealth=npc.wealth,
            lifespan_ticks=npc.lifespan_ticks,
            birth_tick=npc.birth_tick,
            estimated_remaining_life_ticks=max(0, npc.birth_tick + npc.lifespan_ticks - state.tick),
            traits=dict(npc.traits),
        ),
        inventory=_inventory(state, npc),
        visible_items=_visible_items(state, location),
        visible_opportunities=_visible_opportunities(state, location),
        visible_npcs=_visible_npcs(state, npc),
        relationships=_outgoing_relationships(state, npc),
        beliefs=_beliefs(state, npc),
        known_locations=_known_locations(state, known_ids),
        memories=[_memory(row) for row in memories],
        recent_events=[_recent_event(row) for row in recent_events],
        goals=[
            ObservedGoal(
                goal_id=goal.goal_id,
                kind=goal.kind,
                status=goal.status,
                priority=goal.priority,
                params=dict(goal.params),
            )
            for goal in npc.goals
        ],
        active_action=_active_action(npc),
        available_actions=list(PROPOSAL_INTENTS),
    )


def _known_location_ids(npc: Npc, state: WorldState) -> set[str]:
    known = {location_id for location_id in npc.known_locations if location_id in state.locations}
    current = state.locations.get(npc.location_id)
    # Standing somewhere is knowledge of it, except that the contract forbids
    # leaking a secret interior unless the NPC explicitly discovered it.
    if current is not None and current.kind != "secret_realm":
        known.add(current.location_id)
    return known


def _inventory(state: WorldState, npc: Npc) -> list[ObservedItem]:
    items: list[ObservedItem] = []
    for item_id in sorted(npc.inventory):
        item = state.items.get(item_id)
        if item is None or item.hidden:
            continue
        items.append(_observed_item(item))
    return items


def _visible_items(state: WorldState, location: Location) -> list[ObservedItem]:
    items: list[ObservedItem] = []
    for item_id in sorted(location.stash):
        item = state.items.get(item_id)
        if item is None or item.hidden:
            continue
        if item.location_id != location.location_id or item.owner_id is not None:
            continue
        items.append(_observed_item(item))
    return items


def _observed_item(item: Item) -> ObservedItem:
    return ObservedItem(
        item_id=item.item_id,
        name=item.name,
        kind=item.kind,
        properties=dict(item.properties),
    )


def _visible_opportunities(state: WorldState, location: Location) -> list[VisibleOpportunity]:
    opportunities: list[VisibleOpportunity] = []
    for opportunity_id in sorted(state.opportunities):
        opportunity = state.opportunities[opportunity_id]
        if opportunity.location_id != location.location_id:
            continue
        if opportunity.claimed_by is not None or opportunity.expired:
            continue
        if not opportunity.active_from_tick <= state.tick <= opportunity.active_until_tick:
            continue
        opportunities.append(
            VisibleOpportunity(
                opportunity_id=opportunity.opportunity_id,
                name=opportunity.name,
                kind=opportunity.kind,
                location_id=opportunity.location_id,
                active_until_tick=opportunity.active_until_tick,
                reward_item_ids=list(opportunity.reward_item_ids),
            )
        )
    return opportunities


def _visible_npcs(state: WorldState, npc: Npc) -> list[VisibleNpc]:
    visible: list[VisibleNpc] = []
    for other_id in sorted(state.npcs):
        other = state.npcs[other_id]
        if other.npc_id == npc.npc_id or not other.alive:
            continue
        if other.location_id != npc.location_id:
            continue
        visible.append(
            VisibleNpc(
                npc_id=other.npc_id,
                name=other.name,
                realm=other.realm,
                stage=other.stage,
                alive=other.alive,
            )
        )
    return visible


def _outgoing_relationships(state: WorldState, npc: Npc) -> list[ObservedRelationship]:
    rows: list[ObservedRelationship] = []
    for relationship in state.relationships.values():
        if relationship.source_npc_id != npc.npc_id:
            continue
        rows.append(
            ObservedRelationship(
                npc_id=relationship.target_npc_id,
                affinity=relationship.affinity,
                trust=relationship.trust,
                fear=relationship.fear,
                respect=relationship.respect,
                debt=relationship.debt,
            )
        )
    rows.sort(key=lambda row: row.npc_id)
    return rows


def _beliefs(state: WorldState, npc: Npc) -> list[ObservedBelief]:
    rows: list[ObservedBelief] = []
    for belief in state.beliefs.values():
        if belief.npc_id != npc.npc_id:
            continue
        rows.append(
            ObservedBelief(
                subject_key=belief.subject_key,
                predicate=belief.predicate,
                object_value=belief.object_value,
                confidence=belief.confidence,
                source_event_id=belief.source_event_id,
            )
        )
    rows.sort(key=lambda row: (row.subject_key, row.predicate))
    return rows


def _known_locations(state: WorldState, known_ids: set[str]) -> list[KnownLocation]:
    rows: list[KnownLocation] = []
    for location_id in sorted(known_ids):
        location = state.locations[location_id]
        # Only expose adjacency to places the NPC already knows about. This is
        # what keeps a secret interior hidden until it is discovered.
        adjacent = sorted(adjacent for adjacent in location.adjacency if adjacent in known_ids)
        rows.append(
            KnownLocation(
                location_id=location.location_id,
                name=location.name,
                kind=location.kind,
                adjacent_ids=adjacent,
            )
        )
    return rows


def _active_action(npc: Npc) -> ActiveActionView | None:
    action = npc.active_action
    if action is None:
        return None
    return ActiveActionView(type=action.type, remaining_ticks=action.remaining_ticks)


def _memory(row: Mapping[str, Any]) -> MemoryRecord:
    return MemoryRecord(**_picked(row, _MEMORY_KEYS))


def _recent_event(row: Mapping[str, Any]) -> RecentEvent:
    return RecentEvent(**_picked(row, _RECENT_EVENT_KEYS))


def _picked(row: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: row[key] for key in keys if key in row}


__all__ = ["ActionProposal", "NpcObservation", "build_observation"]
