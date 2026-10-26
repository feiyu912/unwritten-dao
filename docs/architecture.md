# Architecture

## Invariants

1. `world_core` is the only authority. It is a pure Python library: no network, no database,
   no GPU imports.
2. Every state change enters through a typed `WorldCommand` and exits as one or more immutable
   `WorldEvent`s. LLMs and clients submit commands; they never mutate state.
3. Time advances in integer ticks (one tick = one in-world day). Randomness is derived from
   `(world_seed, tick, event_id, purpose, entity)` with BLAKE2b, never from process-global RNG.
4. Numeric state that affects outcomes is rounded to fixed precision before persistence so
   macOS and Linux produce identical checksums.
5. Replay uses the recorded command stream, not new model samples. LLM outputs are fixtures.

## Layering

```text
UE5 client / tools
      |
      v
world_server (HTTP + WS, PostgreSQL, snapshots, idempotency)
      |
      +--> agent_runtime (observation -> ActionProposal -> validation)
      |
      v
world_core (state, rules, tick clock, events, checksum)
```

Dependency direction is one-way: `world_core` knows nothing about FastAPI, SQL, agents, or
Unreal. `agent_runtime` reads core models but never imports the server. Both server and tools
compose them.

## Simulation loop (headless)

```text
while tick < end:
    for each idle NPC in stable id order:
        observation = build_observation(state, npc)
        proposal    = policy.decide(observation)
        command     = validate_and_convert(proposal, state)
        engine.apply_command(state, command)
    engine.apply_command(state, advance_time(ticks=1))
```

Agents that are mid-action (cultivation) are not asked for decisions. Background NPCs use the
same loop with a cheaper policy, so the authority path is identical.

## Tick processing

`advance_time` is itself a command. Each tick it:

- applies daily cultivation gains to NPCs with an active cultivation action;
- completes actions and emits aggregated events (never one event per qi point);
- regenerates health slowly and checks natural lifespan;
- settles faction economy every 30 days;
- closes expired secret realms and opportunities.

## Persistence

`world_server` stores commands (idempotency), events (append-only, with causal edges), and
checksummed snapshots. A database transaction commits state version, events, and snapshot
pointer together. Loading a save restores the snapshot and resumes from its `state_version`.

## Determinism and replay

- `state_checksum(state)` canonicalizes JSON with sorted keys and no NaN.
- Replay verifies: same initial seed + same command stream => same final checksum.
- External proposals are recorded with prompt/model/version/response. Replay mode refuses to
  call a model provider.
- Cross-platform CI compares macOS ARM64 and Linux x86_64 checksums for `seed=42`.

## MVP boundaries

In scope: 30 persistent NPCs, two factions, one region, one secret realm, 20 simulated years,
one player, 6 major agent slots, command/event API, snapshots, causal queries.

Out of scope: networking multiplayer, neural rendering, large continents, real-time action
combat, self-trained foundation models. Interfaces are still kept replaceable:
`AgentPolicy` and `InferenceProvider` are protocols.