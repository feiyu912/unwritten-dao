from __future__ import annotations

from agent_runtime import InMemoryEpisodeStore, MemoryEpisode
from tools.character_history import find_npc, simulate
from world_server.memory_store import memory_candidates

QUERIES = [
    ("残破洞府图", "残破洞府图"),
    ("古修洞府", "古修洞府"),
    ("筑基丹", "筑基丹"),
    ("突破", "breakthrough"),
    ("迷雾谷", "迷雾谷"),
    ("洞府丹藏", "洞府丹藏"),
    ("item", "item"),
    ("investigated", "investigated"),
]


def _episodes(state, events, npc_id: str) -> list[MemoryEpisode]:
    episodes: list[MemoryEpisode] = []
    memory_id = 0
    for event in events:
        for candidate_npc, summary, importance, valence in memory_candidates(state, event):
            if candidate_npc != npc_id:
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


def test_recall_at_five_on_a_real_simulated_life() -> None:
    state, events = simulate(years=1, seed=42)
    protagonist = find_npc(state, "protagonist")
    assert protagonist is not None
    episodes = _episodes(state, events, protagonist.npc_id)
    assert episodes
    store = InMemoryEpisodeStore(episodes)

    hits = 0
    for query, expected in QUERIES:
        recalled = store.retrieve(
            npc_id=protagonist.npc_id,
            now_tick=state.tick,
            query=query,
            top_k=5,
        )
        if any(expected in episode.summary for episode in recalled):
            hits += 1
    recall = hits / len(QUERIES)
    assert recall >= 0.9, f"Recall@5={recall:.2f}"
