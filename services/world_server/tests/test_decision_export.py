from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tools.export_decision_samples import export_samples
from world_server.app import create_app

from world_core import PROTAGONIST_ID

pytestmark = pytest.mark.integration


def test_server_samples_export_to_jsonl(session: Any, tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("AGENT_PROVIDER", "decision-model")
    with TestClient(create_app()) as client:
        response = client.post(f"/v1/agents/{PROTAGONIST_ID}/decision")
        assert response.status_code == 200

    path = tmp_path / "samples.jsonl"
    count = export_samples(session, path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert count == len(rows) == 1
    sample = rows[0]
    assert sample["schema_version"] == "policy-decision-record.v1"
    assert sample["policy_name"] == "utility-scoring"
    assert sample["candidates"]
    assert sample["chosen_intent"]
    assert "location_ancient_cave" not in json.dumps(sample["observation"])
