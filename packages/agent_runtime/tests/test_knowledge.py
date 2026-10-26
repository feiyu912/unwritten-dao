"""Tests for the model-free knowledge boundary and explanation layer."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from agent_runtime.knowledge import (
    BELIEF_SECTION,
    FACT_SECTION,
    NpcKnowledgeView,
    explain_action,
    explain_event_chain,
)
from agent_runtime.models import ActionProposal, KnownLocation
from agent_runtime.observation import build_observation

from world_core import (
    ITEM_FOUNDATION_PILL,
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    PROTAGONIST_ID,
    WorldEvent,
    WorldState,
    apply_command,
    create_world,
    make_command,
)

_EVENT_LINE = re.compile(r"^E(\d+) \[tick=(\d+)\] ([A-Z_]+)")


def _send(state: WorldState, command_type: str, arguments: dict[str, Any]) -> list[WorldEvent]:
    command = make_command(
        state,
        PROTAGONIST_ID,
        command_type,  # type: ignore[arg-type]
        arguments,
        source="test",
    )
    return list(apply_command(state, command).events)


def _discover_realm(state: WorldState) -> list[WorldEvent]:
    events: list[WorldEvent] = []
    events += _send(state, "move", {"to_location_id": LOC_BLACKWOOD_FOREST})
    events += _send(state, "move", {"to_location_id": LOC_RUINED_TEMPLE})
    events += _send(
        state,
        "transfer_item",
        {
            "item_id": ITEM_MAP_FRAGMENT,
            "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
            "to": {"kind": "npc", "id": PROTAGONIST_ID},
        },
    )
    events += _send(state, "move", {"to_location_id": LOC_MISTY_VALLEY})
    events += _send(
        state,
        "investigate",
        {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
    )
    return events


def _proposal(memory_refs: list[int]) -> ActionProposal:
    return ActionProposal(
        proposal_id="00000000-0000-4000-8000-000000000001",
        decision_id="test:knowledge",
        npc_id=PROTAGONIST_ID,
        observed_world_version=0,
        goal_id="goal_breakthrough",
        intent="start_cultivation",
        arguments={"days": 30},
        memory_refs=memory_refs,
        rationale_short="cultivate until the opportunity is clear",
        confidence=0.5,
    )


def _all_section_text(sections: dict[str, list[str]]) -> str:
    return "\n".join(line for lines in sections.values() for line in lines)


def test_initial_facts_hide_secret_interior_and_pill() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    view = NpcKnowledgeView.from_observation(observation)

    facts_only = "\n".join(view.to_prompt_sections()[FACT_SECTION])
    assert LOC_ANCIENT_CAVE not in facts_only
    assert ITEM_FOUNDATION_PILL not in facts_only
    assert LOC_ANCIENT_CAVE not in view.known_location_ids
    assert view.validate_boundary(
        secret_interior_ids=[LOC_ANCIENT_CAVE],
        hidden_item_ids=[ITEM_FOUNDATION_PILL],
    ) == []

    # Beliefs are preserved in their own clearly labelled, fallible section.
    sections = view.to_prompt_sections()
    assert sections[BELIEF_SECTION] != ["none"]
    assert any("holds_ancient_relic" in line for line in sections[BELIEF_SECTION])
    assert "holds_ancient_relic" not in facts_only
    assert view.beliefs == tuple(observation.beliefs)


def test_discovery_promotes_interior_and_explanation_cites_valid_ids_only() -> None:
    state = create_world(42)
    events = _discover_realm(state)
    discovered = [event for event in events if event.type == "SECRET_REALM_DISCOVERED"]
    assert discovered, "expected a discovery event"
    valid_event = discovered[-1]

    observation = build_observation(
        state,
        PROTAGONIST_ID,
        memories=[
            {
                "event_id": valid_event.event_id,
                "tick": valid_event.tick,
                "summary": "the cave entrance answered the map",
                "importance": 0.9,
                "emotional_valence": 0.4,
            }
        ],
    )
    view = NpcKnowledgeView.from_observation(observation)

    assert LOC_ANCIENT_CAVE in view.known_location_ids
    facts_only = "\n".join(view.to_prompt_sections()[FACT_SECTION])
    assert LOC_ANCIENT_CAVE in facts_only
    assert view.validate_boundary(
        secret_interior_ids=[LOC_ANCIENT_CAVE],
        hidden_item_ids=[ITEM_FOUNDATION_PILL],
    ) == []

    explanation = explain_action(_proposal([valid_event.event_id, 999_999]), observation)
    assert "goal_breakthrough" in explanation
    assert "cultivate until the opportunity is clear" in explanation
    assert f"E{valid_event.event_id}" in explanation
    assert "E999999" not in explanation
    assert explanation == explain_action(_proposal([valid_event.event_id, 999_999]), observation)


def test_explanation_without_refs_says_so() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    explanation = explain_action(_proposal([]), observation)
    assert "no memory or event references were cited" in explanation
    assert "evidence:" in explanation


def test_redact_unknown_removes_hallucinated_fact_location() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    view = NpcKnowledgeView.from_observation(observation)
    hallucinated = KnownLocation(
        location_id="location_hallucinated_palace",
        name="Imagined Palace",
        kind="ruin",
        adjacent_ids=[LOC_MISTY_VALLEY],
    )
    tainted = replace(
        view,
        world_facts=replace(
            view.world_facts,
            known_locations=(*view.world_facts.known_locations, hallucinated),
        ),
    )

    violations = tainted.validate_boundary()
    assert any(
        row.code == "unknown_location_in_facts"
        and "location_hallucinated_palace" in row.ids
        for row in violations
    )

    boundary = (
        view.known_location_ids
        | view.known_item_ids
        | view.known_npc_ids
        | view.known_opportunity_ids
    )
    redacted = tainted.redact_unknown(boundary)
    facts_only = "\n".join(redacted.to_prompt_sections()[FACT_SECTION])
    assert "location_hallucinated_palace" not in facts_only
    assert "location_hallucinated_palace" not in redacted.known_location_ids
    assert redacted.validate_boundary() == []
    # Beliefs are untouched and no speculative id is promoted to a fact.
    assert redacted.beliefs == view.beliefs


def test_secret_interior_injected_into_facts_is_flagged() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    view = NpcKnowledgeView.from_observation(observation)
    leaked = KnownLocation(
        location_id=LOC_ANCIENT_CAVE,
        name="hidden cave",
        kind="secret_realm",
        adjacent_ids=[],
    )
    tainted = replace(
        view,
        world_facts=replace(
            view.world_facts,
            known_locations=(*view.world_facts.known_locations, leaked),
        ),
    )
    violations = tainted.validate_boundary(secret_interior_ids=[LOC_ANCIENT_CAVE])
    assert any(
        row.code == "secret_interior_leaked" and row.ids == (LOC_ANCIENT_CAVE,)
        for row in violations
    )


def test_event_chain_follows_real_parents_and_stops_at_missing_parent() -> None:
    state = create_world(42)
    events = _discover_realm(state)
    provided = {event.event_id for event in events}
    target = events[-1]
    assert target.type == "SECRET_REALM_DISCOVERED"

    lines = explain_event_chain(events, target.event_id)
    assert lines == explain_event_chain(events, target.event_id)
    assert len(lines) >= 2
    assert lines[-1].startswith(f"E{target.event_id} ")
    parsed_ids = []
    for line in lines:
        match = _EVENT_LINE.match(line)
        assert match is not None, line
        parsed_ids.append(int(match.group(1)))
        assert int(match.group(1)) in provided
        assert int(match.group(2)) >= 0
    assert parsed_ids == sorted(parsed_ids)
    assert target.event_id in parsed_ids

    truncated = explain_event_chain([target], target.event_id)
    assert len(truncated) == 1
    assert truncated[0].startswith(f"E{target.event_id} [tick={target.tick}] {target.type}")
    assert truncated[0].endswith("not provided)")


def test_event_chain_rejects_unknown_target() -> None:
    state = create_world(42)
    events = _discover_realm(state)
    result = explain_event_chain(events, 999_999)
    assert result == ["E999999 not found in provided events"]