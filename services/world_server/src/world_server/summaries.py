"""Human-readable event summaries shared by observations and memories."""

from __future__ import annotations

from typing import Any

from world_core.models import WorldState


def _name(state: WorldState | None, npc_id: str) -> str:
    if state is not None:
        npc = state.npcs.get(npc_id)
        if npc is not None:
            return npc.name
    return npc_id


def summarize_event(
    event_type: str, payload: dict[str, Any], state: WorldState | None = None
) -> str:
    if event_type == "WORLD_ADVANCED":
        return f"world advanced to tick {payload.get('to_tick')}"
    if event_type == "NPC_MOVED":
        target = payload.get("to_location_id")
        if state is not None and isinstance(target, str) and target in state.locations:
            return f"moved to {state.locations[target].name}"
        return f"moved to {target}"
    if event_type == "ITEM_TRANSFERRED":
        return f"item {payload.get('name')} changed hands"
    if event_type == "ITEM_CONSUMED":
        return f"consumed {payload.get('name')}"
    if event_type == "CULTIVATION_STARTED":
        return f"began cultivation for {payload.get('days')} days"
    if event_type == "CULTIVATION_COMPLETED":
        return f"completed cultivation, gained {payload.get('qi_gained')} qi"
    if event_type == "BREAKTHROUGH_ATTEMPT":
        outcome = "succeeded" if payload.get("success") else "failed"
        return f"breakthrough to realm {payload.get('to_realm')} {outcome}"
    if event_type == "NPC_DIED":
        cause = payload.get("cause")
        return f"died ({cause})"
    if event_type == "LOCATION_INVESTIGATED":
        return f"investigated {payload.get('location_name') or payload.get('location_id')}"
    if event_type == "SECRET_REALM_DISCOVERED":
        return f"discovered the secret realm {payload.get('name')}"
    if event_type == "SECRET_REALM_ENTERED":
        realm_id = payload.get("realm_id")
        if state is not None and isinstance(realm_id, str) and realm_id in state.secret_realms:
            return f"entered the secret realm {state.secret_realms[realm_id].name}"
        return f"entered the secret realm {realm_id}"
    if event_type == "SECRET_REALM_CLOSED":
        realm_id = payload.get("realm_id")
        if state is not None and isinstance(realm_id, str) and realm_id in state.secret_realms:
            return f"the secret realm {state.secret_realms[realm_id].name} closed"
        return f"the secret realm {realm_id} closed"
    if event_type == "OPPORTUNITY_CLAIMED":
        if payload.get("success"):
            return f"claimed {payload.get('name')}"
        return f"failed to claim {payload.get('name')}"
    if event_type == "OPPORTUNITY_EXPIRED":
        return "an opportunity expired"
    if event_type == "COMBAT_RESOLVED":
        winner = (
            payload.get("attacker_id")
            if payload.get("attacker_won")
            else payload.get("defender_id")
        )
        return f"combat ended, winner {winner}"
    if event_type == "RELATIONSHIP_CHANGED":
        return "a relationship changed"
    if event_type == "BELIEF_ACQUIRED":
        return "a belief was acquired"
    if event_type == "KNOWLEDGE_ACQUIRED":
        return "new knowledge was acquired"
    if event_type == "FACTION_UPDATED":
        return f"faction treasury at {payload.get('treasury')}"
    return event_type.lower()


__all__ = ["summarize_event"]
