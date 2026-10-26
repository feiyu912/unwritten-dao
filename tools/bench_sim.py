#!/usr/bin/env python3
"""Headless throughput benchmark for the deterministic ``world_core`` engine.

The tool codes against the frozen API in ``docs/design/world-core-api.md`` and is
expected to be run only after ``packages/world_core`` is merged::

    uv run python -m tools.bench_sim --npcs 30 --years 20 --seed 42 --agent-mode rules

It creates a seed world, starts a 365-day cultivation action for every living
NPC, advances time in chunks, and validates the final state. A non-zero exit
code means the simulation produced an invalid state or could not run.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

TICKS_PER_YEAR = 365
CULTIVATION_DAYS = 365
DEFAULT_CHUNK_DAYS = 365
MAX_CHUNK_DAYS = 3650  # advance_time contract maximum


def _require_world_core() -> Any:
    """Import world_core lazily so the CLI can explain a missing module."""
    try:
        import world_core
    except ImportError as exc:  # pragma: no cover - depends on merge order
        raise SystemExit(
            "world_core is not importable yet; merge packages/world_core before "
            f"running the benchmark (import error: {exc})"
        ) from exc
    return world_core


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark and validate a deterministic world_core simulation.",
    )
    parser.add_argument("--npcs", type=int, default=30, help="expected living NPC count")
    parser.add_argument("--years", type=int, default=20, help="simulated years")
    parser.add_argument("--seed", type=int, default=42, help="world seed")
    parser.add_argument(
        "--agent-mode",
        choices=["rules", "replay"],
        default="rules",
        help="rules: all idle NPCs cultivate; replay: reserved for agent_runtime",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=DEFAULT_CHUNK_DAYS,
        help=f"ticks per advance_time call (1-{MAX_CHUNK_DAYS})",
    )
    return parser.parse_args(argv)


def _apply(
    core: Any,
    state: Any,
    actor_id: str | None,
    command_type: str,
    arguments: dict[str, Any],
    *,
    source: str,
    idempotency_key: str,
) -> Any:
    """Build and apply one command, failing loudly on rejection."""
    command = core.make_command(
        state,
        actor_id,
        command_type,
        arguments,
        source=source,
        idempotency_key=idempotency_key,
    )
    result = core.apply_command(state, command)
    if not getattr(result, "accepted", False):
        raise RuntimeError(f"{command_type} rejected for actor {actor_id}")
    return result


def _start_cultivation(core: Any, state: Any) -> tuple[int, int]:
    """Start a year-long cultivation action for every idle living NPC."""
    started = 0
    events = 0
    for npc_id in sorted(state.npcs):
        npc = state.npcs[npc_id]
        if not npc.alive or npc.active_action is not None:
            continue
        result = _apply(
            core,
            state,
            npc_id,
            "start_cultivation",
            {"days": CULTIVATION_DAYS},
            source="test",
            idempotency_key=f"bench:{state.world_seed}:{npc_id}:cultivate:{state.tick}",
        )
        started += 1
        events += len(result.events)
    return started, events


def _final_violations(
    core: Any, state: Any, target_tick: int, events: int, base_event_id: int
) -> list[str]:
    """Collect invariant violations; an empty list means the run is valid."""
    violations = list(core.validate_state(state))
    if state.tick != target_tick:
        violations.append(f"tick {state.tick} != target {target_tick}")

    for npc_id, npc in sorted(state.npcs.items()):
        if not npc.alive and npc.active_action is not None:
            violations.append(f"dead NPC {npc_id} still has an active action")
        if npc.alive and npc.health <= 0:
            violations.append(f"living NPC {npc_id} has non-positive health")

    owners: dict[str, str] = {}
    for item_id, item in sorted(state.items.items()):
        if not getattr(item, "unique", False) or item.owner_id is None:
            continue
        previous = owners.get(item_id)
        if previous is not None and previous != item.owner_id:
            violations.append(f"unique item {item_id} owned by both {previous} and {item.owner_id}")
        owners[item_id] = item.owner_id

    last_event_id = getattr(state, "last_event_id", events)
    if last_event_id != base_event_id + events:
        violations.append(
            f"last_event_id {last_event_id} != genesis {base_event_id} + emitted {events}"
        )
    return violations


def run_benchmark(core: Any, args: argparse.Namespace) -> int:
    if args.years < 1:
        raise ValueError("--years must be >= 1")
    if not 1 <= args.chunk_days <= MAX_CHUNK_DAYS:
        raise ValueError(f"--chunk-days must be between 1 and {MAX_CHUNK_DAYS}")

    state = core.create_world(seed=args.seed)
    base_event_id = state.last_event_id
    npc_count = len(state.npcs)
    if npc_count != args.npcs:
        raise ValueError(f"seed {args.seed} generated {npc_count} NPCs but --npcs is {args.npcs}")

    print(
        f"world={state.world_id} seed={state.world_seed} npcs={npc_count} "
        f"years={args.years} agent_mode={args.agent_mode}"
    )

    started, events = _start_cultivation(core, state)
    print(f"started {CULTIVATION_DAYS}-day cultivation for {started} idle NPCs")

    start_tick = state.tick
    target_tick = start_tick + args.years * TICKS_PER_YEAR
    started_at = time.perf_counter()
    checksum = core.state_checksum(state)

    while state.tick < target_tick:
        ticks = min(args.chunk_days, target_tick - state.tick)
        result = core.advance_time(state, ticks, source="system")
        if not getattr(result, "accepted", False):
            raise RuntimeError(f"advance_time({ticks}) was rejected")
        events += len(result.events)

        elapsed = time.perf_counter() - started_at
        simulated = state.tick - start_tick
        rate = simulated / elapsed if elapsed > 0 else 0.0
        alive = sum(1 for npc in state.npcs.values() if npc.alive)
        checksum = core.state_checksum(state)
        print(
            f"tick={state.tick:5d}/{target_tick} elapsed={elapsed:8.3f}s "
            f"ticks/s={rate:9.1f} npcs={npc_count} alive={alive} "
            f"events={events} checksum={checksum}"
        )

    elapsed = time.perf_counter() - started_at
    simulated = state.tick - start_tick
    rate = simulated / elapsed if elapsed > 0 else 0.0
    alive = sum(1 for npc in state.npcs.values() if npc.alive)
    checksum = core.state_checksum(state)

    print(
        f"final checksum={checksum} elapsed={elapsed:.3f}s ticks/s={rate:.1f} "
        f"ticks={simulated} npcs={npc_count} alive={alive} events={events}"
    )

    violations = _final_violations(core, state, target_tick, events, base_event_id)
    if violations:
        print(f"state validation failed with {len(violations)} violation(s):", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print("state validation passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.agent_mode == "replay":
        print(
            "--agent-mode replay is not available yet: agent_runtime "
            "(packages/agent_runtime) has not landed. Use --agent-mode rules; "
            "replay will be wired to recorded agent decisions once it exists.",
            file=sys.stderr,
        )
        return 2

    core = _require_world_core()
    try:
        return run_benchmark(core, args)
    except Exception as exc:
        print(f"benchmark failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
