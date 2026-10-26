from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from world_core.events import WorldEvent

if TYPE_CHECKING:
    from world_core.models import WorldState

CommandType = Literal[
    "advance_time",
    "wait",
    "move",
    "start_cultivation",
    "attempt_breakthrough",
    "transfer_item",
    "investigate",
    "enter_secret_realm",
    "claim_opportunity",
    "attack",
]

CommandSource = Literal["player", "agent", "system", "replay", "test"]


class WorldCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["world-command.v1"] = "world-command.v1"
    command_id: str
    idempotency_key: str = Field(min_length=1, max_length=128)
    world_id: str
    actor_id: str | None = None
    issued_tick: int = Field(ge=0)
    expected_state_version: int = Field(ge=0)
    type: CommandType
    arguments: dict[str, Any] = Field(default_factory=dict)
    source: CommandSource = "agent"


class CommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool = True
    state_version: int
    events: list[WorldEvent] = Field(default_factory=list)


def make_command(
    state: WorldState,
    actor_id: str | None,
    command_type: CommandType,
    arguments: dict[str, Any] | None = None,
    *,
    source: CommandSource = "agent",
    idempotency_key: str | None = None,
    command_id: str | None = None,
) -> WorldCommand:
    key = idempotency_key or (
        f"{source}:{actor_id or 'system'}:{command_type}:{state.state_version}"
    )
    return WorldCommand(
        command_id=command_id or str(uuid.uuid4()),
        idempotency_key=key,
        world_id=state.world_id,
        actor_id=actor_id,
        issued_tick=state.tick,
        expected_state_version=state.state_version,
        type=command_type,
        arguments=arguments or {},
        source=source,
    )
