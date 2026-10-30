from __future__ import annotations

import pytest

from world_core import (
    CommandRejected,
    advance_time,
    apply_command,
    create_world,
    make_command,
    restore_snapshot,
    snapshot,
    state_checksum,
)

TARGET_LOCATION = "location_blackwood_forest"
GOAL = "goal_defeat_rival"


def _rival_and_player(state):
    rival = next(
        npc
        for npc in state.npcs.values()
        if any(goal.goal_id == GOAL for goal in npc.goals)
    )
    return rival, state.npcs[state.player_id]


def _bring_player_to_rival(state) -> list:
    player = state.npcs[state.player_id]
    commands = []
    for target in (
        "location_xuanyue_sect",
        TARGET_LOCATION,
        "location_chixiao_outpost",
    ):
        command = make_command(state, player.npc_id, "move", {"to_location_id": target})
        apply_command(state, command)
        commands.append(command)
    return commands


def _commit(state, until_ticks: int = 3):
    rival, player = _rival_and_player(state)
    command = make_command(
        state,
        rival.npc_id,
        "make_commitment",
        {
            "with_npc_id": player.npc_id,
            "promised_goal_id": GOAL,
            "target_location_id": TARGET_LOCATION,
            "until_ticks": until_ticks,
            "terms": "先查明落鸦林的真相，再谈复仇。",
        },
    )
    return command, apply_command(state, command)


def test_commitment_defers_attack_then_fulfills_on_investigation() -> None:
    state = create_world(42)
    initial = snapshot(state)
    commands = _bring_player_to_rival(state)
    rival, player = _rival_and_player(state)
    assert rival.location_id == player.location_id == "location_chixiao_outpost"

    command, result = _commit(state)
    commands.append(command)
    assert result.events[0].type == "COMMITMENT_MADE"
    commitment = next(goal for goal in rival.goals if goal.kind == "commitment")
    assert commitment.status == "active"
    promised = next(goal for goal in rival.goals if goal.goal_id == GOAL)
    assert promised.params["deferred_until_tick"] == state.tick + 3
    assert promised.params["commitment_id"] == commitment.goal_id

    for target in ("location_blackwood_forest", "location_xuanyue_sect"):
        move = make_command(state, rival.npc_id, "move", {"to_location_id": target})
        apply_command(state, move)
        commands.append(move)
    target_id = promised.params.get("target_id") or promised.params.get("target")
    target_npc = state.npcs[target_id]
    assert rival.location_id == target_npc.location_id
    attack = make_command(
        state, rival.npc_id, "attack", {"target_id": target_npc.npc_id, "intent": "kill"}
    )
    with pytest.raises(CommandRejected) as rejected:
        apply_command(state, attack)
    assert rejected.value.code == "commitment_deferred"

    move = make_command(state, rival.npc_id, "move", {"to_location_id": TARGET_LOCATION})
    apply_command(state, move)
    commands.append(move)
    investigate = make_command(
        state, rival.npc_id, "investigate", {"target_location_id": TARGET_LOCATION}
    )
    result = apply_command(state, investigate)
    commands.append(investigate)
    assert [event.type for event in result.events] == [
        "LOCATION_INVESTIGATED",
        "COMMITMENT_FULFILLED",
    ]
    assert commitment.status == "achieved"
    assert "deferred_until_tick" not in promised.params
    assert promised.params["commitment_fulfilled_tick"] == state.tick

    replay = restore_snapshot(initial)
    for item in commands:
        apply_command(replay, item)
    assert state_checksum(replay) == state_checksum(state)


def test_commitment_expires_and_clears_the_deferral() -> None:
    state = create_world(42)
    _bring_player_to_rival(state)
    rival, _ = _rival_and_player(state)
    _command, result = _commit(state, until_ticks=1)
    assert result.events[0].type == "COMMITMENT_MADE"
    commitment = next(goal for goal in rival.goals if goal.kind == "commitment")
    promised = next(goal for goal in rival.goals if goal.goal_id == GOAL)

    result = advance_time(state, 2)
    assert any(event.type == "COMMITMENT_BROKEN" for event in result.events)
    assert commitment.status == "failed"
    assert "deferred_until_tick" not in promised.params


def test_commitment_requires_both_actors_to_be_present() -> None:
    state = create_world(42)
    rival, player = _rival_and_player(state)
    assert rival.location_id != player.location_id
    command = make_command(
        state,
        rival.npc_id,
        "make_commitment",
        {
            "with_npc_id": player.npc_id,
            "promised_goal_id": GOAL,
            "target_location_id": TARGET_LOCATION,
            "until_ticks": 3,
            "terms": "先调查再复仇。",
        },
    )
    with pytest.raises(CommandRejected) as rejected:
        apply_command(state, command)
    assert rejected.value.code == "not_together"
