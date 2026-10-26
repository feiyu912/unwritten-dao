from __future__ import annotations

from tools.character_history import character_timeline, find_npc, simulate


def test_protagonist_life_timeline_contains_the_key_chain() -> None:
    state, events = simulate(years=1, seed=42)
    protagonist = find_npc(state, "protagonist")
    assert protagonist is not None
    timeline = "\n".join(character_timeline(state, events, protagonist.npc_id))

    assert "ITEM_TRANSFERRED" in timeline
    assert "SECRET_REALM_DISCOVERED" in timeline
    assert "BREAKTHROUGH_ATTEMPT" in timeline
    assert "CULTIVATION_STARTED" not in timeline
    assert protagonist.alive is True
