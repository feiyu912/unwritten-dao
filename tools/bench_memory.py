#!/usr/bin/env python3
"""Benchmark pgvector memory retrieval (HNSW + cosine).

    uv run python -m tools.bench_memory --events 100000 --queries 1000 --top-k 5

Uses deterministic hash embeddings, so it measures the storage/query path,
not semantic quality. Synthetic rows are removed by default.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
import uuid

from sqlalchemy import delete, select, text
from world_server.db import get_engine, get_session_factory
from world_server.models import MemoryEpisodeRow

from agent_runtime import HashingEmbeddingProvider

BENCH_NPC = uuid.uuid5(uuid.NAMESPACE_URL, "unwritten-dao/bench-memory")
DIM = 768


def seed_episodes(
    session,
    *,
    count: int,
    batch_size: int = 1000,
    provider: HashingEmbeddingProvider,
    npc_id: uuid.UUID = BENCH_NPC,
) -> float:
    started = time.perf_counter()
    for start in range(0, count, batch_size):
        stop = min(count, start + batch_size)
        texts = [f"bench memory {index} token {index % 97}" for index in range(start, stop)]
        vectors = provider.embed_many(texts)
        session.add_all(
            [
                MemoryEpisodeRow(
                    npc_id=npc_id,
                    source_event_id=index + 1,
                    summary=texts[offset],
                    importance=(index % 100) / 100,
                    emotional_valence=0.0,
                    created_tick=index,
                    embedding=vector,
                )
                for offset, (index, vector) in enumerate(
                    zip(range(start, stop), vectors, strict=True)
                )
            ]
        )
        session.commit()
    return time.perf_counter() - started


def query_latencies(
    session,
    *,
    queries: int,
    top_k: int,
    provider: HashingEmbeddingProvider,
    npc_id: uuid.UUID = BENCH_NPC,
) -> tuple[list[float], int]:
    texts = [f"token {index % 97}" for index in range(queries)]
    vectors = provider.embed_many(texts)
    latencies: list[float] = []
    hits = 0
    for vector in vectors:
        started = time.perf_counter()
        rows = (
            session.execute(
                select(MemoryEpisodeRow)
                .where(
                    MemoryEpisodeRow.npc_id == npc_id,
                    MemoryEpisodeRow.embedding.isnot(None),
                )
                .order_by(MemoryEpisodeRow.embedding.cosine_distance(vector))
                .limit(top_k)
            )
            .scalars()
            .all()
        )
        latencies.append((time.perf_counter() - started) * 1000)
        hits += len(rows)
    return latencies, hits


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return ordered[index]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark pgvector memory retrieval.")
    parser.add_argument("--events", type=int, default=100_000)
    parser.add_argument("--queries", type=int, default=1_000)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--keep", action="store_true", help="leave synthetic rows in the database")
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="drop the HNSW index before inserts and rebuild it afterwards",
    )
    args = parser.parse_args(argv)

    factory = get_session_factory(get_engine())
    session = factory()
    provider = HashingEmbeddingProvider(dim=DIM)
    try:
        session.execute(delete(MemoryEpisodeRow).where(MemoryEpisodeRow.npc_id == BENCH_NPC))
        session.commit()
        if args.rebuild_index:
            session.execute(text("DROP INDEX IF EXISTS ix_memory_episode_embedding"))
            session.commit()
        else:
            session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_memory_episode_embedding "
                    "ON memory_episode USING hnsw (embedding vector_cosine_ops) "
                    "WHERE embedding IS NOT NULL"
                )
            )
            session.commit()

        insert_seconds = seed_episodes(
            session,
            count=args.events,
            batch_size=args.batch_size,
            provider=provider,
        )
        index_seconds = 0.0
        if args.rebuild_index:
            started = time.perf_counter()
            session.execute(
                text(
                    "CREATE INDEX ix_memory_episode_embedding "
                    "ON memory_episode USING hnsw (embedding vector_cosine_ops) "
                    "WHERE embedding IS NOT NULL"
                )
            )
            session.commit()
            index_seconds = time.perf_counter() - started

        latencies, hits = query_latencies(
            session,
            queries=args.queries,
            top_k=args.top_k,
            provider=provider,
        )
        rows = (
            session.execute(select(MemoryEpisodeRow).where(MemoryEpisodeRow.npc_id == BENCH_NPC))
            .scalars()
            .all()
        )
        print(f"events={args.events} queries={args.queries} top_k={args.top_k} rows={len(rows)}")
        print(
            f"insert={insert_seconds:.2f}s ({args.events / insert_seconds:,.0f} rows/s) "
            f"index_build={index_seconds:.2f}s hits={hits}"
        )
        print(
            f"latency_ms p50={statistics.median(latencies):.2f} "
            f"p95={_p95(latencies):.2f} max={max(latencies):.2f}"
        )
        return 0 if len(rows) == args.events else 1
    finally:
        if not args.keep:
            session.execute(delete(MemoryEpisodeRow).where(MemoryEpisodeRow.npc_id == BENCH_NPC))
            session.commit()
        session.close()


if __name__ == "__main__":
    sys.exit(main())
