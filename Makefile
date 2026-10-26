UV ?= uv

.PHONY: sync test lint bench db-up db-down

sync:
	$(UV) sync --all-packages

test:
	$(UV) run pytest -m "not integration and not slow" -q

lint:
	$(UV) run ruff check .

bench:
	$(UV) run python -m tools.bench_sim --npcs 30 --years 20 --seed 42 --agent-mode rules

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

demo:
	uv run python -m tools.demo_causal --days 400

bench-db:
	uv run python -m tools.bench_db --reset --years 20

report:
	uv run python -m tools.narrative_report --years 20 --seed 42

history:
	uv run python -m tools.character_history --npc 沈砚 --years 20

dashboard:
	uv run python -m tools.export_dashboard --years 20

replay-decisions:
	uv run python -m tools.replay_decisions --days 30

bench-memory:
	uv run python -m tools.bench_memory --events 100000 --queries 1000 --top-k 5 --rebuild-index
