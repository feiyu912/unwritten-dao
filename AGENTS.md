# Agent rules

Project: an emergent-narrative xianxia RPG MVP. Python 3.12 headless simulation, PostgreSQL
persistence, UE5 client. Only the MVP is in scope.

## Non-negotiable invariants

1. The simulator is the sole source of world truth. LLM output is an `ActionProposal` and
   nothing else; it can never write state directly.
2. Every authoritative mutation flows through `world_core.apply_command(state, command)`.
   Meaningful state changes emit events; no-op bookkeeping (e.g. waiting) may emit none.
3. Simulation is deterministic: integer ticks, stable hashing, seeded RNG, explicit ordering.
   Same seed + same command stream = same state checksum on macOS and Linux.
4. Dead NPCs never act, no unique item has two owners, and state transitions are atomic.
5. Contracts under `docs/contracts/` are the only source of truth for cross-module shapes.
   Change them only with a version bump and an RFC-style PR.

## Module boundaries

| Owner | Write scope |
|---|---|
| A world/rules | `packages/world_core/` |
| B persistence/API | `services/world_server/`, `migrations/` |
| C agents | `packages/agent_runtime/` |
| D UE5 client | `clients/unreal/` |
| E tests/integration | `tests/`, `tools/`, `.github/` |

Do not edit another owner's directory without an explicit request. Contract changes require
approval and touch `docs/contracts/` only.

## Workflow

- Package manager: `uv` (workspace). Use `uv sync --all-packages` once, then `uv run ...`.
- Tests: `uv run pytest`. Contract checks: `uv run pytest tests/contract`. Fast unit subset:
  `uv run pytest -m "not integration and not slow"`.
- Lint/type: `uv run ruff check .`, `uv run mypy`.
- Any change that touches world state must be covered by a deterministic replay test.
- Do not commit `.env`, credentials, local databases, or generated assets. This repository is
  public: no employer names, internal hostnames, or private environment details.
- Never report work as complete without running the relevant tests and pasting the result.
- Do not replace failing business tests with weaker expectations.