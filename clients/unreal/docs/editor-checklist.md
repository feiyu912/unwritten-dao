# Editor checklist (Ubuntu GPU workstation)

**Status: UNVERIFIED.** No Unreal Engine is installed on the authoring machine. Every step
below is a plan for the GPU workstation, not evidence that it works. Do not mark the client
validated until the acceptance captures and packaged run in section 10 exist.

## 0. Preflight

- [ ] Ubuntu 22.04/24.04, NVIDIA driver and Vulkan working (`vulkaninfo --summary`).
- [ ] UE 5.6 installed; confirm the exact patch and pin it in `UnwrittenDao.uproject`
      (`EngineAssociation` is currently `5.6`).
- [ ] Toolchain for UE 5.6 Linux (clang version required by that engine release).
- [ ] Git LFS available; the repository is public, so do not add unlicensed binaries.
- [ ] Python 3.12, `uv`, and the repo checked out; run `uv sync --all-packages`.
- [ ] Server dependencies available if testing the full loop (PostgreSQL, see
      `services/world_server/README.md`).

Record the engine patch, driver version, GPU model, and OS build in the validation notes.

## 1. Regenerate and verify the layout

From the repository root:

```bash
uv run python clients/unreal/tools/export_scene_layout.py
uv run pytest clients/unreal/tools/test_scene_layout.py -q
uv run pytest clients/unreal/tools -q
uv run ruff check clients/unreal/tools
```

- [ ] Export prints `locations=8 npc_spawns=30` and
      `checksum=sha256:690ef5a4ee9baa76197135d6cfd1024a88dd1d55a9a90afc1f668cf844f421bb`.
- [ ] The checked-in `Content/Layout/mvp_scene.json` is unchanged by a second export.
- [ ] If the checksum differs, stop: the seed world changed. Do not hand-edit the JSON.

## 2. Create the persistent level and import the layout

`mvp_scene.json` is data, not a UE asset. Import it with the editor's Python plugin or place
actors manually.

### Option A: editor Python (preferred, unverified)

- [ ] Enable **Python Editor Script Plugin** and restart the editor.
- [ ] Create `/Game/Maps/Courtyard` (matches `Config/DefaultEngine.ini`) as the persistent
      level.
- [ ] Run a Python script in the output log that:
  - loads `Content/Layout/mvp_scene.json` with `json`;
  - spawns one `unreal.TargetPoint` per `locations[]` entry at `coordinates_xy_cm`
    (X, Y, Z=0), sets its actor label/tag to `actor_tag`, and adds a child marker at
    `interaction_anchor.coordinates_xy_cm`;
  - spawns one actor of class `/Script/UnwrittenDao.NpcViewActor` for each non-player
    `npc_spawns[]` entry, sets `NpcId` to the full UUID, tags it with `actor_tag`, and
    positions it at `coordinates_xy_cm`;
  - uses the `is_player` record for the possessed pawn and places a `PlayerStart` at
    `player_spawn.coordinates_xy_cm`; it is not a second remote NPC.
- [ ] Because the C++ module must be compiled before the NPC class exists, do section 4
      first if the class is not found.
- [ ] Save the level and verify actor counts: 8 location markers, 29 remote NPC actors,
      1 player pawn/start; all 30 spawn records are accounted for.

### Option B: manual placement (fallback, unverified)

- [ ] Place 8 `TargetPoint` actors using the coordinates in `docs/scene-plan.md`.
- [ ] Place 30 `ANpcViewActor` actors using the NPC table; set each `NpcId` exactly.
- [ ] Keep a spreadsheet or data table of tag -> UUID so a typo is detectable.

## 3. Blockout the four areas

- [ ] Courtyard (`location_stone_town`): ground plane, low walls, a few market stalls,
      PlayerStart, lighting.
- [ ] Sect gate (`location_xuanyue_sect`): gate frame, steps, hall facade blockout; keep the
      `sect_gate` anchor clear.
- [ ] Forest edge (`location_blackwood_forest`): ground, tree card cluster, trail toward the
      north-east; keep the `forest_edge` anchor clear.
- [ ] Secret-realm entrance (`location_ancient_cave`): rock shell and a cave mouth at
      `cave_mouth`; do not light or label it as a known landmark.
- [ ] Supporting locations: simple markers/proxy geometry only (market, outpost, temple,
      valley). Do not invest in full art before the acceptance pass.
- [ ] Use 1 Unreal unit = 1 cm. Keep the blockout on Z=0; no landscape yet.
- [ ] Verify no overlapping walkable floors at location boundaries.

## 4. Compile and bind the C++ scaffold

- [ ] Generate project files and compile the `UnwrittenDaoEditor` target for Linux. The
      module is currently **uncompiled**; fix compile errors before proceeding.
- [ ] Confirm the GameMode `AUnwrittenDaoGameMode` is set in
      `Config/DefaultEngine.ini` (`GlobalDefaultGameMode`).
- [ ] Confirm `UWorldSyncSubsystem` auto-instantiates for the game world and starts polling.
- [ ] Create a player controller or level Blueprint that creates a `UWorldCommandClient`,
      calls `Initialize(WorldSyncSubsystem)`, and binds `OnCommandAccepted` /
      `OnCommandRejected`.
- [ ] Set the HTTP base URL for the target environment:
      - full server: `http://127.0.0.1:8000` (current default);
      - headless mock: run it on another port and update `Config/DefaultGame.ini`.
- [ ] Wire `ANpcViewActor::BindToWorld()` after spawn; bind snapshot/event delegates.
- [ ] Verify a 409 response triggers `RequestResync()` and not local state changes.

## 5. NavMesh

- [ ] Add a `NavMeshBoundsVolume` covering the courtyard, sect gate, forest edge, and cave
      entrance; add separate volumes in each streaming level.
- [ ] Confirm `bAutoCreateNavigationData=True` (already in `DefaultEngine.ini`).
- [ ] Set agent radius/height for the mannequin; rebuild navigation.
- [ ] Enable `Show Navigation` and verify the cave mouth is reachable only from the valley
      side and the gate anchor is reachable.
- [ ] Test that NPC presentation movement projects onto the NavMesh and snaps on resync.
- [ ] Verify no NavMesh under unloaded streaming levels causes falling actors.

## 6. UMG widgets

- [ ] Create `WBP_Dialogue` with parent class `UDialogueWidget`; add transcript `TextBlock`,
      input `EditableTextBox`, send button, and close button.
- [ ] Implement `BP_OnReply` and `BP_OnError`; never apply the returned proposal.
- [ ] Create `WBP_EventToast` for `SECRET_REALM_DISCOVERED`, `OPPORTUNITY_CLAIMED`,
      `BREAKTHROUGH_ATTEMPT`, `ITEM_TRANSFERRED`, `NPC_DIED`.
- [ ] Create `WBP_InteractionPrompt` that appears inside an interaction volume.
- [ ] Assign the dialogue widget class in the GameMode/player controller and set input mode
      correctly when it opens.
- [ ] Test CJK glyph coverage for all names and UI strings with the chosen OFL font.

## 7. Level streaming

- [ ] Create streaming sublevels matching `location_actor_map`:
      `/Game/Maps/Streaming/L_StoneTown`, `L_XuanyueSect`, `L_BlackwoodForest`,
      `L_RuinedTemple`, `L_MistyValley`, `L_AncientCave`, `L_ChixiaoOutpost`,
      `L_BlackMarket`.
- [ ] Keep `L_StoneTown` always loaded (player start).
- [ ] Use distance streaming for sect gate and forest; manual streaming for the cave,
      outpost, and market.
- [ ] Keep the cave marker and `L_AncientCave` unloaded until the player receives
      `SECRET_REALM_DISCOVERED`; verify no map label leaks it earlier.
- [ ] Verify transitions do not teleport the player or duplicate NPC actors.

## 8. Play-in-Editor validation

Start the authoritative server (not the mock) for the full loop:

```bash
# separate terminal; the app bootstraps the seed=42 world when the DB is empty
docker compose up -d postgres
export DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/unwritten_dao
uv run alembic -c services/world_server/alembic.ini upgrade head
uv run uvicorn world_server.app:app --port 8000
curl -s http://127.0.0.1:8000/v1/health
```

The mock server (`uv run python clients/unreal/tools/mock_world_server.py 127.0.0.1 8787`)
only exercises HTTP plumbing; its snapshot state is empty, so NPC spawning needs the real
server.

- [ ] PIE starts; `/v1/health` returns `ok`; snapshot arrives; `state_version` is displayed.
- [ ] All 30 spawn records are accounted for: 29 remote NPC actors plus the player pawn,
      with the expected tags and no duplicate `NpcId`.
- [ ] Player spawn matches `location_stone_town`; player ID is
      `406f2708-f41f-5fb5-9957-a8f13776b72a`.
- [ ] A `move` command is submitted with a fresh idempotency key; the client waits for
      confirmation and never moves locally first.
- [ ] Dialogue with 沈砚 returns `reply_text`; the proposal is shown as debug text only.
- [ ] Killing the server or returning 409 shows a resync path; no local simulation.
- [ ] Event cursor survives a reconnect and resumes from the last `event_id`.
- [ ] `NPC_DIED` removes/despawns the actor and shows a notification.
- [ ] Cave marker stays hidden until `SECRET_REALM_DISCOVERED`; then the manual level loads.
- [ ] Measure 1080p FPS: `stat fps`, `stat unit`; target >= 60 with 1% low >= 45.
- [ ] Check logs for HTTP errors, JSON parse failures, and ensure no "simulate" fallback.

## 9. Packaging

- [ ] Set the map list to `Courtyard` plus all streaming levels; cook all maps.
- [ ] Package a Linux Development build with the documented Unreal Automation Tool command.
- [ ] Confirm the packaged build includes the UMG assets, font license notices, and no
      editor-only content.
- [ ] Run the packaged binary against the server; repeat the core loop (snapshot, move,
      dialogue, event toast, cave discovery).
- [ ] Confirm the packaged build does not read `Content/Layout/mvp_scene.json` at runtime.

## 10. Acceptance captures

Store these under a local `Saved/Acceptance/` (ignored by git unless approved) and attach
them to the validation note:

- [ ] Editor viewport: courtyard + sect gate + forest edge + cave entrance, with actor tags
      visible.
- [ ] PIE at spawn: 30 NPC actor count, player location, snapshot version.
- [ ] Dialogue panel with a real reply and a proposal shown as non-applied debug text.
- [ ] Event toast for `ITEM_TRANSFERRED` and `NPC_DIED`.
- [ ] Cave marker hidden before discovery and visible after discovery.
- [ ] `stat unit` / `stat fps` screenshot at 1080p.
- [ ] Packaged build running the same loop, with the executable name and build config.
- [ ] Server log excerpt showing command ids, state versions, and no rejected 409 loops.

## 11. Sign-off

| Item | Evidence | Status |
|---|---|---|
| Layout imported | actor counts, screenshot | pending |
| C++ compile | build log | pending |
| NavMesh | navigation screenshot | pending |
| UMG | dialogue screenshot | pending |
| Streaming | cave gating screenshot | pending |
| PIE loop | server log + video | pending |
| Packaging | packaged build + log | pending |
| FPS target | `stat unit` capture | pending |

Until all rows have evidence, the client remains an unvalidated scaffold.