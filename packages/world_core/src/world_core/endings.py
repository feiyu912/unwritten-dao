"""Derive world endings from authoritative state and its event history.

The evaluator is read-only and deterministic: it never mutates state and every
ending cites the event ids that justify it. It does not define new rules; it
only names fates that the simulation has already produced.

The bounded MVP has one key item (the foundation pill), one core conflict (the
sealed ancient cave), and feuds created by real deaths.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from world_core.events import WorldEvent
from world_core.goal_evolution import goal_target_id
from world_core.models import WorldState
from world_core.worldgen import ITEM_FOUNDATION_PILL

ENDING_SCHEMA_VERSION = "ending-report.v1"

_PILL_ACQUISITIONS = {"ITEM_TRANSFERRED", "OPPORTUNITY_CLAIMED", "ITEM_CONSUMED"}


def evaluate_endings(state: WorldState, events: Sequence[WorldEvent]) -> dict[str, Any]:
    """Return the key item's fate, the core conflict, and traceable endings."""
    pill = state.items.get(ITEM_FOUNDATION_PILL)
    holder_id = pill.owner_id if pill is not None else None
    holder = state.npcs.get(holder_id) if holder_id is not None else None

    acquisitions = [event for event in events if _touches_pill(event)]
    consumption = next(
        (event for event in reversed(events) if _is_pill(event, "ITEM_CONSUMED")), None
    )
    consumed_by = _first_actor(consumption) if consumption is not None else None
    consumer = state.npcs.get(consumed_by) if consumed_by is not None else None
    successes = [
        event
        for event in events
        if event.type == "BREAKTHROUGH_ATTEMPT" and event.payload.get("success") is True
    ]

    endings: list[dict[str, Any]] = []
    endings.append(
        _pill_ending(
            pill is not None,
            holder_id,
            holder.name if holder is not None else None,
            consumption,
            consumer.name if consumer is not None else None,
            consumer.npc_id if consumer is not None else None,
            successes,
            acquisitions,
        )
    )
    endings.extend(_realm_endings(state, events))
    endings.extend(_feud_endings(state, events))

    evidence: set[int] = set()
    for ending in endings:
        evidence.update(ending["evidence_event_ids"])

    return {
        "schema_version": ENDING_SCHEMA_VERSION,
        "tick": state.tick,
        "key_item": {
            "item_id": ITEM_FOUNDATION_PILL,
            "name": pill.name if pill is not None else None,
            "holder_id": holder_id,
            "holder_name": holder.name if holder is not None else None,
            "holder_realm": holder.realm if holder is not None else None,
            "location_id": pill.location_id if pill is not None else None,
            "hidden": pill.hidden if pill is not None else None,
            "acquisition_event_ids": [event.event_id for event in acquisitions],
            "consumed_event_id": consumption.event_id if consumption is not None else None,
            "consumed_by": consumed_by,
        },
        "core_conflict": {
            "realm_discovered": any(
                event.type == "SECRET_REALM_DISCOVERED" for event in events
            ),
            "realm_entered": any(event.type == "SECRET_REALM_ENTERED" for event in events),
            "deaths": _deaths(events),
        },
        "endings": endings,
        "evidence_event_ids": sorted(evidence),
    }


def _pill_ending(
    pill_exists: bool,
    holder_id: str | None,
    holder_name: str | None,
    consumption: WorldEvent | None,
    consumer_name: str | None,
    consumer_id: str | None,
    successes: Sequence[WorldEvent],
    acquisitions: Sequence[WorldEvent],
) -> dict[str, Any]:
    if consumption is not None:
        consumed_at = consumption.event_id
        later = next(
            (
                event
                for event in successes
                if consumer_id in event.actor_ids and event.event_id > consumed_at
            ),
            None,
        )
        if later is not None:
            return _ending(
                "pill_ascension",
                f"{consumer_name or consumer_id} consumed the foundation pill and broke through",
                [consumption.event_id, later.event_id],
            )
        return _ending(
            "pill_wasted",
            f"{consumer_name or consumer_id} consumed the foundation pill without breaking through",
            [consumption.event_id],
        )
    if holder_id is not None:
        return _ending(
            "pill_held",
            f"{holder_name or holder_id} holds the foundation pill",
            [event.event_id for event in acquisitions],
        )
    if not pill_exists:
        return _ending("pill_dormant", "the foundation pill is missing", [])
    return _ending("pill_dormant", "the foundation pill has no owner", [])


def _realm_endings(state: WorldState, events: Sequence[WorldEvent]) -> list[dict[str, Any]]:
    # Prefer the state's authoritative event references so a snapshot without
    # its event log (for example after loading a save) still reports correctly.
    discovered = {
        event_id
        for realm in state.secret_realms.values()
        for event_id in realm.discovery_event_ids.values()
    }
    entered = {
        event_id
        for realm in state.secret_realms.values()
        for event_id in realm.entry_event_ids.values()
    }
    discovered.update(e.event_id for e in events if e.type == "SECRET_REALM_DISCOVERED")
    entered.update(e.event_id for e in events if e.type == "SECRET_REALM_ENTERED")
    if entered:
        evidence = sorted(discovered | entered)
        return [_ending("realm_opened", "the ancient cave was entered", evidence)]
    if discovered:
        return [
            _ending(
                "realm_found",
                "the ancient cave was discovered but never entered",
                sorted(discovered),
            )
        ]
    return [_ending("realm_sealed", "no one discovered the ancient cave", [])]


def _feud_endings(state: WorldState, events: Sequence[WorldEvent]) -> list[dict[str, Any]]:
    achieved: list[dict[str, Any]] = []
    open_goals: list[dict[str, Any]] = []
    for npc_id in sorted(state.npcs):
        npc = state.npcs[npc_id]
        for goal in npc.goals:
            if goal.kind != "revenge":
                continue
            entry = {
                "npc_id": npc_id,
                "goal_id": goal.goal_id,
                "target_npc_id": goal_target_id(goal),
                "origin_event_id": goal.origin_event_id,
            }
            if goal.status == "achieved":
                achieved.append(entry)
            elif goal.status == "active":
                open_goals.append(entry)

    endings: list[dict[str, Any]] = []
    if achieved:
        evidence: list[int] = []
        for entry in achieved:
            origin = entry["origin_event_id"]
            if isinstance(origin, int):
                evidence.append(origin)
            target = entry["target_npc_id"]
            evidence.extend(
                event.event_id
                for event in events
                if event.type == "NPC_DIED" and target in event.actor_ids
            )
        endings.append(
            _ending(
                "blood_feud_resolved",
                f"{len(achieved)} revenge goal(s) ended in the killer's death",
                evidence,
            )
        )
    if open_goals:
        evidence = [
            entry["origin_event_id"]
            for entry in open_goals
            if isinstance(entry["origin_event_id"], int)
        ]
        endings.append(
            _ending(
                "blood_feud_open",
                f"{len(open_goals)} revenge goal(s) remain unfinished",
                evidence,
            )
        )
    return endings


def _deaths(events: Sequence[WorldEvent]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        if event.type != "NPC_DIED" or not event.actor_ids:
            continue
        rows.append(
            {
                "npc_id": event.actor_ids[0],
                "killer_id": event.payload.get("killer_id"),
                "cause": event.payload.get("cause"),
                "event_id": event.event_id,
            }
        )
    return rows


def _touches_pill(event: WorldEvent) -> bool:
    if event.type not in _PILL_ACQUISITIONS:
        return False
    if event.type == "OPPORTUNITY_CLAIMED":
        return ITEM_FOUNDATION_PILL in (event.payload.get("reward_item_ids") or [])
    return event.payload.get("item_id") == ITEM_FOUNDATION_PILL


def _is_pill(event: WorldEvent, event_type: str) -> bool:
    return event.type == event_type and event.payload.get("item_id") == ITEM_FOUNDATION_PILL


def _first_actor(event: WorldEvent) -> str | None:
    return event.actor_ids[0] if event.actor_ids else None


def _ending(ending_id: str, summary: str, evidence: Sequence[int]) -> dict[str, Any]:
    return {
        "ending_id": ending_id,
        "summary": summary,
        "evidence_event_ids": sorted({event_id for event_id in evidence if event_id >= 1}),
    }


__all__ = ["ENDING_SCHEMA_VERSION", "evaluate_endings"]