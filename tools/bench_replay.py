#!/usr/bin/env python3
"""Replay a recorded ``world-command.v1`` stream against fresh seed worlds.

Determinism check for ``world_core`` (see ``docs/architecture.md``): the same
seed plus the same command stream must produce the same state checksum and
event count on every run and on every platform::

    uv run python -m tools.bench_replay --runs 10 --seed 42 --commands path.jsonl

Each non-blank JSONL line must be a complete ``world-command.v1`` object. The
stream is applied as recorded (including its ``issued_tick`` and
``expected_state_version`` values), so it must have been produced from a fresh
world created with the same seed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, NamedTuple


def _require_world_core() -> Any:
    """Import world_core lazily so the CLI can explain a missing module."""
    try:
        import world_core
    except ImportError as exc:  # pragma: no cover - depends on merge order
        raise SystemExit(
            "world_core is not importable yet; merge packages/world_core before "
            f"running replay (import error: {exc})"
        ) from exc
    return world_core


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay a world-command.v1 JSONL stream N times and compare outcomes.",
    )
    parser.add_argument("--runs", type=int, default=10, help="number of fresh-world runs")
    parser.add_argument("--seed", type=int, default=42, help="world seed")
    parser.add_argument(
        "--commands",
        type=Path,
        required=True,
        help="JSONL file of world-command.v1 objects",
    )
    return parser.parse_args(argv)


def load_command_docs(path: Path) -> list[dict[str, Any]]:
    """Read and lightly validate the command stream before any simulation."""
    docs: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if not isinstance(doc, dict):
                raise ValueError(f"{path}:{lineno}: command must be a JSON object")
            version = doc.get("schema_version")
            if version != "world-command.v1":
                raise ValueError(
                    f"{path}:{lineno}: expected schema_version world-command.v1, got {version!r}"
                )
            for key in ("world_id", "actor_id", "issued_tick", "type", "arguments"):
                if key not in doc:
                    raise ValueError(f"{path}:{lineno}: missing required field {key!r}")
            docs.append(doc)
    if not docs:
        raise ValueError(f"{path}: no commands found")
    return docs


def _parse_commands(core: Any, docs: list[dict[str, Any]]) -> list[Any]:
    """Convert raw contract objects into world_core's typed command model."""
    command_cls = core.models.WorldCommand
    return [command_cls.model_validate(doc) for doc in docs]


class RunResult(NamedTuple):
    elapsed: float
    checksum: str
    events: int
    last_event_id: int
    violations: list[str]


def _run_once(core: Any, commands: list[Any], seed: int, expected_world_id: str) -> RunResult:
    started_at = time.perf_counter()
    state = core.create_world(seed=seed)
    if state.world_id != expected_world_id:
        raise ValueError(
            f"seed {seed} created world {state.world_id}, but the stream targets "
            f"{expected_world_id}"
        )

    events = 0
    for index, command in enumerate(commands, 1):
        try:
            result = core.apply_command(state, command)
        except Exception as exc:
            raise RuntimeError(f"command {index} ({command.type}) was rejected: {exc}") from exc
        if not getattr(result, "accepted", False):
            raise RuntimeError(f"command {index} ({command.type}) was not accepted")
        events += len(result.events)

    elapsed = time.perf_counter() - started_at
    violations = list(core.validate_state(state))
    last_event_id = getattr(state, "last_event_id", events)
    if last_event_id != events:
        violations.append(f"last_event_id {last_event_id} != emitted events {events}")
    return RunResult(
        elapsed=elapsed,
        checksum=core.state_checksum(state),
        events=events,
        last_event_id=last_event_id,
        violations=violations,
    )


def run_replay(core: Any, args: argparse.Namespace) -> int:
    if args.runs < 1:
        raise ValueError("--runs must be >= 1")

    docs = load_command_docs(args.commands)
    commands = _parse_commands(core, docs)
    expected_world_id = docs[0]["world_id"]
    if any(doc["world_id"] != expected_world_id for doc in docs):
        raise ValueError("command stream mixes world_id values")

    print(
        f"commands={len(commands)} runs={args.runs} seed={args.seed} "
        f"world={expected_world_id} source={args.commands}"
    )

    baseline: tuple[str, int] | None = None
    failures: list[str] = []

    for run in range(1, args.runs + 1):
        result = _run_once(core, commands, args.seed, expected_world_id)
        print(
            f"run {run}/{args.runs}: {result.elapsed:.3f}s events={result.events} "
            f"checksum={result.checksum}"
        )
        outcomes = (result.checksum, result.events)
        if baseline is None:
            baseline = outcomes
        elif outcomes != baseline:
            failures.append(
                f"run {run} diverged: checksum={result.checksum} events={result.events} "
                f"(baseline checksum={baseline[0]} events={baseline[1]})"
            )
        for violation in result.violations:
            failures.append(f"run {run}: {violation}")

    if baseline is None:
        raise RuntimeError("no runs executed")

    if failures:
        print(f"replay failed with {len(failures)} problem(s):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(f"deterministic across {args.runs} run(s): checksum={baseline[0]} events={baseline[1]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    core = _require_world_core()
    try:
        return run_replay(core, args)
    except Exception as exc:
        print(f"replay failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())