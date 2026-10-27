#!/usr/bin/env python3
"""Export persisted decision-model samples from PostgreSQL to JSONL.

    uv run python -m tools.export_decision_samples --out reports/server_samples.jsonl

Only rows with a non-null `sample` payload are exported. Utility/LLM audit rows
without candidate data are skipped.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from sqlalchemy import select
from world_server.db import get_engine, get_session_factory
from world_server.models import AgentDecisionRow


def export_samples(session, path: pathlib.Path, *, limit: int = 100_000) -> int:
    rows = (
        session.execute(
            select(AgentDecisionRow)
            .where(AgentDecisionRow.sample.isnot(None))
            .order_by(AgentDecisionRow.id.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.sample, ensure_ascii=False, sort_keys=True) + "\n")
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export decision samples.")
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=pathlib.Path("reports/server_decisions.jsonl"),
    )
    parser.add_argument("--limit", type=int, default=100_000)
    args = parser.parse_args(argv)

    session = get_session_factory(get_engine())()
    try:
        count = export_samples(session, args.out, limit=args.limit)
    finally:
        session.close()
    print(f"wrote {args.out} samples={count}")
    return 0 if count >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
