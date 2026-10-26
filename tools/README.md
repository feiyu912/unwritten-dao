# Development tools

Small CLIs around the deterministic simulator and the local database. They code against the
frozen API in [`docs/design/world-core-api.md`](../docs/design/world-core-api.md); the
benchmarks will not run until `packages/world_core` is merged.

## Prerequisites

```bash
uv sync --all-packages
```

## Benchmarks

Simulate 30 NPCs for 20 in-world years (7,300 ticks), cultivating for the first 365 days:

```bash
uv run python -m tools.bench_sim --npcs 30 --years 20 --seed 42 --agent-mode rules
```

It prints per-chunk `elapsed`, `ticks/s`, NPC/alive counts, cumulative event count, and the
state checksum. The final state is checked with `validate_state` plus explicit invariants
(no actions on dead NPCs, one owner per unique item, tick target, event-id accounting). Any
violation exits non-zero.

`--agent-mode replay` exits with an explanatory error until `agent_runtime` lands. It is not
emulated.

Replay a recorded command stream ten times and compare outcomes:

```bash
uv run python -m tools.bench_replay --runs 10 --seed 42 --commands path/to/commands.jsonl
```

Every non-blank JSONL line must be a complete `world-command.v1` object produced from a fresh
world with the same seed (the stream carries `issued_tick` and `expected_state_version`). The
command exits non-zero if a command is rejected, state validation fails, or checksums/event
counts differ between runs.

## Inspect a command stream

```bash
uv run python -m tools.replay path/to/commands.jsonl
uv run python -m tools.replay path/to/commands.jsonl --show 3 --json
```

Validates each line against `docs/contracts/world-command.v1.schema.json` and prints command
counts by type/source, world ID, and tick range. Read-only.

## Assumed `world_core` surface

Until the real package is merged these tools import:

- `create_world(seed=...)`, `make_command(...)`, `apply_command(state, command)`,
  `advance_time(state, ticks, source=...)`, `state_checksum(state)`, `validate_state(state)`;
- `world_core.models.WorldCommand.model_validate(doc)` for JSONL commands;
- `CommandResult.accepted` / `.events`, and `Npc.alive` / `.active_action`, `WorldState.tick` /
  `.npcs` / `.items` / `.last_event_id`.

## Database

```bash
cp .env.example .env      # optional; compose already has safe local defaults
make db-up                # docker compose up -d postgres (pgvector/pgvector:pg17)
make db-down
```

The container listens on `POSTGRES_PORT` (default 5432) and persists data in the
`unwritten-dao-postgres-data` volume. The test database used by CI
(`unwritten_dao_test`) is created by the CI service container, not by compose.

## CI

`.github/workflows/ci.yml` runs the fast suite on macOS 14 (ARM64) and Ubuntu 24.04 (x86_64);
job names and the run summary label each result by OS/arch so cross-platform checksum drift is
visible. The Ubuntu-only `integration` job starts a health-checked
`pgvector/pgvector:pg17` service and runs `pytest -m integration`. Until the first integration
test is merged, pytest exits 5 (no tests collected); the command is deliberately not masked
with `|| true`.