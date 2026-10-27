# Godot vertical-slice acceptance

Static checks are verified on macOS. Runtime rows are **NOT RUN** until the project is opened in
Godot 4.7.2 on Windows/Ubuntu.

| Check | Status | Evidence |
|---|---|---|
| Layout sync | PASS | `tools/sync_layout.py --check` (8 locations, 30 NPCs, symmetric adjacency) |
| Project/scene references | PASS | `tools/check_gdscript.py` |
| Client API endpoints | PASS (static) | snapshot, events, commands, dialogue present |
| No local authority logic | PASS (static) | no `world_core`/damage/combat in GDScript |
| NPC ID → Node mapping | PASS (static) | layout IDs; `npc_views` keyed by npc_id |
| Map → investigate → realm → pill → breakthrough | NOT RUN | requires server + Godot |
| 409 resync | NOT RUN | code path present; needs live race |
| Dialogue | NOT RUN | requires server provider/fallback |
| 1080p FPS / 1% low | NOT RUN | target ≥60 / ≥45 |
| Packaging | NOT RUN | export preset not created |

## Manual runbook (target machine)

1. Start the server and seed a 1-year world.
2. Open the project; confirm snapshot tick/NPC count in the status label.
3. Walk to the ruined temple, take the map (F), go to the misty valley, investigate (R).
4. Enter the cave (G), claim the pill (H), then use the API/UI to advance time.
5. Confirm the event log shows authoritative events and the NPC actor count is 30.
6. Force a 409 by submitting a stale command (or use two clients), confirm F5 resync.
7. Capture a 1080p screenshot and FPS/1% low numbers; record them in `docs/status.md`.
