from __future__ import annotations

from agent_runtime.memory import InMemoryEpisodeStore, MemoryEpisode, score_memory, tokens


def _episode(
    memory_id: int,
    summary: str,
    *,
    npc_id: str = "npc-a",
    importance: float = 0.5,
    created_tick: int = 0,
    source_event_id: int = 100,
    related: tuple[str, ...] = (),
) -> MemoryEpisode:
    return MemoryEpisode(
        memory_id=memory_id,
        npc_id=npc_id,
        source_event_id=source_event_id,
        summary=summary,
        importance=importance,
        emotional_valence=0.0,
        created_tick=created_tick,
        related_npc_ids=related,
    )


def test_tokens_handles_cjk_bigrams_and_ascii_words() -> None:
    result = tokens("韩立与Wang在青云宗交易 foundation_pill")
    assert "foundation_pill" in result
    assert "韩立" in result
    assert "青云" in result


def test_retrieval_scores_semantic_relevance() -> None:
    store = InMemoryEpisodeStore(
        [
            _episode(1, "在洞府中找到了筑基丹"),
            _episode(2, "在集市买了一把短刀"),
        ]
    )
    hits = store.retrieve(npc_id="npc-a", now_tick=10, query="筑基丹", top_k=2)
    assert [hit.memory_id for hit in hits] == [1, 2]


def test_retrieval_prefers_recent_important_and_related() -> None:
    store = InMemoryEpisodeStore(
        [
            _episode(1, "无关旧事", importance=0.1, created_tick=0),
            _episode(2, "无关新事", importance=0.1, created_tick=990),
            _episode(3, "重要之事", importance=1.0, created_tick=500),
            _episode(4, "与某人相关", importance=0.2, created_tick=500, related=("npc-b",)),
        ]
    )
    hits = store.retrieve(
        npc_id="npc-a",
        now_tick=1000,
        person_ids=["npc-b"],
        causal_event_ids=[100],
        top_k=4,
    )
    ids = [hit.memory_id for hit in hits]
    assert ids[0] == 3
    assert 1 not in ids[:2]


def test_retrieval_filters_by_npc_and_top_k() -> None:
    store = InMemoryEpisodeStore(
        [
            _episode(1, "a", npc_id="npc-a"),
            _episode(2, "b", npc_id="npc-b"),
            _episode(3, "c", npc_id="npc-a"),
        ]
    )
    hits = store.retrieve(npc_id="npc-a", now_tick=0, top_k=1)
    assert len(hits) == 1
    assert hits[0].npc_id == "npc-a"


def test_scores_are_deterministic_with_stable_ties() -> None:
    store = InMemoryEpisodeStore([_episode(2, "same"), _episode(1, "same")])
    first = store.retrieve(npc_id="npc-a", now_tick=0, top_k=2)
    second = store.retrieve(npc_id="npc-a", now_tick=0, top_k=2)
    assert [item.memory_id for item in first] == [1, 2]
    assert first == second


def test_causal_bonus_changes_ranking() -> None:
    episode = _episode(1, "neutral", importance=0.0, created_tick=0)
    without = score_memory(
        episode,
        now_tick=0,
        query_tokens=set(),
        person_ids=(),
        causal_event_ids=(),
    )
    with_causal = score_memory(
        episode,
        now_tick=0,
        query_tokens=set(),
        person_ids=(),
        causal_event_ids=(100,),
    )
    assert with_causal > without
