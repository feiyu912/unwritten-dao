from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from world_server.models import CommandLogRow, EventEdgeRow, WorldEventRow
from world_server.repository import (
    IdempotencyConflict,
    StaleStateVersion,
    apply_command,
    bootstrap,
    causality,
    list_events,
    load_snapshot,
    load_state,
    save_snapshot,
)

from world_core import (
    ITEM_MAP_FRAGMENT,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    PROTAGONIST_ID,
    CommandRejected,
    WorldCommand,
    make_command,
    state_checksum,
    validate_state,
)

pytestmark = pytest.mark.integration


def test_bootstrap_creates_valid_world_once(session: Session) -> None:
    first = bootstrap(session, seed=42)
    assert len(first.npcs) == 30
    assert state_checksum(first)

    reloaded = load_state(session)
    assert state_checksum(reloaded) == state_checksum(first)

    second = bootstrap(session, seed=42)
    assert state_checksum(second) == state_checksum(first)


def test_apply_command_is_atomic_idempotent_and_versioned(session: Session) -> None:
    state = bootstrap(session, seed=42)
    base_events = session.execute(select(func.count()).select_from(WorldEventRow)).scalar_one()
    command = make_command(
        state,
        PROTAGONIST_ID,
        "move",
        {"to_location_id": LOC_BLACKWOOD_FOREST},
        source="test",
    )
    result = apply_command(session, command)
    assert result.accepted is True
    assert result.state_version == 1
    assert len(result.events) == 1

    event_count = session.execute(select(func.count()).select_from(WorldEventRow)).scalar_one()
    assert event_count == base_events + 1
    log_count = session.execute(select(func.count()).select_from(CommandLogRow)).scalar_one()
    assert log_count == 1

    replayed = apply_command(session, command)
    assert replayed.state_version == result.state_version
    assert replayed.model_dump(mode="json") == result.model_dump(mode="json")
    event_count = session.execute(select(func.count()).select_from(WorldEventRow)).scalar_one()
    assert event_count == base_events + 1

    fresh = load_state(session)
    stale = make_command(
        fresh,
        PROTAGONIST_ID,
        "move",
        {"to_location_id": LOC_RUINED_TEMPLE},
        source="test",
    )
    stale.expected_state_version = 0
    with pytest.raises(StaleStateVersion):
        apply_command(session, stale)


def test_rejected_command_rolls_back_and_keeps_version(session: Session) -> None:
    state = bootstrap(session, seed=42)
    bad = make_command(
        state,
        PROTAGONIST_ID,
        "move",
        {"to_location_id": "location_nowhere"},
        source="test",
    )
    with pytest.raises(CommandRejected):
        apply_command(session, bad)
    reloaded = load_state(session)
    assert reloaded.state_version == 0
    assert reloaded.tick == 0


def test_save_load_resume_is_checksum_identical(session: Session) -> None:
    state = bootstrap(session, seed=42)
    actor = state.npcs[PROTAGONIST_ID]
    path = [LOC_BLACKWOOD_FOREST, LOC_RUINED_TEMPLE, LOC_MISTY_VALLEY]
    for target in path:
        current = load_state(session)
        apply_command(
            session,
            make_command(current, actor.npc_id, "move", {"to_location_id": target}, source="test"),
        )
    save = save_snapshot(session, label="tick0")

    post_save_keys = ["tick:1", "tick:2"]
    for key in post_save_keys:
        current = load_state(session)
        apply_command(
            session,
            make_command(
                current,
                None,
                "advance_time",
                {"ticks": 1},
                idempotency_key=key,
                source="system",
            ),
        )
    checksum_before = state_checksum(load_state(session))

    restored = load_snapshot(session, str(save["save_id"]))
    assert restored["checksum"] == save["checksum"]
    assert state_checksum(load_state(session)) == save["checksum"]

    for key in post_save_keys:
        current = load_state(session)
        apply_command(
            session,
            make_command(
                current,
                None,
                "advance_time",
                {"ticks": 1},
                idempotency_key=key,
                source="system",
            ),
        )
    assert state_checksum(load_state(session)) == checksum_before


def test_causality_links_transfer_investigate_discovery(session: Session) -> None:
    state = bootstrap(session, seed=42)
    actor = state.npcs[PROTAGONIST_ID]
    steps: list[tuple[str, dict[str, object]]] = [
        ("move", {"to_location_id": LOC_BLACKWOOD_FOREST}),
        ("move", {"to_location_id": LOC_RUINED_TEMPLE}),
        (
            "transfer_item",
            {
                "item_id": ITEM_MAP_FRAGMENT,
                "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
                "to": {"kind": "npc", "id": actor.npc_id},
            },
        ),
        ("move", {"to_location_id": LOC_MISTY_VALLEY}),
        (
            "investigate",
            {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
        ),
    ]
    for intent, arguments in steps:
        current = load_state(session)
        apply_command(
            session,
            make_command(current, actor.npc_id, intent, arguments, source="test"),  # type: ignore[arg-type]
        )

    discovery = [
        event
        for event in list_events(session, event_type="SECRET_REALM_DISCOVERED")
        if event.actor_ids == [actor.npc_id]
    ]
    assert len(discovery) == 1
    chain = causality(session, discovery[0].event_id, depth=6)
    chain_types = [event.type for event in chain.events]
    assert "LOCATION_INVESTIGATED" in chain_types

    earlier = list_events(session, after=0, limit=100)
    earlier_types = [event.type for event in earlier]
    assert earlier_types.index("ITEM_TRANSFERRED") < earlier_types.index("SECRET_REALM_DISCOVERED")

    edge_count = session.execute(select(func.count()).select_from(EventEdgeRow)).scalar_one()
    assert edge_count >= 1


def test_command_id_reuse_under_new_key_conflicts(session: Session) -> None:
    state = bootstrap(session, seed=42)
    command = make_command(
        state, PROTAGONIST_ID, "wait", {"ticks": 1}, idempotency_key="k1", source="test"
    )
    apply_command(session, command)
    fresh = load_state(session)
    conflicting = make_command(
        fresh, PROTAGONIST_ID, "wait", {"ticks": 1}, idempotency_key="k2", source="test"
    )
    conflicting.command_id = command.command_id
    with pytest.raises(IdempotencyConflict):
        apply_command(session, conflicting)


def test_events_become_episodic_memories_without_duplicates(session: Session) -> None:
    from world_server.memory_store import retrieve_memories
    from world_server.models import MemoryEpisodeRow

    state = bootstrap(session, seed=42)
    actor = state.npcs[PROTAGONIST_ID]
    steps: list[tuple[str, dict[str, object]]] = [
        ("move", {"to_location_id": LOC_BLACKWOOD_FOREST}),
        ("move", {"to_location_id": LOC_RUINED_TEMPLE}),
        (
            "transfer_item",
            {
                "item_id": ITEM_MAP_FRAGMENT,
                "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
                "to": {"kind": "npc", "id": actor.npc_id},
            },
        ),
        ("move", {"to_location_id": LOC_MISTY_VALLEY}),
        (
            "investigate",
            {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
        ),
    ]
    last_command = None
    for intent, arguments in steps:
        current = load_state(session)
        last_command = make_command(
            current,
            actor.npc_id,
            intent,
            arguments,
            source="test",  # type: ignore[arg-type]
        )
        apply_command(session, last_command)

    rows = (
        session.execute(
            select(MemoryEpisodeRow).where(MemoryEpisodeRow.npc_id == uuid.UUID(actor.npc_id))
        )
        .scalars()
        .all()
    )
    assert rows
    discovery = [row for row in rows if "secret realm" in row.summary]
    assert discovery and discovery[0].importance >= 0.9
    assert any("残破洞府图" in row.summary for row in rows)

    memory_count = len(rows)
    assert last_command is not None
    apply_command(session, last_command)  # idempotent replay
    replayed = session.execute(select(func.count()).select_from(MemoryEpisodeRow)).scalar_one()
    assert replayed == memory_count

    current = load_state(session)
    recalled = retrieve_memories(
        session,
        current,
        actor.npc_id,
        recent_event_ids=[event.event_id for event in list_events(session, limit=100)],
    )
    assert recalled
    assert any("secret realm" in memory["summary"] for memory in recalled)


def test_memories_get_pgvector_embeddings(session: Session, monkeypatch) -> None:
    from world_server.memory_store import retrieve_memories
    from world_server.models import MemoryEpisodeRow

    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    state = bootstrap(session, seed=42)
    actor = state.npcs[PROTAGONIST_ID]
    steps = [
        ("move", {"to_location_id": LOC_BLACKWOOD_FOREST}),
        ("move", {"to_location_id": LOC_RUINED_TEMPLE}),
        (
            "transfer_item",
            {
                "item_id": ITEM_MAP_FRAGMENT,
                "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
                "to": {"kind": "npc", "id": actor.npc_id},
            },
        ),
        ("move", {"to_location_id": LOC_MISTY_VALLEY}),
        ("investigate", {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"}),
    ]
    for intent, arguments in steps:
        current = load_state(session)
        apply_command(
            session,
            make_command(current, actor.npc_id, intent, arguments, source="test"),  # type: ignore[arg-type]
        )

    rows = (
        session.execute(
            select(MemoryEpisodeRow).where(MemoryEpisodeRow.npc_id == uuid.UUID(actor.npc_id))
        )
        .scalars()
        .all()
    )
    embedded = [row for row in rows if row.embedding is not None]
    assert embedded
    assert len(embedded[0].embedding) == 768

    current = load_state(session)
    recalled = retrieve_memories(session, current, actor.npc_id)
    assert recalled


def test_two_sessions_share_state_version_and_idempotency(session: Session) -> None:
    from world_server.db import get_engine, get_session_factory

    state = bootstrap(session, seed=42)
    command = make_command(
        state, PROTAGONIST_ID, "wait", {"ticks": 1}, idempotency_key="race:1", source="test"
    )
    other = make_command(
        state, PROTAGONIST_ID, "wait", {"ticks": 1}, idempotency_key="race:2", source="test"
    )
    factory = get_session_factory(get_engine())
    first = factory()
    second = factory()
    try:
        result = apply_command(first, command)
        replay = apply_command(second, command)
        assert replay.model_dump(mode="json") == result.model_dump(mode="json")

        current = load_state(second)
        stale_command = make_command(
            current,
            PROTAGONIST_ID,
            "wait",
            {"ticks": 1},
            idempotency_key="race:3",
            source="test",
        )
        stale_command.expected_state_version = 0
        with pytest.raises(StaleStateVersion):
            apply_command(second, stale_command)

        assert other.expected_state_version == 0
        with pytest.raises(StaleStateVersion):
            apply_command(second, other)
    finally:
        first.close()
        second.close()


def test_concurrent_commands_allow_exactly_one_writer(session: Session) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from world_server.db import get_engine, get_session_factory

    state = bootstrap(session, seed=42)
    first = make_command(
        state, PROTAGONIST_ID, "wait", {"ticks": 1}, idempotency_key="race-a", source="test"
    )
    second = make_command(
        state, PROTAGONIST_ID, "wait", {"ticks": 1}, idempotency_key="race-b", source="test"
    )
    factory = get_session_factory(get_engine())
    barrier = Barrier(2)

    def worker(command: WorldCommand) -> str:
        db = factory()
        try:
            barrier.wait(timeout=10)
            apply_command(db, command)
            return "ok"
        except StaleStateVersion:
            return "stale"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, first), pool.submit(worker, second)]
        outcomes = sorted(future.result() for future in futures)

    assert outcomes == ["ok", "stale"]
    final = load_state(session)
    assert final.state_version == 1


def test_agent_history_persists_and_reloads(session: Session) -> None:
    from world_server.history import persist_history, simulate_days
    from world_server.models import MemoryEpisodeRow

    state = bootstrap(session, seed=42)
    base_events = session.execute(select(func.count()).select_from(WorldEventRow)).scalar_one()
    events = simulate_days(state, 10)
    persist_history(session, state, events)

    reloaded = load_state(session)
    assert reloaded.tick == 10
    assert state_checksum(reloaded) == state_checksum(state)
    assert validate_state(reloaded) == []
    event_count = session.execute(select(func.count()).select_from(WorldEventRow)).scalar_one()
    assert event_count == base_events + len(events) == state.last_event_id
    memory_count = session.execute(select(func.count()).select_from(MemoryEpisodeRow)).scalar_one()
    assert memory_count > 0


def test_memory_embedding_hnsw_index_exists(session: Session) -> None:
    from sqlalchemy import text

    name = session.execute(
        text("SELECT indexname FROM pg_indexes WHERE indexname = 'ix_memory_episode_embedding'")
    ).scalar_one_or_none()
    assert name == "ix_memory_episode_embedding"
