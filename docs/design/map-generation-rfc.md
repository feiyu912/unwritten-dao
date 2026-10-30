# RFC: Versioned Seed → MapSpec → Authoritative Genesis → Godot Presentation

Status: **Draft for user approval.** No contract, product code, migration, asset or credential is changed by this RFC. Implementation may start only after the contract versions below are approved and Codex has reviewed the compatibility plan.

## 1. Decision summary

1. **Canonical v1 stays frozen.** `create_world(42)`, `world-snapshot.v1`, `ruleset.v1`, the existing golden checksums and all saved v1 worlds keep their current bytes and checksums. No seed-42 special case is introduced.
2. **Generated worlds are a separate, explicitly versioned mode.** A new `create_world_generated(seed)` path uses `mapgen.v1`, `map-spec.v1`, `world-state.v2`, `world-snapshot.v2`, `world-genesis.v1` and `ruleset.v2`. It is never selected implicitly for an existing world.
3. **MapSpec is authoritative and visual-free.** It contains topology, exits, route cost/conditions, resources, opportunities, gates, risks and spawns. Coordinates, colors, meshes, collision and navigation live only in `map-presentation.v1`.
4. **The full genesis is persisted, not regenerated on load.** `world_genesis` stores the complete MapSpec, the initial v2 state and the initial genesis events. Replay restores that genesis and applies the command log; it never re-runs the generator.
5. **Modes and versions are persisted and checkable.** Generated snapshots carry `generation.mode`, `generator_version`, `map_spec_digest` and `genesis_digest`; the v2 checksum includes that generation domain. Canonical v1 checksums are untouched.
6. **Generated presentation is knowledge-filtered.** The public presentation endpoint never returns hidden resources, hidden gates, undiscovered interiors or raw MapSpec. The full genesis artifact is server/offline-only.
7. **MVP remains small.** Fixed 8-location topology, fixed 30-NPC roster, one core opportunity (foundation pill), at most two auxiliary resources, one secret realm and one or two gates/risks. No open world, new NPCs, new event types, editor, art generation or multi-world UI.

## 2. Compatibility invariants

- `create_world(42)` is unchanged: same `world_id`, same `world_seed`, same `ruleset_version=1.0.0`, same state dump and same v1 checksum. Existing golden tests are not edited.
- `restore_snapshot` of a v1 document is unchanged. Existing saves load and continue without a migration that rewrites `state` or `checksum`.
- The new generated path uses a distinct `world_id`:
  - canonical: existing `uuid5(ns, "world:<seed>")`.
  - generated: `uuid5(ns, "world:generated:<generator_version>:<seed>")`.
- The v1 checksum has no new fields and no new domain. The v2 checksum includes `generation` and is versioned as `checksum_version: "2"`. Therefore canonical seed 42 and generated seed 42 are distinguishable by both `world_id` and `checksum`, even if their content happened to coincide.
- A server never switches an existing database from canonical to generated. If `WORLD_GENERATION_MODE` disagrees with the persisted world mode, bootstrap fails with `world_generation_mismatch`; it does not reset or regenerate.
- Generated mode is only created on an empty database, or through an explicit admin command that creates a new world. There is no silent conversion of old saves.
- No generated content is accepted as an excuse to weaken an existing replay, causality, ownership or save/load test. Generated goldens are new, separate fixtures.

## 3. Flow

```text
seed + generator_version + ruleset_version
        -> MapSpec (authoritative, versioned, visual-free)
        -> GenesisBuilder -> initial v2 state + genesis events + genesis digest
        -> world_genesis (immutable, full replay input)
        -> commands / events / snapshots (runtime truth)
        -> public projection + knowledge filter -> map-presentation.v1
        -> Godot placement / collision / navigation only
```

The generator produces data; it does not mutate a running world. Runtime mutations still go only through `world_core.apply_command`.

## 4. What is authoritative and what is visual

| Concern | MapSpec / state | Presentation |
|---|---|---|
| Location identity and kind | authoritative | references only known locations |
| Exits, travel cost, conditions | authoritative | visual anchors/triggers only |
| Items, owners, stashes, opportunities | authoritative | never listed; client uses snapshot visibility |
| Secret realm gates and open windows | authoritative | interior omitted until discovered |
| Risks (guard/gate/deadline) | authoritative declarations compiled into real NPC goals/gates/deadlines | no risk data |
| Coordinates, rotation, scale | absent | visual-only, deterministic profile |
| Mesh/model, material, color | absent | visual-only |
| Collision shapes, navmesh | absent | visual/physics only; never creates a legal exit |
| Generator/ruleset versions, digests | authoritative metadata | digest echoed for consistency checks |

Presentation may be regenerated, restyled or replaced without changing the world checksum. It must not add a location, exit, item, opportunity or NPC decision.

## 5. MapSpec v1

`map-spec.v1` is the only generator output. It is canonical JSON, sorted and content-addressed. It contains no coordinates, colors, mesh paths, collision or navigation data.

```json
{
  "schema_version": "map-spec.v1",
  "spec_version": "1.0.0",
  "seed": 7,
  "generator_version": "mapgen.v1",
  "ruleset_version": "2.0.0",
  "player_spawn": "loc_stone_town",
  "locations": [
    {
      "location_id": "loc_stone_town",
      "kind": "town",
      "aura_multiplier": 0.8,
      "exits": [
        { "to_location_id": "loc_black_market", "travel_cost": 1, "conditions": [] },
        { "to_location_id": "loc_xuanyue_sect", "travel_cost": 2,
          "conditions": [{ "kind": "realm_min", "value": 1 }] }
      ]
    }
  ],
  "items": [
    {
      "item_id": "item_map_fragment",
      "kind": "map",
      "unique": true,
      "placement": { "kind": "location_stash", "location_id": "loc_ruined_temple" },
      "properties": {
        "points_to": "loc_misty_valley",
        "realm_id": "realm_ancient_cave"
      }
    }
  ],
  "opportunities": [
    {
      "opportunity_id": "opp_foundation_pill",
      "location_id": "loc_ancient_cave",
      "reward_item_ids": ["item_foundation_pill"],
      "requires_item_id": "item_map_fragment",
      "active_until_tick": 5475,
      "risk_id": "risk_guard_pill"
    }
  ],
  "gates": [
    {
      "gate_id": "gate_ancient_cave",
      "kind": "secret_realm",
      "entrance_location_id": "loc_misty_valley",
      "interior_location_id": "loc_ancient_cave",
      "requires_item_id": "item_map_fragment",
      "open_tick": 0,
      "close_tick": 5475
    }
  ],
  "risks": [
    {
      "risk_id": "risk_guard_pill",
      "kind": "guard",
      "location_id": "loc_ancient_cave",
      "guard_npc_id": "<npc-uuid>",
      "goal_kind": "defeat_rival",
      "goal_target_id": "<npc-uuid>"
    }
  ]
}
```

Rules:

- Every location must be reachable from `player_spawn` through declared exits when all gate conditions are satisfied. At least one exit on the core path has a condition that is not initially satisfied.
- `travel_cost` is a positive integer **route weight**. In M1 it participates in generator validity, reachability budgets and NPC path ordering; it does not add ticks to `move`. Charging time for travel would change command semantics and is explicitly a separate future ruleset, not silently implemented here.
- `conditions` are checked by `ruleset.v2` at command time. Existing secret-realm failures reuse `realm_undiscovered`/`realm_closed`; ordinary exit conditions reject with a stable `route_locked` error code. No new event type is introduced.
- `risks` may only compile into existing mechanisms: an existing NPC with a real goal (guard), an existing gate condition, or an existing opportunity deadline. No `Risk` object is added to world state and no new event type is invented.
- Items, NPC identities and factions are drawn from the fixed MVP roster; the generator places and connects them, it does not create a new society.
- Unknown fields are rejected. A MapSpec cannot smuggle visual or hidden data into authoritative state.

## 6. Protocol shapes and persistence

### 6.1 Generated snapshot v2

`world-snapshot.v2` is emitted only for generated worlds. Canonical worlds continue to emit `world-snapshot.v1`.

```json
{
  "schema_version": "world-snapshot.v2",
  "world_id": "9e4f...",
  "tick": 0,
  "last_event_id": 7,
  "state_version": 0,
  "world_seed": 7,
  "sim_version": "0.1.0",
  "ruleset_version": "2.0.0",
  "checksum_version": "2",
  "checksum": "sha256:...",
  "generation": {
    "mode": "generated",
    "generator_version": "mapgen.v1",
    "map_spec_digest": "sha256:...",
    "genesis_digest": "sha256:..."
  },
  "state": { "...": "world-state.v2" }
}
```

The seed is persisted as the existing top-level `world_seed`; `ruleset_version` stays top-level and in `state`; `generation.mode`, `generator_version`, `map_spec_digest` and `genesis_digest` identify the generator and immutable genesis. The v2 checksum is `sha256` over a canonical document containing `checksum_version`, `generation` and `state`. It must never be compared numerically with a v1 checksum; equality is only meaningful within the same `checksum_version`.

### 6.2 Full genesis

`world-genesis.v1` is a server/offline artifact, not a public API response. It is immutable and content-addressed.

```json
{
  "schema_version": "world-genesis.v1",
  "world_id": "9e4f...",
  "mode": "generated",
  "seed": 7,
  "generator_version": "mapgen.v1",
  "ruleset_version": "2.0.0",
  "map_spec": { "...": "map-spec.v1" },
  "map_spec_digest": "sha256:...",
  "initial_state": { "...": "world-state.v2 at tick 0" },
  "initial_events": [ { "...": "world-event.v1" } ],
  "initial_state_checksum": "sha256:...",
  "genesis_digest": "sha256:..."
}
```

`genesis_digest` covers the canonical MapSpec, initial state and initial events. A snapshot carries only `genesis_digest`; the full genesis is stored in `world_genesis` and exported by a local operator tool. There is no unauthenticated HTTP route that returns hidden MapSpec content.

### 6.3 Godot presentation

`map-presentation.v1` is public but knowledge-filtered. It is keyed to one snapshot and one MapSpec digest.

```json
{
  "schema_version": "map-presentation.v1",
  "world_id": "9e4f...",
  "map_spec_digest": "sha256:...",
  "state_version": 12,
  "presentation_profile": "placeholder.v1",
  "coordinate_system": "godot-y-up-meters",
  "locations": [
    {
      "location_id": "loc_stone_town",
      "position": [0.0, 0.0, 0.0],
      "rotation_y": 0.0,
      "model": "res://presentation/placeholder_pad.tscn",
      "collision": { "type": "box", "size": [8.0, 0.2, 8.0] },
      "navmesh": "res://presentation/placeholder_nav.tres",
      "exit_markers": [
        { "to_location_id": "loc_black_market", "position": [4.0, 0.0, 0.0] }
      ]
    }
  ],
  "player_spawn": { "location_id": "loc_stone_town", "position": [0.0, 1.0, 0.0] },
  "npc_anchors": [
    { "location_id": "loc_stone_town", "position": [2.0, 0.0, 2.0] }
  ]
}
```

Filtering rules:

- Only locations in the player's `known_locations` (or the current location) are returned. Undiscovered secret interiors are absent.
- Hidden items, hidden opportunities, gate condition details and NPC goals are never returned.
- `npc_anchors` are positions, not identities or hidden NPC data; actual NPCs come from the authoritative snapshot.
- If `map_spec_digest` or `world_id` does not match the snapshot, the client must not use the presentation. It must show a diagnostic/placeholder and continue to use snapshot/commands, never invent a local map.
- The endpoint returns `Cache-Control: no-store`; discovery and state changes can change the filtered set.

## 7. Contract changes requiring approval

| File | Action | Schema/version | Why |
|---|---|---|---|
| `docs/contracts/map-spec.v1.schema.json` | new | `map-spec.v1`, 1.0.0 | authoritative generator output |
| `docs/contracts/world-state.v2.schema.json` | new | `world-state.v2`, 2.0.0 | generated state with exit specs/conditions; canonical state remains v1 |
| `docs/contracts/world-snapshot.v2.schema.json` | new | `world-snapshot.v2`, 2.0.0 | generation metadata and v2 checksum |
| `docs/contracts/world-genesis.v1.schema.json` | new | `world-genesis.v1`, 1.0.0 | full replayable genesis |
| `docs/contracts/map-presentation.v1.schema.json` | new | `map-presentation.v1`, 1.0.0 | filtered visual mapping |
| `docs/contracts/ruleset.v2.yaml` | new | `ruleset.v2`, 2.0.0 | exit conditions and route-weight semantics for generated worlds |
| `docs/contracts/api.openapi.yaml` | upgrade | `1.1.0` → `2.0.0` | `GET /v1/world/snapshot` becomes `oneOf` v1/v2; add `GET /v1/world/presentation` |
| `docs/contracts/world-snapshot.v1.schema.json` | frozen | 1.0.0 | compatibility baseline |
| `docs/contracts/ruleset.v1.yaml` | frozen | 1.0.0 | canonical behavior |
| `world-command.v1`, `world-event.v1`, `npc-observation.v1`, `action-proposal.v1` | unchanged | 1.0.0 | no new commands/events/observation fields |

API 2.0.0 is intentional: widening an existing operation's response to a union is a major contract change. Canonical worlds still return exactly v1; generated worlds require a v2-aware client. Existing `/v1` paths remain. This must not be presented as an additive minor change.

## 8. Migration and replay

### 8.1 Database migration

Proposed migration `0005_world_generation` (number follows the actual current head; do not renumber existing migrations):

- `world_state`: add nullable `generation_mode` (backfill `canonical`), `generator_version`, `map_spec_digest`, `genesis_digest`. Do not rewrite `state` or `checksum`.
- `world_snapshot`: add `checksum_version` (backfill `1`), `generation_mode`, `generator_version`, `map_spec_digest`, `genesis_digest`. Existing snapshots remain v1.
- New immutable `world_genesis` table: `world_id` PK/FK, mode, seed, generator_version, ruleset_version, map_spec JSONB, initial_state JSONB, initial_events JSONB, map_spec_digest, initial_state_checksum, genesis_digest, created_at. No updates; a new world gets a new row.
- `save`, `world_event`, `event_edge`, `command_log`, `memory_episode` need no shape change. A v1 save continues to reference a v1 snapshot.
- Generated rows must satisfy a check: mode `generated` implies non-null generator/map/genesis digests; canonical rows imply null generated metadata.
- Rollback drops the new table/columns only; v1 state/checksum/saves are untouched.

### 8.2 Bootstrap

- Default `WORLD_GENERATION_MODE=canonical`, `WORLD_SEED=42`. Empty DB + canonical calls the existing `create_world(seed)` exactly.
- Empty DB + generated calls `create_world_generated(seed)` with `mapgen.v1`; it writes `world_genesis` before/with the world row and writes the initial events.
- Existing DB: the persisted mode wins. If env mode differs, fail closed with `world_generation_mismatch`. No auto-reset, no regeneration, no silent conversion.
- Generated mode is not selected by seed alone. Seed 42 in generated mode goes through the same generator as 7 and 2026.

### 8.3 Replay from full genesis

1. Read `world_genesis`; verify `map_spec_digest`, `initial_state_checksum` and `genesis_digest`.
2. Restore `initial_state` as `world-state.v2`; verify its v2 checksum with the stored generation metadata.
3. Load `initial_events` into the event table unchanged. Do not call `mapgen` again.
4. Apply accepted entries from `command_log` in `state_version` order (or re-apply the event stream only if a command log is unavailable, with an explicit warning).
5. Compare the final state checksum, `state_version` and `last_event_id` with the record. A mismatch is a hard failure, not a fallback to “regenerate from seed”.
6. For a save, restore the v2 snapshot, apply commands after its `state_version`, and compare. Missing `world_genesis` for a v2 world fails closed.

### 8.4 Compatibility tests

- `create_world(42)` state dump, `world_id`, checksum and golden remain byte-identical.
- Existing v1 snapshot fixture restores and accepts commands; old save/load checksums unchanged.
- Generated seed 42 has a different `world_id` and v2 checksum than canonical seed 42.
- Same seed + same mode + same command stream = same v2 checksum; different mode never does.
- Generated v2 save/load preserves generation metadata and genesis digest.
- No test edits the old golden, and no test special-cases `seed == 42` inside the generator.

## 9. Three-seed acceptance matrix

Signatures are computed over **canonicalized content**, excluding raw IDs, visual coordinates, colors and mesh paths. A change of IDs/coords alone must not make two seeds pass as different.

| Case | Mode | Seed | Route signature | Resource/opportunity signature | Risk/gate signature | Core contention | Realm gate | Checksum |
|---|---|---|---|---|---|---|---|---|
| C-42 | canonical | 42 | legacy, frozen | legacy, frozen | legacy, frozen | existing golden behavior | existing golden behavior | exactly old v1 golden |
| G-42 | generated | 42 | R42 | S42 | X42 | 3 contenders reachable; player can intervene | locked → opened with item | v2; differs from C-42 |
| G-7 | generated | 7 | R7 | S7 | X7 | 3 contenders reachable; player can intervene | locked → opened with item | v2 |
| G-2026 | generated | 2026 | R2026 | S2026 | X2026 | 3 contenders reachable; player can intervene | locked → opened with item | v2 |

Required assertions:

- `R42`, `R7`, `R2026` are pairwise different. At least one exit, cost or condition differs in a way that changes the legal route, not just the label.
- `S42`, `S7`, `S2026` are pairwise different: map-fragment source, pill location/owner, and opportunity location/requirement tuple must not be identical across the three.
- `X42`, `X7`, `X2026` are pairwise different: guard, gate condition or deadline must differ; each declaration must be realized by a real NPC goal/gate/deadline.
- Each generated seed has a legal command path from `player_spawn` to the core opportunity; without the gate item, `enter_secret_realm` is rejected with `realm_undiscovered`; after obtaining it, `SECRET_REALM_DISCOVERED` → `SECRET_REALM_ENTERED` → `OPPORTUNITY_CLAIMED` occurs with real causal parent ids.
- The three contenders (沈砚/裴烈/苏芷) can reach the contested site through their real goals; the player can reach and issue an intervention command before the claim. This must not use `_stage_contenders` mutation.
- Each generated seed’s presentation has one node per known location, no hidden resource/realm IDs, and a matching `map_spec_digest`; every server-legal exit has a navmesh/collision path.
- Same seed same mode replay is exact; G-42 ≠ C-42 in world ID and checksum; generated seeds differ from each other.

## 10. Validation commands (to run by Codex after implementation)

These commands are acceptance after M1/M2. They are **not run in this planning round**, and `tools.map_audit` is a proposed acceptance tool, not an existing command.

```bash
# Contracts and canonical compatibility
uv run pytest tests/contract -q
uv run pytest tests/e2e/test_replay.py tests/e2e/test_save_load_year_ten.py -q
uv run python -m tools.ending_report --days 365 --seed 42

# Three-seed content matrix, legal arrival events, gate rejection/allowance
uv run pytest tests/e2e/test_map_generation_matrix.py -q
uv run pytest tests/e2e/test_map_reachability.py -q

# Hidden-information leakage: presentation, observation, prompts, errors
uv run pytest tests/e2e/test_map_leakage.py -q

# Machine-readable audit for each generated seed (proposed CLI)
uv run python -m tools.map_audit --mode generated --seed 42 --json
uv run python -m tools.map_audit --mode generated --seed 7 --json
uv run python -m tools.map_audit --mode generated --seed 2026 --json
```

`tools.map_audit` must report at least: `route_signature`, `resource_opportunity_signature`, `risk_signature`, `paths`, `arrival_events` (including `NPC_MOVED`, `SECRET_REALM_DISCOVERED`, `SECRET_REALM_ENTERED`, `OPPORTUNITY_CLAIMED`), `gate.denied_code`, `gate.allowed_event`, `checksum_version`, `checksum`, `world_id`, and a leakage check list. The tests assert the JSON; `jq` is not required.

## 11. Godot visual, collision and navigation constraints

- Only `clients/godot/` is in scope. `clients/godot-art/` and all art assets remain untouched. M1 uses placeholder pads and primitive collision.
- The presentation loader validates `world_id` and `map_spec_digest` against the current snapshot before using any coordinates. Mismatch = diagnostic/placeholder, never a locally invented map.
- At most 8 location pads, one connected navmesh region per known area, a capsule player, no jump/fly/swim, no streaming or open world.
- Collision is limited to simple static primitives and one ground pad per location. An exit is an `Area3D` trigger that submits `move` with `expected_state_version`; it never mutates state or teleports.
- For every server-legal exit, a navmesh path must exist between the location anchors. If collision/navigation blocks a legal server route, the presentation fails acceptance; server topology is not changed to fit the visual.
- Hidden interiors/items are not present in the presentation or scene tree until discovered; they are spawned from authoritative snapshot visibility, not from MapSpec.
- No authoritative code reads presentation coordinates, model names, colors or collision data. No visual shortcut may create an exit or resource.

## 12. Knowledge and leakage boundary

- The generator and MapSpec are server-side. LLM prompts and `NpcObservation` continue to be built only from filtered `WorldState`; MapSpec is never pasted into a prompt.
- A generated NPC only knows locations/items/beliefs granted by its observation and initial state. Generation must not populate every NPC with the whole map.
- Public presentation returns only known/public locations; hidden resources, hidden item IDs, secret interiors and gate condition details are absent before discovery.
- Errors and logs must not echo raw MapSpec or hidden IDs. Tests search presentation, observations, prompts and error bodies for canary hidden IDs.
- The full genesis export is a local operator action and is not exposed through the unauthenticated public API.

## 13. MVP scope and non-goals

**In scope:** 8 locations, fixed 30-NPC roster, one core opportunity, at most two auxiliary resources, one secret realm, one or two gates/risks, one generated world per database, canonical and generated modes, seed variants 42/7/2026, filtered presentation, replay and compatibility.

**Out of scope:** infinite/open world, procedural NPCs/factions/items, new event or command types, new art, editor tooling, multi-world browsing, auth/multi-user, real model calls, cloud fallback, changing canonical golden tests, converting existing canonical worlds to generated.

## 14. Unresolved points

1. Exact generator distribution and balance (which edge/gate/resource combinations are fun and fair) is not fixed here; the RFC fixes constraints and acceptance signatures, not authored content.
2. `travel_cost` is a route weight in M1, not a time charge. True per-move tick cost would require a new command/ruleset and is deliberately excluded; reviewers must accept this MVP limitation or request a follow-up RFC.
3. Presentation asset library, collision fidelity, navmesh baking quality and manual visual QA remain placeholders; tests can prove linkage and non-leakage, not visual quality.
4. Full-genesis export authentication and operational access are not designed; the artifact is local/offline for MVP. Multi-user/multi-world access is unresolved.
5. Generated `ruleset.v2` balance and its interaction with existing agent policies need review; T2 policy work is separate from this RFC.
6. API 2.0.0 requires generated clients to understand snapshot v2. Canonical v1 clients remain compatible, but the migration plan for a client that must talk to both modes is not implemented here.
7. Existing canonical databases are not backfilled with genesis and cannot be converted in place. Generated mode requires a new empty database/world and explicit operator action.

## 15. Approval requested

Approve, reject or amend:

- the seven contract changes and exact versions in section 7;
- the frozen canonical v1 boundary and distinct generated v2 checksum/world ID;
- the full-genesis persistence and replay model;
- the MapSpec/presentation split and the public filtering rule;
- the M1 route-weight limitation for `travel_cost`;
- the 3-seed acceptance matrix and API 2.0.0.

No implementation, migration, contract edit or test weakening should begin before this approval and Codex review.
