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
| Stolen-map causal intervention | `tests/e2e/test_causal_intervention.py` + `make demo`; baseline discovers the realm, intervention never does | verified |
| 100k-event invariants | `tests/e2e/test_event_stress.py` (slow): **1.18 s**, 84.6k events/s, invariants hold | verified |
| Snapshot / save-load | core round-trip + server time-travel test; replay checksum identical | verified |
| PostgreSQL persistence | 22 integration tests against real pgvector PostgreSQL 17 | verified |
| Idempotency & concurrency | duplicate key returns stored result; stale version → 409; command_id reuse → 409 | verified |
| Event log + causal query | `event_edge` persisted; `/v1/debug/causality/{id}` BFS | verified |
| Agent tiering | 6 major roles use the LLM path; others stay on UtilityPolicy | verified |
| LLM proposal pipeline | strict JSON parsing, identity binding, one repair, audit rows, replay mode | verified with mock |
| Episodic memory | events → `memory_episode` in the command transaction; top-5 retrieval into prompt | verified |
| Memory recall gate | labeled Recall@5 = 10/10 in `tests/e2e/test_memory_recall.py` | verified (small set) |
| Dialogue | mock/OpenAI-compatible modes; deterministic fallback; no hidden facts | verified with mock |
| Playable headless demo | `uv run python -m tools.play`; scripted smoke test traverses map → realm → pill | verified |
| CI | run `40282504317`: macOS ARM64, Ubuntu x86_64, PostgreSQL integration all green | verified |
| Static gates | `ruff check .` clean; `mypy` clean on 32 source files | verified |

Test totals: **71 fast + 22 integration + 1 slow** (the slow 100k-event test is run manually and
excluded from the fast suite).

## Not verified (requires other hardware or services)

1. **UE5 client** — C++ scaffold, docs, and a tested headless mock exist, but the project has not
   been compiled, opened in the editor, packaged, or measured for FPS/1% low. No Unreal install
   on this machine.
2. **Real model latency/quality** — the OpenAI-compatible path is unit-tested with a mock
   transport; no live endpoint was called. TTFT, cost, and dialogue quality targets are unmeasured.
3. **Embedding-based memory** — `memory_episode.embedding` and pgvector exist, but retrieval is
   deterministic lexical scoring; no embedding provider has been exercised.
4. **Narrative quality** — no human ratings for coherence/surprise/causal plausibility.
5. **Causal coverage / goal persistence metrics** — not instrumented. Causal edges cover direct
   parent chains (e.g. investigate → discover → breakthrough); the map transfer is not an edge of
   the discovery event, only an earlier event in the log.
6. **Database size under 20 years** — the 20-year benchmark runs in memory; no sustained
   repository-driven 20-year run or 1 GB database measurement.
7. **Multi-user / auth / process recovery** — single world, single process, no authentication.

## Next R3 work

- Compile and validate the UE5 client on the GPU workstation; measure 1080p FPS and 1% low with
  and without the local model running.
- Connect a real provider (cloud or llama.cpp) and record TTFT/cost; replay its fixtures.
- Add embeddings behind the existing `MemoryStore` interface and evaluate Recall@5 on a labeled
  set from real 20-year histories.
- Instrument causal coverage and goal persistence over 20 years.
- Drive the 20-year history through PostgreSQL and record database size and query latency.