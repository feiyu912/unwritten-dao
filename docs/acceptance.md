# MVP acceptance report

Status date: 2026-10-26. This maps the plan's acceptance table (section 6.1) to evidence in
this repository. `PASS` means a test or command was run and its output observed; `PARTIAL`
means the mechanism is verified but the real model/hardware was not; `NOT RUN` means no
evidence exists yet.

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Deterministic replay 100/100 | PASS | `tests/e2e/test_replay.py` (100 runs, identical checksums) |
| 2 | Save at year 10, load and run to year 20 = uninterrupted | PASS | `tests/e2e/test_save_load_year_ten.py` (checksum + `last_event_id`) |
| 3 | No illegal transition in 100,000+ events | PASS | `tests/e2e/test_event_stress.py` (1.18 s, invariants hold) |
| 4 | Dead NPCs never act | PASS | dead-actor rejection, natural death, combat death tests |
| 5 | Unique items never have two owners | PASS | transfer rejection + `validate_state` invariants |
| 6 | ≥99.5% proposals accepted or safely rejected with fallback | PARTIAL | 20/20 synthetic impossible plans rejected and fallback applied; real LLM rate not measured |
| 7 | Unsupported world facts <1% | NOT RUN | requires a live model and human audit |
| 8 | Memory Recall@5 ≥90% | PARTIAL | 10/10 toy labels and 8/8 real-history labels; real embedding model not measured |
| 9 | ≥95% important events have upstream causes | PASS | 400-day report: 4/4 = 100%; goldens cover chains |
| 10 | ≥80% long-term goals reach resolution or causal replanning | PARTIAL | 1/1 resolved goal achieved; single-goal sample |
| 11 | 30 NPC × 20 years <10 minutes headless | PASS | 0.06 s (rules), 1.9 s (agent loop), 4.15 s (persisted) |
| 12 | 20-year event storage <1 GB | PASS | 21,897 events / 7,042 memories / 19.4 MB (seeded) |
| 13 | 1080p ≥60 FPS / 1% low ≥45 | NOT RUN | no Unreal Engine on the development machine |
| 14 | Model calls never block render | NOT RUN | belongs to the UE5 integration check |
| 15 | Dialogue p95 <6 s | NOT RUN | requires a real provider; mock path only |
| 16 | Local planning TTFT p95 <1.5 s @8K | NOT RUN | requires GPU/local model |
| 17 | No fatal errors/state corruption over 20 years | PASS | 20-year in-memory and persisted runs, invariants clean |

## User-story coverage

| Stage | Status | Evidence |
|---|---|---|
| R0 contracts + skeleton | PASS | `docs/contracts/`, contract tests, OpenAPI route conformance |
| R1 headless causal world | PASS | 30 NPCs, 20 years, map intervention, 100k events |
| R2 memory + LLM agents | PARTIAL | LLM policy, audit, replay, memory, dialogue verified with mock providers; 3D interaction not built |
| R3 playable MVP | PARTIAL | Headless play CLI, history dashboard, HTTP playthrough, save/load, causal queries; UE5 client unvalidated |

## Latest verification (2026-10-26, local + GitHub CI)

- Fast suite, PostgreSQL integration suite, and the 100k-event slow test: all green.
- 20-year rules benchmark: 0.121 s, 569 events, state valid.
- 400-day causal report: coverage 1.0; goals {active: 29, achieved: 1};
  resolved-goal persistence 1.0; no invariant violations.
- 20-year fate test: baseline realm 2 with the map; stolen-map world realm 1,
  no discovery, checksums diverge.
- Persisted 20-year history: 7.69 s, 21,897 events, 7,042 memories, 19.5 MB.
- DB-backed dashboard: rendered from 21,897 persisted events.
- CI run `40293263312`: macOS ARM64, Ubuntu x86_64, PostgreSQL integration all green.

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
