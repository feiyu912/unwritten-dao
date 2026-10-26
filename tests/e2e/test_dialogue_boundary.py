from __future__ import annotations

from world_server.dialogue import build_dialogue_prompt

from world_core import PROTAGONIST_ID, create_world


def test_dialogue_prompt_does_not_leak_hidden_world_truth() -> None:
    state = create_world(42)
    npc = state.npcs[PROTAGONIST_ID]
    player = state.npcs[state.player_id]
    prompt = build_dialogue_prompt(state, npc, player, "道友可知道什么机缘？")
    assert "item_foundation_pill" not in prompt
    assert "location_ancient_cave" not in prompt
    assert "WORLD_FACTS" in prompt
