from __future__ import annotations

from typing import Any


class CommandRejected(Exception):
    """Raised when a command fails validation and no state was mutated."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class SnapshotError(ValueError):
    """Raised when a snapshot cannot be restored or its checksum does not match."""
