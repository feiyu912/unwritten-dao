"""Dialogue provider selection is independent from background agent decisions.

The compatible provider is replaced by an in-memory stub: these tests never
open a socket or call a real model service.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from world_server.agent_policy import build_policy

from agent_runtime import DecisionModelPolicy, build_observation
from world_core import PROTAGONIST_ID, advance_time, apply_command, create_world, make_command
from world_server import dialogue


class StubProvider:
    """In-memory replacement for OpenAICompatibleProvider."""

    name = "openai_compatible"

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.text_calls = 0
        self.turn_calls = 0
        STUB_INSTANCES.append(self)

    def complete_text(self, *, system: str, user: str) -> str:
        self.text_calls += 1
        return "  stub-dialogue  "

    def complete(self, *, system: str, user: str) -> str:
        self.turn_calls += 1
        return json.dumps({"reply_text": "stub-turn", "proposal": None}, ensure_ascii=False)


STUB_INSTANCES: list[StubProvider] = []


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> type[StubProvider]:
    STUB_INSTANCES.clear()
    monkeypatch.setattr(dialogue, "OpenAICompatibleProvider", StubProvider)
    monkeypatch.setenv("LLM_BASE_URL", "http://stub.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "stub-model")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MOCK_DIALOGUE_REPLY", raising=False)
    monkeypatch.delenv("DIALOGUE_PROVIDER", raising=False)
    monkeypatch.setenv("AGENT_PROVIDER", "utility")
    return StubProvider


def _world():
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
    return state, state.npcs[PROTAGONIST_ID], state.npcs[state.player_id]


def _turn(state, npc, player):
    return dialogue.generate_dialogue_turn(
        state,
        npc,
        player,
        "道友，可愿同行？",
        build_observation(state, npc.npc_id),
    )


def test_dialogue_llm_runs_independently_of_local_decision_model(provider, monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "decision-model")
    monkeypatch.setenv("DIALOGUE_PROVIDER", "openai-compatible")
    selection = build_policy()
    assert selection.mode == "decision-model"
    assert isinstance(selection.policy, DecisionModelPolicy)

    state, npc, player = _world()
    reply = dialogue.generate_dialogue_reply(state, npc, player, "道友，可愿同行？")
    turn = _turn(state, npc, player)

    assert reply == "stub-dialogue"
    assert turn.reply_text == "stub-turn"
    assert turn.proposal is None
    assert turn.record is not None
    assert turn.record.model_version == "stub-model"
    assert len(STUB_INSTANCES) == 2
    assert STUB_INSTANCES[0].text_calls == 1
    assert STUB_INSTANCES[1].turn_calls == 1


def test_explicit_dialogue_provider_overrides_agent_provider(provider, monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "openai-compatible")
    monkeypatch.setenv("DIALOGUE_PROVIDER", "utility")

    state, npc, player = _world()
    reply = dialogue.generate_dialogue_reply(state, npc, player, "道友，可愿同行？")
    turn = _turn(state, npc, player)

    assert "没有多说" in reply
    assert turn.reply_text == reply
    assert turn.proposal is None and turn.record is None
    assert STUB_INSTANCES == []


@pytest.mark.parametrize("dialogue_value", [None, "", "   "])
def test_unset_or_blank_dialogue_provider_falls_back_to_agent_provider(
    provider, monkeypatch, dialogue_value
):
    monkeypatch.setenv("AGENT_PROVIDER", "openai-compatible")
    if dialogue_value is None:
        monkeypatch.delenv("DIALOGUE_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("DIALOGUE_PROVIDER", dialogue_value)

    state, npc, player = _world()
    reply = dialogue.generate_dialogue_reply(state, npc, player, "道友，可愿同行？")
    turn = _turn(state, npc, player)

    assert reply == "stub-dialogue"
    assert turn.reply_text == "stub-turn"
    assert len(STUB_INSTANCES) == 2


def test_unset_dialogue_provider_keeps_decision_model_text_fallback(provider, monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "decision-model")
    monkeypatch.delenv("DIALOGUE_PROVIDER", raising=False)

    state, npc, player = _world()
    reply = dialogue.generate_dialogue_reply(state, npc, player, "道友，可愿同行？")
    turn = _turn(state, npc, player)

    assert "没有多说" in reply
    assert turn.reply_text == reply
    assert turn.proposal is None and turn.record is None
    assert STUB_INSTANCES == []


@pytest.mark.parametrize("mode", ["utility", "replay"])
def test_legacy_non_llm_modes_keep_fallback(provider, monkeypatch, mode):
    monkeypatch.setenv("AGENT_PROVIDER", mode)
    monkeypatch.delenv("DIALOGUE_PROVIDER", raising=False)

    state, npc, player = _world()
    reply = dialogue.generate_dialogue_reply(state, npc, player, "道友，可愿同行？")
    turn = _turn(state, npc, player)

    assert "没有多说" in reply
    assert turn.reply_text == reply
    assert turn.proposal is None and turn.record is None
    assert STUB_INSTANCES == []


def test_legacy_llm_mock_remains_text_only(provider, monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "llm-mock")
    monkeypatch.delenv("DIALOGUE_PROVIDER", raising=False)
    monkeypatch.setenv("LLM_MOCK_DIALOGUE_REPLY", "旧 mock 台词")

    state, npc, player = _world()
    assert (
        dialogue.generate_dialogue_reply(state, npc, player, "道友，可愿同行？") == "旧 mock 台词"
    )
    turn = _turn(state, npc, player)
    assert turn.reply_text == "旧 mock 台词"
    assert turn.proposal is None and turn.record is None
    assert STUB_INSTANCES == []


def test_dialogue_provider_can_select_mock_independently(provider, monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "openai-compatible")
    monkeypatch.setenv("DIALOGUE_PROVIDER", "llm-mock")
    monkeypatch.setenv("LLM_MOCK_DIALOGUE_REPLY", "独立 mock 台词")

    state, npc, player = _world()
    reply = dialogue.generate_dialogue_reply(state, npc, player, "道友，可愿同行？")
    turn = _turn(state, npc, player)

    assert reply == "独立 mock 台词"
    assert turn.reply_text == "独立 mock 台词"
    assert turn.proposal is None and turn.record is None
    assert STUB_INSTANCES == []


@pytest.mark.parametrize("missing", [None, "LLM_BASE_URL", "LLM_MODEL"])
def test_missing_llm_config_is_explicit(monkeypatch, missing):
    monkeypatch.setenv("AGENT_PROVIDER", "decision-model")
    monkeypatch.setenv("DIALOGUE_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "http://stub.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "stub-model")
    if missing is None:
        monkeypatch.delenv("LLM_BASE_URL")
        monkeypatch.delenv("LLM_MODEL")
    else:
        monkeypatch.delenv(missing)

    state, npc, player = _world()
    with pytest.raises(RuntimeError, match="LLM_BASE_URL and LLM_MODEL") as reply_error:
        dialogue.generate_dialogue_reply(state, npc, player, "道友，可愿同行？")
    assert "DIALOGUE_PROVIDER or AGENT_PROVIDER" in str(reply_error.value)

    with pytest.raises(RuntimeError, match="LLM_BASE_URL and LLM_MODEL"):
        _turn(state, npc, player)
