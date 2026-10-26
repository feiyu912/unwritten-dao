#!/usr/bin/env python3
"""Inspect (and optionally dump) a ``world-command.v1`` JSONL stream.

This is a read-only companion to ``tools.bench_replay``::

    uv run python -m tools.replay path/to/commands.jsonl
    uv run python -m tools.replay path/to/commands.jsonl --show 3

Each line is validated against ``docs/contracts/world-command.v1.schema.json``.
The tool exits non-zero if any line is malformed or contract-invalid.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "contracts"
    / "world-command.v1.schema.json"
)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect a world-command.v1 JSONL stream.",
    )
    parser.add_argument("path", type=Path, help="JSONL file to inspect")
    parser.add_argument(
        "--show",
        type=int,
        default=0,
        metavar="N",
        help="pretty-print the first N commands",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="skip JSON Schema validation (structure checks still run)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the summary as JSON",
    )
    return parser.parse_args(argv)


def _load_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def inspect_stream(path: Path, *, validate: bool) -> tuple[dict[str, Any], list[str], int]:
    """Return (summary, errors, loaded_count)."""
    validator = _load_validator() if validate else None
    errors: list[str] = []
    commands: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    world_ids: set[str] = set()
    ticks: list[int] = []

    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{lineno}: invalid JSON: {exc}")
                continue
            if not isinstance(doc, dict):
                errors.append(f"{path}:{lineno}: command must be a JSON object")
                continue

            commands.append(doc)
            command_type = doc.get("type")
            source = doc.get("source")
            if isinstance(command_type, str):
                type_counts[command_type] += 1
            if isinstance(source, str):
                source_counts[source] += 1
            world_id = doc.get("world_id")
            if isinstance(world_id, str):
                world_ids.add(world_id)
            issued_tick = doc.get("issued_tick")
            if isinstance(issued_tick, int):
                ticks.append(issued_tick)

            if validator is not None:
                for error in validator.iter_errors(doc):
                    location = "/".join(str(part) for part in error.absolute_path)
                    suffix = f" at {location}" if location else ""
                    errors.append(f"{path}:{lineno}: schema violation{suffix}: {error.message}")

    summary: dict[str, Any] = {
        "path": str(path),
        "commands": len(commands),
        "world_ids": sorted(world_ids),
        "tick_min": min(ticks) if ticks else None,
        "tick_max": max(ticks) if ticks else None,
        "types": dict(sorted(type_counts.items())),
        "sources": dict(sorted(source_counts.items())),
        "valid": not errors,
    }
    return summary, errors, len(commands)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.show < 0:
        print("--show must be >= 0", file=sys.stderr)
        return 2

    try:
        summary, errors, _ = inspect_stream(args.path, validate=not args.no_validate)
    except OSError as exc:
        print(f"cannot read {args.path}: {exc}", file=sys.stderr)
        return 1

    if args.show:
        shown = 0
        with args.path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                if shown >= args.show:
                    break
                print(json.dumps(json.loads(line), ensure_ascii=False, indent=2))
                shown += 1

    if args.as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"commands: {summary['commands']}")
        print(f"world_ids: {', '.join(summary['world_ids']) or '(none)'}")
        print(f"ticks: {summary['tick_min']}..{summary['tick_max']}")
        print(f"types: {summary['types']}")
        print(f"sources: {summary['sources']}")

    if errors:
        print(f"{len(errors)} problem(s):", file=sys.stderr)
        for error in errors[:20]:
            print(f"  - {error}", file=sys.stderr)
        if len(errors) > 20:
            print(f"  ... {len(errors) - 20} more", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())