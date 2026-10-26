"""Knowledge-boundary and explanation layer.

This module is deliberately model-free and read-only. It turns an
``NpcObservation`` into an explicitly partitioned view (authoritative facts,
private state, fallible beliefs, memories), can redact ids the NPC does not
know, validates that secret interiors / hidden items never leak into facts,
and renders deterministic explanations from already-supplied evidence.

It never reads ``WorldState`` and never invents ids, events, or facts.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from world_core.events import WorldEvent

from agent_runtime.models import (
    ActionProposal,
    KnownLocation,
    MemoryRecord,
    NpcObservation,
    ObservationSelf,
    ObservedBelief,
    ObservedGoal,
    ObservedItem,
    ObservedRelationship,
    VisibleNpc,
    VisibleOpportunity,
)

FACT_SECTION = "WORLD_FACTS"
PRIVATE_SECTION = "PRIVATE_STATE"
BELIEF_SECTION = "BELIEFS (POSSIBLY FALSE)"
MEMORY_SECTION = "MEMORIES"


@dataclass(frozen=True)
class KnowledgeViolation:
    """One detected breach of the knowledge boundary."""

    code: str
    message: str
    ids: tuple[str, ...] = ()


class KnowledgeBoundaryError(ValueError):
    """Raised when authoritative facts contain ids the NPC cannot know."""

    def __init__(self, violations: Sequence[KnowledgeViolation]) -> None:
        self.violations = tuple(violations)
        detail = "; ".join(f"{row.code}: {row.message}" for row in self.violations)
        super().__init__(detail or "knowledge boundary violation")


@dataclass(frozen=True)
class WorldFacts:
    """Authoritative, observation-backed facts only."""

    self_state: ObservationSelf
    location_id: str
    location_name: str
    visible_items: tuple[ObservedItem, ...] = ()
    visible_opportunities: tuple[VisibleOpportunity, ...] = ()
    visible_npcs: tuple[VisibleNpc, ...] = ()
    known_locations: tuple[KnownLocation, ...] = ()


@dataclass(frozen=True)
class PrivateState:
    """The NPC's own inventory, goals, and relationships."""

    inventory: tuple[ObservedItem, ...] = ()
    goals: tuple[ObservedGoal, ...] = ()
    relationships: tuple[ObservedRelationship, ...] = ()


@dataclass(frozen=True)
class NpcKnowledgeView:
    """A partitioned, redactable view of what one NPC knows."""

    npc_id: str
    tick: int
    world_facts: WorldFacts
    private_state: PrivateState
    beliefs: tuple[ObservedBelief, ...] = ()
    memories: tuple[MemoryRecord, ...] = ()
    known_location_ids: frozenset[str] = frozenset()
    known_item_ids: frozenset[str] = frozenset()
    known_npc_ids: frozenset[str] = frozenset()
    known_opportunity_ids: frozenset[str] = frozenset()

    @classmethod
    def from_observation(
        cls,
        observation: NpcObservation,
        *,
        memories: Sequence[MemoryRecord] = (),
    ) -> NpcKnowledgeView:
        """Build the view from an observation plus optional extra memories."""
        location = next(
            (
                row
                for row in observation.known_locations
                if row.location_id == observation.location_id
            ),
            None,
        )
        location_name = location.name if location is not None else observation.location_id

        merged: dict[int, MemoryRecord] = {
            memory.event_id: memory for memory in observation.memories
        }
        for memory in memories:
            merged[memory.event_id] = memory

        known_locations = tuple(
            sorted(observation.known_locations, key=lambda row: row.location_id)
        )
        visible_items = tuple(sorted(observation.visible_items, key=lambda row: row.item_id))
        visible_npcs = tuple(sorted(observation.visible_npcs, key=lambda row: row.npc_id))
        inventory = tuple(sorted(observation.inventory, key=lambda row: row.item_id))

        return cls(
            npc_id=observation.npc_id,
            tick=observation.tick,
            world_facts=WorldFacts(
                self_state=observation.self,
                location_id=observation.location_id,
                location_name=location_name,
                visible_items=visible_items,
                visible_opportunities=tuple(
                    sorted(
                        observation.visible_opportunities,
                        key=lambda row: row.opportunity_id,
                    )
                ),
                visible_npcs=visible_npcs,
                known_locations=known_locations,
            ),
            private_state=PrivateState(
                inventory=inventory,
                goals=tuple(sorted(observation.goals, key=lambda row: row.goal_id)),
                relationships=tuple(sorted(observation.relationships, key=lambda row: row.npc_id)),
            ),
            beliefs=tuple(
                sorted(
                    observation.beliefs,
                    key=lambda row: (row.subject_key, row.predicate),
                )
            ),
            memories=tuple(merged[event_id] for event_id in sorted(merged)),
            known_location_ids=frozenset(row.location_id for row in known_locations)
            | {observation.location_id},
            known_item_ids=frozenset(row.item_id for row in inventory)
            | frozenset(row.item_id for row in visible_items),
            known_npc_ids=frozenset(row.npc_id for row in visible_npcs),
            known_opportunity_ids=frozenset(
                row.opportunity_id for row in observation.visible_opportunities
            ),
        )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def to_prompt_sections(self) -> dict[str, list[str]]:
        """Return labelled prompt sections with facts and beliefs separated."""
        facts = self.world_facts
        view = facts.self_state
        fact_lines = [
            f"self: {view.name} realm={view.realm} stage={view.stage} "
            f"qi={view.qi} foundation={view.foundation:.2f} health={view.health:.2f}",
            f"present_at: {facts.location_id} ({facts.location_name})",
        ]
        if facts.visible_items:
            fact_lines.extend(
                f"visible_item: {item.item_id} ({item.name}, {item.kind})"
                for item in facts.visible_items
            )
        if facts.visible_opportunities:
            fact_lines.extend(
                f"visible_opportunity: {opp.opportunity_id} ({opp.name}, {opp.kind})"
                for opp in facts.visible_opportunities
            )
        if facts.visible_npcs:
            fact_lines.extend(
                f"visible_npc: {npc.npc_id} ({npc.name}, realm={npc.realm} stage={npc.stage})"
                for npc in facts.visible_npcs
            )
        if facts.known_locations:
            fact_lines.extend(
                f"known_location: {loc.location_id} ({loc.name}, {loc.kind}) "
                f"adjacent={','.join(loc.adjacent_ids) or 'none'}"
                for loc in facts.known_locations
            )

        private = self.private_state
        private_lines: list[str] = []
        private_lines.extend(
            f"inventory_item: {item.item_id} ({item.name}, {item.kind})"
            for item in private.inventory
        )
        private_lines.extend(
            f"goal: {goal.goal_id} ({goal.kind}, status={goal.status}, "
            f"priority={goal.priority:.2f})"
            for goal in private.goals
        )
        private_lines.extend(
            f"relationship: {rel.npc_id} affinity={rel.affinity} trust={rel.trust} "
            f"fear={rel.fear} respect={rel.respect} debt={rel.debt}"
            for rel in private.relationships
        )
        if not private_lines:
            private_lines.append("none")

        belief_lines = [
            f"{belief.subject_key} | {belief.predicate} = {belief.object_value} "
            f"(confidence {belief.confidence:.2f})"
            for belief in self.beliefs
        ] or ["none"]

        memory_lines = [
            f"E{memory.event_id} (tick {memory.tick}): {memory.summary}" for memory in self.memories
        ] or ["none"]

        return {
            FACT_SECTION: fact_lines,
            PRIVATE_SECTION: private_lines,
            BELIEF_SECTION: belief_lines,
            MEMORY_SECTION: memory_lines,
        }

    # ------------------------------------------------------------------
    # Redaction and validation
    # ------------------------------------------------------------------
    def redact_unknown(self, known_ids: Iterable[str]) -> NpcKnowledgeView:
        """Return a copy with unknown location/item/NPC ids removed from facts.

        ``known_ids`` can only shrink the boundary: this never promotes an id
        to a fact. Beliefs and memories are left untouched so a belief may
        keep naming a speculative id, but no new belief is created.
        """
        known = (
            frozenset(known_ids)
            | {self.world_facts.location_id}
            | {item.item_id for item in self.private_state.inventory}
        )
        facts = self.world_facts
        kept_locations: list[KnownLocation] = []
        for location in facts.known_locations:
            if location.location_id not in known:
                continue
            kept_locations.append(
                location.model_copy(
                    update={"adjacent_ids": [adj for adj in location.adjacent_ids if adj in known]}
                )
            )
        redacted_facts = replace(
            facts,
            visible_items=tuple(item for item in facts.visible_items if item.item_id in known),
            visible_npcs=tuple(npc for npc in facts.visible_npcs if npc.npc_id in known),
            visible_opportunities=tuple(
                opp for opp in facts.visible_opportunities if opp.opportunity_id in known
            ),
            known_locations=tuple(kept_locations),
        )
        return replace(
            self,
            world_facts=redacted_facts,
            known_location_ids=self.known_location_ids & known,
            known_item_ids=self.known_item_ids & known,
            known_npc_ids=self.known_npc_ids & known,
            known_opportunity_ids=self.known_opportunity_ids & known,
        )

    def validate_boundary(
        self,
        *,
        secret_interior_ids: Iterable[str] = (),
        hidden_item_ids: Iterable[str] = (),
    ) -> list[KnowledgeViolation]:
        """Return every fact-section id the NPC is not allowed to know."""
        secret_ids = frozenset(secret_interior_ids)
        hidden_ids = frozenset(hidden_item_ids)
        inventory_ids = frozenset(item.item_id for item in self.private_state.inventory)
        violations: list[KnowledgeViolation] = []
        seen: set[tuple[str, str]] = set()

        def report(code: str, message: str, identifier: str) -> None:
            key = (code, identifier)
            if key in seen:
                return
            seen.add(key)
            violations.append(KnowledgeViolation(code, message, (identifier,)))

        facts = self.world_facts
        fact_location_ids = {facts.location_id}
        for location in facts.known_locations:
            fact_location_ids.add(location.location_id)
            fact_location_ids.update(location.adjacent_ids)
        for location_id in sorted(fact_location_ids):
            if location_id not in self.known_location_ids:
                code = (
                    "secret_interior_leaked"
                    if location_id in secret_ids
                    else "unknown_location_in_facts"
                )
                report(code, f"location {location_id} is not known to {self.npc_id}", location_id)

        for item in facts.visible_items:
            if item.item_id in hidden_ids and item.item_id not in inventory_ids:
                report(
                    "hidden_item_leaked",
                    f"hidden item {item.item_id} appears before acquisition",
                    item.item_id,
                )
            elif item.item_id not in self.known_item_ids:
                report(
                    "unknown_item_in_facts",
                    f"item {item.item_id} is not known to {self.npc_id}",
                    item.item_id,
                )

        for npc in facts.visible_npcs:
            if npc.npc_id not in self.known_npc_ids:
                report(
                    "unknown_npc_in_facts",
                    f"npc {npc.npc_id} is not visible to {self.npc_id}",
                    npc.npc_id,
                )

        for opp in facts.visible_opportunities:
            if opp.opportunity_id not in self.known_opportunity_ids:
                report(
                    "unknown_opportunity_in_facts",
                    f"opportunity {opp.opportunity_id} is not visible",
                    opp.opportunity_id,
                )

        violations.sort(key=lambda row: (row.code, row.ids))
        return violations

    def raise_if_invalid(
        self,
        *,
        secret_interior_ids: Iterable[str] = (),
        hidden_item_ids: Iterable[str] = (),
    ) -> None:
        """Raise :class:`KnowledgeBoundaryError` if facts contain unknown ids."""
        violations = self.validate_boundary(
            secret_interior_ids=secret_interior_ids,
            hidden_item_ids=hidden_item_ids,
        )
        if violations:
            raise KnowledgeBoundaryError(violations)


# ----------------------------------------------------------------------
# Explanations
# ----------------------------------------------------------------------
def explain_action(proposal: ActionProposal, observation: NpcObservation) -> str:
    """Deterministically explain a proposal using only supplied evidence.

    Cites the selected strategic goal, ``rationale_short``, and only memory or
    recent-event ids that actually exist in ``observation``. Refs that are not
    present are dropped, never cited, so the text cannot invent evidence.
    """
    goals = {goal.goal_id: goal for goal in observation.goals}
    if proposal.goal_id is None:
        goal_line = "goal: none selected"
    elif proposal.goal_id in goals:
        goal = goals[proposal.goal_id]
        goal_line = f"goal: {goal.goal_id} ({goal.kind}, priority {goal.priority:.2f})"
    else:
        goal_line = f"goal: {proposal.goal_id} (not present in observation)"

    known_ids: dict[int, str] = {}
    for memory in observation.memories:
        known_ids[memory.event_id] = f"E{memory.event_id}: {memory.summary}"
    for event in observation.recent_events:
        known_ids.setdefault(
            event.event_id,
            f"E{event.event_id} [{event.type}]: {event.summary}",
        )

    cited = sorted({ref for ref in proposal.memory_refs if ref in known_ids})
    if cited:
        evidence_line = "evidence: " + "; ".join(known_ids[ref] for ref in cited)
    else:
        evidence_line = "evidence: no memory or event references were cited"

    lines = [
        f"npc {observation.npc_id} at tick {observation.tick} proposed {proposal.intent}",
        goal_line,
        f"rationale: {proposal.rationale_short}",
        evidence_line,
    ]
    return "\n".join(lines)


def explain_event_chain(
    events: Iterable[WorldEvent],
    target_event_id: int,
    max_depth: int = 6,
) -> list[str]:
    """Render the real causal chain ending at ``target_event_id``.

    Only events present in ``events`` are used. The chain follows the first
    recorded ``causal_parent_ids`` entry; a missing parent stops the walk. The
    output is deterministic and bounded by ``max_depth``.
    """
    if max_depth < 1:
        return []
    index = {event.event_id: event for event in events}
    target = index.get(target_event_id)
    if target is None:
        return [f"E{target_event_id} not found in provided events"]

    chain: list[WorldEvent] = []
    missing_parent: int | None = None
    seen: set[int] = set()
    node: WorldEvent | None = target
    while node is not None and len(chain) < max_depth:
        if node.event_id in seen:
            break
        seen.add(node.event_id)
        chain.append(node)
        parent_id = node.causal_parent_ids[0] if node.causal_parent_ids else None
        if parent_id is None:
            break
        parent = index.get(parent_id)
        if parent is None:
            missing_parent = parent_id
            break
        node = parent
    chain.reverse()

    lines: list[str] = []
    for position, event in enumerate(chain):
        line = f"E{event.event_id} [tick={event.tick}] {event.type}"
        if position == 0 and missing_parent is not None:
            line += f" (root; parent E{missing_parent} not provided)"
        lines.append(line)
    return lines


__all__ = [
    "BELIEF_SECTION",
    "FACT_SECTION",
    "MEMORY_SECTION",
    "PRIVATE_SECTION",
    "KnowledgeBoundaryError",
    "KnowledgeViolation",
    "NpcKnowledgeView",
    "PrivateState",
    "WorldFacts",
    "explain_action",
    "explain_event_chain",
]
