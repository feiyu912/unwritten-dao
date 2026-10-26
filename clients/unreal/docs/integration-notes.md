# Client integration notes

## Snapshot → actors

1. `UWorldSyncSubsystem` fetches `GET /v1/world/snapshot` on begin play.
2. For each NPC in `state.npcs`, find or spawn `ANpcViewActor` keyed by `npc_id`.
3. Apply presentation fields: name, realm/stage text, alive/dead state, and the location's
   projected world transform. Never write these values back into the client as truth.
4. NPCs whose `location_id` differs from the player's area are hidden or shown as abstract
   markers; only nearby NPCs get full actors.

## Events → feedback

- Poll `GET /v1/world/events?after=<cursor>` (or the WebSocket `/v1/events/stream`).
- Map event types to UI:
  - `SECRET_REALM_DISCOVERED` → unlock the cave marker and show a notification.
  - `OPPORTUNITY_CLAIMED` → item toast with `payload.name`.
  - `BREAKTHROUGH_ATTEMPT` → realm-up or failure banner.
  - `ITEM_TRANSFERRED` → inventory refresh.
  - `NPC_DIED` → remove the actor and show a rumor/notification.
- Persist the last `event_id` locally so a reconnect resumes from the cursor.

## Commands and resync

- All player actions become `POST /v1/commands` with a fresh `command_id`, an idempotency key,
  and the latest `expected_state_version`.
- HTTP 409 `stale_state_version` → fetch a new snapshot, re-render, and ask the player to retry.
- Timeouts → retry the same idempotency key; never simulate locally.

## Movement / NavMesh

- The authoritative state stores region-level `location_id`, not transforms.
- The client projects each region to a NavMesh island and moves the actor locally for animation.
- On region transition, submit a `move` command and wait for `NPC_MOVED`/snapshot confirmation.
- Remote NPCs are abstract markers; do not run behavior trees for them.

## Dialogue

- `POST /v1/dialogue` returns `reply_text` plus an optional proposal.
- Show the text in `UDialogueWidget`; never apply a proposal automatically — the player decides.
- With no LLM provider configured, the server returns a deterministic in-character fallback.

## Still required in a real editor

1. Compile the C++ module against the pinned UE 5.6.
2. Create the UMG widget Blueprints and bind the dialogue/notification delegates.
3. Build the level, NavMesh, and lighting; validate the camera/movement feel.
4. Measure FPS (1080p target ≥60, 1% low ≥45) with the local LLM running, if used.
5. Package a Development build and run a full player→command→event→render loop.