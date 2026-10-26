# world_server implementation contract (R1)

The server exposes authoritative state and persistence. It must not re-implement cultivation,
combat, death, ownership, or discovery rules — every mutation is delegated to
`world_core.apply_command`.

## Scope

Required for R1: bootstrap, snapshot, events, command submission with idempotency and
optimistic concurrency, NPC public state, NPC observation, save/load, causal query, WebSocket
event stream. `POST /v1/agents/{id}/decision` returns a validated proposal from `agent_runtime`
without applying it. `POST /v1/dialogue` may return a deterministic placeholder reply with
`proposal: null`; it is explicitly not LLM-backed until R2.

## Package layout

```text
services/world_server/
  pyproject.toml
  alembic.ini
  README.md
  migrations/env.py
  migrations/versions/0001_initial.py
  src/world_server/
    __init__.py
    app.py            # FastAPI app factory
    config.py         # DATABASE_URL and settings from env
    db.py             # engine/session, dependency
    models.py         # SQLAlchemy tables
    repository.py     # transactional load/apply/persist
    routes.py         # HTTP + WS
    schemas.py        # request/response DTOs where not from world_core
```

## Storage

- `world_state`: one row per world with `state JSONB`, `checksum`, `tick`, `state_version`,
  `last_event_id`, `seed`, `updated_at`. This is the authoritative current row.
- `world_event`: append-only, PK `(world_id, event_id)`, with tick/type/actor_ids/target_ids/
  location_id/rng_seed/command_id/state_version_after/payload/created_at; index on
  `(world_id, tick)` and `(world_id, type)`.
- `event_edge`: `(world_id, parent_event_id, child_event_id, relation)` from
  `causal_parent_ids` with relation `caused_by`.
- `command_log`: `(world_id, idempotency_key)` unique, command_id, state_version_after,
  response JSONB. Duplicate key returns the stored response; reuse of a command_id under a
  different key is a conflict.
- `world_snapshot`: snapshot_id, world_id, tick, last_event_id, state_version, world_seed,
  sim_version, schema_version, state JSONB, checksum, created_at.
- `save`: save_id, world_id, snapshot_id, label, created_at.
- `memory_episode`: contract columns, `embedding VECTOR(768)`, created by the migration with
  `CREATE EXTENSION IF NOT EXISTS vector`. No R1 writes; pgvector must be available so the
  migration and future memory work share one schema.

Use PostgreSQL 17 + pgvector (`docker compose up -d postgres`). Tests may use a separate
database but must run against real PostgreSQL; do not substitute SQLite.

## Command transaction

1. Begin transaction; `SELECT ... FOR UPDATE` the world row.
2. Check `expected_state_version == world.state_version`; otherwise 409 `stale_state_version`.
3. Check idempotency key. Existing → return stored response. Reused command_id with a different
   key → 409.
4. Deserialize `WorldState`, call `world_core.apply_command`. On `CommandRejected` → 422 with
   `{code,message,details}` and roll back.
5. Insert events and causal edges, update the world row with the new state/checksum/version,
   store the command response, commit.
6. Broadcast the new events to WebSocket subscribers after commit.

Never mutate the JSONB state outside this transaction. Never accept a command without an
idempotency key.

## HTTP/WS

Follow `docs/contracts/api.openapi.yaml` exactly for the implemented paths. Add:
- `GET /v1/health` reports DB connectivity and whether a world is loaded.
- `POST /v1/saves`: snapshot the current state, store save row, return ids/checksum.
- `POST /v1/saves/{id}/load`: restore the snapshot state, delete events/edges/command log rows
  after the snapshot boundary (single-player time travel), return the restored snapshot.
- `GET /v1/debug/causality/{event_id}?depth=` performs a bounded BFS over `event_edge` and
  returns root/events/edges.
- `WS /v1/events/stream?after=`: accept, send existing events after the cursor, then pushed
  events; tolerate disconnects. Keep the implementation simple (in-process broadcast).

Bootstrap on startup: if no world exists, create `world_core.create_world(seed=42)` and persist
it. `GET /v1/world/snapshot` loads the current row.

## Agent integration

- `GET /v1/npcs/{id}/observation` calls `agent_runtime.build_observation` with recent events
  from the DB.
- `POST /v1/agents/{id}/decision` calls `agent_runtime.decide_command` and returns the proposal
  shape converted from the command (or a documented fallback proposal). It does not apply it.
- The server never imports an LLM provider in R1.

## Tests

`services/world_server/tests/` with pytest markers `integration`:
- bootstrap creates a valid 30-NPC world; snapshot endpoint matches checksum.
- submit a legal command → 200, events persisted, state_version increments; duplicate key →
  same response, no second event; stale version → 409.
- save at tick 10, advance to tick 20, load, replay the same commands from tick 10 → identical
  checksum.
- causality query for `SECRET_REALM_DISCOVERED` returns the preceding transfer/investigate
  chain.
- event list pagination and event contract shape.
Run:
```bash
docker compose up -d postgres
uv run alembic -c services/world_server/alembic.ini upgrade head
uv run pytest services/world_server/tests -q -m integration
```
Also run `uv run ruff check services/world_server`. Paste actual output. If Docker/network is
unavailable, report it explicitly and do not claim integration success.

## Non-goals

No auth, multiplayer, LLM dialogue, map rendering, or NPC memory embeddings in R1. Keep the
module small and replaceable; the world core remains the sole authority.