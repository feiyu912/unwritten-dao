from __future__ import annotations

from agent_runtime.validator import proposal_to_command
from world_core.worldgen import npc_id

from agent_runtime import UtilityPolicy, build_observation
from world_core import (
    PROTAGONIST_ID,
    Relationship,
    advance_time,
    apply_command,
    create_world,
    make_command,
    relationship_key,
    validate_state,
)


def test_master_death_creates_revenge_and_drives_an_attack() -> None:
    state = create_world(42)
    killer = state.npcs[npc_id("lu_xuanji")]
    victim = state.npcs[npc_id("a_he")]
    survivor = state.npcs[npc_id("su_zhi")]

    victim.location_id = "location_xuanyue_sect"
    victim.health = 0.01
    state.relationships[relationship_key(survivor.npc_id, victim.npc_id)] = Relationship(
        source_npc_id=survivor.npc_id,
        target_npc_id=victim.npc_id,
        affinity=25,
    )

    death_event = None
    for _ in range(5):
        if not victim.alive:
            break
        result = apply_command(
            state,
            make_command(
                state,
                killer.npc_id,
                "attack",
                {"target_id": victim.npc_id, "intent": "kill"},
                source="test",
            ),
        )
        death_event = next(
            (event for event in result.events if event.type == "NPC_DIED"), death_event
        )
    assert victim.alive is False
    assert death_event is not None

    revenge = next(goal for goal in survivor.goals if goal.kind == "revenge")
    assert revenge.params["target_id"] == killer.npc_id
    assert revenge.origin_event_id == death_event.event_id

    observation = build_observation(state, survivor.npc_id)
    proposal = UtilityPolicy().decide(observation)
    assert proposal.goal_id == revenge.goal_id
    assert proposal.intent == "attack"
    assert proposal.arguments == {"target_id": killer.npc_id, "intent": "kill"}

    combat = apply_command(state, proposal_to_command(state, proposal))
    assert any(event.type == "COMBAT_RESOLVED" for event in combat.events)
    assert validate_state(state) == []

    advance_time(state, 10)
    assert any(
        goal.kind == "revenge" and goal.params.get("target_id") == killer.npc_id
        for goal in survivor.goals
    )


def test_unrelated_npc_does_not_gain_revenge() -> None:
    state = create_world(42)
    killer = state.npcs[npc_id("lu_xuanji")]
    victim = state.npcs[npc_id("a_he")]
    victim.location_id = "location_xuanyue_sect"
    victim.health = 0.01

    for _ in range(5):
        if not victim.alive:
            break
        apply_command(
            state,
            make_command(
                state,
                killer.npc_id,
                "attack",
                {"target_id": victim.npc_id, "intent": "kill"},
                source="test",
            ),
        )
    player = state.npcs[PROTAGONIST_ID]
    assert all(goal.kind != "revenge" for goal in player.goals)
