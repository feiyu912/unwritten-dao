from __future__ import annotations

from world_core.events import WorldEvent

from agent_runtime import find_story_threads

WORLD = "11111111-1111-4111-8111-111111111111"
ACTOR = "22222222-2222-4222-8222-222222222222"


def _event(event_id: int, event_type: str, parent: int | None = None) -> WorldEvent:
    return WorldEvent(
        event_id=event_id,
        world_id=WORLD,
        tick=event_id,
        type=event_type,  # type: ignore[arg-type]
        actor_ids=[ACTOR],
        causal_parent_ids=[parent] if parent is not None else [],
        rng_seed=0,
        state_version_after=event_id,
    )


def test_story_threads_backtrack_the_whole_chain() -> None:
    events = [
        _event(1, "ITEM_TRANSFERRED"),
        _event(2, "LOCATION_INVESTIGATED", 1),
        _event(3, "SECRET_REALM_DISCOVERED", 2),
        _event(4, "OPPORTUNITY_CLAIMED", 3),
        _event(5, "BREAKTHROUGH_ATTEMPT", 4),
        _event(6, "NPC_DIED"),
    ]
    threads = find_story_threads(events)
    assert threads
    assert threads[0].event_ids == (1, 2, 3, 4, 5)
    assert "ITEM_TRANSFERRED" in threads[0].headline
    assert "BREAKTHROUGH_ATTEMPT" in threads[0].headline
    assert all(event_id in {1, 2, 3, 4, 5} for event_id in threads[0].event_ids)


def test_isolated_events_do_not_become_threads() -> None:
    events = [_event(1, "NPC_DIED"), _event(2, "BREAKTHROUGH_ATTEMPT")]
    assert find_story_threads(events) == []


def test_thread_detection_is_deterministic_and_bounded() -> None:
    events = [
        _event(1, "ITEM_TRANSFERRED"),
        _event(2, "LOCATION_INVESTIGATED", 1),
        _event(3, "SECRET_REALM_DISCOVERED", 2),
        _event(4, "OPPORTUNITY_CLAIMED", 3),
        _event(5, "BREAKTHROUGH_ATTEMPT", 4),
    ]
    first = find_story_threads(events, max_threads=2)
    second = find_story_threads(events, max_threads=2)
    assert first == second
    assert len(first) <= 2
