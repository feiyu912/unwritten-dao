from __future__ import annotations

from tools.character_history import simulate
from tools.export_dashboard import build_dashboard


def test_dashboard_is_self_contained_and_contains_the_story() -> None:
    state, events = simulate(years=1, seed=42)
    page = build_dashboard(state, events, years=1, seed=42)

    assert page.startswith("<!doctype html>")
    assert "<svg" in page
    assert "沈砚" in page
    assert "残破洞府图" in page
    assert "http://" not in page and "https://" not in page
    assert "violations: none" in page
    assert "故事线" in page
    assert "score=" in page
    assert "world advanced to tick" not in page
