# MVP status — 2026-10-26

This is an evidence-based status report. "Delivered" means tests or commands were actually run;
"not verified" means no evidence exists yet.

## Verified deliverables

| Requirement | Evidence | Status |
|---|---|---|
| Versioned contracts | `docs/contracts/` 5 schemas + ruleset + OpenAPI; contract tests in `tests/contract` | verified |
| Deterministic 30-NPC world | `world_core`; 8 core tests; same seed/commands → identical checksums | verified |
| 20-year headless run | `uv run python -m tools.bench_sim --npcs 30 --years 20 --seed 42` → **0.06 s**, 569 events, state valid | verified |
| 100/100 replay | `tests/e2e/test_replay.py` (100 runs, identical checksums and event counts) | verified |
| Model-proposal replay | record 29 LLM proposals → replay with `ProposalReplayPolicy` and no model; checksum identical | verified |
| Stolen-map causal intervention | 400-day test + **20-year run**: baseline reaches realm 2 and claims the pill; intervention stays realm 1, never discovers the realm, checksums differ | verified |
| 100k-event invariants | `tests/e2e/test_event_stress.py` (slow): **1.18 s**, 84.6k events/s, invariants hold | verified |
| Rule coverage | faction economy, natural and combat deaths clear actions; realm/opportunity expiry directly tested | verified |
| Impossible-plan safety | 20/20 synthetic impossible proposals rejected by the simulator and handled by one Utility fallback; invariants intact | verified (not real LLM) |
| Goal persistence | `report_history` counts goal statuses; resolved-goal persistence **1/1 = 100%** (target ≥80%) | verified (single resolved goal) |
| Snapshot / save-load | core round-trip + server time-travel; **year-10 save → year-20 run matches uninterrupted checksum and event id** | verified |
| 20-year agent history | `tools/narrative_report.py`: **1.9 s**, protagonist reaches realm 2, causal chains + faction outcomes | verified |
| Character life query | `tools/character_history.py --npc 沈砚 --years 20`: full event-ID timeline | verified |
| History dashboard | self-contained HTML (region map, NPC/faction state, causal timeline, story threads); rendered and checked in Chrome | verified |
| DB-backed dashboard | reads 21,897 persisted events from PostgreSQL and renders the same world | verified |
| Story threads | narrative director backtracks real causal parents into ranked multi-event threads; false invention impossible by construction | verified |
| 20-year persisted history | `tools/seed_history.py`: agent-driven, **~4–8 s**, 21,897 events, 7,042 memories, API reloads at tick 7300 | verified |
| Database size target | seeded 20-year agent history: **~19.5 MB** total (< 1 GB) | verified |
| PostgreSQL persistence | 22 integration tests against real pgvector PostgreSQL 17 | verified |
| Idempotency & concurrency | two threads race one version: exactly one writer, one stale; duplicate key returns stored result; command_id reuse → 409 | verified |
| Migration round trip | `alembic downgrade base` then `upgrade head` succeeds; same step runs in CI | verified |
| Event log + causal query | `event_edge` persisted; `/v1/debug/causality/{id}` BFS | verified |
| WebSocket stream | live frame delivery plus resume from an `after` cursor; event pagination matches | verified |
| API contract conformance | every OpenAPI operation implemented; live snapshot/event/observation/decision responses validate JSON Schemas | verified |
| Agent tiering | 6 major roles use the LLM path; otherwise RivalryPolicy (subdue on sight) for majors, UtilityPolicy for background | verified |
| LLM proposal pipeline | strict JSON parsing, identity binding, one repair, audit rows, replay mode; simulator rejection triggers one Utility fallback | verified with mock; real-model legality rate unmeasured |
| Episodic memory | events → `memory_episode` in the command transaction; top-5 retrieval into prompt | verified |
| Memory recall gate | labeled Recall@5 = 10/10 (toy) and 8/8 on a real simulated life | verified (small sets) |
| Dialogue | mock/OpenAI-compatible modes; deterministic fallback; no hidden facts | verified with mock |
| Playable headless demo | `uv run python -m tools.play`; scripted smoke test traverses map → realm → pill | verified |
| Cross-platform determinism | golden 20-year checksum asserted on both macOS ARM64 and Ubuntu x86_64 in CI | verified |
| Cross-process determinism | same benchmark checksum under `PYTHONHASHSEED=0` and `1` | verified |
| CI | macOS ARM64, Ubuntu x86_64, PostgreSQL integration all green | verified |
| Real-process HTTP | uvicorn + httpx: snapshot (30 NPCs), observation (3 memories), decision, dialogue fallback, idempotent 200, stale 409 | verified |
| HTTP playthrough | player-only commands complete map → realm → pill; causality chain and observation memories verified | verified |
| Static gates | `ruff check .` clean; `mypy` clean on 32 source files | verified |

Test totals: **71 fast + 22 integration + 1 slow** (the slow 100k-event test is run manually and
excluded from the fast suite).

## Not verified (requires other hardware or services)

1. **UE5 client** — C++ scaffold, docs, and a tested headless mock exist, but the project has not
   been compiled, opened in the editor, packaged, or measured for FPS/1% low. No Unreal install
   on this machine.
2. **Real model latency/quality** — the OpenAI-compatible path is unit-tested with a mock
   transport; no live endpoint was called. TTFT, cost, and dialogue quality targets are unmeasured.
3. **Semantic memory quality** — pgvector storage, HNSW index, and SQL cosine retrieval are
   exercised with a deterministic hash embedder; no real embedding model was called, so
   semantic Recall@5 is unmeasured.
4. **Narrative quality** — no human ratings for coherence/surprise/causal plausibility.
5. **Causal coverage** — instrumented via `tools/report_history.py`; the 400-day run shows 100%
   coverage on important events, but provenance is "the actor's previous event" (linear).
   Multi-cause links and subjective meaningfulness are not modeled.
6. **Database size** — measured at 19.4 MB for a 20-year agent-driven history (21,897 events).
   A longer or more conflict-heavy history would grow; still far under 1 GB.
7. **Multi-user / auth / process recovery** — single world, single process, no authentication.

## Next R3 work

- Compile and validate the UE5 client on the GPU workstation; measure 1080p FPS and 1% low with
  and without the local model running.
- Connect a real provider (cloud or llama.cpp) and record TTFT/cost; replay its fixtures.
- Add embeddings behind the existing `MemoryStore` interface and evaluate Recall@5 on a labeled
  set from real 20-year histories.
- Extend causal provenance beyond "last actor event" (multi-parent narrative causes) and
  measure goal persistence over 20 years.
- Drive the 20-year history through PostgreSQL and record database size and query latency.