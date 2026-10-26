from __future__ import annotations

from agent_runtime import InMemoryEpisodeStore, MemoryEpisode

NPC = "npc-recall"

EPISODES = [
    MemoryEpisode(1, NPC, 101, "在破庙取得残破洞府图", 0.5, 0.2, 0),
    MemoryEpisode(2, NPC, 102, "在迷雾谷发现无名古修洞府", 0.5, 0.5, 0),
    MemoryEpisode(3, NPC, 103, "在洞府中取得筑基丹", 0.5, 0.6, 0),
    MemoryEpisode(4, NPC, 104, "苏芷长老拒绝借出灵石", 0.5, -0.3, 0),
    MemoryEpisode(5, NPC, 105, "裴烈在演武场挑战沈砚", 0.5, -0.4, 0),
    MemoryEpisode(6, NPC, 106, "黑石集市出售聚气丹", 0.5, 0.1, 0),
    MemoryEpisode(7, NPC, 107, "宗门 treasury 因旱灾下降", 0.5, -0.2, 0),
    MemoryEpisode(8, NPC, 108, "在落鸦林遭遇赤霄门巡逻", 0.5, -0.5, 0),
    MemoryEpisode(9, NPC, 109, "陆玄机宗主召见内门弟子", 0.5, 0.1, 0),
    MemoryEpisode(10, NPC, 110, "突破筑基失败导致气血受损", 0.5, -0.6, 0),
    MemoryEpisode(11, NPC, 111, "青石镇客栈听到秘境传闻", 0.5, 0.2, 0),
    MemoryEpisode(12, NPC, 112, "筑基丹在黑市被高价拍卖", 0.5, 0.3, 0),
]

LABELED_QUERIES = [
    ("残破洞府图", 1),
    ("古修洞府", 2),
    ("筑基丹", 3),
    ("苏芷 灵石", 4),
    ("裴烈 演武场", 5),
    ("黑石集市 聚气丹", 6),
    ("旱灾 宗门", 7),
    ("赤霄门 巡逻", 8),
    ("宗主 召见", 9),
    ("突破 失败 气血", 10),
]


def test_recall_at_five_meets_mvp_threshold() -> None:
    store = InMemoryEpisodeStore(EPISODES)
    hits = 0
    for query, expected_id in LABELED_QUERIES:
        recalled = store.retrieve(npc_id=NPC, now_tick=0, query=query, top_k=5)
        if expected_id in [episode.memory_id for episode in recalled]:
            hits += 1
    recall = hits / len(LABELED_QUERIES)
    assert recall >= 0.9, f"Recall@5={recall:.2f} ({hits}/{len(LABELED_QUERIES)})"


def test_recall_never_crosses_npcs() -> None:
    store = InMemoryEpisodeStore(
        [
            *EPISODES,
            MemoryEpisode(99, "npc-other", 999, "筑基丹在别人手里", 1.0, 0.0, 0),
        ]
    )
    hits = store.retrieve(npc_id=NPC, now_tick=0, query="筑基丹", top_k=5)
    assert all(episode.npc_id == NPC for episode in hits)
    assert 99 not in [episode.memory_id for episode in hits]
