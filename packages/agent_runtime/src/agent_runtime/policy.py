"""Deterministic utility policy used as the R1 agent brain and fallback."""

from __future__ import annotations

import uuid
from collections import deque

from world_core.ruleset import RULESET

from agent_runtime.models import (
    ActionProposal,
    KnownLocation,
    NpcObservation,
    ObservationSelf,
    ObservedBelief,
    ObservedGoal,
    ObservedItem,
)

_ID_NAMESPACE = uuid.UUID("c1b2f0e4-5c7d-4a91-b3d8-2e6f8a9c0d17")
_CULTIVATION_DAYS = 30


class UtilityPolicy:
    """Goal-driven, deterministic policy. No randomness, stable ordering."""

    def decide(self, observation: NpcObservation) -> ActionProposal:
        goal = _breakthrough_goal(observation.goals)
        if goal is not None:
            special = self._breakthrough_path(observation, goal)
            if special is not None:
                return special
        return _cultivate(observation)

    def _breakthrough_path(
        self, obs: NpcObservation, goal: ObservedGoal
    ) -> ActionProposal | None:
        locations = {location.location_id: location for location in obs.known_locations}
        current = obs.location_id
        pill = _owned_pill(obs)
        if pill is not None and _at_realm_cap(obs.self):
            return _proposal(
                obs,
                "attempt_breakthrough",
                {"pill_item_id": pill.item_id},
                "the realm cap is reached and a pill is in hand",
                goal.goal_id,
                confidence=0.85,
            )

        if current in locations and locations[current].kind == "secret_realm":
            if obs.visible_opportunities:
                opportunity = sorted(
                    obs.visible_opportunities, key=lambda row: row.opportunity_id
                )[0]
                return _proposal(
                    obs,
                    "claim_opportunity",
                    {"opportunity_id": opportunity.opportunity_id},
                    "an unclaimed opportunity is visible here",
                    goal.goal_id,
                    confidence=0.8,
                )
            return _proposal(
                obs,
                "start_cultivation",
                {"days": _CULTIVATION_DAYS},
                "cultivate inside the discovered realm",
                goal.goal_id,
            )

        interior = _known_interior(obs, current)
        if interior is not None:
            return _proposal(
                obs,
                "move",
                {"to_location_id": interior.location_id},
                "the discovered realm interior is adjacent",
                goal.goal_id,
                confidence=0.85,
            )

        map_item = _owned_map(obs)
        if map_item is not None:
            target = map_item.properties.get("points_to")
            if isinstance(target, str) and target in locations:
                if target == current:
                    if _entrance_found(obs):
                        return None
                    return _proposal(
                        obs,
                        "investigate",
                        {"target_location_id": current, "focus": "secret_realm"},
                        "the map points here; search for the entrance",
                        goal.goal_id,
                        confidence=0.8,
                    )
                step = _next_step(obs, target)
                if step is not None:
                    return _proposal(
                        obs,
                        "move",
                        {"to_location_id": step},
                        "follow the map toward its marked location",
                        goal.goal_id,
                        confidence=0.75,
                    )
            return None

        visible_map = sorted(
            (item for item in obs.visible_items if item.kind == "map"),
            key=lambda item: item.item_id,
        )
        if visible_map:
            return _proposal(
                obs,
                "transfer_item",
                {
                    "item_id": visible_map[0].item_id,
                    "from": {"kind": "location", "id": current},
                    "to": {"kind": "npc", "id": obs.npc_id},
                },
                "a map lies here; take it",
                goal.goal_id,
                confidence=0.7,
            )

        target = _belief_target(obs, locations)
        if target is not None:
            if target == current:
                return None
            step = _next_step(obs, target)
            if step is not None:
                return _proposal(
                    obs,
                    "move",
                    {"to_location_id": step},
                    "follow the lead about an ancient relic",
                    goal.goal_id,
                    confidence=0.55,
                )
        return None


def _proposal(
    observation: NpcObservation,
    intent: str,
    arguments: dict[str, object],
    rationale: str,
    goal_id: str | None,
    *,
    confidence: float = 0.7,
) -> ActionProposal:
    decision_id = f"util:{observation.npc_id}:{observation.tick}:{intent}"
    return ActionProposal(
        proposal_id=str(uuid.uuid5(_ID_NAMESPACE, decision_id)),
        decision_id=decision_id,
        npc_id=observation.npc_id,
        observed_world_version=observation.world_version,
        goal_id=goal_id,
        intent=intent,  # type: ignore[arg-type]
        arguments=arguments,
        valid_for_ticks=7,
        memory_refs=[memory.event_id for memory in observation.memories[:3]],
        rationale_short=rationale,
        confidence=confidence,
    )


def _cultivate(observation: NpcObservation) -> ActionProposal:
    goal = _breakthrough_goal(observation.goals)
    return _proposal(
        observation,
        "start_cultivation",
        {"days": _CULTIVATION_DAYS},
        "cultivate in place",
        goal.goal_id if goal else None,
        confidence=0.5,
    )


def _breakthrough_goal(goals: list[ObservedGoal]) -> ObservedGoal | None:
    active = [goal for goal in goals if goal.kind == "breakthrough" and goal.status == "active"]
    if not active:
        return None
    return sorted(active, key=lambda goal: (-goal.priority, goal.goal_id))[0]


def _owned_pill(observation: NpcObservation) -> ObservedItem | None:
    pills = sorted(
        (item for item in observation.inventory if item.kind == "pill"),
        key=lambda item: item.item_id,
    )
    return pills[0] if pills else None


def _owned_map(observation: NpcObservation) -> ObservedItem | None:
    maps = sorted(
        (item for item in observation.inventory if item.kind == "map"),
        key=lambda item: item.item_id,
    )
    return maps[0] if maps else None


def _at_realm_cap(self_view: ObservationSelf) -> bool:
    if self_view.realm not in RULESET.realms:
        return False
    return (
        self_view.stage >= RULESET.max_stage(self_view.realm)
        and self_view.qi >= RULESET.cap_qi(self_view.realm)
    )


def _entrance_found(observation: NpcObservation) -> bool:
    return any(belief.predicate == "entrance_found" for belief in observation.beliefs)


def _known_interior(observation: NpcObservation, current: str) -> KnownLocation | None:
    candidates = [
        location
        for location in observation.known_locations
        if location.kind == "secret_realm" and current in location.adjacent_ids
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda location: location.location_id)[0]


def _belief_target(
    observation: NpcObservation, locations: dict[str, KnownLocation]
) -> str | None:
    leads: list[ObservedBelief] = [
        belief
        for belief in observation.beliefs
        if belief.predicate in {"holds_ancient_relic", "linked_to_relics"}
        and isinstance(belief.subject_key, str)
        and belief.subject_key in locations
    ]
    if not leads:
        return None
    leads.sort(key=lambda belief: (-belief.confidence, belief.subject_key))
    return leads[0].subject_key


def _next_step(observation: NpcObservation, target: str) -> str | None:
    locations = {location.location_id: location for location in observation.known_locations}
    current = observation.location_id
    if current not in locations or target not in locations or current == target:
        return None
    previous: dict[str, str | None] = {current: None}
    queue: deque[str] = deque([current])
    while queue:
        node = queue.popleft()
        if node == target:
            break
        for adjacent in sorted(locations[node].adjacent_ids):
            if adjacent in locations and adjacent not in previous:
                previous[adjacent] = node
                queue.append(adjacent)
    if target not in previous:
        return None
    node = target
    while previous[node] is not None and previous[node] != current:
        node = previous[node]  # type: ignore[assignment]
    return node if previous[node] == current else None


__all__ = ["UtilityPolicy"]