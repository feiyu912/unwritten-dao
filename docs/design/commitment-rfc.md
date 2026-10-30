# RFC: world-authoritative commitments for one NPC

Status: requested by the user as the P0 voice-demo prerequisite. The additive
contract change is published in `docs/contracts/api.openapi.yaml` version
`1.2.0`; this RFC records its scope and rationale for review.

## Purpose and scope

Let an NPC make a bounded, persistent promise to another present NPC and let
the simulator — not the language model — decide whether that promise is
recorded, deferred, fulfilled or broken. The first supported commitment is
"delay a personal goal and investigate an agreed location together". It exists
so a player's free conversation can change an NPC's later behaviour and be
observed in the event log, without inventing a debt economy or a second
dialogue system.

Model output remains an `ActionProposal`. A commitment only exists after the
validated `make_commitment` command is applied by `world_core`.

## Contract changes

| Shape | Change |
| --- | --- |
| `world-command.v1` | new command type `make_commitment` with `commitmentArgs` |
| `action-proposal.v1` | new intent `make_commitment` |
| `world-event.v1` | new event types `COMMITMENT_MADE`, `COMMITMENT_FULFILLED`, `COMMITMENT_BROKEN` |
| `api.openapi.yaml` | info version `1.1.0` → `1.2.0`; URL prefix stays `/v1` |

`make_commitment` arguments:

```json
{
  "with_npc_id": "uuid of the other present NPC",
  "promised_goal_id": "active goal of the actor",
  "target_location_id": "known location to investigate",
  "until_ticks": 1,
  "terms": "1..200 characters"
}
```

## Authoritative semantics

- Both NPCs must be alive and at the same location; the actor must be idle.
- `promised_goal_id` must name an active goal of the actor and
  `target_location_id` must be known to the actor.
- Applying the command appends a `commitment` goal (origin = the emitted
  `COMMITMENT_MADE` event) and sets `deferred_until_tick` and `commitment_id`
  on the promised goal. No new top-level state field is introduced.
- While `deferred_until_tick > tick`, an `attack` by the actor against that
  goal's target is rejected with `commitment_deferred`. The promise is
  therefore enforced by the simulator, not by prompt compliance.
- Investigating the agreed location fulfils the commitment: the commitment
  goal becomes `achieved`, the deferral is cleared, and
  `COMMITMENT_FULFILLED` cites both the promise event and the investigation.
- Advancing past `until_tick` without fulfilment marks the commitment `failed`,
  clears the deferral and emits `COMMITMENT_BROKEN`.
- Every transition is deterministic: sorted NPC/goal iteration, stable ids,
  seeded RNG and event parents. Replaying the same command stream reproduces
  the same events and checksum.

## Non-goals

- No debt, currency, reputation ledger or multi-party contracts.
- No new dialogue route: the existing `/v1/dialogue` returns the proposal and
  the client submits it through `/v1/commands`.
- Speech routes remain media-only and do not create commitments.
