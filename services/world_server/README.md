# World server

FastAPI + PostgreSQL (17, pgvector) persistence for the authoritative world. All rules live in
`world_core`; this service only stores state, events, commands, snapshots, and serves the
versioned HTTP/WS contract in `docs/contracts/api.openapi.yaml`.

## Run locally

```bash
docker compose up -d postgres      # reads .env (POSTGRES_PORT, credentials)
# Copy .env.example to .env first if you have not already (keep an existing file).
uv run --env-file .env alembic -c services/world_server/alembic.ini upgrade head
uv run uvicorn --env-file .env world_server.app:app --host 127.0.0.1 --port 8000
```

If you intentionally run without `.env`, omit `--env-file .env` from the last two commands
and export `DATABASE_URL` (or use the `127.0.0.1:5432` default). `uvicorn --env-file` only
loads the file for that server process; Alembic and DB-backed tools need `uv run --env-file .env`.
On Windows, `tools/start_world_server.ps1` loads `.env` for the server but requires the file.

The app bootstraps the `seed=42` world on startup if the database is empty.

## Tests (real PostgreSQL required)

```bash
docker compose up -d postgres
uv run --env-file .env alembic -c services/world_server/alembic.ini upgrade head
uv run --env-file .env pytest services/world_server/tests -m integration -q
```

If there is no `.env`, omit `--env-file .env` and export the same environment variables.

CI runs the same suite against an ephemeral pgvector service container. Do not substitute
SQLite; JSONB semantics and `CREATE EXTENSION vector` are part of the schema contract.

## Agent and embedding modes

| Env | Values | Meaning |
|---|---|---|
| `AGENT_PROVIDER` | `utility` (default), `llm-mock`, `openai`, `openai-compatible`, `replay`, `decision-model` | decision policy for the six major roles; `decision-model` stores candidate/mask samples |
| `DIALOGUE_PROVIDER` | `utility`, `llm-mock`, `openai`, `openai-compatible`, empty (default) | dialogue-only override; empty falls back to `AGENT_PROVIDER`; other values use deterministic text; it does not change background decisions |
| `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` | — | required for `openai`/`openai-compatible`; decisions and dialogue share these values, so two model paths use one endpoint/model, not two independent remote models |
| `EMBEDDING_PROVIDER` | `off` (default), `hash`, `openai` | memory vector indexing; `hash` is for offline plumbing tests |
| `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_API_KEY` | — | required for `openai` embeddings (dimension must be 768; base URL/key may fall back to `LLM_*`) |

Embedding failures are logged and the memory row is stored without a vector; the world command
transaction never fails because of an index error.

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

- `/v1/dialogue` resolves `DIALOGUE_PROVIDER` first, then falls back to `AGENT_PROVIDER`.
  `openai`/`openai-compatible` uses the shared `LLM_*` endpoint and may return an
  `ActionProposal`; that proposal is only a suggestion and must be submitted through
  `/v1/commands`, where normal validation applies. Other modes use a deterministic
  in-character line.
- Speech (ASR/TTS) and real remote-model quality/latency remain unaccepted; current tests
  use local stubs and synthetic audio, with no default cloud endpoint or model.
- Committed events write `memory_episode` rows and observations retrieve the top-5 ranked
  episodes. Embeddings remain null by default; retrieval is deterministic lexical scoring
  until an embedding provider is configured.
- Single-world, single-process; no auth.
