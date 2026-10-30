# Godot vertical slice

This project validates gameplay and authoritative server integration. The separate local
`../godot-art/project.godot` project preserves the courtyard art, retargeted animations,
materials and captures. Its visuals are not evidence that the gameplay slice is integrated.

## OpenAI-compatible dialogue actions

Configure the **server** environment with `DIALOGUE_PROVIDER=openai-compatible`
(or leave it empty and set `AGENT_PROVIDER=openai-compatible` to use the legacy
fallback), `LLM_BASE_URL` (including `/v1`), `LLM_MODEL`, and optional `LLM_API_KEY`.
The decision and dialogue paths share these `LLM_*` values when both use a model;
only one endpoint/model is configured, not two independent remote models.
No credentials belong in the Godot client. Local compatible endpoints can omit a key.
Dialogue includes the NPC's observations, goals and retrieved event memories. The NPC may
decline or propose an action; the client submits that proposal to `/v1/commands` with a
stable idempotency key. Only accepted command events and refreshed snapshots confirm a
world change. A stale proposal is discarded and requires another conversation.

Voice controls are optional: click **录音**, then **停止录音** (automatic stop after
30 seconds). Review/edit the transcript and click Talk to send it. **取消语音** discards
pending audio, and **播放 NPC 合成语音** opts into synthetic reply playback (off by default).
Typing and recording suspend movement shortcuts; Esc returns to walking.

Configure ASR independently on the server with `ASR_BASE_URL`, `ASR_MODEL`, and optional
`ASR_API_KEY`. Configure TTS with `TTS_BASE_URL`, `TTS_MODEL`, `TTS_VOICE`, and optional
`TTS_API_KEY`. URLs include `/v1`; there are no default cloud endpoints or models.
Providers must support 16-bit PCM WAV. Missing speech configuration leaves text dialogue usable.
No audio is stored by default. Cancelling audio does not undo a world command already submitted.

The new voice path is tested using synthetic WAV and localhost substitutes, including actual
Godot HTTP transport. Real microphone input, recognition/pronunciation quality and latency
still need configured providers and manual acceptance. Persistent conversational commitments
and integration with the separate art project remain pending.

Optional transport regression test (requires Godot on PATH or `GODOT_BIN`):
`uv run pytest tests/e2e/test_godot_voice_http.py`.

A lightweight Godot 4.7.2 client for the authoritative world server. This is an **additive**
presentation layer: the UE5 scaffold remains, and neither client owns simulation truth.

**Status: headless runtime verified on macOS, editor/FPS not.** Godot 4.7.2 imported the project,
fetched a live 30-NPC snapshot, and submitted an accepted `advance_time` command (HTTP 200) against
the local world server on 2026-10-27. The interactive editor session, rendering, movement, and FPS
are still unverified and must be checked on the Windows or Ubuntu machine.

## Run the backend

Follow `docs/runbook.md`. In short:

```bash
docker compose up -d postgres
uv run --env-file .env alembic -c services/world_server/alembic.ini upgrade head
uv run uvicorn --env-file .env world_server.app:app --host 127.0.0.1 --port 8000
```

`docker compose` reads `.env` automatically; the other commands load it explicitly. Use the
local `.env` to select a non-default port such as 5433 on this machine. If you intentionally
run without `.env`, omit `--env-file .env` and export `DATABASE_URL` (defaults to
`127.0.0.1:5432`); on Windows, `pwsh -File tools/start_world_server.ps1` starts the server
after requiring `.env`. Seed a world if the database is empty:
`uv run --env-file .env python -m tools.seed_history --years 1 --reset`.

## Run the client

1. Install Godot 4.7.2 (standard build, no .NET).
2. Import `clients/godot/project.godot`.
3. Press Play. The client fetches `/v1/world/snapshot` and polls events every second.

Set `UNWRITTEN_DAO_API` (for example `http://127.0.0.1:8011`) when the server does not run on the
default `http://127.0.0.1:8000`.

Controls: WASD move, E interact (move to nearest location), F take first item, R investigate,
G enter a discovered realm, H claim, T talk, N advance one day, F5 resync.

Movement is presentation-only. Entering a location sends a `move` command; item, investigation,
realm, claim, dialogue, and time actions all go through `world_core` on the server. A 409 response
triggers a snapshot resync and never local simulation.

## Data

`layout/mvp_scene.json` is copied from `clients/unreal/Content/Layout/mvp_scene.json`:

```bash
uv run python clients/godot/tools/sync_layout.py          # copy + validate
uv run python clients/godot/tools/sync_layout.py --check  # verify only
```

The file is checked for 8 locations, 30 unique NPC ids, symmetric adjacency, and the source
checksum/UE5 actor-tag mapping.

## Static verification

```bash
uv run python clients/godot/tools/check_gdscript.py
uvx --from gdtoolkit==4.5.0 gdlint clients/godot/scripts clients/godot/tests/smoke_server.gd
uv run pytest clients/godot/tests -q
uv run ruff check clients/godot/tools clients/godot/tests
```

## Live-server smoke (optional, not CI)

With the world server running:

```bash
UNWRITTEN_DAO_API=http://127.0.0.1:8000 \
  godot --headless --path clients/godot --script res://tests/smoke_server.gd
```

It fetches a snapshot, submits one `advance_time` command through `WorldClient`, prints the
result, and exits 0. It advances the persisted demo world by one day.

`tests/key_item_loop.gd` requires a fresh tick-0 world (reset the local DB first) and drives the
canonical loop: take the map, investigate, enter the realm, claim the pill. It mutates that
world, so reseed afterwards.

## Limitations

- No editor session, rendering check, or FPS measurement yet; only headless import and HTTP
  round-trips were run on this machine.
- No imported 3D assets: all meshes are built-in placeholders.
- No real LLM/embedding calls; dialogue uses the server's configured provider or fallback.
- The player can walk freely, but only location-level movement is authoritative.
- FPS and 1% low must be measured on the target machine.
