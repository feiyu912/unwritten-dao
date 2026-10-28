"""Deterministic three-NPC contention encounter over the foundation pill.

The encounter uses the production decision path end to end: an
``NpcObservation`` is built for the NPC, a real policy proposes an action, the
proposal is validated into a ``WorldCommand``, and ``world_core`` applies it and
emits events. The player is absent for the whole encounter.

This file stages a scenario (positions, inventory and one goal) and never changes
a rule, a contract or a ``worldgen`` default. Two NPCs pursue their existing
goals against a third: the protagonist takes the pill, the rival attacks him,
and the alchemist elder backs the sect disciple. Contention is therefore
emergent from the policies, not scripted.

Evidence asserted here:

1. The winning claim cites the real realm-access chain (transfer -> investigate
   -> discovered -> entered -> claimed), so the encounter is traceable.
2. Every combat and relationship change is attributed to real participants.
3. Each of the three NPCs keeps episodic memories of the contention events, they
   are recalled after 30 absent ticks, and the recalled event is cited in the
   next proposal's ``memory_refs``.
4. The whole run is deterministic: replaying the same staged world produces the
   same event ids and the same state checksum.
"""

from __future__ import annotations

from collections.abc import Iterable

from agent_runtime.validator import decide_and_apply
from world_core.ruleset import RULESET
from world_server.agent_policy import policy_for
from world_server.memory_store import memory_candidates

from agent_runtime import InMemoryEpisodeStore, MemoryEpisode, build_observation
from world_core import (
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    LOC_STONE_TOWN,
    PLAYER_ID,
    PROTAGONIST_ID,
    REALM_ANCIENT_CAVE,
    Goal,
    WorldEvent,
    advance_time,
    apply_command,
    create_world,
    make_command,
    npc_id,
    restore_snapshot,
    snapshot,
    state_checksum,
    validate_state,
)

RIVAL_ID = npc_id("pei_lie")
ALCHEMIST_ID = npc_id("su_zhi")
ENCOUNTER_DAYS = 3
ABSENT_TICKS = 30


def _submit(state, actor_id: str | None, command_type: str, arguments: dict) -> list[WorldEvent]:
    command = make_command(state, actor_id, command_type, arguments, source="test")
    return apply_command(state, command).events


def _stage_protagonist_takes_the_map(state) -> list[WorldEvent]:
    """Walk the canonical map path so the claim has real causal parents."""
    protagonist = state.npcs[PROTAGONIST_ID]
    events: list[WorldEvent] = []
    for target in (LOC_BLACKWOOD_FOREST, LOC_RUINED_TEMPLE):
        events.extend(_submit(state, protagonist.npc_id, "move", {"to_location_id": target}))
    events.extend(
        _submit(
            state,
            protagonist.npc_id,
            "transfer_item",
            {
                "item_id": ITEM_MAP_FRAGMENT,
                "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
                "to": {"kind": "npc", "id": protagonist.npc_id},
            },
        )
    )
    events.extend(_submit(state, protagonist.npc_id, "move", {"to_location_id": LOC_MISTY_VALLEY}))
    events.extend(
        _submit(
            state,
            protagonist.npc_id,
            "investigate",
            {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
        )
    )
    events.extend(
        _submit(state, protagonist.npc_id, "enter_secret_realm", {"realm_id": REALM_ANCIENT_CAVE})
    )
    return events


def _stage_contenders(state) -> None:
    """Place the three NPCs in the same contested room (scenario setup only)."""
    protagonist = state.npcs[PROTAGONIST_ID]
    rival = state.npcs[RIVAL_ID]
    alchemist = state.npcs[ALCHEMIST_ID]

    # The protagonist is at his realm ceiling, so the claimed pill is usable.
    protagonist.stage = RULESET.max_stage(1)
    protagonist.qi = RULESET.cap_qi(1)

    # The rival is already at the contested site: the raid began before the
    # player arrived. Both contenders know the room they are standing in.
    for npc in (rival, alchemist):
        npc.location_id = LOC_ANCIENT_CAVE
        if LOC_ANCIENT_CAVE not in npc.known_locations:
            npc.known_locations.append(LOC_ANCIENT_CAVE)

    # The alchemist elder backs the sect's promising disciple (seed belief
    # "su_zhi -> shen_yan promising_disciple") against the rival. This is the
    # only added goal; it uses the documented defeat_rival kind.
    alchemist.goals.append(
        Goal(
            goal_id="goal_encounter_guard_disciple",
            kind="defeat_rival",
            priority=0.9,
            params={"target": rival.npc_id},
            created_tick=state.tick,
        )
    )


def _autonomous_days(state) -> list[WorldEvent]:
    """One decision per idle living non-player NPC per day, then advance a day."""
    events: list[WorldEvent] = []
    for _day in range(ENCOUNTER_DAYS):
        for npc_key in sorted(state.npcs):
            npc = state.npcs[npc_key]
            if not npc.alive or npc.active_action is not None:
                continue
            if npc.npc_id == PLAYER_ID:
                continue
            result = decide_and_apply(state, npc.npc_id, policy_for(npc).policy)
            if result is not None:
                events.extend(result.events)
        events.extend(advance_time(state, 1, source="system").events)
    return events


def _episodes(state, events: Iterable[WorldEvent], npc_id: str) -> list[MemoryEpisode]:
    episodes: list[MemoryEpisode] = []
    memory_id = 0
    for event in events:
        for candidate, summary, importance, valence in memory_candidates(state, event):
            if candidate != npc_id:
                continue
            memory_id += 1
            episodes.append(
                MemoryEpisode(
                    memory_id=memory_id,
                    npc_id=npc_id,
                    source_event_id=event.event_id,
                    summary=summary,
                    importance=importance,
                    emotional_valence=valence,
                    created_tick=event.tick,
                )
            )
    return episodes


def _event(events: Iterable[WorldEvent], event_type: str, **payload: object) -> WorldEvent | None:
    for event in events:
        if event.type != event_type:
            continue
        if all(event.payload.get(key) == value for key, value in payload.items()):
            return event
    return None


def _by_id(events: Iterable[WorldEvent], event_id: int | None) -> WorldEvent | None:
    return next((event for event in events if event.event_id == event_id), None)


def test_three_npc_pill_contention_is_traceable_and_recalled() -> None:
    state = create_world(42)
    staging_events = _stage_protagonist_takes_the_map(state)
    _stage_contenders(state)
    staged = snapshot(state)
    autonomous_events = _autonomous_days(state)
    absent_events = advance_time(state, ABSENT_TICKS, source="system").events
    events = list(staging_events) + autonomous_events + absent_events

    # 1. The protagonist wins the claim, and the claim is traceable to the real
    #    map -> investigate -> enter chain emitted by world_core itself.
    claim = _event(events, "OPPORTUNITY_CLAIMED", success=True)
    assert claim is not None
    assert claim.actor_ids == [PROTAGONIST_ID]
    entered = _event(events, "SECRET_REALM_ENTERED")
    assert entered is not None
    assert claim.causal_parent_ids == [entered.event_id]
    discovered = _by_id(events, entered.causal_parent_ids[0])
    assert discovered is not None and discovered.type == "SECRET_REALM_DISCOVERED"
    parents = [_by_id(events, parent_id) for parent_id in discovered.causal_parent_ids]
    assert {parent.type for parent in parents if parent is not None} == {
        "ITEM_TRANSFERRED",
        "LOCATION_INVESTIGATED",
    }

    # 2. The rival contests the protagonist by force and the alchemist elder
    #    answers it; every combat names both real participants.
    rival_attack = _event(events, "COMBAT_RESOLVED", attacker_id=RIVAL_ID)
    assert rival_attack is not None
    assert PROTAGONIST_ID in rival_attack.target_ids
    elder_attack = _event(events, "COMBAT_RESOLVED", attacker_id=ALCHEMIST_ID)
    assert elder_attack is not None
    assert RIVAL_ID in elder_attack.target_ids
    changed = [
        event
        for event in events
        if event.type == "RELATIONSHIP_CHANGED"
        and set(event.causal_parent_ids) & {rival_attack.event_id, elder_attack.event_id}
    ]
    assert changed

    # 3. The player never acted: the encounter belongs to the NPCs.
    assert all(PLAYER_ID not in event.actor_ids for event in events)
    assert state.npcs[PLAYER_ID].location_id == LOC_STONE_TOWN

    # 4. Each contender keeps real episodic memories of the contention.
    contention_ids = {
        claim.event_id,
        rival_attack.event_id,
        elder_attack.event_id,
    }
    for npc, query, expected in (
        (PROTAGONIST_ID, "洞府丹藏", claim.event_id),
        (RIVAL_ID, "combat", rival_attack.event_id),
        (ALCHEMIST_ID, "combat", elder_attack.event_id),
    ):
        episodes = _episodes(state, events, npc)
        assert any(episode.source_event_id in contention_ids for episode in episodes), npc
        store = InMemoryEpisodeStore(episodes)
        recalled = store.retrieve(
            npc_id=npc,
            now_tick=state.tick,
            query=query,
            top_k=5,
        )
        recalled_ids = {episode.source_event_id for episode in recalled}
        assert expected in recalled_ids, (npc, query, recalled_ids)

        # The recalled consequence is cited by the next proposal.
        rows = [
            {
                "event_id": episode.source_event_id,
                "tick": episode.created_tick,
                "summary": episode.summary,
                "importance": episode.importance,
                "emotional_valence": episode.emotional_valence,
            }
            for episode in recalled
            if episode.source_event_id == expected
        ]
        observation = build_observation(state, npc, memories=rows)
        proposal = policy_for(state.npcs[npc]).policy.decide(observation)
        assert expected in proposal.memory_refs, (npc, proposal.memory_refs)

    # 5. Same staged world, same decisions, same events and checksum.
    assert validate_state(state) == []
    replay_state = restore_snapshot(staged)
    replay_autonomous = _autonomous_days(replay_state)
    replay_absent = advance_time(replay_state, ABSENT_TICKS, source="system").events
    replay_events = replay_autonomous + replay_absent
    assert [event.event_id for event in replay_events] == [
        event.event_id for event in autonomous_events + absent_events
    ]
    assert [event.type for event in replay_events] == [
        event.type for event in autonomous_events + absent_events
    ]
    assert state_checksum(replay_state) == state_checksum(state)

    # The majority of the world is untouched: only the contenders moved.
    assert all(
        npc.location_id != LOC_ANCIENT_CAVE
        for npc in state.npcs.values()
        if npc.npc_id not in {PROTAGONIST_ID, RIVAL_ID, ALCHEMIST_ID}
    )
