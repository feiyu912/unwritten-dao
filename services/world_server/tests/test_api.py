from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from world_server.app import create_app

from world_core import (
    LOC_BLACKWOOD_FOREST,
    PLAYER_ID,
    PROTAGONIST_ID,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def _move_command(client: TestClient, tick: int, version: int, *, key: str) -> dict[str, Any]:
    return {
        "schema_version": "world-command.v1",
        "command_id": f"11111111-1111-4111-8111-{version:012d}",
        "idempotency_key": key,
        "world_id": client.get("/v1/world/snapshot").json()["world_id"],
        "actor_id": PROTAGONIST_ID,
        "issued_tick": tick,
        "expected_state_version": version,
        "type": "move",
        "arguments": {"to_location_id": LOC_BLACKWOOD_FOREST},
        "source": "player",
    }


def test_health_and_snapshot_contract(client: TestClient) -> None:
    health = client.get("/v1/health").json()
    assert health == {"status": "ok", "world_loaded": True, "tick": 0}

    snapshot = client.get("/v1/world/snapshot").json()
    assert snapshot["schema_version"] == "world-snapshot.v1"
    assert snapshot["checksum"].startswith("sha256:")
    assert len(snapshot["state"]["npcs"]) == 30


def test_command_lifecycle_happy_idempotent_stale(client: TestClient) -> None:
    payload = _move_command(client, 0, 0, key="api:move:1")
    response = client.post("/v1/commands", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["state_version"] == 1
    assert len(body["events"]) == 1

    duplicate = client.post("/v1/commands", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json() == body

    events = client.get("/v1/world/events", params={"after": 0}).json()["events"]
    assert len(events) == 1

    stale = _move_command(client, 1, 0, key="api:move:2")
    stale["issued_tick"] = 5
    conflict = client.post("/v1/commands", json=stale)
    assert conflict.status_code in {409, 422}


def test_observation_and_decision_endpoints(client: TestClient) -> None:
    observation = client.get(f"/v1/npcs/{PROTAGONIST_ID}/observation")
    assert observation.status_code == 200
    body = observation.json()
    assert body["npc_id"] == PROTAGONIST_ID
    assert body["schema_version"] == "npc-observation.v1"
    assert body["known_locations"]
    assert all(loc["location_id"] != "location_ancient_cave" for loc in body["known_locations"])

    decision = client.post(f"/v1/agents/{PROTAGONIST_ID}/decision")
    assert decision.status_code == 200
    proposal = decision.json()
    assert proposal["intent"] in {"move", "investigate", "start_cultivation", "wait"}
    assert proposal["rationale_short"]

    assert client.get(f"/v1/npcs/{PLAYER_ID}").status_code == 200
    assert client.get("/v1/npcs/00000000-0000-4000-8000-000000000000").status_code == 404


def test_save_load_round_trip(client: TestClient) -> None:
    created = client.post("/v1/saves", json={"label": "checkpoint"})
    assert created.status_code == 201
    save = created.json()
    assert save["checksum"].startswith("sha256:")

    advanced = client.post(
        "/v1/commands",
        json=_move_command(client, 0, 0, key="api:save-flow"),
    )
    assert advanced.status_code == 200
    moved_checksum = client.get("/v1/world/snapshot").json()["checksum"]
    assert moved_checksum != save["checksum"]

    loaded = client.post(f"/v1/saves/{save['save_id']}/load")
    assert loaded.status_code == 200
    assert loaded.json()["checksum"] == save["checksum"]

    replay = client.post(
        "/v1/commands",
        json=_move_command(client, 0, 0, key="api:save-flow"),
    )
    assert replay.status_code == 200
    assert client.get("/v1/world/snapshot").json()["checksum"] == moved_checksum


def test_causality_endpoint(client: TestClient) -> None:
    create = client.post(
        "/v1/commands",
        json=_move_command(client, 0, 0, key="api:causality"),
    )
    event_id = create.json()["events"][0]["event_id"]
    chain = client.get(f"/v1/debug/causality/{event_id}").json()
    assert chain["root_event_id"] == event_id
    assert chain["events"][0]["event_id"] == event_id

    assert client.get("/v1/debug/causality/999999").status_code == 404
