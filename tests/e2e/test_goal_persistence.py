from __future__ import annotations

from tools.report_history import run


def test_long_term_goals_persist_to_resolution() -> None:
    report = run(days=400, seed=42)
    assert report["goal_counts"].get("achieved", 0) >= 1
    persistence = report["resolved_goal_persistence"]
    assert persistence is not None
    assert persistence >= 0.8
