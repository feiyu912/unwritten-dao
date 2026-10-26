# world_core public API (R1)

This is the frozen interface every module codes against. Contract schemas in `docs/contracts/`
override this document if they disagree.

## Types and IDs

- All Pydantic models live in `world_core.models`, use `extra="forbid"`, and serialize with
  `model_dump(mode="json")`.
- NPC / faction / world IDs are UUID strings generated with `uuid.uuid5`. Helper:
  `stable_id(kind: str, key: str) -> str`.
- Location, item, opportunity, realm IDs are stable human-readable strings (e.g.
  `location_stone_town`, `item_map_fragment`).
- Locked IDs exported from `world_core.worldgen`:
  `WORLD_ID` (seed-dependent), `PLAYER_ID`, `PROTAGONIST_ID`, `FACTION_XUANYUE`,
  `FACTION_CHIXIAO`, `LOC_STONE_TOWN`, `LOC_XUANYUE_SECT`, `LOC_BLACKWOOD_FOREST`,
  `LOC_RUINED_TEMPLE`, `LOC_MISTY_VALLEY`, `LOC_ANCIENT_CAVE`, `LOC_CHIXIAO_OUTPOST`,
  `LOC_BLACK_MARKET`, `ITEM_MAP_FRAGMENT`, `ITEM_FOUNDATION_PILL`, `REALM_ANCIENT_CAVE`,
  `OPP_FOUNDATION_PILL`.
- `world_id(seed: int) -> str` is deterministic.

## State models (`world_core.models`)

Common fields use snake_case. Numeric floats that can drift are rounded to 6 decimals.

```text
WorldState:
  world_id: str, world_seed: int, tick: int, state_version: int, last_event_id: int,
  sim_version: str, ruleset_version: str, player_id: str,
  npcs: dict[str, Npc], locations: dict[str, Location], factions: dict[str, Faction],
  items: dict[str, Item], opportunities: dict[str, Opportunity],
  secret_realms: dict[str, SecretRealm],
  relationships: dict[str, Relationship],   # key = f"{source}|{target}"
  beliefs: dict[str, Belief],              # key = f"{npc}|{subject}|{predicate}"

Npc:
  npc_id, name, canonical_role, faction_id: str|None, alive: bool,
  birth_tick: int (may be negative), lifespan_ticks: int,
  realm: int, stage: int, qi: int, foundation: float, health: float, wealth: int,
  aptitude: float, luck: float, technique: str, location_id: str,
  traits: dict[str, float], goals: list[Goal], active_action: ActiveAction|None,
  known_locations: list[str], inventory: list[str],
  death_tick: int|None, death_cause: str|None

Goal:
  goal_id, kind, status ("active"|"achieved"|"failed"|"abandoned"), priority: float,
  params: dict, created_tick: int

ActiveAction:
  type ("cultivate"|"wait"), started_tick, remaining_ticks, total_ticks, payload: dict

Location:
  location_id, name, kind ("town"|"sect"|"outpost"|"wilderness"|"ruin"|"shop"|"secret_realm"),
  faction_id: str|None, aura_multiplier: float, adjacency: list[str], stash: list[str]

Faction:
  faction_id, name, kind ("sect"|"clan"), leader_id: str|None,
  treasury: int, income_per_30d: int, upkeep_per_member: int

Item:
  item_id, name, kind, unique: bool, owner_id: str|None,
  location_id: str|None, hidden: bool, properties: dict

Opportunity:
  opportunity_id, name, kind, location_id, reward_item_ids: list[str],
  active_from_tick, active_until_tick, claimed_by: str|None, claimed_tick: int|None,
  expired: bool, base_weight: float, min_realm: int,
  canonical_candidate_id: str|None, canonical_luck_bias: float,
  requires_map_item_id: str|None, attempts: int

SecretRealm:
  realm_id, name, entrance_location_id, interior_location_id,
  required_item_id: str|None, open_tick, close_tick, opened: bool,
  discovered_by: list[str]

Relationship:
  source_npc_id, target_npc_id, affinity, trust, fear, respect, debt,
  last_event_id: int|None

Belief:
  npc_id, subject_key, predicate, object_value (Any), confidence: float,
  source_event_id: int|None, acquired_tick: int

WorldCommand: canonical command contract plus typed helpers.
WorldEvent: canonical event contract.
CommandResult: accepted: bool, state_version: int, events: list[WorldEvent]
```

## Functions (`world_core`)

```python
create_world(seed: int = 42) -> WorldState
make_command(state, actor_id, type, arguments, *, source, idempotency_key=None,
             command_id=None) -> WorldCommand
apply_command(state: WorldState, command: WorldCommand) -> CommandResult
advance_time(state, ticks: int, *, source="system") -> CommandResult  # convenience
state_checksum(state: WorldState) -> str                               # "sha256:<hex>"
snapshot(state: WorldState) -> dict                                    # world-snapshot.v1
restore_snapshot(doc: dict) -> WorldState                              # verifies checksum
validate_state(state: WorldState) -> list[str]                         # empty == valid
RULESET: Ruleset                                                        # parsed ruleset.v1.yaml
```

`apply_command` rejects with `CommandRejected(code, message, details)` when:
unknown world, stale `expected_state_version`, `issued_tick != state.tick`, dead actor,
unknown IDs, illegal transition, or contract-shaped arguments are wrong.

## Tick rules

- One tick = one day; 365 ticks/year; 20 years = 7300 ticks.
- Only `advance_time` moves the clock. Commands from agents execute at the current tick.
- Each accepted command increments `state_version` exactly once. Each event gets the next
  `event_id` and `state_version_after = new version`.
- `advance_time` processes each day: cultivation gains, action completion, health regen
  (0.002/day up to 1.0), natural death when age exceeds lifespan, faction economy every 30
  days, realm/opportunity expiry. Emits `WORLD_ADVANCED` once with from/to ticks.
- Cultivation gain uses the ruleset formula and integer truncation. Stage-ups are automatic;
  realm breakthroughs require `attempt_breakthrough`.
- Death: `alive=False`, `health=0`, active action cleared, `NPC_DIED` emitted, no further
  actions accepted for that NPC.

## Determinism

- RNG: `seed_for(state, purpose, *parts) -> int` using BLAKE2b over a canonical string; use
  `random.Random(seed)` locally. Never use global `random`.
- Logistic probabilities are rounded to 6 decimals before comparing with the roll.
- `state_checksum` hashes canonical JSON (`sort_keys=True`, compact separators, UTF-8).
- `restore_snapshot` must reproduce a byte-identical checksum.

## Canonical past events

`create_world` assigns contiguous belief provenance ids and emits `BELIEF_ACQUIRED`
events at tick 0 (ids 1..N) via `genesis_events(state)`. The server bootstrap persists them;
they have no command and `state_version_after=1`. Later actions may cite these ids as true
causes (e.g. a transfer motivated by a rumor). New worlds start with `last_event_id=N`.

## Seed world (seed=42)

30 NPCs: player `谢无咎`, protagonist `沈砚`, 4 other major (sect leaders 陆玄机 / 霍燃,
elder 苏芷, rival 裴烈), 10 minor, 14 background. All original names.

Locations (symmetric adjacency):
`stone_town` ↔ `xuanyue_sect`, `xuanyue_sect` ↔ `blackwood_forest`,
`blackwood_forest` ↔ `ruined_temple`, `ruined_temple` ↔ `misty_valley`,
`misty_valley` ↔ `ancient_cave` (interior only reachable when realm is discovered/open),
`stone_town` ↔ `black_market`, `blackwood_forest` ↔ `chixiao_outpost`.

Scenario facts:
- `item_map_fragment` starts in `ruined_temple` stash, unowned, visible.
- Its properties include `{"points_to": "misty_valley", "realm_id": "realm_ancient_cave"}`.
- `realm_ancient_cave` opens at tick 0, closes at tick 5475 (year 15), requires the map.
- `opp_foundation_pill` is inside `ancient_cave`, reward `item_foundation_pill`, canonical
  candidate `PROTAGONIST_ID`, luck bias 1.7, active until year 15.
- Protagonist starts in the sect with a belief that `ruined_temple` holds an ancient relic,
  goal `goal_breakthrough`, stage at the cap of realm 1, and no map.
- Player starts in `stone_town`, realm 1 stage 1, no faction.

## Out of scope for the core

No SQL, HTTP, LLM calls, prompts, memory embeddings, narrative text generation, or UE5.
Those live in other modules and consume this API.