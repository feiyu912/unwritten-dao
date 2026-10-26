# World server

FastAPI + PostgreSQL (17, pgvector) persistence for the authoritative world. All rules live in
`world_core`; this service only stores state, events, commands, snapshots, and serves the
versioned HTTP/WS contract in `docs/contracts/api.openapi.yaml`.

## Run locally

```bash
docker compose up -d postgres      # reads .env (POSTGRES_PORT, credentials)
export DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/unwritten_dao
uv run alembic -c services/world_server/alembic.ini upgrade head
uv run uvicorn world_server.app:app --port 8000
```

The app bootstraps the `seed=42` world on startup if the database is empty.

## Tests (real PostgreSQL required)

```bash
docker compose up -d postgres
uv run alembic -c services/world_server/alembic.ini upgrade head
uv run pytest services/world_server/tests -m integration -q
```

CI runs the same suite against an ephemeral pgvector service container. Do not substitute
SQLite; JSONB semantics and `CREATE EXTENSION vector` are part of the schema contract.

## Guarantees

- Every command is applied in one transaction: state row update + event rows + causal edges +
  idempotency log commit together or not at all.
- Replaying an `idempotency_key` returns the stored response without new events, even when the
  command's `expected_state_version` is now stale (idempotency wins over the version check).
- Reusing a `command_id` under a different key is a 409.
- `POST /v1/saves/{id}/load` performs single-player time travel: events, edges, and command
  log entries after the snapshot boundary are removed so replays are checksum-identical.
- The WebSocket stream polls the database every 0.5 s (no in-process pub/sub yet).

## R1 limitations

- `/v1/dialogue` uses the configured provider (`llm-mock` or `openai`) and falls back to a
  deterministic in-character line when no provider is configured or the call fails.
- Committed events write `memory_episode` rows and observations retrieve the top-5 ranked
  episodes. Embeddings remain null; retrieval is deterministic lexical scoring until an
  embedding provider is configured.
- Single-world, single-process; no auth.
