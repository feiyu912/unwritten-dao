from __future__ import annotations

from typing import Any

from world_core.commands import CommandResult, CommandSource, WorldCommand, make_command
from world_core.errors import CommandRejected
from world_core.handlers import (
    handle_attack,
    handle_attempt_breakthrough,
    handle_claim_opportunity,
    handle_enter_secret_realm,
    handle_investigate,
    handle_move,
    handle_start_cultivation,
    handle_transfer_item,
    handle_wait,
)
from world_core.models import Npc, WorldState, relationship_key
from world_core.rng import seed_for
from world_core.ruleset import RULESET
from world_core.support import Emitter, kill_npc, require_actor

_HANDLERS = {
    "wait": handle_wait,
    "move": handle_move,
    "start_cultivation": handle_start_cultivation,
    "attempt_breakthrough": handle_attempt_breakthrough,
    "transfer_item": handle_transfer_item,
    "investigate": handle_investigate,
    "enter_secret_realm": handle_enter_secret_realm,
    "claim_opportunity": handle_claim_opportunity,
    "attack": handle_attack,
}


def apply_command(state: WorldState, command: WorldCommand) -> CommandResult:
    if command.world_id != state.world_id:
        raise CommandRejected("unknown_world", "command targets a different world")
    if command.expected_state_version != state.state_version:
        raise CommandRejected(
            "stale_state_version",
            "command was created against an older state version",
            {"expected": command.expected_state_version, "actual": state.state_version},
        )
    if command.issued_tick != state.tick:
        raise CommandRejected(
            "stale_tick",
            "command tick does not match the world clock",
            {"issued_tick": command.issued_tick, "current_tick": state.tick},
        )

    emit = Emitter(state, command)
    if command.type == "advance_time":
        _advance(state, command.arguments, emit)
    else:
        actor = require_actor(state, command)
        _HANDLERS[command.type](state, actor, command.arguments, emit)

    state.state_version += 1
    state.last_event_id = emit.event_id
    return CommandResult(
        accepted=True,
        state_version=state.state_version,
        events=emit.events,
    )


def advance_time(
    state: WorldState, ticks: int, *, source: CommandSource = "system"
) -> CommandResult:
    command = make_command(
        state,
        None,
        "advance_time",
        {"ticks": ticks},
        source=source,
        idempotency_key=f"system:advance_time:{state.state_version}:{ticks}",
    )
    return apply_command(state, command)


def _advance(state: WorldState, arguments: dict[str, Any], emit: Emitter) -> None:
    ticks = arguments.get("ticks")
    if not isinstance(ticks, int) or isinstance(ticks, bool) or not 1 <= ticks <= 3650:
        raise CommandRejected("invalid_arguments", "ticks must be an integer in [1, 3650]")
    start_tick = state.tick
    for _ in range(ticks):
        state.tick += 1
        _process_tick(state, emit)
    emit(
        "WORLD_ADVANCED",
        rng_seed=seed_for(state, "world_advanced", start_tick, state.tick),
        payload={"from_tick": start_tick, "to_tick": state.tick, "ticks": ticks},
    )


def _process_tick(state: WorldState, emit: Emitter) -> None:
    for npc_key in sorted(state.npcs):
        npc = state.npcs[npc_key]
        if not npc.alive:
            continue
        if npc.health <= 0:
            kill_npc(state, npc, cause="health_depleted", emitter=emit)
            continue
        if npc.health < 1.0:
            npc.health = round(min(1.0, npc.health + 0.002), 6)

        action = npc.active_action
        if action is not None:
            if action.type == "cultivate":
                _cultivate_day(state, npc, action)
            action.remaining_ticks -= 1
            if action.remaining_ticks <= 0:
                if action.type == "cultivate":
                    emit(
                        "CULTIVATION_COMPLETED",
                        actor_ids=[npc.npc_id],
                        location_id=npc.location_id,
                        rng_seed=seed_for(state, "cultivate_end", npc.npc_id, state.tick),
                        payload={
                            "days": action.total_ticks,
                            "qi_gained": action.payload.get("qi_gained", 0),
                            "stage_ups": action.payload.get("stage_ups", 0),
                            "realm": npc.realm,
                            "stage": npc.stage,
                            "qi": npc.qi,
                        },
                    )
                npc.active_action = None

        if state.tick - npc.birth_tick >= npc.lifespan_ticks:
            kill_npc(state, npc, cause="old_age", emitter=emit)
            continue
        if npc.health <= 0:
            kill_npc(state, npc, cause="health_depleted", emitter=emit)

    if state.tick % 30 == 0:
        _settle_factions(state, emit)
    _expire_realms(state, emit)
    _expire_opportunities(state, emit)


def _cultivate_day(state: WorldState, npc: Npc, action: Any) -> None:
    location = state.locations.get(npc.location_id)
    aura = location.aura_multiplier if location else 0.0
    gain = RULESET.daily_qi_gain(npc, aura)
    if gain <= 0:
        return
    npc.qi += gain
    action.payload["qi_gained"] = int(action.payload.get("qi_gained", 0)) + gain
    new_stage = RULESET.stage_for_qi(npc.realm, npc.qi)
    if new_stage > npc.stage:
        action.payload["stage_ups"] = int(action.payload.get("stage_ups", 0)) + (
            new_stage - npc.stage
        )
        npc.stage = new_stage
    if npc.stage >= RULESET.max_stage(npc.realm):
        npc.qi = min(npc.qi, RULESET.cap_qi(npc.realm))


def _settle_factions(state: WorldState, emit: Emitter) -> None:
    for faction_key in sorted(state.factions):
        faction = state.factions[faction_key]
        members = sorted(
            npc.npc_id
            for npc in state.npcs.values()
            if npc.alive and npc.faction_id == faction.faction_id
        )
        upkeep = faction.upkeep_per_member * len(members)
        delta = faction.income_per_30d - upkeep
        faction.treasury = max(0, faction.treasury + delta)
        emit(
            "FACTION_UPDATED",
            target_ids=members,
            rng_seed=seed_for(state, "faction", faction.faction_id, state.tick),
            payload={
                "faction_id": faction.faction_id,
                "name": faction.name,
                "treasury": faction.treasury,
                "income": faction.income_per_30d,
                "upkeep": upkeep,
                "members": len(members),
                "delta": delta,
            },
        )


def _expire_realms(state: WorldState, emit: Emitter) -> None:
    for realm_key in sorted(state.secret_realms):
        realm = state.secret_realms[realm_key]
        if realm.opened and state.tick > realm.close_tick:
            realm.opened = False
            emit(
                "SECRET_REALM_CLOSED",
                location_id=realm.interior_location_id,
                rng_seed=seed_for(state, "realm_close", realm.realm_id, state.tick),
                payload={"realm_id": realm.realm_id, "close_tick": realm.close_tick},
            )


def _expire_opportunities(state: WorldState, emit: Emitter) -> None:
    for opportunity_key in sorted(state.opportunities):
        opportunity = state.opportunities[opportunity_key]
        if (
            opportunity.claimed_by is None
            and not opportunity.expired
            and state.tick > opportunity.active_until_tick
        ):
            opportunity.expired = True
            emit(
                "OPPORTUNITY_EXPIRED",
                location_id=opportunity.location_id,
                rng_seed=seed_for(state, "opportunity_expire", opportunity.opportunity_id),
                payload={
                    "opportunity_id": opportunity.opportunity_id,
                    "active_until_tick": opportunity.active_until_tick,
                },
            )


def validate_state(state: WorldState) -> list[str]:
    problems: list[str] = []
    if len(state.npcs) != 30:
        problems.append(f"expected 30 NPCs, found {len(state.npcs)}")
    player = state.npcs.get(state.player_id)
    if player is None:
        problems.append("player is missing")
    elif player.canonical_role != "player":
        problems.append("player_id does not reference the player role")

    for key, npc in state.npcs.items():
        if key != npc.npc_id:
            problems.append(f"npc key mismatch: {key} != {npc.npc_id}")
        if npc.location_id not in state.locations:
            problems.append(f"{npc.npc_id} is at unknown location {npc.location_id}")
        if npc.faction_id is not None and npc.faction_id not in state.factions:
            problems.append(f"{npc.npc_id} references unknown faction {npc.faction_id}")
        if npc.realm not in RULESET.realms:
            problems.append(f"{npc.npc_id} has unknown realm {npc.realm}")
        else:
            max_stage = RULESET.max_stage(npc.realm)
            if not 1 <= npc.stage <= max_stage:
                problems.append(f"{npc.npc_id} stage {npc.stage} outside 1..{max_stage}")
            if npc.qi > RULESET.cap_qi(npc.realm):
                problems.append(f"{npc.npc_id} qi {npc.qi} above cap {RULESET.cap_qi(npc.realm)}")
        if not 0.0 <= npc.health <= 1.0:
            problems.append(f"{npc.npc_id} health out of range")
        if not 0.0 <= npc.foundation <= 1.0:
            problems.append(f"{npc.npc_id} foundation out of range")
        if npc.alive and npc.death_tick is not None:
            problems.append(f"{npc.npc_id} is alive but has death_tick")
        if not npc.alive and npc.active_action is not None:
            problems.append(f"{npc.npc_id} is dead but has an active action")
        if not npc.alive and npc.death_tick is None:
            problems.append(f"{npc.npc_id} is dead without death_tick")
        for known in npc.known_locations:
            if known not in state.locations:
                problems.append(f"{npc.npc_id} knows unknown location {known}")
        for item_id in npc.inventory:
            item = state.items.get(item_id)
            if item is None:
                problems.append(f"{npc.npc_id} carries unknown item {item_id}")
            elif item.owner_id != npc.npc_id:
                problems.append(f"{npc.npc_id} carries {item_id} without ownership")
        if len(set(npc.inventory)) != len(npc.inventory):
            problems.append(f"{npc.npc_id} has duplicate inventory entries")

    for key, location in state.locations.items():
        if key != location.location_id:
            problems.append(f"location key mismatch: {key}")
        for adjacent in location.adjacency:
            other = state.locations.get(adjacent)
            if other is None:
                problems.append(f"{location.location_id} adjacent to unknown {adjacent}")
            elif location.location_id not in other.adjacency:
                problems.append(f"adjacency not symmetric: {location.location_id}->{adjacent}")
        for item_id in location.stash:
            item = state.items.get(item_id)
            if item is None:
                problems.append(f"{location.location_id} holds unknown item {item_id}")
            elif item.location_id != location.location_id or item.owner_id is not None:
                problems.append(f"{location.location_id} holds {item_id} inconsistently")
        if len(set(location.stash)) != len(location.stash):
            problems.append(f"{location.location_id} has duplicate stash entries")

    for key, item in state.items.items():
        if key != item.item_id:
            problems.append(f"item key mismatch: {key}")
        if item.hidden:
            if item.owner_id is not None or item.location_id is not None:
                problems.append(f"hidden item {item.item_id} has a visible container")
        elif item.owner_id is None and item.location_id is None:
            problems.append(f"visible item {item.item_id} has no container")
        if item.owner_id is not None and item.location_id is not None:
            problems.append(f"item {item.item_id} has two containers")

    for key, rel in state.relationships.items():
        expected = relationship_key(rel.source_npc_id, rel.target_npc_id)
        if key != expected:
            problems.append(f"relationship key mismatch: {key}")
        if rel.source_npc_id not in state.npcs or rel.target_npc_id not in state.npcs:
            problems.append(f"relationship {key} references unknown NPC")

    for key, faction in state.factions.items():
        if key != faction.faction_id:
            problems.append(f"faction key mismatch: {key}")
        if faction.leader_id is not None and faction.leader_id not in state.npcs:
            problems.append(f"{key} has unknown leader")
        if faction.treasury < 0:
            problems.append(f"{key} has negative treasury")

    for key, realm in state.secret_realms.items():
        if key != realm.realm_id:
            problems.append(f"realm key mismatch: {key}")
        if realm.entrance_location_id not in state.locations:
            problems.append(f"{key} has unknown entrance")
        if realm.interior_location_id not in state.locations:
            problems.append(f"{key} has unknown interior")
        for npc in realm.discovered_by:
            if npc not in state.npcs:
                problems.append(f"{key} discovered by unknown NPC {npc}")

    for key, opportunity in state.opportunities.items():
        if key != opportunity.opportunity_id:
            problems.append(f"opportunity key mismatch: {key}")
        if opportunity.location_id not in state.locations:
            problems.append(f"{key} has unknown location")
        for reward in opportunity.reward_item_ids:
            if reward not in state.items:
                problems.append(f"{key} rewards unknown item {reward}")

    return problems
