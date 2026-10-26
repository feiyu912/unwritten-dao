# Unwritten Dao

A deterministic xianxia world simulation where persistent NPCs pursue goals, form beliefs,
and change a canonical storyline through validated actions. The simulator owns truth; language
models only propose actions.

**Status:** R1 complete; R2 headless agent stack complete (LLM proposal pipeline, episodic
memory, dialogue, audit/replay); R3 playable headless demo available. The UE5 client is an
unvalidated scaffold; 3D/FPS work awaits a machine with Unreal. See
[`docs/status.md`](docs/status.md) for the evidence table and remaining gaps.

## Architecture in one paragraph

`world_core` is a pure, deterministic tick-based simulator with typed commands and an
append-only event log. `agent_runtime` turns observations into validated action proposals
(utility AI now, LLM later). `world_server` persists events/snapshots in PostgreSQL and exposes
HTTP/WebSocket APIs. A UE5 client renders the authoritative state; it never simulates it.

## Quickstart

```bash
uv sync --all-packages
uv run pytest packages services tests clients/unreal/tools -m "not integration and not slow"
uv run python -m tools.bench_sim --npcs 30 --years 20 --seed 42
uv run python -m tools.demo_causal --days 400     # baseline vs stolen-map timeline
uv run python -m tools.play                        # playable headless MVP
uv run uvicorn world_server.app:app --port 8000    # HTTP/WS server (needs PostgreSQL)
```

PostgreSQL integration tests (optional locally):

```bash
docker compose up -d postgres
uv run alembic -c services/world_server/alembic.ini upgrade head
uv run pytest -m integration
```

## Repository layout

```text
docs/contracts/        versioned JSON Schemas + ruleset + OpenAPI
packages/world_core/   authoritative simulation
packages/agent_runtime/observation -> action proposal policies
services/world_server/ FastAPI + persistence
clients/unreal/        UE5 client (interface scaffold)
tests/                 contract, determinism, invariance, causal E2E
tools/                 benchmarks and replay CLIs
```