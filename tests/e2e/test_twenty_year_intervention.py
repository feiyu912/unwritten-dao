from __future__ import annotations

from tools.demo_causal import run

DAYS = 7300


def test_twenty_year_stolen_map_rewrites_the_protagonist_fate() -> None:
    baseline = run(days=DAYS, steal=False)
    stolen = run(days=DAYS, steal=True)

    baseline_fate = baseline.protagonist_outcome
    stolen_fate = stolen.protagonist_outcome

    assert baseline_fate["alive"] is True
    assert baseline_fate["realm"] == 2
    assert baseline_fate["realm_discovered"] is True
    assert baseline_fate["pill_claimed_by"] is not None

    assert stolen_fate["alive"] is True
    assert stolen_fate["realm"] == 1
    assert stolen_fate["has_map"] is False
    assert stolen_fate["realm_discovered"] is False
    assert stolen_fate["pill_claimed_by"] is None

    assert baseline.checksum != stolen.checksum
