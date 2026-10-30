from __future__ import annotations

import random
from typing import Any

from world_core.goal_evolution import apply_breakthrough_goal_progress, goal_target_id
from world_core.models import ActiveAction, Goal, Npc, WorldState
from world_core.rng import seed_for
from world_core.ruleset import RULESET
from world_core.support import (
    Emitter,
    add_belief,
    adjust_relationship,
    kill_npc,
    owned_item_id,
    reject,
    require_entity_ref,
    require_idle,
    require_int,
    require_str,
)


def _unique_event_ids(*event_ids: int | None) -> list[int]:
    """Deterministic, duplicate-free parent list. Only true causes belong here."""
    return sorted({event_id for event_id in event_ids if event_id is not None})


def _realm_access_event_id(state: WorldState, actor: Npc) -> int | None:
    """Provenance for the actor's current access to a secret realm interior."""
    for realm in sorted(state.secret_realms.values(), key=lambda item: item.realm_id):
        if realm.interior_location_id != actor.location_id:
            continue
        entry_id = realm.entry_event_ids.get(actor.npc_id)
        if entry_id is not None:
            return entry_id
        discovery_id = realm.discovery_event_ids.get(actor.npc_id)
        if discovery_id is not None:
            return discovery_id
    return None


def _belief_cause(state: WorldState, actor: Npc, location_id: str) -> int | None:
    candidates = [
        belief
        for belief in state.beliefs.values()
        if belief.npc_id == actor.npc_id
        and belief.subject_key == location_id
        and belief.source_event_id is not None
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda belief: (belief.confidence, belief.source_event_id or 0))
    return best.source_event_id


def handle_wait(state: WorldState, actor: Npc, arguments: dict[str, Any], emit: Emitter) -> None:
    require_idle(actor)
    ticks = require_int(arguments, "ticks", 1, 365)
    actor.active_action = ActiveAction(
        type="wait",
        started_tick=state.tick,
        remaining_ticks=ticks,
        total_ticks=ticks,
    )


def _active_commitments(npc: Npc) -> list[Goal]:
    return [
        goal
        for goal in sorted(npc.goals, key=lambda item: item.goal_id)
        if goal.kind == "commitment" and goal.status == "active"
    ]


def handle_make_commitment(
    state: WorldState, actor: Npc, arguments: dict[str, Any], emit: Emitter
) -> None:
    """Record a bounded, world-authoritative promise between two present NPCs."""
    require_idle(actor)
    with_id = require_str(arguments, "with_npc_id")
    counterparty = state.npcs.get(with_id)
    if counterparty is None or not counterparty.alive:
        reject("unknown_counterparty", f"unknown or dead counterparty {with_id}")
    if counterparty.npc_id == actor.npc_id:
        reject("self_commitment", "an NPC cannot promise itself")
    if counterparty.location_id != actor.location_id:
        reject("not_together", "both actors must be at the same location")

    promised_goal_id = require_str(arguments, "promised_goal_id")
    promised = next((goal for goal in actor.goals if goal.goal_id == promised_goal_id), None)
    if promised is None or promised.status != "active":
        reject("unknown_goal", f"{promised_goal_id} is not an active goal of the actor")

    target_location_id = require_str(arguments, "target_location_id")
    if target_location_id not in state.locations:
        reject("unknown_location", f"unknown location {target_location_id}")
    if target_location_id not in actor.known_locations:
        reject("unknown_location", "the actor does not know that location")

    until_ticks = require_int(arguments, "until_ticks", 1, 365)
    terms = arguments.get("terms")
    if not isinstance(terms, str) or not terms.strip() or len(terms) > 200:
        reject("invalid_arguments", "terms must be 1..200 characters")
    if any(
        goal.params.get("promised_goal_id") == promised_goal_id
        for goal in _active_commitments(actor)
    ):
        reject("duplicate_commitment", "an active promise already covers this goal")

    until_tick = state.tick + until_ticks
    event_id = emit(
        "COMMITMENT_MADE",
        actor_ids=[actor.npc_id],
        target_ids=[with_id],
        location_id=actor.location_id,
        rng_seed=seed_for(
            state, "commitment", actor.npc_id, promised_goal_id, with_id, state.tick
        ),
        payload={
            "with_npc_id": with_id,
            "promised_goal_id": promised_goal_id,
            "target_location_id": target_location_id,
            "until_tick": until_tick,
            "terms": terms.strip(),
        },
    )
    commitment_id = f"commitment_{actor.npc_id}_{event_id}"
    actor.goals.append(
        Goal(
            goal_id=commitment_id,
            kind="commitment",
            priority=0.85,
            params={
                "commitment_id": commitment_id,
                "with_npc_id": with_id,
                "promised_goal_id": promised_goal_id,
                "target_location_id": target_location_id,
                "until_tick": until_tick,
                "terms": terms.strip(),
            },
            created_tick=state.tick,
            origin_event_id=event_id,
            last_updated_tick=state.tick,
        )
    )
    promised.params["deferred_until_tick"] = until_tick
    promised.params["commitment_id"] = commitment_id
    promised.last_updated_tick = state.tick


def handle_move(state: WorldState, actor: Npc, arguments: dict[str, Any], emit: Emitter) -> None:
    require_idle(actor)
    target = require_str(arguments, "to_location_id")
    location = state.locations.get(target)
    if location is None:
        reject("unknown_location", f"unknown location {target}", location_id=target)
    if target == actor.location_id:
        reject("already_there", f"{actor.npc_id} is already at {target}")
    current = state.locations.get(actor.location_id)
    if current is None or target not in current.adjacency:
        reject(
            "not_adjacent",
            f"{actor.location_id} is not adjacent to {target}",
            from_location_id=actor.location_id,
            to_location_id=target,
        )
    for realm in state.secret_realms.values():
        if realm.interior_location_id == target:
            if not realm.opened:
                reject("realm_closed", f"{realm.realm_id} is closed", realm_id=realm.realm_id)
            if actor.npc_id not in realm.discovered_by:
                reject(
                    "realm_undiscovered",
                    f"{actor.npc_id} has not discovered {realm.realm_id}",
                    realm_id=realm.realm_id,
                )
    source = actor.location_id
    actor.location_id = target
    emit(
        "NPC_MOVED",
        actor_ids=[actor.npc_id],
        location_id=target,
        rng_seed=seed_for(state, "move", actor.npc_id, source, target),
        payload={"from_location_id": source, "to_location_id": target},
    )


def handle_start_cultivation(
    state: WorldState, actor: Npc, arguments: dict[str, Any], emit: Emitter
) -> None:
    require_idle(actor)
    days = require_int(arguments, "days", 1, 365)
    location = state.locations.get(actor.location_id)
    aura = location.aura_multiplier if location else 0.0
    if aura <= 0:
        reject("no_aura", f"no aura at {actor.location_id}", location_id=actor.location_id)
    actor.active_action = ActiveAction(
        type="cultivate",
        started_tick=state.tick,
        remaining_ticks=days,
        total_ticks=days,
        payload={"qi_gained": 0, "stage_ups": 0, "aura": aura},
    )
    emit(
        "CULTIVATION_STARTED",
        actor_ids=[actor.npc_id],
        location_id=actor.location_id,
        rng_seed=seed_for(state, "cultivate_start", actor.npc_id, days),
        payload={"days": days, "aura_multiplier": aura, "realm": actor.realm},
    )


def handle_attempt_breakthrough(
    state: WorldState, actor: Npc, arguments: dict[str, Any], emit: Emitter
) -> None:
    require_idle(actor)
    rule = RULESET.realm(actor.realm)
    if actor.realm >= max(RULESET.realms):
        reject("realm_cap", "no further realm exists in the ruleset")
    if actor.stage < rule.stages:
        reject(
            "not_at_cap",
            "breakthrough requires the final stage of the current realm",
            stage=actor.stage,
            required_stage=rule.stages,
        )
    cap_qi = RULESET.cap_qi(actor.realm)
    if actor.qi < cap_qi:
        reject("insufficient_qi", "breakthrough requires more qi", qi=actor.qi, required=cap_qi)

    pill_id = arguments.get("pill_item_id")
    pill_item = None
    pill_quality = 0.0
    if pill_id is not None:
        if not isinstance(pill_id, str):
            reject("invalid_arguments", "pill_item_id must be a string")
        owned_item_id(state, actor, pill_id)
        pill_item = state.items[pill_id]
        if pill_item.kind != "pill":
            reject("not_a_pill", f"{pill_id} is not a pill", item_id=pill_id)
        pill_quality = float(pill_item.properties.get("quality", 0.5))

    support = 0.6 if actor.faction_id else 0.2
    probability = RULESET.breakthrough_probability(
        actor, pill_quality=pill_quality, support=support
    )
    next_realm = actor.realm + 1
    event_id = emit.event_id + 1
    rng = random.Random(seed_for(state, "breakthrough", actor.npc_id, event_id, next_realm))
    roll = round(rng.random(), 6)

    parent_ids: list[int] = []
    if pill_item is not None:
        assert pill_id is not None
        pill_acquired_event_id = pill_item.acquired_event_id
        actor.inventory.remove(pill_id)
        pill_item.owner_id = None
        pill_item.location_id = None
        pill_item.hidden = True
        consume_id = emit(
            "ITEM_CONSUMED",
            actor_ids=[actor.npc_id],
            location_id=actor.location_id,
            parents=_unique_event_ids(pill_acquired_event_id),
            rng_seed=seed_for(state, "consume", actor.npc_id, pill_id),
            payload={"item_id": pill_id, "name": pill_item.name, "reason": "breakthrough"},
        )
        parent_ids = _unique_event_ids(pill_acquired_event_id, consume_id)

    success = roll < probability
    payload: dict[str, Any] = {
        "from_realm": actor.realm,
        "to_realm": next_realm,
        "pill_id": pill_id,
        "probability": probability,
        "roll": roll,
        "success": success,
        "rng_seed": rng.randint(0, 2**62),
    }
    if success:
        actor.realm = next_realm
        actor.stage = 1
        actor.qi = 0
        actor.foundation = round(min(1.0, actor.foundation + 0.08), 6)
        actor.health = round(min(1.0, actor.health + 0.05), 6)
        actor.lifespan_ticks = max(
            actor.lifespan_ticks, RULESET.lifespan_ticks(actor.realm, actor.foundation)
        )
        achieved = apply_breakthrough_goal_progress(
            actor, event_id=emit.event_id + 1, tick=state.tick
        )
        payload["goals_achieved"] = achieved
        payload["lifespan_ticks"] = actor.lifespan_ticks
    else:
        loss = round(rng.uniform(0.15, 0.45), 6)
        actor.health = round(max(0.0, actor.health - loss), 6)
        died = rng.random() < float(RULESET.breakthrough["failure"]["death_probability"])
        payload["health_loss"] = loss
        payload["died"] = died or actor.health <= 0
        attempt_id = emit(
            "BREAKTHROUGH_ATTEMPT",
            actor_ids=[actor.npc_id],
            location_id=actor.location_id,
            parents=parent_ids,
            rng_seed=payload["rng_seed"],
            payload=payload,
        )
        if payload["died"]:
            kill_npc(
                state,
                actor,
                cause="breakthrough_deviation",
                emitter=emit,
                parents=[attempt_id],
                rng_seed=seed_for(state, "breakthrough_death", actor.npc_id),
            )
        return

    emit(
        "BREAKTHROUGH_ATTEMPT",
        actor_ids=[actor.npc_id],
        location_id=actor.location_id,
        parents=parent_ids,
        rng_seed=payload["rng_seed"],
        payload=payload,
    )


def handle_transfer_item(
    state: WorldState, actor: Npc, arguments: dict[str, Any], emit: Emitter
) -> None:
    require_idle(actor)
    item_id = require_str(arguments, "item_id")
    from_kind, from_id = require_entity_ref(arguments, "from")
    to_kind, to_id = require_entity_ref(arguments, "to")
    item = state.items.get(item_id)
    if item is None:
        reject("unknown_item", f"unknown item {item_id}", item_id=item_id)
    if item.hidden:
        reject("item_hidden", f"{item_id} is not in the world yet", item_id=item_id)
    if from_kind == "npc":
        if from_id != actor.npc_id:
            reject("not_owner", "only the owner may transfer an item from an NPC")
        if item.owner_id != actor.npc_id or item_id not in actor.inventory:
            reject("not_owner", f"{actor.npc_id} does not own {item_id}")
        source_inventory = actor.inventory
    else:
        source_location = state.locations.get(from_id)
        if source_location is None:
            reject("unknown_location", f"unknown location {from_id}", location_id=from_id)
        if item.owner_id is not None or item.location_id != from_id:
            reject("item_not_there", f"{item_id} is not at {from_id}")
        if actor.location_id != from_id:
            reject("actor_not_present", "the actor must be present to take an item")
        source_inventory = source_location.stash

    if to_kind == "npc":
        destination = state.npcs.get(to_id)
        if destination is None:
            reject("unknown_recipient", f"unknown NPC {to_id}")
        if not destination.alive:
            reject("recipient_dead", f"{to_id} is dead")
        if destination.location_id != actor.location_id:
            reject("recipient_not_present", "the recipient must be at the same location")
    else:
        destination_location = state.locations.get(to_id)
        if destination_location is None:
            reject("unknown_location", f"unknown location {to_id}", location_id=to_id)
        if actor.location_id != to_id:
            reject("actor_not_present", "the actor must be present to drop an item")

    source_inventory.remove(item_id)
    item.owner_id = None
    item.location_id = None
    target_ids: list[str] = []
    if to_kind == "npc":
        assert destination is not None
        destination.inventory.append(item_id)
        item.owner_id = destination.npc_id
        target_ids.append(destination.npc_id)
    else:
        assert destination_location is not None
        destination_location.stash.append(item_id)
        item.location_id = destination_location.location_id

    item.acquired_event_id = emit.event_id + 1
    belief_cause = _belief_cause(state, actor, from_id) if from_kind == "location" else None
    emit(
        "ITEM_TRANSFERRED",
        actor_ids=[actor.npc_id],
        target_ids=target_ids,
        location_id=actor.location_id,
        parents=[belief_cause] if belief_cause is not None else [],
        rng_seed=seed_for(state, "transfer", actor.npc_id, item_id, to_id),
        payload={
            "item_id": item_id,
            "name": item.name,
            "from": {"kind": from_kind, "id": from_id},
            "to": {"kind": to_kind, "id": to_id},
            "unique": item.unique,
        },
    )


def handle_investigate(
    state: WorldState, actor: Npc, arguments: dict[str, Any], emit: Emitter
) -> None:
    require_idle(actor)
    target = require_str(arguments, "target_location_id")
    location = state.locations.get(target)
    if location is None:
        reject("unknown_location", f"unknown location {target}", location_id=target)
    if actor.location_id != target:
        reject("actor_not_present", "the actor must be at the location being investigated")
    if target not in actor.known_locations:
        actor.known_locations.append(target)

    investigate_id = emit(
        "LOCATION_INVESTIGATED",
        actor_ids=[actor.npc_id],
        location_id=target,
        rng_seed=seed_for(state, "investigate", actor.npc_id, target),
        payload={"focus": arguments.get("focus", "secret_realm"), "location_name": location.name},
    )
    for goal in _active_commitments(actor):
        if goal.params.get("target_location_id") != target:
            continue
        goal.status = "achieved"
        goal.last_updated_tick = state.tick
        promised = next(
            (
                item
                for item in actor.goals
                if item.goal_id == goal.params.get("promised_goal_id")
            ),
            None,
        )
        if promised is not None:
            promised.params.pop("deferred_until_tick", None)
            promised.params["commitment_fulfilled_tick"] = state.tick
            promised.last_updated_tick = state.tick
        counterparty = goal.params.get("with_npc_id")
        emit(
            "COMMITMENT_FULFILLED",
            actor_ids=[actor.npc_id],
            target_ids=[counterparty] if isinstance(counterparty, str) else [],
            location_id=target,
            parents=_unique_event_ids(investigate_id, goal.origin_event_id),
            rng_seed=seed_for(state, "commitment_fulfilled", actor.npc_id, goal.goal_id),
            payload={
                "commitment_id": goal.goal_id,
                "with_npc_id": goal.params.get("with_npc_id"),
                "promised_goal_id": goal.params.get("promised_goal_id"),
                "location_id": target,
                "investigate_event_id": investigate_id,
            },
        )

    for realm in sorted(state.secret_realms.values(), key=lambda item: item.realm_id):
        if realm.entrance_location_id != target or not realm.opened:
            continue
        if actor.npc_id in realm.discovered_by:
            continue
        if realm.required_item_id is None:
            continue
        item = state.items.get(realm.required_item_id)
        if item is None or item.owner_id != actor.npc_id:
            continue
        realm.discovered_by.append(actor.npc_id)
        if realm.interior_location_id not in actor.known_locations:
            actor.known_locations.append(realm.interior_location_id)
        add_belief(
            state,
            npc_id=actor.npc_id,
            subject_key=realm.realm_id,
            predicate="entrance_found",
            object_value=realm.entrance_location_id,
            confidence=0.95,
            source_event_id=investigate_id,
        )
        # Discovery through a map has two true causes: the investigation that
        # consumed the knowledge and the event that put the map in the actor's
        # hands. A merely previous action is not a cause.
        discovery_id = emit(
            "SECRET_REALM_DISCOVERED",
            actor_ids=[actor.npc_id],
            location_id=target,
            parents=_unique_event_ids(investigate_id, item.acquired_event_id),
            rng_seed=seed_for(state, "discover", actor.npc_id, realm.realm_id),
            payload={
                "realm_id": realm.realm_id,
                "name": realm.name,
                "entrance_location_id": realm.entrance_location_id,
                "interior_location_id": realm.interior_location_id,
                "map_item_id": realm.required_item_id,
            },
        )
        realm.discovery_event_ids[actor.npc_id] = discovery_id


def handle_enter_secret_realm(
    state: WorldState, actor: Npc, arguments: dict[str, Any], emit: Emitter
) -> None:
    require_idle(actor)
    realm_id = require_str(arguments, "realm_id")
    realm = state.secret_realms.get(realm_id)
    if realm is None:
        reject("unknown_realm", f"unknown realm {realm_id}", realm_id=realm_id)
    if not realm.opened or not realm.open_tick <= state.tick <= realm.close_tick:
        reject("realm_closed", f"{realm_id} is not open", realm_id=realm_id)
    if actor.location_id != realm.entrance_location_id:
        reject("not_at_entrance", "the actor is not at the realm entrance")
    if actor.npc_id not in realm.discovered_by:
        reject("realm_undiscovered", "the actor has not discovered this realm")
    source = actor.location_id
    actor.location_id = realm.interior_location_id
    discovery_id = realm.discovery_event_ids.get(actor.npc_id)
    entry_id = emit(
        "SECRET_REALM_ENTERED",
        actor_ids=[actor.npc_id],
        location_id=realm.interior_location_id,
        parents=_unique_event_ids(discovery_id),
        rng_seed=seed_for(state, "enter_realm", actor.npc_id, realm_id),
        payload={
            "realm_id": realm_id,
            "from_location_id": source,
            "to_location_id": realm.interior_location_id,
        },
    )
    realm.entry_event_ids[actor.npc_id] = entry_id


def handle_claim_opportunity(
    state: WorldState, actor: Npc, arguments: dict[str, Any], emit: Emitter
) -> None:
    require_idle(actor)
    opportunity_id = require_str(arguments, "opportunity_id")
    opportunity = state.opportunities.get(opportunity_id)
    if opportunity is None:
        reject("unknown_opportunity", f"unknown opportunity {opportunity_id}")
    if opportunity.claimed_by is not None:
        reject("already_claimed", "the opportunity has already been claimed")
    if opportunity.expired or state.tick > opportunity.active_until_tick:
        reject("opportunity_expired", "the opportunity has expired")
    if state.tick < opportunity.active_from_tick:
        reject("opportunity_not_open", "the opportunity is not active yet")
    if actor.location_id != opportunity.location_id:
        reject("not_at_opportunity", "the actor is not at the opportunity location")
    if actor.realm < opportunity.min_realm:
        reject("realm_too_low", "the actor's realm is too low")
    if opportunity.requires_map_item_id is not None:
        owned_item_id(state, actor, opportunity.requires_map_item_id)

    luck_bias = (
        opportunity.canonical_luck_bias
        if actor.npc_id == opportunity.canonical_candidate_id
        else 1.0
    )
    probability = RULESET.opportunity_probability(
        actor,
        base_weight=opportunity.base_weight,
        luck_bias=luck_bias,
        knowledge=1.0,
    )
    event_id = emit.event_id + 1
    rng = random.Random(seed_for(state, "claim", actor.npc_id, opportunity_id, event_id))
    roll = round(rng.random(), 6)
    opportunity.attempts += 1
    success = roll < probability
    payload: dict[str, Any] = {
        "opportunity_id": opportunity_id,
        "name": opportunity.name,
        "probability": probability,
        "roll": roll,
        "success": success,
    }
    if success:
        awarded: list[str] = []
        for reward_id in opportunity.reward_item_ids:
            item = state.items.get(reward_id)
            if item is None:
                continue
            item.hidden = False
            item.owner_id = actor.npc_id
            item.location_id = None
            item.acquired_event_id = event_id
            if reward_id not in actor.inventory:
                actor.inventory.append(reward_id)
            awarded.append(reward_id)
        opportunity.claimed_by = actor.npc_id
        opportunity.claimed_tick = state.tick
        payload["reward_item_ids"] = awarded
    emit(
        "OPPORTUNITY_CLAIMED",
        actor_ids=[actor.npc_id],
        location_id=actor.location_id,
        parents=_unique_event_ids(_realm_access_event_id(state, actor)),
        rng_seed=seed_for(state, "claim_result", actor.npc_id, opportunity_id, event_id),
        payload=payload,
    )


def handle_attack(state: WorldState, actor: Npc, arguments: dict[str, Any], emit: Emitter) -> None:
    require_idle(actor)
    target_id = require_str(arguments, "target_id")
    intent = arguments.get("intent")
    if intent not in {"kill", "subdue", "rob"}:
        reject("invalid_arguments", "intent must be kill, subdue, or rob")
    target = state.npcs.get(target_id)
    if target is None:
        reject("unknown_target", f"unknown target {target_id}")
    if target.npc_id == actor.npc_id:
        reject("self_target", "an NPC cannot attack itself")
    if not target.alive:
        reject("target_dead", "the target is already dead")
    if target.location_id != actor.location_id:
        reject("target_not_present", "the target must be at the same location")

    for goal in actor.goals:
        if goal.status != "active":
            continue
        deferred_until = goal.params.get("deferred_until_tick")
        if not isinstance(deferred_until, int) or deferred_until <= state.tick:
            continue
        if goal_target_id(goal) != target_id:
            continue
        reject(
            "commitment_deferred",
            "an active promise defers hostile action against this target",
            goal_id=goal.goal_id,
            until_tick=deferred_until,
        )

    attacker_power = RULESET.power(actor)
    defender_power = RULESET.power(target)
    probability = RULESET.combat_win_probability(attacker_power, defender_power)
    event_id = emit.event_id + 1
    rng = random.Random(seed_for(state, "attack", actor.npc_id, target_id, event_id))
    roll = round(rng.random(), 6)
    won = roll < probability
    damage = round(rng.uniform(0.25, 0.55), 6)
    stolen_item: str | None = None
    died = False
    if won:
        target.health = round(max(0.0, target.health - damage), 6)
        if intent == "rob" and target.inventory:
            stolen_item = sorted(target.inventory)[0]
            target.inventory.remove(stolen_item)
            actor.inventory.append(stolen_item)
            state.items[stolen_item].owner_id = actor.npc_id
        if target.health <= 0 or (intent == "kill" and target.health <= 0.15):
            target.health = 0.0
            died = True
    else:
        actor.health = round(max(0.0, actor.health - round(rng.uniform(0.15, 0.35), 6)), 6)
        if actor.health <= 0:
            died = True

    combat_id = emit(
        "COMBAT_RESOLVED",
        actor_ids=[actor.npc_id],
        target_ids=[target.npc_id],
        location_id=actor.location_id,
        rng_seed=seed_for(state, "combat_result", actor.npc_id, target_id, event_id),
        payload={
            "attacker_id": actor.npc_id,
            "defender_id": target.npc_id,
            "intent": intent,
            "probability": probability,
            "roll": roll,
            "attacker_won": won,
            "damage": damage,
            "stolen_item_id": stolen_item,
            "defender_died": died and won,
        },
    )
    if won:
        adjust_relationship(
            state,
            source_id=target.npc_id,
            target_id=actor.npc_id,
            affinity=-30,
            trust=-20,
            fear=20,
            last_event_id=combat_id,
        )
        adjust_relationship(
            state,
            source_id=actor.npc_id,
            target_id=target.npc_id,
            affinity=-10,
            respect=5,
            last_event_id=combat_id,
        )
    else:
        adjust_relationship(
            state,
            source_id=target.npc_id,
            target_id=actor.npc_id,
            affinity=-15,
            respect=-5,
            last_event_id=combat_id,
        )
    emit(
        "RELATIONSHIP_CHANGED",
        actor_ids=[actor.npc_id, target.npc_id],
        location_id=actor.location_id,
        parents=[combat_id],
        rng_seed=seed_for(state, "relationship", actor.npc_id, target.npc_id, event_id),
        payload={"source_npc_id": target.npc_id, "target_npc_id": actor.npc_id},
    )
    if died:
        victim = target if won else actor
        killer = actor if won else target
        kill_npc(
            state,
            victim,
            cause="combat",
            emitter=emit,
            parents=[combat_id],
            rng_seed=seed_for(state, "combat_death", event_id),
            killer_id=killer.npc_id,
        )
