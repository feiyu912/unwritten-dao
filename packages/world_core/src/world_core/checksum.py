from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from world_core.errors import SnapshotError
from world_core.models import WorldState

SIM_VERSION = "0.1.0"


def canonical_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def state_checksum(state: WorldState) -> str:
    digest = hashlib.sha256(canonical_json(state).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def snapshot(state: WorldState) -> dict[str, Any]:
    return {
        "schema_version": "world-snapshot.v1",
        "world_id": state.world_id,
        "tick": state.tick,
        "last_event_id": state.last_event_id,
        "state_version": state.state_version,
        "world_seed": state.world_seed,
        "sim_version": SIM_VERSION,
        "ruleset_version": state.ruleset_version,
        "checksum": state_checksum(state),
        "state": state.model_dump(mode="json"),
    }


def restore_snapshot(doc: dict[str, Any]) -> WorldState:
    if doc.get("schema_version") != "world-snapshot.v1":
        raise SnapshotError("unsupported snapshot schema_version")
    state = WorldState.model_validate(doc["state"])
    expected = doc.get("checksum")
    actual = state_checksum(state)
    if expected != actual:
        raise SnapshotError(f"snapshot checksum mismatch: {expected} != {actual}")
    if doc["world_id"] != state.world_id or doc["tick"] != state.tick:
        raise SnapshotError("snapshot envelope disagrees with embedded state")
    return state
