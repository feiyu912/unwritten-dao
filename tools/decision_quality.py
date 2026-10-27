#!/usr/bin/env python3
"""Summarize decision samples for trajectory quality.

    uv run python -m tools.collect_decisions --days 10 --policy utility --out /tmp/d.jsonl
    uv run python -m tools.decision_quality /tmp/d.jsonl
    uv run python -m tools.decision_quality /tmp/d.jsonl --json

Reads ``decision-sample.v1`` JSONL only; it never simulates or mutates world
state. A non-zero exit means the dataset itself is inconsistent (a chosen
intent outside the sample's own available actions, or no samples at all).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

SCHEMA_VERSION = "decision-sample.v1"


def load_jsonl(paths: Iterable[pathlib.Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("schema_version") != SCHEMA_VERSION:
                raise ValueError(
                    f"{path}:{number}: expected {SCHEMA_VERSION}, "
                    f"got {row.get('schema_version')!r}"
                )
            rows.append(row)
    return rows


def summarize(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ValueError("no samples")
    actions = Counter(str(sample["chosen_intent"]) for sample in samples)
    outcomes = Counter(str(sample.get("outcome") or "unlabeled") for sample in samples)
    rejections = Counter(
        str(sample["rejection_code"]) for sample in samples if sample.get("rejection_code")
    )
    policies = Counter(str(sample["policy"]) for sample in samples)
    ticks = [int(sample["tick"]) for sample in samples]
    confidences = [float(sample.get("confidence", 0.0)) for sample in samples]
    labeled = outcomes["accepted"] + outcomes["rejected"]
    goal_samples = sum(1 for sample in samples if sample.get("goals"))
    result_events = sum(len(sample.get("result_event_ids") or []) for sample in samples)
    outside = sum(
        1
        for sample in samples
        if sample["chosen_intent"] not in sample.get("available_actions", [])
    )
    return {
        "samples": len(samples),
        "policies": dict(sorted(policies.items())),
        "npcs": len({str(sample["npc_id"]) for sample in samples}),
        "ticks": {"min": min(ticks), "max": max(ticks), "distinct": len(set(ticks))},
        "actions": dict(sorted(actions.items())),
        "action_diversity": len(actions),
        "outcomes": dict(sorted(outcomes.items())),
        "acceptance_rate": round(outcomes["accepted"] / labeled, 4) if labeled else None,
        "chosen_outside_available": outside,
        "rejection_codes": dict(sorted(rejections.items())),
        "with_goals": goal_samples,
        "with_goals_rate": round(goal_samples / len(samples), 4),
        "mean_confidence": round(statistics.fmean(confidences), 4),
        "mean_result_events": round(result_events / len(samples), 4),
        "wait_share": round(actions.get("wait", 0) / len(samples), 4),
    }


def _print_report(summary: Mapping[str, Any]) -> None:
    print(f"samples={summary['samples']} npcs={summary['npcs']} policies={summary['policies']}")
    ticks = summary["ticks"]
    print(f"ticks={ticks['min']}..{ticks['max']} distinct={ticks['distinct']}")
    print(f"actions={summary['actions']} diversity={summary['action_diversity']}")
    print(f"outcomes={summary['outcomes']} acceptance_rate={summary['acceptance_rate']}")
    print(f"rejections={summary['rejection_codes']}")
    print(
        f"with_goals={summary['with_goals']} ({summary['with_goals_rate']:.2f}) "
        f"mean_confidence={summary['mean_confidence']:.3f} "
        f"mean_result_events={summary['mean_result_events']:.2f} "
        f"wait_share={summary['wait_share']:.2f}"
    )
    print(f"chosen_outside_available={summary['chosen_outside_available']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize decision-sample.v1 JSONL files.")
    parser.add_argument("paths", nargs="+", type=pathlib.Path)
    parser.add_argument("--json", action="store_true", help="emit the summary as JSON")
    args = parser.parse_args(argv)

    try:
        summary = summarize(load_jsonl(args.paths))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        _print_report(summary)
    return 0 if summary["chosen_outside_available"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())