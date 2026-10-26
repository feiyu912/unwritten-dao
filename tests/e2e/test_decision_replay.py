from __future__ import annotations

from tools.replay_decisions import record_and_replay


def test_recorded_model_proposals_replay_exactly() -> None:
    report = record_and_replay(days=5, seed=42)
    assert report["fixtures"] > 0
    assert report["violations"] == []
    assert report["recorded_checksum"] == report["replayed_checksum"]
