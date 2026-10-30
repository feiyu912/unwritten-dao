"""An NPC that made a commitment must not propose the deferred hostile action.

The simulator rejects a deferred attack (``commitment_deferred``). Without this
guard the deterministic policy would propose the same attack again, the single
fallback would be rejected too, and ``decide_and_apply`` would raise instead of
advancing the world. The promise exists so the character itself holds it.
"""

from __future__ import annotations

from agent_runtime.validator import decide_and_apply
from world_core.goal_evolution import goal_target_id

from agent_runtime import RivalryPolicy, UtilityPolicy, build_observation
from world_core import (
    LOC_XUANYUE_SECT,
    PROTAGONIST_ID,
    Goal,
    apply_command,
    create_world,
    make_command,
    npc_id,
)

RIVAL_ID = npc_id("pei_lie")


def _world_with_revenge_promise():
    state = create_world(42)
    killer = state.npcs[npc_id("lu_xuanji")]
    survivor = state.npcs[npc_id("su_zhi")]
    player = state.npcs[state.player_id]
    state.npcs[PROTAGONIST_ID].location_id = LOC_XUANYUE_SECT
    killer.location_id = LOC_XUANYUE_SECT
    survivor.location_id = LOC_XUANYUE_SECT
    survivor.goals.append(
        Goal(
            goal_id="goal_avenge_probe",
            kind="revenge",
            priority=0.9,
            params={"target_id": killer.npc_id},
            created_tick=0,
        )
    )
    apply_command(
        state,
        make_command(state, player.npc_id, "move", {"to_location_id": LOC_XUANYUE_SECT}),
    )
    return state, survivor, killer


def test_deferred_revenge_goal_is_not_proposed_and_does_not_crash_fallback() -> None:
    state, survivor, killer = _world_with_revenge_promise()
    observation = build_observation(state, survivor.npc_id)
    # The raw goal is still active and the target is visible.
    assert UtilityPolicy().decide(observation).intent == "attack"

    apply_command(
        state,
        make_command(
            state,
            survivor.npc_id,
            "make_commitment",
            {
                "with_npc_id": state.player_id,
                "promised_goal_id": "goal_avenge_probe",
                "target_location_id": LOC_XUANYUE_SECT,
                "until_ticks": 5,
                "terms": "先与道友查清此事，再谈报仇。",
            },
        ),
    )
    result = decide_and_apply(state, survivor.npc_id, UtilityPolicy())
    assert result is not None
    assert all(event.type != "COMBAT_RESOLVED" for event in result.events)
    assert killer.alive


def test_deferred_rival_goal_is_not_proposed_by_rivalry_policy() -> None:
    state = create_world(42)
    rival = state.npcs[RIVAL_ID]
    protagonist = state.npcs[PROTAGONIST_ID]
    player = state.npcs[state.player_id]
    rival.location_id = LOC_XUANYUE_SECT
    protagonist.location_id = LOC_XUANYUE_SECT
    apply_command(
        state,
        make_command(state, player.npc_id, "move", {"to_location_id": LOC_XUANYUE_SECT}),
    )
    rival_goal = next(goal for goal in rival.goals if goal.kind == "defeat_rival")
    assert goal_target_id(rival_goal) == PROTAGONIST_ID
    assert RivalryPolicy().decide(build_observation(state, rival.npc_id)).intent == "attack"

    apply_command(
        state,
        make_command(
            state,
            rival.npc_id,
            "make_commitment",
            {
                "with_npc_id": state.player_id,
                "promised_goal_id": rival_goal.goal_id,
                "target_location_id": LOC_XUANYUE_SECT,
                "until_ticks": 5,
                "terms": "五日之内不动这玄岳弟子。",
            },
        ),
    )
    result = decide_and_apply(state, rival.npc_id, RivalryPolicy())
    assert result is not None
    assert all(event.type != "COMBAT_RESOLVED" for event in result.events)
    assert protagonist.alive
