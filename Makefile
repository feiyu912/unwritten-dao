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
