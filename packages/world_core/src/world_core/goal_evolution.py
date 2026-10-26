"""Goal lifecycle rules.

Goals are persistent state: they are created by worldgen or by these rules and
are only changed by documented events. There is no random abandonment and no
per-tick regeneration.

Documented transitions
----------------------
* A named NPC dies with a recorded killer: every alive NPC holding a strong
  relationship to the victim (``affinity >= 20`` or ``respect >= 20``) gains a
  persistent ``revenge`` goal whose target is the killer. The goal cites the
  ``NPC_DIED`` event as its origin.
* An NPC dies: every active ``defeat_rival`` goal that targets the victim
  becomes ``achieved``.
* A breakthrough succeeds: every active ``breakthrough`` goal whose target
  realm has been reached becomes ``achieved`` and records provenance.
* Expiry: an active non-revenge goal with a dead target is abandoned; a revenge
  goal is never abandoned, and becomes achieved once its target dies.
"""

from __future__ import annotations

from world_core.models import Goal, Npc, WorldState, relationship_key
from world_core.worldgen import stable_id

STRONG_RELATIONSHIP_THRESHOLD = 20
REVENGE_PRIORITY = 0.9


def goal_target_id(goal: Goal) -> str | None:
    """Read a goal's target, accepting both the legacy ``target`` and the
    explicit ``target_id`` key used by newer goals."""
    for key in ("target_id", "target"):
        value = goal.params.get(key)
        if isinstance(value, str):
            return value
    return None


def revenge_goal_id(npc_id: str, victim_id: str, killer_id: str, death_event_id: int) -> str:
    """Stable id so replaying the same death produces the same goal id."""
    return stable_id("goal", f"revenge:{npc_id}:{victim_id}:{killer_id}:{death_event_id}")


def _has_revenge_against(npc: Npc, killer_id: str, goal_id: str) -> bool:
    """A survivor needs at most one revenge goal per killer, ever."""
    return any(
        goal.kind == "revenge"
        and (goal.goal_id == goal_id or goal_target_id(goal) == killer_id)
        for goal in npc.goals
    )


def apply_death_goal_evolution(
    state: WorldState,
    victim: Npc,
    *,
    death_event_id: int,
    killer_id: str | None,
) -> list[str]:
    """Apply the documented death transitions and return changed goal ids.

    Idempotent: re-applying the same death event neither duplicates a revenge
    goal nor re-marks an already resolved goal.
    """
    if victim.alive:
        return []

    changed: list[str] = []

    # Active defeat_rival goals that targeted the victim are now achieved.
    for npc_key in sorted(state.npcs):
        npc = state.npcs[npc_key]
        if npc.npc_id == victim.npc_id:
            continue
        for goal in npc.goals:
            if (
                goal.kind == "defeat_rival"
                and goal.status == "active"
                and goal_target_id(goal) == victim.npc_id
            ):
                goal.status = "achieved"
                if goal.origin_event_id is None:
                    goal.origin_event_id = death_event_id
                goal.last_updated_tick = state.tick
                changed.append(goal.goal_id)

    if killer_id is None or killer_id == victim.npc_id:
        return changed
    if killer_id not in state.npcs:
        return changed

    # Strongly related survivors swear revenge on the recorded killer.
    for npc_key in sorted(state.npcs):
        npc = state.npcs[npc_key]
        if not npc.alive or npc.npc_id in {victim.npc_id, killer_id}:
            continue
        relationship = state.relationships.get(
            relationship_key(npc.npc_id, victim.npc_id)
        )
        if relationship is None:
            continue
        if (
            relationship.affinity < STRONG_RELATIONSHIP_THRESHOLD
            and relationship.respect < STRONG_RELATIONSHIP_THRESHOLD
        ):
            continue
        goal_id = revenge_goal_id(npc.npc_id, victim.npc_id, killer_id, death_event_id)
        if _has_revenge_against(npc, killer_id, goal_id):
            continue
        goal = Goal(
            goal_id=goal_id,
            kind="revenge",
            priority=REVENGE_PRIORITY,
            params={
                "target_id": killer_id,
                "victim_id": victim.npc_id,
                "origin_event_id": death_event_id,
            },
            created_tick=state.tick,
            origin_event_id=death_event_id,
            last_updated_tick=state.tick,
        )
        npc.goals.append(goal)
        changed.append(goal.goal_id)

    return changed


def apply_breakthrough_goal_progress(
    npc: Npc, *, event_id: int, tick: int
) -> list[str]:
    """Mark matching active breakthrough goals achieved; return their ids."""
    achieved: list[str] = []
    for goal in npc.goals:
        if goal.kind != "breakthrough" or goal.status != "active":
            continue
        target_realm = goal.params.get("target_realm", 0)
        if not isinstance(target_realm, int):
            continue
        if target_realm <= npc.realm:
            goal.status = "achieved"
            if goal.origin_event_id is None:
                goal.origin_event_id = event_id
            goal.last_updated_tick = tick
            achieved.append(goal.goal_id)
    return achieved


def expire_obsolete_goals(state: WorldState) -> list[str]:
    """Apply the documented expiry rules and return changed goal ids.

    Only active goals owned by living NPCs are considered. A non-revenge goal
    whose target NPC is dead is abandoned; a revenge goal becomes achieved when
    its target dies. Goals without a target id are never expired here.
    """
    changed: list[str] = []
    for npc_key in sorted(state.npcs):
        npc = state.npcs[npc_key]
        if not npc.alive:
            continue
        for goal in npc.goals:
            if goal.status != "active":
                continue
            target_id = goal_target_id(goal)
            if target_id is None:
                continue
            target = state.npcs.get(target_id)
            if target is None or target.alive:
                continue
            if goal.kind == "revenge":
                goal.status = "achieved"
            else:
                goal.status = "abandoned"
            goal.last_updated_tick = state.tick
            changed.append(goal.goal_id)
    return changed