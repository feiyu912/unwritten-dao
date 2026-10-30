from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "WORLD_ADVANCED",
    "NPC_MOVED",
    "CULTIVATION_STARTED",
    "CULTIVATION_COMPLETED",
    "BREAKTHROUGH_ATTEMPT",
    "NPC_DIED",
    "ITEM_TRANSFERRED",
    "ITEM_CONSUMED",
    "LOCATION_INVESTIGATED",
    "SECRET_REALM_DISCOVERED",
    "SECRET_REALM_ENTERED",
    "SECRET_REALM_CLOSED",
    "OPPORTUNITY_CLAIMED",
    "OPPORTUNITY_EXPIRED",
    "COMBAT_RESOLVED",
    "RELATIONSHIP_CHANGED",
    "BELIEF_ACQUIRED",
    "FACTION_UPDATED",
    "KNOWLEDGE_ACQUIRED",
    "COMMITMENT_MADE",
    "COMMITMENT_FULFILLED",
    "COMMITMENT_BROKEN",
]


class WorldEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["world-event.v1"] = "world-event.v1"
    event_id: int = Field(ge=1)
    world_id: str
    tick: int = Field(ge=0)
    type: EventType
    actor_ids: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    location_id: str | None = None
    causal_parent_ids: list[int] = Field(default_factory=list)
    rng_seed: int = Field(ge=0)
    command_id: str | None = None
    state_version_after: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
