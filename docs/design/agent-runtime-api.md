# agent_runtime public API (R1)

`agent_runtime` turns authoritative state into *proposals*. It never mutates `WorldState`.
It depends on `world_core`; no SQL, HTTP server, or UE5 imports. Pydantic models mirror the
contracts in `docs/contracts/`.

## Models (`agent_runtime.models`)

- `NpcObservation` — exactly `npc-observation.v1.schema.json`.
- `ActionProposal` — exactly `action-proposal.v1.schema.json`.
- `AgentPolicy` Protocol: `decide(self, observation: NpcObservation) -> ActionProposal`.
- `InferenceProvider` Protocol: `complete(self, *, system: str, user: str) -> str`.
  Providers are injected; replay mode must refuse network calls.

## Functions

```python
build_observation(
    state: WorldState,
    npc_id: str,
    *,
    memories: Sequence[dict] = (),
    recent_events: Sequence[dict] = (),
) -> NpcObservation
```
- `self` from the NPC; `inventory` from owned items; `visible_items` from the current
  location stash, excluding `hidden` items; `visible_opportunities` for unclaimed, unexpired
  opportunities at the current location; `visible_npcs` from living NPCs at the same
  location (public fields only).
- `relationships` are outgoing edges from this NPC. `beliefs` are only this NPC's beliefs.
  `known_locations` must never include locations the NPC does not know, and must never leak
  the secret interior before discovery.
- `memories` / `recent_events` are passed in by the caller (the server owns the event log);
  the builder does not invent history.
- `available_actions` lists the command intents legal for this NPC now (at minimum all
  contract intents that could be valid; the simulator re-validates).

```python
class UtilityPolicy:
    def decide(self, observation: NpcObservation) -> ActionProposal
```

```python
proposal_to_command(state: WorldState, proposal: ActionProposal) -> WorldCommand
```
- Reject stale proposals (`observed_world_version != state.state_version`), wrong NPC, or
  intents not in the observation's `available_actions` with `ProposalRejected(code, message)`.
- Convert intent + arguments into a `world-command.v1` command with `source="agent"` and a
  deterministic idempotency key. The simulator performs final legality checks.

```python
decide_command(
    state: WorldState,
    npc_id: str,
    policy: AgentPolicy,
    *,
    fallback: AgentPolicy | None = None,
    memories: Sequence[dict] = (),
    recent_events: Sequence[dict] = (),
) -> WorldCommand | None
```
- Return `None` when the NPC is dead or already has an active action; the caller skips it.
- Build observation, call policy, validate. On `ProposalRejected`, call one fallback
  (`UtilityPolicy` by default) exactly once; if that also fails, raise.
- Never call a provider directly; `LLMPolicy` composes an `InferenceProvider`.

```python
decide_and_apply(state, npc_id, policy, *, fallback=None, memories=(), recent_events=())
    -> CommandResult | None
```
- Full safety chain: validate the proposal, apply through the simulator, and if the
  simulator rejects it (impossible plan), call the deterministic UtilityPolicy exactly once
  and apply that. Raises if the fallback is also rejected.

## UtilityPolicy behavior (R1)

Deterministic, no randomness. Stable key order. For an NPC whose active goal is
`breakthrough` (the protagonist path):

1. owns `foundation_pill` and is at realm stage cap → `attempt_breakthrough` with the pill;
2. inside the secret realm and the pill opportunity is unclaimed → `claim_opportunity`;
3. at the realm entrance with the realm discovered → `move` into the interior;
4. at the realm entrance and owns the map → `investigate` the entrance;
5. owns the map and knows the interior location → move one step toward the entrance;
6. at the map's marked location and a map item is visible → transfer it to self;
7. knows the marked location → move one step toward it;
8. otherwise cultivate at the current location (30-day action), or move one step toward the
   nearest sect if aura is poor.

Other NPCs: cultivate at their current location in 30-day blocks; leaders/deacons stay put.
The policy receives everything it needs from the observation; it must not import
`worldgen` constants to cheat. Item semantics may be read from item `kind` and `properties`
(e.g. `points_to`), not from hidden state.

## DecisionModelPolicy (pluggable scoring, no training)

`DecisionModelPolicy` selects tactical actions from generated candidates using a
`DecisionModel` protocol (`score(observation, candidates)` + `value(observation)`). It records, per
decision: the observation dump, strategic goal, candidates with legal mask and scores, chosen
action, value estimate, and cited event ids (`PolicyDecisionRecord`). Illegal candidates are
masked; all-illegal/model-error cases fall back to `UtilityPolicy` once. It never mutates state.
`UtilityCandidateGenerator` is the baseline candidate source; `UtilityScoringModel` is a
reference scorer that selects the utility candidate and exists to exercise the interface before a
trained action scorer exists. Future BC/RL models implement the same protocol without changing
policies or the simulator. `tools.collect_decisions --policy decision-model` records this path.

## Decision dataset

`DecisionRecorder` + `RecordingPolicy` wrap any policy and produce `DecisionSample` rows:
public observation, goals, available actions, chosen proposal, rationale/confidence, cited event
ids, simulator outcome, rejection code, and resulting event ids. `tools.collect_decisions` writes
JSONL for future BC / action scoring / RL. The available-actions list is a coarse mask; the
simulator outcome is the authoritative legality label.

## Knowledge boundary

`NpcKnowledgeView` separates authoritative facts, private state, fallible beliefs, and memories;
`redact_unknown` removes ids the NPC does not know; `validate_boundary` checks secret interiors and
hidden items. `explain_action` and `explain_event_chain` cite only real goals, memories, and
causal parent ids.

## RivalryPolicy

`RivalryPolicy` extends `UtilityPolicy`: if an active `defeat_rival` goal's target is visible
and the actor is healthy, it proposes `attack` with intent `subdue` (never lethal by choice).
Otherwise it falls back to normal utility behavior. The server's utility mode uses it for the
six major roles; background NPCs stay on `UtilityPolicy`.

## Fallback

`UtilityPolicy` is the deterministic fallback. Any proposal that fails validation triggers at
most one fallback attempt; the outcome is either a legal command or an exception. Never retry
the LLM repeatedly.

## Tests (`packages/agent_runtime/tests/`)

- Observation validates against `npc-observation.v1.schema.json`; hidden items and secret
  interiors are absent until discovered.
- Utility policy drives the protagonist from the sect to the map, the realm, the pill, and a
  breakthrough attempt within 400 simulated days (using `world_core.apply_command` and
  `advance_time`).
- A policy returning a stale/wrong-NPC proposal gets exactly one fallback command.
- `MockInferenceProvider` is deterministic and records its calls; `ReplayInferenceProvider`
  raises on provider access and returns recorded fixtures.
- No test performs network I/O.