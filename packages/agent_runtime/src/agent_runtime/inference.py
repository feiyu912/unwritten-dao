"""Deterministic inference providers for tests and replay."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


class ReplayExhausted(RuntimeError):
    """Raised when replay mode runs out of recorded model responses."""


@dataclass
class MockInferenceProvider:
    """Returns a fixed reply and records every prompt it receives."""

    reply: str | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.reply is not None:
            return self.reply
        return json.dumps(
            {
                "intent": "wait",
                "arguments": {"ticks": 1},
                "rationale_short": "mock provider",
                "confidence": 0.1,
            },
            ensure_ascii=False,
            sort_keys=True,
        )


@dataclass
class ReplayInferenceProvider:
    """Returns recorded responses in order and never performs network I/O."""

    replies: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)
    index: int = 0

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.index >= len(self.replies):
            raise ReplayExhausted("no recorded model response remains")
        reply = self.replies[self.index]
        self.index += 1
        return reply


__all__ = ["MockInferenceProvider", "ReplayExhausted", "ReplayInferenceProvider"]