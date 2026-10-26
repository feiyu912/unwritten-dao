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


def _decision(client: TestClient, npc_id: str) -> Any:
    return client.post(f"/v1/agents/{npc_id}/decision")


def test_decision_is_audited_for_utility(client: TestClient, session: Any) -> None:
    from world_server.repository import list_decisions

    response = _decision(client, PROTAGONIST_ID)
    assert response.status_code == 200
    rows = list_decisions(session, npc_id=PROTAGONIST_ID)
    assert rows
    assert rows[-1].provider == "utility"
    assert rows[-1].accepted is True
    assert rows[-1].proposal["npc_id"] == PROTAGONIST_ID


def test_llm_mock_decision_records_prompt(
    client: TestClient, session: Any, monkeypatch: Any
) -> None:
    from world_server.repository import list_decisions

    monkeypatch.setenv("AGENT_PROVIDER", "llm-mock")
    response = _decision(client, PROTAGONIST_ID)
    assert response.status_code == 200
    rows = list_decisions(session, npc_id=PROTAGONIST_ID, accepted_only=True)
    assert rows[-1].provider == "MockInferenceProvider"
    assert "自主角色" in rows[-1].system_prompt
    assert "WORLD_FACTS" in rows[-1].user_prompt
    assert rows[-1].proposal is not None


def test_invalid_llm_falls_back_and_audits_both(
    client: TestClient, session: Any, monkeypatch: Any
) -> None:
    from world_server.repository import list_decisions

    monkeypatch.setenv("AGENT_PROVIDER", "llm-mock")
    monkeypatch.setenv("LLM_MOCK_REPLY", "not json at all")
    response = _decision(client, PROTAGONIST_ID)
    assert response.status_code == 200
    rows = list_decisions(session, npc_id=PROTAGONIST_ID)
    assert any(not row.accepted and row.provider == "MockInferenceProvider" for row in rows)
    accepted = [row for row in rows if row.accepted]
    assert len(accepted) == 1
    assert accepted[0].provider == "utility"
    assert accepted[0].proposal is not None


def test_background_npc_stays_on_utility(
    client: TestClient, session: Any, monkeypatch: Any
) -> None:
    from world_core.worldgen import npc_id
    from world_server.repository import list_decisions

    monkeypatch.setenv("AGENT_PROVIDER", "llm-mock")
    response = _decision(client, npc_id("a_he"))
    assert response.status_code == 200
    rows = list_decisions(session, npc_id=npc_id("a_he"))
    assert rows[-1].provider == "utility"


def test_replay_mode_returns_recorded_proposal(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setenv("AGENT_PROVIDER", "llm-mock")
    recorded = _decision(client, PROTAGONIST_ID)
    assert recorded.status_code == 200

    monkeypatch.setenv("AGENT_PROVIDER", "replay")
    replayed = _decision(client, PROTAGONIST_ID)
    assert replayed.status_code == 200
    assert replayed.json() == recorded.json()

    snapshot = client.get("/v1/world/snapshot").json()
    advance = {
        "schema_version": "world-command.v1",
        "command_id": "22222222-2222-4222-8222-222222222222",
        "idempotency_key": "api:replay-advance",
        "world_id": snapshot["world_id"],
        "actor_id": None,
        "issued_tick": snapshot["tick"],
        "expected_state_version": snapshot["state_version"],
        "type": "advance_time",
        "arguments": {"ticks": 1},
        "source": "system",
    }
    assert client.post("/v1/commands", json=advance).status_code == 200
    missing = _decision(client, PROTAGONIST_ID)
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "replay_fixture_missing"


def test_observation_and_prompt_include_relevant_memories(
    client: TestClient, session: Any, monkeypatch: Any
) -> None:
    from world_server.repository import apply_command, load_state

    from world_core import (
        ITEM_MAP_FRAGMENT as MAP,
    )
    from world_core import (
        LOC_BLACKWOOD_FOREST as FOREST,
    )
    from world_core import (
        LOC_MISTY_VALLEY as VALLEY,
    )
    from world_core import (
        LOC_RUINED_TEMPLE as TEMPLE,
    )
    from world_core import (
        make_command,
    )

    state = load_state(session)
    actor = state.npcs[PROTAGONIST_ID]
    steps: list[tuple[str, dict[str, Any]]] = [
        ("move", {"to_location_id": FOREST}),
        ("move", {"to_location_id": TEMPLE}),
        (
            "transfer_item",
            {
                "item_id": MAP,
                "from": {"kind": "location", "id": TEMPLE},
                "to": {"kind": "npc", "id": actor.npc_id},
            },
        ),
        ("move", {"to_location_id": VALLEY}),
        ("investigate", {"target_location_id": VALLEY, "focus": "secret_realm"}),
    ]
    for intent, arguments in steps:
        current = load_state(session)
        apply_command(
            session,
            make_command(current, actor.npc_id, intent, arguments, source="test"),  # type: ignore[arg-type]
        )

    observation = client.get(f"/v1/npcs/{PROTAGONIST_ID}/observation").json()
    assert observation["memories"]
    assert any("secret realm" in memory["summary"] for memory in observation["memories"])

    monkeypatch.setenv("AGENT_PROVIDER", "llm-mock")
    decision = client.post(f"/v1/agents/{PROTAGONIST_ID}/decision")
    assert decision.status_code == 200

    from sqlalchemy import select
    from world_server.models import AgentDecisionRow

    row = session.execute(
        select(AgentDecisionRow).order_by(AgentDecisionRow.id.desc()).limit(1)
    ).scalar_one()
    assert "RELEVANT_MEMORIES" in row.user_prompt
    assert "secret realm" in row.user_prompt


def test_dialogue_placeholder_without_provider(client: TestClient) -> None:
    response = client.post(
        "/v1/dialogue",
        json={"npc_id": PROTAGONIST_ID, "player_id": PLAYER_ID, "message": "道友可曾见过残图？"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reply_text"]
    assert body["proposal"] is None


def test_dialogue_mock_provider(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setenv("AGENT_PROVIDER", "llm-mock")
    monkeypatch.setenv("LLM_MOCK_DIALOGUE_REPLY", "此处不是说话的地方。")
    response = client.post(
        "/v1/dialogue",
        json={"npc_id": PROTAGONIST_ID, "player_id": PLAYER_ID, "message": "借一步说话。"},
    )
    assert response.status_code == 200
    assert response.json()["reply_text"] == "此处不是说话的地方。"


def test_dialogue_rejects_empty_message_and_dead_npc(client: TestClient) -> None:
    empty = client.post(
        "/v1/dialogue",
        json={"npc_id": PROTAGONIST_ID, "player_id": PLAYER_ID, "message": "   "},
    )
    assert empty.status_code == 422

    unknown = client.post(
        "/v1/dialogue",
        json={"npc_id": "00000000-0000-4000-8000-000000000000", "message": "有人吗？"},
    )
    assert unknown.status_code == 404


def test_dialogue_openai_misconfigured_returns_503(client: TestClient, monkeypatch: Any) -> None:
    monkeypatch.setenv("AGENT_PROVIDER", "openai")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    response = client.post(
        "/v1/dialogue",
        json={"npc_id": PROTAGONIST_ID, "player_id": PLAYER_ID, "message": "你好。"},
    )
    assert response.status_code == 503
