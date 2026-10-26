"""FastAPI application exposing the authoritative world API.

R1 notes: the WebSocket stream polls the database (0.5s) instead of using an
in-process pub/sub; LLM-backed dialogue is intentionally absent.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from agent_runtime import (
    DecisionRecord,
    LLMPolicy,
    NpcObservation,
    ProposalRejected,
    UtilityPolicy,
    build_observation,
)
from world_core import CommandRejected, WorldCommand
from world_core import snapshot as core_snapshot
from world_server.agent_policy import policy_for
from world_server.config import SETTINGS
from world_server.db import get_engine, get_session_factory, session_dependency
from world_server.dialogue import generate_dialogue_reply
from world_server.memory_store import retrieve_memories
from world_server.repository import (
    IdempotencyConflict,
    NotFound,
    StaleStateVersion,
    apply_command,
    bootstrap,
    causality,
    list_decisions,
    list_events,
    load_snapshot,
    load_state,
    save_decisions,
    save_snapshot,
)
from world_server.summaries import summarize_event

SessionDep = Annotated[Session, Depends(session_dependency)]


def _error(
    code: str, message: str, status: int, details: dict[str, Any] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "details": details or {}},
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    session = get_session_factory(get_engine())()
    try:
        bootstrap(session, SETTINGS.world_seed)
    finally:
        session.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Unwritten Dao World API", version="1.0.0", lifespan=_lifespan)

    @app.exception_handler(CommandRejected)
    async def _rejected(_request: Any, exc: CommandRejected) -> JSONResponse:
        return _error(exc.code, exc.message, 422, exc.details)

    @app.exception_handler(StaleStateVersion)
    async def _stale(_request: Any, exc: StaleStateVersion) -> JSONResponse:
        return _error(
            "stale_state_version",
            str(exc),
            409,
            {"expected": exc.expected, "actual": exc.actual},
        )

    @app.exception_handler(IdempotencyConflict)
    async def _conflict(_request: Any, exc: IdempotencyConflict) -> JSONResponse:
        return _error("idempotency_conflict", str(exc), 409)

    @app.exception_handler(NotFound)
    async def _not_found(_request: Any, exc: NotFound) -> JSONResponse:
        return _error("not_found", str(exc), 404)

    @app.get("/v1/health")
    def health(session: SessionDep) -> dict[str, Any]:
        try:
            state = load_state(session)
            return {"status": "ok", "world_loaded": True, "tick": state.tick}
        except NotFound:
            return {"status": "degraded", "world_loaded": False}

    @app.get("/v1/world/snapshot")
    def world_snapshot(session: SessionDep) -> dict[str, Any]:
        return core_snapshot(load_state(session))

    @app.get("/v1/world/events")
    def world_events(
        session: SessionDep,
        after: int = Query(0, ge=0),
        limit: int = Query(200, ge=1, le=1000),
        type: str | None = Query(None),
    ) -> dict[str, Any]:
        events = list_events(session, after=after, limit=limit, event_type=type)
        return {"events": [event.model_dump(mode="json") for event in events]}

    @app.get("/v1/npcs/{npc_id}")
    def get_npc(npc_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
        state = load_state(session)
        npc = state.npcs.get(str(npc_id))
        if npc is None:
            raise NotFound(f"unknown npc {npc_id}")
        return npc.model_dump(mode="json")

    @app.get("/v1/npcs/{npc_id}/observation")
    def get_observation(npc_id: uuid.UUID, session: SessionDep) -> NpcObservation:
        state = load_state(session)
        if str(npc_id) not in state.npcs:
            raise NotFound(f"unknown npc {npc_id}")
        return _observation(session, state, str(npc_id))

    @app.post("/v1/commands")
    def submit_command(session: SessionDep, command: dict[str, Any]) -> dict[str, Any]:
        parsed = WorldCommand.model_validate(command)
        return apply_command(session, parsed).model_dump(mode="json")

    @app.post("/v1/agents/{npc_id}/decision")
    def request_decision(npc_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
        state = load_state(session)
        npc = state.npcs.get(str(npc_id))
        if npc is None:
            raise NotFound(f"unknown npc {npc_id}")
        if not npc.alive or npc.active_action is not None:
            raise HTTPException(
                status_code=409,
                detail={"code": "actor_busy", "message": "NPC is dead or mid-action"},
            )
        if os.environ.get("AGENT_PROVIDER", "").strip().lower() == "replay":
            rows = list_decisions(session, npc_id=str(npc_id), tick=state.tick, accepted_only=True)
            if not rows or rows[-1].proposal is None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "replay_fixture_missing",
                        "message": f"no recorded proposal for {npc_id} at tick {state.tick}",
                    },
                )
            return rows[-1].proposal

        observation = _observation(session, state, str(npc_id))
        try:
            selection = policy_for(npc)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "agent_provider_misconfigured", "message": str(exc)},
            ) from exc

        started = time.perf_counter()
        try:
            proposal = selection.policy.decide(observation)
            records = (
                list(selection.policy.records)
                if isinstance(selection.policy, LLMPolicy)
                else [_utility_record(observation, proposal.decision_id, started, error=None)]
            )
        except ProposalRejected as exc:
            proposal = UtilityPolicy().decide(observation)
            records = (
                list(selection.policy.records) if isinstance(selection.policy, LLMPolicy) else []
            )
            records.append(
                _utility_record(
                    observation,
                    f"fallback:{proposal.decision_id}",
                    started,
                    error=f"llm fallback: {exc.code}",
                )
            )
        save_decisions(
            session,
            world_id=state.world_id,
            records=records,
            proposal=proposal,
        )
        return proposal.model_dump(mode="json")

    @app.post("/v1/dialogue")
    def dialogue(payload: dict[str, Any], session: SessionDep) -> dict[str, Any]:
        state = load_state(session)
        npc = state.npcs.get(str(payload.get("npc_id"))) if payload.get("npc_id") else None
        if npc is None:
            raise NotFound(f"unknown npc {payload.get('npc_id')}")
        if not npc.alive:
            raise HTTPException(
                status_code=409,
                detail={"code": "npc_dead", "message": f"{npc.name} is dead"},
            )
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_message", "message": "message must be non-empty"},
            )
        player = state.npcs.get(str(payload.get("player_id") or state.player_id))
        if player is None:
            raise NotFound("unknown player")
        try:
            reply = generate_dialogue_reply(state, npc, player, message.strip()[:2000])
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "agent_provider_misconfigured", "message": str(exc)},
            ) from exc
        return {"reply_text": reply, "proposal": None}

    @app.post("/v1/saves", status_code=201)
    def create_save(session: SessionDep, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return save_snapshot(session, label=(payload or {}).get("label"))

    @app.post("/v1/saves/{save_id}/load")
    def load_save(save_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
        return load_snapshot(session, str(save_id))

    @app.get("/v1/debug/causality/{event_id}")
    def get_causality(
        event_id: int, session: SessionDep, depth: int = Query(8, ge=1, le=20)
    ) -> dict[str, Any]:
        chain = causality(session, event_id, depth=depth)
        return {
            "root_event_id": chain.root_event_id,
            "events": [event.model_dump(mode="json") for event in chain.events],
            "edges": chain.edges,
        }

    @app.websocket("/v1/events/stream")
    async def events_stream(websocket: WebSocket, after: int = 0) -> None:
        await websocket.accept()
        session = get_session_factory(get_engine())()
        cursor = after
        try:
            while True:
                events = list_events(session, after=cursor, limit=200)
                for event in events:
                    await websocket.send_json(event.model_dump(mode="json"))
                    cursor = event.event_id
                await asyncio.sleep(0.5)
        except WebSocketDisconnect:
            pass
        finally:
            session.close()

    return app


def _observation(session: Session, state: Any, npc_id: str) -> NpcObservation:
    recent = list_events(session, after=max(0, state.last_event_id - 50))
    recent_rows = [
        {
            "event_id": event.event_id,
            "tick": event.tick,
            "type": event.type,
            "summary": summarize_event(event.type, event.payload, state),
        }
        for event in recent
    ]
    memories = retrieve_memories(
        session, state, npc_id, recent_event_ids=[event.event_id for event in recent]
    )
    return build_observation(state, npc_id, memories=memories, recent_events=recent_rows)


def _utility_record(
    observation: NpcObservation,
    decision_id: str,
    started: float,
    *,
    error: str | None,
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        npc_id=observation.npc_id,
        tick=observation.tick,
        world_version=observation.world_version,
        provider="utility",
        model_version="rules-v1",
        system_prompt="",
        user_prompt="",
        raw_response=None,
        attempts=1,
        accepted=True,
        error=error,
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
    )


__all__ = ["create_app"]
