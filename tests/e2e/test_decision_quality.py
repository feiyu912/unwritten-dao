from __future__ import annotations

from tools.collect_decisions import collect
from tools.decision_quality import summarize


def test_summary_of_collected_samples() -> None:
    recorder, _ = collect(days=2, seed=42, policy_name="utility")
    rows = [sample.to_dict() for sample in recorder.samples]
    assert rows

    summary = summarize(rows)

    assert summary["samples"] == len(rows)
    assert summary["npcs"] > 0
    assert summary["policies"] == {"utility": len(rows)}
    assert summary["chosen_outside_available"] == 0
    assert summary["acceptance_rate"] is not None
    assert 0.0 <= summary["wait_share"] <= 1.0
    assert summary["action_diversity"] == len(summary["actions"])


def test_rejection_and_invalid_choice_metrics() -> None:
    recorder, _ = collect(days=1, seed=7, policy_name="utility")
    base = recorder.samples[0].to_dict()
    rejected = dict(base, outcome="rejected", rejection_code="stale_state_version")
    invalid = dict(
        base, chosen_intent="wait", available_actions=["move"], outcome="rejected"
    )

    summary = summarize([rejected, invalid])

    assert summary["acceptance_rate"] == 0.0
    assert summary["rejection_codes"] == {"stale_state_version": 1}
    assert summary["chosen_outside_available"] == 1