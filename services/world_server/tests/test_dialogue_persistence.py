"""Dialogue consequences against real PostgreSQL; inference alone is stubbed.

Transport compatibility is covered separately. These tests exercise the real
HTTP app, command transaction, audit rows, event memories and save restoration.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from world_server.app import create_app
from world_server.dialogue import OpenAICompatibleProvider
from world_server.models import AgentDecisionRow, CommandLogRow, MemoryEpisodeRow, WorldEventRow

from world_core import LOC_XUANYUE_SECT, PLAYER_ID, PROTAGONIST_ID

pytestmark = pytest.mark.integration


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as result:
        yield result


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> tuple[list[dict[str, Any]], list[str]]:
    replies: list[dict[str, Any]] = []
    prompts: list[str] = []

    def complete(_self: Any, *, system: str, user: str) -> str:
        assert "不能" in system or "不要" in system
        prompts.append(user)
        return json.dumps(replies.pop(0), ensure_ascii=False)

    monkeypatch.setenv("AGENT_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "http://unused.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "integration-stub")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "off")
    monkeypatch.setattr(OpenAICompatibleProvider, "complete", complete)
    return replies, prompts


def _submit(client: TestClient, intent: str, arguments: dict[str, Any]) -> dict[str, Any]:
    snapshot = client.get("/v1/world/snapshot").json()
    command = {
        "schema_version": "world-command.v1",
        "command_id": str(uuid.uuid4()),
        "idempotency_key": str(uuid.uuid4()),
        "world_id": snapshot["world_id"],
        "actor_id": None if intent == "advance_time" else PLAYER_ID,
        "issued_tick": snapshot["tick"],
        "expected_state_version": snapshot["state_version"],
        "type": intent,
        "arguments": arguments,
        "source": "system" if intent == "advance_time" else "player",
    }
    response = client.post("/v1/commands", json=command)
    assert response.status_code == 200, response.text
    return response.json()


def _colocate(client: TestClient) -> None:
    _submit(client, "move", {"to_location_id": LOC_XUANYUE_SECT})
    _submit(client, "advance_time", {"ticks": 1})
    state = client.get("/v1/world/snapshot").json()["state"]
    assert state["npcs"][PLAYER_ID]["location_id"] == LOC_XUANYUE_SECT
    assert state["npcs"][PROTAGONIST_ID]["location_id"] == LOC_XUANYUE_SECT


def _turn(client: TestClient, message: str = "可否赠我护符？") -> dict[str, Any]:
    response = client.post(
        "/v1/dialogue",
        json={
            "npc_id": PROTAGONIST_ID,
            "player_id": PLAYER_ID,
            "message": message,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _gift(item_id: str = "item_talisman") -> dict[str, Any]:
    return {
        "reply_text": "我愿将此物相赠。",
        "proposal": {
            "intent": "transfer_item",
            "arguments": {
                "item_id": item_id,
                "from": {"kind": "npc", "id": PROTAGONIST_ID},
                "to": {"kind": "npc", "id": PLAYER_ID},
            },
            "rationale_short": "赠予道友防身之物",
        },
    }


def _proposal_command(client: TestClient, proposal: dict[str, Any]) -> dict[str, Any]:
    snapshot = client.get("/v1/world/snapshot").json()
    return {
        "schema_version": "world-command.v1",
        "command_id": proposal["proposal_id"],
        "idempotency_key": "dialogue:" + proposal["proposal_id"],
        "world_id": snapshot["world_id"],
        "actor_id": proposal["npc_id"],
        "issued_tick": snapshot["tick"],
        "expected_state_version": proposal["observed_world_version"],
        "type": proposal["intent"],
        "arguments": proposal["arguments"],
        "source": "agent",
    }


def test_dialogue_transfer_persists_once_and_is_recalled_after_reload(
    client: TestClient,
    session: Session,
    model: tuple[list[dict[str, Any]], list[str]],
) -> None:
    replies, prompts = model
    _colocate(client)
    before = client.get("/v1/world/snapshot").json()
    replies.append(_gift())
    turn = _turn(client)
    assert turn["proposal"] is not None
    assert client.get("/v1/world/snapshot").json()["checksum"] == before["checksum"]
    audit = session.execute(select(AgentDecisionRow)).scalar_one()
    assert audit.accepted and audit.proposal == turn["proposal"]
    assert audit.raw_response is not None and "相赠" in audit.raw_response
    assert audit.npc_id == uuid.UUID(PROTAGONIST_ID)

    command = _proposal_command(client, turn["proposal"])
    first = client.post("/v1/commands", json=command)
    duplicate = client.post("/v1/commands", json=command)
    assert first.status_code == duplicate.status_code == 200
    assert first.json() == duplicate.json()
    event = next(row for row in first.json()["events"] if row["type"] == "ITEM_TRANSFERRED")
    event_id = event["event_id"]
    assert (
        session.scalar(
            select(func.count())
            .select_from(WorldEventRow)
            .where(
                WorldEventRow.event_id == event_id,
            )
        )
        == 1
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(CommandLogRow)
            .where(
                CommandLogRow.idempotency_key == command["idempotency_key"],
            )
        )
        == 1
    )
    memories = session.scalars(
        select(MemoryEpisodeRow).where(
            MemoryEpisodeRow.source_event_id == event_id,
        )
    ).all()
    assert {str(memory.npc_id) for memory in memories} == {PROTAGONIST_ID, PLAYER_ID}
    assert len(memories) == 2
    assert all("旧护身符" in memory.summary for memory in memories)
    saved_world = client.get("/v1/world/snapshot").json()
    assert saved_world["state"]["items"]["item_talisman"]["owner_id"] == PLAYER_ID
    save = client.post("/v1/saves", json={"label": "after-dialogue-gift"})
    assert save.status_code == 201
    _submit(client, "advance_time", {"ticks": 3})
    loaded = client.post(f"/v1/saves/{save.json()['save_id']}/load")
    assert loaded.status_code == 200
    assert loaded.json()["checksum"] == saved_world["checksum"]
    assert loaded.json()["state"]["items"]["item_talisman"]["owner_id"] == PLAYER_ID

    replies.append({"reply_text": "那枚旧护身符还请收好。", "proposal": None})
    followup = _turn(client, "还记得刚才赠我的东西吗？")
    assert followup["proposal"] is None
    memory_section = prompts[-1].split("RELEVANT_MEMORIES", 1)[1].split("AVAILABLE_ACTIONS", 1)[0]
    assert f"[E{event_id}]" in memory_section and "旧护身符" in memory_section
    session.expire_all()
    assert (
        session.scalar(
            select(func.count())
            .select_from(MemoryEpisodeRow)
            .where(
                MemoryEpisodeRow.source_event_id == event_id,
            )
        )
        == 2
    )


@pytest.mark.parametrize("failure", ["illegal", "stale"])
def test_failed_dialogue_action_cannot_mutate_ownership_or_memories(
    client: TestClient,
    session: Session,
    model: tuple[list[dict[str, Any]], list[str]],
    failure: str,
) -> None:
    replies, _ = model
    _colocate(client)
    replies.append(_gift("item_foundation_pill" if failure == "illegal" else "item_talisman"))
    turn = _turn(client)
    command = _proposal_command(client, turn["proposal"])
    if failure == "stale":
        _submit(client, "advance_time", {"ticks": 1})
    before = client.get("/v1/world/snapshot").json()
    memory_count = session.scalar(select(func.count()).select_from(MemoryEpisodeRow))
    response = client.post("/v1/commands", json=command)
    assert response.status_code == (409 if failure == "stale" else 422)
    after = client.get("/v1/world/snapshot").json()
    assert after["checksum"] == before["checksum"]
    assert after["state"]["items"] == before["state"]["items"]
    assert session.scalar(select(func.count()).select_from(MemoryEpisodeRow)) == memory_count
    assert (
        session.scalar(
            select(func.count())
            .select_from(CommandLogRow)
            .where(
                CommandLogRow.idempotency_key == command["idempotency_key"],
            )
        )
        == 0
    )
