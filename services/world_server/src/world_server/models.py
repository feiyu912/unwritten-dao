"""SQLAlchemy tables for the authoritative world server."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class WorldStateRow(Base):
    """The single authoritative current-state row per world."""

    __tablename__ = "world_state"

    world_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tick: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    state_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=_utcnow
    )


class WorldEventRow(Base):
    __tablename__ = "world_event"

    world_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("world_state.world_id"), primary_key=True
    )
    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    target_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    location_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    rng_seed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    command_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    state_version_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=_utcnow
    )

    __table_args__ = (
        Index("ix_world_event_world_tick", "world_id", "tick"),
        Index("ix_world_event_world_type", "world_id", "type"),
    )


class EventEdgeRow(Base):
    __tablename__ = "event_edge"

    world_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("world_state.world_id"), primary_key=True
    )
    parent_event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    child_event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    relation: Mapped[str] = mapped_column(Text, primary_key=True, default="caused_by")


class CommandLogRow(Base):
    __tablename__ = "command_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("world_state.world_id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    command_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    accepted: Mapped[bool] = mapped_column(nullable=False, default=True)
    state_version_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("world_id", "idempotency_key", name="uq_command_idempotency"),
        UniqueConstraint("world_id", "command_id", name="uq_command_id"),
    )


class WorldSnapshotRow(Base):
    __tablename__ = "world_snapshot"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    world_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("world_state.world_id"), nullable=False
    )
    tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    world_seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sim_version: Mapped[str] = mapped_column(Text, nullable=False)
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=_utcnow
    )


class SaveRow(Base):
    __tablename__ = "save"

    save_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    world_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("world_state.world_id"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("world_snapshot.snapshot_id"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=_utcnow
    )


class MemoryEpisodeRow(Base):
    """Reserved for R2 semantic memory; schema ships with the MVP migration."""

    __tablename__ = "memory_episode"

    memory_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    npc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_event_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(nullable=False, default=0.5)
    emotional_valence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    embedding = mapped_column(Vector(768), nullable=True)
    created_tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_recalled_tick: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    recall_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=_utcnow
    )

    __table_args__ = (Index("ix_memory_episode_npc", "npc_id"),)


class AgentDecisionRow(Base):
    """Audit trail of agent decisions (LLM or deterministic fallback)."""

    __tablename__ = "agent_decision"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    world_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("world_state.world_id"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(Text, nullable=False)
    npc_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tick: Mapped[int] = mapped_column(BigInteger, nullable=False)
    world_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    proposal: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), default=_utcnow
    )

    __table_args__ = (Index("ix_agent_decision_world_npc_tick", "world_id", "npc_id", "tick"),)
