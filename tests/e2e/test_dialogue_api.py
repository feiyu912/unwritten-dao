"""Route orchestration tests, with an in-memory repository double.

These exercise the real dialogue parser, observation builder and world simulator.
They prove repository calls and ordering, not PostgreSQL persistence or locks.
"""

from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from world_server.repository import StaleStateVersion

from agent_runtime import (
    ActionProposal,
    OpenAICompatibleProvider,
    ProviderError,
    proposal_to_command,
)
from world_core import (
    PROTAGONIST_ID,
    advance_time,
    apply_command,
    create_world,
    make_command,
    state_checksum,
)

api = importlib.import_module("world_server.app")


@pytest.fixture
def route(monkeypatch):
    state = create_world(42)
    apply_command(
        state,
        make_command(
            state,
            PROTAGONIST_ID,
            "move",
            {"to_location_id": "location_stone_town"},
        ),
    )
    advance_time(state, 10)
    trace = []
    audit = []
    session = SimpleNamespace(rollback=lambda: trace.append("rollback"))
    monkeypatch.setattr(api, "load_state", lambda _session: state.model_copy(deep=True))
    monkeypatch.setattr(api, "list_events", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        api,
        "retrieve_memories",
        lambda *_args, **_kwargs: [
            {
                "event_id": 1,
                "tick": 0,
                "summary": "保留的事件记忆",
                "importance": 0.8,
                "emotional_valence": 0.0,
            }
        ],
    )

    def save(_session, **kwargs):
        trace.append("audit")
        audit.append(kwargs)

    def submit(_session, command):
        if command.expected_state_version != state.state_version:
            raise StaleStateVersion(command.expected_state_version, state.state_version)
        return apply_command(state, command)

    monkeypatch.setattr(api, "save_decisions", save)
    monkeypatch.setattr(api, "apply_command", submit)
    monkeypatch.setenv("AGENT_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "http://unused.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    app = api.create_app()
    app.dependency_overrides[api.session_dependency] = lambda: session
    # No context manager: do not run the PostgreSQL-backed lifespan.
    client = TestClient(app)
    yield SimpleNamespace(client=client, state=state, trace=trace, audit=audit)
    client.close()


def _talk(route):
    return route.client.post(
        "/v1/dialogue",
        json={
            "npc_id": PROTAGONIST_ID,
            "player_id": route.state.player_id,
            "message": "可以赠我护符吗？",
        },
    )


def _answer(route, monkeypatch, *, item="item_talisman"):
    def complete(_self, *, system, user):
        assert route.trace == ["rollback"]
        assert "保留的事件记忆" in user
        route.trace.append("inference")
        return json.dumps(
            {
                "reply_text": "我愿一试。",
                "proposal": {
                    "intent": "transfer_item",
                    "arguments": {
                        "item_id": item,
                        "from": {"kind": "npc", "id": PROTAGONIST_ID},
                        "to": {"kind": "npc", "id": route.state.player_id},
                    },
                    "memory_refs": [1, 999999],
                },
            }
        )

    monkeypatch.setattr(OpenAICompatibleProvider, "complete", complete)


def test_route_audits_proposal_but_only_command_changes_world(route, monkeypatch):
    _answer(route, monkeypatch)
    checksum = state_checksum(route.state)
    response = _talk(route)
    assert response.status_code == 200
    proposal = ActionProposal.model_validate(response.json()["proposal"])
    assert state_checksum(route.state) == checksum
    assert proposal.memory_refs == [1]
    assert route.trace == ["rollback", "inference", "audit"]
    assert route.audit[0]["proposal"] == proposal
    record = route.audit[0]["records"][0]
    assert record.accepted and record.decision_id == proposal.decision_id
    command = proposal_to_command(route.state, proposal)
    applied = route.client.post("/v1/commands", json=command.model_dump(mode="json"))
    assert applied.status_code == 200
    assert any(e["type"] == "ITEM_TRANSFERRED" for e in applied.json()["events"])
    assert route.state.items["item_talisman"].owner_id == route.state.player_id


@pytest.mark.parametrize("stale", [False, True])
def test_rejected_or_stale_proposal_does_not_report_command_success(route, monkeypatch, stale):
    _answer(route, monkeypatch, item="item_talisman" if stale else "item_foundation_pill")
    proposal = ActionProposal.model_validate(_talk(route).json()["proposal"])
    command = proposal_to_command(route.state, proposal)
    if stale:
        advance_time(route.state, 1)
    checksum = state_checksum(route.state)
    response = route.client.post("/v1/commands", json=command.model_dump(mode="json"))
    assert response.status_code == (409 if stale else 422)
    assert response.json().get("accepted") is not True
    assert state_checksum(route.state) == checksum


@pytest.mark.parametrize("mode", ["utility", "llm-mock"])
def test_old_text_only_modes_do_not_submit_actions(route, monkeypatch, mode):
    monkeypatch.setenv("AGENT_PROVIDER", mode)
    monkeypatch.setenv("LLM_MOCK_DIALOGUE_REPLY", "此物不可相赠。")
    response = _talk(route)
    assert response.status_code == 200
    assert response.json()["proposal"] is None
    assert response.json()["reply_text"]
    assert route.audit == []


def test_dead_player_rejected_before_inference(route, monkeypatch):
    route.state.npcs[route.state.player_id].alive = False
    _answer(route, monkeypatch)
    response = _talk(route)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "player_dead"
    assert not route.trace and not route.audit


def test_missing_provider_config_returns_unavailable_without_audit(route, monkeypatch):
    monkeypatch.delenv("LLM_MODEL")
    response = _talk(route)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "agent_provider_misconfigured"
    assert route.trace == ["rollback"] and not route.audit


@pytest.mark.parametrize("failed_transport", [False, True])
def test_bad_provider_reply_is_audited_without_executing_or_leaking_error(
    route,
    monkeypatch,
    failed_transport,
):
    def complete(_self, **_kwargs):
        assert route.trace == ["rollback"]
        if failed_transport:
            raise ProviderError("secret_remote_error_body")
        return '{"reply_text":"我已交付丹药","proposal":[]}'

    monkeypatch.setattr(OpenAICompatibleProvider, "complete", complete)
    checksum = state_checksum(route.state)
    response = _talk(route)
    assert response.status_code == 200
    assert response.json()["proposal"] is None
    assert "已交付" not in response.json()["reply_text"]
    assert "secret_remote_error_body" not in response.text
    assert state_checksum(route.state) == checksum
    record = route.audit[0]["records"][0]
    assert not record.accepted
    assert record.error == "dialogue_provider_or_output_invalid"
    assert route.audit[0]["proposal"] is None
