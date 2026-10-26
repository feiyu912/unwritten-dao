from __future__ import annotations

import pytest
from tools.export_dashboard import dashboard_from_db
from world_server.history import persist_history, simulate_days
from world_server.repository import bootstrap

pytestmark = pytest.mark.integration


def test_dashboard_reads_the_persisted_world(session) -> None:
    state = bootstrap(session, seed=42)
    from sqlalchemy import func, select
    from world_server.models import WorldEventRow

    base_events = session.execute(select(func.count()).select_from(WorldEventRow)).scalar_one()
    events = simulate_days(state, 5)
    persist_history(session, state, events)

    page, event_count, valid = dashboard_from_db(session)
    assert event_count == base_events + len(events)
    assert event_count > 0
    assert valid is True
    assert "沈砚" in page
    assert "violations: none" in page
