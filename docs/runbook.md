# Runbook

## 1. Local setup (macOS or Linux)

Prerequisites: `uv`, Docker (with Compose), Python 3.12 via uv.

```bash
uv sync --all-packages
docker compose up -d postgres
export DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/unwritten_dao
uv run alembic -c services/world_server/alembic.ini upgrade head
```

If host port 5432 is already used by another project, create a gitignored `.env`:

```dotenv
POSTGRES_PORT=5433
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/unwritten_dao
```

If the Docker volume predates the current `POSTGRES_PASSWORD`, the password in the volume wins.
Align it inside the container (`ALTER USER postgres PASSWORD 'postgres';`) or recreate the
volume if the data is disposable.

## 2. Verify the simulation

```bash
uv run pytest packages services tests clients/unreal/tools -m "not integration and not slow"
uv run pytest services/world_server/tests -q          # requires PostgreSQL
uv run pytest -m slow -q                              # 100k-event invariant run

uv run python -m tools.bench_sim --npcs 30 --years 20 --seed 42
uv run python -m tools.bench_db --reset --years 20    # persisted; truncates local tables
uv run python -m tools.report_history --days 400
uv run python -m tools.demo_causal --days 400
uv run python -m tools.play
```

The cross-platform determinism gate is `tests/e2e/test_determinism_golden.py`: the 20-year
yearly-cultivation history must hash to the recorded golden on both macOS ARM64 and Linux
x86_64. If a rule change is intentional, update the golden in the same PR and say why.

## 2b. Seed a 20-year agent history (optional, destructive)

```bash
uv run python -m tools.seed_history --years 20 --reset
```

This truncates the local tables, simulates 30 NPCs for 7,300 days with the deterministic
policies, and persists the state/events/memories in one transaction (~4 s, ~19 MB). The server
then boots at tick 7300 with a full history.

## 3. Run the server

```bash
uv run uvicorn world_server.app:app --host 127.0.0.1 --port 8000
```

Modes (environment):

| Variable | Values | Notes |
|---|---|---|
| `AGENT_PROVIDER` | `utility`, `llm-mock`, `openai`, `replay` | only the six major roles use the LLM path |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | — | for `openai` (cloud or local llama.cpp `/v1`) |
| `EMBEDDING_PROVIDER` | `off`, `hash`, `openai` | `hash` is deterministic plumbing-only |
| `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY` | — | 768-dim required |

Smoke:

```bash
curl -s localhost:8000/v1/health
curl -s localhost:8000/v1/world/snapshot | head -c 300
```

## 4. GPU workstation checklist (R3)

1. Clone the repo, run sections 1–2, confirm the golden test passes on Linux x86_64.
2. Start a local model server (llama.cpp or vLLM) exposing an OpenAI-compatible `/v1`.
3. Run the world server with `AGENT_PROVIDER=openai` and `EMBEDDING_PROVIDER=openai`.
   Record TTFT, tokens/s, and p95 dialogue latency; keep the request/response fixtures.
4. Open `clients/unreal/UnwrittenDao.uproject` with UE 5.6, compile, create the UMG assets,
   and point the client at the server.
5. Measure 1080p FPS and 1% low with the game alone and with the model running.
6. Record results in `docs/status.md`; if a target is missed, state the measured number.

## 5. Troubleshooting

- `StaleStateVersion` in scripts: build each command from a freshly loaded state; commands carry
  the state version at creation time.
- `password authentication failed`: the Docker volume keeps the password from its first init.
- `ModuleNotFoundError: tools`: run from the repo root or via `uv run python -m tools.<name>`.
- CI fast job must exclude integration tests; they are marked at module level in
  `services/world_server/tests/`.