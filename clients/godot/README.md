# Godot vertical slice

A lightweight Godot 4.7.2 client for the authoritative world server. This is an **additive**
presentation layer: the UE5 scaffold remains, and neither client owns simulation truth.

**Status: scaffold only.** Godot is not installed on the current macOS development machine, so
the project has not been opened, imported, or run. Static checks and the layout sync are verified;
runtime/FPS must be validated on the Windows or Ubuntu machine with Godot 4.7.2.

## Run the backend

Follow `docs/runbook.md`. In short:

```bash
docker compose up -d postgres
export DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/unwritten_dao
uv run alembic -c services/world_server/alembic.ini upgrade head
uv run uvicorn world_server.app:app --host 127.0.0.1 --port 8000
```

Use the local `.env` for the 5433 port on this machine. Seed a world if the database is empty:
`uv run python -m tools.seed_history --years 1 --reset`.

## Run the client

1. Install Godot 4.7.2 (standard build, no .NET).
2. Import `clients/godot/project.godot`.
3. Press Play. The client fetches `/v1/world/snapshot` and polls events every second.

Controls: WASD move, E interact (move to nearest location), F take first item, R investigate,
G enter a discovered realm, H claim, T talk, N advance one day, F5 resync.

Movement is presentation-only. Entering a location sends a `move` command; item, investigation,
realm, claim, dialogue, and time actions all go through `world_core` on the server. A 409 response
triggers a snapshot resync and never local simulation.

## Data

`data/mvp_scene.json` is copied from `clients/unreal/Content/Layout/mvp_scene.json`:

```bash
uv run python clients/godot/tools/sync_layout.py          # copy + validate
uv run python clients/godot/tools/sync_layout.py --check  # verify only
```

The file is checked for 8 locations, 30 unique NPC ids, symmetric adjacency, and the source
checksum/UE5 actor-tag mapping.

## Static verification

```bash
uv run python clients/godot/tools/check_gdscript.py
uv run pytest clients/godot/tests -q
uv run ruff check clients/godot/tools clients/godot/tests
```

## Limitations

- No Godot editor/runtime validation on this machine.
- No imported 3D assets: all meshes are built-in placeholders.
- No real LLM/embedding calls; dialogue uses the server's configured provider or fallback.
- The player can walk freely, but only location-level movement is authoritative.
- FPS and 1% low must be measured on the target machine.
