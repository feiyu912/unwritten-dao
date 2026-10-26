from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from world_core import (
    ITEM_FOUNDATION_PILL,
    ITEM_MAP_FRAGMENT,
    LOC_ANCIENT_CAVE,
    LOC_BLACKWOOD_FOREST,
    LOC_MISTY_VALLEY,
    LOC_RUINED_TEMPLE,
    LOC_XUANYUE_SECT,
    PLAYER_ID,
)

from world_server.app import create_app

pytestmark = pytest.mark.integration


@pytest.fixture()
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client


def _submit(
    client: TestClient, intent: str, arguments: dict[str, Any], *, key: str
) -> list[dict[str, Any]]:
    snapshot = client.get("/v1/world/snapshot").json()
    command = {
        "schema_version": "world-command.v1",
        "command_id": str(uuid.uuid4()),
        "idempotency_key": key,
        "world_id": snapshot["world_id"],
        "actor_id": PLAYER_ID,
        "issued_tick": snapshot["tick"],
        "expected_state_version": snapshot["state_version"],
        "type": intent,
        "arguments": arguments,
        "source": "player",
    }
    response = client.post("/v1/commands", json=command)
    assert response.status_code == 200, response.text
    return response.json()["events"]


def test_player_completes_the_realm_arc_over_http(client: TestClient) -> None:
    all_events: list[dict[str, Any]] = []
    for index, target in enumerate(
        [LOC_XUANYUE_SECT, LOC_BLACKWOOD_FOREST, LOC_RUINED_TEMPLE]
    ):
        all_events += _submit(
            client, "move", {"to_location_id": target}, key=f"play:move:{index}"
        )
    all_events += _submit(
        client,
        "transfer_item",
        {
            "item_id": ITEM_MAP_FRAGMENT,
            "from": {"kind": "location", "id": LOC_RUINED_TEMPLE},
            "to": {"kind": "npc", "id": PLAYER_ID},
        },
        key="play:take-map",
    )
    all_events += _submit(
        client, "move", {"to_location_id": LOC_MISTY_VALLEY}, key="play:valley"
    )
    all_events += _submit(
        client,
        "investigate",
        {"target_location_id": LOC_MISTY_VALLEY, "focus": "secret_realm"},
        key="play:investigate",
    )
    all_events += _submit(
        client, "move", {"to_location_id": LOC_ANCIENT_CAVE}, key="play:cave"
    )

    claimed = False
    for attempt in range(10):
        events = _submit(
            client,
            "claim_opportunity",
            {"opportunity_id": "opp_foundation_pill"},
            key=f"play:claim:{attempt}",
        )
        all_events += events
        if any(event["type"] == "OPPORTUNITY_CLAIMED" and event["payload"]["success"] for event in events):
            claimed = True
            break
    assert claimed

    snapshot = client.get("/v1/world/snapshot").json()
    player = snapshot["state"]["npcs"][PLAYER_ID]
    assert ITEM_FOUNDATION_PILL in player["inventory"]
    assert snapshot["state"]["secret_realms"]["realm_ancient_cave"]["discovered_by"] == [
        PLAYER_ID
    ]

    discovery = next(event for event in all_events if event["type"] == "SECRET_REALM_DISCOVERED")
    chain = client.get(f"/v1/debug/causality/{discovery['event_id']}").json()
    chain_types = [event["type"] for event in chain["events"]]
    assert "LOCATION_INVESTIGATED" in chain_types
    assert "ITEM_TRANSFERRED" in chain_types

    observation = client.get(f"/v1/npcs/{PLAYER_ID}/observation").json()
    assert observation["memories"]
    assert observation["location_id"] == LOC_ANCIENT_CAVE
