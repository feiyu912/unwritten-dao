from __future__ import annotations

import pytest
from sqlalchemy import func, select
from tools.bench_memory import BENCH_NPC, query_latencies, seed_episodes
from world_server.models import MemoryEpisodeRow

from agent_runtime import HashingEmbeddingProvider

pytestmark = pytest.mark.integration


def test_memory_benchmark_smoke(session) -> None:
    provider = HashingEmbeddingProvider(dim=768)
    seed_episodes(session, count=50, batch_size=10, provider=provider)
    rows = session.execute(
        select(func.count())
        .select_from(MemoryEpisodeRow)
        .where(MemoryEpisodeRow.npc_id == BENCH_NPC)
    ).scalar_one()
    assert rows == 50

    latencies, hits = query_latencies(session, queries=5, top_k=3, provider=provider)
    assert len(latencies) == 5
    assert hits == 15
    assert max(latencies) >= 0
