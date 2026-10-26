from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=False)


GoalStatus = Literal["active", "achieved", "failed", "abandoned"]


class Goal(StrictModel):
    goal_id: str
    kind: str
    status: GoalStatus = "active"
    priority: float = Field(default=0.5, ge=0.0, le=1.0)
    params: dict[str, Any] = Field(default_factory=dict)
    created_tick: int = 0


class ActiveAction(StrictModel):
    type: Literal["cultivate", "wait"]
    started_tick: int
    remaining_ticks: int = Field(ge=0)
    total_ticks: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class Npc(StrictModel):
    npc_id: str
    name: str
    canonical_role: str
    faction_id: str | None = None
    alive: bool = True
    birth_tick: int
    lifespan_ticks: int = Field(ge=1)
    realm: int = Field(ge=0)
    stage: int = Field(ge=1)
    qi: int = Field(ge=0)
    foundation: float = Field(default=0.5, ge=0.0, le=1.0)
    health: float = Field(default=1.0, ge=0.0, le=1.0)
    wealth: int = Field(default=0, ge=0)
    aptitude: float = Field(default=0.5, ge=0.0, le=1.0)
    luck: float = Field(default=1.0, ge=0.0)
    technique: str = "basic"
    location_id: str
    traits: dict[str, float] = Field(default_factory=dict)
    goals: list[Goal] = Field(default_factory=list)
    active_action: ActiveAction | None = None
    known_locations: list[str] = Field(default_factory=list)
    inventory: list[str] = Field(default_factory=list)
    death_tick: int | None = None
    death_cause: str | None = None
    last_event_id: int | None = Field(default=None, ge=1)


class Location(StrictModel):
    location_id: str
    name: str
    kind: Literal["town", "sect", "outpost", "wilderness", "ruin", "shop", "secret_realm"]
    faction_id: str | None = None
    aura_multiplier: float = Field(default=1.0, ge=0.0)
    adjacency: list[str] = Field(default_factory=list)
    stash: list[str] = Field(default_factory=list)


class Faction(StrictModel):
    faction_id: str
    name: str
    kind: Literal["sect", "clan"]
    leader_id: str | None = None
    treasury: int = Field(default=0, ge=0)
    income_per_30d: int = Field(default=0, ge=0)
    upkeep_per_member: int = Field(default=0, ge=0)


class Item(StrictModel):
    item_id: str
    name: str
    kind: str
    unique: bool = False
    owner_id: str | None = None
    location_id: str | None = None
    hidden: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)


class Opportunity(StrictModel):
    opportunity_id: str
    name: str
    kind: str
    location_id: str
    reward_item_ids: list[str] = Field(default_factory=list)
    active_from_tick: int = 0
    active_until_tick: int
    claimed_by: str | None = None
    claimed_tick: int | None = None
    expired: bool = False
    base_weight: float = Field(default=1.0, ge=0.0)
    min_realm: int = Field(default=0, ge=0)
    canonical_candidate_id: str | None = None
    canonical_luck_bias: float = Field(default=1.0, ge=0.0)
    requires_map_item_id: str | None = None
    attempts: int = Field(default=0, ge=0)


class SecretRealm(StrictModel):
    realm_id: str
    name: str
    entrance_location_id: str
    interior_location_id: str
    required_item_id: str | None = None
    open_tick: int = 0
    close_tick: int
    opened: bool = True
    discovered_by: list[str] = Field(default_factory=list)


class Relationship(StrictModel):
    source_npc_id: str
    target_npc_id: str
    affinity: int = 0
    trust: int = 0
    fear: int = 0
    respect: int = 0
    debt: int = 0
    last_event_id: int | None = None


class Belief(StrictModel):
    npc_id: str
    subject_key: str
    predicate: str
    object_value: Any = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_event_id: int | None = None
    acquired_tick: int = 0


class WorldState(StrictModel):
    world_id: str
    world_seed: int = Field(ge=0)
    tick: int = Field(default=0, ge=0)
    state_version: int = Field(default=0, ge=0)
    last_event_id: int = Field(default=0, ge=0)
    sim_version: str
    ruleset_version: str
    player_id: str
    npcs: dict[str, Npc] = Field(default_factory=dict)
    locations: dict[str, Location] = Field(default_factory=dict)
    factions: dict[str, Faction] = Field(default_factory=dict)
    items: dict[str, Item] = Field(default_factory=dict)
    opportunities: dict[str, Opportunity] = Field(default_factory=dict)
    secret_realms: dict[str, SecretRealm] = Field(default_factory=dict)
    relationships: dict[str, Relationship] = Field(default_factory=dict)
    beliefs: dict[str, Belief] = Field(default_factory=dict)


def relationship_key(source_npc_id: str, target_npc_id: str) -> str:
    return f"{source_npc_id}|{target_npc_id}"


def belief_key(npc_id: str, subject_key: str, predicate: str) -> str:
    return f"{npc_id}|{subject_key}|{predicate}"
