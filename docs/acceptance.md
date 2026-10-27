# MVP acceptance report

Status date: 2026-10-26. This maps the plan's acceptance table (section 6.1) to evidence in
this repository. `PASS` means a test or command was run and its output observed; `PARTIAL`
means the mechanism is verified but the real model/hardware was not; `NOT RUN` means no
evidence exists yet.

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Deterministic replay 100/100 | PASS | `tests/e2e/test_replay.py` (100 runs, identical checksums) |
| 2 | Save at year 10, load and run to year 20 = uninterrupted | PASS | `tests/e2e/test_save_load_year_ten.py` (checksum + `last_event_id`) |
| 3 | No illegal transition in 100,000+ events | PASS (pre-change) | 100k test passed before the parallel state-schema change; not rerun under the lightweight-round constraint |
| 4 | Dead NPCs never act | PASS | dead-actor rejection, natural death, combat death tests |
| 5 | Unique items never have two owners | PASS | transfer rejection + `validate_state` invariants |
| 6 | ≥99.5% proposals accepted or safely rejected with fallback | PARTIAL | 20/20 synthetic impossible plans rejected and fallback applied; real LLM rate not measured |
| 7 | Unsupported world facts <1% | NOT RUN | requires a live model and human audit |
| 8 | Memory Recall@5 ≥90% | PARTIAL | 10/10 toy labels and 8/8 real-history labels; real embedding model not measured |
| 9 | ≥95% important events have upstream causes | PASS | canonical beliefs + true parents: 4/4 = 100% (no fabricated previous-event links) |
| 10 | ≥80% long-term goals reach resolution or causal replanning | PARTIAL | lifecycle rules added (revenge, target death); resolved sample still 1/1 |
| 11 | 30 NPC × 20 years <10 minutes headless | PASS (pre-change) | 0.06 s / 1.9 s / ~4–8 s measured before the provenance change |
| 12 | 20-year event storage <1 GB | PASS (pre-change) | 21,897 events / 7,042 memories / 19.4 MB, measured before the state-schema change |
| 13 | 1080p ≥60 FPS / 1% low ≥45 | NOT RUN | no Unreal Engine on the development machine |
| 14 | Model calls never block render | NOT RUN | belongs to the UE5 integration check |
| 15 | Dialogue p95 <6 s | NOT RUN | requires a real provider; mock path only |
| 16 | Local planning TTFT p95 <1.5 s @8K | NOT RUN | requires GPU/local model |
| 17 | No fatal errors/state corruption over 20 years | PASS (pre-change) | 20-year runs were clean before the state-schema change; rerun pending |

## User-story coverage

| Stage | Status | Evidence |
|---|---|---|
| R0 contracts + skeleton | PASS | `docs/contracts/`, contract tests, OpenAPI route conformance |
| R1 headless causal world | PASS | 30 NPCs, 20 years, map intervention, 100k events |
| R2 memory + LLM agents | PARTIAL | LLM policy, audit, replay, memory, dialogue verified with mock providers; 3D interaction not built |
| R3 playable MVP | PARTIAL | Headless play CLI, history dashboard, HTTP playthrough, save/load, causal queries, traceable ending report; UE5 unvalidated; Godot 4.7 headless snapshot + command verified, editor/FPS not run |

## Latest verification (2026-10-26, after the parallel round)

- Fast suite (decision model, knowledge boundary, UE scene layout, updated golden): green.
- PostgreSQL integration suite: 35 tests green.
- Strict causality: 4/4 = 100% after canonical belief events; transfers cite the motivating rumor.
  The old fabricated previous-event links remain removed.
- Golden checksum updated to `sha256:ef134aa5…` after canonical past + provenance fields.
- UE layout regenerated for the new state checksum (8 locations, 30 NPCs, `sha256:2d739daa…`).
- 20-year persisted numbers in this file predate the state-schema change; the local DB must be
  reseeded with `tools.seed_history` before serving. No long benchmark was rerun in this round
  per the lightweight-verification constraint.

## Latest verification (2026-10-27, Godot headless)

- Godot 4.7.2 `--headless --import` on `clients/godot` completed with no script errors.
- Headless run of `scenes/main.tscn` against a live server: `snapshot tick=365 version=749
  player=… location=location_stone_town npcs=30`.
- `tests/smoke_server.gd` submitted `advance_time` through `WorldClient`; server answered 200,
  `state_version` 749 → 750, and `/v1/health` then reported `tick: 366`.
- Not run: editor session, mouse/keyboard movement, rendering, FPS.

## Latest verification (2026-10-27, decision trajectory summary)

- `tools/collect_decisions --days 10 --policy utility`: 37 samples, 29 NPCs, 37 accepted,
  0 violations.
- `tools.decision_quality` on that JSONL: action diversity 6, goal coverage 1.00,
  `chosen_outside_available=0`, `wait_share=0.00`.
- `tests/e2e/test_decision_quality.py` covers the real collector schema plus rejection and
  invalid-choice accounting.

## Latest verification (2026-10-27, ending report)

- `tools.ending_report --days 365 --seed 42`: `pill_ascension` (沈砚 consumed the foundation
  pill at event 51 and broke through at 52) and `realm_found` (discovered at 45, never entered);
  0 deaths, 0 violations, checksum matches the 1-year demo seed `1cfb3e4b…`.
- Causal contrast (`tests/e2e/test_endings.py`): stealing the map fragment at tick 0 flips the
  same seed/horizon to `pill_dormant` + `realm_sealed`.
- Endings are read-only: `evaluate_endings` leaves the state checksum unchanged, and every
  evidence id is present in the supplied event log.

## How to reproduce the PASS rows

```bash
uv sync --all-packages
docker compose up -d postgres
export DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5433/unwritten_dao
uv run alembic -c services/world_server/alembic.ini upgrade head
uv run pytest packages services tests clients/unreal/tools -m "not integration and not slow"
uv run pytest services/world_server/tests -q
uv run pytest -m slow -q
uv run python -m tools.bench_sim --npcs 30 --years 20 --seed 42
uv run python -m tools.report_history --days 400
uv run python -m tools.seed_history --years 20 --reset
uv run python -m tools.demo_causal --days 7300
```

## Blocking items for the remaining rows

1. **UE5 client**: compile the scaffold, create UMG assets, measure 1080p FPS/1% low with and
   without a local model. No engine is installed on this machine.
2. **Live model**: run `AGENT_PROVIDER=openai` and `EMBEDDING_PROVIDER=openai` against a real
   endpoint, record TTFT, p95 dialogue latency, proposal legality, and unsupported-fact audits.
3. **Human evaluation**: score 20-year histories for coherence, surprise, causal plausibility,
   character consistency, and drama (1–5 scale). Not automatable.

These require resources the current development machine does not have; the code paths and
fixtures are ready for them.
