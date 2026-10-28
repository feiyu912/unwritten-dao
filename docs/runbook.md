# Runbook

## 1. Local setup (macOS or Linux)

Prerequisites: `uv`, Docker (with Compose), Python 3.12 via uv.

```bash
uv sync --all-packages
docker compose up -d postgres
# Without .env, use the default port 5432:
export DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/unwritten_dao
uv run alembic -c services/world_server/alembic.ini upgrade head
```

If host port 5432 is already used by another project, create a gitignored `.env`:

```dotenv
POSTGRES_PORT=5433
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/unwritten_dao
```

Then load it explicitly for Alembic and DB-backed tools; `uvicorn --env-file` does not affect
independent commands:

```bash
docker compose up -d postgres
uv run --env-file .env alembic -c services/world_server/alembic.ini upgrade head
```

If the Docker volume predates the current `POSTGRES_PASSWORD`, the password in the volume wins.
Align it inside the container (`ALTER USER postgres PASSWORD 'postgres';`) or recreate the
volume if the data is disposable.

## 1b. Windows setup (PowerShell)

Prerequisites: `uv` and Docker Desktop with Compose. Run the commands from the repository
root (the folder containing `.env.example`). The private config file is `.env` in that root;
the public template is `.env.example`. `.env` is gitignored — never commit it or real keys.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
uv sync --all-packages
docker compose up -d postgres
uv run --env-file .env alembic -c services/world_server/alembic.ini upgrade head
```

The conditional copy leaves an existing `.env` untouched. If you intentionally run without
`.env`, omit `--env-file .env` and export `DATABASE_URL` (or use the `127.0.0.1:5432` default).
`uvicorn --env-file` only loads the file for the server process; Alembic and DB-backed tools
need `uv run --env-file .env`.

If host port 5432 is already used, set `POSTGRES_PORT=5433` in `.env` and use the matching
`DATABASE_URL` (as in the macOS/Linux note above). The interpreter lives under
`.venv\Scripts\`; `uv run ...` selects it without activating the environment.

## 2. Verify the simulation

```bash
uv run pytest packages services tests clients/unreal/tools -m "not integration and not slow"
uv run --env-file .env pytest services/world_server/tests -q          # requires PostgreSQL
uv run pytest -m slow -q                              # 100k-event invariant run

uv run python -m tools.bench_sim --npcs 30 --years 20 --seed 42
uv run --env-file .env python -m tools.bench_db --reset --years 20    # persisted; truncates local tables
uv run python -m tools.report_history --days 400
uv run python -m tools.demo_causal --days 400
uv run python -m tools.play
```

The DB-backed commands above load `.env` explicitly. If you intentionally run without it,
omit `--env-file .env` and export the same variables.

The cross-platform determinism gate is `tests/e2e/test_determinism_golden.py`: the 20-year
yearly-cultivation history must hash to the recorded golden on both macOS ARM64 and Linux
x86_64. If a rule change is intentional, update the golden in the same PR and say why.

## 2b. Seed a 20-year agent history (optional, destructive)

```bash
uv run --env-file .env python -m tools.seed_history --years 20 --reset
```

This truncates the local tables, simulates 30 NPCs for 7,300 days with the deterministic
policies, and persists the state/events/memories in one transaction (~4 s, ~19 MB). The server
then boots at tick 7300 with a full history.

## 3. Run the server

Preferred Windows PowerShell launcher (run from the repository root):

```powershell
pwsh -File tools/start_world_server.ps1
# Extra uvicorn arguments are forwarded:
pwsh -File tools/start_world_server.ps1 --host 127.0.0.1 --port 8001
```

Argument forwarding through the script is not acceptance-tested on every PowerShell version.
If a dashed option is rejected, run the equivalent `uv run uvicorn ...` command below directly.

The script runs `uv run uvicorn --env-file .env world_server.app:app` from the repo root and
listens on `127.0.0.1:8000` when no arguments are given. If `.env` is missing it prints an
absolute template/target copy command plus a repository-root `Set-Location` instruction, then
exits; it never creates or overwrites `.env`. The script itself requires `.env`.

Equivalent cross-platform command:

```bash
uv run uvicorn --env-file .env world_server.app:app --host 127.0.0.1 --port 8000
```

Modes (environment):

| Variable | Values | Notes |
|---|---|---|
| `AGENT_PROVIDER` | `utility`, `llm-mock`, `decision-model`, `openai`, `openai-compatible`, `replay` | background decisions; only the six major roles use the configured decision path |
| `DIALOGUE_PROVIDER` | `utility`, `llm-mock`, `openai`, `openai-compatible`, empty | dialogue-only override; empty falls back to `AGENT_PROVIDER`; other values use deterministic text |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | — | required by `openai`/`openai-compatible`; decisions and dialogue share these values when both use a model path, so one endpoint/model is configured (no second independent remote model) |
| `ASR_BASE_URL`, `ASR_MODEL`, `ASR_API_KEY` | — | speech recognition; blank disables it |
| `TTS_BASE_URL`, `TTS_MODEL`, `TTS_VOICE`, `TTS_API_KEY` | — | speech synthesis; blank disables it |
| `EMBEDDING_PROVIDER` | `off`, `hash`, `openai` | `hash` is deterministic plumbing-only |
| `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY` | — | 768-dim required |

Dialogue can run independently of background decisions. For example, keep decisions on the
in-process deterministic `DecisionModelPolicy` while sending dialogue to a local compatible
server:

```dotenv
AGENT_PROVIDER=decision-model
DIALOGUE_PROVIDER=openai-compatible
LLM_BASE_URL=http://127.0.0.1:8080/v1
LLM_MODEL=local-model
# LLM_API_KEY=... only if the local endpoint requires one
```

`decision-model` is the existing local, in-process policy. No standalone Java Decision service
or remote Decision service is currently integrated, and none is required for this setup.
The `/v1/dialogue` response shape is unchanged: `reply_text` plus an optional `proposal`.

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
- `.env` missing on Windows: `tools/start_world_server.ps1` stops with absolute-path copy
  instructions instead of creating the file; from the repo root run
  `if (-not (Test-Path .env)) { Copy-Item .env.example .env }`, then edit `.env` yourself.
- Alembic/DB tools ignore `uvicorn --env-file`: use `uv run --env-file .env alembic ...` or
  `uv run --env-file .env python -m tools.<name> ...` (or export `DATABASE_URL`).
- PowerShell blocks the script: use
  `powershell -ExecutionPolicy Bypass -File tools/start_world_server.ps1` or adjust the local
  execution policy.
- `/v1/dialogue` returns 503 `agent_provider_misconfigured` with
  `DIALOGUE_PROVIDER=openai-compatible`: set `LLM_BASE_URL` and `LLM_MODEL`, or clear
  `DIALOGUE_PROVIDER` to fall back to `AGENT_PROVIDER`.
- CI fast job must exclude integration tests; they are marked at module level in
  `services/world_server/tests/`.
