from __future__ import annotations

import json

from agent_runtime.dataset import DecisionRecorder, RecordingPolicy, write_jsonl
from agent_runtime.validator import proposal_to_command
from tools.collect_decisions import collect

from agent_runtime import UtilityPolicy, build_observation
from world_core import (
    PROTAGONIST_ID,
    apply_command,
    create_world,
    validate_state,
)


def test_recording_policy_captures_observation_and_outcome() -> None:
    state = create_world(42)
    observation = build_observation(state, PROTAGONIST_ID)
    recorder = DecisionRecorder()
    policy = RecordingPolicy(UtilityPolicy(), recorder, name="utility")
    proposal = policy.decide(observation)

    assert len(recorder.samples) == 1
    sample = recorder.samples[0]
    assert sample.policy == "utility"
    assert sample.chosen_intent == proposal.intent
    assert sample.observation["npc_id"] == PROTAGONIST_ID
    assert "location_ancient_cave" not in str(sample.observation)
    assert "item_foundation_pill" not in str(sample.observation)
    assert sample.event_refs == []
    assert sample.outcome is None

    result = apply_command(state, proposal_to_command(state, proposal))
    sample.outcome = "accepted"
    sample.result_event_ids = [event.event_id for event in result.events]
    assert sample.outcome == "accepted"
    assert sample.result_event_ids
    assert validate_state(state) == []


def test_collect_writes_valid_jsonl(tmp_path) -> None:
    recorder, state = collect(days=1, seed=42, policy_name="utility")
    assert recorder.samples
    assert all(sample.outcome == "accepted" for sample in recorder.samples)
    assert validate_state(state) == []

    path = tmp_path / "decisions.jsonl"
    count = write_jsonl(path, recorder.samples)
    # write_jsonl emits UTF-8 JSONL; decode explicitly so the Windows locale
    # code page (cp936) cannot reinterpret the bytes.
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert count == len(rows) == len(recorder.samples)
    assert rows[0]["schema_version"] == "decision-sample.v1"
    assert rows[0]["available_actions"]
    assert "observation" in rows[0]
    assert "location_ancient_cave" not in json.dumps(rows[0])


def test_collection_is_deterministic() -> None:
    first, _ = collect(days=1, seed=42, policy_name="utility")
    second, _ = collect(days=1, seed=42, policy_name="utility")
    assert [sample.to_dict() for sample in first.samples] == [
        sample.to_dict() for sample in second.samples
    ]


def test_decision_model_policy_can_be_collected() -> None:
    recorder, state = collect(days=1, seed=42, policy_name="decision-model")
    assert recorder.samples
    assert all(sample.policy == "decision-model" for sample in recorder.samples)
    assert all(sample.outcome == "accepted" for sample in recorder.samples)
    assert validate_state(state) == []
