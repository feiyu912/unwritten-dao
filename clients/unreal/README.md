# Unreal client (scaffold)

UE5 is the presentation client for the authoritative world server. This directory contains an
**unvalidated C++ scaffold plus a headless mock server**. There is no Unreal Engine installation
on the current development machine, so nothing here has been compiled or opened in the editor.

## Target

- Engine: **UE 5.6** — confirm the exact 5.x patch on the GPU workstation and pin it in
  `UnwrittenDao.uproject` before the first editor session.
- Template: Third Person, C++ project with Blueprint-exposed components.
- Scope: one courtyard/town area, sect gate, forest edge, and a secret-realm entrance.

## Modules

| Type | Responsibility |
|---|---|
| `UWorldSyncSubsystem` | Fetches `/v1/world/snapshot` and `/v1/world/events?after=`, broadcasts snapshot/event updates. Never simulates. |
| `UWorldCommandClient` | Posts `world-command.v1` JSON with `command_id`, `idempotency_key`, `expected_state_version`; resyncs on HTTP 409. |
| `ANpcViewActor` | Projects authoritative NPC fields (location, realm, stage, alive) onto a pawn/actor. Movement is cosmetic. |
| `UDialogueWidget` | Submits `/v1/dialogue` and shows the reply text. Blueprint asset binding still required. |

## Hard rules

1. The client never computes cultivation, combat, death, ownership, or discovery.
2. A failed request must surface as failure or queue for retry — never local simulation.
3. The world server is the only source of truth; the client renders snapshots and events.

## Getting started (on a machine with UE5)

1. Verify UE 5.6 is installed; open `UnwrittenDao.uproject`.
2. Start the backend (`services/world_server/README.md`) or the headless mock:
   `uv run python clients/unreal/tools/mock_world_server.py --port 8787`.
3. Set the base URL in `Config/DefaultGame.ini`.
4. Create the UMG assets that derive from `UDialogueWidget` and assign the pawn/actor classes in
   the level Blueprint.
5. Validate Play-in-Editor, then package a Development build.

## Blockout layout

`Content/Layout/mvp_scene.json` is generated from the authoritative seed world (8 locations,
30 NPC spawns, player spawn, actor tags, streaming suggestions). Regenerate and verify it with:

```bash
uv run python clients/unreal/tools/export_scene_layout.py
uv run pytest clients/unreal/tools/test_scene_layout.py -q
```

Do not hand-edit the JSON. The editor import procedure, scene plan, and asset policy are in
`docs/scene-plan.md`, `docs/editor-checklist.md`, and `docs/asset-licenses.md`.

## Status

- C++ scaffold: written against the versioned JSON contracts; **not compiled**.
- Headless mock: tested (`uv run pytest clients/unreal/tools -q`).
- Layout export: deterministic and tested headlessly (no editor/DB); editor import is pending.
- Editor validation, asset import, NavMesh projection, and packaging: **pending on the GPU machine**.

See `docs/integration-notes.md`, `docs/asset-list.md`, `docs/asset-licenses.md`,
`docs/scene-plan.md`, and `docs/editor-checklist.md`.
